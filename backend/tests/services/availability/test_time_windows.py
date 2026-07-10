from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.availability.time_windows import (
    TimeWindow,
    TimeWindowError,
    _add_elapsed_time,
    _merge_windows,
    _require_timezone,
    _sorted_valid_windows,
    _subtract_one,
    _to_utc,
    _validate_slot_duration,
    generate_time_slots,
    intersect_windows,
    is_slot_aligned,
    subtract_busy_windows,
    validate_time_window,
)

TORONTO = ZoneInfo("America/Toronto")


def dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=TORONTO)


def test_validate_time_window_accepts_timezone_aware_forward_range() -> None:
    window = TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 22))

    assert validate_time_window(window) == window


def test_validate_time_window_rejects_naive_datetimes() -> None:
    window = TimeWindow(datetime(2026, 7, 9, 18), dt(2026, 7, 9, 22))

    with pytest.raises(TimeWindowError, match="timezone"):
        validate_time_window(window)


def test_validate_time_window_rejects_start_at_or_after_end() -> None:
    window = TimeWindow(dt(2026, 7, 9, 22), dt(2026, 7, 9, 18))

    with pytest.raises(TimeWindowError, match="before"):
        validate_time_window(window)


def test_is_slot_aligned_accepts_times_on_slot_grid() -> None:
    origin = dt(2026, 7, 9, 18)

    assert is_slot_aligned(dt(2026, 7, 9, 19, 30), origin, 30)


def test_is_slot_aligned_rejects_times_between_slots() -> None:
    origin = dt(2026, 7, 9, 18)

    assert not is_slot_aligned(dt(2026, 7, 9, 19, 15), origin, 30)


def test_is_slot_aligned_rejects_non_positive_slot_duration() -> None:
    with pytest.raises(TimeWindowError, match="positive"):
        is_slot_aligned(dt(2026, 7, 9, 19), dt(2026, 7, 9, 18), 0)


def test_generate_time_slots_returns_half_open_slot_starts() -> None:
    window = TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 20))

    slots = generate_time_slots(window, slot_duration_minutes=30)

    assert slots == [
        dt(2026, 7, 9, 18),
        dt(2026, 7, 9, 18, 30),
        dt(2026, 7, 9, 19),
        dt(2026, 7, 9, 19, 30),
    ]


def test_generate_time_slots_excludes_partial_final_slot() -> None:
    window = TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 19, 45))

    slots = generate_time_slots(window, slot_duration_minutes=60)

    assert slots == [dt(2026, 7, 9, 18)]


def test_generate_time_slots_preserves_dst_offset_change() -> None:
    window = TimeWindow(
        datetime(2026, 3, 8, 1, 0, tzinfo=TORONTO),
        datetime(2026, 3, 8, 4, 0, tzinfo=TORONTO),
    )

    slots = generate_time_slots(window, slot_duration_minutes=30)

    assert slots == [
        datetime(2026, 3, 8, 1, 0, tzinfo=TORONTO),
        datetime(2026, 3, 8, 1, 30, tzinfo=TORONTO),
        datetime(2026, 3, 8, 3, 0, tzinfo=TORONTO),
        datetime(2026, 3, 8, 3, 30, tzinfo=TORONTO),
    ]
    assert slots[0].utcoffset() == timedelta(hours=-5)
    assert slots[-1].utcoffset() == timedelta(hours=-4)


def test_intersect_windows_returns_common_overlap() -> None:
    left = [TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 22))]
    right = [TimeWindow(dt(2026, 7, 9, 20), dt(2026, 7, 9, 21))]

    assert intersect_windows(left, right) == [TimeWindow(dt(2026, 7, 9, 20), dt(2026, 7, 9, 21))]


def test_intersect_windows_returns_empty_when_only_touching() -> None:
    left = [TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 20))]
    right = [TimeWindow(dt(2026, 7, 9, 20), dt(2026, 7, 9, 22))]

    assert intersect_windows(left, right) == []


def test_intersect_windows_handles_unsorted_multiple_windows() -> None:
    left = [
        TimeWindow(dt(2026, 7, 9, 21), dt(2026, 7, 9, 23)),
        TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 20)),
    ]
    right = [
        TimeWindow(dt(2026, 7, 9, 19), dt(2026, 7, 9, 22)),
    ]

    assert intersect_windows(left, right) == [
        TimeWindow(dt(2026, 7, 9, 19), dt(2026, 7, 9, 20)),
        TimeWindow(dt(2026, 7, 9, 21), dt(2026, 7, 9, 22)),
    ]


def test_subtract_busy_windows_removes_middle_busy_period() -> None:
    available = [TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 22))]
    busy = [TimeWindow(dt(2026, 7, 9, 19), dt(2026, 7, 9, 20))]

    assert subtract_busy_windows(available, busy) == [
        TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 19)),
        TimeWindow(dt(2026, 7, 9, 20), dt(2026, 7, 9, 22)),
    ]


def test_subtract_busy_windows_handles_overlapping_busy_windows() -> None:
    available = [TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 23))]
    busy = [
        TimeWindow(dt(2026, 7, 9, 19), dt(2026, 7, 9, 21)),
        TimeWindow(dt(2026, 7, 9, 20), dt(2026, 7, 9, 22)),
    ]

    assert subtract_busy_windows(available, busy) == [
        TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 19)),
        TimeWindow(dt(2026, 7, 9, 22), dt(2026, 7, 9, 23)),
    ]


def test_subtract_busy_windows_ignores_non_overlapping_busy_windows() -> None:
    available = [TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 20))]
    busy = [TimeWindow(dt(2026, 7, 9, 21), dt(2026, 7, 9, 22))]

    assert subtract_busy_windows(available, busy) == available


def test_subtract_one_returns_original_window_when_busy_does_not_overlap() -> None:
    available = TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 20))
    busy = TimeWindow(dt(2026, 7, 9, 21), dt(2026, 7, 9, 22))

    assert _subtract_one(available, busy) == [available]


def test_subtract_one_removes_window_when_busy_covers_it() -> None:
    available = TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 20))
    busy = TimeWindow(dt(2026, 7, 9, 17), dt(2026, 7, 9, 21))

    assert _subtract_one(available, busy) == []


def test_merge_windows_combines_overlapping_and_touching_windows() -> None:
    windows = [
        TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 19)),
        TimeWindow(dt(2026, 7, 9, 19), dt(2026, 7, 9, 20)),
        TimeWindow(dt(2026, 7, 9, 21), dt(2026, 7, 9, 22)),
    ]

    assert _merge_windows(windows) == [
        TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 20)),
        TimeWindow(dt(2026, 7, 9, 21), dt(2026, 7, 9, 22)),
    ]


def test_merge_windows_returns_empty_list_for_empty_input() -> None:
    assert _merge_windows([]) == []


def test_sorted_valid_windows_returns_windows_by_start_time() -> None:
    windows = [
        TimeWindow(dt(2026, 7, 9, 21), dt(2026, 7, 9, 22)),
        TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 19)),
    ]

    assert _sorted_valid_windows(windows) == [
        TimeWindow(dt(2026, 7, 9, 18), dt(2026, 7, 9, 19)),
        TimeWindow(dt(2026, 7, 9, 21), dt(2026, 7, 9, 22)),
    ]


def test_validate_slot_duration_accepts_positive_minutes() -> None:
    assert _validate_slot_duration(30) is None


def test_validate_slot_duration_rejects_negative_minutes() -> None:
    with pytest.raises(TimeWindowError, match="positive"):
        _validate_slot_duration(-30)


def test_require_timezone_accepts_aware_datetime() -> None:
    assert _require_timezone(dt(2026, 7, 9, 18)) is None


def test_require_timezone_rejects_naive_datetime() -> None:
    with pytest.raises(TimeWindowError, match="timezone"):
        _require_timezone(datetime(2026, 7, 9, 18))


def test_to_utc_converts_timezone_aware_datetime() -> None:
    assert _to_utc(dt(2026, 7, 9, 18)).isoformat() == "2026-07-09T22:00:00+00:00"


def test_add_elapsed_time_skips_nonexistent_local_time_across_dst() -> None:
    value = datetime(2026, 3, 8, 1, 30, tzinfo=TORONTO)

    result = _add_elapsed_time(value, timedelta(minutes=30))

    assert result == datetime(2026, 3, 8, 3, 0, tzinfo=TORONTO)
