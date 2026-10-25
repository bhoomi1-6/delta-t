"""Coordinate calendar, weather, routing, and Gemini plan review."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import load_backend_environment
from app.agents.chaos import AgentContext
from app.agents.judge import compare_timelines
from app.agents.intake import parse_plan
from app.agents.predictor import predict_outcomes
from app.agents.repair import propose_repair
from app.agents.schemas import Plan
from app.integrations.google_calendar import get_busy_events
from app.integrations.router import get_route_durations_by_arrival
from app.integrations.weather import get_oxford_weather_forecasts
from app.steplog import logger, step
from app.timeutil import day_bounds
from google.oauth2.credentials import Credentials

@dataclass(frozen=True)
class _ItineraryItem:
    event_id: str
    title: str
    start: datetime
    location: str | None
    source: str


def _collect_context(
    plan: Plan,
    starting_location: str,
    calendar_id: str | None,
    now: datetime,
    credentials,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    # The simulated day is tomorrow, midnight to midnight; times in the plan
    # are minutes since that day's midnight.
    day_start, end = day_bounds(now=now)
    with step(f"calendar {day_start.date()}"):
        busy_events = get_busy_events(day_start, end, calendar_id, credentials=credentials)
    logger.info(
        "[calendar] %d event(s): %s",
        len(busy_events),
        ", ".join(f"{e.summary} @ {e.start:%H:%M}" for e in busy_events) or "none",
    )

    calendar_context: list[dict[str, object]] = []
    itinerary: list[_ItineraryItem] = []
    for event in busy_events:
        calendar_context.append(
            {
                "id": event.event_id,
                "title": event.summary,
                "start": event.start.isoformat(),
                "end": event.end.isoformat(),
                "location": event.location,
                "description": event.description,
            }
        )
        itinerary.append(
            _ItineraryItem(
                event_id=event.event_id,
                title=event.summary,
                start=event.start,
                location=event.location,
                source="google_calendar",
            )
        )

    for event in plan.events:
        start = event.start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=day_start.tzinfo)
        if day_start <= start < end:
            itinerary.append(
                _ItineraryItem(
                    event_id=event.id,
                    title=event.title,
                    start=start,
                    location=event.location,
                    source="user_plan",
                )
            )

    itinerary.sort(key=lambda item: item.start)

    weather_times = [
        item.start.astimezone(timezone.utc).replace(tzinfo=None)
        for item in itinerary
    ]
    with step(f"weather batch ({len(weather_times)} event(s))"):
        weather_forecasts = get_oxford_weather_forecasts(weather_times)
    conditions: list[dict[str, object]] = []
    origin = starting_location
    route_results: dict[tuple[str, str, str], dict[str, float]] = {}
    for item, weather in zip(itinerary, weather_forecasts):
        start = item.start
        location = item.location
        logger.info("[weather] %s -> %s", item.title, weather)
        condition: dict[str, object] = {
            "event_id": item.event_id,
            "title": item.title,
            "start": start.isoformat(),
            "source": item.source,
            "weather_location": "Oxford, UK",
            "weather": weather,
        }
        if isinstance(location, str) and location.strip():
            condition["origin"] = origin
            condition["destination"] = location
            route_key = (
                origin.strip().casefold(),
                location.strip().casefold(),
                start.replace(minute=0, second=0, microsecond=0).isoformat(),
            )
            if route_key not in route_results:
                with step(f"routes {origin} -> {location}"):
                    route_results[route_key] = get_route_durations_by_arrival(
                        origin,
                        location,
                        start.astimezone(timezone.utc).replace(tzinfo=None),
                    )
            condition["route_minutes"] = route_results[route_key]
            logger.info(
                "[routes] %s -> %s: %s", origin, location, condition["route_minutes"]
            )
            origin = location
        else:
            condition["route_note"] = "No destination location was provided."
            logger.info("[routes] %s has no location, skipping route lookup", item.title)
        conditions.append(condition)

    return calendar_context, conditions


def _check_ready(starting_location: str) -> None:
    if not starting_location.strip():
        raise ValueError("Starting location cannot be empty.")

    load_backend_environment()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")


def review_day(
    description: str,
    starting_location: str,
    calendar_id: str | None = None,
) -> dict[str, object]:
    """Return a proposed revision without writing to Google Calendar."""
    _check_ready(starting_location)

    now = datetime.now(timezone.utc)
    day_start = day_bounds(now=now)[0]
    plan = parse_plan(description, plan_day=day_start.date())
    return review_plan(plan, starting_location, calendar_id, now)


def review_plan(
    plan: Plan,
    starting_location: str,
    calendar_id: str | None = None,
    now: datetime | None = None,
    credentials: Credentials | None = None,
    preferred_transport_mode: str = "fastest",
    workday_start_hour: int = 8,
    workday_end_hour: int = 19,
    num_simulations: int = 10000,
) -> dict[str, object]:
    """Run the predictor, repair, and judge agents on an existing plan."""
    _check_ready(starting_location)
    logger.info(
        "[workflow] %d task(s), %d plan event(s), starting from %r",
        len(plan.tasks),
        len(plan.events),
        starting_location,
    )

    now = now or datetime.now(timezone.utc)
    day_start = day_bounds(now=now)[0]
    plan_day = day_start.date().isoformat()
    calendar_context, conditions = _collect_context(
        plan,
        starting_location,
        calendar_id,
        now,
        credentials=credentials
    )
    agent_context: AgentContext = {
        "calendar_commitments": calendar_context,
        "conditions": conditions,
        "starting_location": starting_location,
        "day_start": day_start,
        "preferred_transport_mode": preferred_transport_mode,
        "workday_start_hour": workday_start_hour,
        "workday_end_hour": workday_end_hour,
    }

    with step("predictor (original plan)"):
        original_prediction = predict_outcomes(
            plan,
            agent_context,
            num_simulations=num_simulations,
        )
    logger.info("[predictor] risk by id: %s", original_prediction["risk_by_id"])
    with step("repair agent (Gemini)"):
        proposal = propose_repair(
            plan,
            agent_context,
            original_prediction,
            plan_day,
        )
    logger.info("[repair] changes: %s", proposal.changes)
    with step("predictor (repaired plan)"):
        repaired_prediction = predict_outcomes(
            proposal.proposed_plan,
            agent_context,
            task_schedule=proposal.proposed_task_schedule,
            num_simulations=num_simulations,
        )
    logger.info("[predictor] risk by id: %s", repaired_prediction["risk_by_id"])
    with step("judge agent (Gemini)"):
        judgment = compare_timelines(
            original_prediction,
            repaired_prediction,
            proposal,
        )
    logger.info("[judge] verdict: %s", judgment["measured_verdict"])
    return {
        "calendar_commitments": calendar_context,
        "conditions": conditions,
        "original_prediction": original_prediction,
        "repair": proposal.model_dump(mode="json"),
        "repaired_prediction": repaired_prediction,
        "judge": judgment,
        "assumptions": [
            "Times are minutes since midnight (Europe/London) on tomorrow's date; tasks can be scheduled only during the configured work hours.",
            "Weather and route estimates use Oxford, UK.",
            "Wind can increase walking and cycling travel times and variability.",
            "Weather and route integrations may return fallback estimates if their data sources fail.",
            "The simulator currently models transit shocks and rain-adjusted travel; other generated disruption fields are informational only.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review a day plan with calendar, weather, and route context."
    )
    parser.add_argument("description", nargs="+", help="Describe the day and tasks")
    parser.add_argument(
        "--starting-location",
        required=True,
        help="Where the day starts, for route estimates",
    )
    parser.add_argument("--calendar-id", help="Google Calendar ID (defaults to primary)")
    args = parser.parse_args()
    result = review_day(
        " ".join(args.description),
        args.starting_location,
        args.calendar_id,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
