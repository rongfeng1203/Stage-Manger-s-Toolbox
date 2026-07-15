from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.availability import TimeWindow
from backend.app.services.scheduling import ActorBusyConflict
from backend.app.services.scheduling.validation import (
    ScheduleValidationInput,
    ValidationActor,
    ValidationAvailability,
    ValidationScene,
    ValidationSession,
    _calculate_debts,
    _effective_availability,
    _format_conflict,
    _require_unique_ids,
    _time_range,
    validate_schedule,
)

TZ = ZoneInfo("America/Toronto")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 14, hour, minute, tzinfo=TZ)


def payload(*, start: datetime | None = None, duration: int = 120) -> ScheduleValidationInput:
    session_start = start or at(18)
    return ScheduleValidationInput(
        actors=(ValidationActor(1, "Rina Feng"),),
        availability=(ValidationAvailability(1, at(18), at(22), "AVAILABLE"),),
        scenes=(ValidationScene(1, "A1S1", 120),),
        sessions=(
            ValidationSession(
                1,
                1,
                "A1S1",
                frozenset({1}),
                session_start,
                session_start.replace(hour=session_start.hour + duration // 60),
                duration,
            ),
        ),
    )


def test_validate_schedule_accepts_available_session() -> None:
    result = validate_schedule(payload())
    assert result.valid
    assert result.conflicts == ()
    assert result.debts[0].remaining_minutes == 0


def test_validate_schedule_explains_busy_actor() -> None:
    result = validate_schedule(payload(start=at(17)))
    assert not result.valid
    assert result.conflicts[0].message == "A1S1: Rina Feng BUSY 17:00-19:00"


def test_busy_window_is_subtracted_from_available_window() -> None:
    result = validate_schedule(
        ScheduleValidationInput(
            actors=(ValidationActor(1, "Rina Feng"),),
            availability=(
                ValidationAvailability(1, at(18), at(22), "AVAILABLE"),
                ValidationAvailability(1, at(19), at(20), "BUSY"),
            ),
            scenes=(ValidationScene(1, "A1S1", 120),),
            sessions=(ValidationSession(1, 1, "A1S1", frozenset({1}), at(18), at(20), 120),),
        )
    )
    assert result.conflicts[0].code == "ACTOR_BUSY"


def test_overlap_and_scene_target_are_reported() -> None:
    base = payload()
    second = ValidationSession(2, 1, "A1S1", frozenset({1}), at(18, 30), at(19, 30), 60)
    result = validate_schedule(
        ScheduleValidationInput(
            actors=base.actors,
            availability=base.availability,
            scenes=base.scenes,
            sessions=(*base.sessions, second),
        )
    )
    assert {item.code for item in result.conflicts} == {
        "ACTOR_OVERLAP",
        "SCENE_TARGET_EXCEEDED",
    }


def test_helpers_are_directly_covered() -> None:
    availability = _effective_availability(
        (ValidationAvailability(1, at(18), at(22), "AVAILABLE"),)
    )
    assert availability == {1: [TimeWindow(at(18), at(22))]}
    session = payload().sessions[0]
    assert _time_range(session) == "18:00-20:00"
    assert _calculate_debts(payload().scenes, payload().sessions)[0].scheduled_minutes == 120
    conflict = ActorBusyConflict(
        scene_id=1,
        actor_id=1,
        requested_window=TimeWindow(at(18), at(20)),
        available_windows=(),
        message="busy",
    )
    assert _format_conflict(conflict, session, {1: "Rina Feng"}).code == "ACTOR_BUSY"


def test_unknown_availability_type_is_rejected() -> None:
    bad = (ValidationAvailability(1, at(18), at(22), "MAYBE"),)
    try:
        _effective_availability(bad)
    except ValueError as error:
        assert str(error) == "unknown availability type: MAYBE"
    else:
        raise AssertionError("unknown availability type should fail")


def test_duplicate_identifiers_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate actor id"):
        _require_unique_ids("actor", [1, 1])
