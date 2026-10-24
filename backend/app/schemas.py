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
    bias_mw: float | None = Field(
        description="Mean signed error over January at this cutoff (+ = too high)"
    )
    rolling_buffer_90_mw: float | None = Field(
        description="90% buffer built only from errors known at this day's cutoff "
        "(days up to D-2). Null when there is not enough history."
    )


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


class ConfidenceRanges(BaseModel):
    """Ranges from resampling whole delivery days (bootstrap)."""

    level: float = Field(description="Coverage of each range, e.g. 0.9")
    mae: list[float] = Field(description="[low, high]")
    bias: list[float]
    buffer_90: list[float]


class LookAheadSide(BaseModel):
    mae: float | None
    bias: float | None
    buffer_90: float | None
    median_horizon_h: float | None
    n: int


class LookAhead(BaseModel):
    """The forecast at the cutoff vs the newest forecast before each hour began
    (which a buyer could not have used: look-ahead leakage)."""

    at_cutoff: LookAheadSide
    latest_before_delivery: LookAheadSide


class RollingBufferDay(BaseModel):
    delivery_date: date
    buffer_mw: float | None = Field(description="Null when history is too short")
    covered_hours: int | None = Field(description="Hours with error <= buffer")
    n_hours: int


class RollingBuffer(BaseModel):
    """90% shortfall buffer built without hindsight, and how often it worked."""

    level: float
    target_pct: int
    min_history_days: int
    n_days: int = Field(description="Days with enough history to be tested")
    n_hours: int
    coverage_pct: float | None = Field(description="Share of hours covered")
    mean_buffer_mw: float | None
    days: list[RollingBufferDay]


class Metrics(BaseModel):
    date_from: date
    date_to: date
    cutoff: str
    overall: OverallMetrics
    overall_ci: ConfidenceRanges | None
    by_hour: list[HourSlice]
    by_wind_level: list[WindLevelSlice]
    wind_thresholds: WindThresholds | None
    by_day: list[DaySlice]
    data_quality: DataQuality
    baseline: Baseline
    look_ahead: LookAhead
    rolling_buffer: RollingBuffer
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
