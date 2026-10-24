from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.agents import orchestrator
from app.agents.schemas import Plan
from app.integrations.google_calendar import CalendarBusyEvent
from app.models import Event


def test_collect_context_enriches_calendar_and_plan_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 10, 24, 8, tzinfo=ZoneInfo("Europe/London"))
    calendar_event = CalendarBusyEvent(
        event_id="calendar-1",
        summary="Lecture",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        all_day=False,
        location="Lecture Hall",
    )
    monkeypatch.setattr(
        orchestrator,
        "get_busy_events",
        lambda start, end, calendar_id: [calendar_event],
    )
    monkeypatch.setattr(
        orchestrator,
        "get_oxford_weather_forecast",
        lambda at: {
            "precipitation_probability": 70.0,
            "precipitation_mm": 1.2,
        },
    )
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
    )

    assert [item["title"] for item in calendar] == ["Lecture"]
    assert [item["title"] for item in conditions] == ["Lecture", "Project meeting"]
    assert routes == [("Home", "Lecture Hall"), ("Lecture Hall", "Department")]
    assert conditions[0]["weather"] == {
        "precipitation_probability": 70.0,
        "precipitation_mm": 1.2,
    }


def test_review_day_returns_review_without_changing_calendar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeModels:
        def generate_content(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(
                text=(
                    '{"proposed_plan":{"events":[],"tasks":[]},"proposed_task_schedule":[],'
                    '"reasoning":"Keep the meeting fixed.","changes":[],"warnings":[]}'
                )
            )

    class FakeClient:
        models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        orchestrator,
        "parse_plan",
        lambda *_args, **_kwargs: Plan(events=[], tasks=[]),
    )
    monkeypatch.setattr(
        orchestrator,
        "_collect_context",
        lambda *args: ([{"id": "fixed-1"}], [{"event_id": "fixed-1"}]),
    )
    monkeypatch.setattr(
        orchestrator,
        "compare_timelines",
        lambda *_: {"measured_verdict": "unchanged"},
    )
    monkeypatch.setattr(orchestrator.genai, "Client", lambda **_: FakeClient())

    result = orchestrator.review_day("Plan my day", "Home")

    assert result["calendar_commitments"] == [{"id": "fixed-1"}]
    assert result["repair"]["reasoning"] == "Keep the meeting fixed."
    assert result["repair"]["proposed_plan"] == {"events": [], "tasks": []}
    assert result["judge"] == {"measured_verdict": "unchanged"}
