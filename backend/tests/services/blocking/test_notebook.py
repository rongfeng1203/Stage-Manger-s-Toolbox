from backend.app.services.blocking.notebook import (
    ActorPosition,
    BlockingBeat,
    BlockingNotebook,
    Cue,
    Movement,
    Stage,
    validate_blocking_notebook,
)


def notebook(*beats: BlockingBeat, stage: Stage | None = None) -> BlockingNotebook:
    return BlockingNotebook(
        stage=stage or Stage(100, 100),
        known_actor_ids=frozenset({1, 2}),
        known_scene_ids=frozenset({10}),
        beats=beats,
    )


def beat(
    *,
    beat_id: int = 1,
    scene_id: int = 10,
    positions: tuple[ActorPosition, ...] = (ActorPosition(1, 20, 40),),
    movements: tuple[Movement, ...] = (Movement(1, 20, 40, 60, 70, 1),),
    cues: tuple[Cue, ...] = (Cue(1, "LIGHT", "LX 1", "WHEN THE DOOR CLOSES"),),
) -> BlockingBeat:
    return BlockingBeat(
        id=beat_id,
        scene_id=scene_id,
        label="ENTRANCE",
        order=beat_id,
        positions=positions,
        movements=movements,
        cues=cues,
    )


def test_valid_notebook_returns_counts() -> None:
    result = validate_blocking_notebook(notebook(beat()))
    assert result.valid
    assert result.issues == ()
    assert result.summary.beat_count == 1
    assert result.summary.position_count == 1
    assert result.summary.movement_count == 1
    assert result.summary.cue_count == 1


def test_reports_unknown_references_and_out_of_bounds_coordinates() -> None:
    result = validate_blocking_notebook(
        notebook(
            beat(
                scene_id=99,
                positions=(ActorPosition(9, 120, 40),),
                movements=(Movement(9, 120, 40, 20, -1, 1),),
            )
        )
    )
    assert [issue.code for issue in result.issues] == [
        "UNKNOWN_SCENE",
        "UNKNOWN_ACTOR",
        "POSITION_OUT_OF_BOUNDS",
        "UNKNOWN_ACTOR",
        "MOVEMENT_OUT_OF_BOUNDS",
    ]


def test_reports_duplicate_ids_positions_and_sequences() -> None:
    first = beat(
        positions=(ActorPosition(1, 20, 40), ActorPosition(1, 30, 50)),
        movements=(Movement(1, 20, 40, 60, 70, 1), Movement(1, 60, 70, 80, 80, 1)),
    )
    second = beat(beat_id=1, cues=(Cue(1, "SOUND", "SFX 1", "GO"),))
    result = validate_blocking_notebook(notebook(first, second))
    codes = [issue.code for issue in result.issues]
    assert codes[:2] == ["DUPLICATE_BEAT_ID", "DUPLICATE_CUE_ID"]
    assert "DUPLICATE_ACTOR_POSITION" in codes
    assert "DUPLICATE_MOVEMENT_SEQUENCE" in codes


def test_reports_movement_without_start_and_mismatched_origin() -> None:
    no_start = beat(
        beat_id=1,
        positions=(),
        movements=(Movement(1, 20, 40, 60, 70, 1),),
    )
    mismatch = beat(
        beat_id=2,
        movements=(Movement(1, 30, 40, 60, 70, 1),),
        cues=(Cue(2, "LIGHT", "LX 2", "GO"),),
    )
    result = validate_blocking_notebook(notebook(no_start, mismatch))
    assert "STARTING_POSITION_REQUIRED" in [issue.code for issue in result.issues]
    assert "MOVEMENT_ORIGIN_MISMATCH" in [issue.code for issue in result.issues]


def test_reports_invalid_stage_and_incomplete_cues() -> None:
    result = validate_blocking_notebook(
        notebook(
            beat(cues=(Cue(1, "LIGHT", " ", ""),)),
            stage=Stage(0, -1),
        )
    )
    assert [issue.code for issue in result.issues] == [
        "INVALID_STAGE_DIMENSIONS",
        "POSITION_OUT_OF_BOUNDS",
        "MOVEMENT_OUT_OF_BOUNDS",
        "CUE_LABEL_REQUIRED",
        "CUE_TRIGGER_REQUIRED",
    ]
