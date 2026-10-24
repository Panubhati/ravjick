"""Tests for app/metrics.py on small, hand-computed examples (spec Section 11.2)."""

from datetime import date, time

import numpy as np
import pandas as pd
import pytest

from app.metrics import (
    baseline_comparison,
    bias,
    bootstrap_ci,
    build_pairs,
    by_day,
    by_hour,
    by_wind_level,
    cutoff_sensitivity,
    error_by_horizon,
    headline_findings,
    look_ahead_comparison,
    mae,
    overall_metrics,
    rmse,
    rolling_buffer_backtest,
    run_analysis,
    shortfall_buffer,
)


def ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def pairs_frame(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """rows = (target_time, forecast_mw, actual_mw); NaN forecast = missing."""
    df = pd.DataFrame(rows, columns=["target_time", "forecast_mw", "actual_mw"])
    df["target_time"] = pd.to_datetime(df["target_time"], utc=True)
    df["missing"] = df["forecast_mw"].isna()
    df["error_mw"] = df["forecast_mw"] - df["actual_mw"]
    return df


def day_forecasts(publish: str, day: str, mw: float) -> list[dict]:
    return [
        {
            "publish_time": ts(publish),
            "start_time": ts(f"{day}T{h:02d}:00"),
            "generation_mw": mw,
        }
        for h in range(24)
    ]


def day_actuals(day: str, mw: float) -> list[dict]:
    return [
        {"target_time": ts(f"{day}T{h:02d}:00"), "actual_mw": mw} for h in range(24)
    ]


ERRORS = pd.Series([100.0, -50.0, 200.0, -250.0])


# ---------------------------------------------------------------- helpers


def test_mae_rmse_bias_match_hand_calculation():
    assert mae(ERRORS) == 150
    assert rmse(ERRORS) == pytest.approx(
        np.sqrt((100**2 + 50**2 + 200**2 + 250**2) / 4)
    )
    assert bias(ERRORS) == 0


def test_shortfall_buffer_is_the_upper_quantile_of_signed_error():
    # Sorted: -250, -50, 100, 200. Linear quantile 0.9 -> 100 + 0.7 * 100.
    assert shortfall_buffer(ERRORS, 0.90) == pytest.approx(170)


def test_shortfall_buffer_is_never_negative():
    # Wind always came in above forecast: no shortfall, so no buffer needed.
    assert shortfall_buffer(pd.Series([-10.0, -20.0, -30.0]), 0.90) == 0


def test_sign_convention_forecast_above_actual_is_positive():
    pairs = pairs_frame([("2026-01-03T00:00", 120, 100)])
    assert pairs["error_mw"].iloc[0] == 20


# ---------------------------------------------------------------- overall


def test_overall_metrics_hand_calculated():
    pairs = pairs_frame(
        [
            ("2026-01-03T00:00", 1100, 1000),
            ("2026-01-03T01:00", 950, 1000),
            ("2026-01-03T02:00", 1200, 1000),
            ("2026-01-03T03:00", 750, 1000),
            ("2026-01-03T04:00", np.nan, 1000),  # missing forecast
            ("2026-01-03T05:00", 500, np.nan),  # missing actual
        ]
    )
    m = overall_metrics(pairs)
    assert m["n"] == 4
    assert m["n_missing_forecast"] == 1
    assert m["n_missing_actual"] == 1
    assert m["mae"] == 150
    assert m["bias"] == 0
    assert m["nmae_pct"] == pytest.approx(15.0)
    assert m["mean_actual_mw"] == 1000
    # |e| sorted 50, 100, 200, 250
    assert m["abs_p50"] == pytest.approx(150)
    assert m["abs_p90"] == pytest.approx(235)
    assert m["abs_p95"] == pytest.approx(242.5)
    # e sorted -250, -50, 100, 200
    assert m["signed_p5"] == pytest.approx(-220)
    assert m["signed_p50"] == pytest.approx(25)
    assert m["signed_p95"] == pytest.approx(185)
    assert m["buffer_90"] == pytest.approx(170)
    assert m["buffer_95"] == pytest.approx(185)


def test_overall_metrics_with_no_matched_pairs_returns_none_values():
    m = overall_metrics(pairs_frame([("2026-01-03T00:00", np.nan, 1000)]))
    assert m["n"] == 0
    assert m["n_missing_forecast"] == 1
    assert m["mae"] is None
    assert m["buffer_90"] is None


# ----------------------------------------------------------------- slices


def test_by_hour_groups_on_hour_of_day_and_lists_all_24():
    pairs = pairs_frame(
        [
            ("2026-01-03T05:00", 110, 100),
            ("2026-01-04T05:00", 70, 100),
            ("2026-01-03T06:00", 100, 100),
        ]
    )
    out = by_hour(pairs).set_index("hour")
    assert len(out) == 24
    assert out.loc[5, "mae"] == 20
    assert out.loc[5, "bias"] == -10
    assert out.loc[5, "n"] == 2
    assert out.loc[6, "mae"] == 0
    assert out.loc[0, "n"] == 0


def test_by_wind_level_uses_terciles_of_actual():
    actuals = [100, 200, 300, 400, 500, 600]
    errors = [10, -10, 20, 20, -30, -50]
    pairs = pairs_frame(
        [
            (f"2026-01-03T{i:02d}:00", a + e, a)
            for i, (a, e) in enumerate(zip(actuals, errors, strict=True))
        ]
    )
    levels, thresholds = by_wind_level(pairs)
    assert thresholds["low_max_mw"] == pytest.approx(266.667, abs=1e-3)
    assert thresholds["medium_max_mw"] == pytest.approx(433.333, abs=1e-3)
    out = levels.set_index("level")
    assert out.index.tolist() == ["low", "medium", "high"]
    assert out.loc["low", "mae"] == 10 and out.loc["low", "bias"] == 0
    assert out.loc["medium", "mae"] == 20 and out.loc["medium", "bias"] == 20
    assert out.loc["high", "mae"] == 40 and out.loc["high", "bias"] == -40
    assert out["n"].tolist() == [2, 2, 2]


def test_by_day():
    pairs = pairs_frame(
        [
            ("2026-01-03T00:00", 110, 100),
            ("2026-01-03T01:00", 130, 100),
            ("2026-01-04T00:00", 50, 100),
        ]
    )
    out = by_day(pairs).set_index("delivery_date")
    assert out.loc[date(2026, 1, 3), "mae"] == 20
    assert out.loc[date(2026, 1, 3), "bias"] == 20
    assert out.loc[date(2026, 1, 4), "bias"] == -50
    assert out.loc[date(2026, 1, 4), "n"] == 1


# --------------------------------------------------- pairs and cutoffs


def test_build_pairs_joins_decision_forecast_to_hourly_actuals():
    fc = pd.DataFrame(day_forecasts("2026-01-02T07:30", "2026-01-03", 1000))
    hourly = pd.DataFrame(day_actuals("2026-01-03", 900))
    hourly = hourly[hourly["target_time"] != ts("2026-01-03T05:00")]
    pairs = build_pairs(fc, hourly, date(2026, 1, 3), date(2026, 1, 4), time(9, 0))
    assert len(pairs) == 48  # two delivery days, 24 hours each
    day3 = pairs[pairs["target_time"].dt.date == date(2026, 1, 3)]
    assert (day3["error_mw"].dropna() == 100).all()
    assert day3["actual_mw"].isna().sum() == 1  # 05:00
    day4 = pairs[pairs["target_time"].dt.date == date(2026, 1, 4)]
    assert day4["missing"].all()  # no forecast for 4 Jan


def test_cutoff_sensitivity_recomputes_per_cutoff():
    fc = pd.DataFrame(
        day_forecasts("2026-01-02T04:30", "2026-01-03", 1200)
        + day_forecasts("2026-01-02T09:30", "2026-01-03", 1050)
    )
    hourly = pd.DataFrame(day_actuals("2026-01-03", 1000))
    out = cutoff_sensitivity(
        fc, hourly, date(2026, 1, 3), date(2026, 1, 3), [time(9, 0), time(10, 0)]
    ).set_index("cutoff")
    assert out.loc["09:00", "mae"] == 200
    assert out.loc["09:00", "buffer_90"] == 200
    assert out.loc["10:00", "mae"] == 50
    assert out.loc["10:00", "bias"] == 50
    assert out.loc["10:00", "n"] == 24


# ---------------------------------------------------------------- horizon


def test_error_by_horizon_buckets_all_positive_horizon_rows():
    target = "2026-01-03T12:00"
    rows = [
        ("2026-01-03T06:00", 1100),  # 6h   -> 0-6h (right-closed)
        ("2026-01-03T05:00", 900),  # 7h   -> 6-12h
        ("2026-01-02T00:00", 1300),  # 36h  -> 24-36h
        ("2026-01-01T10:00", 800),  # 50h  -> 48h+
        ("2026-01-03T12:00", 5000),  # 0h   -> excluded
        ("2026-01-03T13:00", 5000),  # -1h  -> excluded
    ]
    fc = pd.DataFrame(
        [
            {"publish_time": ts(p), "start_time": ts(target), "generation_mw": g}
            for p, g in rows
        ]
        # Target outside the date range: excluded.
        + [
            {
                "publish_time": ts("2026-01-04T00:00"),
                "start_time": ts("2026-01-05T00:00"),
                "generation_mw": 9999,
            }
        ]
    )
    hourly = pd.DataFrame(
        [
            {"target_time": ts(target), "actual_mw": 1000},
            {"target_time": ts("2026-01-05T00:00"), "actual_mw": 1000},
        ]
    )
    out = error_by_horizon(fc, hourly, date(2026, 1, 3), date(2026, 1, 3))
    out = out.set_index("bucket")
    assert out.index.tolist() == ["0-6h", "6-12h", "12-24h", "24-36h", "36-48h", "48h+"]
    assert out["n"].tolist() == [1, 1, 0, 1, 0, 1]
    assert out.loc["0-6h", "bias"] == 100
    assert out.loc["6-12h", "bias"] == -100
    assert out.loc["24-36h", "mae"] == 300
    assert out.loc["48h+", "bias"] == -200
    assert pd.isna(out.loc["12-24h", "mae"])


# --------------------------------------------------------------- baseline


def test_baseline_uses_actual_two_days_earlier_on_the_same_hours():
    pairs = pairs_frame(
        [(f"2026-01-03T{h:02d}:00", 1100, 1000) for h in range(24)]
        + [("2026-01-04T00:00", 1100, 1000)]  # no D-2 actual: excluded
    )
    hourly = pd.DataFrame(
        day_actuals("2026-01-01", 800) + day_actuals("2026-01-03", 1000)
    )
    out = baseline_comparison(pairs, hourly)
    assert out["n"] == 24
    assert out["forecast_mae"] == 100
    assert out["baseline_mae"] == 200


# --------------------------------------------------------------- findings


def test_run_analysis_and_findings_on_synthetic_month():
    fc = pd.DataFrame(
        day_forecasts("2026-01-02T07:30", "2026-01-03", 1100)
        + day_forecasts("2026-01-03T07:30", "2026-01-04", 1100)
    )
    hourly = pd.DataFrame(
        day_actuals("2026-01-01", 900)
        + day_actuals("2026-01-02", 900)
        + day_actuals("2026-01-03", 1000)
        + day_actuals("2026-01-04", 1000)
    )
    results = run_analysis(fc, hourly, date(2026, 1, 3), date(2026, 1, 4), time(9, 0))
    assert results["overall"]["n"] == 48
    assert results["overall"]["buffer_90"] == pytest.approx(100)
    findings = headline_findings(results)
    assert findings and all(isinstance(f, str) for f in findings)
    text = " ".join(findings)
    assert "100 MW" in text  # MAE and buffer both 100 MW
    assert "2 delivery days" in text
    assert "small sample" in text


# ------------------------------------------------- bootstrap confidence ranges


def test_bootstrap_ci_is_zero_width_when_every_day_is_identical():
    errors = [100.0, -50.0, 200.0, -250.0]
    pairs = pairs_frame(
        [
            (f"2026-01-0{d}T{h:02d}:00", 1000 + e, 1000)
            for d in (3, 4, 5)
            for h, e in enumerate(errors)
        ]
    )
    ci = bootstrap_ci(pairs)
    assert ci["mae"] == pytest.approx([150, 150])
    assert ci["bias"] == pytest.approx([0, 0])
    # 12 errors (4 values x 3 days): the 90th percentile is 200.
    buffer = overall_metrics(pairs)["buffer_90"]
    assert buffer == 200
    assert ci["buffer_90"] == pytest.approx([buffer, buffer])


def test_bootstrap_ci_is_reproducible_with_a_seed():
    pairs = pairs_frame(
        [
            (f"2026-01-{d:02d}T00:00", 1000 + 37 * d * (-1) ** d, 1000)
            for d in range(1, 21)
        ]
    )
    assert bootstrap_ci(pairs, seed=1) == bootstrap_ci(pairs, seed=1)
    low, high = bootstrap_ci(pairs, seed=1)["mae"]
    assert low < high


def test_bootstrap_ci_none_without_matched_pairs():
    assert bootstrap_ci(pairs_frame([("2026-01-03T00:00", np.nan, 1000)])) is None


def test_bootstrap_ci_contains_point_estimates_on_real_data(real_forecasts):
    from app.data_loader import load_hourly_actuals

    pairs = build_pairs(
        real_forecasts,
        load_hourly_actuals(),
        date(2026, 1, 1),
        date(2026, 1, 31),
        time(9, 0),
    )
    overall = overall_metrics(pairs)
    ci = bootstrap_ci(pairs)
    for key in ("mae", "bias", "buffer_90"):
        low, high = ci[key]
        assert low <= overall[key] <= high


# ------------------------------------------- look-ahead (peeking) comparison


def test_look_ahead_comparison_uses_newer_forecasts_only_on_the_cheating_side():
    target = "2026-01-03T12:00"
    fc = pd.DataFrame(
        [
            # Available at the 09:00 cutoff on 2 Jan.
            {
                "publish_time": ts("2026-01-02T07:30"),
                "start_time": ts(target),
                "generation_mw": 1200,
            },
            # Published later, but before delivery: a buyer could not have used it.
            {
                "publish_time": ts("2026-01-03T10:00"),
                "start_time": ts(target),
                "generation_mw": 1050,
            },
            # Published after the hour began: never counts as a forecast.
            {
                "publish_time": ts("2026-01-03T13:00"),
                "start_time": ts(target),
                "generation_mw": 1000,
            },
        ]
    )
    hourly = pd.DataFrame([{"target_time": ts(target), "actual_mw": 1000}])
    pairs = build_pairs(fc, hourly, date(2026, 1, 3), date(2026, 1, 3), time(9, 0))
    out = look_ahead_comparison(pairs, fc, hourly, date(2026, 1, 3), date(2026, 1, 3))
    assert out["at_cutoff"]["mae"] == 200
    assert out["at_cutoff"]["median_horizon_h"] == 28.5
    assert out["latest_before_delivery"]["mae"] == 50
    assert out["latest_before_delivery"]["bias"] == 50
    assert out["latest_before_delivery"]["median_horizon_h"] == 2
    assert out["latest_before_delivery"]["n"] == 1


# --------------------------------------- shortfall buffer without hindsight


def one_hour_per_day(errors: dict[str, float]) -> pd.DataFrame:
    return pairs_frame([(f"{day}T12:00", 1000 + e, 1000) for day, e in errors.items()])


def test_rolling_buffer_uses_only_days_known_at_the_cutoff():
    pairs = one_hour_per_day(
        {
            "2026-01-01": 100,
            "2026-01-02": 200,
            "2026-01-03": 300,
            "2026-01-04": 50,
            "2026-01-05": 400,
        }
    )
    days, summary = rolling_buffer_backtest(
        pairs, date(2026, 1, 1), date(2026, 1, 5), min_history_days=2
    )
    by_day = days.set_index("delivery_date")
    # 1-3 Jan: fewer than 2 complete earlier days (D-2 or before) -> no buffer.
    assert by_day.loc[date(2026, 1, 3), "buffer_mw"] is None or pd.isna(
        by_day.loc[date(2026, 1, 3), "buffer_mw"]
    )
    # 4 Jan: history = 1-2 Jan [100, 200] -> 90th percentile 190; error 50 covered.
    assert by_day.loc[date(2026, 1, 4), "buffer_mw"] == pytest.approx(190)
    assert by_day.loc[date(2026, 1, 4), "covered_hours"] == 1
    # 5 Jan: history = 1-3 Jan [100, 200, 300] -> 280; error 400 not covered.
    assert by_day.loc[date(2026, 1, 5), "buffer_mw"] == pytest.approx(280)
    assert by_day.loc[date(2026, 1, 5), "covered_hours"] == 0
    assert summary["n_days"] == 2
    assert summary["coverage_pct"] == 50
    assert summary["mean_buffer_mw"] == pytest.approx(235)


def test_rolling_buffer_ignores_the_future():
    base = {"2026-01-01": 100, "2026-01-02": 200, "2026-01-03": 300}
    a, _ = rolling_buffer_backtest(
        one_hour_per_day(base), date(2026, 1, 3), date(2026, 1, 3), 1
    )
    b, _ = rolling_buffer_backtest(
        one_hour_per_day(base | {"2026-01-04": 99999}),
        date(2026, 1, 3),
        date(2026, 1, 3),
        1,
    )
    assert a["buffer_mw"].tolist() == b["buffer_mw"].tolist()


def test_rolling_buffer_is_never_negative():
    pairs = one_hour_per_day(
        {"2026-01-01": -100, "2026-01-02": -200, "2026-01-03": -50}
    )
    days, _ = rolling_buffer_backtest(pairs, date(2026, 1, 3), date(2026, 1, 3), 1)
    assert days["buffer_mw"].tolist() == [0]
