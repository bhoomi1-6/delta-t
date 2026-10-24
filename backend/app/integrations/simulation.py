import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any
from collections import Counter

# Data Structures

@dataclass
class CalendarEvent:
    title: str
    start_min: int  # minutes from midnight (e.g., 09:00 AM = 540)
    end_min: int
    location: str
    is_flexible: bool = False

@dataclass
class Task:
    title: str
    estimated_total_mins: float
    completion_pct: float
    deadline_min: int  # hard deadline in minutes from midnight
    priority: str      # priority high,medium,low

# --- 2. THE SIMULATION ENGINE ---

def simulate(
    events: List[CalendarEvent], 
    tasks: List[Task], 
    transit_shock_active: bool,
    num_simulations: int = 1000,
    route_cache: Dict[str, Dict[str, float]] = None
) -> Dict[str, Any]:
    
    meeting_failures = Counter()
    task_failures = Counter()
    
    # Sort events chronologically to ensure proper gap calculation
    sorted_events = sorted(events, key=lambda e: e.start_min)
    
    # Pre-calculate transit delay samples
    if transit_shock_active:
        transit_delay_samples = np.random.exponential(scale=15.0, size=num_simulations) + 10.0
    else:
        transit_delay_samples = np.random.uniform(0, 5, size=num_simulations)

    for run in range(num_simulations):
        current_time = 480  # Day starts at 08:00 AM (480 mins)
        
        # Track remaining work for each task in this specific universe (deep copy tracking)
        active_tasks = []
        for t in tasks:
            rem_work = t.estimated_total_mins * (1.0 - (t.completion_pct / 100.0))
            active_tasks.append({
                "title": t.title,
                "remaining_mins": rem_work,
                "deadline": t.deadline_min,
                "priority": t.priority
            })
        
        # Sort tasks by priority (high priority gets first pick of available gaps)
        priority_map = {"high": 0, "medium": 1, "low": 2}
        active_tasks.sort(key=lambda t: priority_map[t["priority"]])

        currentLocation = "St. Catherine's College"  # Starting point for the day

        # --- ITERATE THROUGH THE DAY'S CALENDAR EVENTS & GAPS ---
        for event in sorted_events:
            # 1. Evaluate Transit to the Event

            route_data = dict(route_cache.get(
                f"{currentLocation}_to_{event.location}", 
                {"walking": 15.0, "transit": 10.0}
            ))

            if "transit" in route_data:
                route_data["transit"] += transit_delay_samples[run]


            # Baseline travel duration (e.g., choosing transit baseline)
            
            optimal_transport = min(route_data, key=route_data.get)  # Choose the fastest mode
            total_commute_time = route_data[optimal_transport]

            # 2. Calculate true workable gap BEFORE the user must depart for the event
            latest_departure_time = event.start_min - total_commute_time  # Target departure under ideal conditions
            workable_gap = latest_departure_time - current_time


            if workable_gap > 15:  # If there is a meaningful window to work before leaving
                for task in active_tasks:
                    if task["remaining_mins"] <= 0:
                        continue
                    
                    # Stochastic distractions during work block
                    distraction_penalty = np.random.uniform(10, 30) if np.random.rand() < 0.3 else 0.0
                    time_allocated = min(workable_gap, task["remaining_mins"])
                    
                    progress_made = max(0.0, time_allocated - distraction_penalty)
                    task["remaining_mins"] -= progress_made
                    workable_gap -= time_allocated
                    
                    if workable_gap <= 0:
                        break

            # 3. Depart and evaluate arrival at the meeting
            # Current time advances to departure time (or stays current if running late)
            departure_time = max(current_time, latest_departure_time)
            actual_arrival = departure_time + total_commute_time

            # Check for late arrival
            if actual_arrival > event.start_min + 5:  # 5 min grace period
                meeting_failures[event.title] += 1

            # Advance current time to the conclusion of the event
            current_time = max(actual_arrival, event.start_min) + (event.end_min - event.start_min)
            currentLocation = event.location  # Update location

        # --- 3. END-OF-DAY LEFTOVER TASK SWEEP ---
        # Any remaining tasks are tackled in the evening block after the final event
        for task in active_tasks:
            if task["remaining_mins"] > 0:
                # Stochastic completion for remaining work
                final_push = np.random.triangular(
                    task["remaining_mins"] * 0.9, 
                    task["remaining_mins"], 
                    task["remaining_mins"] * 1.5 if isinstance(task["remaining_mins"], float) else task["remaining_mins"] * 1.3
                )
                current_time += final_push
                
                # Check if it missed the hard deadline
                if current_time > task["deadline"]:
                    task_failures[task["title"]] += 1

    # --- 4. COMPILE PROBABILISTIC INSIGHTS ---
    return {
        "transit_shock_flagged": transit_shock_active,
        "meeting_failure_probabilities": {title: (count / num_simulations) * 100 for title, count in meeting_failures.items()},
        "task_failure_probabilities": {title: (count / num_simulations) * 100 for title, count in task_failures.items()}
    }

# --- TEST EXECUTION ---
if __name__ == "__main__":
    mock_events = [
        CalendarEvent(title="Morning Lecture", start_min=540, end_min=600, location="Lecture Hall"),       # 09:00 - 10:00
        CalendarEvent(title="Afternoon Supervision", start_min=720, end_min=780, location="College")       # 12:00 - 13:00 (2h gap prior!)
    ]
    
    mock_tasks = [
        Task(title="Problem Sheet 3", estimated_total_mins=90, completion_pct=10.0, deadline_min=900, priority="high") # 3:00 PM deadline
    ]

    results = simulate(mock_events, mock_tasks, transit_shock_active=True, num_simulations=1000)
    print("=== DELTA-T SIMULATION RESULTS ===", results)