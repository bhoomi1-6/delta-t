from datetime import datetime

import pytest

from backend.app.integrations import router


def test_route_durations_include_cycling_and_arrival_time_for_transit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, object]] = []

    class Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"routes": [{"duration": "600s"}]}

    def post(url: str, *, json: dict[str, object], headers: dict[str, str]) -> Response:
        requests.append(json)
        return Response()

    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    monkeypatch.setattr(router.requests, "post", post)
    arrival = datetime(2026, 10, 24, 9)

    durations = router.get_route_durations_by_arrival("Home", "Work", arrival)

    assert durations == {"walking": 10.0, "transit": 10.0, "cycling": 10.0}
    assert [request["travelMode"] for request in requests] == [
        "WALK",
        "TRANSIT",
        "BICYCLE",
    ]
    assert "arrivalTime" not in requests[0]
    assert requests[1]["arrivalTime"] == arrival.isoformat() + "Z"
    assert "arrivalTime" not in requests[2]


def test_route_durations_without_api_key_include_cycling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    assert router.get_route_durations_by_arrival("Home", "Work") == {
        "walking": 15.0,
        "transit": 10.0,
        "cycling": 12.0,
    }


def test_route_durations_are_cached_for_repeated_itinerary_legs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router._ROUTE_CACHE.clear()
    calls: list[tuple[str, str, datetime | None]] = []

    def fetch(
        origin: str,
        destination: str,
        target_arrival_time: datetime | None,
    ) -> dict[str, float]:
        calls.append((origin, destination, target_arrival_time))
        return {"walking": 10.0, "transit": 15.0, "cycling": 8.0}

    monkeypatch.setattr(router, "_fetch_route_durations_by_arrival", fetch)
    arrival = datetime(2026, 10, 25, 10)

    first = router.get_route_durations_by_arrival("Home", "Work", arrival)
    second = router.get_route_durations_by_arrival("Home", "Work", arrival)
    first["walking"] = 999.0

    assert len(calls) == 1
    assert second["walking"] == 10.0
