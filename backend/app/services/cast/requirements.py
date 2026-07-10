from dataclasses import dataclass
from enum import StrEnum


class CastRequirementError(ValueError):
    """Raised when cast requirement inputs are structurally invalid."""


class DuplicateCastAssignmentPolicy(StrEnum):
    REJECT_CONFLICTS = "REJECT_CONFLICTS"
    KEEP_FIRST = "KEEP_FIRST"


class RequirementWarningType(StrEnum):
    MISSING_CAST_ASSIGNMENT = "MISSING_CAST_ASSIGNMENT"
    UNKNOWN_CHARACTER = "UNKNOWN_CHARACTER"


@dataclass(frozen=True, slots=True)
class CharacterInput:
    id: int
    production_id: int
    name: str

    def __post_init__(self) -> None:
        _require_positive("character_id", self.id)
        _require_positive("production_id", self.production_id)
        if not self.name:
            raise CastRequirementError("character name must not be empty")


@dataclass(frozen=True, slots=True)
class CastAssignmentInput:
    character_id: int
    actor_id: int

    def __post_init__(self) -> None:
        _require_positive("character_id", self.character_id)
        _require_positive("actor_id", self.actor_id)


@dataclass(frozen=True, slots=True)
class SceneCharacterInput:
    scene_id: int
    character_id: int
    required: bool = True

    def __post_init__(self) -> None:
        _require_positive("scene_id", self.scene_id)
        _require_positive("character_id", self.character_id)


@dataclass(frozen=True, slots=True)
class RequirementWarning:
    warning_type: RequirementWarningType
    scene_id: int
    character_id: int
    message: str

    def __post_init__(self) -> None:
        _require_positive("scene_id", self.scene_id)
        _require_positive("character_id", self.character_id)
        if not self.message:
            raise CastRequirementError("warning message must not be empty")


@dataclass(frozen=True, slots=True)
class RequirementResolution:
    scene_id: int
    actor_ids: frozenset[int]
    warnings: tuple[RequirementWarning, ...] = ()

    def __post_init__(self) -> None:
        _require_positive("scene_id", self.scene_id)
        for actor_id in self.actor_ids:
            _require_positive("actor_id", actor_id)


def normalize_cast_assignments(
    cast_assignments: list[CastAssignmentInput],
    *,
    duplicate_policy: DuplicateCastAssignmentPolicy = (
        DuplicateCastAssignmentPolicy.REJECT_CONFLICTS
    ),
) -> dict[int, int]:
    assignments_by_character: dict[int, int] = {}

    for cast_assignment in cast_assignments:
        existing_actor_id = assignments_by_character.get(cast_assignment.character_id)
        if existing_actor_id is None:
            assignments_by_character[cast_assignment.character_id] = cast_assignment.actor_id
            continue
        if existing_actor_id == cast_assignment.actor_id:
            continue
        if duplicate_policy == DuplicateCastAssignmentPolicy.KEEP_FIRST:
            continue
        raise CastRequirementError(
            "duplicate cast assignment for character "
            f"{cast_assignment.character_id}: actors {existing_actor_id} and "
            f"{cast_assignment.actor_id}"
        )

    return assignments_by_character


def get_required_actors(
    *,
    scene_id: int,
    characters: list[CharacterInput],
    cast_assignments: list[CastAssignmentInput],
    scene_characters: list[SceneCharacterInput],
    duplicate_policy: DuplicateCastAssignmentPolicy = (
        DuplicateCastAssignmentPolicy.REJECT_CONFLICTS
    ),
) -> RequirementResolution:
    _require_positive("scene_id", scene_id)
    characters_by_id = {character.id: character for character in characters}
    assignments_by_character = normalize_cast_assignments(
        cast_assignments,
        duplicate_policy=duplicate_policy,
    )
    actor_ids: set[int] = set()
    warnings: list[RequirementWarning] = []

    for scene_character in scene_characters:
        if scene_character.scene_id != scene_id or not scene_character.required:
            continue
        if scene_character.character_id not in characters_by_id:
            warnings.append(
                RequirementWarning(
                    warning_type=RequirementWarningType.UNKNOWN_CHARACTER,
                    scene_id=scene_id,
                    character_id=scene_character.character_id,
                    message=f"character {scene_character.character_id} is not defined",
                )
            )
            continue
        actor_id = assignments_by_character.get(scene_character.character_id)
        if actor_id is None:
            warnings.append(
                RequirementWarning(
                    warning_type=RequirementWarningType.MISSING_CAST_ASSIGNMENT,
                    scene_id=scene_id,
                    character_id=scene_character.character_id,
                    message=f"character {scene_character.character_id} has no actor assignment",
                )
            )
            continue
        actor_ids.add(actor_id)

    return RequirementResolution(
        scene_id=scene_id,
        actor_ids=frozenset(actor_ids),
        warnings=tuple(warnings),
    )


def _require_positive(label: str, value: int) -> None:
    if value <= 0:
        raise CastRequirementError(f"{label} must be positive")
