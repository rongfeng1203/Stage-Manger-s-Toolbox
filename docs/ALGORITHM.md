# Algorithm

The scheduler will use discrete time slots and hard constraints before soft
scoring. Day 1 defines the project foundation only; solver implementation starts
after time, availability, and cast-resolution utilities are tested.

Hard constraints planned for the MVP:

- Required actor availability.
- Actor overlap prevention.
- Session contiguity.
- Production date window.
- Daily rehearsal hours.
- Minimum session length.
- Rehearsal target cap unless overrun is explicitly enabled.

Soft scoring must remain explainable and deterministic.

## Day 2 Time And Availability Engine

Implemented pure functions live in
`backend/app/services/availability/time_windows.py`.

- `validate_time_window()` requires timezone-aware datetimes and `start < end`.
- `is_slot_aligned()` checks alignment from a timezone-aware origin using elapsed
  UTC time.
- `generate_time_slots()` returns half-open slot starts. A 18:00-20:00 window at
  30-minute slots returns 18:00, 18:30, 19:00, and 19:30.
- `intersect_windows()` returns sorted common overlaps. Touching endpoints are
  not an overlap.
- `subtract_busy_windows()` removes busy intervals from available intervals and
  returns sorted remaining windows.

DST policy: slot generation steps through real elapsed time and converts back to
the source timezone. Nonexistent local times during spring-forward transitions
are not emitted.

## Day 3 Cast Requirement Resolution

Implemented pure functions live in `backend/app/services/cast/requirements.py`.

- `get_required_actors(scene_id)` resolves the set of required actor IDs for a
  scene from characters, cast assignments, and scene-character links.
- Optional scene characters do not block scheduling and are excluded from the
  required actor set.
- Actor doubling is collapsed naturally because the result is a set of actor IDs.
- Missing cast assignments produce structured warnings, not exceptions.
- Unknown scene-character references produce structured warnings.
- Duplicate cast assignments are normalized when identical. Conflicting
  duplicate assignments are rejected by default, with an explicit `KEEP_FIRST`
  policy available for imports that need deterministic normalization.
