from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class TimeWindowError(ValueError):
    """Raised when a time window or slot configuration is invalid."""


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: datetime
    end: datetime


def validate_time_window(window: TimeWindow) -> TimeWindow:
    _require_timezone(window.start)
    _require_timezone(window.end)
    if window.start >= window.end:
        raise TimeWindowError("window start must be before window end")
    return window


def is_slot_aligned(value: datetime, origin: datetime, slot_duration_minutes: int) -> bool:
    _validate_slot_duration(slot_duration_minutes)
    _require_timezone(value)
    _require_timezone(origin)
    elapsed_seconds = (_to_utc(value) - _to_utc(origin)).total_seconds()
    slot_seconds = slot_duration_minutes * 60
    return elapsed_seconds % slot_seconds == 0


def generate_time_slots(window: TimeWindow, slot_duration_minutes: int) -> list[datetime]:
    validate_time_window(window)
    _validate_slot_duration(slot_duration_minutes)

    slot_duration = timedelta(minutes=slot_duration_minutes)
    current = window.start
    slots: list[datetime] = []

    while _to_utc(_add_elapsed_time(current, slot_duration)) <= _to_utc(window.end):
        slots.append(current)
        current = _add_elapsed_time(current, slot_duration)

    return slots


def intersect_windows(left: list[TimeWindow], right: list[TimeWindow]) -> list[TimeWindow]:
    left_windows = _sorted_valid_windows(left)
    right_windows = _sorted_valid_windows(right)
    intersections: list[TimeWindow] = []
    left_index = 0
    right_index = 0

    while left_index < len(left_windows) and right_index < len(right_windows):
        left_window = left_windows[left_index]
        right_window = right_windows[right_index]
        start = max(left_window.start, right_window.start)
        end = min(left_window.end, right_window.end)

        if _to_utc(start) < _to_utc(end):
            intersections.append(TimeWindow(start, end))

        if _to_utc(left_window.end) <= _to_utc(right_window.end):
            left_index += 1
        else:
            right_index += 1

    return intersections


def subtract_busy_windows(
    available_windows: list[TimeWindow], busy_windows: list[TimeWindow]
) -> list[TimeWindow]:
    remaining = _sorted_valid_windows(available_windows)

    for busy_window in _merge_windows(_sorted_valid_windows(busy_windows)):
        next_remaining: list[TimeWindow] = []
        for available_window in remaining:
            next_remaining.extend(_subtract_one(available_window, busy_window))
        remaining = next_remaining

    return remaining


def _subtract_one(available: TimeWindow, busy: TimeWindow) -> list[TimeWindow]:
    if _to_utc(busy.end) <= _to_utc(available.start) or _to_utc(busy.start) >= _to_utc(
        available.end
    ):
        return [available]

    parts: list[TimeWindow] = []
    if _to_utc(available.start) < _to_utc(busy.start):
        parts.append(TimeWindow(available.start, busy.start))
    if _to_utc(busy.end) < _to_utc(available.end):
        parts.append(TimeWindow(busy.end, available.end))
    return parts


def _merge_windows(windows: list[TimeWindow]) -> list[TimeWindow]:
    if not windows:
        return []

    merged = [windows[0]]
    for window in windows[1:]:
        last = merged[-1]
        if _to_utc(window.start) <= _to_utc(last.end):
            merged[-1] = TimeWindow(last.start, max(last.end, window.end))
        else:
            merged.append(window)
    return merged


def _sorted_valid_windows(windows: list[TimeWindow]) -> list[TimeWindow]:
    return sorted((validate_time_window(window) for window in windows), key=lambda item: item.start)


def _validate_slot_duration(slot_duration_minutes: int) -> None:
    if slot_duration_minutes <= 0:
        raise TimeWindowError("slot duration must be positive")


def _require_timezone(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeWindowError("datetime must include timezone information")


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _add_elapsed_time(value: datetime, duration: timedelta) -> datetime:
    return (_to_utc(value) + duration).astimezone(value.tzinfo)
