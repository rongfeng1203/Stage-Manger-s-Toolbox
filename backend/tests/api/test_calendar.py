from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

import backend.app.api.calendar as calendar_api
from backend.app.main import app
from backend.app.services.calendar import (
    CalendarAvailabilityImport,
    CalendarImportError,
    GoogleOAuthConfig,
    ImportedAvailabilityWindow,
    OAuthTokenStore,
)

client = TestClient(app)


def calendar_payload() -> dict[str, object]:
    return {
        "sessions": [
            {
                "id": 1,
                "scene_code": "A1S1",
                "start": "2026-07-14T18:00",
                "end": "2026-07-14T20:00",
                "called": [
                    {
                        "character_name": "Hamlet",
                        "actor_name": "Rina Feng",
                        "email": "rina@example.com",
                    }
                ],
            }
        ],
        "conflicts": [],
        "timezone": "America/Toronto",
    }


def test_calendar_status_exposes_demo_without_google_secrets(monkeypatch: object) -> None:
    response = client.get("/api/calendar/status")
    assert response.status_code == 200
    assert response.json()["demoPublisherAvailable"] is True


def test_calendar_diagnostics_verifies_primary_freebusy(
    monkeypatch: object,
    tmp_path: object,
) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    monkeypatch.setattr(  # type: ignore[attr-defined]
        calendar_api,
        "_google_oauth_config",
        lambda: GoogleOAuthConfig("client", "secret", "http://localhost/callback"),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        calendar_api,
        "default_google_token_store",
        lambda: OAuthTokenStore(tmp_path / "token.json"),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        calendar_api,
        "get_valid_access_token",
        lambda config, store: "token",
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        calendar_api,
        "verify_google_freebusy_connection",
        lambda **kwargs: None,
    )

    response = client.get("/api/calendar/diagnostics")

    assert response.status_code == 200
    assert response.json()["freeBusyReachable"] is True


def test_calendar_preview_summarizes_events() -> None:
    response = client.post("/api/calendar/preview", json=calendar_payload())
    assert response.status_code == 200
    assert response.json()["sessionCount"] == 1
    assert response.json()["invitedActorCount"] == 1
    assert response.json()["events"][0]["title"] == "REHEARSAL // A1S1"


def test_publish_requires_approval_and_clean_conflicts() -> None:
    payload = calendar_payload() | {"approved": False, "provider": "fake"}
    assert client.post("/api/calendar/publish", json=payload).status_code == 409
    payload["approved"] = True
    payload["conflicts"] = ["ACTOR BUSY"]
    assert client.post("/api/calendar/publish", json=payload).status_code == 409


def test_fake_calendar_publish_returns_result_report() -> None:
    payload = calendar_payload() | {"approved": True, "provider": "fake"}
    response = client.post("/api/calendar/publish", json=payload)
    assert response.status_code == 200
    assert response.json() == {
        "publishedCount": 1,
        "failedCount": 0,
        "events": [{"sessionId": 1, "eventId": "fake-event-1", "status": "PUBLISHED"}],
    }


def test_missing_email_and_midnight_crossing_are_previewable() -> None:
    payload = calendar_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    sessions[0]["start"] = "2026-07-14T23:30"
    sessions[0]["end"] = "2026-07-15T00:30"
    called = sessions[0]["called"]
    assert isinstance(called, list)
    called[0]["email"] = ""
    response = client.post("/api/calendar/preview", json=payload)
    assert response.status_code == 200
    assert response.json()["invitedActorCount"] == 0
    assert response.json()["events"][0]["end"].startswith("2026-07-15T00:30")


def test_freebusy_import_serializes_available_windows(
    monkeypatch: object,
    tmp_path: object,
) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    timezone = ZoneInfo("America/Toronto")
    monkeypatch.setattr(  # type: ignore[attr-defined]
        calendar_api,
        "_google_oauth_config",
        lambda: GoogleOAuthConfig("client", "secret", "http://localhost/callback"),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        calendar_api,
        "default_google_token_store",
        lambda: OAuthTokenStore(tmp_path / "token.json"),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        calendar_api,
        "get_valid_access_token",
        lambda config, store: "token",
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        calendar_api,
        "import_google_availability",
        lambda **kwargs: CalendarAvailabilityImport(
            (
                ImportedAvailabilityWindow(
                    1,
                    datetime(2026, 7, 14, 18, tzinfo=timezone),
                    datetime(2026, 7, 14, 22, tzinfo=timezone),
                ),
            ),
            (1,),
            (CalendarImportError(2, "outside@school.edu", "FORBIDDEN"),),
        ),
    )
    response = client.post(
        "/api/calendar/freebusy/import",
        json={
            "actors": [
                {"id": 1, "email": "rina@example.com"},
                {"id": 2, "email": "outside@school.edu"},
            ],
            "start_date": "2026-07-14",
            "end_date": "2026-07-14",
            "daily_start_time": "18:00",
            "daily_end_time": "22:00",
            "timezone": "America/Toronto",
        },
    )
    assert response.status_code == 200
    assert response.json()["windows"] == [
        {
            "actorId": 1,
            "start": "2026-07-14T18:00",
            "end": "2026-07-14T22:00",
            "availabilityType": "AVAILABLE",
        }
    ]
    assert response.json()["errors"][0]["reason"] == "FORBIDDEN"
