"""API endpoints (spec Section 8). All under /api; see main.py.

The data is static, so results are cached per (date range, cutoff). Only the
listed cutoffs are accepted, which bounds the work any request can cause.
"""

import json
from datetime import date, time
from functools import lru_cache
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app import config, schemas
from app import metrics as metrics_module
from app.data_loader import get_dataset
from app.decision import cutoff_datetime
from app.metrics import (
    build_pairs,
    headline_findings,
    overall_metrics,
    run_analysis,
    sensitivity_row,
)

router = APIRouter()

CutoffParam = Annotated[
    str,
    Query(
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
        description="Decision time on the day before delivery, HH:MM UTC",
    ),
]
FromParam = Annotated[date, Query(alias="from", description="First delivery day")]
ToParam = Annotated[date, Query(alias="to", description="Last delivery day")]
DEFAULT_CUTOFF = config.DEFAULT_CUTOFF.strftime("%H:%M")
CUTOFF_OPTIONS = [c.strftime("%H:%M") for c in config.CUTOFF_OPTIONS]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def check_dates(*days: date) -> None:
    for day in days:
        if not config.MIN_DATE <= day <= config.MAX_DATE:
            raise HTTPException(
                422,
                f"Date {day} is out of range: dates must be between "
                f"{config.MIN_DATE} and {config.MAX_DATE}.",
            )


def check_range(date_from: date, date_to: date) -> None:
    check_dates(date_from, date_to)
    if date_from > date_to:
        raise HTTPException(
            422, f"'from' ({date_from}) must not be after 'to' ({date_to})."
        )


def parse_cutoff(cutoff: str) -> time:
    if cutoff not in CUTOFF_OPTIONS:
        raise HTTPException(
            422,
            f"Cutoff {cutoff} is not supported: use one of "
            f"{', '.join(CUTOFF_OPTIONS)}.",
        )
    return time.fromisoformat(cutoff)


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe dicts (NaN/NaT become None, numpy types become
    plain Python)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


@lru_cache(maxsize=128)
def cached_pairs(date_from: date, date_to: date, cutoff: time) -> pd.DataFrame:
    data = get_dataset()
    return build_pairs(data.forecasts, data.hourly_actuals, date_from, date_to, cutoff)


@lru_cache(maxsize=64)
def cached_analysis(date_from: date, date_to: date, cutoff: time) -> dict:
    data = get_dataset()
    return run_analysis(
        data.forecasts,
        data.hourly_actuals,
        date_from,
        date_to,
        cutoff,
        pairs=cached_pairs(date_from, date_to, cutoff),
        horizon=cached_horizon(date_from, date_to),
        sensitivity=cached_sensitivity(date_from, date_to),
        # Earlier days (from 30 Dec) give the no-hindsight buffer its history.
        history_pairs=cached_pairs(config.BASELINE_ACTUALS_FROM, date_to, cutoff),
    )


@lru_cache(maxsize=64)
def cached_horizon(date_from: date, date_to: date) -> pd.DataFrame:
    data = get_dataset()
    return metrics_module.error_by_horizon(
        data.forecasts, data.hourly_actuals, date_from, date_to
    )


@lru_cache(maxsize=64)
def cached_sensitivity(date_from: date, date_to: date) -> pd.DataFrame:
    return pd.DataFrame(
        [
            sensitivity_row(cutoff, cached_pairs(date_from, date_to, cutoff))
            for cutoff in config.CUTOFF_OPTIONS
        ]
    )


def warm_caches() -> None:
    """Compute the default views at start-up so first requests are fast."""
    cached_analysis(config.MIN_DATE, config.MAX_DATE, config.DEFAULT_CUTOFF)
    cached_horizon(config.MIN_DATE, config.MAX_DATE)
    cached_sensitivity(config.MIN_DATE, config.MAX_DATE)


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.get("/health", response_model=schemas.Health)
def health() -> schemas.Health:
    return schemas.Health(status="ok")


@router.get("/meta", response_model=schemas.Meta)
def meta() -> schemas.Meta:
    data = get_dataset()
    fc = data.forecasts
    return schemas.Meta(
        min_date=config.MIN_DATE,
        max_date=config.MAX_DATE,
        default_cutoff=DEFAULT_CUTOFF,
        cutoff_options=CUTOFF_OPTIONS,
        timezone="UTC",
        data_notes=[
            "Source: Elexon BMRS. Actuals are FUELHH (fuel type WIND); forecasts "
            "are WINDFOR. Data was downloaded once and is not live.",
            f"Actuals: {data.n_half_hourly_actuals:,} half-hourly values for "
            f"January 2026, with no gaps. Hourly actual = mean of the two half-hours.",
            f"Forecasts: {len(fc):,} hourly values from "
            f"{fc['publish_time'].nunique()} publishes, normally 8 per day "
            f"at :30 past the hour.",
            "On 15 Jan the 11:30 forecast was published late, at 12:25. For "
            "delivery on 16 Jan with a 12:00 cutoff, the 09:30 forecast is used.",
            "All times are UTC, which equals UK time in January.",
        ],
    )


@router.get("/decision-forecast", response_model=schemas.DecisionForecast)
def decision_forecast(
    delivery_date: date, cutoff: CutoffParam = DEFAULT_CUTOFF
) -> schemas.DecisionForecast:
    """The forecast available at the cutoff on D-1 for each hour of the day."""
    check_dates(delivery_date)
    cutoff_time = parse_cutoff(cutoff)
    month = cached_pairs(config.MIN_DATE, config.MAX_DATE, cutoff_time)
    day = month[month["target_time"].dt.date == delivery_date]
    month_metrics = overall_metrics(month)
    day_metrics = overall_metrics(day)
    available = day.dropna(subset=["publish_time"])
    rolling = cached_analysis(config.MIN_DATE, config.MAX_DATE, cutoff_time)[
        "rolling_buffer_days"
    ].set_index("delivery_date")["buffer_mw"]
    rolling_buffer = rolling.get(delivery_date)

    return schemas.DecisionForecast(
        delivery_date=delivery_date,
        cutoff=cutoff,
        cutoff_datetime=cutoff_datetime(delivery_date, cutoff_time),
        publish_times=sorted(available["publish_time"].unique()),
        horizon_min_h=available["horizon_h"].min() if len(available) else None,
        horizon_max_h=available["horizon_h"].max() if len(available) else None,
        n_missing=int(day["missing"].sum()),
        points=records(day),
        buffer_90_mw=month_metrics["buffer_90"],
        buffer_95_mw=month_metrics["buffer_95"],
        buffer_basis=schemas.BufferBasis(
            date_from=config.MIN_DATE,
            date_to=config.MAX_DATE,
            cutoff=cutoff,
            n=month_metrics["n"],
        ),
        day_mae_mw=day_metrics["mae"],
        bias_mw=month_metrics["bias"],
        rolling_buffer_90_mw=None if pd.isna(rolling_buffer) else rolling_buffer,
    )


@router.get("/series", response_model=schemas.Series)
def series(
    date_from: FromParam = config.MIN_DATE,
    date_to: ToParam = config.MAX_DATE,
    cutoff: CutoffParam = DEFAULT_CUTOFF,
) -> schemas.Series:
    """Hourly decision forecast, actual and error over a date range."""
    check_range(date_from, date_to)
    pairs = cached_pairs(date_from, date_to, parse_cutoff(cutoff))
    return schemas.Series(
        date_from=date_from, date_to=date_to, cutoff=cutoff, points=records(pairs)
    )


@router.get("/metrics", response_model=schemas.Metrics)
def metrics(
    date_from: FromParam = config.MIN_DATE,
    date_to: ToParam = config.MAX_DATE,
    cutoff: CutoffParam = DEFAULT_CUTOFF,
) -> schemas.Metrics:
    """Overall error metrics, slices and headline findings (spec Section 6)."""
    check_range(date_from, date_to)
    results = cached_analysis(date_from, date_to, parse_cutoff(cutoff))
    overall = results["overall"]
    by_day = results["by_day"].assign(
        delivery_date=results["by_day"]["delivery_date"].astype(str)
    )
    return schemas.Metrics(
        date_from=date_from,
        date_to=date_to,
        cutoff=cutoff,
        overall=overall,
        overall_ci=results["overall_ci"],
        by_hour=records(results["by_hour"]),
        by_wind_level=records(results["by_wind_level"]),
        wind_thresholds=results["wind_thresholds"] if overall["n"] else None,
        by_day=records(by_day),
        data_quality=schemas.DataQuality(
            n_hours=len(results["pairs"]),
            n_pairs=overall["n"],
            n_missing_forecast=overall["n_missing_forecast"],
            n_missing_actual=overall["n_missing_actual"],
        ),
        baseline=results["baseline"],
        look_ahead=results["look_ahead"],
        rolling_buffer=results["rolling_buffer"]
        | {
            "days": records(
                results["rolling_buffer_days"].assign(
                    delivery_date=results["rolling_buffer_days"][
                        "delivery_date"
                    ].astype(str)
                )
            )
        },
        findings=headline_findings(results),
    )


@router.get("/error-by-horizon", response_model=schemas.ErrorByHorizon)
def error_by_horizon(
    date_from: FromParam = config.MIN_DATE, date_to: ToParam = config.MAX_DATE
) -> schemas.ErrorByHorizon:
    """Accuracy by lead time, using every forecast with horizon > 0."""
    check_range(date_from, date_to)
    return schemas.ErrorByHorizon(
        date_from=date_from,
        date_to=date_to,
        buckets=records(cached_horizon(date_from, date_to)),
    )


@router.get("/cutoff-sensitivity", response_model=schemas.CutoffSensitivity)
def cutoff_sensitivity(
    date_from: FromParam = config.MIN_DATE, date_to: ToParam = config.MAX_DATE
) -> schemas.CutoffSensitivity:
    """MAE, bias and 90% buffer for each cutoff from 06:00 to 12:00."""
    check_range(date_from, date_to)
    return schemas.CutoffSensitivity(
        date_from=date_from,
        date_to=date_to,
        rows=records(cached_sensitivity(date_from, date_to)),
    )
