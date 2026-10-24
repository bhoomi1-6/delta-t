import weather
import router
import simulation
from simulation import CalendarEvent, Task
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def main():
    print("Initializing Delta-t Stochastic Simulation Engine...")

    oxford_timezone = ZoneInfo("Europe/London")
    simulation_base_date = datetime(2026, 10, 24, 8, tzinfo=oxford_timezone)

    # 1. Define dummy calendar events (sorted or unsorted—the engine handles chronological order)
    mock_events = [
        CalendarEvent(
            title="Linear Algebra Lecture", 
            start=simulation_base_date.replace(hour=9),
            end=simulation_base_date.replace(hour=10),
            location="Mathematical Institute"
        ),
        CalendarEvent(
            title="College Tutorial / Supervision", 
            start=simulation_base_date.replace(hour=12),
            end=simulation_base_date.replace(hour=13),
            location="St. Catherine's College"
        ),
        CalendarEvent(
            title="Lab Practical", 
            start=simulation_base_date.replace(hour=14),
            end=simulation_base_date.replace(hour=17),
            location="Department of Computer Science"
        )
    ]

    print("\n[API] Pre-fetching baseline route durations from Google Maps...")
    route_cache = {}
    weather_cache = {}

    
    
    # Assuming user starts from "Home" for the first event, then moves between event locations
    currentLocation = "St. Catherine's College"  # Starting point for the first event
    for event in mock_events:
        route_key = f"{currentLocation}_to_{event.location}"

        event_start_datetime = event.start
    
        
        print(f"Fetching route: {route_key}...")
        route_cache[route_key] = router.get_route_durations_by_arrival(
            origin=currentLocation, 
            destination=event.location, 
            target_arrival_time=event_start_datetime
        )
        print(f"Route durations: {route_cache[route_key]}")

        weather_data = weather.get_oxford_weather_forecast(event_start_datetime)
        weather_cache[event.title] = weather_data["precipitation_probability"] / 100.0  # e.g., 0.70

        currentLocation = event.location  # Next event originates from the current event's location

    # 2. Define dummy tasks with completion states, priorities, and hard deadlines
    mock_tasks = [
        Task(
            title="Problem Sheet 4 (Maths)",
            estimated_total_mins=420,
            completion_pct=15.0,
            deadline=(simulation_base_date + timedelta(days=1)).replace(hour=16),
            priority=0,
        ),
        Task(
            title="CS Practical Writeup",
            estimated_total_mins=600,
            completion_pct=50.0,
            deadline=(simulation_base_date + timedelta(days=2)).replace(hour=17),
            priority=1,
        ),
        Task(
            title="Long-term Research Project",
            estimated_total_mins=4800,
            completion_pct=0.0,
            deadline=(simulation_base_date + timedelta(days=30)).replace(hour=17),
            priority=2,
        ),
    ]

    # 4. Test scenario: Simulate normal day conditions
    print("\n--- Running Simulation [ Test Scenario: Nominal Conditions ] ---")
    results_normal = simulation.simulate(
        simulation_base_date=simulation_base_date,
        events=mock_events, 
        tasks=mock_tasks, 
        transit_shock_active=False, 
        num_simulations=10000,
        route_cache=route_cache,  # Use pre-fetched route durations for efficiency
        weather_cache=weather_cache  # Use pre-fetched weather data for efficiency
    )
    
    print_results_report(results_normal)

def print_results_report(results: dict):
    print(f"Transit Capacity Shock Flagged: {results['transit_shock_flagged']}")
    
    print("\nMeeting Failure Risks (% of universes missed):")
    if not results["meeting_failure_probabilities"]:
        print(" - None (All meetings reached successfully)")
    else:
        for meeting, prob in results["meeting_failure_probabilities"].items():
            print(f" - {meeting}: {prob:.1f}% risk")
        
    print("\nTask Deadline Failure Risks (% of universes missed):")
    if not results["task_failure_probabilities"]:
        print(" - None (All tasks completed on time across all universes)")
    else:
        for task_name, prob in results["task_failure_probabilities"].items():
            print(f" - {task_name}: {prob:.1f}% risk")

    print("\nTasks unfinished at the simulation horizon:")
    if not results["task_unfinished_probabilities"]:
        print(" - None")
    else:
        for task_name, prob in results["task_unfinished_probabilities"].items():
            print(f" - {task_name}: {prob:.1f}% of universes")
    print("-" * 50)

if __name__ == "__main__":
    main()