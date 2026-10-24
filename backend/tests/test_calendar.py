from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.integrations import calendar as calendar_integration
from app.integrations.calendar import _to_busy_event, get_busy_events


def test_to_busy_event_parses_timed_and_all_day_events() -> None:
    timed_event = _to_busy_event(
        {
            "id": "meeting",
            "summary": "Planning",
            "start": {"dateTime": "2026-10-24T09:00:00+01:00"},
            "end": {"dateTime": "2026-10-24T10:00:00+01:00"},
        },
        "Europe/London",
    )
    all_day_event = _to_busy_event(
        {
            "id": "holiday",
            "start": {"date": "2026-10-25"},
            "end": {"date": "2026-10-26"},
        },
        "Europe/London",
    )

    assert timed_event is not None
    assert timed_event.summary == "Planning"
    assert timed_event.start == datetime.fromisoformat("2026-10-24T09:00:00+01:00")
    assert timed_event.all_day is False
    assert all_day_event is not None
    assert all_day_event.start == datetime(
        2026, 10, 25, tzinfo=ZoneInfo("Europe/London")
    )
    assert all_day_event.end == datetime(
        2026, 10, 26, tzinfo=ZoneInfo("Europe/London")
    )
    assert all_day_event.all_day is True


@pytest.mark.parametrize(
    "event",
    [
        {"id": "cancelled", "status": "cancelled"},
        {"id": "free", "transparency": "transparent"},
    ],
)
def test_to_busy_event_excludes_cancelled_and_transparent_events(
    event: dict[str, str],
) -> None:
    assert _to_busy_event(event, "UTC") is None


def test_get_busy_events_requires_aware_ordered_range() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        get_busy_events(datetime(2026, 10, 24), datetime(2026, 10, 25))

    with pytest.raises(ValueError, match="earlier"):
        get_busy_events(
            datetime(2026, 10, 25, tzinfo=ZoneInfo("UTC")),
            datetime(2026, 10, 24, tzinfo=ZoneInfo("UTC")),
        )


def test_get_busy_events_reads_all_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    class Request:
        def __init__(self, response: dict[str, object]) -> None:
            self.response = response

        def execute(self) -> dict[str, object]:
            return self.response

    class CalendarList:
        def get(self, **_: str) -> Request:
            return Request({"timeZone": "Europe/London"})

    class Events:
        def __init__(self) -> None:
            self.page_tokens: list[str | None] = []

        def list(self, **kwargs: object) -> Request:
            page_token = kwargs["pageToken"]
            assert page_token is None or isinstance(page_token, str)
            self.page_tokens.append(page_token)
            if page_token is None:
                return Request(
                    {
                        "items": [
                            {
                                "id": "first",
                                "start": {"dateTime": "2026-10-24T09:00:00Z"},
                                "end": {"dateTime": "2026-10-24T10:00:00Z"},
                            }
                        ],
                        "nextPageToken": "next",
                    }
                )
            return Request(
                {
                    "items": [
                        {
                            "id": "second",
                            "start": {"date": "2026-10-25"},
                            "end": {"date": "2026-10-26"},
                        }
                    ]
                }
            )

    class Service:
        def __init__(self) -> None:
            self.event_api = Events()

        def calendarList(self) -> CalendarList:
            return CalendarList()

        def events(self) -> Events:
            return self.event_api

    service = Service()
    monkeypatch.setattr(calendar_integration, "_service", lambda: service)

    events = get_busy_events(
        datetime(2026, 10, 24, tzinfo=ZoneInfo("UTC")),
        datetime(2026, 10, 26, tzinfo=ZoneInfo("UTC")),
    )

    assert [event.event_id for event in events] == ["first", "second"]
    assert service.event_api.page_tokens == [None, "next"]
