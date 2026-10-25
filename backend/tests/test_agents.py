from datetime import datetime

from app.agents import predictor
from app.agents import repair
from app.agents.chaos import AgentContext, ChaosReport, TaskScheduleItem
from app.agents import judge
from app.agents.judge import _average_failure_risk
from app.agents.repair import RepairProposal
from app.agents.schemas import Plan, PlanTask
from app.models import Disruption, Event, EventKind


def test_predictor_weights_nominal_and_transit_shock_runs(monkeypatch) -> None:
    results = iter(
        [
            {
                "meeting_failure_probabilities": {"Lecture": 10.0},
                "task_failure_probabilities": {"Report": 20.0},
                "task_unfinished_probabilities": {},
            },
            {
                "meeting_failure_probabilities": {"Lecture": 50.0},
                "task_failure_probabilities": {"Report": 80.0},
                "task_unfinished_probabilities": {},
            },
        ]
    )
    calls: list[bool] = []

    def fake_simulate(*args, transit_shock_active: bool, **kwargs):
        calls.append(transit_shock_active)
        return next(results)

    monkeypatch.setattr(predictor.simulation, "simulate", fake_simulate)
    chaos = ChaosReport(
        disruptions=[
            Disruption(
                id="delay",
                title="Transit delay",
                probability=0.25,
                time_wasted=10,
                predicted_cost=1,
            )
        ],
        transit_shock_probability=0.25,
        notes=[],
    )

    outcome = predictor.predict_outcomes(
        Plan(events=[], tasks=[]),
        [],
        [],
        chaos,
        datetime(2026, 10, 25),
    )

    assert calls == [False, True]
    assert outcome["meeting_failure_probabilities"]["Lecture"] == 20.0
    assert outcome["task_failure_probabilities"]["Report"] == 35.0
    assert len(outcome["limitations"]) == 3


def test_predictor_sorts_events_by_model_start_time() -> None:
    plan = Plan(
        events=[
            Event(
                id="later",
                title="Later",
                kind=EventKind.fixed,
                std=0,
                start_time=datetime(2026, 10, 25, 10),
                end_time=datetime(2026, 10, 25, 11),
            ),
            Event(
                id="earlier",
                title="Earlier",
                kind=EventKind.fixed,
                std=0,
                start_time=datetime(2026, 10, 25, 9),
                end_time=datetime(2026, 10, 25, 10),
            ),
        ],
        tasks=[],
    )
    context = {
        "calendar_commitments": [],
        "conditions": [],
        "starting_location": "Home",
        "day_start": datetime(2026, 10, 25),
    }

    inputs = predictor._simulation_inputs(
        plan,
        context,
        task_schedule=None,
        day_start=datetime(2026, 10, 25),
    )

    assert [event.title for event in inputs.events] == [
        "event:earlier",
        "event:later",
    ]
    named_risks = predictor._named_risks(
        {
            "meetings": {"later": 25.0, "earlier": 10.0},
            "tasks": {},
            "unfinished_tasks": {},
        },
        inputs,
    )

    assert {risk["name"] for risk in named_risks} == {"Earlier", "Later"}
    assert all("id" not in risk for risk in named_risks)


def test_repair_retries_proposal_with_mismatched_event_ids(
    monkeypatch,
) -> None:
    original_plan = Plan(
        events=[
            Event(
                id="meeting-1",
                title="Meeting",
                kind=EventKind.fixed,
                std=0,
                start_time=datetime(2026, 10, 25, 10),
                end_time=datetime(2026, 10, 25, 11),
            )
        ],
        tasks=[
            PlanTask(
                id="report-1",
                title="Report",
                estimated_length=60,
                completion_pct=0,
                deadline=900,
                priority=1,
            )
        ],
    )
    invalid_proposal = RepairProposal(
        proposed_plan=Plan(
            events=[
                Event(
                    id="calendar-event-1",
                    title="Calendar event mistakenly included",
                    kind=EventKind.fixed,
                    std=0,
                    start_time=datetime(2026, 10, 25, 10),
                    end_time=datetime(2026, 10, 25, 11),
                )
            ],
            tasks=original_plan.tasks,
        ),
        proposed_task_schedule=[
            TaskScheduleItem(task_id="report-1", start_time=600, reasoning="Work")
        ],
        reasoning="Repair schedule",
        changes=[],
        warnings=[],
    )
    valid_proposal = invalid_proposal.model_copy(
        update={
            "proposed_plan": original_plan,
        }
    )
    responses = iter(
        [invalid_proposal.model_dump_json(), valid_proposal.model_dump_json()]
    )
    prompts: list[str] = []

    class FakeModels:
        def generate_content(self, **kwargs):
            prompts.append(str(kwargs["contents"]))
            return type("Response", (), {"text": next(responses)})()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(repair, "load_backend_environment", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(repair.genai, "Client", lambda **_: FakeClient())
    context: AgentContext = {
        "calendar_commitments": [],
        "conditions": [],
        "starting_location": "Home",
        "day_start": datetime(2026, 10, 25),
    }

    result = repair.propose_repair(
        original_plan,
        context,
        disruptions=[],
        prediction={},
        plan_day="2026-10-25",
    )

    assert len(prompts) == 2
    assert '"meeting-1"' in prompts[0]
    assert "previous proposal was rejected" in prompts[1]
    assert result.proposed_plan.events[0].id == "meeting-1"


def test_judge_average_risk_uses_all_failure_categories() -> None:
    prediction = {
        "meeting_failure_probabilities": {"Lecture": 20.0},
        "task_failure_probabilities": {"Report": 40.0},
        "task_unfinished_probabilities": {"Essay": 60.0},
    }

    assert _average_failure_risk(prediction) == 40.0


def test_judge_prompt_uses_event_names_not_internal_ids(monkeypatch) -> None:
    prompts: list[str] = []

    class FakeModels:
        def generate_content(self, **kwargs):
            prompts.append(str(kwargs["contents"]))
            return type(
                "Response",
                (),
                {
                    "text": (
                        '{"verdict":"unchanged","summary":"Meet Alex is unchanged.",'
                        '"tradeoffs":[],"remaining_risks":[]}'
                    )
                },
            )()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(judge, "load_backend_environment", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(judge.genai, "Client", lambda **_: FakeClient())
    proposal = RepairProposal(
        proposed_plan=Plan(
            events=[
                Event(
                    id="secret-event-id",
                    title="Meet Alex",
                    kind=EventKind.fixed,
                    std=0,
                    start_time=datetime(2026, 10, 25, 10),
                    end_time=datetime(2026, 10, 25, 11),
                )
            ],
            tasks=[],
        ),
        proposed_task_schedule=[],
        reasoning="Keep the meeting.",
        changes=[],
        warnings=[],
    )
    prediction = {
        "risk_by_id": {"meetings": {"secret-event-id": 25.0}, "tasks": {}, "unfinished_tasks": {}},
        "risk_by_name": [
            {
                "name": "Meet Alex",
                "category": "meetings",
                "failure_probability_percent": 25.0,
            }
        ],
        "limitations": [],
    }

    judge.compare_timelines(prediction, prediction, proposal)

    assert "Meet Alex" in prompts[0]
    assert "secret-event-id" not in prompts[0]
