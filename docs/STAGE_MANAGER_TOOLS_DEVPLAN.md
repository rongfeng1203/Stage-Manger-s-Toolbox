# Stage Manager Tools Development Plan

## Purpose

Extend the deterministic Stage Scheduler into a working stage-management
toolbox without weakening the scheduling engine. The next module follows the
original roadmap's post-MVP entities: stage, blocking beat, actor position,
movement, cue, and trigger.

The tools must remain useful without an LLM. Automation may help parse inputs,
but operational records and validation stay structured, reviewable, and
deterministic.

## Product Order

1. Blocking notebook
2. Rehearsal running tools
3. Rehearsal reports
4. Performance cue stack
5. Export, persistence, and collaboration hardening

Only one major module is implemented at a time.

## Phase 1: Blocking Notebook MVP

Status: COMPLETE (2026-07-17)

### User Workflow

1. Select an imported scene.
2. Create an ordered blocking beat.
3. Select an actor and click the stage plot to place them.
4. Switch to movement mode and click a new location to record movement.
5. Add light, sound, actor, scenery, or other cues with explicit triggers.
6. Validate the notebook and receive explainable issues.
7. Refresh the browser without losing blocking work.

### Structured Data

- `Stage`: width and depth in normalized units.
- `BlockingBeat`: id, scene id, label, and order.
- `ActorPosition`: actor id plus stage `x` and `y` coordinates.
- `Movement`: actor id, origin, destination, and sequence.
- `Cue`: id, type, label, and trigger.

Coordinates use a deterministic 0-100 stage space:

- `x = 0`: stage right (viewer left)
- `x = 100`: stage left (viewer right)
- `y = 0`: upstage
- `y = 100`: downstage

### Validation Rules

- Stage dimensions must be positive.
- Beat ids and cue ids must be unique.
- Every beat must reference a known scene.
- Every position and movement actor must reference a known actor.
- Coordinates must remain inside the stage bounds.
- An actor may have only one position in a beat.
- Movement origins must match the actor's prior position in that beat.
- Cue labels and triggers are required.
- Validation returns structured issues instead of a bare boolean.

### Acceptance Criteria

- [x] Pure Python blocking validation has direct unit tests.
- [x] FastAPI serializes valid and invalid notebook results.
- [x] The UI provides beat creation and selection.
- [x] The stage plot supports actor placement and recorded movement.
- [x] The UI provides cue entry and a cue table.
- [x] Empty actor and scene states link back to the required setup sections.
- [x] Blocking data persists in browser storage.
- [x] Backend, component, lint, type, build, and browser checks pass.
- [x] The production deployment exposes the working module.

## Phase 2: Rehearsal Running Tools

Status: PLANNED

- Session check-in and attendance states.
- Start, pause, resume, and complete rehearsal timing.
- Scene progress and completed rehearsal-minute updates.
- Timestamped rehearsal notes with department and priority.
- Carry-forward items for the next rehearsal.

## Phase 3: Rehearsal Reports

Status: PLANNED

- Generate a report from attendance, timing, notes, and schedule changes.
- Organize notes by scenic, props, costumes, lighting, sound, and production.
- Preview before export or distribution.
- Export a deterministic PDF and printable HTML version.

## Phase 4: Performance Cue Stack

Status: PLANNED

- Ordered standby and go states.
- Cue type, operator, trigger, action, and completion status.
- Keyboard-efficient progression with explicit confirmation.
- Timestamped run history and incident notes.

## Phase 5: Hardening

Status: PLANNED

- Move production state from browser-only storage to durable persistence.
- Add import/export for toolbox data.
- Add role-aware collaboration only after single-user reliability is proven.
- Add accessibility, mobile, recovery, and adversarial workflow coverage.

## Engineering Rules

- Business validation stays framework-independent.
- FastAPI only parses and serializes requests.
- React does not duplicate backend validation rules.
- Every fixed defect receives a regression test.
- Existing scheduler tests must remain green before a phase is marked complete.
- The plan status and acceptance checklist are updated as implementation lands.
