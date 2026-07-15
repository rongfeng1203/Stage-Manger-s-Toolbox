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

## Day 5 Conflict Engine

Implemented pure functions live in `backend/app/services/scheduling/conflicts.py`.

- `get_scene_common_availability()` intersects the availability windows for all
  required actors in a scene.
- `can_schedule_scene()` validates one requested session and returns a
  `ScheduleCheck` with typed conflicts. It never returns only `False`.
- `find_valid_session_starts()` returns slot-aligned valid starts for a scene and
  duration.
- `detect_actor_overlap()` checks requested sessions against existing sessions
  and allows overlapping sessions when casts do not share actors.

Current conflict types:

- `ActorBusyConflict`
- `ActorOverlapConflict`
- `SessionLengthConflict`
- `SlotAlignmentConflict`

The engine uses half-open time windows. Touching sessions, such as 18:00-19:00
and 19:00-20:00, are not overlapping. Existing sessions are accepted as pure
input data; no FastAPI, database session, or frontend state is involved.

## Day 6 CP-SAT Solver V1

Implemented pure functions live in `backend/app/services/scheduling/solver.py`.

The public API is:

```python
result = generate_schedule(problem)
```

V1 uses Google OR-Tools CP-SAT and hard constraints only:

- Required actors must be available for the complete session.
- Required actors cannot be double-booked.
- Sessions are contiguous slot-aligned windows.
- Sessions are clipped to the production date range and daily rehearsal hours.
- Minimum session length defaults to 60 minutes.
- Scheduled rehearsal time does not exceed remaining scene rehearsal debt.
- Parallel rehearsals with different casts are configurable.

MVP policy for impossible targets: partial coverage is allowed. The result stays
`FEASIBLE` and reports `remaining_rehearsal_debt`.

The objective maximizes scheduled rehearsal minutes with deterministic
tie-breaking toward earlier candidate windows. Soft scoring modes are not part
of Day 6.

## Day 7 Scoring Engine

Implemented pure functions live in `backend/app/services/scheduling/scoring.py`.

The scoring engine does not use machine learning. It produces explainable
metrics from scheduled sessions and scene rehearsal debt.

Public functions:

- `calculate_idle_minutes()`
- `calculate_actor_workload()`
- `calculate_scene_debt_coverage()`
- `calculate_cast_similarity()`
- `calculate_short_call_penalty()`
- `calculate_schedule_metrics()`

Current default constants:

- `DEFAULT_DAILY_WORKLOAD_TARGET_MINUTES = 240`
- `DEFAULT_SHORT_CALL_MINUTES = 60`
- `DEFAULT_SHORT_CALL_PENALTY = -120`

`ScheduleMetrics` includes:

- `total_rehearsal_minutes`
- `number_of_rehearsal_days`
- `total_actor_idle_minutes`
- `average_actor_daily_workload`
- `maximum_actor_daily_workload`
- `scene_rehearsal_debt_completed`
- `remaining_rehearsal_debt`
- `critical_scene_coverage`
- `short_call_penalty`
- `objective_score`

The Day 7 objective score is intentionally simple:

```text
TOTAL REHEARSAL MINUTES
- ACTOR IDLE MINUTES
+ SHORT CALL PENALTY
```

## Day 8 Schedule Modes

Day 8 keeps one solver and one hard-constraint set. Modes only change the soft
objective weights.

Implemented public API:

```python
result = generate_schedule(problem)
options = generate_schedule_options(problem)
```

`generate_schedule()` defaults to balanced weights. `generate_schedule_options()`
returns:

- `efficient`
- `balanced`
- `scene_priority`

`SolverWeights` controls:

- rehearsal minute reward
- scene priority reward
- earlier-start tie-breaking
- actor idle-time penalty
- adjacent cast-grouping reward

The hard constraints from Day 6 are unchanged across all modes. For example,
shared actors still cannot overlap, production-wide parallel rehearsal policy is
still enforced, and scheduled minutes still cannot exceed scene debt.

Mode intent:

- `efficient`: favors compact adjacent calls and lower shared-actor idle time.
- `balanced`: keeps the default compromise between priority, compactness, and
  deterministic early scheduling.
- `scene_priority`: gives critical scenes a much stronger objective reward when
  limited availability forces tradeoffs.

All modes use fixed solver parameters and deterministic candidate ordering, so
repeated calls with the same `SchedulingProblem` produce repeatable results.

## Manual Edit Validation

`POST /api/schedules/validate` converts the edited plan to pure conflict-engine
inputs. Python checks availability after subtracting busy windows, shared-actor
overlap, minimum duration, slot alignment, duplicate identifiers, and scene target
overrun. It returns structured conflict codes, stage-manager-facing messages, and
recalculated scene debt. React contains no duplicate conflict rules.

Naive browser datetimes are interpreted using the request timezone. Nonexistent
spring-forward and ambiguous fallback local times are rejected with explicit
validation errors.

## Deterministic Script Parser

`DeterministicScriptParser` implements the `ScriptParser` protocol. It detects
numeric or Roman-numeral act/scene headers, contextual standalone or colon-style
character cues, stage directions, empty scenes, and repeated page headers.
Character names are normalized and accompanied by a cue-frequency table. Output
is editable and must be confirmed before import.

No LLM participates in parsing or scheduling in this release.

## Calendar Event Construction

One approved rehearsal session creates one event titled
`REHEARSAL // <SCENE CODE>`. Descriptions list the scene, called
character/actor pairs, and generator identity. Invite emails are deduplicated.
Publishing is blocked when approval is absent or validation conflicts remain.
