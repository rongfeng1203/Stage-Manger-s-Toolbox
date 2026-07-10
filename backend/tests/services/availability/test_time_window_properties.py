from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from backend.app.services.availability.time_windows import (
    TimeWindow,
    generate_time_slots,
    is_slot_aligned,
    subtract_busy_windows,
)

UTC = UTC


@st.composite
def utc_windows(draw: st.DrawFn, *, max_duration_minutes: int = 24 * 60) -> TimeWindow:
    start_offset = draw(st.integers(min_value=0, max_value=24 * 60))
    duration = draw(st.integers(min_value=1, max_value=max_duration_minutes))
    start = datetime(2026, 7, 9, tzinfo=UTC) + timedelta(minutes=start_offset)
    return TimeWindow(start, start + timedelta(minutes=duration))


@given(
    window=utc_windows(),
    slot_duration_minutes=st.sampled_from([15, 30, 45, 60, 90, 120]),
)
def test_generated_slots_are_aligned_and_inside_window(
    window: TimeWindow, slot_duration_minutes: int
) -> None:
    slots = generate_time_slots(window, slot_duration_minutes)

    for slot in slots:
        slot_end = slot + timedelta(minutes=slot_duration_minutes)
        assert is_slot_aligned(slot, window.start, slot_duration_minutes)
        assert window.start <= slot
        assert slot_end <= window.end


@given(
    available=utc_windows(max_duration_minutes=12 * 60),
    busy=utc_windows(max_duration_minutes=12 * 60),
)
def test_subtracted_windows_do_not_overlap_busy_window(
    available: TimeWindow, busy: TimeWindow
) -> None:
    remaining_windows = subtract_busy_windows([available], [busy])

    for remaining in remaining_windows:
        assert remaining.start < remaining.end
        assert not (remaining.start < busy.end and busy.start < remaining.end)
        assert available.start <= remaining.start
        assert remaining.end <= available.end

