"""Receive the dashboard's task list and run the planning workflow on it."""

from __future__ import annotations

import os
from datetime import date, datetime, time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents.orchestrator import review_plan
from app.agents.schemas import Plan, PlanTask
from app.integrations.simulation import DEFAULT_STARTING_LOCATION
from app.steplog import step
from app.timeutil import LOCAL_TIMEZONE, day_bounds

from app.integrations.google_oauth import get_calendar_credentials
from app.integrations.google_calendar import get_day



PRIORITY = {"high": 0, "medium": 1, "low": 2}  # models.Task: 0 = high, 2 = low

router = APIRouter(prefix="/api")


class FrontendTask(BaseModel):
    """A task exactly as the dashboard sends it (camelCase, date-only deadline)."""

    id: str
    name: str = Field(min_length=1)
    deadline: date
    priority: Literal["low", "medium", "high"]
    can_be_divided: bool = Field(default=False, alias="canBeDivided")
    completion_percentage: float = Field(default=0.0, ge=0, le=100, alias="completionPercentage")
    estimated_length: int = Field(gt=0, alias="estimatedLength")


class PredictRequest(BaseModel):
    tasks: list[FrontendTask]
    starting_location: str | None = Field(default=None, alias="startingLocation")


class PredictResponse(BaseModel):
    simulation_day: date
    tasks: list[PlanTask]
    review: dict[str, Any]


def to_plan_task(task: FrontendTask) -> PlanTask:
    """Map a dashboard task onto the planning agents' task schema.

    The dashboard deadline is a date with no time, so it is treated as the end
    of that day (Europe/London).
    """
    return PlanTask(
        id=task.id,
        title=task.name,
        estimated_length=task.estimated_length,
        completion_pct=task.completion_percentage,
        can_be_divided=task.can_be_divided,
        deadline=datetime.combine(task.deadline, time(23, 59), tzinfo=LOCAL_TIMEZONE),
        priority=PRIORITY[task.priority],
    )


@router.post("/predict")
def predict(payload: PredictRequest, request: Request) -> PredictResponse:
    credentials = get_calendar_credentials(request)
    from app.integrations.google_calendar import get_day
    simulation_start, simulation_end, events = get_day(credentials=credentials)

    tasks = [to_plan_task(task) for task in payload.tasks]
    starting_location = (
        payload.starting_location
        or os.environ.get("STARTING_LOCATION")
        or DEFAULT_STARTING_LOCATION
    )

    try:
        with step("predict request"):
            review = review_plan(Plan(events=events, tasks=tasks), starting_location, credentials=credentials)
    except (RuntimeError, ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return PredictResponse(
        simulation_day=day_bounds()[0].date(),
        tasks=tasks,
        review=review,
    )

