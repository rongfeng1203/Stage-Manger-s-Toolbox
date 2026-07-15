# Testing

No function is complete until its test passes.

Day 1 verification commands:

```bash
.venv/bin/pytest backend/tests
.venv/bin/pytest backend/tests/services/availability
.venv/bin/pytest backend/tests/services/cast
.venv/bin/pytest backend/tests/services/scheduling
.venv/bin/mypy backend/app
.venv/bin/ruff check backend
cd frontend
npm run test
npm run lint
npm run build
npm run e2e
```

Bug fixes require a regression test before the fix is considered complete.

Day 2 added direct unit tests for every public and private time-window function,
plus Hypothesis property tests for slot alignment and busy-window subtraction.

Day 3 added direct unit tests for cast requirement resolution, actor doubling,
optional scene characters, duplicate cast assignment policy, missing cast
warnings, unknown character warnings, and private validation helpers.

Day 4 added React component tests and a Playwright flow for:

- Create production.
- Add actor.
- Add character.
- Assign character to actor.
- Add scene.
- Assign character to scene.
- Add availability.
- Set rehearsal target minutes.

Day 5 added direct unit tests for the pure conflict engine:

- Common availability intersection.
- Single-session schedule checks.
- Actor busy conflicts.
- Actor overlap conflicts.
- Minimum session length conflicts.
- Slot-alignment conflicts.
- Valid session start discovery.
- DST-sensitive requested windows.
- Private validation and overlap helpers.

Day 6 added CP-SAT hard-constraint solver tests for:

- One scene with one available actor.
- Fully unavailable actor returns feasible partial output with remaining debt.
- Multi-actor availability intersection.
- Shared actor sessions never overlap.
- Different-cast overlap is allowed when parallel rehearsals are enabled.
- Production-level parallel rehearsals can be disabled.
- 90-minute sessions use three contiguous 30-minute slots.
- Rehearsal debt calculation.
- Impossible targets allow partial coverage.
- Deterministic solver output.
- Private solver helper functions.

Day 7 added direct scoring tests for:

- Actor idle minutes.
- Actor daily workload.
- Scene rehearsal debt coverage.
- Cast Jaccard similarity.
- Short-call penalties.
- Schedule metrics summaries.
- Critical scene coverage.
- Private scoring helpers and validation.

Day 8 added solver mode tests for:

- Returning exactly efficient, balanced, and scene-priority options.
- Preserving the same hard shared-actor overlap constraints in every mode.
- Favoring critical scenes under scene-priority weights when only one scene can
  fit.
- Favoring adjacent same-actor sessions under efficient weights.
- Allowing custom `SolverWeights` to alter deterministic candidate preference.
- Rejecting invalid negative weights.
- Producing deterministic mode-option results across repeated calls.

Day 9 added frontend tests and E2E coverage for:

- Generating three comparable plan cards from manual input.
- Showing a metrics comparison table.
- Showing a selected daily timeline.
- Showing scene debt completion and remaining debt.
- Showing conflict output for incomplete scheduling inputs.

Day 10 added frontend tests and E2E coverage for:

- Moving a generated session and revalidating actor availability.
- Changing session duration and revalidating minimum duration.
- Deleting a session and refreshing scene debt.
- Adding a manual session and reporting actor double-booking.

Day 11 added golden-file parser and UI coverage for:

- Standard play format and mixed capitalization.
- Empty scenes, stage directions, and two-word character names.
- Repeated scene headers and invalid scripts.
- Editable review followed by explicit import confirmation.

Day 12 added interface-isolated calendar coverage for:

- Event title, description, called cast, and invite construction.
- OAuth URL construction.
- Fake and Google publisher behavior.
- Approval and clean-conflict publication gates.
- Per-event calendar failure reports.
- Frontend event preview and publish result rendering.

Day 13 added named small, medium, conflict-heavy, doubling-heavy, and impossible
productions. Deterministic repeat tests cover the bounded fixtures; the medium
fixture is a performance smoke test. Boundary regressions cover duplicate IDs,
zero/negative values, midnight crossing, DST gaps and ambiguity, missing email,
missing cast, and calendar failure.

Day 14 adds a Playwright release flow for loading the complete demo production,
reviewing the balanced plan, previewing calendar events, explicit approval, and
successful demo publication.

Post-release script import coverage adds UTF-8 and Windows-1252 text extraction,
supported extension checks, valid text-based PDF extraction, scanned-PDF OCR
errors, corrupt PDF errors, upload size limits, headerless transition inference,
numbered character cues, frontend automatic analysis, and a Playwright file upload
flow.
