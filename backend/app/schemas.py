"""Pydantic response models for every endpoint.

All power values are in MW. All times are UTC (equal to UK time in January).
error = forecast - actual: positive means wind was over-forecast (buyer short).
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str


class Meta(BaseModel):
    min_date: date
    max_date: date
    default_cutoff: str = Field(description="HH:MM UTC on the day before delivery")
    cutoff_options: list[str]
    timezone: str
    data_notes: list[str]


class DecisionPoint(BaseModel):
    target_time: datetime = Field(description="Start of the delivery hour")
    forecast_mw: float | None = Field(description="Null if no forecast by the cutoff")
    publish_time: datetime | None
    horizon_h: float | None = Field(description="Hours from publish to target hour")
    actual_mw: float | None = Field(description="Mean of the two half-hours")
    error_mw: float | None = Field(description="forecast - actual")
    missing: bool = Field(description="True if no forecast was available by the cutoff")


class BufferBasis(BaseModel):
    """Which errors the shortfall buffer was computed from."""

    date_from: date
    date_to: date
    cutoff: str
    n: int


class DecisionForecast(BaseModel):
    delivery_date: date
    cutoff: str
    cutoff_datetime: datetime
    publish_times: list[datetime] = Field(description="Distinct publishes used")
    horizon_min_h: float | None
    horizon_max_h: float | None
    n_missing: int
    points: list[DecisionPoint]
    buffer_90_mw: float | None = Field(
        description="Shortfall covered in 9 of 10 hours, from the whole-January errors"
    )
    buffer_95_mw: float | None
    buffer_basis: BufferBasis
    day_mae_mw: float | None = Field(description="This day's mean absolute error")


class SeriesPoint(BaseModel):
    target_time: datetime
    forecast_mw: float | None
    actual_mw: float | None
    error_mw: float | None
    missing: bool


class Series(BaseModel):
    date_from: date
    date_to: date
    cutoff: str
    points: list[SeriesPoint]


class OverallMetrics(BaseModel):
    n: int = Field(description="Hours with both a forecast and an actual")
    n_missing_forecast: int
    n_missing_actual: int
    mae: float | None
    rmse: float | None
    bias: float | None = Field(description="Mean signed error")
    mean_actual_mw: float | None
    nmae_pct: float | None = Field(description="MAE / mean actual, in percent")
    abs_p50: float | None
    abs_p90: float | None
    abs_p95: float | None
    signed_p5: float | None
    signed_p50: float | None
    signed_p95: float | None
    buffer_90: float | None = Field(description="max(0, 90th percentile of error)")
    buffer_95: float | None


class HourSlice(BaseModel):
    hour: int
    mae: float | None
    bias: float | None
    n: int


class WindLevelSlice(BaseModel):
    level: str
    mae: float | None
    bias: float | None
    n: int


class WindThresholds(BaseModel):
    low_max_mw: float = Field(description="Upper bound of 'low' (first tercile)")
    medium_max_mw: float = Field(description="Upper bound of 'medium'")


class DaySlice(BaseModel):
    delivery_date: date
    mae: float | None
    bias: float | None
    n: int


class DataQuality(BaseModel):
    n_hours: int
    n_pairs: int
    n_missing_forecast: int
    n_missing_actual: int


class Baseline(BaseModel):
    """Naive forecast: the actual at the same hour two days earlier."""

    n: int
    forecast_mae: float | None
    baseline_mae: float | None


class Metrics(BaseModel):
    date_from: date
    date_to: date
    cutoff: str
    overall: OverallMetrics
    by_hour: list[HourSlice]
    by_wind_level: list[WindLevelSlice]
    wind_thresholds: WindThresholds | None
    by_day: list[DaySlice]
    data_quality: DataQuality
    baseline: Baseline
    findings: list[str]


class HorizonBucket(BaseModel):
    bucket: str
    mae: float | None
    bias: float | None
    n: int


class ErrorByHorizon(BaseModel):
    date_from: date
    date_to: date
    buckets: list[HorizonBucket]


class CutoffRow(BaseModel):
    cutoff: str
    mae: float | None
    bias: float | None
    buffer_90: float | None
    n: int


class CutoffSensitivity(BaseModel):
    date_from: date
    date_to: date
    rows: list[CutoffRow]
