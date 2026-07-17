from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Stage:
    width: float
    depth: float


@dataclass(frozen=True, slots=True)
class ActorPosition:
    actor_id: int
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Movement:
    actor_id: int
    from_x: float
    from_y: float
    to_x: float
    to_y: float
    sequence: int


@dataclass(frozen=True, slots=True)
class Cue:
    id: int
    cue_type: str
    label: str
    trigger: str


@dataclass(frozen=True, slots=True)
class BlockingBeat:
    id: int
    scene_id: int
    label: str
    order: int
    positions: tuple[ActorPosition, ...]
    movements: tuple[Movement, ...]
    cues: tuple[Cue, ...]


@dataclass(frozen=True, slots=True)
class BlockingNotebook:
    stage: Stage
    known_actor_ids: frozenset[int]
    known_scene_ids: frozenset[int]
    beats: tuple[BlockingBeat, ...]


@dataclass(frozen=True, slots=True)
class BlockingIssue:
    code: str
    message: str
    beat_id: int | None = None
    actor_id: int | None = None
    cue_id: int | None = None


@dataclass(frozen=True, slots=True)
class BlockingSummary:
    beat_count: int
    position_count: int
    movement_count: int
    cue_count: int


@dataclass(frozen=True, slots=True)
class BlockingValidationResult:
    valid: bool
    summary: BlockingSummary
    issues: tuple[BlockingIssue, ...]


def validate_blocking_notebook(notebook: BlockingNotebook) -> BlockingValidationResult:
    issues: list[BlockingIssue] = []
    if notebook.stage.width <= 0 or notebook.stage.depth <= 0:
        issues.append(
            BlockingIssue(
                "INVALID_STAGE_DIMENSIONS",
                "STAGE WIDTH AND DEPTH MUST BE POSITIVE",
            )
        )

    duplicate_beat_ids = _duplicates(beat.id for beat in notebook.beats)
    for beat_id in duplicate_beat_ids:
        issues.append(
            BlockingIssue(
                "DUPLICATE_BEAT_ID",
                f"BEAT {beat_id}: ID IS USED MORE THAN ONCE",
                beat_id=beat_id,
            )
        )

    cue_ids = (cue.id for beat in notebook.beats for cue in beat.cues)
    duplicate_cue_ids = _duplicates(cue_ids)
    for cue_id in duplicate_cue_ids:
        issues.append(
            BlockingIssue(
                "DUPLICATE_CUE_ID",
                f"CUE {cue_id}: ID IS USED MORE THAN ONCE",
                cue_id=cue_id,
            )
        )

    for beat in sorted(notebook.beats, key=lambda item: (item.order, item.id)):
        issues.extend(_validate_beat(notebook, beat))

    summary = BlockingSummary(
        beat_count=len(notebook.beats),
        position_count=sum(len(beat.positions) for beat in notebook.beats),
        movement_count=sum(len(beat.movements) for beat in notebook.beats),
        cue_count=sum(len(beat.cues) for beat in notebook.beats),
    )
    return BlockingValidationResult(valid=not issues, summary=summary, issues=tuple(issues))


def _validate_beat(notebook: BlockingNotebook, beat: BlockingBeat) -> list[BlockingIssue]:
    issues: list[BlockingIssue] = []
    if beat.scene_id not in notebook.known_scene_ids:
        issues.append(
            BlockingIssue(
                "UNKNOWN_SCENE",
                f"BEAT {beat.id}: SCENE {beat.scene_id} IS NOT IN THIS PRODUCTION",
                beat_id=beat.id,
            )
        )

    duplicate_actors = _duplicates(position.actor_id for position in beat.positions)
    for actor_id in duplicate_actors:
        issues.append(
            BlockingIssue(
                "DUPLICATE_ACTOR_POSITION",
                f"BEAT {beat.id}: ACTOR {actor_id} HAS MORE THAN ONE STARTING POSITION",
                beat_id=beat.id,
                actor_id=actor_id,
            )
        )

    positions_by_actor: dict[int, ActorPosition] = {}
    for position in beat.positions:
        if position.actor_id not in notebook.known_actor_ids:
            issues.append(
                BlockingIssue(
                    "UNKNOWN_ACTOR",
                    f"BEAT {beat.id}: ACTOR {position.actor_id} IS NOT IN THIS PRODUCTION",
                    beat_id=beat.id,
                    actor_id=position.actor_id,
                )
            )
        if not _inside_stage(position.x, position.y, notebook.stage):
            issues.append(
                BlockingIssue(
                    "POSITION_OUT_OF_BOUNDS",
                    f"BEAT {beat.id}: ACTOR {position.actor_id} POSITION IS OUTSIDE THE STAGE",
                    beat_id=beat.id,
                    actor_id=position.actor_id,
                )
            )
        positions_by_actor.setdefault(position.actor_id, position)

    sequences_by_actor: dict[int, list[int]] = {}
    for movement in beat.movements:
        sequences_by_actor.setdefault(movement.actor_id, []).append(movement.sequence)
    for actor_id, sequences in sorted(sequences_by_actor.items()):
        for sequence in _duplicates(sequences):
            issues.append(
                BlockingIssue(
                    "DUPLICATE_MOVEMENT_SEQUENCE",
                    f"BEAT {beat.id}: ACTOR {actor_id} MOVEMENT {sequence} IS DUPLICATED",
                    beat_id=beat.id,
                    actor_id=actor_id,
                )
            )

    prior_by_actor = {
        actor_id: (position.x, position.y) for actor_id, position in positions_by_actor.items()
    }
    for movement in sorted(beat.movements, key=lambda item: (item.sequence, item.actor_id)):
        issues.extend(_validate_movement(notebook, beat, movement, prior_by_actor))
        prior_by_actor[movement.actor_id] = (movement.to_x, movement.to_y)

    for cue in beat.cues:
        if not cue.label.strip():
            issues.append(
                BlockingIssue(
                    "CUE_LABEL_REQUIRED",
                    f"BEAT {beat.id}: CUE {cue.id} NEEDS A LABEL",
                    beat_id=beat.id,
                    cue_id=cue.id,
                )
            )
        if not cue.trigger.strip():
            issues.append(
                BlockingIssue(
                    "CUE_TRIGGER_REQUIRED",
                    f"BEAT {beat.id}: CUE {cue.id} NEEDS A TRIGGER",
                    beat_id=beat.id,
                    cue_id=cue.id,
                )
            )
    return issues


def _validate_movement(
    notebook: BlockingNotebook,
    beat: BlockingBeat,
    movement: Movement,
    prior_by_actor: dict[int, tuple[float, float]],
) -> list[BlockingIssue]:
    issues: list[BlockingIssue] = []
    if movement.actor_id not in notebook.known_actor_ids:
        issues.append(
            BlockingIssue(
                "UNKNOWN_ACTOR",
                f"BEAT {beat.id}: ACTOR {movement.actor_id} IS NOT IN THIS PRODUCTION",
                beat_id=beat.id,
                actor_id=movement.actor_id,
            )
        )
    if not _inside_stage(movement.from_x, movement.from_y, notebook.stage) or not _inside_stage(
        movement.to_x, movement.to_y, notebook.stage
    ):
        issues.append(
            BlockingIssue(
                "MOVEMENT_OUT_OF_BOUNDS",
                f"BEAT {beat.id}: ACTOR {movement.actor_id} MOVEMENT LEAVES THE STAGE",
                beat_id=beat.id,
                actor_id=movement.actor_id,
            )
        )

    prior = prior_by_actor.get(movement.actor_id)
    if prior is None:
        issues.append(
            BlockingIssue(
                "STARTING_POSITION_REQUIRED",
                f"BEAT {beat.id}: PLACE ACTOR {movement.actor_id} BEFORE RECORDING MOVEMENT",
                beat_id=beat.id,
                actor_id=movement.actor_id,
            )
        )
    elif prior != (movement.from_x, movement.from_y):
        issues.append(
            BlockingIssue(
                "MOVEMENT_ORIGIN_MISMATCH",
                (
                    f"BEAT {beat.id}: ACTOR {movement.actor_id} MOVEMENT "
                    "DOES NOT START AT THE PRIOR POSITION"
                ),
                beat_id=beat.id,
                actor_id=movement.actor_id,
            )
        )
    return issues


def _inside_stage(x: float, y: float, stage: Stage) -> bool:
    return 0 <= x <= stage.width and 0 <= y <= stage.depth


def _duplicates(values: Iterable[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    duplicates: set[int] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))
