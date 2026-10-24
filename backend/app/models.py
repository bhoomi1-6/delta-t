"""Pydantic models: Event, Task, Disruption"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class EventKind(str, Enum):
    deadline = "deadline"
    flexible = "flexible"
    travel = "travel"
    fixed = "fixed"



class Event(BaseModel):
    id: str
    title: str
    kind: EventKind
    std: int = Field(ge=0)  # standard deviation of duration, in minutes
    start_time: datetime
    end_time: datetime
    location: str | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "Event":
        if (self.start_time.utcoffset() is None) != (
            self.end_time.utcoffset() is None
        ):
            raise ValueError(
                "start_time and end_time must have matching timezone awareness"
            )
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class Task(BaseModel):
    id: str
    title: str
    estimated_length: int = Field(gt=0)  # minutes
    completion_pct: float = Field(ge=0, le=100)
    can_be_divided: bool = False
    deadline: datetime
    priority: int = Field(ge=0, le=2)  # 0 = high, 1 = medium, 2 = low


class Disruption(BaseModel):
    id: str
    title: str
    probability: float = Field(ge=0, le=1)
    time_wasted: float = Field(ge=0)  # minutes lost if it occurs
    predicted_cost: float = Field(ge=0)
