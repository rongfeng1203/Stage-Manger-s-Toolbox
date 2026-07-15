import json
import os
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.app.services.calendar.https import google_ssl_context


class GoogleOAuthError(ValueError):
    """Raised when local Google OAuth configuration or tokens are invalid."""


@dataclass(frozen=True, slots=True)
class GoogleOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    auth_uri: str = "https://accounts.google.com/o/oauth2/auth"
    token_uri: str = "https://oauth2.googleapis.com/token"


class OAuthHTTPTransport(Protocol):
    def post_form(self, url: str, fields: dict[str, str]) -> dict[str, object]: ...


class OAuthTokenStorage(Protocol):
    def load(self) -> dict[str, object] | None: ...

    def save(self, token: dict[str, object]) -> None: ...

    def is_connected(self) -> bool: ...


class GoogleOAuthHTTPTransport:
    def post_form(self, url: str, fields: dict[str, str]) -> dict[str, object]:
        request = Request(
            url,
            data=urlencode(fields).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15, context=google_ssl_context()) as response:  # noqa: S310
                return _json_object(response.read())
        except HTTPError as error:
            raise GoogleOAuthError("Google rejected the OAuth token request") from error
        except OSError as error:
            raise GoogleOAuthError("Google OAuth token service is unavailable") from error


class OAuthTokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, object] | None:
        try:
            return _json_object(self.path.read_text())
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            raise GoogleOAuthError("stored Google OAuth token is unreadable") from error

    def save(self, token: dict[str, object]) -> None:
        _secure_write_json(self.path, token)

    def is_connected(self) -> bool:
        token = self.load()
        return token is not None and _token_is_connected(token)


class OAuthEnvironmentTokenStore:
    """Use a refresh token supplied by a deployment secret."""

    def __init__(self, refresh_token: str) -> None:
        self._token: dict[str, object] = {"refresh_token": refresh_token}

    def load(self) -> dict[str, object]:
        return dict(self._token)

    def save(self, token: dict[str, object]) -> None:
        self._token = dict(token)

    def is_connected(self) -> bool:
        return _token_is_connected(self._token)


class OAuthStateStore:
    def __init__(self, path: Path, *, lifetime_seconds: int = 600) -> None:
        self.path = path
        self.lifetime_seconds = lifetime_seconds

    def issue(self, *, now: float | None = None) -> str:
        issued_at = time.time() if now is None else now
        state = secrets.token_urlsafe(32)
        states = self._load_states()
        active = {key: expires_at for key, expires_at in states.items() if expires_at > issued_at}
        active[state] = issued_at + self.lifetime_seconds
        _secure_write_json(self.path, {"states": active})
        return state

    def consume(self, state: str, *, now: float | None = None) -> None:
        if not state:
            raise GoogleOAuthError("OAuth state is missing")
        checked_at = time.time() if now is None else now
        states = self._load_states()
        matched = next((key for key in states if secrets.compare_digest(key, state)), None)
        if matched is None or states[matched] <= checked_at:
            raise GoogleOAuthError("OAuth state is invalid or expired")
        del states[matched]
        _secure_write_json(
            self.path,
            {"states": {key: value for key, value in states.items() if value > checked_at}},
        )

    def _load_states(self) -> dict[str, float]:
        try:
            payload = _json_object(self.path.read_text())
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            raise GoogleOAuthError("stored OAuth state is unreadable") from error
        raw_states = payload.get("states")
        if not isinstance(raw_states, dict):
            return {}
        return {
            key: _number(value, 0.0) for key, value in raw_states.items() if isinstance(key, str)
        }


def load_google_oauth_config(path: Path | None = None) -> GoogleOAuthConfig:
    env_client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    env_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    env_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if env_client_id and env_client_secret and env_redirect_uri:
        return GoogleOAuthConfig(env_client_id, env_client_secret, env_redirect_uri)

    config_path = (
        path
        or Path(
            os.getenv(
                "GOOGLE_OAUTH_CONFIG",
                "~/.config/stage-scheduler/google-oauth.json",
            )
        ).expanduser()
    )
    try:
        payload = _json_object(config_path.read_text())
    except FileNotFoundError as error:
        raise GoogleOAuthError("Google OAuth credentials are not configured") from error
    except (OSError, json.JSONDecodeError) as error:
        raise GoogleOAuthError("Google OAuth credentials are unreadable") from error

    web = payload.get("web")
    if not isinstance(web, dict):
        raise GoogleOAuthError("Google OAuth credential file is missing web configuration")
    client_id = _required_string(web, "client_id")
    client_secret = _required_string(web, "client_secret")
    redirect_uris = web.get("redirect_uris")
    file_redirect = (
        next((value for value in redirect_uris if isinstance(value, str) and value), "")
        if isinstance(redirect_uris, list)
        else ""
    )
    redirect_uri = env_redirect_uri or file_redirect
    if not redirect_uri:
        raise GoogleOAuthError("Google OAuth redirect URI is not configured")
    return GoogleOAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        auth_uri=_optional_string(web, "auth_uri", "https://accounts.google.com/o/oauth2/auth"),
        token_uri=_optional_string(web, "token_uri", "https://oauth2.googleapis.com/token"),
    )


def default_google_token_store() -> OAuthTokenStorage:
    environment_refresh_token = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip()
    if environment_refresh_token:
        return OAuthEnvironmentTokenStore(environment_refresh_token)
    path = Path(
        os.getenv(
            "GOOGLE_OAUTH_TOKEN_FILE",
            "~/.config/stage-scheduler/google-token.json",
        )
    ).expanduser()
    return OAuthTokenStore(path)


def default_google_state_store() -> OAuthStateStore:
    path = Path(
        os.getenv(
            "GOOGLE_OAUTH_STATE_FILE",
            "~/.config/stage-scheduler/google-oauth-state.json",
        )
    ).expanduser()
    return OAuthStateStore(path)


def exchange_authorization_code(
    config: GoogleOAuthConfig,
    code: str,
    token_store: OAuthTokenStorage,
    *,
    transport: OAuthHTTPTransport | None = None,
    now: Callable[[], float] = time.time,
) -> None:
    if not code:
        raise GoogleOAuthError("Google authorization code is missing")
    payload = (transport or GoogleOAuthHTTPTransport()).post_form(
        config.token_uri,
        {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": config.redirect_uri,
        },
    )
    _save_token_response(payload, token_store, now=now())


def get_valid_access_token(
    config: GoogleOAuthConfig,
    token_store: OAuthTokenStorage,
    *,
    transport: OAuthHTTPTransport | None = None,
    now: Callable[[], float] = time.time,
) -> str:
    token = token_store.load()
    if token is None:
        raise GoogleOAuthError("Google Calendar is not connected")
    access_token = token.get("access_token")
    if (
        isinstance(access_token, str)
        and access_token
        and _number(token.get("expires_at"), 0.0) > now() + 60
    ):
        return access_token

    refresh_token = token.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise GoogleOAuthError("Google Calendar connection has expired; reconnect it")
    payload = (transport or GoogleOAuthHTTPTransport()).post_form(
        config.token_uri,
        {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    _save_token_response(payload, token_store, now=now(), refresh_token=refresh_token)
    refreshed = token_store.load()
    if refreshed is None or not isinstance(refreshed.get("access_token"), str):
        raise GoogleOAuthError("Google did not return a usable access token")
    return str(refreshed["access_token"])


def _save_token_response(
    payload: dict[str, object],
    token_store: OAuthTokenStorage,
    *,
    now: float,
    refresh_token: str = "",
) -> None:
    access_token = _required_string(payload, "access_token")
    returned_refresh = payload.get("refresh_token")
    stored_refresh = returned_refresh if isinstance(returned_refresh, str) else refresh_token
    expires_in = max(1.0, _number(payload.get("expires_in"), 3600.0))
    token_store.save(
        {
            "access_token": access_token,
            "refresh_token": stored_refresh,
            "expires_at": now + expires_in,
            "scope": _optional_string(payload, "scope", ""),
            "token_type": _optional_string(payload, "token_type", "Bearer"),
        }
    )


def _secure_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def _json_object(raw: str | bytes) -> dict[str, object]:
    parsed: object = json.loads(raw)
    if not isinstance(parsed, dict):
        raise GoogleOAuthError("Google OAuth response must be a JSON object")
    return {str(key): value for key, value in parsed.items()}


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GoogleOAuthError(f"Google OAuth value is missing: {key}")
    return value


def _optional_string(payload: Mapping[str, object], key: str, default: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) and value else default


def _number(value: object, default: float) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return default


def _token_is_connected(token: Mapping[str, object]) -> bool:
    refresh_token = token.get("refresh_token")
    if isinstance(refresh_token, str) and bool(refresh_token):
        return True
    access_token = token.get("access_token")
    return (
        isinstance(access_token, str)
        and bool(access_token)
        and _number(token.get("expires_at"), 0.0) > time.time()
    )
