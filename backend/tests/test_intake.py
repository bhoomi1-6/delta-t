from types import SimpleNamespace

import pytest

from app.agents import intake


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
          "duration": {"min": 30, "mode": 45, "max": 60},
          "start_time": 600,
          "location": null,
          "priority": 2
        }
      ],
      "tasks": [
        {
          "id": "report-1",
          "title": "Finish report",
          "estimated_length": 90,
          "can_be_divided": false,
          "deadline": 900
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

    plan = intake.parse_plan("Meet Alex at 10 and finish a report by 3.")

    assert plan.events[0].title == "Meet Alex"
    assert plan.events[0].duration.mode == 45
    assert plan.tasks[0].deadline == 900


def test_parse_plan_requires_nonempty_description() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        intake.parse_plan("  ")


def test_parse_plan_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        intake.parse_plan("Work on my report.")
