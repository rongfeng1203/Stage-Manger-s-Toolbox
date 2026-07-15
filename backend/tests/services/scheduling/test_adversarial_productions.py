import pytest

from backend.app.services.scheduling import SchedulingProblem, generate_schedule
from backend.tests.fixtures.adversarial_productions import (
    conflict_heavy_production,
    doubling_heavy_production,
    impossible_production,
    medium_production,
    small_production,
)


@pytest.mark.parametrize(
    ("factory", "actors", "scenes"),
    [
        (small_production, 5, 5),
        (medium_production, 20, 40),
        (conflict_heavy_production, 10, 30),
        (doubling_heavy_production, 5, 15),
        (impossible_production, 5, 5),
    ],
)
def test_named_adversarial_fixture_shape(factory: object, actors: int, scenes: int) -> None:
    assert callable(factory)
    problem = factory()
    assert isinstance(problem, SchedulingProblem)
    assert len(problem.actors) == actors
    assert len(problem.scenes) == scenes


@pytest.mark.parametrize(
    "factory",
    [small_production, conflict_heavy_production, doubling_heavy_production],
)
def test_adversarial_production_solves_deterministically(factory: object) -> None:
    assert callable(factory)
    problem = factory()
    first = generate_schedule(problem)
    second = generate_schedule(problem)
    assert first == second
    assert first.metrics["total_rehearsal_minutes"] > 0


def test_medium_production_completes_as_performance_smoke_test() -> None:
    result = generate_schedule(medium_production())
    assert result.metrics["total_rehearsal_minutes"] > 0


def test_impossible_production_reports_all_debt_without_crashing() -> None:
    problem = impossible_production()
    result = generate_schedule(problem)
    assert result.sessions == ()
    assert result.metrics["remaining_rehearsal_debt"] == 300
