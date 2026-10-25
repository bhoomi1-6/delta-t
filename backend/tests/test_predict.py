from fastapi import Request

from backend.app import predict as predict_module


def test_predict_delegates_calendar_loading_to_review_workflow(
    monkeypatch,
) -> None:
    credentials = object()
    received = {}

    monkeypatch.setattr(
        predict_module,
        "get_calendar_credentials",
        lambda request: credentials,
    )

    def fake_review_plan(
        plan,
        starting_location,
        credentials=None,
        preferred_transport_mode="fastest",
        workday_start_hour=8,
        workday_end_hour=19,
    ):
        received["plan"] = plan
        received["starting_location"] = starting_location
        received["credentials"] = credentials
        received["preferred_transport_mode"] = preferred_transport_mode
        received["workday_start_hour"] = workday_start_hour
        received["workday_end_hour"] = workday_end_hour
        return {"judge": {"measured_verdict": "unchanged"}}

    monkeypatch.setattr(predict_module, "review_plan", fake_review_plan)
    payload = predict_module.PredictRequest(
        tasks=[
            predict_module.FrontendTask(
                id="shops",
                name="Go to shops",
                deadline="2026-10-25",
                priority="high",
                canBeDivided=False,
                estimatedLength=60,
            )
        ],
        startingLocation="Home",
        preferredTransportMode="cycling",
        workdayStartHour=7,
        workdayEndHour=18,
    )

    result = predict_module.predict(payload, Request({"type": "http", "headers": []}))

    assert received["plan"].events == []
    assert received["plan"].tasks[0].can_be_divided is False
    assert received["starting_location"] == "Home"
    assert received["credentials"] is credentials
    assert received["preferred_transport_mode"] == "cycling"
    assert received["workday_start_hour"] == 7
    assert received["workday_end_hour"] == 18
    assert result.review == {"judge": {"measured_verdict": "unchanged"}}
