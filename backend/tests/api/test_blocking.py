from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def request_payload() -> dict[str, object]:
    return {
        "stage": {"width": 100, "depth": 100},
        "known_actor_ids": [1],
        "known_scene_ids": [10],
        "beats": [
            {
                "id": 1,
                "scene_id": 10,
                "label": "ENTRANCE",
                "order": 1,
                "positions": [{"actor_id": 1, "x": 20, "y": 40}],
                "movements": [
                    {
                        "actor_id": 1,
                        "from_x": 20,
                        "from_y": 40,
                        "to_x": 60,
                        "to_y": 70,
                        "sequence": 1,
                    }
                ],
                "cues": [
                    {
                        "id": 1,
                        "cue_type": "LIGHT",
                        "label": "LX 1",
                        "trigger": "WHEN THE DOOR CLOSES",
                    }
                ],
            }
        ],
    }


def test_blocking_validation_route_serializes_valid_notebook() -> None:
    response = client.post("/api/blocking/validate", json=request_payload())
    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "summary": {
            "beatCount": 1,
            "positionCount": 1,
            "movementCount": 1,
            "cueCount": 1,
        },
        "issues": [],
    }


def test_blocking_validation_route_returns_structured_issues() -> None:
    payload = request_payload()
    beats = payload["beats"]
    assert isinstance(beats, list)
    beats[0]["scene_id"] = 99
    beats[0]["cues"][0]["trigger"] = ""
    response = client.post("/api/blocking/validate", json=payload)
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["issues"] == [
        {
            "code": "UNKNOWN_SCENE",
            "message": "BEAT 1: SCENE 99 IS NOT IN THIS PRODUCTION",
            "beatId": 1,
        },
        {
            "code": "CUE_TRIGGER_REQUIRED",
            "message": "BEAT 1: CUE 1 NEEDS A TRIGGER",
            "beatId": 1,
            "cueId": 1,
        },
    ]


def test_blocking_validation_route_rejects_malformed_movement() -> None:
    payload = request_payload()
    beats = payload["beats"]
    assert isinstance(beats, list)
    beats[0]["movements"][0]["sequence"] = 0
    response = client.post("/api/blocking/validate", json=payload)
    assert response.status_code == 422
