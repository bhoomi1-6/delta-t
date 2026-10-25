from datetime import datetime, timezone

import pytest

from backend.app.integrations import simulation
from backend.app.integrations.simulation import Task
from backend.app.models import Event


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
        can_be_divided=True,
    )

    result = simulation.simulate(
        simulation_base_date=base_date,
        events=[],
        tasks=[task],
        transit_shock_active=False,
        num_simulations=1,
    )

    assert result["task_failure_probabilities"].get("Write-up", 0.0) == expected_failure


def test_simulation_uses_configured_workday_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(simulation.np.random, "rand", lambda: 1.0)
    task = Task(
        id="early-task",
        title="Early task",
        estimated_length=60,
        completion_pct=0,
        deadline=datetime(2026, 10, 24, 8),
        priority=0,
        can_be_divided=True,
    )

    result = simulation.simulate(
        simulation_base_date=datetime(2026, 10, 24),
        events=[],
        tasks=[task],
        transit_shock_active=False,
        num_simulations=1,
        workday_start_hour=7,
        workday_end_hour=18,
    )

    assert result["task_failure_probabilities"].get("Early task", 0.0) == 0.0


def test_simulation_rejects_invalid_workday_hours() -> None:
    with pytest.raises(ValueError, match="after workday_start_hour"):
        simulation.simulate(
            simulation_base_date=datetime(2026, 10, 24),
            events=[],
            tasks=[],
            transit_shock_active=False,
            num_simulations=1,
            workday_start_hour=18,
            workday_end_hour=18,
        )


@pytest.mark.parametrize(
    ("can_be_divided", "estimated_length", "expected_failure"),
    [(True, 90, 0.0), (False, 90, 100.0), (False, 60, 0.0)],
)
def test_atomic_tasks_need_one_uninterrupted_work_block(
    monkeypatch: pytest.MonkeyPatch,
    can_be_divided: bool,
    estimated_length: int,
    expected_failure: float,
) -> None:
    monkeypatch.setattr(simulation.np.random, "rand", lambda: 1.0)
    base_date = datetime(2026, 10, 24, 8)
    task = Task(
        id="shop-trip",
        title="Go to shops",
        estimated_length=estimated_length,
        completion_pct=0,
        deadline=datetime(2026, 10, 24, 12),
        priority=0,
        can_be_divided=can_be_divided,
    )
    events = [
        Event(
            id=f"meeting-{hour}",
            title=f"Meeting {hour}",
            kind="fixed",
            std=0,
            start_time=base_date.replace(hour=hour),
            end_time=base_date.replace(hour=hour + 1),
        )
        for hour in (9, 11)
    ]

    result = simulation.simulate(
        simulation_base_date=base_date,
        events=events,
        tasks=[task],
        transit_shock_active=False,
        num_simulations=1,
    )

    assert result["task_failure_probabilities"].get("Go to shops", 0.0) == expected_failure


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


@pytest.mark.parametrize(
    ("preferred_transport_mode", "expected_meeting_failure"),
    [("fastest", 0.0), ("walking", 100.0)],
)
def test_wind_increases_active_travel_time_and_preference_is_respected(
    monkeypatch: pytest.MonkeyPatch,
    preferred_transport_mode: str,
    expected_meeting_failure: float,
) -> None:
    monkeypatch.setattr(simulation.np.random, "rand", lambda: 1.0)
    monkeypatch.setattr(
        simulation.np.random,
        "uniform",
        lambda *_args, **kwargs: simulation.np.zeros(kwargs["size"]),
    )
    sampled_distributions: list[tuple[float, float]] = []

    def sample_normal(mean: float, std: float) -> float:
        sampled_distributions.append((mean, std))
        return mean

    monkeypatch.setattr(simulation.np.random, "normal", sample_normal)
    base_date = datetime(2026, 10, 24, 8, 58)
    event = Event(
        id="meeting",
        title="Windy meeting",
        kind="fixed",
        std=0,
        start_time=base_date.replace(hour=9, minute=10),
        end_time=base_date.replace(hour=9, minute=30),
        location="Work",
    )

    result = simulation.simulate(
        simulation_base_date=base_date,
        events=[event],
        tasks=[],
        transit_shock_active=False,
        num_simulations=1,
        route_cache={
            "Home_to_Work": {
                "walking": 15.0,
                "transit": 1.0,
                "cycling": 2.0,
            }
        },
        weather_cache={
            "Windy meeting": {
                "precipitation_probability": 0.0,
                "wind_speed_kmh": 60.0,
            }
        },
        starting_location="Home",
        preferred_transport_mode=preferred_transport_mode,
    )

    assert (
        result["meeting_failure_probabilities"].get("Windy meeting", 0.0)
        == expected_meeting_failure
    )
    assert (17.25, 1.725) in sampled_distributions
    assert (3.0, 0.75) in sampled_distributions
