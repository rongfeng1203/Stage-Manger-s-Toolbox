import pytest

from backend.app.services.cast.requirements import (
    CastAssignmentInput,
    CastRequirementError,
    CharacterInput,
    DuplicateCastAssignmentPolicy,
    RequirementResolution,
    RequirementWarning,
    RequirementWarningType,
    SceneCharacterInput,
    _require_positive,
    get_required_actors,
    normalize_cast_assignments,
)


def character(character_id: int, name: str = "Hamlet") -> CharacterInput:
    return CharacterInput(id=character_id, production_id=1, name=name)


def scene_character(
    scene_id: int, character_id: int, *, required: bool = True
) -> SceneCharacterInput:
    return SceneCharacterInput(scene_id=scene_id, character_id=character_id, required=required)


def assignment(character_id: int, actor_id: int) -> CastAssignmentInput:
    return CastAssignmentInput(character_id=character_id, actor_id=actor_id)


def test_get_required_actors_resolves_one_character() -> None:
    result = get_required_actors(
        scene_id=10,
        characters=[character(1)],
        cast_assignments=[assignment(1, 100)],
        scene_characters=[scene_character(10, 1)],
    )

    assert result.actor_ids == frozenset({100})
    assert result.warnings == ()


def test_get_required_actors_resolves_multiple_characters() -> None:
    result = get_required_actors(
        scene_id=10,
        characters=[character(1), character(2, "Ophelia")],
        cast_assignments=[assignment(1, 100), assignment(2, 200)],
        scene_characters=[scene_character(10, 1), scene_character(10, 2)],
    )

    assert result.actor_ids == frozenset({100, 200})


def test_get_required_actors_collapses_actor_doubling() -> None:
    result = get_required_actors(
        scene_id=10,
        characters=[character(1), character(2, "Ghost")],
        cast_assignments=[assignment(1, 100), assignment(2, 100)],
        scene_characters=[scene_character(10, 1), scene_character(10, 2)],
    )

    assert result.actor_ids == frozenset({100})


def test_get_required_actors_ignores_optional_character_for_required_call() -> None:
    result = get_required_actors(
        scene_id=10,
        characters=[character(1), character(2, "Ensemble")],
        cast_assignments=[assignment(1, 100), assignment(2, 200)],
        scene_characters=[scene_character(10, 1), scene_character(10, 2, required=False)],
    )

    assert result.actor_ids == frozenset({100})


def test_get_required_actors_only_uses_requested_scene() -> None:
    result = get_required_actors(
        scene_id=10,
        characters=[character(1), character(2, "Polonius")],
        cast_assignments=[assignment(1, 100), assignment(2, 200)],
        scene_characters=[scene_character(10, 1), scene_character(11, 2)],
    )

    assert result.actor_ids == frozenset({100})


def test_get_required_actors_warns_for_missing_cast_assignment() -> None:
    result = get_required_actors(
        scene_id=10,
        characters=[character(1)],
        cast_assignments=[],
        scene_characters=[scene_character(10, 1)],
    )

    assert result.actor_ids == frozenset()
    assert len(result.warnings) == 1
    assert result.warnings[0].warning_type == RequirementWarningType.MISSING_CAST_ASSIGNMENT
    assert result.warnings[0].character_id == 1


def test_get_required_actors_warns_for_unknown_scene_character() -> None:
    result = get_required_actors(
        scene_id=10,
        characters=[],
        cast_assignments=[],
        scene_characters=[scene_character(10, 999)],
    )

    assert result.actor_ids == frozenset()
    assert len(result.warnings) == 1
    assert result.warnings[0].warning_type == RequirementWarningType.UNKNOWN_CHARACTER
    assert result.warnings[0].character_id == 999


def test_normalize_cast_assignments_keeps_identical_duplicate_once() -> None:
    normalized = normalize_cast_assignments(
        [assignment(1, 100), assignment(1, 100)],
        duplicate_policy=DuplicateCastAssignmentPolicy.REJECT_CONFLICTS,
    )

    assert normalized == {1: 100}


def test_normalize_cast_assignments_rejects_conflicting_duplicate_by_default() -> None:
    with pytest.raises(CastRequirementError, match="duplicate cast assignment"):
        normalize_cast_assignments(
            [assignment(1, 100), assignment(1, 200)],
            duplicate_policy=DuplicateCastAssignmentPolicy.REJECT_CONFLICTS,
        )


def test_normalize_cast_assignments_can_keep_first_duplicate_consistently() -> None:
    normalized = normalize_cast_assignments(
        [assignment(1, 100), assignment(1, 200)],
        duplicate_policy=DuplicateCastAssignmentPolicy.KEEP_FIRST,
    )

    assert normalized == {1: 100}


def test_get_required_actors_uses_duplicate_policy() -> None:
    result = get_required_actors(
        scene_id=10,
        characters=[character(1)],
        cast_assignments=[assignment(1, 100), assignment(1, 200)],
        scene_characters=[scene_character(10, 1)],
        duplicate_policy=DuplicateCastAssignmentPolicy.KEEP_FIRST,
    )

    assert result.actor_ids == frozenset({100})


def test_inputs_reject_non_positive_identifiers() -> None:
    with pytest.raises(CastRequirementError, match="positive"):
        CastAssignmentInput(character_id=0, actor_id=1)


def test_character_input_rejects_empty_name() -> None:
    with pytest.raises(CastRequirementError, match="name"):
        CharacterInput(id=1, production_id=1, name="")


def test_warning_rejects_empty_message() -> None:
    with pytest.raises(CastRequirementError, match="message"):
        RequirementWarning(
            warning_type=RequirementWarningType.UNKNOWN_CHARACTER,
            scene_id=10,
            character_id=1,
            message="",
        )


def test_resolution_rejects_non_positive_actor_id() -> None:
    with pytest.raises(CastRequirementError, match="actor_id"):
        RequirementResolution(scene_id=10, actor_ids=frozenset({0}))


def test_require_positive_accepts_positive_value() -> None:
    assert _require_positive("actor_id", 1) is None


def test_require_positive_rejects_zero_value() -> None:
    with pytest.raises(CastRequirementError, match="actor_id"):
        _require_positive("actor_id", 0)
