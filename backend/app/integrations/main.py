import router
import simulation
from simulation import CalendarEvent, Task
from datetime import datetime, timedelta

def main():
    print("Initializing Delta-t Stochastic Simulation Engine...")

    # 1. Define dummy calendar events (sorted or unsorted—the engine handles chronological order)
    mock_events = [
        CalendarEvent(
            title="Linear Algebra Lecture", 
            start_min=540,  # 09:00 AM
            end_min=600,    # 10:00 AM
            location="Mathematical Institute"
        ),
        CalendarEvent(
            title="College Tutorial / Supervision", 
            start_min=720,  # 12:00 PM (Creates a crucial 2-hour gap from 10:00 - 12:00)
            end_min=780,    # 1:00 PM
            location="St. Catherine's College"
        ),
        CalendarEvent(
            title="Lab Practical", 
            start_min=840,  # 2:00 PM (1-hour gap after tutorial)
            end_min=1020,   # 5:00 PM
            location="Department of Computer Science"
        )
    ]

    simulation_base_date = datetime(2026, 10, 24)

    print("\n[API] Pre-fetching baseline route durations from Google Maps...")
    route_cache = {}

    
    
    # Assuming user starts from "Home" for the first event, then moves between event locations
    currentLocation = "St. Catherine's College"  # Starting point for the first event
    for event in mock_events:
        route_key = f"{currentLocation}_to_{event.location}"

        event_start_datetime = simulation_base_date + timedelta(minutes=event.start_min)
    
        
        print(f"Fetching route: {route_key}...")
        route_cache[route_key] = router.get_route_durations_by_arrival(
            origin=currentLocation, 
            destination=event.location, 
            target_arrival_time=event_start_datetime
        )
        print(f"Route durations: {route_cache[route_key]}")
        currentLocation = event.location  # Next event originates from the current event's location

    # 2. Define dummy tasks with completion states, priorities, and hard deadlines
    mock_tasks = [
        Task(
            title="Problem Sheet 4 (Maths)", 
            estimated_total_mins=120, 
            completion_pct=15.0,  # Mostly unfinished, high urgency
            deadline_min=960,     # 4:00 PM hard deadline
            priority="high"
        ),
        Task(
            title="CS Practical Writeup", 
            estimated_total_mins=90, 
            completion_pct=50.0,  # Halfway done
            deadline_min=1140,    # 7:00 PM evening deadline
            priority="medium"
        )
    ]

    # 3. Test scenario: Simulate with an active infrastructure disruption (Transit Shock)
    print("\n--- Running Simulation [Scenario A: Transit Bottleneck Active] ---")
    results_shock = simulation.simulate(
        events=mock_events, 
        tasks=mock_tasks, 
        transit_shock_active=True, 
        num_simulations=10000,
        route_cache=route_cache  # Use pre-fetched route durations for efficiency
    )
    
    print_results_report(results_shock)

    # 4. Test scenario: Simulate normal day conditions (No transit shock)
    print("\n--- Running Simulation [Scenario B: Nominal Conditions] ---")
    results_normal = simulation.simulate(
        events=mock_events, 
        tasks=mock_tasks, 
        transit_shock_active=False, 
        num_simulations=10000,
        route_cache=route_cache  # Use pre-fetched route durations for efficiency
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
    print("-" * 50)

if __name__ == "__main__":
    main()