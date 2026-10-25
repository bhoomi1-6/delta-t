from datetime import datetime

from app.integrations import weather


def test_legacy_weather_name_delegates_to_forecast(monkeypatch) -> None:
    target = datetime(2026, 10, 25, 14)
    expected = {"precipitation_probability": 70.0, "precipitation_mm": 1.2}
    calls: list[datetime] = []

    def fake_forecast(value: datetime) -> dict[str, float]:
        calls.append(value)
        return expected

    monkeypatch.setattr(weather, "get_oxford_weather_forecast", fake_forecast)

    assert weather.get_oxford_weather(target) == expected
    assert calls == [target]


def test_weather_batch_fetches_each_local_day_once_and_returns_wind(
    monkeypatch,
) -> None:
    weather._WEATHER_CACHE.clear()
    requests: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "hourly": {
                    "time": [
                        "2026-10-25T10:00",
                        "2026-10-25T11:00",
                    ],
                    "precipitation_probability": [20, 40],
                    "precipitation": [0.0, 0.2],
                    "rain": [0.0, 0.1],
                    "wind_speed_10m": [12, 38],
                }
            }

    def get(url: str, *, params: dict[str, object], timeout: int) -> Response:
        requests.append(params)
        return Response()

    monkeypatch.setattr(weather.requests, "get", get)
    targets = [
        datetime(2026, 10, 25, 10, 15),
        datetime(2026, 10, 25, 11, 45),
    ]

    result = weather.get_oxford_weather_forecasts(targets)

    assert len(requests) == 1
    assert requests[0]["hourly"] == (
        "precipitation_probability,precipitation,rain,wind_speed_10m"
    )
    assert [item["wind_speed_kmh"] for item in result] == [12.0, 38.0]
    assert [item["precipitation_probability"] for item in result] == [20.0, 40.0]

    weather.get_oxford_weather_forecasts(targets)
    assert len(requests) == 1
