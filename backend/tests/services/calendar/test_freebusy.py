from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from backend.app.services.availability.time_windows import TimeWindow
from backend.app.services.calendar.freebusy import (
    ActorCalendar,
    CalendarBusyResult,
    import_google_availability,
    verify_google_freebusy_connection,
)

TZ = ZoneInfo("America/Toronto")


class RecordingFreeBusyTransport:
    def __init__(self, results: dict[str, CalendarBusyResult]) -> None:
        self.results = results
        self.calendar_ids: tuple[str, ...] = ()

    def query(
        self,
        *,
        access_token: str,
        time_min: datetime,
        time_max: datetime,
        timezone: ZoneInfo,
        calendar_ids: tuple[str, ...],
    ) -> dict[str, CalendarBusyResult]:
        assert access_token == "token"
        assert time_min == datetime(2026, 7, 14, 18, tzinfo=TZ)
        assert time_max.hour == 22
        assert time_max > time_min
        assert timezone == TZ
        self.calendar_ids = calendar_ids
        return self.results


def test_freebusy_import_subtracts_busy_time_and_reports_inaccessible_calendars() -> None:
    transport = RecordingFreeBusyTransport(
        {
            "rina@example.com": CalendarBusyResult(
                (
                    TimeWindow(
                        datetime(2026, 7, 14, 19, tzinfo=TZ),
                        datetime(2026, 7, 14, 20, tzinfo=TZ),
                    ),
                )
            ),
            "maya@school.edu": CalendarBusyResult((), "FORBIDDEN"),
        }
    )
    imported = import_google_availability(
        actors=(
            ActorCalendar(1, "Rina@example.com"),
            ActorCalendar(2, "maya@school.edu"),
            ActorCalendar(3, ""),
        ),
        start_date=date(2026, 7, 14),
        end_date=date(2026, 7, 14),
        daily_start=time(18),
        daily_end=time(22),
        timezone=TZ,
        access_token="token",
        transport=transport,
    )
    assert transport.calendar_ids == ("rina@example.com", "maya@school.edu")
    assert imported.imported_actor_ids == (1,)
    assert [(item.start.hour, item.end.hour) for item in imported.windows] == [
        (18, 19),
        (20, 22),
    ]
    assert [(item.actor_id, item.reason) for item in imported.errors] == [
        (3, "MISSING_EMAIL"),
        (2, "FORBIDDEN"),
    ]


def test_freebusy_import_returns_full_daily_windows_when_calendar_is_clear() -> None:
    imported = import_google_availability(
        actors=(ActorCalendar(1, "rina@example.com"),),
        start_date=date(2026, 7, 14),
        end_date=date(2026, 7, 15),
        daily_start=time(18),
        daily_end=time(22),
        timezone=TZ,
        access_token="token",
        transport=RecordingFreeBusyTransport({"rina@example.com": CalendarBusyResult(())}),
    )
    assert len(imported.windows) == 2
    assert imported.windows[1].start.date() == date(2026, 7, 15)


class PrimaryCalendarTransport:
    def query(
        self,
        *,
        access_token: str,
        time_min: datetime,
        time_max: datetime,
        timezone: ZoneInfo,
        calendar_ids: tuple[str, ...],
    ) -> dict[str, CalendarBusyResult]:
        assert access_token == "token"
        assert time_max > time_min
        assert timezone == ZoneInfo("UTC")
        assert calendar_ids == ("primary",)
        return {"primary": CalendarBusyResult(())}


def test_freebusy_connection_verifies_primary_calendar() -> None:
    verify_google_freebusy_connection(
        access_token="token",
        transport=PrimaryCalendarTransport(),
    )
