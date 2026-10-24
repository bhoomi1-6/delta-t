"""Coordinate calendar, weather, routing, and Gemini plan review."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import load_backend_environment
from app.agents.chaos import AgentContext, generate_disruptions
from app.agents.judge import compare_timelines
from app.agents.intake import parse_plan
from app.agents.predictor import predict_outcomes
from app.agents.repair import propose_repair
from app.agents.schemas import Plan
from app.integrations.google_calendar import get_busy_events
from app.integrations.router import get_route_durations_by_arrival
from app.integrations.weather import get_oxford_weather_forecast
from app.timeutil import day_bounds

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
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    # The simulated day is tomorrow, midnight to midnight; times in the plan
    # are minutes since that day's midnight.
    day_start, end = day_bounds(now=now)
    busy_events = get_busy_events(day_start, end, calendar_id)

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

    conditions: list[dict[str, object]] = []
    origin = starting_location
    for item in itinerary:
        start = item.start
        location = item.location
        condition: dict[str, object] = {
            "event_id": item.event_id,
            "title": item.title,
            "start": start.isoformat(),
            "source": item.source,
            "weather_location": "Oxford, UK",
            "weather": get_oxford_weather_forecast(
                start.astimezone(timezone.utc).replace(tzinfo=None)
            ),
        }
        if isinstance(location, str) and location.strip():
            condition["origin"] = origin
            condition["destination"] = location
            condition["route_minutes"] = get_route_durations_by_arrival(
                origin,
                location,
                start.astimezone(timezone.utc).replace(tzinfo=None),
            )
            origin = location
        else:
            condition["route_note"] = "No destination location was provided."
        conditions.append(condition)

    return calendar_context, conditions


def review_day(
    description: str,
    starting_location: str,
    calendar_id: str | None = None,
) -> dict[str, object]:
    """Return a proposed revision without writing to Google Calendar."""
    if not starting_location.strip():
        raise ValueError("Starting location cannot be empty.")

    load_backend_environment()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    now = datetime.now(timezone.utc)
    day_start = day_bounds(now=now)[0]
    plan = parse_plan(description, plan_day=day_start.date())
    plan_day = day_start.date().isoformat()
    calendar_context, conditions = _collect_context(
        plan,
        starting_location,
        calendar_id,
        now,
    )
    agent_context: AgentContext = {
        "calendar_commitments": calendar_context,
        "conditions": conditions,
        "starting_location": starting_location,
        "day_start": day_start,
    }

    chaos = generate_disruptions(plan, agent_context)
    original_prediction = predict_outcomes(
        plan,
        agent_context,
        chaos,
    )
    proposal = propose_repair(
        plan,
        agent_context,
        chaos.disruptions,
        original_prediction,
        plan_day,
    )
    repaired_prediction = predict_outcomes(
        proposal.proposed_plan,
        agent_context,
        chaos,
        task_schedule=proposal.proposed_task_schedule,
    )
    judgment = compare_timelines(
        original_prediction,
        repaired_prediction,
        proposal,
    )
    return {
        "calendar_commitments": calendar_context,
        "conditions": conditions,
        "chaos": chaos.model_dump(mode="json"),
        "original_prediction": original_prediction,
        "repair": proposal.model_dump(mode="json"),
        "repaired_prediction": repaired_prediction,
        "judge": judgment,
        "assumptions": [
            "All times are minutes since midnight (Europe/London) on tomorrow's date; the simulated day is always the next calendar day, midnight to midnight.",
            "Weather and route estimates use Oxford, UK.",
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
