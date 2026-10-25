"""Structured schemas used by AI agents."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models import Event


class PlanTask(BaseModel):
    """Gemini-compatible task input, adapted to the simulation Task model."""

    id: str
    title: str
    estimated_length: int = Field(ge=1)
    completion_pct: float = Field(ge=0, le=100)
    can_be_divided: bool = True
    deadline: datetime | None = None


class Plan(BaseModel):
    """Events and tasks extracted from a user's day description."""

    events: list[Event]
    tasks: list[PlanTask]
