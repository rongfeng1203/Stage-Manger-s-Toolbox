from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_script_analysis_route_returns_reviewable_output() -> None:
    response = client.post(
        "/api/scripts/analyze",
        json={"text": "HAMLET\n\nACT I, SCENE I\n\nHAMLET\nTo be."},
    )
    assert response.status_code == 200
    assert response.json()["scenes"][0]["sceneCode"] == "A1S1"
    assert response.json()["scenes"][0]["characters"] == ["Hamlet"]


def test_script_analysis_route_explains_invalid_script() -> None:
    response = client.post("/api/scripts/analyze", json={"text": "No scenes here."})
    assert response.status_code == 200
    assert "INFERRED_SCENES" in {warning["code"] for warning in response.json()["warnings"]}


def test_script_upload_extracts_and_analyzes_text_file() -> None:
    response = client.post(
        "/api/scripts/upload",
        files={
            "file": (
                "aladdin.script",
                b"ALADDIN\n\nPEDDLER: Welcome.\n\n(Cut to rooftop.)\nALADDIN: Run!",
                "text/plain",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["fileName"] == "aladdin.script"
    assert response.json()["scenes"][1]["characters"] == ["Aladdin"]


def test_script_upload_rejects_unsupported_and_oversized_files() -> None:
    unsupported = client.post(
        "/api/scripts/upload",
        files={"file": ("play.docx", b"content", "application/octet-stream")},
    )
    assert unsupported.status_code == 422
    oversized = client.post(
        "/api/scripts/upload",
        files={"file": ("play.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")},
    )
    assert oversized.status_code == 413
