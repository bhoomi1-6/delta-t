"""Structured schemas used by AI agents."""

from pydantic import BaseModel, Field

from app.models import Event


class PlanTask(BaseModel):
    """Gemini-compatible task fields without unsupported exclusive bounds."""

    id: str
    title: str
    estimated_length: int = Field(ge=1)
    can_be_divided: bool = False
    deadline: int | None = None  # minutes since midnight


class Plan(BaseModel):
    """Events and tasks extracted from a user's day description."""

    events: list[Event]
    tasks: list[PlanTask]
