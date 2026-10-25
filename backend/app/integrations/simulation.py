from datetime import date, datetime, time, timedelta
import numpy as np
from dataclasses import dataclass
from typing import Any
from collections import Counter
from typing import Literal
from ..models import Event, Task

WORKDAY_START = time(hour=8)
WORKDAY_CUTOFF = time(hour=19)
SIMULATION_HORIZON = timedelta(days=7)
DEFAULT_STARTING_LOCATION = "St. Catherine's College"
TransportMode = Literal["fastest", "walking", "transit", "cycling"]

# Data Structures

@dataclass
class _ActiveTask:
    title: str
    remaining_mins: float
    deadline: datetime
    priority: int
    can_be_divided: bool


def _work_on_tasks(
    active_tasks: list[_ActiveTask],
    current_time: datetime,
    work_until: datetime,
    failed_tasks: set[str],
) -> datetime:
    for task in active_tasks:
        if task.remaining_mins <= 0:
            continue
        if task.deadline <= current_time:
            failed_tasks.add(task.title)
            continue

        task_work_until = min(work_until, task.deadline)
        available_mins = (task_work_until - current_time).total_seconds() / 60
        if available_mins <= 0:
            continue

        if not task.can_be_divided:
            if available_mins < task.remaining_mins:
                continue

            distraction_penalty = (
                np.random.uniform(10, 30) if np.random.rand() < 0.3 else 0.0
            )
            required_mins = task.remaining_mins + distraction_penalty
            if available_mins < required_mins:
                continue

            current_time += timedelta(minutes=required_mins)
            task.remaining_mins = 0.0
            continue

        time_allocated = min(available_mins, task.remaining_mins)
        distraction_penalty = (
            np.random.uniform(10, 30) if np.random.rand() < 0.3 else 0.0
        )
        progress_made = max(0.0, time_allocated - distraction_penalty)
        task.remaining_mins = max(0.0, task.remaining_mins - progress_made)
        current_time += timedelta(minutes=time_allocated)

        if task.remaining_mins > 0 and current_time >= task.deadline:
            failed_tasks.add(task.title)

    return current_time

# --- 2. THE SIMULATION ENGINE ---

def simulate(
    simulation_base_date: datetime,
    events: list[Event],
    tasks: list[Task],
    transit_shock_active: bool,
    num_simulations: int = 1000,
    route_cache: dict[str, dict[str, float]] | None = None,
    weather_cache: dict[str, float | dict[str, float]] | None = None,
    starting_location: str = DEFAULT_STARTING_LOCATION,
    preferred_transport_mode: TransportMode = "fastest",
    workday_start_hour: int = WORKDAY_START.hour,
    workday_end_hour: int = WORKDAY_CUTOFF.hour,
) -> dict[str, Any]:

    meeting_failures = Counter()
    task_failures = Counter()
    task_unfinished = Counter()

    if not isinstance(simulation_base_date, datetime):
        raise TypeError("simulation_base_date must be a datetime")
    if not 0 <= workday_start_hour < 24:
        raise ValueError("workday_start_hour must be between 0 and 23")
    if not 1 <= workday_end_hour <= 24:
        raise ValueError("workday_end_hour must be between 1 and 24")
    if workday_end_hour <= workday_start_hour:
        raise ValueError("workday_end_hour must be after workday_start_hour")

    all_datetimes = [simulation_base_date]
    for event in events:
        if event.end_time <= event.start_time:
            raise ValueError(f"Event {event.title!r} must end after it starts")
        if event.std < 0:
            raise ValueError(f"Event {event.title!r} std must be nonnegative")
        all_datetimes.extend((event.start_time, event.end_time))
    all_datetimes.extend(task.deadline for task in tasks)

    base_is_aware = simulation_base_date.utcoffset() is not None
    if any((value.utcoffset() is not None) != base_is_aware for value in all_datetimes):
        raise ValueError("All simulation datetimes must consistently be timezone-aware or naive")
    if any(value.tzinfo != simulation_base_date.tzinfo for value in all_datetimes):
        raise ValueError("All simulation datetimes must use the same timezone")
    if any(
        event.start_time.date() < simulation_base_date.date()
        for event in events
    ):
        raise ValueError("Events cannot start before simulation_base_date")

    route_cache = route_cache or {}
    weather_cache = weather_cache or {}
    events_by_date: dict[date, list[Event]] = {}
    for event in events:
        events_by_date.setdefault(event.start_time.date(), []).append(event)
    for daily_events in events_by_date.values():
        daily_events.sort(key=lambda event: event.start_time)

    latest_relevant_time = max(
        [simulation_base_date]
        + [event.end_time for event in events]
        + [task.deadline for task in tasks]
    )
    simulation_end = min(
        latest_relevant_time,
        simulation_base_date + SIMULATION_HORIZON,
    )
    last_simulation_date = simulation_end.date()

    # Pre-calculate transit delay samples
    if transit_shock_active:
        transit_delay_samples = np.random.exponential(scale=15.0, size=num_simulations) + 10.0
    else:
        transit_delay_samples = np.random.uniform(0, 5, size=num_simulations)

    for run in range(num_simulations):
        failed_tasks: set[str] = set()
        active_tasks: list[_ActiveTask] = []
        for t in tasks:
            rem_work = t.estimated_length * (1.0 - (t.completion_pct / 100.0))
            active_tasks.append(
                _ActiveTask(
                    title=t.title,
                    remaining_mins=rem_work,
                    deadline=t.deadline,
                    priority=t.priority,
                    can_be_divided=t.can_be_divided,
                )
            )

        active_tasks.sort(key=lambda task: task.priority)

        current_location = starting_location
        current_date = simulation_base_date.date()
        current_time = simulation_base_date
        while current_date <= last_simulation_date:
            day_start = datetime.combine(
                current_date,
                time(hour=workday_start_hour),
                tzinfo=simulation_base_date.tzinfo,
            )
            cutoff_date = current_date + timedelta(days=1) if workday_end_hour == 24 else current_date
            cutoff_time = time(0) if workday_end_hour == 24 else time(hour=workday_end_hour)
            day_cutoff = min(
                datetime.combine(
                    cutoff_date,
                    cutoff_time,
                    tzinfo=simulation_base_date.tzinfo,
                ),
                simulation_end,
            )
            current_time = max(current_time, day_start, simulation_base_date)

            for event in events_by_date.get(current_date, []):
                event_start = event.start_time
                if event_start >= simulation_end:
                    continue

                if event.location and event.location.strip():
                    route_data = dict(
                        route_cache.get(
                            f"{current_location}_to_{event.location}",
                            {"walking": 15.0, "transit": 10.0, "cycling": 12.0},
                        )
                    )
                    if "transit" in route_data:
                        route_data["transit"] += transit_delay_samples[run]

                    event_weather = weather_cache.get(event.title, 0.0)
                    if isinstance(event_weather, dict):
                        rain_probability = event_weather.get(
                            "precipitation_probability", 0.0
                        )
                        wind_speed_kmh = max(
                            0.0, event_weather.get("wind_speed_kmh", 0.0)
                        )
                    else:
                        rain_probability = event_weather
                        wind_speed_kmh = 0.0

                    is_raining = np.random.rand() < rain_probability
                    if is_raining:
                        route_data["walking"] *= 1.1
                        route_data["cycling"] *= 1.5

                    wind_exposure = min(max(wind_speed_kmh - 15.0, 0.0) / 45.0, 1.0)
                    route_data["walking"] *= 1.0 + (0.15 * wind_exposure)
                    route_data["cycling"] *= 1.0 + (0.5 * wind_exposure)
                    route_variability = {
                        "walking": 0.1 * wind_exposure,
                        "cycling": 0.25 * wind_exposure,
                    }
                    sampled_routes = {
                        mode: max(
                            0.0,
                            float(
                                np.random.normal(
                                    duration,
                                    duration * route_variability.get(mode, 0.0),
                                )
                            ),
                        )
                        for mode, duration in route_data.items()
                    }
                    selected_mode = (
                        preferred_transport_mode
                        if preferred_transport_mode != "fastest"
                        and preferred_transport_mode in sampled_routes
                        else min(sampled_routes, key=sampled_routes.get)
                    )
                    total_commute_time = sampled_routes[selected_mode]
                else:
                    total_commute_time = 0.0

                latest_departure_time = event_start - timedelta(
                    minutes=total_commute_time
                )
                work_until = min(latest_departure_time, day_cutoff)
                if (work_until - current_time).total_seconds() > 10 * 60:
                    current_time = _work_on_tasks(
                        active_tasks, current_time, work_until, failed_tasks
                    )

                departure_time = max(current_time, latest_departure_time)
                actual_arrival = departure_time + timedelta(
                    minutes=total_commute_time
                )
                if actual_arrival > event_start:
                    meeting_failures[event.title] += 1

                nominal_duration_mins = (
                    event.end_time - event_start
                ).total_seconds() / 60
                sampled_duration_mins = max(
                    0.0,
                    float(np.random.normal(nominal_duration_mins, event.std)),
                )
                actual_event_end = max(actual_arrival, event_start) + timedelta(
                    minutes=sampled_duration_mins
                )
                current_time = max(
                    current_time,
                    actual_event_end,
                )
                if event.location and event.location.strip():
                    current_location = event.location

            if current_time < day_cutoff:
                current_time = _work_on_tasks(
                    active_tasks, current_time, day_cutoff, failed_tasks
                )

            current_date += timedelta(days=1)

        for task in active_tasks:
            if task.remaining_mins <= 0:
                continue
            if task.deadline <= simulation_end:
                failed_tasks.add(task.title)
            else:
                task_unfinished[task.title] += 1

        for task_title in failed_tasks:
            task_failures[task_title] += 1

    # --- 4. COMPILE PROBABILISTIC INSIGHTS ---
    return {
        "transit_shock_flagged": transit_shock_active,
        "meeting_failure_probabilities": {title: (count / num_simulations) * 100 for title, count in meeting_failures.items()},
        "task_failure_probabilities": {title: (count / num_simulations) * 100 for title, count in task_failures.items()},
        "task_unfinished_probabilities": {
            title: (count / num_simulations) * 100
            for title, count in task_unfinished.items()
        },
    }