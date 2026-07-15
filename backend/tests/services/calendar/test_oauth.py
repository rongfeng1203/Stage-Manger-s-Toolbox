import json
from pathlib import Path

import pytest

from backend.app.services.calendar.https import google_ssl_context
from backend.app.services.calendar.oauth import (
    GoogleOAuthConfig,
    GoogleOAuthError,
    OAuthEnvironmentTokenStore,
    OAuthStateStore,
    OAuthTokenStore,
    exchange_authorization_code,
    get_valid_access_token,
    load_google_oauth_config,
)


class RecordingOAuthTransport:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.requests: list[dict[str, str]] = []

    def post_form(self, url: str, fields: dict[str, str]) -> dict[str, object]:
        assert url == "https://oauth.example/token"
        self.requests.append(fields)
        return self.responses.pop(0)


def oauth_config() -> GoogleOAuthConfig:
    return GoogleOAuthConfig(
        "client-id",
        "client-secret",
        "http://localhost:8000/api/calendar/oauth/callback",
        token_uri="https://oauth.example/token",
    )


def test_load_google_oauth_config_from_download_json(tmp_path: Path) -> None:
    path = tmp_path / "oauth.json"
    path.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                    "redirect_uris": ["http://localhost/callback"],
                }
            }
        )
    )
    config = load_google_oauth_config(path)
    assert config.client_id == "client-id"
    assert config.client_secret == "client-secret"
    assert config.redirect_uri == "http://localhost/callback"


def test_oauth_state_is_single_use_and_expires(tmp_path: Path) -> None:
    store = OAuthStateStore(tmp_path / "state.json", lifetime_seconds=60)
    state = store.issue(now=100)
    store.consume(state, now=120)
    with pytest.raises(GoogleOAuthError, match="invalid or expired"):
        store.consume(state, now=121)
    expired = store.issue(now=200)
    with pytest.raises(GoogleOAuthError, match="invalid or expired"):
        store.consume(expired, now=261)


def test_exchange_and_refresh_store_tokens_with_private_permissions(tmp_path: Path) -> None:
    token_store = OAuthTokenStore(tmp_path / "tokens" / "google.json")
    transport = RecordingOAuthTransport(
        [
            {
                "access_token": "access-one",
                "refresh_token": "refresh-one",
                "expires_in": 30,
                "scope": "calendar.freebusy",
            },
            {"access_token": "access-two", "expires_in": 3600},
        ]
    )
    exchange_authorization_code(
        oauth_config(),
        "authorization-code",
        token_store,
        transport=transport,
        now=lambda: 100,
    )
    assert token_store.path.stat().st_mode & 0o777 == 0o600
    assert token_store.path.parent.stat().st_mode & 0o777 == 0o700

    access_token = get_valid_access_token(
        oauth_config(),
        token_store,
        transport=transport,
        now=lambda: 200,
    )
    assert access_token == "access-two"
    assert transport.requests[0]["grant_type"] == "authorization_code"
    assert transport.requests[1]["grant_type"] == "refresh_token"
    stored = token_store.load()
    assert stored is not None
    assert stored["refresh_token"] == "refresh-one"


def test_missing_token_requires_connection(tmp_path: Path) -> None:
    with pytest.raises(GoogleOAuthError, match="not connected"):
        get_valid_access_token(oauth_config(), OAuthTokenStore(tmp_path / "missing.json"))


def test_environment_token_store_refreshes_without_writing_a_file() -> None:
    store = OAuthEnvironmentTokenStore("deployment-refresh-token")
    transport = RecordingOAuthTransport([{"access_token": "fresh-access", "expires_in": 3600}])

    assert store.is_connected()
    assert get_valid_access_token(
        oauth_config(),
        store,
        transport=transport,
        now=lambda: 100,
    ) == "fresh-access"
    assert transport.requests[0]["refresh_token"] == "deployment-refresh-token"


def test_google_ssl_context_loads_packaged_certificate_authorities() -> None:
    assert google_ssl_context().cert_store_stats()["x509_ca"] > 0
