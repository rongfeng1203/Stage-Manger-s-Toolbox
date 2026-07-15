from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date

from backend.app.services.scheduling.solver import SceneProblem, ScheduledSession

DEFAULT_DAILY_WORKLOAD_TARGET_MINUTES = 240
DEFAULT_SHORT_CALL_MINUTES = 60
DEFAULT_SHORT_CALL_PENALTY = -120


class ScoringError(ValueError):
    """Raised when scoring inputs are structurally invalid."""


@dataclass(frozen=True, slots=True)
class ScheduleMetrics:
    total_rehearsal_minutes: int
    number_of_rehearsal_days: int
    total_actor_idle_minutes: int
    average_actor_daily_workload: int
    maximum_actor_daily_workload: int
    scene_rehearsal_debt_completed: int
    remaining_rehearsal_debt: int
    critical_scene_coverage: int
    short_call_penalty: int
    objective_score: int


def calculate_idle_minutes(sessions: list[ScheduledSession]) -> int:
    sessions_by_actor_day: dict[tuple[int, date], list[ScheduledSession]] = defaultdict(list)
    for scheduled_session in sessions:
        for actor_id in scheduled_session.actor_ids:
            sessions_by_actor_day[(actor_id, scheduled_session.start.date())].append(
                scheduled_session
            )

    idle_minutes = 0
    for actor_sessions in sessions_by_actor_day.values():
        sorted_sessions = sorted(actor_sessions, key=lambda item: item.start)
        for earlier, later in zip(sorted_sessions, sorted_sessions[1:], strict=False):
            gap_minutes = int(
                (later.start.astimezone(UTC) - earlier.end.astimezone(UTC)).total_seconds() // 60
            )
            idle_minutes += max(0, gap_minutes)
    return idle_minutes


def calculate_actor_workload(sessions: list[ScheduledSession]) -> dict[tuple[int, date], int]:
    return dict(_actor_minutes_by_day(sessions))


def calculate_scene_debt_coverage(
    scenes: list[SceneProblem],
    sessions: list[ScheduledSession],
) -> dict[int, dict[str, int]]:
    scheduled_by_scene: dict[int, int] = defaultdict(int)
    for scheduled_session in sessions:
        scheduled_by_scene[scheduled_session.scene_id] += _duration_minutes(scheduled_session)

    coverage: dict[int, dict[str, int]] = {}
    for scene in scenes:
        remaining_debt = max(
            0,
            scene.target_rehearsal_minutes - scene.completed_rehearsal_minutes,
        )
        scheduled_minutes = min(remaining_debt, scheduled_by_scene[scene.id])
        coverage[scene.id] = {
            "remaining_debt": remaining_debt,
            "scheduled_minutes": scheduled_minutes,
            "remaining_after_schedule": max(0, remaining_debt - scheduled_minutes),
        }
    return coverage


def calculate_cast_similarity(
    left_actor_ids: frozenset[int],
    right_actor_ids: frozenset[int],
) -> float:
    if not left_actor_ids and not right_actor_ids:
        return 1.0
    union = left_actor_ids.union(right_actor_ids)
    if not union:
        return 0.0
    return len(left_actor_ids.intersection(right_actor_ids)) / len(union)


def calculate_short_call_penalty(
    sessions: list[ScheduledSession],
    *,
    short_call_minutes: int = DEFAULT_SHORT_CALL_MINUTES,
    penalty_per_short_call: int = DEFAULT_SHORT_CALL_PENALTY,
) -> int:
    _require_non_negative("short_call_minutes", short_call_minutes)
    actor_minutes = _actor_minutes_by_day(sessions)
    short_call_count = sum(1 for minutes in actor_minutes.values() if minutes < short_call_minutes)
    return short_call_count * penalty_per_short_call


def calculate_schedule_metrics(
    scenes: list[SceneProblem],
    sessions: list[ScheduledSession],
    *,
    daily_workload_target_minutes: int = DEFAULT_DAILY_WORKLOAD_TARGET_MINUTES,
) -> ScheduleMetrics:
    _require_non_negative("daily_workload_target_minutes", daily_workload_target_minutes)
    total_rehearsal_minutes = sum(
        _duration_minutes(scheduled_session) for scheduled_session in sessions
    )
    rehearsal_days = len({scheduled_session.start.date() for scheduled_session in sessions})
    idle_minutes = calculate_idle_minutes(sessions)
    actor_workload = calculate_actor_workload(sessions)
    average_workload = (
        round(sum(actor_workload.values()) / len(actor_workload)) if actor_workload else 0
    )
    maximum_workload = max(actor_workload.values(), default=0)
    debt_coverage = calculate_scene_debt_coverage(scenes, sessions)
    debt_completed = sum(item["scheduled_minutes"] for item in debt_coverage.values())
    remaining_debt = sum(item["remaining_after_schedule"] for item in debt_coverage.values())
    critical_coverage = _critical_scene_coverage(scenes, debt_coverage)
    short_call_penalty = calculate_short_call_penalty(sessions)
    objective_score = total_rehearsal_minutes - idle_minutes + short_call_penalty

    return ScheduleMetrics(
        total_rehearsal_minutes=total_rehearsal_minutes,
        number_of_rehearsal_days=rehearsal_days,
        total_actor_idle_minutes=idle_minutes,
        average_actor_daily_workload=average_workload,
        maximum_actor_daily_workload=maximum_workload,
        scene_rehearsal_debt_completed=debt_completed,
        remaining_rehearsal_debt=remaining_debt,
        critical_scene_coverage=critical_coverage,
        short_call_penalty=short_call_penalty,
        objective_score=objective_score,
    )


def _critical_scene_coverage(
    scenes: list[SceneProblem],
    debt_coverage: dict[int, dict[str, int]],
) -> int:
    critical_scene_ids = [scene.id for scene in scenes if scene.priority == 4]
    if not critical_scene_ids:
        return 0
    total_debt = sum(debt_coverage[scene_id]["remaining_debt"] for scene_id in critical_scene_ids)
    if total_debt == 0:
        return 100
    scheduled = sum(debt_coverage[scene_id]["scheduled_minutes"] for scene_id in critical_scene_ids)
    return round((scheduled / total_debt) * 100)


def _duration_minutes(session: ScheduledSession) -> int:
    elapsed_seconds = (session.end.astimezone(UTC) - session.start.astimezone(UTC)).total_seconds()
    return int(elapsed_seconds // 60)


def _session_actor_minutes(session: ScheduledSession) -> dict[int, int]:
    duration = _duration_minutes(session)
    return {actor_id: duration for actor_id in session.actor_ids}


def _actor_minutes_by_day(sessions: list[ScheduledSession]) -> dict[tuple[int, date], int]:
    actor_minutes: dict[tuple[int, date], int] = defaultdict(int)
    for scheduled_session in sessions:
        for actor_id, minutes in _session_actor_minutes(scheduled_session).items():
            actor_minutes[(actor_id, scheduled_session.start.date())] += minutes
    return dict(actor_minutes)


def _require_non_negative(label: str, value: int) -> None:
    if value < 0:
        raise ScoringError(f"{label} must be non-negative")
