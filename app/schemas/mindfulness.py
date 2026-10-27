from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Mood = Literal["amazing", "good", "fine", "bad", "horrible"]


class MoodCreate(BaseModel):
    log_date: date
    mood: Mood
    emotion: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=240)

    @field_validator("emotion", "reason")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter a description.")
        return cleaned


class MoodResponse(MoodCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class MoodDay(BaseModel):
    date: date
    count: int
    average_score: float | None
    average_mood: Mood | None


class MoodSummary(BaseModel):
    date: date
    latest: MoodResponse | None
    today_entries: list[MoodResponse]
    history: list[MoodDay]


class BreathingSessionCreate(BaseModel):
    exercise: Literal["box", "478", "belly", "custom"]
    duration_seconds: int = Field(ge=1, le=3600)
    started_at: datetime

    @field_validator("started_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A timezone is required.")
        return value


class BreathingSessionResponse(BreathingSessionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class BreathingDay(BaseModel):
    date: date
    count: int
    duration_seconds: int


class BreathingSummary(BaseModel):
    history: list[BreathingDay]


MeditationCategory = Literal["sleep", "ambient", "nature", "instrumental"]


class MeditationSessionCreate(BaseModel):
    category: MeditationCategory
    track_id: str = Field(pattern=r"^(sleep|ambient|nature|instrumental)_(0[1-6])$", max_length=40)
    duration_seconds: int = Field(ge=1, le=14400)
    started_at: datetime

    @model_validator(mode="after")
    def track_matches_category(self):
        if not self.track_id.startswith(f"{self.category}_"):
            raise ValueError("Track does not match category.")
        return self

    @field_validator("started_at")
    @classmethod
    def meditation_timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A timezone is required.")
        return value


class MeditationSessionResponse(MeditationSessionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class MeditationDay(BaseModel):
    date: date
    count: int
    duration_seconds: int


class MeditationSummary(BaseModel):
    history: list[MeditationDay]
