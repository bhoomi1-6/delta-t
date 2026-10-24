import os
import requests
from typing import Dict
from datetime import datetime, timezone

DEFAULT_ROUTE_DURATIONS = {"walking": 15.0, "transit": 10.0, "cycling": 12.0}


def get_route_durations_by_arrival(origin: str, destination: str, target_arrival_time: datetime = None) -> Dict[str, float]:
    """
    Queries Google's Routes API (v2) for walking, transit, and cycling options.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return DEFAULT_ROUTE_DURATIONS.copy()

    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"
    }

    routes = {}
    modes = {"walking": "WALK", "transit": "TRANSIT", "cycling": "BICYCLE"}

    arrival_str = None
    if target_arrival_time:
        if target_arrival_time.utcoffset() is None:
            arrival_str = target_arrival_time.replace(tzinfo=timezone.utc).isoformat()
        else:
            arrival_str = target_arrival_time.isoformat()
        if arrival_str.endswith("+00:00"):
            arrival_str = arrival_str[:-6] + "Z"

    for mode_name, google_mode in modes.items():
        payload = {
            "origin": {"address": f"{origin}, Oxford, UK"},
            "destination": {"address": f"{destination}, Oxford, UK"},
            "travelMode": google_mode
        }
        
        # Inject arrival time constraint (primarily active for TRANSIT mode)
        if arrival_str and google_mode == "TRANSIT":
            payload["arrivalTime"] = arrival_str

        try:
            response = requests.post(url, json=payload, headers=headers)
            data = response.json()

            if response.status_code == 200 and "routes" in data and len(data["routes"]) > 0:
                duration_str = data["routes"][0].get("duration", "900s")
                routes[mode_name] = float(duration_str.rstrip("s")) / 60.0
            else:
                routes[mode_name] = DEFAULT_ROUTE_DURATIONS[mode_name]
                
        except Exception as e:
            routes[mode_name] = DEFAULT_ROUTE_DURATIONS[mode_name]

    return routes