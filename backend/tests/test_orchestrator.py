from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.agents import orchestrator
from app.agents.schemas import Plan
from app.integrations.google_calendar import CalendarBusyEvent, _to_busy_event
from app.models import Event


def test_calendar_event_parsing_preserves_description() -> None:
    event = _to_busy_event(
        {
            "id": "calendar-call",
            "summary": "Project call",
            "description": "Tentative; reschedule if needed.",
            "start": {"dateTime": "2026-10-25T10:00:00+01:00"},
            "end": {"dateTime": "2026-10-25T11:00:00+01:00"},
        },
        "Europe/London",
    )

    assert event is not None
    assert event.description == "Tentative; reschedule if needed."


def test_collect_context_enriches_calendar_and_plan_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 10, 24, 8, tzinfo=ZoneInfo("Europe/London"))
    calendar_event = CalendarBusyEvent(
        event_id="calendar-1",
        summary="Lecture",
        start=now + timedelta(days=1, hours=1),
        end=now + timedelta(days=1, hours=2),
        all_day=False,
        location="Lecture Hall",
        description="Weekly in-person lecture.",
    )
    monkeypatch.setattr(
        orchestrator,
        "get_busy_events",
        lambda start, end, calendar_id, **kwargs: [calendar_event],
    )
    weather_calls: list[list[datetime]] = []

    def get_weather(targets: list[datetime]) -> list[dict[str, float]]:
        weather_calls.append(targets)
        return [
            {
                "precipitation_probability": 70.0,
                "precipitation_mm": 1.2,
                "rain_mm": 0.8,
                "wind_speed_kmh": 35.0,
            }
            for _ in targets
        ]

    monkeypatch.setattr(orchestrator, "get_oxford_weather_forecasts", get_weather)
    routes: list[tuple[str, str]] = []

    def get_routes(origin: str, destination: str, arrival: datetime) -> dict[str, float]:
        routes.append((origin, destination))
        return {"walking": 20.0}

    monkeypatch.setattr(orchestrator, "get_route_durations_by_arrival", get_routes)
    plan = Plan(
        events=[
            Event(
                id="meeting-1",
                title="Project meeting",
                kind="fixed",
                std=0,
                start_time=(now + timedelta(days=1)).replace(hour=10, minute=0),
                end_time=(now + timedelta(days=1)).replace(hour=10, minute=30),
                location="Department",
            )
        ],
        tasks=[],
    )

    calendar, conditions = orchestrator._collect_context(
        plan,
        "Home",
        None,
        now.astimezone(ZoneInfo("UTC")),
        credentials=None,
    )

    assert [item["title"] for item in calendar] == ["Lecture"]
    assert calendar[0]["description"] == "Weekly in-person lecture."
    assert [item["title"] for item in conditions] == ["Lecture", "Project meeting"]
    assert routes == [("Home", "Lecture Hall"), ("Lecture Hall", "Department")]
    assert len(weather_calls) == 1
    assert len(weather_calls[0]) == 2
    assert conditions[0]["weather"] == {
        "precipitation_probability": 70.0,
        "precipitation_mm": 1.2,
        "rain_mm": 0.8,
        "wind_speed_kmh": 35.0,
    }


def test_review_plan_uses_requested_simulation_count_for_both_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = Plan(events=[], tasks=[])
    prediction_calls: list[int] = []
    proposal = SimpleNamespace(
        proposed_plan=plan,
        proposed_task_schedule=[],
        changes=[],
        model_dump=lambda **_kwargs: {},
    )

    monkeypatch.setattr(orchestrator, "_check_ready", lambda _location: None)
    monkeypatch.setattr(
        orchestrator,
        "_collect_context",
        lambda *_args, **_kwargs: ([], []),
    )

    def fake_predict_outcomes(*_args, num_simulations: int, **_kwargs):
        prediction_calls.append(num_simulations)
        return {"risk_by_id": {}}

    monkeypatch.setattr(orchestrator, "predict_outcomes", fake_predict_outcomes)
    monkeypatch.setattr(orchestrator, "propose_repair", lambda *_args: proposal)
    monkeypatch.setattr(
        orchestrator,
        "compare_timelines",
        lambda *_args: {"measured_verdict": "unchanged"},
    )

    orchestrator.review_plan(plan, "Home", num_simulations=2500)

    assert prediction_calls == [2500, 2500]
