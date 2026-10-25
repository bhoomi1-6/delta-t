"""Run Monte Carlo schedule simulations and summarize failure risks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from app.agents.chaos import AgentContext, Prediction, TaskScheduleItem
from app.agents.schemas import Plan
from app.integrations import simulation
from app.models import Event, EventKind, Task
from app.timeutil import LOCAL_TIMEZONE


@dataclass(frozen=True)
class _SimulationInputs:
    events: list[Event]
    tasks: list[Task]
    route_cache: dict[str, dict[str, float]]
    weather_cache: dict[str, dict[str, float]]
    meeting_ids: dict[str, str]
    task_ids: dict[str, str]
    display_names: dict[str, str]


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
                    location=item.get("location"),
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
                    location=event.location,
                )
            )
            meeting_ids[simulation_title] = event.id
            display_names[simulation_title] = event.title
    events.sort(key=lambda event: event.start_time)

    if task_schedule is not None:
        task_order = {
            item.task_id: rank
            for rank, item in enumerate(
                sorted(task_schedule, key=lambda item: item.start_time)
            )
        }
    else:
        workday_start_hour = context.get("workday_start_hour", 8)
        workday_end_hour = context.get("workday_end_hour", 19)

        def task_urgency(task: PlanTask) -> tuple[float, datetime, float]:
            deadline = (
                _local_naive(task.deadline)
                if task.deadline is not None
                else base + simulation.SIMULATION_HORIZON
            )
            available_minutes, _ = _task_work_capacity(
                base,
                deadline,
                events,
                workday_start_hour,
                workday_end_hour,
            )
            remaining_effort = task.estimated_length * (
                1.0 - task.completion_pct / 100.0
            )
            return (
                available_minutes - remaining_effort,
                deadline,
                -remaining_effort,
            )

        task_order = {
            task.id: rank
            for rank, task in enumerate(sorted(plan.tasks, key=task_urgency))
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
                completion_pct=task.completion_pct,
                deadline=(
                    _local_naive(task.deadline)
                    if task.deadline is not None
                    else day_end
                ),
                priority=task_order[task.id],
                can_be_divided=task.can_be_divided,
            )
        )

    route_cache: dict[str, dict[str, float]] = {}
    weather_cache: dict[str, dict[str, float]] = {}
    for item in context["conditions"]:
        origin = item.get("origin")
        destination = item.get("destination")
        routes = item.get("route_minutes")
        if origin and destination and routes:
            route_cache[f"{origin}_to_{destination}"] = routes

        weather = item.get("weather", {})
        prefix = "calendar" if item["source"] == "google_calendar" else "event"
        weather_cache[f"{prefix}:{item['event_id']}"] = {
            "precipitation_probability": (
                weather.get("precipitation_probability", 0.0) / 100.0
            ),
            "wind_speed_kmh": weather.get("wind_speed_kmh", 0.0),
        }

    return _SimulationInputs(
        events=events,
        tasks=tasks,
        route_cache=route_cache,
        weather_cache=weather_cache,
        meeting_ids=meeting_ids,
        task_ids=task_ids,
        display_names=display_names,
    )


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


def _named_risks(
    risks_by_id: dict[str, dict[str, float]],
    inputs: _SimulationInputs,
) -> list[dict[str, object]]:
    named_risks: list[dict[str, object]] = []
    categories = (
        ("meetings", inputs.meeting_ids),
        ("tasks", inputs.task_ids),
        ("unfinished_tasks", inputs.task_ids),
    )
    for category, simulation_names in categories:
        for simulation_name, item_id in simulation_names.items():
            named_risks.append(
                {
                    "name": inputs.display_names[simulation_name],
                    "category": category,
                    "failure_probability_percent": risks_by_id[category].get(
                        item_id, 0.0
                    ),
                }
            )
    return named_risks


def _task_work_capacity(
    base: datetime,
    deadline: datetime,
    events: list[Event],
    workday_start_hour: int,
    workday_end_hour: int,
) -> tuple[float, float]:
    """Return modeled work minutes and the longest uninterrupted window."""
    effective_deadline = min(deadline, base + simulation.SIMULATION_HORIZON)
    available_minutes = 0.0
    longest_window_minutes = 0.0
    current_date = base.date()

    while current_date <= effective_deadline.date():
        work_start = max(
            datetime.combine(
                current_date,
                time(hour=workday_start_hour),
                tzinfo=base.tzinfo,
            ),
            base,
        )
        cutoff_date = (
            current_date + timedelta(days=1)
            if workday_end_hour == 24
            else current_date
        )
        work_end = min(
            datetime.combine(
                cutoff_date,
                time(0) if workday_end_hour == 24 else time(hour=workday_end_hour),
                tzinfo=base.tzinfo,
            ),
            effective_deadline,
        )
        if work_start < work_end:
            cursor = work_start
            for event in sorted(events, key=lambda item: item.start_time):
                blocked_start = max(work_start, event.start_time)
                blocked_end = min(work_end, event.end_time)
                if blocked_start >= blocked_end:
                    continue
                if blocked_start > cursor:
                    gap_minutes = (blocked_start - cursor).total_seconds() / 60
                    available_minutes += gap_minutes
                    longest_window_minutes = max(longest_window_minutes, gap_minutes)
                cursor = max(cursor, blocked_end)
                if cursor >= work_end:
                    break
            if cursor < work_end:
                gap_minutes = (work_end - cursor).total_seconds() / 60
                available_minutes += gap_minutes
                longest_window_minutes = max(longest_window_minutes, gap_minutes)
        current_date += timedelta(days=1)

    return available_minutes, longest_window_minutes


def _task_diagnostics(
    plan: Plan,
    inputs: _SimulationInputs,
    risks_by_id: dict[str, dict[str, float]],
    base: datetime,
    workday_start_hour: int,
    workday_end_hour: int,
) -> list[dict[str, object]]:
    """Summarize measurable task constraints without claiming causal attribution."""
    simulated_tasks = {task.id: task for task in inputs.tasks}
    diagnostics: list[dict[str, object]] = []
    for task in plan.tasks:
        simulated_task = simulated_tasks[task.id]
        remaining_effort = task.estimated_length * (
            1.0 - task.completion_pct / 100.0
        )
        available_minutes, longest_window_minutes = _task_work_capacity(
            base,
            simulated_task.deadline,
            inputs.events,
            workday_start_hour,
            workday_end_hour,
        )
        potential_constraints: list[str] = []
        if remaining_effort > available_minutes:
            potential_constraints.append(
                "Remaining estimated effort exceeds all modeled work-window time "
                "before the deadline, even before travel, event overruns, "
                "distractions, or other tasks."
            )
        if not task.can_be_divided and remaining_effort > longest_window_minutes:
            potential_constraints.append(
                "The task is indivisible and its remaining estimated effort exceeds "
                "the longest modeled uninterrupted work window before the deadline."
            )
        diagnostics.append(
            {
                "name": task.title,
                "failure_probability_percent": risks_by_id["tasks"].get(task.id, 0.0),
                "unfinished_probability_percent": risks_by_id[
                    "unfinished_tasks"
                ].get(task.id, 0.0),
                "remaining_effort_minutes": round(remaining_effort, 1),
                "deadline": simulated_task.deadline.isoformat(),
                "deadline_source": (
                    "provided" if task.deadline is not None else "simulator_default"
                ),
                "deadline_within_simulation_horizon": (
                    simulated_task.deadline <= base + simulation.SIMULATION_HORIZON
                ),
                "can_be_divided": task.can_be_divided,
                "available_work_minutes_before_deadline": round(
                    available_minutes, 1
                ),
                "longest_uninterrupted_work_window_minutes": round(
                    longest_window_minutes, 1
                ),
                "potential_constraints": potential_constraints,
            }
        )
    return diagnostics


def predict_outcomes(
    plan: Plan,
    context: AgentContext,
    task_schedule: list[TaskScheduleItem] | None = None,
    num_simulations: int = 5000,
) -> Prediction:
    """Estimate risks and return canonical probabilities keyed by stable IDs.

    The existing simulator models transit shocks and rain. Title-keyed risk
    fields remain in the output for existing CLI consumers; agents use the
    parallel ID-keyed ``risk_by_id`` structure.
    """
    if num_simulations < 1:
        raise ValueError("num_simulations must be at least 1.")

    day_start = context["day_start"]
    inputs = _simulation_inputs(plan, context, task_schedule, day_start)
    base = day_start.astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)
    starting_location = (
        context["starting_location"] or simulation.DEFAULT_STARTING_LOCATION
    )
    preferred_transport_mode = context.get(
        "preferred_transport_mode", "fastest"
    )
    workday_start_hour = context.get("workday_start_hour", 8)
    workday_end_hour = context.get("workday_end_hour", 19)
    results = simulation.simulate(
        base,
        inputs.events,
        inputs.tasks,
        transit_shock_active=False,
        num_simulations=num_simulations,
        route_cache=inputs.route_cache,
        weather_cache=inputs.weather_cache,
        starting_location=starting_location,
        preferred_transport_mode=preferred_transport_mode,
        workday_start_hour=workday_start_hour,
        workday_end_hour=workday_end_hour,
    )

    probability_keys = (
        "meeting_failure_probabilities",
        "task_failure_probabilities",
        "task_unfinished_probabilities",
    )
    probabilities = {
        key: results.get(key, {})
        for key in probability_keys
    }
    risks_by_id = {
        "meetings": _map_risks_by_id(
            probabilities["meeting_failure_probabilities"], inputs.meeting_ids
        ),
        "tasks": _map_risks_by_id(
            probabilities["task_failure_probabilities"], inputs.task_ids
        ),
        "unfinished_tasks": _map_risks_by_id(
            probabilities["task_unfinished_probabilities"], inputs.task_ids
        ),
    }
    task_diagnostics = _task_diagnostics(
        plan,
        inputs,
        risks_by_id,
        base,
        workday_start_hour,
        workday_end_hour,
    )

    result: Prediction = {
        "num_simulations_per_scenario": num_simulations,
        "risk_by_id": risks_by_id,
        "risk_by_name": _named_risks(risks_by_id, inputs),
        "task_diagnostics": task_diagnostics,
        "limitations": [
            "Disruption forecasts and transit-shock scenarios are disabled; travel still uses the simulator's baseline delay and weather adjustments.",
            "The task schedule defines a strict work priority: available work time goes to the first unfinished divisible task until it is complete or its deadline passes, then proceeds to the next task. Tasks marked indivisible are attempted only when a single available work window can fit their remaining effort.",
            "Event duration is sampled from a normal distribution centered on the scheduled duration, using std as its standard deviation and clamping samples at zero.",
            "Task probabilities do not include per-run failure-cause attribution; task diagnostics are screening facts, not proof of which factor caused a simulated failure.",
        ],
    }
    for key in probability_keys:
        result[key] = _map_risks_by_title(probabilities[key], inputs.display_names)
    return result
