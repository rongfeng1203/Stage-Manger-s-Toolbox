# Data Model

Persistent Day 1 entities are implemented in `backend/app/models/entities.py`.
Pure Day 3 cast-resolution input and output types are implemented in
`backend/app/services/cast/requirements.py`.

## Production

- `id`
- `name`
- `rehearsal_start_date`
- `rehearsal_end_date`
- `daily_start_time`
- `daily_end_time`
- `slot_duration_minutes`

## Scene

- `id`
- `production_id`
- `scene_code`
- `title`
- `page_start`
- `page_end`
- `priority`
- `target_rehearsal_minutes`
- `completed_rehearsal_minutes`

## Character

- `id`
- `production_id`
- `name`

## Actor

- `id`
- `name`
- `email`
- `calendar_connected`

## Cast Assignment

- `character_id`
- `actor_id`

## Scene Character

- `scene_id`
- `character_id`
- `required`

Optional scene characters are excluded from the required actor set used by the
conflict engine and solver.

## Availability Window

- `id`
- `actor_id`
- `start_datetime`
- `end_datetime`
- `availability_type`

## Rehearsal Session

- `id`
- `scene_id`
- `start_datetime`
- `end_datetime`
- `status`
- `solver_score`

## Cast Requirement Resolution

`RequirementResolution` is a serializable service result containing:

- `scene_id`
- `actor_ids`
- `warnings`

Warnings currently include:

- `MISSING_CAST_ASSIGNMENT`
- `UNKNOWN_CHARACTER`
