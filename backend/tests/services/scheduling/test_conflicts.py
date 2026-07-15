from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.availability.time_windows import TimeWindow
from backend.app.services.scheduling.conflicts import (
    ActorBusyConflict,
    ActorOverlapConflict,
    ConflictContext,
    ConflictEngineError,
    ExistingSession,
    SceneInput,
    ScheduleCheck,
    SessionLengthConflict,
    SlotAlignmentConflict,
    _is_aligned_to_any_availability_origin,
    _require_positive,
    _validate_conflict_base,
    _window_is_contained,
    _windows_overlap,
    can_schedule_scene,
    detect_actor_overlap,
    find_valid_session_starts,
    get_scene_common_availability,
)

TORONTO = ZoneInfo("America/Toronto")


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=TORONTO)


def scene(scene_id: int = 10, actor_ids: frozenset[int] = frozenset({1})) -> SceneInput:
    return SceneInput(id=scene_id, scene_code="A1S1", required_actor_ids=actor_ids)


def context(
    availability_by_actor: dict[int, list[TimeWindow]],
    *,
    existing_sessions: list[ExistingSession] | None = None,
    slot_duration_minutes: int = 30,
    minimum_session_minutes: int = 60,
) -> ConflictContext:
    return ConflictContext(
        availability_by_actor=availability_by_actor,
        existing_sessions=existing_sessions or [],
        slot_duration_minutes=slot_duration_minutes,
        minimum_session_minutes=minimum_session_minutes,
    )


def test_get_scene_common_availability_returns_intersection_for_required_actors() -> None:
    result = get_scene_common_availability(
        scene(10, frozenset({1, 2})),
        context(
            {
                1: [TimeWindow(dt(14, 18), dt(14, 22))],
                2: [TimeWindow(dt(14, 20), dt(14, 21))],
            }
        ),
    )

    assert result == [TimeWindow(dt(14, 20), dt(14, 21))]


def test_get_scene_common_availability_returns_empty_when_actor_has_no_window() -> None:
    result = get_scene_common_availability(
        scene(10, frozenset({1, 2})),
        context({1: [TimeWindow(dt(14, 18), dt(14, 22))]}),
    )

    assert result == []


def test_get_scene_common_availability_returns_empty_for_scene_without_required_actors() -> None:
    assert get_scene_common_availability(scene(10, frozenset()), context({})) == []


def test_can_schedule_scene_accepts_available_session() -> None:
    check = can_schedule_scene(
        scene=scene(),
        start=dt(14, 18),
        duration_minutes=60,
        context=context({1: [TimeWindow(dt(14, 18), dt(14, 22))]}),
    )

    assert check.valid is True
    assert check.conflicts == ()
    assert check.session_window == TimeWindow(dt(14, 18), dt(14, 19))


def test_can_schedule_scene_reports_actor_busy_conflict() -> None:
    check = can_schedule_scene(
        scene=scene(),
        start=dt(14, 17),
        duration_minutes=60,
        context=context({1: [TimeWindow(dt(14, 18), dt(14, 22))]}),
    )

    assert check.valid is False
    assert check.conflicts == (
        ActorBusyConflict(
            scene_id=10,
            actor_id=1,
            requested_window=TimeWindow(dt(14, 17), dt(14, 18)),
            available_windows=(TimeWindow(dt(14, 18), dt(14, 22)),),
            message="actor 1 is not available for the complete requested session",
        ),
    )


def test_can_schedule_scene_reports_minimum_session_length_conflict() -> None:
    check = can_schedule_scene(
        scene=scene(),
        start=dt(14, 18),
        duration_minutes=30,
        context=context({1: [TimeWindow(dt(14, 18), dt(14, 22))]}),
    )

    assert check.valid is False
    assert check.conflicts == (
        SessionLengthConflict(
            scene_id=10,
            requested_minutes=30,
            minimum_minutes=60,
            message="requested session is shorter than the minimum session length",
        ),
    )


def test_can_schedule_scene_reports_actor_overlap_conflict() -> None:
    existing = ExistingSession(
        id=99,
        scene_id=20,
        actor_ids=frozenset({1}),
        window=TimeWindow(dt(14, 18, 30), dt(14, 19, 30)),
    )

    check = can_schedule_scene(
        scene=scene(),
        start=dt(14, 18),
        duration_minutes=60,
        context=context(
            {1: [TimeWindow(dt(14, 18), dt(14, 22))]},
            existing_sessions=[existing],
        ),
    )

    assert check.valid is False
    assert check.conflicts == (
        ActorOverlapConflict(
            scene_id=10,
            actor_id=1,
            requested_window=TimeWindow(dt(14, 18), dt(14, 19)),
            existing_session_id=99,
            existing_scene_id=20,
            existing_window=TimeWindow(dt(14, 18, 30), dt(14, 19, 30)),
            message="actor 1 is already scheduled for overlapping session 99",
        ),
    )


def test_detect_actor_overlap_allows_different_cast_overlap() -> None:
    conflicts = detect_actor_overlap(
        scene=scene(10, frozenset({1})),
        requested_window=TimeWindow(dt(14, 18), dt(14, 19)),
        existing_sessions=[
            ExistingSession(
                id=99,
                scene_id=20,
                actor_ids=frozenset({2}),
                window=TimeWindow(dt(14, 18), dt(14, 19)),
            )
        ],
    )

    assert conflicts == ()


def test_detect_actor_overlap_treats_touching_sessions_as_non_overlapping() -> None:
    conflicts = detect_actor_overlap(
        scene=scene(10, frozenset({1})),
        requested_window=TimeWindow(dt(14, 18), dt(14, 19)),
        existing_sessions=[
            ExistingSession(
                id=99,
                scene_id=20,
                actor_ids=frozenset({1}),
                window=TimeWindow(dt(14, 19), dt(14, 20)),
            )
        ],
    )

    assert conflicts == ()


def test_find_valid_session_starts_returns_slot_aligned_valid_starts() -> None:
    starts = find_valid_session_starts(
        scene=scene(10, frozenset({1, 2})),
        duration_minutes=60,
        context=context(
            {
                1: [TimeWindow(dt(14, 18), dt(14, 22))],
                2: [TimeWindow(dt(14, 20), dt(14, 21, 30))],
            }
        ),
    )

    assert starts == [dt(14, 20), dt(14, 20, 30)]


def test_find_valid_session_starts_excludes_overlapping_existing_sessions() -> None:
    starts = find_valid_session_starts(
        scene=scene(),
        duration_minutes=60,
        context=context(
            {1: [TimeWindow(dt(14, 18), dt(14, 21))]},
            existing_sessions=[
                ExistingSession(
                    id=99,
                    scene_id=20,
                    actor_ids=frozenset({1}),
                    window=TimeWindow(dt(14, 18, 30), dt(14, 19, 30)),
                )
            ],
        ),
    )

    assert starts == [dt(14, 19, 30), dt(14, 20)]


def test_can_schedule_scene_rejects_non_slot_aligned_start() -> None:
    check = can_schedule_scene(
        scene=scene(),
        start=dt(14, 18, 15),
        duration_minutes=60,
        context=context({1: [TimeWindow(dt(14, 18), dt(14, 22))]}),
    )

    assert check.valid is False
    assert check.conflicts[0].message == "requested session start is not slot aligned"


def test_conflict_inputs_reject_invalid_identifiers() -> None:
    with pytest.raises(ConflictEngineError, match="scene_id"):
        SceneInput(id=0, scene_code="A1S1", required_actor_ids=frozenset({1}))


def test_conflict_inputs_reject_invalid_slot_duration() -> None:
    with pytest.raises(ConflictEngineError, match="slot"):
        context({}, slot_duration_minutes=0)


def test_conflict_inputs_reject_invalid_minimum_session_length() -> None:
    with pytest.raises(ConflictEngineError, match="minimum"):
        context({}, minimum_session_minutes=0)


def test_can_schedule_scene_rejects_non_positive_duration() -> None:
    with pytest.raises(ConflictEngineError, match="duration"):
        can_schedule_scene(
            scene=scene(),
            start=dt(14, 18),
            duration_minutes=0,
            context=context({1: [TimeWindow(dt(14, 18), dt(14, 22))]}),
        )


def test_valid_session_start_generation_skips_dst_gap() -> None:
    spring_forward = ZoneInfo("America/Toronto")
    start = datetime(2026, 3, 8, 1, 0, tzinfo=spring_forward)
    end = datetime(2026, 3, 8, 4, 0, tzinfo=spring_forward)

    starts = find_valid_session_starts(
        scene=scene(),
        duration_minutes=30,
        context=context(
            {1: [TimeWindow(start, end)]},
            minimum_session_minutes=30,
        ),
    )

    assert starts == [
        datetime(2026, 3, 8, 1, 0, tzinfo=spring_forward),
        datetime(2026, 3, 8, 1, 30, tzinfo=spring_forward),
        datetime(2026, 3, 8, 3, 0, tzinfo=spring_forward),
        datetime(2026, 3, 8, 3, 30, tzinfo=spring_forward),
    ]


def test_requested_window_uses_elapsed_time_across_dst_gap() -> None:
    spring_forward = ZoneInfo("America/Toronto")
    start = datetime(2026, 3, 8, 1, 30, tzinfo=spring_forward)

    check = can_schedule_scene(
        scene=scene(),
        start=start,
        duration_minutes=30,
        context=context(
            {
                1: [
                    TimeWindow(
                        datetime(2026, 3, 8, 1, 0, tzinfo=spring_forward),
                        datetime(2026, 3, 8, 4, 0, tzinfo=spring_forward),
                    )
                ]
            },
            minimum_session_minutes=30,
        ),
    )

    assert check.valid is True
    assert check.session_window == TimeWindow(
        start,
        datetime(2026, 3, 8, 3, 0, tzinfo=spring_forward),
    )


def test_window_is_contained_accepts_fully_contained_window() -> None:
    assert _window_is_contained(
        TimeWindow(dt(14, 19), dt(14, 20)),
        [TimeWindow(dt(14, 18), dt(14, 22))],
    )


def test_window_is_contained_rejects_partial_overlap() -> None:
    assert not _window_is_contained(
        TimeWindow(dt(14, 17), dt(14, 19)),
        [TimeWindow(dt(14, 18), dt(14, 22))],
    )


def test_windows_overlap_detects_overlap() -> None:
    assert _windows_overlap(
        TimeWindow(dt(14, 18), dt(14, 19)),
        TimeWindow(dt(14, 18, 30), dt(14, 19, 30)),
    )


def test_windows_overlap_rejects_touching_windows() -> None:
    assert not _windows_overlap(
        TimeWindow(dt(14, 18), dt(14, 19)),
        TimeWindow(dt(14, 19), dt(14, 20)),
    )


def test_is_aligned_to_any_availability_origin_accepts_matching_grid() -> None:
    assert _is_aligned_to_any_availability_origin(
        scene(),
        dt(14, 19, 30),
        context({1: [TimeWindow(dt(14, 18), dt(14, 22))]}),
    )


def test_is_aligned_to_any_availability_origin_rejects_missing_actor_origin() -> None:
    assert not _is_aligned_to_any_availability_origin(
        scene(),
        dt(14, 19, 30),
        context({}),
    )


def test_validate_conflict_base_accepts_valid_base_fields() -> None:
    assert _validate_conflict_base(10, "message") is None


def test_validate_conflict_base_rejects_empty_message() -> None:
    with pytest.raises(ConflictEngineError, match="message"):
        _validate_conflict_base(10, "")


def test_require_positive_accepts_positive_value() -> None:
    assert _require_positive("actor_id", 1) is None


def test_require_positive_rejects_zero_value() -> None:
    with pytest.raises(ConflictEngineError, match="actor_id"):
        _require_positive("actor_id", 0)


def test_schedule_check_rejects_valid_result_with_conflicts() -> None:
    conflict = SlotAlignmentConflict(
        scene_id=10,
        requested_start=dt(14, 18, 15),
        slot_duration_minutes=30,
        message="requested session start is not slot aligned",
    )

    with pytest.raises(ConflictEngineError, match="valid"):
        ScheduleCheck(
            valid=True,
            scene_id=10,
            session_window=TimeWindow(dt(14, 18), dt(14, 19)),
            conflicts=(conflict,),
        )
