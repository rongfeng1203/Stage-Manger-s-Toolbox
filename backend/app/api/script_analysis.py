from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from backend.app.services.script_parser import (
    DeterministicScriptParser,
    ParserError,
    extract_script_text,
)

router = APIRouter(prefix="/api/scripts", tags=["scripts"])
MAX_SCRIPT_BYTES = 10 * 1024 * 1024


class AnalyzeScriptPayload(BaseModel):
    text: str = Field(min_length=1)


@router.post("/analyze")
def analyze_script(payload: AnalyzeScriptPayload) -> dict[str, object]:
    return _analyze_text(payload.text)


@router.post("/upload")
async def upload_script(file: Annotated[UploadFile, File()]) -> dict[str, object]:
    filename = file.filename or "uploaded-script"
    content = await file.read(MAX_SCRIPT_BYTES + 1)
    if len(content) > MAX_SCRIPT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="script file exceeds the 10 MB upload limit",
        )
    try:
        text = extract_script_text(filename, content)
    except ParserError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    analysis = _analyze_text(text)
    return {
        **analysis,
        "fileName": filename,
        "fileType": file.content_type or "application/octet-stream",
        "extractedCharacterCount": len(text),
    }


def _analyze_text(text: str) -> dict[str, object]:
    try:
        result = DeterministicScriptParser().parse(text)
    except ParserError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "title": result.title,
        "scenes": [
            {
                "sceneCode": scene.scene_code,
                "title": scene.title,
                "sourceHeader": scene.source_header,
                "sourceLine": scene.source_line,
                "characters": list(scene.characters),
                "dialogueCueCount": scene.dialogue_cue_count,
                "stageDirectionCount": scene.stage_direction_count,
            }
            for scene in result.scenes
        ],
        "characterCandidates": [
            {"name": item.name, "cueCount": item.cue_count, "accepted": item.accepted}
            for item in result.character_candidates
        ],
        "warnings": [
            {"code": item.code, "message": item.message, "line": item.line}
            for item in result.warnings
        ],
    }
