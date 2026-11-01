import io
import json
from datetime import date, time

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.main import app

client = TestClient(app)
CAST = [{"id": 1, "name": "Alex", "email": "alex@example.com"}]


def upload(raw: bytes, filename: str = "schedule.csv", actors: list | None = None):
    return client.post(
        "/api/availability/import",
        files={"file": (filename, raw)},
        data={"actors": json.dumps(actors or CAST), "timezone": "America/Toronto"},
    )


def test_csv_matches_email_and_preserves_busy():
    response = upload(
        b"email,date,start,end,type\nALEX@example.com,2026-11-02,18:00,22:00,AVAILABLE\nalex@example.com,2026-11-02,19:00,20:00,BUSY\n"
    )
    assert response.status_code == 200
    assert response.json()["windowCount"] == 2
    assert response.json()["windows"][1]["availabilityType"] == "BUSY"


def test_excel_native_dates_and_multiple_sheets():
    workbook = Workbook()
    for sheet in (workbook.active, workbook.create_sheet("Other")):
        sheet.append(["actor", "date", "start", "end"])
        sheet.append(["Alex", date(2026, 11, 2), time(18), time(22)])
    stream = io.BytesIO()
    workbook.save(stream)
    response = upload(stream.getvalue(), "schedule.xlsx")
    assert response.status_code == 200
    assert response.json()["windows"] == [
        {
            "actorId": 1,
            "start": "2026-11-02T18:00",
            "end": "2026-11-02T22:00",
            "availabilityType": "AVAILABLE",
        }
    ]


def test_bad_rows_reject_entire_import():
    response = upload(
        b"actor,start,end\nAlex,2026-11-02T18:00,2026-11-02T22:00\nUnknown,2026-11-02T18:00,2026-11-02T22:00"
    )
    assert response.status_code == 422
    assert "row 3" in response.json()["detail"]
    assert "No rows imported" in response.json()["detail"]


def test_ambiguous_names_require_identifier():
    cast = CAST + [{"id": 2, "name": "Alex", "email": "other@example.com"}]
    assert (
        upload(b"actor,start,end\nAlex,2026-11-02T18:00,2026-11-02T22:00", actors=cast).status_code
        == 422
    )
    assert (
        upload(
            b"actor,email,start,end\nAlex,other@example.com,2026-11-02T18:00,2026-11-02T22:00",
            actors=cast,
        ).json()["windows"][0]["actorId"]
        == 2
    )


def test_invalid_times_and_files():
    for start, end in [
        ("2026-11-02T22:00", "2026-11-02T18:00"),
        ("2026-11-01T01:30", "2026-11-01T03:00"),
        ("=NOW()", "2026-11-02T22:00"),
    ]:
        assert upload(f"actor,start,end\nAlex,{start},{end}".encode()).status_code == 422
    assert upload(b"not a workbook", "bad.xlsx").status_code == 422
    assert upload(b"old format", "old.xls").status_code == 422
