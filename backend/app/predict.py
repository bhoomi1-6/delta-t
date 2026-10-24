"""Receive the dashboard's task list and convert it to models.Task."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models import Task
from app.timeutil import day_bounds

# The dashboard has no length field, so assume this until it does.
DEFAULT_TASK_MINUTES = 60
END_OF_DAY = 24 * 60 - 1
PRIORITY = {"low": 0, "medium": 1, "high": 2}

router = APIRouter(prefix="/api")


class FrontendTask(BaseModel):
    """A task exactly as the dashboard sends it (camelCase, date-only deadline)."""

    id: str
    name: str = Field(min_length=1)
    deadline: date
    priority: Literal["low", "medium", "high"]
    can_be_divided: bool = Field(default=False, alias="canBeDivided")


class PredictRequest(BaseModel):
    tasks: list[FrontendTask]


class PredictResponse(BaseModel):
    simulation_day: date
    tasks: list[Task]


def to_task(task: FrontendTask, simulation_day: date) -> Task:
    """Map a dashboard task onto the simulated day.

    The dashboard deadline is a date with no time, so it is treated as the end
    of that day: due on the simulated day -> minute 1439, due later -> no
    deadline within the day, already past -> minute 0.
    """
    if task.deadline == simulation_day:
        deadline = END_OF_DAY
    elif task.deadline > simulation_day:
        deadline = None
    else:
        deadline = 0

    return Task(
        id=task.id,
        title=task.name,
        estimated_length=DEFAULT_TASK_MINUTES,
        can_be_divided=task.can_be_divided,
        deadline=deadline,
        priority=PRIORITY[task.priority],
    )


@router.post("/predict")
def predict(request: PredictRequest) -> PredictResponse:
    simulation_day = day_bounds()[0].date()
    return PredictResponse(
        simulation_day=simulation_day,
        tasks=[to_task(task, simulation_day) for task in request.tasks],
    )
