"""Tests for the pure helpers in scripts/ingest.py (no network access)."""

from datetime import UTC, date, datetime, time

import pandas as pd
import pytest
from pydantic import ValidationError

from scripts.ingest import (
    date_chunks,
    datetime_chunks,
    decision_coverage,
    dedupe,
    find_half_hour_gaps,
    parse_actuals,
    parse_forecasts,
)


def actual_record(start: str, generation: int = 5000, **overrides) -> dict:
    record = {
        "dataset": "FUELHH",
        "publishTime": start,
        "startTime": start,
        "settlementDate": start[:10],
        "settlementPeriod": 1,
        "fuelType": "WIND",
        "generation": generation,
    }
    record.update(overrides)
    return record


def forecast_record(publish: str, start: str, generation: int = 7000) -> dict:
    return {
        "dataset": "WINDFOR",
        "publishTime": publish,
        "startTime": start,
        "generation": generation,
    }


# ---------------------------------------------------------------- chunking


def test_date_chunks_cover_january_in_weeks_without_overlap():
    chunks = date_chunks(date(2026, 1, 1), date(2026, 1, 31))
    assert chunks[0] == (date(2026, 1, 1), date(2026, 1, 7))
    assert chunks[-1] == (date(2026, 1, 29), date(2026, 1, 31))
    assert len(chunks) == 5
    for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:], strict=False):
        assert (next_start - prev_end).days == 1


def test_date_chunks_single_short_range():
    assert date_chunks(date(2025, 12, 30), date(2025, 12, 31)) == [
        (date(2025, 12, 30), date(2025, 12, 31))
    ]


def test_datetime_chunks_are_contiguous_and_end_exactly():
    start = datetime(2025, 12, 29, tzinfo=UTC)
    end = datetime(2026, 1, 31, tzinfo=UTC)
    chunks = datetime_chunks(start, end)
    assert chunks[0][0] == start
    assert chunks[-1][1] == end
    for chunk_start, chunk_end in chunks:
        assert (chunk_end - chunk_start).days <= 7
    for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:], strict=False):
        assert prev_end == next_start


# -------------------------------------------------------------- validation


def test_parse_actuals_returns_utc_snake_case_frame():
    df = parse_actuals([actual_record("2026-01-01T00:00:00Z", 4321)])
    assert list(df.columns) == [
        "start_time",
        "publish_time",
        "settlement_date",
        "settlement_period",
        "generation_mw",
    ]
    assert df.loc[0, "start_time"] == pd.Timestamp("2026-01-01T00:00:00Z")
    assert str(df["start_time"].dt.tz) == "UTC"
    assert df.loc[0, "generation_mw"] == 4321


def test_parse_actuals_rejects_other_fuel_types():
    with pytest.raises(ValidationError):
        parse_actuals([actual_record("2026-01-01T00:00:00Z", fuelType="CCGT")])


def test_parse_actuals_rejects_unknown_fields():
    # Section 4 lists the fields exactly; anything else means the API changed.
    with pytest.raises(ValidationError):
        parse_actuals([actual_record("2026-01-01T00:00:00Z", surprise=1)])


def test_parse_forecasts_returns_utc_snake_case_frame():
    df = parse_forecasts(
        [forecast_record("2026-01-02T07:30:00Z", "2026-01-03T00:00:00Z", 18711)]
    )
    assert list(df.columns) == ["publish_time", "start_time", "generation_mw"]
    assert df.loc[0, "publish_time"] == pd.Timestamp("2026-01-02T07:30:00Z")
    assert df.loc[0, "generation_mw"] == 18711


def test_parse_forecasts_rejects_missing_generation():
    record = forecast_record("2026-01-02T07:30:00Z", "2026-01-03T00:00:00Z")
    del record["generation"]
    with pytest.raises(ValidationError):
        parse_forecasts([record])


def test_parse_handles_empty_list():
    assert parse_forecasts([]).empty
    assert parse_actuals([]).empty


# ------------------------------------------------------------------ dedupe


def test_dedupe_drops_exact_duplicates_from_overlapping_chunks():
    rec = forecast_record("2026-01-02T07:30:00Z", "2026-01-03T00:00:00Z")
    df = parse_forecasts([rec, rec])
    out = dedupe(df, ["start_time", "publish_time"])
    assert len(out) == 1


def test_dedupe_raises_on_conflicting_values_for_same_key():
    df = parse_forecasts(
        [
            forecast_record("2026-01-02T07:30:00Z", "2026-01-03T00:00:00Z", 100),
            forecast_record("2026-01-02T07:30:00Z", "2026-01-03T00:00:00Z", 200),
        ]
    )
    with pytest.raises(ValueError, match="conflicting"):
        dedupe(df, ["start_time", "publish_time"])


# -------------------------------------------------------------------- gaps


def test_find_half_hour_gaps_reports_missing_slot():
    starts = pd.date_range("2026-01-01T00:00Z", "2026-01-01T23:30Z", freq="30min")
    starts = starts.delete(5)  # drop 02:30
    gaps = find_half_hour_gaps(
        pd.Series(starts),
        datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 23, 30, tzinfo=UTC),
    )
    assert gaps == [pd.Timestamp("2026-01-01T02:30Z")]


def test_find_half_hour_gaps_empty_when_complete():
    starts = pd.date_range("2026-01-01T00:00Z", "2026-01-01T23:30Z", freq="30min")
    gaps = find_half_hour_gaps(
        pd.Series(starts),
        datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 23, 30, tzinfo=UTC),
    )
    assert gaps == []


# ---------------------------------------------------------------- coverage


def _day_forecasts(publish: str, day: str, hours: range = range(24)) -> list[dict]:
    return [forecast_record(publish, f"{day}T{h:02d}:00:00Z", 1000 + h) for h in hours]


def test_coverage_counts_only_publishes_at_or_before_cutoff():
    records = (
        _day_forecasts("2026-01-02T07:30:00Z", "2026-01-03", range(12))
        # Exactly at the cutoff: counts.
        + _day_forecasts("2026-01-02T09:00:00Z", "2026-01-03", range(12, 20))
        # After the cutoff: must not count, even though it fills the gap.
        + _day_forecasts("2026-01-02T09:30:00Z", "2026-01-03", range(20, 24))
    )
    cov = decision_coverage(parse_forecasts(records), [date(2026, 1, 3)], time(9, 0))
    row = cov.iloc[0]
    assert row["delivery_date"] == date(2026, 1, 3)
    assert row["hours_covered"] == 20
    assert row["latest_eligible_publish"] == pd.Timestamp("2026-01-02T09:00Z")


def test_coverage_reports_zero_for_day_without_forecasts():
    records = _day_forecasts("2026-01-02T07:30:00Z", "2026-01-03")
    cov = decision_coverage(
        parse_forecasts(records), [date(2026, 1, 3), date(2026, 1, 4)], time(9, 0)
    )
    assert cov["hours_covered"].tolist() == [24, 0]
    assert pd.isna(cov.iloc[1]["latest_eligible_publish"])
