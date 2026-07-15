from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from backend.app.services.availability import TimeWindow
from backend.app.services.scheduling import (
    ActorProblem,
    AvailabilityProblem,
    CastAssignmentProblem,
    CharacterProblem,
    ProductionProblem,
    SceneCharacterProblem,
    SceneProblem,
    SchedulingProblem,
)

TORONTO = ZoneInfo("America/Toronto")


def small_production() -> SchedulingProblem:
    return _cyclic_problem(actor_count=5, scene_count=5, day_count=2)


def medium_production() -> SchedulingProblem:
    return _cyclic_problem(actor_count=20, scene_count=40, day_count=7)


def conflict_heavy_production() -> SchedulingProblem:
    return _cyclic_problem(actor_count=10, scene_count=30, day_count=1, window_hours=2)


def doubling_heavy_production() -> SchedulingProblem:
    problem = _cyclic_problem(actor_count=5, scene_count=15, day_count=4)
    characters = [
        CharacterProblem(id=index, production_id=1, name=f"Character {index}")
        for index in range(1, 16)
    ]
    assignments = [
        CastAssignmentProblem(character_id=index, actor_id=((index - 1) % 5) + 1)
        for index in range(1, 16)
    ]
    return SchedulingProblem(
        production=problem.production,
        scenes=problem.scenes,
        actors=problem.actors,
        characters=characters,
        cast_assignments=assignments,
        scene_characters=problem.scene_characters,
        availability=problem.availability,
        max_solver_seconds=2.0,
    )


def impossible_production() -> SchedulingProblem:
    problem = _cyclic_problem(actor_count=5, scene_count=5, day_count=1)
    return SchedulingProblem(
        production=problem.production,
        scenes=problem.scenes,
        actors=problem.actors,
        characters=problem.characters,
        cast_assignments=problem.cast_assignments,
        scene_characters=problem.scene_characters,
        availability=[],
        max_solver_seconds=2.0,
    )


def _cyclic_problem(
    *, actor_count: int, scene_count: int, day_count: int, window_hours: int = 4
) -> SchedulingProblem:
    production = ProductionProblem(
        id=1,
        name="Adversarial Production",
        rehearsal_start_date=date(2026, 7, 14),
        rehearsal_end_date=date(2026, 7, 13 + day_count),
        daily_start_time=time(18),
        daily_end_time=time(22),
    )
    actors = [ActorProblem(index, f"Actor {index}") for index in range(1, actor_count + 1)]
    characters = [
        CharacterProblem(index, 1, f"Character {index}") for index in range(1, scene_count + 1)
    ]
    scenes = [
        SceneProblem(index, 1, f"S{index}", 2 + (index % 3), 60, 0)
        for index in range(1, scene_count + 1)
    ]
    assignments = [
        CastAssignmentProblem(index, ((index - 1) % actor_count) + 1)
        for index in range(1, scene_count + 1)
    ]
    scene_characters = [
        SceneCharacterProblem(index, index, True) for index in range(1, scene_count + 1)
    ]
    availability = [
        AvailabilityProblem(
            actor.id,
            TimeWindow(
                datetime(2026, 7, day, 18, tzinfo=TORONTO),
                datetime(2026, 7, day, 18 + window_hours, tzinfo=TORONTO),
            ),
        )
        for actor in actors
        for day in range(14, 14 + day_count)
    ]
    return SchedulingProblem(
        production=production,
        scenes=scenes,
        actors=actors,
        characters=characters,
        cast_assignments=assignments,
        scene_characters=scene_characters,
        availability=availability,
        max_solver_seconds=2.0,
    )
