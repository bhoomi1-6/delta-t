"""Structured schemas used by AI agents."""

from pydantic import BaseModel

from app.models import Event, Task


class Plan(BaseModel):
    """Events and tasks extracted from a user's day description."""

    events: list[Event]
    tasks: list[Task]
