from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.availability.time_windows import TimeWindow
from backend.app.services.scheduling.solver import (
    ActorProblem,
    AvailabilityProblem,
    CastAssignmentProblem,
    CharacterProblem,
    ProductionProblem,
    SceneCharacterProblem,
    SceneProblem,
    SchedulingProblem,
    SchedulingStatus,
    SolverError,
    generate_schedule,
    rehearsal_debt_minutes,
)

TORONTO = ZoneInfo("America/Toronto")


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=TORONTO)


def base_production() -> ProductionProblem:
    return ProductionProblem(
        id=1,
        name="Hamlet",
        rehearsal_start_date=date(2026, 7, 14),
        rehearsal_end_date=date(2026, 7, 14),
        daily_start_time=time(18, 0),
        daily_end_time=time(22, 0),
        slot_duration_minutes=30,
    )


def scene(
    scene_id: int,
    code: str,
    *,
    target_minutes: int = 60,
    completed_minutes: int = 0,
    priority: int = 2,
) -> SceneProblem:
    return SceneProblem(
        id=scene_id,
        production_id=1,
        scene_code=code,
        priority=priority,
        target_rehearsal_minutes=target_minutes,
        completed_rehearsal_minutes=completed_minutes,
    )


def actor(actor_id: int, name: str) -> ActorProblem:
    return ActorProblem(id=actor_id, name=name)


def character(character_id: int, name: str) -> CharacterProblem:
    return CharacterProblem(id=character_id, production_id=1, name=name)


def cast(character_id: int, actor_id: int) -> CastAssignmentProblem:
    return CastAssignmentProblem(character_id=character_id, actor_id=actor_id)


def scene_character(scene_id: int, character_id: int) -> SceneCharacterProblem:
    return SceneCharacterProblem(scene_id=scene_id, character_id=character_id, required=True)


def availability(actor_id: int, start: datetime, end: datetime) -> AvailabilityProblem:
    return AvailabilityProblem(actor_id=actor_id, window=TimeWindow(start, end))


def problem(
    *,
    scenes: list[SceneProblem],
    actors: list[ActorProblem],
    characters: list[CharacterProblem],
    cast_assignments: list[CastAssignmentProblem],
    scene_characters: list[SceneCharacterProblem],
    availability_windows: list[AvailabilityProblem],
    allow_parallel_rehearsals: bool = True,
) -> SchedulingProblem:
    return SchedulingProblem(
        production=base_production(),
        scenes=scenes,
        actors=actors,
        characters=characters,
        cast_assignments=cast_assignments,
        scene_characters=scene_characters,
        availability=availability_windows,
        minimum_session_minutes=60,
        allow_parallel_rehearsals=allow_parallel_rehearsals,
    )


def test_rehearsal_debt_minutes_subtracts_completed_time() -> None:
    assert (
        rehearsal_debt_minutes(scene(1, "A1S1", target_minutes=300, completed_minutes=120)) == 180
    )


def test_one_scene_one_available_actor_is_scheduled() -> None:
    result = generate_schedule(
        problem(
            scenes=[scene(1, "A1S1")],
            actors=[actor(1, "Rina")],
            characters=[character(1, "Hamlet")],
            cast_assignments=[cast(1, 1)],
            scene_characters=[scene_character(1, 1)],
            availability_windows=[availability(1, dt(14, 18), dt(14, 22))],
        )
    )

    assert result.status == SchedulingStatus.OPTIMAL
    assert len(result.sessions) == 1
    assert result.sessions[0].scene_id == 1
    assert result.sessions[0].start == dt(14, 18)
    assert result.sessions[0].end == dt(14, 19)
    assert result.metrics["total_rehearsal_minutes"] == 60


def test_busy_actor_for_complete_window_returns_feasible_partial_with_remaining_debt() -> None:
    result = generate_schedule(
        problem(
            scenes=[scene(1, "A1S1")],
            actors=[actor(1, "Rina")],
            characters=[character(1, "Hamlet")],
            cast_assignments=[cast(1, 1)],
            scene_characters=[scene_character(1, 1)],
            availability_windows=[],
        )
    )

    assert result.status == SchedulingStatus.FEASIBLE
    assert result.sessions == ()
    assert result.metrics["remaining_rehearsal_debt"] == 60


def test_two_actor_intersection_is_the_only_valid_window() -> None:
    result = generate_schedule(
        problem(
            scenes=[scene(1, "A1S1")],
            actors=[actor(1, "Rina"), actor(2, "John")],
            characters=[character(1, "Hamlet"), character(2, "Horatio")],
            cast_assignments=[cast(1, 1), cast(2, 2)],
            scene_characters=[scene_character(1, 1), scene_character(1, 2)],
            availability_windows=[
                availability(1, dt(14, 18), dt(14, 22)),
                availability(2, dt(14, 20), dt(14, 21)),
            ],
        )
    )

    assert result.sessions[0].start == dt(14, 20)
    assert result.sessions[0].end == dt(14, 21)


def test_same_actor_scenes_never_overlap() -> None:
    result = generate_schedule(
        problem(
            scenes=[scene(1, "A1S1"), scene(2, "A1S2")],
            actors=[actor(1, "Rina")],
            characters=[character(1, "Hamlet")],
            cast_assignments=[cast(1, 1)],
            scene_characters=[scene_character(1, 1), scene_character(2, 1)],
            availability_windows=[availability(1, dt(14, 18), dt(14, 22))],
        )
    )

    first, second = sorted(result.sessions, key=lambda session: session.start)
    assert first.end <= second.start


def test_different_cast_overlap_is_allowed_when_parallel_enabled() -> None:
    result = generate_schedule(
        problem(
            scenes=[scene(1, "A1S1"), scene(2, "A1S2")],
            actors=[actor(1, "Rina"), actor(2, "Maya")],
            characters=[character(1, "Hamlet"), character(2, "Ophelia")],
            cast_assignments=[cast(1, 1), cast(2, 2)],
            scene_characters=[scene_character(1, 1), scene_character(2, 2)],
            availability_windows=[
                availability(1, dt(14, 18), dt(14, 22)),
                availability(2, dt(14, 18), dt(14, 22)),
            ],
        )
    )

    starts = {session.scene_id: session.start for session in result.sessions}
    assert starts == {1: dt(14, 18), 2: dt(14, 18)}


def test_parallel_rehearsals_can_be_disabled_at_production_level() -> None:
    result = generate_schedule(
        problem(
            scenes=[scene(1, "A1S1"), scene(2, "A1S2")],
            actors=[actor(1, "Rina"), actor(2, "Maya")],
            characters=[character(1, "Hamlet"), character(2, "Ophelia")],
            cast_assignments=[cast(1, 1), cast(2, 2)],
            scene_characters=[scene_character(1, 1), scene_character(2, 2)],
            availability_windows=[
                availability(1, dt(14, 18), dt(14, 22)),
                availability(2, dt(14, 18), dt(14, 22)),
            ],
            allow_parallel_rehearsals=False,
        )
    )

    first, second = sorted(result.sessions, key=lambda session: session.start)
    assert first.end <= second.start


def test_ninety_minute_scene_uses_three_contiguous_thirty_minute_slots() -> None:
    result = generate_schedule(
        problem(
            scenes=[scene(1, "A1S1", target_minutes=90)],
            actors=[actor(1, "Rina")],
            characters=[character(1, "Hamlet")],
            cast_assignments=[cast(1, 1)],
            scene_characters=[scene_character(1, 1)],
            availability_windows=[availability(1, dt(14, 18), dt(14, 22))],
        )
    )

    assert result.sessions[0].start == dt(14, 18)
    assert result.sessions[0].end == dt(14, 19, 30)
    assert result.sessions[0].duration_minutes == 90


def test_impossible_target_allows_partial_coverage_and_reports_remaining_debt() -> None:
    result = generate_schedule(
        problem(
            scenes=[scene(1, "A1S1", target_minutes=300)],
            actors=[actor(1, "Rina")],
            characters=[character(1, "Hamlet")],
            cast_assignments=[cast(1, 1)],
            scene_characters=[scene_character(1, 1)],
            availability_windows=[availability(1, dt(14, 18), dt(14, 20))],
        )
    )

    assert result.status == SchedulingStatus.FEASIBLE
    assert result.metrics["total_rehearsal_minutes"] == 120
    assert result.metrics["remaining_rehearsal_debt"] == 180


def test_solver_output_is_deterministic() -> None:
    scheduling_problem = problem(
        scenes=[scene(1, "A1S1"), scene(2, "A1S2")],
        actors=[actor(1, "Rina")],
        characters=[character(1, "Hamlet")],
        cast_assignments=[cast(1, 1)],
        scene_characters=[scene_character(1, 1), scene_character(2, 1)],
        availability_windows=[availability(1, dt(14, 18), dt(14, 22))],
    )

    results = [generate_schedule(scheduling_problem) for _ in range(10)]

    assert all(result == results[0] for result in results)


def test_invalid_scene_target_raises_validation_error() -> None:
    with pytest.raises(SolverError, match="completed"):
        scene(1, "A1S1", target_minutes=60, completed_minutes=90)
