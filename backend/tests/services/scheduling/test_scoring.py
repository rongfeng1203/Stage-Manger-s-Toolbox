from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.scheduling.scoring import (
    DEFAULT_SHORT_CALL_PENALTY,
    ScheduleMetrics,
    ScoringError,
    _actor_minutes_by_day,
    _duration_minutes,
    _require_non_negative,
    _session_actor_minutes,
    calculate_actor_workload,
    calculate_cast_similarity,
    calculate_idle_minutes,
    calculate_scene_debt_coverage,
    calculate_schedule_metrics,
    calculate_short_call_penalty,
)
from backend.app.services.scheduling.solver import SceneProblem, ScheduledSession

TORONTO = ZoneInfo("America/Toronto")


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=TORONTO)


def session(
    scene_id: int,
    start: datetime,
    end: datetime,
    actor_ids: frozenset[int],
    *,
    scene_code: str | None = None,
) -> ScheduledSession:
    duration = int((end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() // 60)
    return ScheduledSession(
        scene_id=scene_id,
        scene_code=scene_code or f"A1S{scene_id}",
        actor_ids=actor_ids,
        start=start,
        end=end,
        duration_minutes=duration,
        solver_score=duration,
    )


def scene(
    scene_id: int,
    *,
    priority: int = 2,
    target: int = 120,
    completed: int = 0,
) -> SceneProblem:
    return SceneProblem(
        id=scene_id,
        production_id=1,
        scene_code=f"A1S{scene_id}",
        priority=priority,
        target_rehearsal_minutes=target,
        completed_rehearsal_minutes=completed,
    )


def test_calculate_idle_minutes_penalizes_gaps_between_actor_sessions() -> None:
    sessions = [
        session(1, dt(14, 18), dt(14, 19), frozenset({1})),
        session(2, dt(14, 20), dt(14, 21), frozenset({1})),
        session(3, dt(14, 21), dt(14, 22), frozenset({2})),
    ]

    assert calculate_idle_minutes(sessions) == 60


def test_calculate_idle_minutes_does_not_count_gaps_across_days() -> None:
    sessions = [
        session(1, dt(14, 18), dt(14, 19), frozenset({1})),
        session(2, dt(15, 20), dt(15, 21), frozenset({1})),
    ]

    assert calculate_idle_minutes(sessions) == 0


def test_calculate_actor_workload_returns_minutes_per_actor_per_day() -> None:
    sessions = [
        session(1, dt(14, 18), dt(14, 19), frozenset({1, 2})),
        session(2, dt(14, 19), dt(14, 20, 30), frozenset({1})),
        session(3, dt(15, 18), dt(15, 19), frozenset({1})),
    ]

    assert calculate_actor_workload(sessions) == {
        (1, dt(14, 18).date()): 150,
        (1, dt(15, 18).date()): 60,
        (2, dt(14, 18).date()): 60,
    }


def test_calculate_scene_debt_coverage_caps_at_remaining_debt() -> None:
    scenes = [scene(1, target=300, completed=120)]
    sessions = [session(1, dt(14, 18), dt(14, 22), frozenset({1}))]

    assert calculate_scene_debt_coverage(scenes, sessions) == {
        1: {
            "remaining_debt": 180,
            "scheduled_minutes": 180,
            "remaining_after_schedule": 0,
        }
    }


def test_calculate_scene_debt_coverage_reports_remaining_after_partial_schedule() -> None:
    scenes = [scene(1, target=300, completed=120)]
    sessions = [session(1, dt(14, 18), dt(14, 19), frozenset({1}))]

    assert calculate_scene_debt_coverage(scenes, sessions)[1]["remaining_after_schedule"] == 120


def test_calculate_cast_similarity_uses_jaccard_similarity() -> None:
    assert calculate_cast_similarity(frozenset({1, 2, 3}), frozenset({1, 2})) == pytest.approx(
        2 / 3
    )


def test_calculate_cast_similarity_returns_one_for_two_empty_casts() -> None:
    assert calculate_cast_similarity(frozenset(), frozenset()) == 1.0


def test_calculate_short_call_penalty_applies_penalty_below_threshold() -> None:
    sessions = [session(1, dt(14, 18), dt(14, 18, 30), frozenset({1}))]

    assert calculate_short_call_penalty(sessions) == DEFAULT_SHORT_CALL_PENALTY


def test_calculate_short_call_penalty_ignores_calls_at_threshold() -> None:
    sessions = [session(1, dt(14, 18), dt(14, 19), frozenset({1}))]

    assert calculate_short_call_penalty(sessions) == 0


def test_calculate_short_call_penalty_supports_custom_threshold_and_penalty() -> None:
    sessions = [session(1, dt(14, 18), dt(14, 19), frozenset({1}))]

    assert (
        calculate_short_call_penalty(
            sessions,
            short_call_minutes=90,
            penalty_per_short_call=-50,
        )
        == -50
    )


def test_calculate_schedule_metrics_returns_explainable_summary() -> None:
    scenes = [
        scene(1, target=120, completed=0),
        scene(2, priority=4, target=60, completed=0),
    ]
    sessions = [
        session(1, dt(14, 18), dt(14, 19), frozenset({1})),
        session(2, dt(14, 20), dt(14, 21), frozenset({1, 2})),
    ]

    metrics = calculate_schedule_metrics(scenes, sessions)

    assert metrics == ScheduleMetrics(
        total_rehearsal_minutes=120,
        number_of_rehearsal_days=1,
        total_actor_idle_minutes=60,
        average_actor_daily_workload=90,
        maximum_actor_daily_workload=120,
        scene_rehearsal_debt_completed=120,
        remaining_rehearsal_debt=60,
        critical_scene_coverage=100,
        short_call_penalty=0,
        objective_score=60,
    )


def test_calculate_schedule_metrics_handles_empty_schedule() -> None:
    metrics = calculate_schedule_metrics([scene(1)], [])

    assert metrics.total_rehearsal_minutes == 0
    assert metrics.number_of_rehearsal_days == 0
    assert metrics.critical_scene_coverage == 0


def test_duration_minutes_uses_elapsed_time() -> None:
    assert _duration_minutes(session(1, dt(14, 18), dt(14, 19), frozenset({1}))) == 60


def test_session_actor_minutes_returns_one_entry_per_called_actor() -> None:
    assert _session_actor_minutes(session(1, dt(14, 18), dt(14, 19), frozenset({1, 2}))) == {
        1: 60,
        2: 60,
    }


def test_actor_minutes_by_day_groups_by_actor_and_local_date() -> None:
    assert _actor_minutes_by_day([session(1, dt(14, 18), dt(14, 19), frozenset({1}))]) == {
        (1, dt(14, 18).date()): 60,
    }


def test_require_non_negative_accepts_zero() -> None:
    assert _require_non_negative("minutes", 0) is None


def test_require_non_negative_rejects_negative_value() -> None:
    with pytest.raises(ScoringError, match="minutes"):
        _require_non_negative("minutes", -1)


def test_short_call_penalty_rejects_negative_threshold() -> None:
    with pytest.raises(ScoringError, match="short_call_minutes"):
        calculate_short_call_penalty([], short_call_minutes=-1)
