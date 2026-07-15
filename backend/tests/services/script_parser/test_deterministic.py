import json
from pathlib import Path

import pytest

from backend.app.services.script_parser.deterministic import (
    DeterministicScriptParser,
    ParserError,
    _detect_title,
    _extract_character_cue,
    _extract_inferred_character_cue,
    _extract_inline_character_cue,
    _finish_script,
    _first_content_index,
    _inferred_scene_title,
    _is_header,
    _is_stage_direction,
    _looks_like_cue,
    _next_content_line,
    _normalize_character_name,
    _ordinal,
    _roman_to_int,
)

FIXTURES = Path(__file__).parent / "fixtures"


def summarized(name: str) -> dict[str, object]:
    result = DeterministicScriptParser().parse((FIXTURES / f"{name}.txt").read_text())
    return {
        "title": result.title,
        "scenes": [
            {
                "scene_code": scene.scene_code,
                "title": scene.title,
                "characters": list(scene.characters),
                "dialogue_cue_count": scene.dialogue_cue_count,
                "stage_direction_count": scene.stage_direction_count,
            }
            for scene in result.scenes
        ],
        "character_candidates": [
            {"name": item.name, "cue_count": item.cue_count, "accepted": item.accepted}
            for item in result.character_candidates
        ],
        "warnings": (
            [item.code for item in result.warnings] if name == "fixture_edge_cases" else []
        ),
    }


@pytest.mark.parametrize("name", ["fixture_hamlet_sample", "fixture_edge_cases"])
def test_golden_script_parse(name: str) -> None:
    expected = json.loads((FIXTURES / f"{name}.expected.json").read_text())
    assert summarized(name) == expected


def test_invalid_script_is_rejected() -> None:
    text = (FIXTURES / "fixture_invalid.txt").read_text()
    result = DeterministicScriptParser().parse(text)
    assert result.scenes[0].scene_code == "A1S1"
    assert result.warnings[0].code == "INFERRED_SCENES"


def test_empty_script_is_rejected() -> None:
    with pytest.raises(ParserError, match="must not be empty"):
        DeterministicScriptParser().parse("  \n")


def test_parser_helpers_cover_normalization_and_detection() -> None:
    lines = ["Hamlet", "Speak the speech."]
    assert _detect_title(["", "HAMLET", "ACT I"]) == "HAMLET"
    assert _extract_character_cue(lines, 0) == "Hamlet"
    assert _next_content_line(["", "  ", "text"], 0) == "text"
    assert _looks_like_cue("HAMLET")
    assert _is_header("SCENE 2")
    assert _is_stage_direction("[Exit.]")
    assert _normalize_character_name("KING CLAUDIUS.") == "King Claudius"
    assert _ordinal("IV") == 4
    assert _roman_to_int("IX") == 9


def test_headerless_screenplay_infers_scenes_and_numbered_character_cues() -> None:
    result = DeterministicScriptParser().parse(
        "ALADDIN: THE COMPLETE SCRIPT\n\nPEDDLER: Welcome.\n\n"
        "(Cut to a rooftop.)\n\nGUARD 1: Stop!\nALADDIN: Run!"
    )
    assert [scene.scene_code for scene in result.scenes] == ["A1S1", "A1S2"]
    assert result.scenes[0].characters == ("Peddler",)
    assert result.scenes[1].characters == ("Aladdin", "Guard 1")
    assert result.warnings[0].code == "INFERRED_SCENES"


def test_inferred_scene_helpers_are_directly_covered() -> None:
    assert _first_content_index(["", "Title"]) == 1
    assert _inferred_scene_title("(Cut   to a rooftop.)") == "Cut to a rooftop."
    assert _extract_inline_character_cue("GUARD 1: Stop!") == "Guard 1"
    assert _extract_inline_character_cue("A lyric without a cue") is None
    assert _extract_inferred_character_cue(["HAMLET", "To be."], 0) == "Hamlet"
    with pytest.raises(ParserError, match="no scene structure"):
        _finish_script("Title", [], [])
