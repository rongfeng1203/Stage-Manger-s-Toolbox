"""Validated, atomic schedule imports; no actor is guessed from a partial name."""

import csv
import io
import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Annotated
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from openpyxl import load_workbook  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

router = APIRouter(prefix="/api/availability", tags=["availability"])


class ImportActor(BaseModel):
    id: int = Field(gt=0)
    name: str
    email: str = ""


def _datetime(value: object, day: object, timezone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, time):
        parsed_day = day.date() if isinstance(day, datetime) else date.fromisoformat(str(day))
        result = datetime.combine(parsed_day, value)
    else:
        text = str(value or "").strip()
        if day and "T" not in text and " " not in text:
            parsed_day = day.date() if isinstance(day, datetime) else date.fromisoformat(str(day))
            result = datetime.combine(parsed_day, time.fromisoformat(text))
        else:
            result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone)
        # Reject nonexistent or ambiguous wall times instead of silently guessing.
        if (
            result.astimezone(UTC).astimezone(timezone).replace(tzinfo=None)
            != result.replace(tzinfo=None)
            or result.replace(fold=0).utcoffset() != result.replace(fold=1).utcoffset()
        ):
            raise ValueError("Nonexistent or ambiguous DST local time is not supported")
    local = result.astimezone(timezone)
    if local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset():
        raise ValueError("Ambiguous DST local times are not supported by the schedule editor")
    if local.second or local.microsecond:
        raise ValueError("Use whole-minute times")
    return local


@router.post("/import")
async def import_spreadsheet(
    file: Annotated[UploadFile, File()],
    actors: Annotated[str, Form()],
    timezone: Annotated[str, Form()] = "America/Toronto",
) -> dict[str, object]:
    try:
        cast = TypeAdapter(list[ImportActor]).validate_json(actors)
        zone = ZoneInfo(timezone)
    except (ValidationError, ZoneInfoNotFoundError, ValueError) as error:
        raise HTTPException(422, "Provide a valid cast and timezone") from error
    if not cast or len({actor.id for actor in cast}) != len(cast):
        raise HTTPException(422, "Add actors with unique IDs before importing")
    raw = await file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "Schedule files must be at most 5 MB")
    suffix = Path(file.filename or "").suffix.lower()
    tables: list[tuple[str, list[tuple[object, ...]]]] = []
    try:
        if suffix == ".csv":
            tables = [
                ("CSV", [tuple(row) for row in csv.reader(io.StringIO(raw.decode("utf-8-sig")))])
            ]
        elif suffix == ".xlsx":
            with ZipFile(io.BytesIO(raw)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 25 * 1024 * 1024:
                    raise ValueError("Expanded workbook exceeds 25 MB")
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
            try:
                for sheet in workbook:
                    rows = []
                    for row in sheet.iter_rows(values_only=True):
                        rows.append(tuple(row))
                        if len(rows) > 10001:
                            raise ValueError("Each sheet supports at most 10,000 schedule rows")
                    tables.append((sheet.title, rows))
            finally:
                workbook.close()
        else:
            raise ValueError("Upload an .xlsx or UTF-8 .csv file; save older .xls files as .xlsx")
    except (
        ValueError,
        OSError,
        BadZipFile,
        KeyError,
        ParseError,
        DefusedXmlException,
        csv.Error,
    ) as error:
        raise HTTPException(422, f"Cannot read schedule: {error}") from error

    windows: list[dict[str, object]] = []
    errors: list[str] = []
    for sheet_name, rows in tables:
        nonempty = [
            (index, row)
            for index, row in enumerate(rows, 1)
            if any(v is not None and v != "" for v in row)
        ]
        if not nonempty:
            continue
        headers = [str(v or "").strip().lower().replace(" ", "_") for v in nonempty[0][1]]
        if not {"start", "end"}.issubset(headers) or not {
            "actor",
            "email",
            "actor_id",
        }.intersection(headers):
            errors.append(f"{sheet_name}: requires actor (or email / actor_id), start, end columns")
            continue
        if len(set(headers)) != len(headers):
            errors.append(f"{sheet_name}: duplicate column headers")
            continue
        for row_number, row in nonempty[1:]:
            try:
                values = dict(zip(headers, row, strict=False))
                matches = cast[:]
                identifiers = 0
                for column, attribute in (
                    ("actor_id", "id"),
                    ("email", "email"),
                    ("actor", "name"),
                ):
                    value = str(values.get(column) or "").strip().casefold()
                    if value:
                        identifiers += 1
                        matches = [
                            a
                            for a in matches
                            if str(getattr(a, attribute)).strip().casefold() == value
                        ]
                if not identifiers or len(matches) != 1:
                    raise ValueError("actor is unknown, ambiguous, or has conflicting identifiers")
                kind = str(values.get("type") or "AVAILABLE").strip().upper()
                if kind not in {"AVAILABLE", "BUSY", "PREFERRED"}:
                    raise ValueError("type must be AVAILABLE, BUSY, or PREFERRED")
                start = _datetime(values.get("start"), values.get("date"), zone)
                end = _datetime(values.get("end"), values.get("date"), zone)
                if start.astimezone(UTC) >= end.astimezone(UTC):
                    raise ValueError("start must precede end")
                windows.append(
                    {
                        "actorId": matches[0].id,
                        "start": start.strftime("%Y-%m-%dT%H:%M"),
                        "end": end.strftime("%Y-%m-%dT%H:%M"),
                        "availabilityType": kind,
                    }
                )
            except (ValueError, TypeError) as error:
                errors.append(f"{sheet_name} row {row_number}: {error}")
    if errors:
        raise HTTPException(422, "No rows imported. " + "; ".join(errors[:20]))
    if not windows or len(windows) > 10000:
        raise HTTPException(422, "Provide between 1 and 10,000 schedule rows")
    unique = list({json.dumps(window, sort_keys=True): window for window in windows}.values())
    return {"windows": unique, "windowCount": len(unique)}
