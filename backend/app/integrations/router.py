import os
import requests
from threading import Lock
from time import monotonic
from typing import Dict
from datetime import datetime, timezone

from app.steplog import logger

DEFAULT_ROUTE_DURATIONS = {"walking": 15.0, "transit": 10.0, "cycling": 12.0}
ROUTE_CACHE_TTL_SECONDS = 15 * 60
_ROUTE_CACHE: dict[
    tuple[str, str, str | None], tuple[float, Dict[str, float]]
] = {}
_ROUTE_CACHE_LOCK = Lock()


def _fetch_route_durations_by_arrival(
    origin: str,
    destination: str,
    target_arrival_time: datetime | None,
) -> Dict[str, float]:
    """
    Queries Google's Routes API (v2) for walking, transit, and cycling options.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logger.warning(
            "[routes] GOOGLE_MAPS_API_KEY is not set: using FALLBACK durations %s",
            DEFAULT_ROUTE_DURATIONS,
        )
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
                logger.warning(
                    "[routes] %s lookup returned HTTP %s (%s): using fallback %.0f min",
                    mode_name,
                    response.status_code,
                    data.get("error", {}).get("message", "no routes found"),
                    DEFAULT_ROUTE_DURATIONS[mode_name],
                )
                routes[mode_name] = DEFAULT_ROUTE_DURATIONS[mode_name]

        except Exception as e:
            logger.warning(
                "[routes] %s lookup failed (%s): using fallback %.0f min",
                mode_name,
                e,
                DEFAULT_ROUTE_DURATIONS[mode_name],
            )
            routes[mode_name] = DEFAULT_ROUTE_DURATIONS[mode_name]

    return routes


def get_route_durations_by_arrival(
    origin: str,
    destination: str,
    target_arrival_time: datetime | None = None,
) -> Dict[str, float]:
    """Return cached route estimates for repeated itinerary legs."""
    arrival_key = (
        target_arrival_time.isoformat() if target_arrival_time is not None else None
    )
    key = (origin.strip().casefold(), destination.strip().casefold(), arrival_key)
    now = monotonic()
    with _ROUTE_CACHE_LOCK:
        cached = _ROUTE_CACHE.get(key)
        if cached and cached[0] > now:
            return cached[1].copy()

    routes = _fetch_route_durations_by_arrival(
        origin,
        destination,
        target_arrival_time,
    )
    with _ROUTE_CACHE_LOCK:
        _ROUTE_CACHE[key] = (now + ROUTE_CACHE_TTL_SECONDS, routes.copy())
    return routes