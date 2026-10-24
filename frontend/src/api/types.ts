// Mirrors backend/app/schemas.py. Power in MW, times are ISO 8601 UTC strings.
// error = forecast - actual: positive means wind was over-forecast (buyer short).

export interface Meta {
  min_date: string;
  max_date: string;
  default_cutoff: string;
  cutoff_options: string[];
  timezone: string;
  data_notes: string[];
}

export interface DecisionPoint {
  target_time: string;
  forecast_mw: number | null;
  publish_time: string | null;
  horizon_h: number | null;
  actual_mw: number | null;
  error_mw: number | null;
  missing: boolean;
}

export interface BufferBasis {
  date_from: string;
  date_to: string;
  cutoff: string;
  n: number;
}

export interface DecisionForecast {
  delivery_date: string;
  cutoff: string;
  cutoff_datetime: string;
  publish_times: string[];
  horizon_min_h: number | null;
  horizon_max_h: number | null;
  n_missing: number;
  points: DecisionPoint[];
  buffer_90_mw: number | null;
  buffer_95_mw: number | null;
  buffer_basis: BufferBasis;
  day_mae_mw: number | null;
  /** Mean signed error over January at this cutoff (positive = forecast too high). */
  bias_mw: number | null;
  /** 90% buffer from errors known at this day's cutoff only; null without enough history. */
  rolling_buffer_90_mw: number | null;
}

export interface SeriesPoint {
  target_time: string;
  forecast_mw: number | null;
  actual_mw: number | null;
  error_mw: number | null;
  missing: boolean;
}

export interface Series {
  date_from: string;
  date_to: string;
  cutoff: string;
  points: SeriesPoint[];
}

export interface OverallMetrics {
  n: number;
  n_missing_forecast: number;
  n_missing_actual: number;
  mae: number | null;
  rmse: number | null;
  bias: number | null;
  mean_actual_mw: number | null;
  nmae_pct: number | null;
  abs_p50: number | null;
  abs_p90: number | null;
  abs_p95: number | null;
  signed_p5: number | null;
  signed_p50: number | null;
  signed_p95: number | null;
  buffer_90: number | null;
  buffer_95: number | null;
}

export interface Slice {
  mae: number | null;
  bias: number | null;
  n: number;
}

export interface HourSlice extends Slice {
  hour: number;
}

export interface WindLevelSlice extends Slice {
  level: "low" | "medium" | "high";
}

export interface DaySlice extends Slice {
  delivery_date: string;
}

/** [low, high] ranges from resampling whole delivery days. */
export interface ConfidenceRanges {
  level: number;
  mae: [number, number];
  bias: [number, number];
  buffer_90: [number, number];
}

export interface Metrics {
  date_from: string;
  date_to: string;
  cutoff: string;
  overall: OverallMetrics;
  overall_ci: ConfidenceRanges | null;
  by_hour: HourSlice[];
  by_wind_level: WindLevelSlice[];
  wind_thresholds: { low_max_mw: number; medium_max_mw: number } | null;
  by_day: DaySlice[];
  data_quality: {
    n_hours: number;
    n_pairs: number;
    n_missing_forecast: number;
    n_missing_actual: number;
  };
  baseline: { n: number; forecast_mae: number | null; baseline_mae: number | null };
  look_ahead: LookAhead;
  rolling_buffer: RollingBuffer;
  findings: string[];
}

export interface LookAheadSide {
  mae: number | null;
  bias: number | null;
  buffer_90: number | null;
  median_horizon_h: number | null;
  n: number;
}

/** Forecast at the cutoff vs the newest forecast before each hour (look-ahead). */
export interface LookAhead {
  at_cutoff: LookAheadSide;
  latest_before_delivery: LookAheadSide;
}

/** 90% buffer built only from errors known at each cutoff, and how often it worked. */
export interface RollingBuffer {
  level: number;
  target_pct: number;
  min_history_days: number;
  n_days: number;
  n_hours: number;
  coverage_pct: number | null;
  mean_buffer_mw: number | null;
  days: { delivery_date: string; buffer_mw: number | null; covered_hours: number | null; n_hours: number }[];
}

export interface HorizonBucket extends Slice {
  bucket: string;
}

export interface ErrorByHorizon {
  date_from: string;
  date_to: string;
  buckets: HorizonBucket[];
}

export interface CutoffRow {
  cutoff: string;
  mae: number | null;
  bias: number | null;
  buffer_90: number | null;
  n: number;
}

export interface CutoffSensitivity {
  date_from: string;
  date_to: string;
  rows: CutoffRow[];
}
