"""Tests for decision-time forecast selection (spec Section 11.1)."""

from datetime import date, time, timedelta

import pandas as pd

from app.decision import cutoff_datetime, select_decision_forecast

DAY = date(2026, 1, 3)
CUTOFF = time(9, 0)


def ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def forecasts(*publishes: tuple[str, range, int]) -> pd.DataFrame:
    """Build a forecast frame. Each publish is (publish_time, hours of DAY, mw)."""
    rows = [
        {
            "publish_time": ts(publish),
            "start_time": ts(f"2026-01-03T{hour:02d}:00"),
            "generation_mw": mw,
        }
        for publish, hours, mw in publishes
        for hour in hours
    ]
    return pd.DataFrame(rows, columns=["publish_time", "start_time", "generation_mw"])


ALL_DAY = range(24)


def test_cutoff_datetime_is_on_the_day_before_delivery():
    assert cutoff_datetime(DAY, CUTOFF) == ts("2026-01-02T09:00")


def test_output_has_24_hourly_rows_and_expected_columns():
    out = select_decision_forecast(
        forecasts(("2026-01-02T07:30", ALL_DAY, 1)), DAY, CUTOFF
    )
    assert list(out.columns) == [
        "target_time",
        "forecast_mw",
        "publish_time",
        "horizon_h",
        "missing",
    ]
    assert len(out) == 24
    assert out["target_time"].iloc[0] == ts("2026-01-03T00:00")
    assert out["target_time"].iloc[-1] == ts("2026-01-03T23:00")


def test_publish_after_cutoff_is_ignored_even_if_newer():
    fc = forecasts(
        ("2026-01-02T07:30", ALL_DAY, 100),
        ("2026-01-02T09:30", ALL_DAY, 999),  # newer, but after the cutoff
    )
    out = select_decision_forecast(fc, DAY, CUTOFF)
    assert (out["forecast_mw"] == 100).all()
    assert (out["publish_time"] == ts("2026-01-02T07:30")).all()


def test_latest_publish_before_cutoff_wins():
    fc = forecasts(
        ("2026-01-02T02:30", ALL_DAY, 1),
        ("2026-01-02T07:30", ALL_DAY, 3),
        ("2026-01-02T04:30", ALL_DAY, 2),  # deliberately out of order
    )
    out = select_decision_forecast(fc, DAY, CUTOFF)
    assert (out["forecast_mw"] == 3).all()


def test_publish_exactly_at_cutoff_is_included():
    fc = forecasts(
        ("2026-01-02T07:30", ALL_DAY, 1),
        ("2026-01-02T09:00", ALL_DAY, 2),
    )
    out = select_decision_forecast(fc, DAY, CUTOFF)
    assert (out["forecast_mw"] == 2).all()
    assert (out["publish_time"] == ts("2026-01-02T09:00")).all()


def test_hour_without_eligible_forecast_is_missing_not_filled_from_later():
    fc = forecasts(
        ("2026-01-02T07:30", range(0, 20), 100),
        ("2026-01-02T09:30", ALL_DAY, 999),  # would fill hours 20-23: forbidden
    )
    out = select_decision_forecast(fc, DAY, CUTOFF)
    late = out[out["target_time"] >= ts("2026-01-03T20:00")]
    assert late["missing"].all()
    assert late["forecast_mw"].isna().all()
    assert late["publish_time"].isna().all()
    assert late["horizon_h"].isna().all()
    assert not out.loc[out["target_time"] < ts("2026-01-03T20:00"), "missing"].any()


def test_selection_is_per_target_hour_across_publishes():
    # The 07:30 publish only covers the afternoon, so mornings fall back to 04:30.
    fc = forecasts(
        ("2026-01-02T04:30", ALL_DAY, 1),
        ("2026-01-02T07:30", range(12, 24), 2),
    )
    out = select_decision_forecast(fc, DAY, CUTOFF).set_index("target_time")
    assert out.loc[ts("2026-01-03T11:00"), "forecast_mw"] == 1
    assert out.loc[ts("2026-01-03T11:00"), "publish_time"] == ts("2026-01-02T04:30")
    assert out.loc[ts("2026-01-03T12:00"), "forecast_mw"] == 2
    assert out.loc[ts("2026-01-03T12:00"), "publish_time"] == ts("2026-01-02T07:30")


def test_horizon_is_hours_from_publish_to_target():
    out = select_decision_forecast(
        forecasts(("2026-01-02T07:30", ALL_DAY, 1)), DAY, CUTOFF
    )
    assert out["horizon_h"].iloc[0] == 16.5
    assert out["horizon_h"].iloc[-1] == 39.5


def test_forecasts_for_other_days_are_ignored():
    fc = forecasts(("2026-01-02T07:30", ALL_DAY, 1))
    other_day = fc.assign(start_time=fc["start_time"] + timedelta(days=1))
    out = select_decision_forecast(pd.concat([fc, other_day]), DAY, CUTOFF)
    assert len(out) == 24
    assert (out["target_time"].dt.date == DAY).all()


def test_no_forecasts_at_all_gives_24_missing_hours():
    out = select_decision_forecast(forecasts(), DAY, CUTOFF)
    assert len(out) == 24
    assert out["missing"].all()


# ------------------------------------------------- regression on real data


def test_golden_example(real_forecasts):
    out = select_decision_forecast(real_forecasts, DAY, CUTOFF)
    assert not out["missing"].any()
    assert set(out["publish_time"]) == {ts("2026-01-02T07:30")}
    assert out["horizon_h"].min() == 16.5
    assert out["horizon_h"].max() == 39.5
    # First value seen in the Phase 1 exploration.
    assert out["forecast_mw"].iloc[0] == 18711


def test_cutoff_1000_picks_the_0930_publish(real_forecasts):
    out = select_decision_forecast(real_forecasts, DAY, time(10, 0))
    assert set(out["publish_time"]) == {ts("2026-01-02T09:30")}


def test_late_publish_quirk_on_16_january(real_forecasts):
    # The 11:30 publish on 15 Jan arrived at 12:25 (docs/DATA_NOTES.md), so a
    # 12:00 cutoff must fall back to 09:30, never use the 12:25 publish.
    out = select_decision_forecast(real_forecasts, date(2026, 1, 16), time(12, 0))
    assert set(out["publish_time"]) == {ts("2026-01-15T09:30")}
