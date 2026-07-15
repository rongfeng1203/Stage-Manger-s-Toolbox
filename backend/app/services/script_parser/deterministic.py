import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol


class ParserError(ValueError):
    """Raised when deterministic parsing cannot produce reviewable scene data."""


@dataclass(frozen=True, slots=True)
class ParserWarning:
    code: str
    message: str
    line: int


@dataclass(frozen=True, slots=True)
class ParsedCharacterCandidate:
    name: str
    cue_count: int
    accepted: bool


@dataclass(frozen=True, slots=True)
class ParsedScene:
    scene_code: str
    title: str
    source_header: str
    source_line: int
    characters: tuple[str, ...]
    dialogue_cue_count: int
    stage_direction_count: int


@dataclass(frozen=True, slots=True)
class ParsedScript:
    title: str
    scenes: tuple[ParsedScene, ...]
    character_candidates: tuple[ParsedCharacterCandidate, ...]
    warnings: tuple[ParserWarning, ...]


class ScriptParser(Protocol):
    def parse(self, text: str) -> ParsedScript: ...


@dataclass(slots=True)
class _SceneBuilder:
    scene_code: str
    title: str
    source_header: str
    source_line: int
    cues: list[str]
    stage_direction_count: int = 0


_ACT_ONLY = re.compile(r"^ACT\s+([IVXLCDM]+|\d+)\s*[,.:;-]?$", re.IGNORECASE)
_ACT_SCENE = re.compile(
    r"^ACT\s+([IVXLCDM]+|\d+)\s*[,.:;-]?\s*SCENE\s+([IVXLCDM]+|\d+)"
    r"(?:\s*[:.\-]\s*(.*))?$",
    re.IGNORECASE,
)
_SCENE_ONLY = re.compile(
    r"^SCENE\s+([IVXLCDM]+|\d+)(?:\s*[:.\-]\s*(.*))?$",
    re.IGNORECASE,
)
_CUE_NAME = r"[A-Za-z][A-Za-z'\-]*(?:\s+(?:[A-Za-z][A-Za-z'\-]*|\d+)){0,3}"
_INLINE_CUE = re.compile(rf"^({_CUE_NAME})\s*:\s*(.*)$")
_CUE_WORDS = re.compile(rf"^{_CUE_NAME}[.:]?$")
_SCREENPLAY_TRANSITION = re.compile(
    r"^\((?:CUT TO|CUT BACK|DISSOLVE|FADE|CAMERA (?:CUTS|PANS|TILTS))\b",
    re.IGNORECASE,
)
_CONTROL_WORDS = {
    "ACT",
    "BLACKOUT",
    "CURTAIN",
    "END",
    "ENTER",
    "EXIT",
    "EXEUNT",
    "INTERMISSION",
    "LIGHTS",
    "SCENE",
    "SOUND",
}


class DeterministicScriptParser:
    def parse(self, text: str) -> ParsedScript:
        if not text.strip():
            raise ParserError("script text must not be empty")

        lines = text.splitlines()
        title = _detect_title(lines)
        if not any(_is_header(line.strip()) for line in lines if line.strip()):
            return _parse_inferred_scenes(lines, title)

        builders: list[_SceneBuilder] = []
        by_code: dict[str, _SceneBuilder] = {}
        warnings: list[ParserWarning] = []
        current: _SceneBuilder | None = None
        current_act = 1

        for index, raw_line in enumerate(lines):
            line_number = index + 1
            stripped = raw_line.strip()
            if not stripped:
                continue

            combined = _ACT_SCENE.fullmatch(stripped)
            if combined:
                current_act = _ordinal(combined.group(1))
                current = _start_scene(
                    builders,
                    by_code,
                    warnings,
                    current_act,
                    _ordinal(combined.group(2)),
                    (combined.group(3) or "").strip(),
                    stripped,
                    line_number,
                )
                continue

            act = _ACT_ONLY.fullmatch(stripped)
            if act:
                current_act = _ordinal(act.group(1))
                continue

            scene = _SCENE_ONLY.fullmatch(stripped)
            if scene:
                current = _start_scene(
                    builders,
                    by_code,
                    warnings,
                    current_act,
                    _ordinal(scene.group(1)),
                    (scene.group(2) or "").strip(),
                    stripped,
                    line_number,
                )
                continue

            if current is None:
                continue
            if _is_stage_direction(stripped):
                current.stage_direction_count += 1
                continue
            cue = _extract_character_cue(lines, index)
            if cue is not None:
                current.cues.append(cue)

        return _finish_script(title, builders, warnings)


def _parse_inferred_scenes(lines: list[str], title: str) -> ParsedScript:
    title_index = _first_content_index(lines)
    first_line = title_index + 1
    builders = [_SceneBuilder("A1S1", "Opening", "INFERRED OPENING", first_line, [])]
    warnings = [
        ParserWarning(
            "INFERRED_SCENES",
            "no authored scene headers found; boundaries were inferred from screenplay transitions",
            first_line,
        )
    ]
    current = builders[0]

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or index == title_index:
            continue
        if _SCREENPLAY_TRANSITION.match(stripped) and current.cues:
            scene_number = len(builders) + 1
            current = _SceneBuilder(
                f"A1S{scene_number}",
                _inferred_scene_title(stripped),
                stripped,
                index + 1,
                [],
                1,
            )
            builders.append(current)
            continue
        if _is_stage_direction(stripped):
            current.stage_direction_count += 1
            continue
        cue = _extract_inferred_character_cue(lines, index)
        if cue is not None:
            current.cues.append(cue)

    return _finish_script(title, builders, warnings)


def _finish_script(
    title: str, builders: list[_SceneBuilder], warnings: list[ParserWarning]
) -> ParsedScript:
    if not builders:
        raise ParserError("no scene structure detected")
    all_cues = Counter(cue for builder in builders for cue in builder.cues)
    scenes: list[ParsedScene] = []
    for builder in builders:
        characters = tuple(sorted(set(builder.cues)))
        if not builder.cues:
            warnings.append(
                ParserWarning(
                    "EMPTY_SCENE",
                    f"{builder.scene_code} contains no detected character cues",
                    builder.source_line,
                )
            )
        scenes.append(
            ParsedScene(
                scene_code=builder.scene_code,
                title=builder.title,
                source_header=builder.source_header,
                source_line=builder.source_line,
                characters=characters,
                dialogue_cue_count=len(builder.cues),
                stage_direction_count=builder.stage_direction_count,
            )
        )

    candidates = tuple(
        ParsedCharacterCandidate(name, count, True)
        for name, count in sorted(all_cues.items(), key=lambda item: (-item[1], item[0]))
    )
    return ParsedScript(
        title,
        tuple(scenes),
        candidates,
        tuple(sorted(warnings, key=lambda item: (item.line, item.code))),
    )


def _start_scene(
    builders: list[_SceneBuilder],
    by_code: dict[str, _SceneBuilder],
    warnings: list[ParserWarning],
    act: int,
    scene: int,
    title: str,
    source_header: str,
    source_line: int,
) -> _SceneBuilder:
    scene_code = f"A{act}S{scene}"
    if scene_code in by_code:
        warnings.append(
            ParserWarning(
                "REPEATED_SCENE_HEADER",
                f"repeated {scene_code} header was merged into its first occurrence",
                source_line,
            )
        )
        return by_code[scene_code]
    builder = _SceneBuilder(scene_code, title, source_header, source_line, [])
    builders.append(builder)
    by_code[scene_code] = builder
    return builder


def _detect_title(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if (
            _ACT_ONLY.fullmatch(stripped)
            or _ACT_SCENE.fullmatch(stripped)
            or _SCENE_ONLY.fullmatch(stripped)
        ):
            return "UNTITLED SCRIPT"
        return stripped
    return "UNTITLED SCRIPT"


def _extract_character_cue(lines: list[str], index: int) -> str | None:
    stripped = lines[index].strip()
    inline = _INLINE_CUE.fullmatch(stripped)
    if inline and inline.group(2).strip():
        candidate = inline.group(1)
    else:
        if not _CUE_WORDS.fullmatch(stripped):
            return None
        candidate = stripped.rstrip(".:")
        next_line = _next_content_line(lines, index + 1)
        if next_line is None or _is_header(next_line) or _looks_like_cue(next_line):
            return None

    normalized = _normalize_character_name(candidate)
    if any(word.upper() in _CONTROL_WORDS for word in normalized.split()):
        return None
    return normalized


def _extract_inline_character_cue(line: str) -> str | None:
    inline = _INLINE_CUE.fullmatch(line)
    if inline is None:
        return None
    normalized = _normalize_character_name(inline.group(1))
    if any(word.upper() in _CONTROL_WORDS for word in normalized.split()):
        return None
    return normalized


def _extract_inferred_character_cue(lines: list[str], index: int) -> str | None:
    line = lines[index].strip()
    inline = _extract_inline_character_cue(line)
    if inline is not None:
        return inline
    if line.upper() == line:
        return _extract_character_cue(lines, index)
    return None


def _next_content_line(lines: list[str], start: int) -> str | None:
    for line in lines[start:]:
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _looks_like_cue(line: str) -> bool:
    inline = _INLINE_CUE.fullmatch(line)
    if inline:
        return True
    return bool(_CUE_WORDS.fullmatch(line) and line.upper() == line)


def _is_header(line: str) -> bool:
    return bool(
        _ACT_ONLY.fullmatch(line) or _ACT_SCENE.fullmatch(line) or _SCENE_ONLY.fullmatch(line)
    )


def _is_stage_direction(line: str) -> bool:
    return line.startswith("[") or line.startswith("(")


def _first_content_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if line.strip():
            return index
    raise ParserError("script text must not be empty")


def _inferred_scene_title(transition: str) -> str:
    compact = " ".join(transition.strip().strip("()").split())
    return compact[:80]


def _normalize_character_name(value: str) -> str:
    return " ".join(word.capitalize() for word in value.strip().rstrip(".:").split())


def _ordinal(value: str) -> int:
    if value.isdigit():
        number = int(value)
    else:
        number = _roman_to_int(value.upper())
    if number <= 0:
        raise ParserError(f"scene and act numbers must be positive: {value}")
    return number


def _roman_to_int(value: str) -> int:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for character in reversed(value):
        current = values.get(character)
        if current is None:
            raise ParserError(f"invalid Roman numeral: {value}")
        total += -current if current < previous else current
        previous = max(previous, current)
    return total
