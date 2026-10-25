import os
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo
from app.models import Task

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="delta-t")


# This describes the *existing dashboard payload*, plus estimatedLength.
class DashboardTask(BaseModel):
    id: str
    name: str = Field(min_length=1)
    estimatedLength: int = Field(gt=0)
    completionPercentage: float = Field(default=0, ge=0, le=100)
    canBeDivided: bool = False
    deadline: date
    priority: Literal["high", "medium", "low"]


class PredictionRequest(BaseModel):
    tasks: list[DashboardTask]


class PredictionResponse(BaseModel):
    success: bool
    tasks: list[Task]


PRIORITIES = {"high": 0, "medium": 1, "low": 2}


def to_prediction_task(incoming: DashboardTask) -> Task:
    """Convert a form task to an engine Task, without guessing its duration.

    Date-only deadlines are interpreted as the END of that day in the configured
    local timezone. Set LOCAL_TIMEZONE to the user's actual calendar timezone
    before processing other users' deadlines.
    """
    
    # Fetch the raw lowercase string: "europe/london"
    raw_env = os.environ.get("TZ", "europe/london") 

    # Format it to "Europe/London"
    formatted_env = "/".join(part.capitalize() for part in raw_env.split("/"))
    
    tz = ZoneInfo(formatted_env)
    deadline = datetime.combine(incoming.deadline, time.max, tzinfo=tz)

    return Task(
        id=incoming.id,
        title=incoming.name,
        estimated_length=incoming.estimatedLength,
        completion_pct=incoming.completionPercentage,
        can_be_divided=incoming.canBeDivided,
        deadline=deadline,
        priority=PRIORITIES[incoming.priority],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/predict", response_model=PredictionResponse)
def start_prediction(request: PredictionRequest) -> PredictionResponse:
    # These are real Task Pydantic objects, ready for the engine.
    prediction_tasks: list[Task] = [
        to_prediction_task(task) for task in request.tasks
    ]

    # NEXT STEP: use your actual engine here:
    # result = run_prediction(tasks=prediction_tasks, ...)
    # This endpoint currently *converts and returns* Task objects. It does not
    # perform predictions or fabricate AI information cards.

    return PredictionResponse(success=True, tasks=prediction_tasks)
