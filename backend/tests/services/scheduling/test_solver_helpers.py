from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.availability.time_windows import TimeWindow
from backend.app.services.scheduling.solver import (
    AvailabilityProblem,
    ProductionProblem,
    SchedulingProblem,
    SchedulingStatus,
    SolverError,
    _candidate_duration_options,
    _candidate_objective,
    _empty_result,
    _metrics,
    _problem_timezone,
    _production_windows,
    _require_positive,
    _result_from_candidates,
    _windows_inside_production,
)
from backend.app.services.scheduling.solver import _SessionCandidate as SessionCandidate

TORONTO = ZoneInfo("America/Toronto")


def production() -> ProductionProblem:
    return ProductionProblem(
        id=1,
        name="Hamlet",
        rehearsal_start_date=date(2026, 7, 14),
        rehearsal_end_date=date(2026, 7, 15),
        daily_start_time=time(18, 0),
        daily_end_time=time(22, 0),
        slot_duration_minutes=30,
    )


def empty_problem(*, availability: list[AvailabilityProblem] | None = None) -> SchedulingProblem:
    return SchedulingProblem(
        production=production(),
        scenes=[],
        actors=[],
        characters=[],
        cast_assignments=[],
        scene_characters=[],
        availability=availability or [],
    )


def test_candidate_duration_options_returns_slot_aligned_descending_options() -> None:
    assert _candidate_duration_options(150, 30, 60) == [150, 120, 90, 60]


def test_candidate_duration_options_allows_short_debt_under_minimum() -> None:
    assert _candidate_duration_options(30, 30, 60) == [30]


def test_candidate_duration_options_returns_empty_for_zero_debt() -> None:
    assert _candidate_duration_options(0, 30, 60) == []


def test_problem_timezone_uses_availability_timezone_when_production_time_is_naive() -> None:
    problem = empty_problem(
        availability=[
            AvailabilityProblem(
                actor_id=1,
                window=TimeWindow(
                    datetime(2026, 7, 14, 18, tzinfo=TORONTO),
                    datetime(2026, 7, 14, 22, tzinfo=TORONTO),
                ),
            )
        ]
    )

    assert _problem_timezone(problem) == TORONTO


def test_problem_timezone_falls_back_to_utc_without_availability() -> None:
    assert _problem_timezone(empty_problem()) == UTC


def test_production_windows_builds_one_window_per_rehearsal_date() -> None:
    assert _production_windows(production(), TORONTO) == [
        TimeWindow(
            datetime(2026, 7, 14, 18, tzinfo=TORONTO),
            datetime(2026, 7, 14, 22, tzinfo=TORONTO),
        ),
        TimeWindow(
            datetime(2026, 7, 15, 18, tzinfo=TORONTO),
            datetime(2026, 7, 15, 22, tzinfo=TORONTO),
        ),
    ]


def test_windows_inside_production_clips_actor_availability() -> None:
    assert _windows_inside_production(
        [
            TimeWindow(
                datetime(2026, 7, 14, 17, tzinfo=TORONTO),
                datetime(2026, 7, 14, 23, tzinfo=TORONTO),
            )
        ],
        [
            TimeWindow(
                datetime(2026, 7, 14, 18, tzinfo=TORONTO),
                datetime(2026, 7, 14, 22, tzinfo=TORONTO),
            )
        ],
    ) == [
        TimeWindow(
            datetime(2026, 7, 14, 18, tzinfo=TORONTO),
            datetime(2026, 7, 14, 22, tzinfo=TORONTO),
        )
    ]


def test_candidate_objective_prefers_earlier_candidate_when_duration_ties() -> None:
    candidate = SessionCandidate(
        scene_id=1,
        scene_code="A1S1",
        actor_ids=frozenset({1}),
        priority=2,
        start=datetime(2026, 7, 14, 18, tzinfo=TORONTO),
        end=datetime(2026, 7, 14, 19, tzinfo=TORONTO),
        duration_minutes=60,
        score=60,
    )

    assert _candidate_objective(candidate, 0) > _candidate_objective(candidate, 1)


def test_empty_result_uses_given_status_and_zero_metrics() -> None:
    result = _empty_result(SchedulingStatus.OPTIMAL)

    assert result.status == SchedulingStatus.OPTIMAL
    assert result.sessions == ()
    assert result.metrics["total_rehearsal_minutes"] == 0


def test_metrics_counts_scheduled_minutes_and_days() -> None:
    candidate = SessionCandidate(
        scene_id=1,
        scene_code="A1S1",
        actor_ids=frozenset({1}),
        priority=2,
        start=datetime(2026, 7, 14, 18, tzinfo=TORONTO),
        end=datetime(2026, 7, 14, 19, tzinfo=TORONTO),
        duration_minutes=60,
        score=60,
    )
    result = _result_from_candidates(empty_problem(), (candidate,))

    assert _metrics(empty_problem(), result.sessions)["total_rehearsal_minutes"] == 60
    assert _metrics(empty_problem(), result.sessions)["number_of_rehearsal_days"] == 1


def test_require_positive_accepts_positive_value() -> None:
    assert _require_positive("scene_id", 1) is None


def test_require_positive_rejects_zero_value() -> None:
    with pytest.raises(SolverError, match="scene_id"):
        _require_positive("scene_id", 0)
