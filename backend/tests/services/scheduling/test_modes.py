from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.availability.time_windows import TimeWindow
from backend.app.services.scheduling.solver import (
    EFFICIENT_WEIGHTS,
    SCENE_PRIORITY_WEIGHTS,
    ActorProblem,
    AvailabilityProblem,
    CastAssignmentProblem,
    CharacterProblem,
    ProductionProblem,
    SceneCharacterProblem,
    SceneProblem,
    SchedulingProblem,
    SolverWeights,
    generate_schedule,
    generate_schedule_options,
)

TORONTO = ZoneInfo("America/Toronto")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 14, hour, minute, tzinfo=TORONTO)


def production() -> ProductionProblem:
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
    priority: int = 2,
    target_minutes: int = 60,
) -> SceneProblem:
    return SceneProblem(
        id=scene_id,
        production_id=1,
        scene_code=code,
        priority=priority,
        target_rehearsal_minutes=target_minutes,
        completed_rehearsal_minutes=0,
    )


def availability(actor_id: int, start: datetime, end: datetime) -> AvailabilityProblem:
    return AvailabilityProblem(actor_id=actor_id, window=TimeWindow(start, end))


def base_problem(
    *,
    scenes: list[SceneProblem],
    scene_characters: list[SceneCharacterProblem],
    availability_windows: list[AvailabilityProblem],
    allow_parallel_rehearsals: bool = True,
) -> SchedulingProblem:
    return SchedulingProblem(
        production=production(),
        scenes=scenes,
        actors=[ActorProblem(1, "Rina"), ActorProblem(2, "Maya")],
        characters=[
            CharacterProblem(1, 1, "Hamlet"),
            CharacterProblem(2, 1, "Ophelia"),
        ],
        cast_assignments=[
            CastAssignmentProblem(1, 1),
            CastAssignmentProblem(2, 2),
        ],
        scene_characters=scene_characters,
        availability=availability_windows,
        minimum_session_minutes=60,
        allow_parallel_rehearsals=allow_parallel_rehearsals,
    )


def test_generate_schedule_options_returns_three_named_modes() -> None:
    problem = base_problem(
        scenes=[scene(1, "A1S1")],
        scene_characters=[SceneCharacterProblem(1, 1, True)],
        availability_windows=[availability(1, dt(18), dt(22))],
    )

    options = generate_schedule_options(problem)

    assert set(options) == {"efficient", "balanced", "scene_priority"}


def test_all_modes_use_same_hard_constraints_for_shared_actor_overlap() -> None:
    problem = base_problem(
        scenes=[scene(1, "A1S1"), scene(2, "A1S2")],
        scene_characters=[
            SceneCharacterProblem(1, 1, True),
            SceneCharacterProblem(2, 1, True),
        ],
        availability_windows=[availability(1, dt(18), dt(20))],
    )

    for result in generate_schedule_options(problem).values():
        first, second = sorted(result.sessions, key=lambda session: session.start)
        assert first.end <= second.start


def test_scene_priority_weights_favor_critical_scene_when_only_one_can_fit() -> None:
    problem = base_problem(
        scenes=[
            scene(1, "NORMAL", priority=2),
            scene(2, "CRITICAL", priority=4),
        ],
        scene_characters=[
            SceneCharacterProblem(1, 1, True),
            SceneCharacterProblem(2, 1, True),
        ],
        availability_windows=[availability(1, dt(18), dt(19))],
    )

    result = generate_schedule(problem, weights=SCENE_PRIORITY_WEIGHTS)

    assert [session.scene_code for session in result.sessions] == ["CRITICAL"]


def test_efficient_weights_prefer_adjacent_sessions_for_same_actor() -> None:
    problem = base_problem(
        scenes=[scene(1, "A1S1"), scene(2, "A1S2")],
        scene_characters=[
            SceneCharacterProblem(1, 1, True),
            SceneCharacterProblem(2, 1, True),
        ],
        availability_windows=[availability(1, dt(18), dt(22))],
    )

    result = generate_schedule(problem, weights=EFFICIENT_WEIGHTS)
    first, second = sorted(result.sessions, key=lambda session: session.start)

    assert first.end == second.start


def test_custom_weights_can_favor_later_candidate_when_candidate_bias_is_reversed() -> None:
    problem = base_problem(
        scenes=[scene(1, "A1S1")],
        scene_characters=[SceneCharacterProblem(1, 1, True)],
        availability_windows=[availability(1, dt(18), dt(20))],
    )
    weights = SolverWeights(
        rehearsal_minute_reward=100,
        priority_reward=0,
        earlier_start_reward=-10,
        idle_penalty=0,
        cast_grouping_reward=0,
    )

    result = generate_schedule(problem, weights=weights)

    assert result.sessions[0].start == dt(19)


def test_solver_weights_reject_negative_required_weights() -> None:
    with pytest.raises(ValueError, match="rehearsal_minute_reward"):
        SolverWeights(rehearsal_minute_reward=-1)


def test_generate_schedule_options_is_deterministic() -> None:
    problem = base_problem(
        scenes=[scene(1, "A1S1"), scene(2, "A1S2")],
        scene_characters=[
            SceneCharacterProblem(1, 1, True),
            SceneCharacterProblem(2, 1, True),
        ],
        availability_windows=[availability(1, dt(18), dt(22))],
    )

    first = generate_schedule_options(problem)
    second = generate_schedule_options(problem)

    assert first == second
