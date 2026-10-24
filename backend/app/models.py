"""Pydantic models: Event, Task, Disruption"""
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class EventKind(str, Enum):
    deadline = "deadline"
    flexible = "flexible"
    travel = "travel"
    fixed = "fixed"


class TriangularDist(BaseModel):
    """Triangular distribution over a duration, in minutes."""

    min: float = Field(ge=0)
    mode: float = Field(ge=0)
    max: float = Field(ge=0)

    @model_validator(mode="after")
    def check_order(self) -> "TriangularDist":
        if not self.min <= self.mode <= self.max:
            raise ValueError("require min <= mode <= max")
        return self


class Event(BaseModel):
    id: str
    title: str
    kind: EventKind
    duration: TriangularDist
    start_time: int | None = None  # minutes from simulation start
    location: str | None = None
    priority: int = Field(default=1, ge=0, le=2)  


class Task(BaseModel):
    id: str
    title: str
    estimated_length: int = Field(gt=0)  # minutes
    can_be_divided: bool = False
    deadline: int | None = None  # minutes since midnight


class Disruption(BaseModel):
    id: str
    title: str
    probability: float = Field(ge=0, le=1)
    time_wasted: float = Field(ge=0)  # minutes lost if it occurs
    predicted_cost: float = Field(ge=0)
