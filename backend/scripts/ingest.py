"""Fetch, validate and save the Elexon data the portal needs. Run once, offline.

Usage (from the backend/ folder):
    python -m scripts.ingest

Writes to data/processed/:
    actuals_half_hourly.csv           FUELHH WIND, 2026-01-01 .. 2026-01-31
    actuals_half_hourly_baseline.csv  FUELHH WIND, 2025-12-30 .. 2025-12-31
    forecasts.csv                     WINDFOR, published 2025-12-29 .. 2026-01-31

Then prints a validation report. Exits non-zero if an acceptance check fails.
"""

import sys
import time as time_module
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

import httpx
import pandas as pd
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter

from app import config

MAX_ATTEMPTS = 4
TIMEOUT_SECONDS = 60
CHUNK_DAYS = 7


# --------------------------------------------------------------------------
# Row schemas: exactly the fields verified in Section 4 of the spec.
# extra="forbid" makes ingestion stop loudly if the API shape changes.
# --------------------------------------------------------------------------


class ActualRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: Literal["FUELHH"]
    publishTime: AwareDatetime
    startTime: AwareDatetime
    settlementDate: date
    settlementPeriod: int = Field(ge=1, le=50)
    fuelType: Literal["WIND"]
    generation: int


class ForecastRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: Literal["WINDFOR"]
    publishTime: AwareDatetime
    startTime: AwareDatetime
    generation: int


ACTUALS_COLUMNS = [
    "start_time",
    "publish_time",
    "settlement_date",
    "settlement_period",
    "generation_mw",
]
FORECASTS_COLUMNS = ["publish_time", "start_time", "generation_mw"]


# --------------------------------------------------------------------------
# Pure helpers (unit-tested)
# --------------------------------------------------------------------------


def date_chunks(
    start: date, end: date, days: int = CHUNK_DAYS
) -> list[tuple[date, date]]:
    """Split an inclusive date range into consecutive, non-overlapping chunks."""
    chunks = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=days - 1), end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return chunks


def datetime_chunks(
    start: datetime, end: datetime, days: int = CHUNK_DAYS
) -> list[tuple[datetime, datetime]]:
    """Split a datetime range into back-to-back chunks of at most `days` days.

    Neighbouring chunks share a boundary instant, so a row published exactly
    on a boundary may come back twice; dedupe() removes it.
    """
    chunks = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=days), end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end
    return chunks


def parse_actuals(records: list[dict]) -> pd.DataFrame:
    """Validate raw FUELHH records and return a tidy, UTC frame."""
    rows = TypeAdapter(list[ActualRow]).validate_python(records)
    df = pd.DataFrame(
        {
            "start_time": [r.startTime for r in rows],
            "publish_time": [r.publishTime for r in rows],
            "settlement_date": [r.settlementDate for r in rows],
            "settlement_period": [r.settlementPeriod for r in rows],
            "generation_mw": [r.generation for r in rows],
        },
        columns=ACTUALS_COLUMNS,
    )
    return _to_utc(df, ["start_time", "publish_time"])


def parse_forecasts(records: list[dict]) -> pd.DataFrame:
    """Validate raw WINDFOR records and return a tidy, UTC frame."""
    rows = TypeAdapter(list[ForecastRow]).validate_python(records)
    df = pd.DataFrame(
        {
            "publish_time": [r.publishTime for r in rows],
            "start_time": [r.startTime for r in rows],
            "generation_mw": [r.generation for r in rows],
        },
        columns=FORECASTS_COLUMNS,
    )
    return _to_utc(df, ["publish_time", "start_time"])


def _to_utc(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        df[col] = pd.to_datetime(df[col], utc=True)
    return df


def dedupe(df: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    """Drop exact duplicate rows; raise if one key has two different values.

    Exact duplicates are expected where weekly chunks overlap. Conflicting
    values for the same key would mean we do not understand the data, so we
    stop instead of silently picking one.
    """
    out = df.drop_duplicates()
    conflicts = out[out.duplicated(subset=key, keep=False)]
    if not conflicts.empty:
        raise ValueError(
            f"{len(conflicts)} rows have conflicting values for key {key}:\n"
            f"{conflicts.head(10).to_string()}"
        )
    return out.sort_values(key).reset_index(drop=True)


def find_half_hour_gaps(
    start_times: pd.Series, first: datetime, last: datetime
) -> list[pd.Timestamp]:
    """Return every expected half-hour slot in [first, last] that is missing."""
    expected = pd.date_range(first, last, freq="30min", tz="UTC")
    present = pd.DatetimeIndex(start_times)
    return list(expected.difference(present))


def decision_coverage(
    forecasts: pd.DataFrame, delivery_days: list[date], cutoff: time
) -> pd.DataFrame:
    """For each delivery day, count target hours that have at least one
    forecast published at or before the cutoff on D-1.

    This is only a data-availability check. The actual per-hour selection
    lives in app/decision.py (Phase 3).
    """
    rows = []
    for day in delivery_days:
        cutoff_dt = pd.Timestamp(datetime.combine(day - timedelta(days=1), cutoff, UTC))
        day_start = pd.Timestamp(datetime.combine(day, time(0, 0), UTC))
        day_end = pd.Timestamp(
            datetime.combine(day + timedelta(days=1), time(0, 0), UTC)
        )
        eligible = forecasts[
            (forecasts["publish_time"] <= cutoff_dt)
            & (forecasts["start_time"] >= day_start)
            & (forecasts["start_time"] < day_end)
        ]
        rows.append(
            {
                "delivery_date": day,
                "cutoff": cutoff_dt,
                "hours_covered": int(eligible["start_time"].nunique()),
                "latest_eligible_publish": eligible["publish_time"].max()
                if not eligible.empty
                else pd.NaT,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------


def fetch_list(client: httpx.Client, path: str, params: dict) -> list[dict]:
    """GET a stream endpoint (bare JSON list) with retries and backoff."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.get(path, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError(f"Expected a JSON list from {path}, got {type(data)}")
            print(f"  GET {response.url} -> {len(data)} rows")
            return data
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            retryable = isinstance(exc, httpx.TransportError) or (
                exc.response.status_code == 429 or exc.response.status_code >= 500
            )
            if not retryable or attempt == MAX_ATTEMPTS:
                raise
            wait = 2**attempt
            print(f"  attempt {attempt} failed ({exc}); retrying in {wait}s")
            time_module.sleep(wait)
    raise AssertionError("unreachable")


def fetch_actuals(client: httpx.Client, start: date, end: date) -> pd.DataFrame:
    records: list[dict] = []
    for chunk_start, chunk_end in date_chunks(start, end):
        records += fetch_list(
            client,
            "/datasets/FUELHH/stream",
            {
                "settlementDateFrom": chunk_start.isoformat(),
                "settlementDateTo": chunk_end.isoformat(),
                "fuelType": "WIND",
            },
        )
    return dedupe(parse_actuals(records), ["start_time"])


def fetch_forecasts(
    client: httpx.Client, start: datetime, end: datetime
) -> pd.DataFrame:
    records: list[dict] = []
    for chunk_start, chunk_end in datetime_chunks(start, end):
        records += fetch_list(
            client,
            "/datasets/WINDFOR/stream",
            {
                "publishDateTimeFrom": chunk_start.strftime("%Y-%m-%dT%H:%MZ"),
                "publishDateTimeTo": chunk_end.strftime("%Y-%m-%dT%H:%MZ"),
            },
        )
    return dedupe(parse_forecasts(records), ["start_time", "publish_time"])


# --------------------------------------------------------------------------
# Output and report
# --------------------------------------------------------------------------


def write_csv(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    print(f"  wrote {len(df)} rows -> {path.name}")


def in_range(df: pd.DataFrame, first: date, last: date) -> pd.DataFrame:
    days = df["start_time"].dt.date
    return df[(days >= first) & (days <= last)]


def report(
    actuals: pd.DataFrame, baseline: pd.DataFrame, forecasts: pd.DataFrame
) -> bool:
    """Print the validation report. Return True if all acceptance checks pass."""
    ok = True

    def check(passed: bool, message: str) -> None:
        nonlocal ok
        ok = ok and passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {message}")

    print("\nACTUALS (FUELHH WIND)")
    jan = in_range(actuals, config.ACTUALS_FROM, config.ACTUALS_TO)
    check(len(jan) == 1488, f"January half-hourly rows: {len(jan)} (expected 1488)")
    check(len(actuals) == len(jan), f"rows outside January: {len(actuals) - len(jan)}")
    gaps = find_half_hour_gaps(
        jan["start_time"],
        datetime.combine(config.ACTUALS_FROM, time(0, 0), UTC),
        datetime.combine(config.ACTUALS_TO, time(23, 30), UTC),
    )
    check(not gaps, f"missing half-hours: {len(gaps)} {gaps[:5]}")
    check(not actuals["start_time"].duplicated().any(), "no duplicate start_time")
    print(
        f"  generation MW min/mean/max: {actuals['generation_mw'].min()} / "
        f"{actuals['generation_mw'].mean():.0f} / {actuals['generation_mw'].max()}"
    )
    print(
        f"  settlement periods per day: "
        f"{sorted(actuals.groupby('settlement_date').size().unique().tolist())}"
    )

    print("\nBASELINE ACTUALS (2025-12-30 .. 2025-12-31)")
    check(len(baseline) == 96, f"rows: {len(baseline)} (expected 96)")

    print("\nFORECASTS (WINDFOR)")
    dupes = forecasts.duplicated(subset=["start_time", "publish_time"]).sum()
    check(dupes == 0, f"duplicate (start_time, publish_time): {dupes}")
    print(f"  rows: {len(forecasts)}")
    print(f"  distinct publish times: {forecasts['publish_time'].nunique()}")
    print(
        f"  publish time range: {forecasts['publish_time'].min()} .. "
        f"{forecasts['publish_time'].max()}"
    )
    print(
        f"  target time range: {forecasts['start_time'].min()} .. "
        f"{forecasts['start_time'].max()}"
    )
    publish_minutes = forecasts["publish_time"].dt.minute.value_counts().to_dict()
    target_minutes = forecasts["start_time"].dt.minute.value_counts().to_dict()
    print(f"  publish minute-of-hour counts: {publish_minutes}")
    print(f"  target minute-of-hour counts: {target_minutes}")
    pubs = pd.Series(sorted(forecasts["publish_time"].unique()))
    intervals = pubs.diff().dropna().value_counts().sort_index()
    print("  publish intervals:", {str(k): int(v) for k, v in intervals.items()})
    horizon_h = (
        forecasts["start_time"] - forecasts["publish_time"]
    ).dt.total_seconds() / 3600
    print(
        f"  horizon h min/median/max: {horizon_h.min()} / {horizon_h.median()} / "
        f"{horizon_h.max()}; negative horizons: {int((horizon_h < 0).sum())}"
    )
    per_target = forecasts.groupby("start_time").size()
    print(
        f"  forecasts per target hour min/median/max: {per_target.min()} / "
        f"{per_target.median()} / {per_target.max()}"
    )
    print(
        f"  negative generation values: {int((forecasts['generation_mw'] < 0).sum())}"
    )

    print(f"\nDECISION COVERAGE at default cutoff {config.DEFAULT_CUTOFF:%H:%M} on D-1")
    days = [
        config.MIN_DATE + timedelta(days=i)
        for i in range((config.MAX_DATE - config.MIN_DATE).days + 1)
    ]
    cov = decision_coverage(forecasts, days, config.DEFAULT_CUTOFF)
    short = cov[cov["hours_covered"] < 24]
    check(short.empty, f"days with < 24 covered hours: {len(short)}")
    if not short.empty:
        print(short.to_string(index=False))
    lag = (cov["cutoff"] - cov["latest_eligible_publish"]).dt.total_seconds() / 3600
    print(
        f"  latest eligible publish before cutoff, hours before cutoff "
        f"min/max: {lag.min()} / {lag.max()}"
    )
    golden = cov[cov["delivery_date"] == date(2026, 1, 3)].iloc[0]
    print(
        f"  golden day 2026-01-03: {golden['hours_covered']} hours, latest "
        f"eligible publish {golden['latest_eligible_publish']}"
    )

    print("\nCOVERAGE AT OTHER CUTOFFS (days with < 24 covered hours)")
    for cutoff in config.CUTOFF_OPTIONS:
        c = decision_coverage(forecasts, days, cutoff)
        print(f"  {cutoff:%H:%M}: {int((c['hours_covered'] < 24).sum())}")

    return ok


def main() -> int:
    with httpx.Client(
        base_url=config.ELEXON_BASE_URL, timeout=TIMEOUT_SECONDS
    ) as client:
        print("Fetching actuals (January)")
        actuals = fetch_actuals(client, config.ACTUALS_FROM, config.ACTUALS_TO)
        print("Fetching baseline actuals (late December)")
        baseline = fetch_actuals(
            client, config.BASELINE_ACTUALS_FROM, config.BASELINE_ACTUALS_TO
        )
        print("Fetching forecasts")
        forecasts = fetch_forecasts(
            client, config.FORECASTS_PUBLISHED_FROM, config.FORECASTS_PUBLISHED_TO
        )

    print("\nWriting CSV files")
    write_csv(actuals, config.ACTUALS_CSV)
    write_csv(baseline, config.BASELINE_ACTUALS_CSV)
    write_csv(forecasts, config.FORECASTS_CSV)

    ok = report(actuals, baseline, forecasts)
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
