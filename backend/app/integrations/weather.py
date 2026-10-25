from __future__ import annotations

from datetime import date, datetime, timezone
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo

import requests

from app.steplog import logger

LOCAL_TIMEZONE = ZoneInfo("Europe/London")
WEATHER_CACHE_TTL_SECONDS = 60 * 60
_WEATHER_CACHE: dict[date, tuple[float, dict[str, dict[str, float]]]] = {}
_WEATHER_CACHE_LOCK = Lock()


def _fetch_daily_forecast(day: date) -> dict[str, dict[str, float]]:
    with _WEATHER_CACHE_LOCK:
        cached = _WEATHER_CACHE.get(day)
        if cached and cached[0] > monotonic():
            return cached[1]

    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": 51.7522,
            "longitude": -1.2560,
            "hourly": (
                "precipitation_probability,precipitation,rain,wind_speed_10m"
            ),
            "timezone": LOCAL_TIMEZONE.key,
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
        },
        timeout=10,
    )
    response.raise_for_status()
    hourly = response.json().get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError("Open-Meteo response did not contain hourly forecasts.")

    times = hourly.get("time")
    fields = {
        "precipitation_probability": hourly.get("precipitation_probability"),
        "precipitation_mm": hourly.get("precipitation"),
        "rain_mm": hourly.get("rain"),
        "wind_speed_kmh": hourly.get("wind_speed_10m"),
    }
    if not isinstance(times, list) or any(
        not isinstance(values, list) or len(values) != len(times)
        for values in fields.values()
    ):
        raise ValueError("Open-Meteo returned incomplete hourly forecast data.")

    forecast = {
        timestamp: {
            field_name: float(values[index] or 0.0)
            for field_name, values in fields.items()
        }
        for index, timestamp in enumerate(times)
    }
    for item in forecast.values():
        item["forecast_available"] = 1.0
    with _WEATHER_CACHE_LOCK:
        _WEATHER_CACHE[day] = (monotonic() + WEATHER_CACHE_TTL_SECONDS, forecast)
    return forecast


def _local_datetime(target: datetime) -> datetime:
    if target.utcoffset() is None:
        target = target.replace(tzinfo=timezone.utc)
    return target.astimezone(LOCAL_TIMEZONE)


def get_oxford_weather_forecasts(
    target_datetimes: list[datetime],
) -> list[dict[str, float]]:
    """Fetch/cache one hourly forecast per local date for all requested times."""
    forecasts_by_day: dict[date, dict[str, dict[str, float]]] = {}
    local_targets = [_local_datetime(target) for target in target_datetimes]

    results: list[dict[str, float]] = []
    for local_target in local_targets:
        day = local_target.date()
        if day not in forecasts_by_day:
            try:
                forecasts_by_day[day] = _fetch_daily_forecast(day)
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                logger.warning(
                    "[weather] Open-Meteo fetch failed for %s (%s): using FALLBACK",
                    day,
                    error,
                )
                forecasts_by_day[day] = {}

        hour = local_target.replace(minute=0, second=0, microsecond=0)
        result = forecasts_by_day[day].get(hour.strftime("%Y-%m-%dT%H:%M"))
        if result is None:
            logger.warning(
                "[weather] %s is outside the Open-Meteo forecast window: using FALLBACK",
                hour.isoformat(),
            )
            result = {
                "precipitation_probability": 0.0,
                "precipitation_mm": 0.0,
                "rain_mm": 0.0,
                "wind_speed_kmh": 0.0,
                "forecast_available": 0.0,
            }
        results.append(result)
    return results


def get_oxford_weather_forecast(target_datetime: datetime) -> dict[str, float]:
    """Fetch one hourly forecast using the shared daily cache."""
    return get_oxford_weather_forecasts([target_datetime])[0]


def get_oxford_weather(target_datetime: datetime) -> dict[str, float]:
    """Compatibility alias for the Oxford weather forecast helper."""
    return get_oxford_weather_forecast(target_datetime)
