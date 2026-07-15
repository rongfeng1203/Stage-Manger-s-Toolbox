from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from enum import StrEnum

from ortools.sat.python import cp_model

from backend.app.services.availability.time_windows import TimeWindow, _add_elapsed_time
from backend.app.services.cast.requirements import (
    CastAssignmentInput,
    CharacterInput,
    SceneCharacterInput,
    get_required_actors,
)
from backend.app.services.scheduling.conflicts import (
    ConflictContext,
    SceneInput,
    find_valid_session_starts,
)


class SolverError(ValueError):
    """Raised when scheduling problem inputs are structurally invalid."""


class SchedulingStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    ERROR = "ERROR"


class SchedulingMode(StrEnum):
    EFFICIENT = "efficient"
    BALANCED = "balanced"
    SCENE_PRIORITY = "scene_priority"


@dataclass(frozen=True, slots=True)
class SolverWeights:
    rehearsal_minute_reward: int = 1_000
    priority_reward: int = 8
    earlier_start_reward: int = 1
    idle_penalty: int = 4
    cast_grouping_reward: int = 3

    def __post_init__(self) -> None:
        for label in (
            "rehearsal_minute_reward",
            "priority_reward",
            "idle_penalty",
            "cast_grouping_reward",
        ):
            if getattr(self, label) < 0:
                raise SolverError(f"{label} must be non-negative")


EFFICIENT_WEIGHTS = SolverWeights(
    rehearsal_minute_reward=1_000,
    priority_reward=4,
    earlier_start_reward=1,
    idle_penalty=20,
    cast_grouping_reward=12,
)
BALANCED_WEIGHTS = SolverWeights()
SCENE_PRIORITY_WEIGHTS = SolverWeights(
    rehearsal_minute_reward=1_000,
    priority_reward=2_000,
    earlier_start_reward=1,
    idle_penalty=2,
    cast_grouping_reward=1,
)


@dataclass(frozen=True, slots=True)
class ProductionProblem:
    id: int
    name: str
    rehearsal_start_date: date
    rehearsal_end_date: date
    daily_start_time: time
    daily_end_time: time
    slot_duration_minutes: int = 30

    def __post_init__(self) -> None:
        _require_positive("production_id", self.id)
        if not self.name:
            raise SolverError("production name must not be empty")
        if self.rehearsal_start_date > self.rehearsal_end_date:
            raise SolverError("rehearsal_start_date must be on or before rehearsal_end_date")
        if self.daily_start_time >= self.daily_end_time:
            raise SolverError("daily_start_time must be before daily_end_time")
        _require_positive("slot_duration_minutes", self.slot_duration_minutes)


@dataclass(frozen=True, slots=True)
class SceneProblem:
    id: int
    production_id: int
    scene_code: str
    priority: int
    target_rehearsal_minutes: int
    completed_rehearsal_minutes: int

    def __post_init__(self) -> None:
        _require_positive("scene_id", self.id)
        _require_positive("production_id", self.production_id)
        if not self.scene_code:
            raise SolverError("scene_code must not be empty")
        if self.priority < 1 or self.priority > 4:
            raise SolverError("scene priority must be between 1 and 4")
        if self.target_rehearsal_minutes < 0:
            raise SolverError("target_rehearsal_minutes must be non-negative")
        if self.completed_rehearsal_minutes < 0:
            raise SolverError("completed_rehearsal_minutes must be non-negative")
        if self.completed_rehearsal_minutes > self.target_rehearsal_minutes:
            raise SolverError("completed rehearsal minutes cannot exceed target rehearsal minutes")


@dataclass(frozen=True, slots=True)
class ActorProblem:
    id: int
    name: str

    def __post_init__(self) -> None:
        _require_positive("actor_id", self.id)
        if not self.name:
            raise SolverError("actor name must not be empty")


@dataclass(frozen=True, slots=True)
class CharacterProblem:
    id: int
    production_id: int
    name: str

    def __post_init__(self) -> None:
        _require_positive("character_id", self.id)
        _require_positive("production_id", self.production_id)
        if not self.name:
            raise SolverError("character name must not be empty")


@dataclass(frozen=True, slots=True)
class CastAssignmentProblem:
    character_id: int
    actor_id: int

    def __post_init__(self) -> None:
        _require_positive("character_id", self.character_id)
        _require_positive("actor_id", self.actor_id)


@dataclass(frozen=True, slots=True)
class SceneCharacterProblem:
    scene_id: int
    character_id: int
    required: bool

    def __post_init__(self) -> None:
        _require_positive("scene_id", self.scene_id)
        _require_positive("character_id", self.character_id)


@dataclass(frozen=True, slots=True)
class AvailabilityProblem:
    actor_id: int
    window: TimeWindow

    def __post_init__(self) -> None:
        _require_positive("actor_id", self.actor_id)


@dataclass(frozen=True, slots=True)
class SchedulingProblem:
    production: ProductionProblem
    scenes: list[SceneProblem]
    actors: list[ActorProblem]
    characters: list[CharacterProblem]
    cast_assignments: list[CastAssignmentProblem]
    scene_characters: list[SceneCharacterProblem]
    availability: list[AvailabilityProblem]
    minimum_session_minutes: int = 60
    allow_parallel_rehearsals: bool = True
    random_seed: int = 1
    max_solver_seconds: float = 5.0

    def __post_init__(self) -> None:
        _require_positive("minimum_session_minutes", self.minimum_session_minutes)
        _require_positive("random_seed", self.random_seed)
        if self.max_solver_seconds <= 0:
            raise SolverError("max_solver_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ScheduledSession:
    scene_id: int
    scene_code: str
    actor_ids: frozenset[int]
    start: datetime
    end: datetime
    duration_minutes: int
    solver_score: int


@dataclass(frozen=True, slots=True)
class SchedulingResult:
    status: SchedulingStatus
    sessions: tuple[ScheduledSession, ...]
    score: int
    metrics: dict[str, int]
    violations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _SessionCandidate:
    scene_id: int
    scene_code: str
    actor_ids: frozenset[int]
    priority: int
    start: datetime
    end: datetime
    duration_minutes: int
    score: int


def rehearsal_debt_minutes(scene: SceneProblem) -> int:
    return max(0, scene.target_rehearsal_minutes - scene.completed_rehearsal_minutes)


def generate_schedule(
    problem: SchedulingProblem,
    *,
    weights: SolverWeights = BALANCED_WEIGHTS,
) -> SchedulingResult:
    if not problem.scenes:
        return _empty_result(SchedulingStatus.OPTIMAL)

    candidates = _build_session_candidates(problem)
    if not candidates:
        return _result_from_candidates(problem, ())

    model = cp_model.CpModel()
    variables = [model.new_bool_var(f"candidate_{index}") for index, _ in enumerate(candidates)]
    _add_scene_target_constraints(model, variables, candidates, problem)
    _add_actor_overlap_constraints(model, variables, candidates)
    if not problem.allow_parallel_rehearsals:
        _add_production_overlap_constraints(model, variables, candidates)
    objective_terms: list[cp_model.LinearExpr] = [
        variables[index] * _candidate_objective(candidate, index, weights)
        for index, candidate in enumerate(candidates)
    ]
    objective_terms.extend(_pairwise_objective_terms(model, variables, candidates, weights))
    model.maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.random_seed = problem.random_seed
    solver.parameters.max_time_in_seconds = problem.max_solver_seconds
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SchedulingResult(
            status=SchedulingStatus.INFEASIBLE,
            sessions=(),
            score=0,
            metrics=_metrics(problem, ()),
            violations=("solver found no feasible assignment",),
        )

    chosen = tuple(
        candidate
        for index, candidate in enumerate(candidates)
        if solver.boolean_value(variables[index])
    )
    return _result_from_candidates(problem, chosen, optimal=status == cp_model.OPTIMAL)


def generate_schedule_options(problem: SchedulingProblem) -> dict[str, SchedulingResult]:
    return {
        SchedulingMode.EFFICIENT.value: generate_schedule(problem, weights=EFFICIENT_WEIGHTS),
        SchedulingMode.BALANCED.value: generate_schedule(problem, weights=BALANCED_WEIGHTS),
        SchedulingMode.SCENE_PRIORITY.value: generate_schedule(
            problem,
            weights=SCENE_PRIORITY_WEIGHTS,
        ),
    }


def _build_session_candidates(problem: SchedulingProblem) -> list[_SessionCandidate]:
    production_windows = _production_windows(problem.production, _problem_timezone(problem))
    availability_by_actor = _availability_by_actor(problem)
    candidates: list[_SessionCandidate] = []

    for scene in sorted(problem.scenes, key=lambda item: item.id):
        debt = rehearsal_debt_minutes(scene)
        if debt <= 0:
            continue
        duration_options = _candidate_duration_options(
            debt,
            problem.production.slot_duration_minutes,
            problem.minimum_session_minutes,
        )
        actor_ids = _required_actor_ids(scene, problem)
        context = ConflictContext(
            availability_by_actor={
                actor_id: _windows_inside_production(
                    availability_by_actor.get(actor_id, []), production_windows
                )
                for actor_id in actor_ids
            },
            existing_sessions=[],
            slot_duration_minutes=problem.production.slot_duration_minutes,
            minimum_session_minutes=min(problem.minimum_session_minutes, min(duration_options)),
        )
        for duration_minutes in duration_options:
            starts = find_valid_session_starts(
                scene=SceneInput(scene.id, scene.scene_code, actor_ids),
                duration_minutes=duration_minutes,
                context=context,
            )
            for start in starts:
                end = _add_elapsed_time(start, timedelta(minutes=duration_minutes))
                candidates.append(
                    _SessionCandidate(
                        scene_id=scene.id,
                        scene_code=scene.scene_code,
                        actor_ids=actor_ids,
                        priority=scene.priority,
                        start=start,
                        end=end,
                        duration_minutes=duration_minutes,
                        score=duration_minutes,
                    )
                )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.start,
            candidate.scene_id,
            candidate.duration_minutes,
            tuple(sorted(candidate.actor_ids)),
        ),
    )


def _candidate_duration_options(
    debt_minutes: int,
    slot_duration_minutes: int,
    minimum_session_minutes: int,
) -> list[int]:
    if debt_minutes < minimum_session_minutes:
        return [debt_minutes] if debt_minutes > 0 else []

    maximum_slot_aligned_minutes = (debt_minutes // slot_duration_minutes) * slot_duration_minutes
    durations: list[int] = []
    current = maximum_slot_aligned_minutes
    while current >= minimum_session_minutes:
        durations.append(current)
        current -= slot_duration_minutes
    return durations


def _required_actor_ids(scene: SceneProblem, problem: SchedulingProblem) -> frozenset[int]:
    resolution = get_required_actors(
        scene_id=scene.id,
        characters=[
            CharacterInput(character.id, character.production_id, character.name)
            for character in problem.characters
        ],
        cast_assignments=[
            CastAssignmentInput(assignment.character_id, assignment.actor_id)
            for assignment in problem.cast_assignments
        ],
        scene_characters=[
            SceneCharacterInput(link.scene_id, link.character_id, link.required)
            for link in problem.scene_characters
        ],
    )
    return resolution.actor_ids


def _availability_by_actor(problem: SchedulingProblem) -> dict[int, list[TimeWindow]]:
    windows: dict[int, list[TimeWindow]] = {}
    for item in problem.availability:
        windows.setdefault(item.actor_id, []).append(item.window)
    return windows


def _production_windows(production: ProductionProblem, timezone: tzinfo) -> list[TimeWindow]:
    windows: list[TimeWindow] = []
    current = production.rehearsal_start_date
    while current <= production.rehearsal_end_date:
        start = datetime.combine(current, production.daily_start_time, tzinfo=timezone)
        end = datetime.combine(current, production.daily_end_time, tzinfo=timezone)
        windows.append(TimeWindow(start, end))
        current = current + timedelta(days=1)
    return windows


def _problem_timezone(problem: SchedulingProblem) -> tzinfo:
    if problem.production.daily_start_time.tzinfo is not None:
        return problem.production.daily_start_time.tzinfo
    if problem.availability:
        return problem.availability[0].window.start.tzinfo or UTC
    return UTC


def _windows_inside_production(
    actor_windows: list[TimeWindow],
    production_windows: list[TimeWindow],
) -> list[TimeWindow]:
    from backend.app.services.availability.time_windows import intersect_windows

    return intersect_windows(actor_windows, production_windows)


def _add_scene_target_constraints(
    model: cp_model.CpModel,
    variables: list[cp_model.IntVar],
    candidates: list[_SessionCandidate],
    problem: SchedulingProblem,
) -> None:
    for scene in problem.scenes:
        scene_variables = [
            variables[index]
            for index, candidate in enumerate(candidates)
            if candidate.scene_id == scene.id
        ]
        if not scene_variables:
            continue
        model.add(sum(scene_variables) <= 1)


def _add_actor_overlap_constraints(
    model: cp_model.CpModel,
    variables: list[cp_model.IntVar],
    candidates: list[_SessionCandidate],
) -> None:
    for left_index, left in enumerate(candidates):
        for right_index in range(left_index + 1, len(candidates)):
            right = candidates[right_index]
            if not left.actor_ids.intersection(right.actor_ids):
                continue
            if _candidates_overlap(left, right):
                model.add(variables[left_index] + variables[right_index] <= 1)


def _add_production_overlap_constraints(
    model: cp_model.CpModel,
    variables: list[cp_model.IntVar],
    candidates: list[_SessionCandidate],
) -> None:
    for left_index, left in enumerate(candidates):
        for right_index in range(left_index + 1, len(candidates)):
            right = candidates[right_index]
            if _candidates_overlap(left, right):
                model.add(variables[left_index] + variables[right_index] <= 1)


def _candidates_overlap(left: _SessionCandidate, right: _SessionCandidate) -> bool:
    return left.start < right.end and right.start < left.end


def _candidate_objective(
    candidate: _SessionCandidate,
    candidate_index: int,
    weights: SolverWeights = BALANCED_WEIGHTS,
) -> int:
    return (
        candidate.score * weights.rehearsal_minute_reward
        + candidate.duration_minutes * candidate.priority * weights.priority_reward
        - candidate_index * weights.earlier_start_reward
    )


def _pairwise_objective_terms(
    model: cp_model.CpModel,
    variables: list[cp_model.IntVar],
    candidates: list[_SessionCandidate],
    weights: SolverWeights,
) -> list[cp_model.LinearExpr]:
    if weights.idle_penalty == 0 and weights.cast_grouping_reward == 0:
        return []

    terms: list[cp_model.LinearExpr] = []
    for left_index, left in enumerate(candidates):
        for right_index in range(left_index + 1, len(candidates)):
            right = candidates[right_index]
            adjustment = _pairwise_objective_adjustment(left, right, weights)
            if adjustment == 0:
                continue
            pair_variable = model.new_bool_var(f"pair_{left_index}_{right_index}")
            model.add(pair_variable <= variables[left_index])
            model.add(pair_variable <= variables[right_index])
            model.add(pair_variable >= variables[left_index] + variables[right_index] - 1)
            terms.append(pair_variable * adjustment)
    return terms


def _pairwise_objective_adjustment(
    left: _SessionCandidate,
    right: _SessionCandidate,
    weights: SolverWeights,
) -> int:
    if _candidates_overlap(left, right):
        return 0

    adjustment = 0
    shared_actor_count = len(left.actor_ids.intersection(right.actor_ids))
    if shared_actor_count:
        adjustment -= (
            _same_day_idle_minutes(left, right) * shared_actor_count * weights.idle_penalty
        )
    if _sessions_touch(left, right):
        adjustment += _cast_similarity_percent(left, right) * weights.cast_grouping_reward
    return adjustment


def _same_day_idle_minutes(left: _SessionCandidate, right: _SessionCandidate) -> int:
    earlier, later = (left, right) if left.start <= right.start else (right, left)
    if earlier.end.date() != later.start.date():
        return 0
    gap = later.start - earlier.end
    return max(0, int(gap.total_seconds() // 60))


def _sessions_touch(left: _SessionCandidate, right: _SessionCandidate) -> bool:
    return left.end == right.start or right.end == left.start


def _cast_similarity_percent(left: _SessionCandidate, right: _SessionCandidate) -> int:
    union = left.actor_ids.union(right.actor_ids)
    if not union:
        return 0
    return len(left.actor_ids.intersection(right.actor_ids)) * 100 // len(union)


def _result_from_candidates(
    problem: SchedulingProblem,
    candidates: tuple[_SessionCandidate, ...],
    *,
    optimal: bool = True,
) -> SchedulingResult:
    sessions = tuple(
        ScheduledSession(
            scene_id=candidate.scene_id,
            scene_code=candidate.scene_code,
            actor_ids=candidate.actor_ids,
            start=candidate.start,
            end=candidate.end,
            duration_minutes=candidate.duration_minutes,
            solver_score=candidate.score,
        )
        for candidate in sorted(candidates, key=lambda item: (item.start, item.scene_id))
    )
    total_debt = sum(rehearsal_debt_minutes(scene) for scene in problem.scenes)
    scheduled_minutes = sum(session.duration_minutes for session in sessions)
    status = (
        SchedulingStatus.OPTIMAL
        if optimal and scheduled_minutes == total_debt
        else SchedulingStatus.FEASIBLE
    )
    return SchedulingResult(
        status=status,
        sessions=sessions,
        score=scheduled_minutes,
        metrics=_metrics(problem, sessions),
        violations=(),
    )


def _metrics(
    problem: SchedulingProblem,
    sessions: tuple[ScheduledSession, ...] | tuple[()],
) -> dict[str, int]:
    total_debt = sum(rehearsal_debt_minutes(scene) for scene in problem.scenes)
    scheduled_minutes = sum(session.duration_minutes for session in sessions)
    rehearsal_days = len({session.start.date() for session in sessions})
    return {
        "total_rehearsal_minutes": scheduled_minutes,
        "number_of_rehearsal_days": rehearsal_days,
        "scene_rehearsal_debt_completed": scheduled_minutes,
        "remaining_rehearsal_debt": max(0, total_debt - scheduled_minutes),
        "objective_score": scheduled_minutes,
    }


def _empty_result(status: SchedulingStatus) -> SchedulingResult:
    return SchedulingResult(
        status=status,
        sessions=(),
        score=0,
        metrics={
            "total_rehearsal_minutes": 0,
            "number_of_rehearsal_days": 0,
            "scene_rehearsal_debt_completed": 0,
            "remaining_rehearsal_debt": 0,
            "objective_score": 0,
        },
        violations=(),
    )


def _require_positive(label: str, value: int) -> None:
    if value <= 0:
        raise SolverError(f"{label} must be positive")
