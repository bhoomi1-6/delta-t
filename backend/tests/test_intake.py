from datetime import date, datetime
from types import SimpleNamespace

import pytest
from google.genai import _transformers

from app.agents import intake
from app.agents.schemas import Plan


def test_plan_schema_is_accepted_by_gemini_sdk() -> None:
    schema = _transformers.t_schema(None, Plan)

    assert schema is not None


def test_parse_plan_returns_validated_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_text = """
    {
      "events": [
        {
          "id": "meeting-1",
          "title": "Meet Alex",
          "kind": "fixed",
          "std": 5,
          "start_time": "2026-10-25T10:00:00",
          "end_time": "2026-10-25T10:45:00",
          "location": null
        }
      ],
      "tasks": [
        {
          "id": "report-1",
          "title": "Finish report",
          "estimated_length": 90,
          "completion_pct": 0,
          "can_be_divided": false,
          "deadline": "2026-10-25T15:00:00",
          "priority": 1
        }
      ]
    }
    """

    class FakeModels:
        def generate_content(self, **kwargs: object) -> SimpleNamespace:
            assert kwargs["model"] == intake.DEFAULT_MODEL
            return SimpleNamespace(text=response_text)

    class FakeClient:
        models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(intake.genai, "Client", lambda **_: FakeClient())

    plan = intake.parse_plan(
        "Meet Alex at 10 and finish a report by 3.",
        plan_day=date(2026, 10, 25),
    )

    assert plan.events[0].title == "Meet Alex"
    assert plan.events[0].std == 5
    assert plan.events[0].start_time == datetime(2026, 10, 25, 10)
    assert plan.events[0].end_time == datetime(2026, 10, 25, 10, 45)
    assert plan.tasks[0].deadline == datetime(2026, 10, 25, 15)
    assert plan.tasks[0].priority == 1


def test_parse_plan_requires_nonempty_description() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        intake.parse_plan("  ")


def test_parse_plan_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake, "load_backend_environment", lambda: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        intake.parse_plan("Work on my report.")
