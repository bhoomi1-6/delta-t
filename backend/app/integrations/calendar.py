"""Read busy events from Google Calendar for use as schedule constraints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]
DEFAULT_CREDENTIALS_FILE = "google-calendar-credentials.json"
DEFAULT_TOKEN_FILE = "google-calendar-token.json"


@dataclass(frozen=True)
class CalendarBusyEvent:
    """A calendar event that blocks the schedule."""

    event_id: str
    summary: str
    start: datetime
    end: datetime
    all_day: bool


def _credentials() -> Credentials:
    credentials_path = Path(
        os.environ.get("GOOGLE_CALENDAR_CREDENTIALS_FILE", DEFAULT_CREDENTIALS_FILE)
    )
    token_path = Path(
        os.environ.get("GOOGLE_CALENDAR_TOKEN_FILE", DEFAULT_TOKEN_FILE)
    )

    credentials: Credentials | None = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if credentials is not None and credentials.valid:
        return credentials

    if credentials is not None and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    else:
        if not credentials_path.is_file():
            raise FileNotFoundError(
                f"Google OAuth client credentials not found: {credentials_path}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path), SCOPES
        )
        credentials = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    token_path.chmod(0o600)
    return credentials


def _service() -> Resource:
    return build("calendar", "v3", credentials=_credentials(), cache_discovery=False)


def _parse_event_time(
    value: dict[str, Any], calendar_timezone: str
) -> tuple[datetime, bool]:
    if "dateTime" in value:
        event_time = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if event_time.tzinfo is None:
            event_time = event_time.replace(
                tzinfo=ZoneInfo(value.get("timeZone", calendar_timezone))
            )
        return event_time, False

    if "date" in value:
        event_date = date.fromisoformat(value["date"])
        return datetime.combine(
            event_date, time.min, tzinfo=ZoneInfo(calendar_timezone)
        ), True

    raise ValueError("Google Calendar event is missing a valid start or end time")


def _to_busy_event(
    event: dict[str, Any], calendar_timezone: str
) -> CalendarBusyEvent | None:
    if event.get("status") == "cancelled" or event.get("transparency") == "transparent":
        return None

    start, start_all_day = _parse_event_time(event["start"], calendar_timezone)
    end, end_all_day = _parse_event_time(event["end"], calendar_timezone)
    if start >= end:
        raise ValueError(
            f"Google Calendar event {event.get('id', '<unknown>')} "
            "has an invalid time range"
        )

    return CalendarBusyEvent(
        event_id=event["id"],
        summary=event.get("summary", "(untitled event)"),
        start=start,
        end=end,
        all_day=start_all_day and end_all_day,
    )


def get_busy_events(
    start: datetime,
    end: datetime,
    calendar_id: str | None = None,
) -> list[CalendarBusyEvent]:
    """Fetch opaque events overlapping the given timezone-aware time range.

    The first call starts Google's local OAuth consent flow unless a valid
    token already exists. Set ``GOOGLE_CALENDAR_CREDENTIALS_FILE`` and
    ``GOOGLE_CALENDAR_TOKEN_FILE`` to override the default file paths.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware datetimes")
    if start >= end:
        raise ValueError("start must be earlier than end")

    selected_calendar = calendar_id or os.environ.get(
        "GOOGLE_CALENDAR_ID", "primary"
    )
    service = _service()
    calendar = service.calendarList().get(calendarId=selected_calendar).execute()
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
            busy_event = _to_busy_event(event, calendar_timezone)
            if busy_event is not None:
                events.append(busy_event)

        page_token = response.get("nextPageToken")
        if page_token is None:
            break

    return events
