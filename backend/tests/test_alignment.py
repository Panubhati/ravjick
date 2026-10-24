"""Tests for half-hourly to hourly alignment of actuals (spec Section 11.2)."""

import pandas as pd
import pytest

from app.alignment import hourly_actuals


def half_hours(values: dict[str, int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "start_time": [pd.Timestamp(t, tz="UTC") for t in values],
            "generation_mw": list(values.values()),
        }
    )


def test_hourly_actual_is_mean_of_the_two_half_hours():
    out = hourly_actuals(half_hours({"2026-01-01T00:00": 100, "2026-01-01T00:30": 201}))
    assert list(out.columns) == ["target_time", "actual_mw"]
    assert out["target_time"].tolist() == [pd.Timestamp("2026-01-01T00:00Z")]
    assert out["actual_mw"].tolist() == [150.5]


def test_hour_with_one_half_hour_missing_is_null():
    out = hourly_actuals(
        half_hours(
            {
                "2026-01-01T00:00": 100,
                "2026-01-01T00:30": 200,
                "2026-01-01T01:00": 300,  # 01:30 missing
            }
        )
    ).set_index("target_time")
    assert out.loc[pd.Timestamp("2026-01-01T00:00Z"), "actual_mw"] == 150
    assert pd.isna(out.loc[pd.Timestamp("2026-01-01T01:00Z"), "actual_mw"])


def test_hour_with_only_second_half_hour_is_null():
    out = hourly_actuals(half_hours({"2026-01-01T02:30": 300}))
    assert out["target_time"].tolist() == [pd.Timestamp("2026-01-01T02:00Z")]
    assert out["actual_mw"].isna().all()


def test_output_is_sorted_by_hour():
    out = hourly_actuals(
        half_hours(
            {
                "2026-01-01T01:30": 4,
                "2026-01-01T00:00": 1,
                "2026-01-01T01:00": 3,
                "2026-01-01T00:30": 2,
            }
        )
    )
    assert out["actual_mw"].tolist() == [1.5, 3.5]


def test_duplicate_half_hours_are_rejected():
    df = half_hours({"2026-01-01T00:00": 100, "2026-01-01T00:30": 200})
    with pytest.raises(ValueError, match="duplicate"):
        hourly_actuals(pd.concat([df, df.iloc[:1]]))


def test_real_january_data_gives_744_complete_hours(real_actuals):
    out = hourly_actuals(real_actuals)
    assert len(out) == 31 * 24
    assert out["actual_mw"].notna().all()
