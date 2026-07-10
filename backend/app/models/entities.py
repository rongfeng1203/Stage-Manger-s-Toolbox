from datetime import date, datetime, time
from enum import StrEnum

from pydantic import field_validator, model_validator
from sqlmodel import Field, SQLModel


class AvailabilityType(StrEnum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    PREFERRED = "PREFERRED"


class SessionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Production(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(min_length=1)
    rehearsal_start_date: date
    rehearsal_end_date: date
    daily_start_time: time
    daily_end_time: time
    slot_duration_minutes: int = Field(default=30, gt=0)

    @model_validator(mode="after")
    def validate_windows(self) -> "Production":
        if self.rehearsal_start_date > self.rehearsal_end_date:
            raise ValueError("rehearsal_start_date must be on or before rehearsal_end_date")
        if self.daily_start_time >= self.daily_end_time:
            raise ValueError("daily_start_time must be before daily_end_time")
        return self


class Scene(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    production_id: int = Field(foreign_key="production.id")
    scene_code: str = Field(min_length=1)
    title: str = Field(default="")
    page_start: int = Field(ge=0)
    page_end: int = Field(ge=0)
    priority: int = Field(default=2, ge=1, le=4)
    target_rehearsal_minutes: int = Field(default=0, ge=0)
    completed_rehearsal_minutes: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_scene(self) -> "Scene":
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        if self.completed_rehearsal_minutes > self.target_rehearsal_minutes:
            raise ValueError("completed_rehearsal_minutes cannot exceed target_rehearsal_minutes")
        return self


class Character(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    production_id: int = Field(foreign_key="production.id")
    name: str = Field(min_length=1)


class Actor(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(min_length=1)
    email: str | None = None
    calendar_connected: bool = False


class CastAssignment(SQLModel, table=True):
    character_id: int = Field(foreign_key="character.id", primary_key=True)
    actor_id: int = Field(foreign_key="actor.id", primary_key=True)


class SceneCharacter(SQLModel, table=True):
    scene_id: int = Field(foreign_key="scene.id", primary_key=True)
    character_id: int = Field(foreign_key="character.id", primary_key=True)
    required: bool = True


class AvailabilityWindow(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    actor_id: int = Field(foreign_key="actor.id")
    start_datetime: datetime
    end_datetime: datetime
    availability_type: AvailabilityType

    @field_validator("start_datetime", "end_datetime")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "AvailabilityWindow":
        if self.start_datetime >= self.end_datetime:
            raise ValueError("start_datetime must be before end_datetime")
        return self


class RehearsalSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    scene_id: int = Field(foreign_key="scene.id")
    start_datetime: datetime
    end_datetime: datetime
    status: SessionStatus = SessionStatus.PROPOSED
    solver_score: int = 0

    @field_validator("start_datetime", "end_datetime")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_session(self) -> "RehearsalSession":
        if self.start_datetime >= self.end_datetime:
            raise ValueError("start_datetime must be before end_datetime")
        return self
