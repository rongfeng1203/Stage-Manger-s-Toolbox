from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.app.services.availability.time_windows import (
    TimeWindow,
    _add_elapsed_time,
    intersect_windows,
    is_slot_aligned,
    validate_time_window,
)


class ConflictEngineError(ValueError):
    """Raised when conflict engine inputs are structurally invalid."""


@dataclass(frozen=True, slots=True)
class SceneInput:
    id: int
    scene_code: str
    required_actor_ids: frozenset[int]

    def __post_init__(self) -> None:
        _require_positive("scene_id", self.id)
        if not self.scene_code:
            raise ConflictEngineError("scene_code must not be empty")
        for actor_id in self.required_actor_ids:
            _require_positive("actor_id", actor_id)


@dataclass(frozen=True, slots=True)
class ExistingSession:
    id: int
    scene_id: int
    actor_ids: frozenset[int]
    window: TimeWindow

    def __post_init__(self) -> None:
        _require_positive("session_id", self.id)
        _require_positive("scene_id", self.scene_id)
        validate_time_window(self.window)
        for actor_id in self.actor_ids:
            _require_positive("actor_id", actor_id)


@dataclass(frozen=True, slots=True)
class ConflictContext:
    availability_by_actor: dict[int, list[TimeWindow]]
    existing_sessions: list[ExistingSession]
    slot_duration_minutes: int = 30
    minimum_session_minutes: int = 60

    def __post_init__(self) -> None:
        _require_positive("slot_duration_minutes", self.slot_duration_minutes)
        _require_positive("minimum_session_minutes", self.minimum_session_minutes)
        for actor_id, windows in self.availability_by_actor.items():
            _require_positive("actor_id", actor_id)
            for window in windows:
                validate_time_window(window)


@dataclass(frozen=True, slots=True)
class ActorBusyConflict:
    scene_id: int
    actor_id: int
    requested_window: TimeWindow
    available_windows: tuple[TimeWindow, ...]
    message: str

    def __post_init__(self) -> None:
        _validate_conflict_base(self.scene_id, self.message)
        _require_positive("actor_id", self.actor_id)
        validate_time_window(self.requested_window)
        for window in self.available_windows:
            validate_time_window(window)


@dataclass(frozen=True, slots=True)
class ActorOverlapConflict:
    scene_id: int
    actor_id: int
    requested_window: TimeWindow
    existing_session_id: int
    existing_scene_id: int
    existing_window: TimeWindow
    message: str

    def __post_init__(self) -> None:
        _validate_conflict_base(self.scene_id, self.message)
        _require_positive("actor_id", self.actor_id)
        _require_positive("existing_session_id", self.existing_session_id)
        _require_positive("existing_scene_id", self.existing_scene_id)
        validate_time_window(self.requested_window)
        validate_time_window(self.existing_window)


@dataclass(frozen=True, slots=True)
class SessionLengthConflict:
    scene_id: int
    requested_minutes: int
    minimum_minutes: int
    message: str

    def __post_init__(self) -> None:
        _validate_conflict_base(self.scene_id, self.message)
        _require_positive("requested_minutes", self.requested_minutes)
        _require_positive("minimum_minutes", self.minimum_minutes)


@dataclass(frozen=True, slots=True)
class SlotAlignmentConflict:
    scene_id: int
    requested_start: datetime
    slot_duration_minutes: int
    message: str

    def __post_init__(self) -> None:
        _validate_conflict_base(self.scene_id, self.message)
        _require_positive("slot_duration_minutes", self.slot_duration_minutes)


type Conflict = (
    ActorBusyConflict | ActorOverlapConflict | SessionLengthConflict | SlotAlignmentConflict
)


@dataclass(frozen=True, slots=True)
class ScheduleCheck:
    valid: bool
    scene_id: int
    session_window: TimeWindow
    conflicts: tuple[Conflict, ...]

    def __post_init__(self) -> None:
        _require_positive("scene_id", self.scene_id)
        validate_time_window(self.session_window)
        if self.valid and self.conflicts:
            raise ConflictEngineError("valid schedule checks cannot include conflicts")


def get_scene_common_availability(scene: SceneInput, context: ConflictContext) -> list[TimeWindow]:
    if not scene.required_actor_ids:
        return []

    actor_ids = sorted(scene.required_actor_ids)
    common = list(context.availability_by_actor.get(actor_ids[0], []))
    for actor_id in actor_ids[1:]:
        common = intersect_windows(common, context.availability_by_actor.get(actor_id, []))
        if not common:
            return []
    return common


def can_schedule_scene(
    *,
    scene: SceneInput,
    start: datetime,
    duration_minutes: int,
    context: ConflictContext,
) -> ScheduleCheck:
    _require_positive("duration_minutes", duration_minutes)
    requested_window = TimeWindow(
        start,
        _add_elapsed_time(start, timedelta(minutes=duration_minutes)),
    )
    validate_time_window(requested_window)
    conflicts: list[Conflict] = []

    if duration_minutes < context.minimum_session_minutes:
        conflicts.append(
            SessionLengthConflict(
                scene_id=scene.id,
                requested_minutes=duration_minutes,
                minimum_minutes=context.minimum_session_minutes,
                message="requested session is shorter than the minimum session length",
            )
        )

    if not _is_aligned_to_any_availability_origin(scene, start, context):
        conflicts.append(
            SlotAlignmentConflict(
                scene_id=scene.id,
                requested_start=start,
                slot_duration_minutes=context.slot_duration_minutes,
                message="requested session start is not slot aligned",
            )
        )

    for actor_id in sorted(scene.required_actor_ids):
        actor_windows = context.availability_by_actor.get(actor_id, [])
        if not _window_is_contained(requested_window, actor_windows):
            conflicts.append(
                ActorBusyConflict(
                    scene_id=scene.id,
                    actor_id=actor_id,
                    requested_window=requested_window,
                    available_windows=tuple(actor_windows),
                    message=(
                        f"actor {actor_id} is not available for the complete requested session"
                    ),
                )
            )

    conflicts.extend(
        detect_actor_overlap(
            scene=scene,
            requested_window=requested_window,
            existing_sessions=context.existing_sessions,
        )
    )

    return ScheduleCheck(
        valid=not conflicts,
        scene_id=scene.id,
        session_window=requested_window,
        conflicts=tuple(conflicts),
    )


def find_valid_session_starts(
    *,
    scene: SceneInput,
    duration_minutes: int,
    context: ConflictContext,
) -> list[datetime]:
    _require_positive("duration_minutes", duration_minutes)
    starts: list[datetime] = []
    for window in get_scene_common_availability(scene, context):
        candidate = window.start
        while _add_elapsed_time(candidate, timedelta(minutes=duration_minutes)) <= window.end:
            check = can_schedule_scene(
                scene=scene,
                start=candidate,
                duration_minutes=duration_minutes,
                context=context,
            )
            if check.valid:
                starts.append(candidate)
            candidate = _add_elapsed_time(
                candidate,
                timedelta(minutes=context.slot_duration_minutes),
            )
    return starts


def detect_actor_overlap(
    *,
    scene: SceneInput,
    requested_window: TimeWindow,
    existing_sessions: list[ExistingSession],
) -> tuple[ActorOverlapConflict, ...]:
    validate_time_window(requested_window)
    conflicts: list[ActorOverlapConflict] = []
    for existing_session in existing_sessions:
        shared_actor_ids = sorted(scene.required_actor_ids.intersection(existing_session.actor_ids))
        if not shared_actor_ids or not _windows_overlap(requested_window, existing_session.window):
            continue
        for actor_id in shared_actor_ids:
            conflicts.append(
                ActorOverlapConflict(
                    scene_id=scene.id,
                    actor_id=actor_id,
                    requested_window=requested_window,
                    existing_session_id=existing_session.id,
                    existing_scene_id=existing_session.scene_id,
                    existing_window=existing_session.window,
                    message=(
                        f"actor {actor_id} is already scheduled for overlapping session "
                        f"{existing_session.id}"
                    ),
                )
            )
    return tuple(conflicts)


def _window_is_contained(window: TimeWindow, containing_windows: list[TimeWindow]) -> bool:
    return any(
        container.start <= window.start and window.end <= container.end
        for container in containing_windows
    )


def _windows_overlap(left: TimeWindow, right: TimeWindow) -> bool:
    return left.start < right.end and right.start < left.end


def _is_aligned_to_any_availability_origin(
    scene: SceneInput,
    start: datetime,
    context: ConflictContext,
) -> bool:
    for actor_id in scene.required_actor_ids:
        for window in context.availability_by_actor.get(actor_id, []):
            if is_slot_aligned(start, window.start, context.slot_duration_minutes):
                return True
    return False


def _validate_conflict_base(scene_id: int, message: str) -> None:
    _require_positive("scene_id", scene_id)
    if not message:
        raise ConflictEngineError("conflict message must not be empty")


def _require_positive(label: str, value: int) -> None:
    if value <= 0:
        raise ConflictEngineError(f"{label} must be positive")
