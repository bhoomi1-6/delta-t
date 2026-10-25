from datetime import datetime

from app.agents import predictor
from app.agents import repair
from app.agents.chaos import AgentContext, TaskScheduleItem
from app.agents import judge
from app.agents.judge import _average_failure_risk
from app.agents.repair import RepairProposal
from app.agents.schemas import Plan, PlanTask
from app.models import Event, EventKind


def test_predictor_runs_without_chaos_agent(monkeypatch) -> None:
    calls: list[bool] = []

    def fake_simulate(*args, transit_shock_active: bool, **kwargs):
        calls.append(transit_shock_active)
        return {
            "meeting_failure_probabilities": {"event:meeting-1": 10.0},
            "task_failure_probabilities": {"task:task-1": 20.0},
            "task_unfinished_probabilities": {},
        }

    monkeypatch.setattr(predictor.simulation, "simulate", fake_simulate)
    context: AgentContext = {
        "calendar_commitments": [],
        "conditions": [],
        "starting_location": "Home",
        "day_start": datetime(2026, 10, 25),
    }
    outcome = predictor.predict_outcomes(
        Plan(events=[], tasks=[]),
        context,
    )

    assert calls == [False]
    assert outcome["meeting_failure_probabilities"]["event:meeting-1"] == 10.0
    assert outcome["task_failure_probabilities"]["task:task-1"] == 20.0
    assert len(outcome["limitations"]) == 4
    assert "Disruption forecasts and transit-shock scenarios are disabled" in outcome["limitations"][0]


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


def test_predictor_reports_task_capacity_constraints_without_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        predictor.simulation,
        "simulate",
        lambda *args, **kwargs: {
            "meeting_failure_probabilities": {},
            "task_failure_probabilities": {"task:task-1": 100.0},
            "task_unfinished_probabilities": {"task:task-1": 0.0},
        },
    )
    plan = Plan(
        events=[
            Event(
                id="event-1",
                title="Lecture",
                kind=EventKind.fixed,
                std=0,
                start_time=datetime(2026, 10, 25, 10),
                end_time=datetime(2026, 10, 25, 12),
            )
        ],
        tasks=[
            PlanTask(
                id="task-1",
                title="Write report",
                estimated_length=180,
                completion_pct=0,
                can_be_divided=False,
                deadline=datetime(2026, 10, 25, 12),
                priority=1,
            )
        ],
    )
    context: AgentContext = {
        "calendar_commitments": [],
        "conditions": [],
        "starting_location": "Home",
        "day_start": datetime(2026, 10, 25),
        "workday_start_hour": 8,
        "workday_end_hour": 19,
    }

    outcome = predictor.predict_outcomes(
        plan,
        context,
        num_simulations=1,
    )

    [diagnostic] = outcome["task_diagnostics"]
    assert diagnostic["name"] == "Write report"
    assert diagnostic["failure_probability_percent"] == 100.0
    assert diagnostic["remaining_effort_minutes"] == 180.0
    assert diagnostic["available_work_minutes_before_deadline"] == 120.0
    assert diagnostic["longest_uninterrupted_work_window_minutes"] == 120.0
    assert len(diagnostic["potential_constraints"]) == 2
    assert "task-1" not in str(diagnostic)


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
        "calendar_commitments": [
            {
                "id": "calendar-call",
                "title": "Project call",
                "start": "2026-10-25T10:00:00+01:00",
                "end": "2026-10-25T11:00:00+01:00",
                "location": None,
                "description": "Tentative call; can be rescheduled if needed.",
            }
        ],
        "conditions": [],
        "starting_location": "Home",
        "day_start": datetime(2026, 10, 25),
        "preferred_transport_mode": "transit",
        "workday_start_hour": 7,
        "workday_end_hour": 21,
    }

    result = repair.propose_repair(
        original_plan,
        context,
        prediction={},
        plan_day="2026-10-25",
    )

    prompt = " ".join(prompts[0].split())
    assert len(prompts) == 2
    assert '"meeting-1"' in prompt
    assert "Starting location: Home" in prompt
    assert "Preferred transport: transit" in prompt
    assert "Workday: 07:00 to 21:00 local time" in prompt
    assert "per-run causal attribution" in prompt
    assert "task reordering can fix" in prompt
    assert "not an interactive clarification flow" in prompt
    assert "not address the user with a direct question" in prompt
    assert "Tentative call; can be rescheduled if needed." in prompt
    assert "assess its likely flexibility cautiously" in prompt
    assert "advisory, unverified, and not applied" in prompt
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
        "task_diagnostics": [
            {
                "name": "Write report",
                "failure_probability_percent": 80.0,
                "potential_constraints": ["Limited work window before deadline."],
            }
        ],
        "limitations": [],
    }

    judge.compare_timelines(prediction, prediction, proposal)

    prompt = " ".join(prompts[0].split())
    assert "Meet Alex" in prompt
    assert "Limited work window before deadline." in prompt
    assert "provides no cause, say so once" in prompt
    assert "change in percentage points" in prompt
    assert "do not repeat their issues" in prompt
    assert "do not ask" in prompt
    assert "direct question" in prompt
    assert "not applied or evaluated" in prompt
    assert "secret-event-id" not in prompt
