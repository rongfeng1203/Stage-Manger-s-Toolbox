import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from backend.app.services.availability.time_windows import TimeWindow, subtract_busy_windows
from backend.app.services.calendar.https import google_ssl_context


class GoogleFreeBusyError(ValueError):
    """Raised when Google free/busy data cannot be read safely."""


@dataclass(frozen=True, slots=True)
class ActorCalendar:
    actor_id: int
    email: str


@dataclass(frozen=True, slots=True)
class CalendarBusyResult:
    busy: tuple[TimeWindow, ...]
    error: str = ""


@dataclass(frozen=True, slots=True)
class ImportedAvailabilityWindow:
    actor_id: int
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class CalendarImportError:
    actor_id: int
    email: str
    reason: str


@dataclass(frozen=True, slots=True)
class CalendarAvailabilityImport:
    windows: tuple[ImportedAvailabilityWindow, ...]
    imported_actor_ids: tuple[int, ...]
    errors: tuple[CalendarImportError, ...]


class GoogleFreeBusyTransport(Protocol):
    def query(
        self,
        *,
        access_token: str,
        time_min: datetime,
        time_max: datetime,
        timezone: ZoneInfo,
        calendar_ids: tuple[str, ...],
    ) -> dict[str, CalendarBusyResult]: ...


class GoogleFreeBusyHTTPTransport:
    def query(
        self,
        *,
        access_token: str,
        time_min: datetime,
        time_max: datetime,
        timezone: ZoneInfo,
        calendar_ids: tuple[str, ...],
    ) -> dict[str, CalendarBusyResult]:
        request = Request(
            "https://www.googleapis.com/calendar/v3/freeBusy",
            data=json.dumps(
                {
                    "timeMin": time_min.isoformat(),
                    "timeMax": time_max.isoformat(),
                    "timeZone": timezone.key,
                    "items": [{"id": calendar_id} for calendar_id in calendar_ids],
                }
            ).encode(),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15, context=google_ssl_context()) as response:  # noqa: S310
                payload = _json_object(response.read())
        except HTTPError as error:
            raise GoogleFreeBusyError("Google rejected the free/busy request") from error
        except OSError as error:
            raise GoogleFreeBusyError("Google Calendar free/busy service is unavailable") from error
        return _calendar_results(payload, calendar_ids)


def import_google_availability(
    *,
    actors: tuple[ActorCalendar, ...],
    start_date: date,
    end_date: date,
    daily_start: time,
    daily_end: time,
    timezone: ZoneInfo,
    access_token: str,
    transport: GoogleFreeBusyTransport | None = None,
) -> CalendarAvailabilityImport:
    if start_date > end_date:
        raise GoogleFreeBusyError("production start date must not follow end date")
    if daily_start >= daily_end:
        raise GoogleFreeBusyError("daily rehearsal start must precede daily end")
    if not access_token:
        raise GoogleFreeBusyError("Google access token is required")

    valid_actors: list[ActorCalendar] = []
    errors: list[CalendarImportError] = []
    for actor in actors:
        email = actor.email.strip().lower()
        if not email or "@" not in email:
            errors.append(CalendarImportError(actor.actor_id, actor.email, "MISSING_EMAIL"))
            continue
        valid_actors.append(ActorCalendar(actor.actor_id, email))

    calendar_ids = tuple(dict.fromkeys(actor.email for actor in valid_actors))
    if len(calendar_ids) > 50:
        raise GoogleFreeBusyError("Google free/busy imports support at most 50 calendars")
    if not calendar_ids:
        return CalendarAvailabilityImport((), (), tuple(errors))

    baseline = _daily_windows(start_date, end_date, daily_start, daily_end, timezone)
    query_results = (transport or GoogleFreeBusyHTTPTransport()).query(
        access_token=access_token,
        time_min=baseline[0].start,
        time_max=baseline[-1].end,
        timezone=timezone,
        calendar_ids=calendar_ids,
    )
    windows: list[ImportedAvailabilityWindow] = []
    imported_actor_ids: list[int] = []
    for actor in valid_actors:
        result = query_results.get(actor.email)
        if result is None:
            errors.append(CalendarImportError(actor.actor_id, actor.email, "NO_RESPONSE"))
            continue
        if result.error:
            errors.append(CalendarImportError(actor.actor_id, actor.email, result.error))
            continue
        imported_actor_ids.append(actor.actor_id)
        effective = subtract_busy_windows(list(baseline), list(result.busy))
        windows.extend(
            ImportedAvailabilityWindow(actor.actor_id, window.start, window.end)
            for window in effective
        )

    return CalendarAvailabilityImport(
        tuple(sorted(windows, key=lambda item: (item.actor_id, item.start))),
        tuple(sorted(set(imported_actor_ids))),
        tuple(errors),
    )


def verify_google_freebusy_connection(
    *,
    access_token: str,
    transport: GoogleFreeBusyTransport | None = None,
) -> None:
    """Verify that the token can read its own primary calendar's free/busy data."""
    if not access_token:
        raise GoogleFreeBusyError("Google access token is required")
    timezone = ZoneInfo("UTC")
    start = datetime.now(timezone)
    result = (transport or GoogleFreeBusyHTTPTransport()).query(
        access_token=access_token,
        time_min=start,
        time_max=start + timedelta(minutes=1),
        timezone=timezone,
        calendar_ids=("primary",),
    ).get("primary")
    if result is None:
        raise GoogleFreeBusyError("Google returned no primary calendar data")
    if result.error:
        raise GoogleFreeBusyError(f"Google primary calendar check failed: {result.error}")


def _daily_windows(
    start_date: date,
    end_date: date,
    daily_start: time,
    daily_end: time,
    timezone: ZoneInfo,
) -> tuple[TimeWindow, ...]:
    windows: list[TimeWindow] = []
    current = start_date
    while current <= end_date:
        windows.append(
            TimeWindow(
                datetime.combine(current, daily_start, tzinfo=timezone),
                datetime.combine(current, daily_end, tzinfo=timezone),
            )
        )
        current += timedelta(days=1)
    return tuple(windows)


def _calendar_results(
    payload: dict[str, object], calendar_ids: tuple[str, ...]
) -> dict[str, CalendarBusyResult]:
    raw_calendars = payload.get("calendars")
    if not isinstance(raw_calendars, dict):
        raise GoogleFreeBusyError("Google free/busy response is missing calendars")
    results: dict[str, CalendarBusyResult] = {}
    for calendar_id in calendar_ids:
        raw_result = raw_calendars.get(calendar_id)
        if not isinstance(raw_result, dict):
            results[calendar_id] = CalendarBusyResult((), "NO_RESPONSE")
            continue
        reason = _calendar_error_reason(raw_result.get("errors"))
        if reason:
            results[calendar_id] = CalendarBusyResult((), reason)
            continue
        raw_busy = raw_result.get("busy")
        busy: list[TimeWindow] = []
        if isinstance(raw_busy, list):
            for item in raw_busy:
                if not isinstance(item, dict):
                    continue
                start = _parse_google_datetime(item.get("start"))
                end = _parse_google_datetime(item.get("end"))
                if start < end:
                    busy.append(TimeWindow(start, end))
        results[calendar_id] = CalendarBusyResult(tuple(busy))
    return results


def _calendar_error_reason(value: object) -> str:
    if not isinstance(value, list) or not value:
        return ""
    first = value[0]
    if not isinstance(first, dict):
        return "CALENDAR_UNAVAILABLE"
    reason = first.get("reason")
    return str(reason).upper() if isinstance(reason, str) else "CALENDAR_UNAVAILABLE"


def _parse_google_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise GoogleFreeBusyError("Google busy window is missing a datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GoogleFreeBusyError("Google busy window contains an invalid datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GoogleFreeBusyError("Google busy window datetime must include a timezone")
    return parsed


def _json_object(raw: str | bytes) -> dict[str, object]:
    parsed: object = json.loads(raw)
    if not isinstance(parsed, dict):
        raise GoogleFreeBusyError("Google free/busy response must be a JSON object")
    return {str(key): value for key, value in parsed.items()}
