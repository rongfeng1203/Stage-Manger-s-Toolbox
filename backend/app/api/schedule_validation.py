from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.scheduling.validation import (
    ScheduleValidationInput,
    ValidationActor,
    ValidationAvailability,
    ValidationScene,
    ValidationSession,
    validate_schedule,
)

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class ActorPayload(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1)


class AvailabilityPayload(BaseModel):
    actor_id: int = Field(gt=0)
    start: datetime
    end: datetime
    availability_type: str


class ScenePayload(BaseModel):
    id: int = Field(gt=0)
    scene_code: str = Field(min_length=1)
    target_rehearsal_minutes: int = Field(ge=0)


class SessionPayload(BaseModel):
    id: int = Field(gt=0)
    scene_id: int = Field(gt=0)
    scene_code: str = Field(min_length=1)
    actor_ids: list[int]
    start: datetime
    end: datetime
    duration_minutes: int = Field(gt=0)


class ValidateSchedulePayload(BaseModel):
    actors: list[ActorPayload]
    availability: list[AvailabilityPayload]
    scenes: list[ScenePayload]
    sessions: list[SessionPayload]
    timezone: str = "America/Toronto"
    slot_duration_minutes: int = Field(default=30, gt=0)
    minimum_session_minutes: int = Field(default=60, gt=0)


@router.post("/validate")
def validate_schedule_route(payload: ValidateSchedulePayload) -> dict[str, object]:
    try:
        timezone = ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=422, detail="unknown timezone") from error

    try:
        result = validate_schedule(
            ScheduleValidationInput(
                actors=tuple(ValidationActor(item.id, item.name) for item in payload.actors),
                availability=tuple(
                    ValidationAvailability(
                        actor_id=item.actor_id,
                        start=_with_timezone(item.start, timezone),
                        end=_with_timezone(item.end, timezone),
                        availability_type=item.availability_type,
                    )
                    for item in payload.availability
                ),
                scenes=tuple(
                    ValidationScene(
                        item.id,
                        item.scene_code,
                        item.target_rehearsal_minutes,
                    )
                    for item in payload.scenes
                ),
                sessions=tuple(
                    ValidationSession(
                        id=item.id,
                        scene_id=item.scene_id,
                        scene_code=item.scene_code,
                        actor_ids=frozenset(item.actor_ids),
                        start=_with_timezone(item.start, timezone),
                        end=_with_timezone(item.end, timezone),
                        duration_minutes=item.duration_minutes,
                    )
                    for item in payload.sessions
                ),
                slot_duration_minutes=payload.slot_duration_minutes,
                minimum_session_minutes=payload.minimum_session_minutes,
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return {
        "valid": result.valid,
        "conflicts": [
            {"code": conflict.code, "message": conflict.message} for conflict in result.conflicts
        ],
        "debts": [
            {
                "sceneCode": debt.scene_code,
                "requiredMinutes": debt.required_minutes,
                "scheduledMinutes": debt.scheduled_minutes,
                "remainingMinutes": debt.remaining_minutes,
            }
            for debt in result.debts
        ],
    }


def _with_timezone(value: datetime, timezone: ZoneInfo) -> datetime:
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value
    localized = value.replace(tzinfo=timezone)
    round_trip = localized.astimezone(ZoneInfo("UTC")).astimezone(timezone).replace(tzinfo=None)
    if round_trip != value:
        raise ValueError(f"local time does not exist in {timezone.key}: {value.isoformat()}")
    alternate = value.replace(tzinfo=timezone, fold=1)
    if localized.utcoffset() != alternate.utcoffset():
        raise ValueError(f"local time is ambiguous in {timezone.key}: {value.isoformat()}")
    return localized
