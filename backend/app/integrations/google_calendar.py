
"""Read Google Calendar events as constraints for a 24-hour simulation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from dotenv import load_dotenv

from app.models import Event, TriangularDist


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
DEFAULT_TOKEN_FILE = "google-calendar-token.json"

SIMULATION_HOURS = 24


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


def _credentials() -> Credentials:
    credentials_path = _configured_path(
        "GOOGLE_CALENDAR_CREDENTIALS_FILE",
        DEFAULT_CREDENTIALS_FILE,
    )

    token_path = _configured_path(
        "GOOGLE_CALENDAR_TOKEN_FILE",
        DEFAULT_TOKEN_FILE,
    )

    credentials: Credentials | None = None

    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_path),
            SCOPES,
        )

    if credentials is not None and credentials.valid:
        return credentials

    if (
        credentials is not None
        and credentials.expired
        and credentials.refresh_token
    ):
        credentials.refresh(Request())

    else:
        if not credentials_path.is_file():
            raise FileNotFoundError(
                "Google OAuth client credentials not found: "
                f"{credentials_path}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path),
            SCOPES,
        )

        credentials = flow.run_local_server(port=0)

    token_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    token_path.write_text(
        credentials.to_json(),
        encoding="utf-8",
    )

    token_path.chmod(0o600)

    return credentials


def _service() -> Resource:
    return build(
        "calendar",
        "v3",
        credentials=_credentials(),
        cache_discovery=False,
    )


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
) -> list[CalendarBusyEvent]:
    """Fetch busy events overlapping a timezone-aware time range.

    The first call starts Google's local OAuth consent flow
    unless a valid token already exists.

    Environment variables:
        GOOGLE_CALENDAR_CREDENTIALS_FILE
        GOOGLE_CALENDAR_TOKEN_FILE
        GOOGLE_CALENDAR_ID
    """

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

    service = _service()

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

    Start times are integer minutes relative to the
    simulation start.

    Events overlapping the simulation boundaries are
    clipped to the 24-hour simulation window.
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

    # Duration in minutes.
    duration_minutes = (
        effective_end - effective_start
    ).total_seconds() / 60

    # Minutes from the beginning of the simulation.
    start_offset = int(
        (
            effective_start - simulation_start
        ).total_seconds() // 60
    )

    return Event(
        id=event.event_id,
        title=event.summary,
        kind="fixed",
        duration=TriangularDist(
            min=duration_minutes,
            mode=duration_minutes,
            max=duration_minutes,
        ),
        start_time=start_offset,
        location=event.location,
    )


# ============================================================
# Rolling 24-Hour Simulation
# ============================================================

def get_next_24_hours(
    calendar_id: str | None = None,
) -> tuple[datetime, datetime, list[Event]]:
    """Get simulation events for the next 24 hours from now.

    Event start_time values are minutes from simulation_start.

    Returns:
        simulation_start: Current UTC datetime.
        simulation_end: Exactly 24 hours after start.
        events: Calendar events converted into Event objects.
    """

    # Always use the current time.
    simulation_start = datetime.now(timezone.utc)

    # Exactly 24 hours later.
    simulation_end = (
        simulation_start
        + timedelta(hours=SIMULATION_HOURS)
    )

    # Fetch Google Calendar events.
    busy_events = get_busy_events(
        start=simulation_start,
        end=simulation_end,
        calendar_id=calendar_id,
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
    simulation_events.sort(
        key=lambda event: (
            event.start_time
            if event.start_time is not None
            else float("inf")
        )
    )

    return (
        simulation_start,
        simulation_end,
        simulation_events,
    )


# ============================================================
# Example Usage
# ============================================================

if __name__ == "__main__":

    simulation_start, simulation_end, events = (
        get_next_24_hours()
    )

    print(
        "Simulation start:",
        simulation_start.isoformat(),
    )

    print(
        "Simulation end:",
        simulation_end.isoformat(),
    )

    print(
        "Number of events:",
        len(events),
    )

    for event in events:
        print(event)
