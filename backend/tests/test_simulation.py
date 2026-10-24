from datetime import datetime, timezone

import pytest

from backend.app.integrations import simulation
from backend.app.integrations.simulation import Task


@pytest.mark.parametrize(
    ("estimated_minutes", "deadline", "expected_failure"),
    [
        (670, datetime(2026, 10, 24, 21), 100.0),
        (680, datetime(2026, 10, 25, 10), 0.0),
    ],
)
def test_tasks_pause_at_seven_and_resume_on_following_day(
    monkeypatch: pytest.MonkeyPatch,
    estimated_minutes: float,
    deadline: datetime,
    expected_failure: float,
) -> None:
    monkeypatch.setattr(simulation.np.random, "rand", lambda: 1.0)
    base_date = datetime(2026, 10, 24, 8)
    task = Task(
        id="write-up",
        title="Write-up",
        estimated_length=estimated_minutes,
        completion_pct=0,
        deadline=deadline,
        priority=0,
    )

    result = simulation.simulate(
        simulation_base_date=base_date,
        events=[],
        tasks=[task],
        transit_shock_active=False,
        num_simulations=1,
    )

    assert result["task_failure_probabilities"].get("Write-up", 0.0) == expected_failure


def test_simulation_requires_matching_datetime_timezone_awareness() -> None:
    base_date = datetime(2026, 10, 24, 8)
    task = Task(
        id="write-up",
        title="Write-up",
        estimated_length=60,
        completion_pct=0,
        deadline=datetime(2026, 10, 24, 17, tzinfo=timezone.utc),
        priority=0,
    )

    with pytest.raises(ValueError, match="timezone-aware or naive"):
        simulation.simulate(
            simulation_base_date=base_date,
            events=[],
            tasks=[task],
            transit_shock_active=False,
            num_simulations=1,
        )
