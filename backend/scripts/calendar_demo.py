"""Fetch tomorrow's Google Calendar events as models.Event.

Times are minutes since local midnight (Europe/London).

Run from backend/:  python -m scripts.calendar_demo
"""
from app.integrations.google_calendar import get_day


if __name__ == "__main__":
    start, end, events = get_day()

    print(f"Window: {start.isoformat()} -> {end.isoformat()}")
    print(f"{len(events)} event(s)")
    for event in events:
        hh, mm = divmod(event.start_time, 60)
        print(f"{hh:02d}:{mm:02d}  {event.title}  ({event.duration.mode:.0f} min)")
        print(event.model_dump_json(indent=2))
