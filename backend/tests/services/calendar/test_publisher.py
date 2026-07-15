from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.calendar.publisher import (
    CalendarCalledActor,
    CalendarPublishError,
    CalendarSession,
    FakeCalendarPublisher,
    GoogleCalendarPublisher,
    _google_event_payload,
    build_event_previews,
    build_google_auth_url,
)

TZ = ZoneInfo("America/Toronto")


def session() -> CalendarSession:
    return CalendarSession(
        7,
        "A1S3",
        datetime(2026, 7, 14, 18, tzinfo=TZ),
        datetime(2026, 7, 14, 20, tzinfo=TZ),
        (CalendarCalledActor("Hamlet", "Rina Feng", "rina@example.com"),),
    )


class RecordingTransport:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.events: list[dict[str, object]] = []

    def create_event(self, *, calendar_id: str, access_token: str, event: dict[str, object]) -> str:
        assert calendar_id == "primary"
        assert access_token == "token"
        self.events.append(event)
        if self.fails:
            raise OSError("calendar unavailable")
        return "google-event-7"


def test_event_preview_has_required_title_description_and_invite() -> None:
    preview = build_event_previews((session(),))[0]
    assert preview.title == "REHEARSAL // A1S3"
    assert "HAMLET // RINA FENG" in preview.description
    assert preview.attendee_emails == ("rina@example.com",)


def test_fake_publisher_is_deterministic() -> None:
    report = FakeCalendarPublisher().publish((session(),))
    assert report.published_count == 1
    assert report.events[0].event_id == "fake-event-7"


def test_google_publisher_uses_transport_interface() -> None:
    transport = RecordingTransport()
    report = GoogleCalendarPublisher(access_token="token", transport=transport).publish(
        (session(),)
    )
    assert report.published_count == 1
    assert report.events[0].event_id == "google-event-7"
    assert transport.events[0]["summary"] == "REHEARSAL // A1S3"


def test_google_publisher_reports_calendar_failure() -> None:
    report = GoogleCalendarPublisher(
        access_token="token", transport=RecordingTransport(fails=True)
    ).publish((session(),))
    assert report.failed_count == 1
    assert report.events[0].status == "FAILED"


def test_calendar_helpers_are_directly_covered() -> None:
    preview = build_event_previews((session(),))[0]
    assert _google_event_payload(preview)["attendees"] == [{"email": "rina@example.com"}]
    auth_url = build_google_auth_url("client", "http://localhost/callback", "state")
    assert auth_url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert parse_qs(urlparse(auth_url).query)["scope"] == [
        "https://www.googleapis.com/auth/calendar.freebusy"
    ]
    with pytest.raises(CalendarPublishError, match="required"):
        build_google_auth_url("", "", "")
    with pytest.raises(CalendarPublishError, match="access token"):
        GoogleCalendarPublisher(access_token="")
