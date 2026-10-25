
"""Read Google Calendar events as constraints for a 24-hour simulation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from dotenv import load_dotenv

from app.models import Event
from app.timeutil import LOCAL_TIMEZONE, day_bounds


# ============================================================
# Configuration
# ============================================================

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = Path(__file__).resolve().parent / ".env"

load_dotenv(ENV_FILE)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]

DEFAULT_CREDENTIALS_FILE = "google-calendar-credentials.json"


# ============================================================
# Event Models
# ============================================================

@dataclass(frozen=True)
class CalendarBusyEvent:
    """A Google Calendar event that blocks the schedule."""

    event_id: str
    summary: str
    start: datetime
    end: datetime
    all_day: bool
    location: str | None = None


# ============================================================
# Google OAuth Authentication
# ============================================================

def _configured_path(variable: str, default: str) -> Path:
    path = Path(os.environ.get(variable, default)).expanduser()

    if not path.is_absolute():
        path = BACKEND_DIR / path

    return path


def _service(credentials: Credentials) -> Resource:
    """Use credentials already associated with the current browser session."""
    if credentials is None:
        raise ValueError("Google Calendar credentials are required")
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


# ============================================================
# Google Calendar Event Parsing
# ============================================================

def _parse_event_time(
    value: dict[str, Any],
    calendar_timezone: str,
) -> tuple[datetime, bool]:
    """Parse a Google Calendar date or datetime."""

    if "dateTime" in value:
        event_time = datetime.fromisoformat(
            value["dateTime"].replace("Z", "+00:00")
        )

        if event_time.tzinfo is None:
            event_time = event_time.replace(
                tzinfo=ZoneInfo(
                    value.get("timeZone", calendar_timezone)
                )
            )

        return event_time, False

    if "date" in value:
        event_date = date.fromisoformat(value["date"])

        return datetime.combine(
            event_date,
            time.min,
            tzinfo=ZoneInfo(calendar_timezone),
        ), True

    raise ValueError(
        "Google Calendar event is missing "
        "a valid start or end time"
    )


def _to_busy_event(
    event: dict[str, Any],
    calendar_timezone: str,
) -> CalendarBusyEvent | None:
    """Convert a Google Calendar event into a busy event."""

    # Ignore cancelled events and events marked as free.
    if (
        event.get("status") == "cancelled"
        or event.get("transparency") == "transparent"
    ):
        return None

    start, start_all_day = _parse_event_time(
        event["start"],
        calendar_timezone,
    )

    end, end_all_day = _parse_event_time(
        event["end"],
        calendar_timezone,
    )

    if start >= end:
        raise ValueError(
            f"Google Calendar event "
            f"{event.get('id', '<unknown>')} "
            "has an invalid time range"
        )

    return CalendarBusyEvent(
        event_id=event["id"],
        summary=event.get(
            "summary",
            "(untitled event)",
        ),
        start=start,
        end=end,
        all_day=start_all_day and end_all_day,
        location=event.get("location"),
    )


# ============================================================
# Fetch Google Calendar Events
# ============================================================

def get_busy_events(
    start: datetime,
    end: datetime,
    calendar_id: str | None = None,
    *,
    credentials: Credentials,
) -> list[CalendarBusyEvent]:
    """Fetch events using the current user's connected Google account."""

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError(
            "start and end must be timezone-aware datetimes"
        )

    if start >= end:
        raise ValueError(
            "start must be earlier than end"
        )

    selected_calendar = (
        calendar_id
        or os.environ.get("GOOGLE_CALENDAR_ID", "primary")
    )

    service = _service(credentials)

    calendar = (
        service.calendarList()
        .get(calendarId=selected_calendar)
        .execute()
    )

    calendar_timezone = calendar["timeZone"]

    events: list[CalendarBusyEvent] = []
    page_token: str | None = None

    while True:
        response = (
            service.events()
            .list(
                calendarId=selected_calendar,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                showDeleted=False,
                pageToken=page_token,
            )
            .execute()
        )

        for event in response.get("items", []):
            busy_event = _to_busy_event(
                event,
                calendar_timezone,
            )

            if busy_event is not None:
                events.append(busy_event)

        page_token = response.get("nextPageToken")

        if page_token is None:
            break

    return events


# ============================================================
# Convert Calendar Events to Simulation Events
# ============================================================

def _to_simulation_event(
    event: CalendarBusyEvent,
    simulation_start: datetime,
    simulation_end: datetime,
) -> Event | None:
    """Convert a calendar event into a simulation Event.

    Calendar events are treated as fixed commitments.

    Event timestamps are converted to the local simulation timezone.

    Events overlapping the simulation window are clipped
    to it.
    """

    # Convert all times to UTC for consistent arithmetic.
    event_start = event.start.astimezone(timezone.utc)
    event_end = event.end.astimezone(timezone.utc)

    # Clip to simulation window.
    effective_start = max(
        event_start,
        simulation_start,
    )

    effective_end = min(
        event_end,
        simulation_end,
    )

    # Ignore events outside the simulation window.
    if effective_start >= effective_end:
        return None

    return Event(
        id=event.event_id,
        title=event.summary,
        kind="fixed",
        std=0,
        start_time=effective_start.astimezone(LOCAL_TIMEZONE),
        end_time=effective_end.astimezone(LOCAL_TIMEZONE),
        location=event.location,
    )


# ============================================================
# Midnight-to-Midnight Simulation Day
# ============================================================

def get_day(
    day: date | None = None,
    calendar_id: str | None = None,
    *,
    credentials: Credentials,
) -> tuple[datetime, datetime, list[Event]]:
    """Get simulation events for one local day, midnight to midnight.

    Event start_time and end_time values are local, timezone-aware datetimes.

    Args:
        day: Day to load. Defaults to tomorrow in LOCAL_TIMEZONE,
            so running at 15:00 on the 24th loads the 25th.
        calendar_id: Calendar to read. Defaults to GOOGLE_CALENDAR_ID.

    Returns:
        simulation_start: Midnight at the start of the day, tz-aware.
        simulation_end: The next local midnight.
        events: Calendar events converted into Event objects.
    """

    day_start, simulation_end = day_bounds(day)
    simulation_start = day_start

    # Fetch Google Calendar events.
    busy_events = get_busy_events(
        start=simulation_start,
        end=simulation_end,
        calendar_id=calendar_id,
        credentials=credentials,
    )

    simulation_events: list[Event] = []

    for busy_event in busy_events:
        simulation_event = _to_simulation_event(
            event=busy_event,
            simulation_start=simulation_start,
            simulation_end=simulation_end,
        )

        if simulation_event is not None:
            simulation_events.append(
                simulation_event
            )

    # Sort events chronologically.
    simulation_events.sort(key=lambda event: event.start_time)

    return (
        simulation_start,
        simulation_end,
        simulation_events,
    )


# Call from your authenticated FastAPI prediction endpoint:
# credentials = get_calendar_credentials(request)
# simulation_start, simulation_end, events = get_day(credentials=credentials)
