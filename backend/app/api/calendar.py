import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from backend.app.services.calendar import (
    ActorCalendar,
    CalendarCalledActor,
    CalendarPublisher,
    CalendarSession,
    FakeCalendarPublisher,
    GoogleCalendarPublisher,
    GoogleFreeBusyError,
    GoogleOAuthConfig,
    GoogleOAuthError,
    build_event_previews,
    build_google_auth_url,
    default_google_state_store,
    default_google_token_store,
    exchange_authorization_code,
    get_valid_access_token,
    import_google_availability,
    load_google_oauth_config,
    verify_google_freebusy_connection,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class CalledActorPayload(BaseModel):
    character_name: str
    actor_name: str
    email: str = ""


class CalendarSessionPayload(BaseModel):
    id: int = Field(gt=0)
    scene_code: str = Field(min_length=1)
    start: datetime
    end: datetime
    called: list[CalledActorPayload]


class CalendarPlanPayload(BaseModel):
    sessions: list[CalendarSessionPayload]
    conflicts: list[str] = []
    timezone: str = "America/Toronto"


class PublishCalendarPayload(CalendarPlanPayload):
    approved: bool
    provider: str = "fake"
    access_token: str = ""


class FreeBusyActorPayload(BaseModel):
    id: int = Field(gt=0)
    email: str = ""


class FreeBusyImportPayload(BaseModel):
    actors: list[FreeBusyActorPayload]
    start_date: date
    end_date: date
    daily_start_time: time
    daily_end_time: time
    timezone: str = "America/Toronto"


@router.get("/status")
def calendar_status() -> dict[str, object]:
    try:
        load_google_oauth_config()
        configured = True
    except GoogleOAuthError:
        configured = False
    try:
        connected = configured and default_google_token_store().is_connected()
    except GoogleOAuthError:
        connected = False
    return {
        "provider": "google",
        "configured": configured,
        "connected": connected,
        "demoPublisherAvailable": True,
        "authUrl": "/api/calendar/oauth/start" if configured else None,
        "scope": "calendar.freebusy",
    }


@router.get("/diagnostics")
def calendar_diagnostics() -> dict[str, object]:
    try:
        config = _google_oauth_config()
    except GoogleOAuthError as error:
        return {
            "configured": False,
            "connected": False,
            "freeBusyReachable": False,
            "message": str(error),
        }
    try:
        access_token = get_valid_access_token(config, default_google_token_store())
    except GoogleOAuthError as error:
        return {
            "configured": True,
            "connected": False,
            "freeBusyReachable": False,
            "message": str(error),
        }
    try:
        verify_google_freebusy_connection(access_token=access_token)
    except GoogleFreeBusyError as error:
        return {
            "configured": True,
            "connected": True,
            "freeBusyReachable": False,
            "message": str(error),
        }
    return {
        "configured": True,
        "connected": True,
        "freeBusyReachable": True,
        "message": "Google primary calendar free/busy is reachable",
    }


@router.get("/oauth/start")
def start_google_oauth() -> RedirectResponse:
    config = _google_oauth_config()
    state = default_google_state_store().issue()
    return RedirectResponse(
        build_google_auth_url(config.client_id, config.redirect_uri, state),
        status_code=302,
    )


@router.get("/oauth/callback")
def finish_google_oauth(
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail="Google authorization was not completed")
    try:
        default_google_state_store().consume(state)
        exchange_authorization_code(
            _google_oauth_config(),
            code,
            default_google_token_store(),
        )
    except GoogleOAuthError as oauth_error:
        raise HTTPException(status_code=400, detail=str(oauth_error)) from oauth_error
    success_url = os.getenv(
        "GOOGLE_OAUTH_SUCCESS_REDIRECT",
        "http://127.0.0.1:5173/#availability",
    )
    return RedirectResponse(success_url, status_code=303)


@router.post("/freebusy/import")
def import_freebusy(payload: FreeBusyImportPayload) -> dict[str, object]:
    try:
        timezone = ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=422, detail="unknown timezone") from error
    try:
        config = _google_oauth_config()
        token_store = default_google_token_store()
        access_token = get_valid_access_token(config, token_store)
        imported = import_google_availability(
            actors=tuple(ActorCalendar(actor.id, actor.email) for actor in payload.actors),
            start_date=payload.start_date,
            end_date=payload.end_date,
            daily_start=payload.daily_start_time,
            daily_end=payload.daily_end_time,
            timezone=timezone,
            access_token=access_token,
        )
    except GoogleOAuthError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except GoogleFreeBusyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "importedActorIds": list(imported.imported_actor_ids),
        "importedActorCount": len(imported.imported_actor_ids),
        "windowCount": len(imported.windows),
        "windows": [
            {
                "actorId": window.actor_id,
                "start": _local_input_datetime(window.start, timezone),
                "end": _local_input_datetime(window.end, timezone),
                "availabilityType": "AVAILABLE",
            }
            for window in imported.windows
        ],
        "errors": [
            {
                "actorId": item.actor_id,
                "email": item.email,
                "reason": item.reason,
            }
            for item in imported.errors
        ],
    }


@router.post("/preview")
def preview_calendar(payload: CalendarPlanPayload) -> dict[str, object]:
    sessions = _calendar_sessions(payload.sessions, payload.timezone)
    previews = build_event_previews(sessions)
    starts = [event.start for event in previews]
    return {
        "sessionCount": len(previews),
        "invitedActorCount": len({email for event in previews for email in event.attendee_emails}),
        "dateRange": (
            {"start": min(starts).date().isoformat(), "end": max(starts).date().isoformat()}
            if starts
            else None
        ),
        "conflictWarnings": payload.conflicts,
        "events": [_event_json(event) for event in previews],
    }


@router.post("/publish")
def publish_calendar(payload: PublishCalendarPayload) -> dict[str, object]:
    if not payload.approved:
        raise HTTPException(status_code=409, detail="schedule must be explicitly approved")
    if payload.conflicts:
        raise HTTPException(status_code=409, detail="resolve schedule conflicts before publishing")
    sessions = _calendar_sessions(payload.sessions, payload.timezone)
    publisher: CalendarPublisher
    if payload.provider == "fake":
        publisher = FakeCalendarPublisher()
    elif payload.provider == "google":
        try:
            publisher = GoogleCalendarPublisher(access_token=payload.access_token)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    else:
        raise HTTPException(status_code=422, detail="unknown calendar provider")
    report = publisher.publish(sessions)
    return {
        "publishedCount": report.published_count,
        "failedCount": report.failed_count,
        "events": [
            {"sessionId": item.session_id, "eventId": item.event_id, "status": item.status}
            for item in report.events
        ],
    }


def _calendar_sessions(
    payload: list[CalendarSessionPayload], timezone_name: str
) -> tuple[CalendarSession, ...]:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=422, detail="unknown timezone") from error
    sessions: list[CalendarSession] = []
    for item in payload:
        start = item.start if item.start.tzinfo else item.start.replace(tzinfo=timezone)
        end = item.end if item.end.tzinfo else item.end.replace(tzinfo=timezone)
        if start >= end:
            raise HTTPException(status_code=422, detail="calendar event start must precede end")
        sessions.append(
            CalendarSession(
                item.id,
                item.scene_code,
                start,
                end,
                tuple(
                    CalendarCalledActor(c.character_name, c.actor_name, c.email)
                    for c in item.called
                ),
            )
        )
    return tuple(sessions)


def _event_json(event: object) -> dict[str, object]:
    from backend.app.services.calendar import CalendarEventPreview

    if not isinstance(event, CalendarEventPreview):
        raise TypeError("expected CalendarEventPreview")
    return {
        "sessionId": event.session_id,
        "title": event.title,
        "description": event.description,
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "attendeeEmails": list(event.attendee_emails),
    }


def _google_oauth_config() -> GoogleOAuthConfig:
    try:
        return load_google_oauth_config()
    except GoogleOAuthError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _local_input_datetime(value: datetime, timezone: ZoneInfo) -> str:
    return value.astimezone(timezone).strftime("%Y-%m-%dT%H:%M")
