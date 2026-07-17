from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.services.blocking.notebook import (
    ActorPosition,
    BlockingBeat,
    BlockingIssue,
    BlockingNotebook,
    Cue,
    Movement,
    Stage,
    validate_blocking_notebook,
)

router = APIRouter(prefix="/api/blocking", tags=["blocking"])


class StagePayload(BaseModel):
    width: float
    depth: float


class PositionPayload(BaseModel):
    actor_id: int = Field(gt=0)
    x: float
    y: float


class MovementPayload(BaseModel):
    actor_id: int = Field(gt=0)
    from_x: float
    from_y: float
    to_x: float
    to_y: float
    sequence: int = Field(gt=0)


class CuePayload(BaseModel):
    id: int = Field(gt=0)
    cue_type: str = Field(min_length=1)
    label: str
    trigger: str


class BlockingBeatPayload(BaseModel):
    id: int = Field(gt=0)
    scene_id: int = Field(gt=0)
    label: str
    order: int = Field(gt=0)
    positions: list[PositionPayload]
    movements: list[MovementPayload]
    cues: list[CuePayload]


class ValidateBlockingPayload(BaseModel):
    stage: StagePayload
    known_actor_ids: list[int]
    known_scene_ids: list[int]
    beats: list[BlockingBeatPayload]


@router.post("/validate")
def validate_blocking_route(payload: ValidateBlockingPayload) -> dict[str, object]:
    result = validate_blocking_notebook(
        BlockingNotebook(
            stage=Stage(payload.stage.width, payload.stage.depth),
            known_actor_ids=frozenset(payload.known_actor_ids),
            known_scene_ids=frozenset(payload.known_scene_ids),
            beats=tuple(
                BlockingBeat(
                    id=beat.id,
                    scene_id=beat.scene_id,
                    label=beat.label,
                    order=beat.order,
                    positions=tuple(
                        ActorPosition(item.actor_id, item.x, item.y) for item in beat.positions
                    ),
                    movements=tuple(
                        Movement(
                            actor_id=item.actor_id,
                            from_x=item.from_x,
                            from_y=item.from_y,
                            to_x=item.to_x,
                            to_y=item.to_y,
                            sequence=item.sequence,
                        )
                        for item in beat.movements
                    ),
                    cues=tuple(
                        Cue(item.id, item.cue_type, item.label, item.trigger)
                        for item in beat.cues
                    ),
                )
                for beat in payload.beats
            ),
        )
    )
    return {
        "valid": result.valid,
        "summary": {
            "beatCount": result.summary.beat_count,
            "positionCount": result.summary.position_count,
            "movementCount": result.summary.movement_count,
            "cueCount": result.summary.cue_count,
        },
        "issues": [_serialize_issue(issue) for issue in result.issues],
    }


def _serialize_issue(issue: BlockingIssue) -> dict[str, object]:
    serialized: dict[str, object] = {"code": issue.code, "message": issue.message}
    if issue.beat_id is not None:
        serialized["beatId"] = issue.beat_id
    if issue.actor_id is not None:
        serialized["actorId"] = issue.actor_id
    if issue.cue_id is not None:
        serialized["cueId"] = issue.cue_id
    return serialized
