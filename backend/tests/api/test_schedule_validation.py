from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def request_payload() -> dict[str, object]:
    return {
        "actors": [{"id": 1, "name": "Rina Feng"}],
        "availability": [
            {
                "actor_id": 1,
                "start": "2026-07-14T18:00",
                "end": "2026-07-14T22:00",
                "availability_type": "AVAILABLE",
            }
        ],
        "scenes": [{"id": 1, "scene_code": "A1S1", "target_rehearsal_minutes": 120}],
        "sessions": [
            {
                "id": 1,
                "scene_id": 1,
                "scene_code": "A1S1",
                "actor_ids": [1],
                "start": "2026-07-14T18:00",
                "end": "2026-07-14T20:00",
                "duration_minutes": 120,
            }
        ],
        "timezone": "America/Toronto",
    }


def test_schedule_validation_route_returns_python_result() -> None:
    response = client.post("/api/schedules/validate", json=request_payload())
    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "conflicts": [],
        "debts": [
            {
                "sceneCode": "A1S1",
                "requiredMinutes": 120,
                "scheduledMinutes": 120,
                "remainingMinutes": 0,
            }
        ],
    }


def test_schedule_validation_route_rejects_unknown_timezone() -> None:
    payload = request_payload()
    payload["timezone"] = "Mars/Olympus"
    response = client.post("/api/schedules/validate", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"] == "unknown timezone"


def test_schedule_validation_route_rejects_dst_gap() -> None:
    payload = request_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    sessions[0]["start"] = "2026-03-08T02:30"
    sessions[0]["end"] = "2026-03-08T03:30"
    response = client.post("/api/schedules/validate", json=payload)
    assert response.status_code == 422
    assert "local time does not exist" in response.json()["detail"]


def test_schedule_validation_route_rejects_ambiguous_dst_time() -> None:
    payload = request_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    sessions[0]["start"] = "2026-11-01T01:30"
    sessions[0]["end"] = "2026-11-01T02:30"
    response = client.post("/api/schedules/validate", json=payload)
    assert response.status_code == 422
    assert "local time is ambiguous" in response.json()["detail"]


def test_schedule_validation_route_rejects_zero_duration_and_negative_target() -> None:
    payload = request_payload()
    sessions = payload["sessions"]
    scenes = payload["scenes"]
    assert isinstance(sessions, list)
    assert isinstance(scenes, list)
    sessions[0]["duration_minutes"] = 0
    assert client.post("/api/schedules/validate", json=payload).status_code == 422
    sessions[0]["duration_minutes"] = 120
    scenes[0]["target_rehearsal_minutes"] = -1
    assert client.post("/api/schedules/validate", json=payload).status_code == 422


def test_schedule_validation_route_rejects_duplicate_actor_ids() -> None:
    payload = request_payload()
    actors = payload["actors"]
    assert isinstance(actors, list)
    actors.append({"id": 1, "name": "Duplicate"})
    response = client.post("/api/schedules/validate", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"] == "duplicate actor id"
