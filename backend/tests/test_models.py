from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from backend.app.models import (
    AvailabilityType,
    AvailabilityWindow,
    Production,
    RehearsalSession,
    Scene,
)


def test_production_defaults_to_30_minute_slots() -> None:
    production = Production.model_validate(
        {
            "name": "Hamlet",
            "rehearsal_start_date": date(2026, 7, 1),
            "rehearsal_end_date": date(2026, 7, 14),
            "daily_start_time": time(18, 0),
            "daily_end_time": time(22, 0),
        }
    )

    assert production.slot_duration_minutes == 30


def test_production_rejects_invalid_date_range() -> None:
    with pytest.raises(ValidationError):
        Production.model_validate(
            {
                "name": "Hamlet",
                "rehearsal_start_date": date(2026, 7, 14),
                "rehearsal_end_date": date(2026, 7, 1),
                "daily_start_time": time(18, 0),
                "daily_end_time": time(22, 0),
            }
        )


def test_production_rejects_invalid_daily_hours() -> None:
    with pytest.raises(ValidationError):
        Production.model_validate(
            {
                "name": "Hamlet",
                "rehearsal_start_date": date(2026, 7, 1),
                "rehearsal_end_date": date(2026, 7, 14),
                "daily_start_time": time(22, 0),
                "daily_end_time": time(18, 0),
            }
        )


def test_scene_rejects_completed_minutes_above_target() -> None:
    with pytest.raises(ValidationError):
        Scene.model_validate(
            {
                "production_id": 1,
                "scene_code": "A1S1",
                "page_start": 1,
                "page_end": 2,
                "target_rehearsal_minutes": 60,
                "completed_rehearsal_minutes": 90,
            }
        )


def test_availability_window_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        AvailabilityWindow.model_validate(
            {
                "actor_id": 1,
                "start_datetime": datetime(2026, 7, 1, 18, 0),
                "end_datetime": datetime(2026, 7, 1, 22, 0),
                "availability_type": AvailabilityType.AVAILABLE,
            }
        )


def test_availability_window_rejects_invalid_range() -> None:
    tz = ZoneInfo("America/Toronto")

    with pytest.raises(ValidationError):
        AvailabilityWindow.model_validate(
            {
                "actor_id": 1,
                "start_datetime": datetime(2026, 7, 1, 22, 0, tzinfo=tz),
                "end_datetime": datetime(2026, 7, 1, 18, 0, tzinfo=tz),
                "availability_type": AvailabilityType.AVAILABLE,
            }
        )


def test_rehearsal_session_rejects_invalid_range() -> None:
    tz = ZoneInfo("America/Toronto")

    with pytest.raises(ValidationError):
        RehearsalSession.model_validate(
            {
                "scene_id": 1,
                "start_datetime": datetime(2026, 7, 1, 19, 0, tzinfo=tz),
                "end_datetime": datetime(2026, 7, 1, 19, 0, tzinfo=tz),
            }
        )
