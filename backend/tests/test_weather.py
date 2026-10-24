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
