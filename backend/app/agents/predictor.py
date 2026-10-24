"""Run Monte Carlo schedule simulations and summarize failure risks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.agents.chaos import AgentContext, ChaosReport, Prediction, TaskScheduleItem
from app.agents.schemas import Plan
from app.integrations import simulation
from app.models import Event, EventKind, Task
from app.timeutil import LOCAL_TIMEZONE, at_minute


@dataclass(frozen=True)
class _SimulationInputs:
    events: list[Event]
    tasks: list[Task]
    route_cache: dict[str, dict[str, float]]
    weather_cache: dict[str, float]
    meeting_ids: dict[str, str]
    task_ids: dict[str, str]
    display_names: dict[str, str]


def _legacy_context(
    calendar_events: list[dict[str, object]],
    conditions: list[dict[str, object]],
    day_start: datetime,
) -> AgentContext:
    """Adapt the former positional predictor inputs to the shared context."""
    return {
        "calendar_commitments": calendar_events,
        "conditions": conditions,
        "starting_location": "",
        "day_start": day_start,
    }


def _local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)


def _simulation_inputs(
    plan: Plan,
    context: AgentContext,
    task_schedule: list[TaskScheduleItem] | None,
    day_start: datetime,
) -> _SimulationInputs:
    base = day_start.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)
    day_end = base + timedelta(days=1)
    events: list[Event] = []
    meeting_ids: dict[str, str] = {}
    display_names: dict[str, str] = {}

    for item in context["calendar_commitments"]:
        start = _local_naive(datetime.fromisoformat(item["start"]))
        end = _local_naive(datetime.fromisoformat(item["end"]))
        start, end = max(start, base), min(end, day_end)
        if start < end:
            simulation_title = f"calendar:{item['id']}"
            events.append(
                Event(
                    id=item["id"],
                    title=simulation_title,
                    kind=EventKind.fixed,
                    std=0,
                    start_time=start,
                    end_time=end,
                    location=item.get("location") or "Unknown",
                )
            )
            meeting_ids[simulation_title] = item["id"]
            display_names[simulation_title] = item["title"]

    for event in plan.events:
        start = _local_naive(event.start_time)
        end = _local_naive(event.end_time)
        start, end = max(start, base), min(end, day_end)
        if start < end:
            simulation_title = f"event:{event.id}"
            events.append(
                Event(
                    id=event.id,
                    title=simulation_title,
                    kind=event.kind,
                    std=event.std,
                    start_time=start,
                    end_time=end,
                    location=event.location or "Unknown",
                )
            )
            meeting_ids[simulation_title] = event.id
            display_names[simulation_title] = event.title
    events.sort(key=lambda event: event.start)

    task_order = {
        item.task_id: rank
        for rank, item in enumerate(
            sorted(task_schedule or [], key=lambda item: item.start_time)
        )
    }
    task_ids: dict[str, str] = {}
    tasks = []
    for rank, task in enumerate(plan.tasks):
        simulation_title = f"task:{task.id}"
        task_ids[simulation_title] = task.id
        display_names[simulation_title] = task.title
        tasks.append(
            Task(
                id=task.id,
                title=simulation_title,
                estimated_length=task.estimated_length,
                completion_pct=0.0,
                deadline=(
                    at_minute(day_start, task.deadline).replace(tzinfo=None)
                    if task.deadline is not None
                    else day_end
                ),
                priority=min(task_order.get(task.id, rank + 100), 2),
                can_be_divided=task.can_be_divided,
            )
        )

    route_cache: dict[str, dict[str, float]] = {}
    weather_cache: dict[str, float] = {}
    for item in context["conditions"]:
        origin = item.get("origin")
        destination = item.get("destination")
        routes = item.get("route_minutes")
        if origin and destination and routes:
            route_cache[f"{origin}_to_{destination}"] = routes

        probability = item.get("weather", {}).get("precipitation_probability")
        if probability is not None:
            prefix = (
                "calendar"
                if item["source"] == "google_calendar"
                else "event"
            )
            weather_cache[f"{prefix}:{item['event_id']}"] = probability / 100.0

    return _SimulationInputs(
        events=events,
        tasks=tasks,
        route_cache=route_cache,
        weather_cache=weather_cache,
        meeting_ids=meeting_ids,
        task_ids=task_ids,
        display_names=display_names,
    )


def _blend_probabilities(
    nominal: dict[str, float],
    shocked: dict[str, float],
    shock_probability: float,
) -> dict[str, float]:
    names = set(nominal) | set(shocked)
    return {
        name: (1 - shock_probability) * nominal.get(name, 0.0)
        + shock_probability * shocked.get(name, 0.0)
        for name in sorted(names)
    }


def _map_risks_by_id(
    probabilities: dict[str, float],
    names_to_ids: dict[str, str],
) -> dict[str, float]:
    return {
        item_id: probabilities.get(simulation_name, 0.0)
        for simulation_name, item_id in names_to_ids.items()
    }


def _map_risks_by_title(
    probabilities: dict[str, float],
    display_names: dict[str, str],
) -> dict[str, float]:
    return {
        display_names.get(name, name): probability
        for name, probability in probabilities.items()
    }


def predict_outcomes(
    plan: Plan,
    context: AgentContext | list[dict[str, object]],
    chaos: ChaosReport | list[dict[str, object]],
    *legacy_args: object,
    task_schedule: list[TaskScheduleItem] | None = None,
    num_simulations: int = 500,
) -> Prediction:
    """Estimate risks and return canonical probabilities keyed by stable IDs.

    The existing simulator models transit shocks and rain. Title-keyed risk
    fields remain in the output for existing CLI consumers; agents use the
    parallel ID-keyed ``risk_by_id`` structure.
    """
    if num_simulations < 1:
        raise ValueError("num_simulations must be at least 1.")

    if isinstance(context, dict):
        if not isinstance(chaos, ChaosReport) or legacy_args:
            raise TypeError("Shared context must be paired with a ChaosReport.")
        shared_context = context
        chaos_report = chaos
    else:
        if (
            not isinstance(chaos, list)
            or len(legacy_args) != 2
            or not isinstance(legacy_args[0], ChaosReport)
            or not isinstance(legacy_args[1], datetime)
        ):
            raise TypeError("Legacy predictor calls require calendar, context, chaos, and day_start.")
        shared_context = _legacy_context(context, chaos, legacy_args[1])
        chaos_report = legacy_args[0]

    day_start = shared_context["day_start"]
    inputs = _simulation_inputs(plan, shared_context, task_schedule, day_start)
    base = day_start.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)
    nominal = simulation.simulate(
        base,
        inputs.events,
        inputs.tasks,
        transit_shock_active=False,
        num_simulations=num_simulations,
        route_cache=inputs.route_cache,
        weather_cache=inputs.weather_cache,
    )
    shocked = simulation.simulate(
        base,
        inputs.events,
        inputs.tasks,
        transit_shock_active=True,
        num_simulations=num_simulations,
        route_cache=inputs.route_cache,
        weather_cache=inputs.weather_cache,
    )

    shock_probability = chaos_report.transit_shock_probability
    probability_keys = (
        "meeting_failure_probabilities",
        "task_failure_probabilities",
        "task_unfinished_probabilities",
    )
    blended = {
        key: _blend_probabilities(
            nominal.get(key, {}),
            shocked.get(key, {}),
            shock_probability,
        )
        for key in probability_keys
    }
    risks_by_id = {
        "meetings": _map_risks_by_id(
            blended["meeting_failure_probabilities"], inputs.meeting_ids
        ),
        "tasks": _map_risks_by_id(
            blended["task_failure_probabilities"], inputs.task_ids
        ),
        "unfinished_tasks": _map_risks_by_id(
            blended["task_unfinished_probabilities"], inputs.task_ids
        ),
    }

    result: Prediction = {
        "transit_shock_probability": shock_probability,
        "num_simulations_per_scenario": num_simulations,
        "disruptions": [
            disruption.model_dump(mode="json")
            for disruption in chaos_report.disruptions
        ],
        "risk_by_id": risks_by_id,
        "limitations": [
            "Only transit shocks and rain-adjusted travel affect simulation outcomes; other disruption details are not yet modeled.",
            "Task start times affect task priority/order, not exact clock-time blocking.",
            "Event durations use their most-likely (mode) value; duration uncertainty is not sampled.",
        ],
    }
    for key in probability_keys:
        result[key] = _map_risks_by_title(blended[key], inputs.display_names)
    return result
