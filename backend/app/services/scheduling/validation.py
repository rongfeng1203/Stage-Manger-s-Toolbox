from dataclasses import dataclass
from datetime import datetime

from backend.app.services.availability.time_windows import TimeWindow, subtract_busy_windows
from backend.app.services.scheduling.conflicts import (
    ActorBusyConflict,
    ActorOverlapConflict,
    ConflictContext,
    ExistingSession,
    SceneInput,
    SessionLengthConflict,
    SlotAlignmentConflict,
    can_schedule_scene,
)


@dataclass(frozen=True, slots=True)
class ValidationActor:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class ValidationAvailability:
    actor_id: int
    start: datetime
    end: datetime
    availability_type: str


@dataclass(frozen=True, slots=True)
class ValidationScene:
    id: int
    scene_code: str
    target_rehearsal_minutes: int


@dataclass(frozen=True, slots=True)
class ValidationSession:
    id: int
    scene_id: int
    scene_code: str
    actor_ids: frozenset[int]
    start: datetime
    end: datetime
    duration_minutes: int


@dataclass(frozen=True, slots=True)
class ValidationConflict:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SceneDebt:
    scene_code: str
    required_minutes: int
    scheduled_minutes: int
    remaining_minutes: int


@dataclass(frozen=True, slots=True)
class ScheduleValidationInput:
    actors: tuple[ValidationActor, ...]
    availability: tuple[ValidationAvailability, ...]
    scenes: tuple[ValidationScene, ...]
    sessions: tuple[ValidationSession, ...]
    slot_duration_minutes: int = 30
    minimum_session_minutes: int = 60


@dataclass(frozen=True, slots=True)
class ScheduleValidationResult:
    valid: bool
    conflicts: tuple[ValidationConflict, ...]
    debts: tuple[SceneDebt, ...]


def validate_schedule(payload: ScheduleValidationInput) -> ScheduleValidationResult:
    _require_unique_ids("actor", [actor.id for actor in payload.actors])
    _require_unique_ids("scene", [scene.id for scene in payload.scenes])
    _require_unique_ids("session", [session.id for session in payload.sessions])
    actor_names = {actor.id: actor.name for actor in payload.actors}
    availability = _effective_availability(payload.availability)
    conflicts: list[ValidationConflict] = []

    for session in sorted(payload.sessions, key=lambda item: (item.start, item.id)):
        existing = [
            ExistingSession(
                id=item.id,
                scene_id=item.scene_id,
                actor_ids=item.actor_ids,
                window=TimeWindow(item.start, item.end),
            )
            for item in payload.sessions
            if item.id != session.id
        ]
        check = can_schedule_scene(
            scene=SceneInput(session.scene_id, session.scene_code, session.actor_ids),
            start=session.start,
            duration_minutes=session.duration_minutes,
            context=ConflictContext(
                availability_by_actor=availability,
                existing_sessions=existing,
                slot_duration_minutes=payload.slot_duration_minutes,
                minimum_session_minutes=payload.minimum_session_minutes,
            ),
        )
        conflicts.extend(
            _format_conflict(conflict, session, actor_names) for conflict in check.conflicts
        )

    debts = _calculate_debts(payload.scenes, payload.sessions)
    for debt in debts:
        if debt.scheduled_minutes > debt.required_minutes:
            conflicts.append(
                ValidationConflict(
                    "SCENE_TARGET_EXCEEDED",
                    f"{debt.scene_code}: SCHEDULED MINUTES EXCEED TARGET",
                )
            )

    unique = tuple({(item.code, item.message): item for item in conflicts}.values())
    return ScheduleValidationResult(valid=not unique, conflicts=unique, debts=debts)


def _effective_availability(
    items: tuple[ValidationAvailability, ...],
) -> dict[int, list[TimeWindow]]:
    available: dict[int, list[TimeWindow]] = {}
    busy: dict[int, list[TimeWindow]] = {}
    for item in items:
        window = TimeWindow(item.start, item.end)
        if item.availability_type.upper() == "BUSY":
            busy.setdefault(item.actor_id, []).append(window)
        elif item.availability_type.upper() in {"AVAILABLE", "PREFERRED"}:
            available.setdefault(item.actor_id, []).append(window)
        else:
            raise ValueError(f"unknown availability type: {item.availability_type}")
    return {
        actor_id: subtract_busy_windows(windows, busy.get(actor_id, []))
        for actor_id, windows in available.items()
    }


def _format_conflict(
    conflict: ActorBusyConflict
    | ActorOverlapConflict
    | SessionLengthConflict
    | SlotAlignmentConflict,
    session: ValidationSession,
    actor_names: dict[int, str],
) -> ValidationConflict:
    if isinstance(conflict, ActorBusyConflict):
        name = actor_names.get(conflict.actor_id, f"ACTOR {conflict.actor_id}")
        return ValidationConflict(
            "ACTOR_BUSY",
            f"{session.scene_code}: {name} BUSY {_time_range(session)}",
        )
    if isinstance(conflict, ActorOverlapConflict):
        name = actor_names.get(conflict.actor_id, f"ACTOR {conflict.actor_id}")
        return ValidationConflict(
            "ACTOR_OVERLAP",
            f"{session.scene_code}: {name} DOUBLE BOOKED {_time_range(session)}",
        )
    if isinstance(conflict, SessionLengthConflict):
        return ValidationConflict(
            "SESSION_TOO_SHORT",
            f"{session.scene_code}: SESSION SHORTER THAN {conflict.minimum_minutes} MIN",
        )
    return ValidationConflict(
        "SLOT_ALIGNMENT",
        f"{session.scene_code}: START IS NOT SLOT ALIGNED",
    )


def _calculate_debts(
    scenes: tuple[ValidationScene, ...],
    sessions: tuple[ValidationSession, ...],
) -> tuple[SceneDebt, ...]:
    return tuple(
        SceneDebt(
            scene_code=scene.scene_code,
            required_minutes=scene.target_rehearsal_minutes,
            scheduled_minutes=sum(
                session.duration_minutes for session in sessions if session.scene_id == scene.id
            ),
            remaining_minutes=max(
                0,
                scene.target_rehearsal_minutes
                - sum(
                    session.duration_minutes for session in sessions if session.scene_id == scene.id
                ),
            ),
        )
        for scene in scenes
    )


def _time_range(session: ValidationSession) -> str:
    return f"{session.start:%H:%M}-{session.end:%H:%M}"


def _require_unique_ids(label: str, values: list[int]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} id")
