"""API tests with FastAPI's TestClient against the real January data (spec 11.3)."""

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)


def get(path: str, **params) -> dict:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def assert_422(path: str, **params) -> dict:
    response = client.get(path, params=params)
    assert response.status_code == 422, response.text
    return response.json()


# ----------------------------------------------------------- happy paths


def test_health():
    assert get("/api/health") == {"status": "ok"}


def test_meta():
    body = get("/api/meta")
    assert body["min_date"] == "2026-01-01"
    assert body["max_date"] == "2026-01-31"
    assert body["default_cutoff"] == "09:00"
    assert body["cutoff_options"] == [f"{h:02d}:00" for h in range(6, 13)]
    assert body["timezone"] == "UTC"
    assert body["data_notes"]


def test_decision_forecast_golden_example():
    body = get("/api/decision-forecast", delivery_date="2026-01-03")
    assert body["cutoff"] == "09:00"
    assert body["cutoff_datetime"] == "2026-01-02T09:00:00Z"
    assert body["publish_times"] == ["2026-01-02T07:30:00Z"]
    assert body["horizon_min_h"] == 16.5
    assert body["horizon_max_h"] == 39.5
    assert body["n_missing"] == 0
    points = body["points"]
    assert len(points) == 24
    first = points[0]
    assert first["target_time"] == "2026-01-03T00:00:00Z"
    assert first["forecast_mw"] == 18711
    assert first["publish_time"] == "2026-01-02T07:30:00Z"
    assert first["horizon_h"] == 16.5
    assert first["missing"] is False
    assert first["error_mw"] == pytest.approx(first["forecast_mw"] - first["actual_mw"])
    # The buffer comes from the whole of January at the same cutoff.
    assert body["buffer_90_mw"] == pytest.approx(4300.15)
    assert body["buffer_basis"]["n"] == 744
    assert body["day_mae_mw"] == pytest.approx(2102, abs=1)


def test_decision_forecast_other_cutoff():
    body = get("/api/decision-forecast", delivery_date="2026-01-03", cutoff="10:00")
    assert body["publish_times"] == ["2026-01-02T09:30:00Z"]


def test_series_range_and_default():
    body = get("/api/series", **{"from": "2026-01-01", "to": "2026-01-02"})
    assert len(body["points"]) == 48
    assert body["points"][0]["target_time"] == "2026-01-01T00:00:00Z"
    assert len(get("/api/series")["points"]) == 744


def test_metrics_default_range():
    body = get("/api/metrics")
    assert body["date_from"] == "2026-01-01"
    assert body["date_to"] == "2026-01-31"
    assert body["overall"]["n"] == 744
    assert body["overall"]["mae"] == pytest.approx(2142.12, abs=0.01)
    assert body["overall"]["buffer_90"] == pytest.approx(4300.15)
    assert len(body["by_hour"]) == 24
    assert [w["level"] for w in body["by_wind_level"]] == ["low", "medium", "high"]
    assert (
        body["wind_thresholds"]["low_max_mw"] < body["wind_thresholds"]["medium_max_mw"]
    )
    assert len(body["by_day"]) == 31
    assert body["by_day"][0]["delivery_date"] == "2026-01-01"
    assert body["data_quality"] == {
        "n_hours": 744,
        "n_pairs": 744,
        "n_missing_forecast": 0,
        "n_missing_actual": 0,
    }
    assert body["baseline"]["n"] == 744
    assert any("small sample" in f for f in body["findings"])


def test_metrics_short_range():
    body = get("/api/metrics", **{"from": "2026-01-03", "to": "2026-01-03"})
    assert body["overall"]["n"] == 24
    assert len(body["by_day"]) == 1


def test_error_by_horizon():
    body = get("/api/error-by-horizon")
    buckets = [b["bucket"] for b in body["buckets"]]
    assert buckets == ["0-6h", "6-12h", "12-24h", "24-36h", "36-48h", "48h+"]
    assert all(b["n"] > 0 for b in body["buckets"])


def test_cutoff_sensitivity():
    body = get("/api/cutoff-sensitivity")
    assert [r["cutoff"] for r in body["rows"]] == [f"{h:02d}:00" for h in range(6, 13)]
    assert all(r["n"] == 744 for r in body["rows"])


def test_docs_and_openapi_render():
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/decision-forecast" in schema["paths"]


# ------------------------------------------------------- validation (422)


def test_decision_forecast_requires_delivery_date():
    assert_422("/api/decision-forecast")


@pytest.mark.parametrize("day", ["2025-12-31", "2026-02-01"])
def test_decision_forecast_date_out_of_range(day):
    body = assert_422("/api/decision-forecast", delivery_date=day)
    assert "2026-01-01" in body["detail"] and "2026-01-31" in body["detail"]


@pytest.mark.parametrize("cutoff", ["9am", "25:00", "09:60", "9:00", ""])
def test_malformed_cutoff(cutoff):
    assert_422("/api/decision-forecast", delivery_date="2026-01-03", cutoff=cutoff)


def test_malformed_date():
    assert_422("/api/decision-forecast", delivery_date="03/01/2026")


@pytest.mark.parametrize(
    "path",
    ["/api/series", "/api/metrics", "/api/error-by-horizon", "/api/cutoff-sensitivity"],
)
def test_range_endpoints_reject_out_of_range_dates(path):
    assert_422(path, **{"from": "2025-12-01"})
    assert_422(path, **{"to": "2026-02-02"})


@pytest.mark.parametrize("path", ["/api/series", "/api/metrics"])
def test_range_endpoints_reject_reversed_range(path):
    body = assert_422(path, **{"from": "2026-01-10", "to": "2026-01-05"})
    assert "from" in body["detail"]


# ------------------------------------------------ improvement pass (F-items)


@pytest.mark.parametrize("cutoff", ["13:00", "09:30", "05:00"])
def test_cutoff_must_be_one_of_the_listed_options(cutoff):
    body = assert_422(
        "/api/decision-forecast", delivery_date="2026-01-03", cutoff=cutoff
    )
    assert "06:00" in body["detail"] and "12:00" in body["detail"]


def test_decision_forecast_includes_january_bias():
    body = get("/api/decision-forecast", delivery_date="2026-01-03")
    assert body["bias_mw"] == pytest.approx(1851.9, abs=0.1)


def test_metrics_include_confidence_ranges():
    body = get("/api/metrics")
    ci = body["overall_ci"]
    assert ci["level"] == 0.9
    for key in ("mae", "bias", "buffer_90"):
        low, high = ci[key]
        assert low <= body["overall"][key] <= high


def test_responses_are_gzipped_when_accepted():
    response = client.get("/api/series", headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"


def test_security_headers_on_api():
    headers = client.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in headers["content-security-policy"]


def test_docs_page_has_no_csp_so_swagger_can_load():
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.skipif(
    not (config.STATIC_DIR / "assets").is_dir(), reason="front end not built"
)
def test_static_cache_headers():
    asset = next((config.STATIC_DIR / "assets").iterdir()).name
    assert "immutable" in client.get(f"/assets/{asset}").headers["cache-control"]
    assert client.get("/").headers["cache-control"] == "no-cache"


# ------------------------------------------------------------- extras


def test_metrics_include_look_ahead_comparison():
    look = get("/api/metrics")["look_ahead"]
    assert look["at_cutoff"]["n"] == 744
    assert look["latest_before_delivery"]["n"] == 744
    # Peeking at later forecasts makes the error look smaller.
    assert look["latest_before_delivery"]["mae"] < look["at_cutoff"]["mae"]
    assert (
        look["latest_before_delivery"]["median_horizon_h"]
        < look["at_cutoff"]["median_horizon_h"]
    )


def test_metrics_include_rolling_buffer_backtest():
    rolling = get("/api/metrics")["rolling_buffer"]
    assert rolling["target_pct"] == 90
    assert 0 <= rolling["coverage_pct"] <= 100
    # 1 Jan has only one complete earlier day (30 Dec), so 30 days are evaluated.
    assert rolling["n_days"] == 30
    assert len(rolling["days"]) == 31
    assert rolling["days"][0]["buffer_mw"] is None


def test_decision_forecast_includes_rolling_buffer():
    assert (
        get("/api/decision-forecast", delivery_date="2026-01-01")[
            "rolling_buffer_90_mw"
        ]
        is None
    )
    value = get("/api/decision-forecast", delivery_date="2026-01-15")[
        "rolling_buffer_90_mw"
    ]
    assert value is not None and value >= 0
