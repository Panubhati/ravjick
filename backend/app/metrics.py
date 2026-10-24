"""Forecast error metrics and slices (spec Section 6).

Sign convention: error_mw = forecast_mw - actual_mw.
  Positive: wind was over-forecast, so the buyer is short and must buy extra.
  Negative: wind was under-forecast, so the buyer bought too much.

Everything here works on "pairs": one row per delivery hour, holding the
decision forecast (from decision.py) and the hourly actual (from alignment.py).
Only hours where both exist ("matched pairs") count towards the metrics.

Percentiles use linear interpolation (the pandas/numpy default).
"""

from datetime import UTC, date, datetime, time, timedelta

import numpy as np
import pandas as pd

from app.decision import select_decision_forecast

HORIZON_BINS = [0, 6, 12, 24, 36, 48, np.inf]
HORIZON_LABELS = ["0-6h", "6-12h", "12-24h", "24-36h", "36-48h", "48h+"]
WIND_LEVELS = ["low", "medium", "high"]

METRIC_KEYS = [
    "mae",
    "rmse",
    "bias",
    "mean_actual_mw",
    "nmae_pct",
    "abs_p50",
    "abs_p90",
    "abs_p95",
    "signed_p5",
    "signed_p50",
    "signed_p95",
    "buffer_90",
    "buffer_95",
]


# --------------------------------------------------------------------------
# Basic error statistics
# --------------------------------------------------------------------------


def mae(errors: pd.Series) -> float:
    """Mean absolute error: the typical size of a miss, in MW."""
    return float(errors.abs().mean())


def rmse(errors: pd.Series) -> float:
    """Root mean squared error: like MAE, but punishes big misses more."""
    return float(np.sqrt((errors**2).mean()))


def bias(errors: pd.Series) -> float:
    """Mean signed error. Above zero means the forecast is too high on average."""
    return float(errors.mean())


def shortfall_buffer(errors: pd.Series, confidence: float) -> float:
    """MW of margin that would have covered the shortfall in `confidence` of hours.

    It is the upper quantile of the signed error, and never below zero (if wind
    always beat the forecast, no buffer is needed).
    """
    return max(0.0, float(errors.quantile(confidence)))


# --------------------------------------------------------------------------
# Building pairs
# --------------------------------------------------------------------------


def delivery_days(date_from: date, date_to: date) -> list[date]:
    """Every day from date_from to date_to, inclusive."""
    return [
        date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)
    ]


def build_pairs(
    forecasts: pd.DataFrame,
    hourly: pd.DataFrame,
    date_from: date,
    date_to: date,
    cutoff: time,
) -> pd.DataFrame:
    """Decision forecast + hourly actual + error for every hour in the range."""
    decisions = pd.concat(
        [
            select_decision_forecast(forecasts, day, cutoff)
            for day in delivery_days(date_from, date_to)
        ],
        ignore_index=True,
    )
    pairs = decisions.merge(hourly, on="target_time", how="left")
    pairs["error_mw"] = pairs["forecast_mw"] - pairs["actual_mw"]
    return pairs


def matched(pairs: pd.DataFrame) -> pd.DataFrame:
    """Only the hours where both a forecast and an actual exist."""
    return pairs.dropna(subset=["forecast_mw", "actual_mw"])


# --------------------------------------------------------------------------
# Overall metrics and slices
# --------------------------------------------------------------------------


def overall_metrics(pairs: pd.DataFrame) -> dict:
    """Headline numbers (Section 6.1). Values are None if nothing matched."""
    m = matched(pairs)
    result = {
        "n": len(m),
        "n_missing_forecast": int(pairs["missing"].sum()),
        "n_missing_actual": int(pairs["actual_mw"].isna().sum()),
    }
    if m.empty:
        return result | dict.fromkeys(METRIC_KEYS)

    errors = m["error_mw"]
    abs_errors = errors.abs()
    mean_actual = float(m["actual_mw"].mean())
    return result | {
        "mae": mae(errors),
        "rmse": rmse(errors),
        "bias": bias(errors),
        "mean_actual_mw": mean_actual,
        "nmae_pct": 100 * mae(errors) / mean_actual,
        "abs_p50": float(abs_errors.quantile(0.50)),
        "abs_p90": float(abs_errors.quantile(0.90)),
        "abs_p95": float(abs_errors.quantile(0.95)),
        "signed_p5": float(errors.quantile(0.05)),
        "signed_p50": float(errors.quantile(0.50)),
        "signed_p95": float(errors.quantile(0.95)),
        "buffer_90": shortfall_buffer(errors, 0.90),
        "buffer_95": shortfall_buffer(errors, 0.95),
    }


def _summarise(errors_by_group) -> pd.DataFrame:
    """MAE, bias and count per group of a grouped error series."""
    return pd.DataFrame(
        {
            "mae": errors_by_group.apply(lambda e: e.abs().mean()),
            "bias": errors_by_group.mean(),
            "n": errors_by_group.count(),
        }
    )


def by_hour(pairs: pd.DataFrame) -> pd.DataFrame:
    """MAE, bias and count for each hour of the day (0-23, all listed)."""
    m = matched(pairs)
    out = _summarise(m.groupby(m["target_time"].dt.hour)["error_mw"])
    out = out.reindex(range(24))
    out["n"] = out["n"].fillna(0).astype(int)
    return out.rename_axis("hour").reset_index()


def by_wind_level(pairs: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """MAE, bias and count for low, medium and high wind (terciles of actual).

    low: actual <= low_max_mw; medium: up to medium_max_mw; high: above that.
    """
    m = matched(pairs)
    low_max, medium_max = m["actual_mw"].quantile([1 / 3, 2 / 3]).tolist()
    level = np.where(
        m["actual_mw"] <= low_max,
        "low",
        np.where(m["actual_mw"] <= medium_max, "medium", "high"),
    )
    out = _summarise(m.groupby(level)["error_mw"]).reindex(WIND_LEVELS)
    out["n"] = out["n"].fillna(0).astype(int)
    thresholds = {"low_max_mw": float(low_max), "medium_max_mw": float(medium_max)}
    return out.rename_axis("level").reset_index(), thresholds


def by_day(pairs: pd.DataFrame) -> pd.DataFrame:
    """MAE, bias and count for each delivery day."""
    m = matched(pairs)
    out = _summarise(m.groupby(m["target_time"].dt.date)["error_mw"])
    return out.rename_axis("delivery_date").reset_index()


def cutoff_sensitivity(
    forecasts: pd.DataFrame,
    hourly: pd.DataFrame,
    date_from: date,
    date_to: date,
    cutoffs: list[time],
) -> pd.DataFrame:
    """Recompute MAE, bias and the 90% buffer for each cutoff (Section 6.2)."""
    rows = []
    for cutoff in cutoffs:
        m = overall_metrics(build_pairs(forecasts, hourly, date_from, date_to, cutoff))
        rows.append(
            {
                "cutoff": cutoff.strftime("%H:%M"),
                "mae": m["mae"],
                "bias": m["bias"],
                "buffer_90": m["buffer_90"],
                "n": m["n"],
            }
        )
    return pd.DataFrame(rows)


def error_by_horizon(
    forecasts: pd.DataFrame, hourly: pd.DataFrame, date_from: date, date_to: date
) -> pd.DataFrame:
    """MAE, bias and count by forecast lead time (Section 6.3).

    Uses every forecast row (not only decision forecasts) whose target hour is
    in the date range and whose horizon is above zero. Buckets include their
    upper edge: a 6.0 h horizon falls in 0-6h.
    """
    start = pd.Timestamp(datetime.combine(date_from, time(0, 0), UTC))
    end = pd.Timestamp(datetime.combine(date_to + timedelta(days=1), time(0, 0), UTC))
    fc = forecasts[(forecasts["start_time"] >= start) & (forecasts["start_time"] < end)]
    horizon_h = (fc["start_time"] - fc["publish_time"]).dt.total_seconds() / 3600
    fc = fc.assign(horizon_h=horizon_h)[horizon_h > 0]

    joined = fc.merge(hourly, left_on="start_time", right_on="target_time")
    joined = joined.dropna(subset=["actual_mw"])
    errors = joined["generation_mw"] - joined["actual_mw"]
    bucket = pd.cut(joined["horizon_h"], bins=HORIZON_BINS, labels=HORIZON_LABELS)
    out = _summarise(errors.groupby(bucket, observed=False))
    out["n"] = out["n"].astype(int)
    return out.rename_axis("bucket").reset_index()


def baseline_comparison(pairs: pd.DataFrame, hourly: pd.DataFrame) -> dict:
    """Compare the forecast with a naive guess: "same as two days earlier".

    The actual at the same hour on D-2 is fully known at the D-1 morning
    cutoff, so the guess uses no future information. Both MAEs are computed on
    the same hours (those with a forecast, an actual and a D-2 actual).
    """
    two_days_earlier = hourly.assign(
        target_time=hourly["target_time"] + timedelta(days=2)
    ).rename(columns={"actual_mw": "baseline_mw"})
    m = matched(pairs).merge(two_days_earlier, on="target_time")
    m = m.dropna(subset=["baseline_mw"])
    return {
        "n": len(m),
        "forecast_mae": mae(m["error_mw"]) if len(m) else None,
        "baseline_mae": mae(m["baseline_mw"] - m["actual_mw"]) if len(m) else None,
    }


# --------------------------------------------------------------------------
# Full analysis and findings
# --------------------------------------------------------------------------


def run_analysis(
    forecasts: pd.DataFrame,
    hourly: pd.DataFrame,
    date_from: date,
    date_to: date,
    cutoff: time,
    sensitivity_cutoffs: list[time] | None = None,
) -> dict:
    """Everything in Section 6 for one date range and cutoff."""
    pairs = build_pairs(forecasts, hourly, date_from, date_to, cutoff)
    wind_levels, thresholds = by_wind_level(pairs)
    return {
        "date_from": date_from,
        "date_to": date_to,
        "cutoff": cutoff,
        "n_days": len(delivery_days(date_from, date_to)),
        "pairs": pairs,
        "overall": overall_metrics(pairs),
        "by_hour": by_hour(pairs),
        "by_wind_level": wind_levels,
        "wind_thresholds": thresholds,
        "by_day": by_day(pairs),
        "by_horizon": error_by_horizon(forecasts, hourly, date_from, date_to),
        "cutoff_sensitivity": cutoff_sensitivity(
            forecasts, hourly, date_from, date_to, sensitivity_cutoffs or [cutoff]
        ),
        "baseline": baseline_comparison(pairs, hourly),
    }


def headline_findings(results: dict) -> list[str]:
    """Short, plain sentences with real numbers (Section 6.5)."""
    o = results["overall"]
    n_days = results["n_days"]
    cutoff = results["cutoff"].strftime("%H:%M")
    if not o["n"]:
        return ["No hours with both a forecast and an actual in this range."]

    findings = [
        f"Across {n_days} delivery days ({o['n']} hours), the forecast available "
        f"at the {cutoff} cutoff on the day before was off by {o['mae']:,.0f} MW "
        f"on average. That is {o['nmae_pct']:.1f}% of average wind output "
        f"({o['mean_actual_mw']:,.0f} MW).",
    ]

    # Bias, and how consistent its direction is.
    m = matched(results["pairs"])
    pct_over = 100 * (m["error_mw"] > 0).mean()
    days = results["by_day"]
    days_over = int((days["bias"] > 0).sum())
    direction = "too high" if o["bias"] > 0 else "too low"
    findings.append(
        f"On average the forecast was {abs(o['bias']):,.0f} MW {direction}. "
        f"Wind came in below forecast in {pct_over:.0f}% of hours, and on "
        f"{days_over} of {len(days)} days the forecast was too high on average."
    )

    findings.append(
        f"To be covered in 9 hours out of 10, plan for up to "
        f"{o['buffer_90']:,.0f} MW less wind than forecast "
        f"({o['buffer_95']:,.0f} MW for 19 hours out of 20)."
    )

    hours = results["by_hour"].dropna(subset=["mae"]).sort_values("mae")
    worst = hours.tail(3).iloc[::-1]
    best = hours.iloc[0]
    worst_text = ", ".join(
        f"{int(r.hour):02d}:00 ({r.mae:,.0f} MW)" for r in worst.itertuples()
    )
    findings.append(
        f"Errors are largest at {worst_text} UTC and smallest at "
        f"{int(best.hour):02d}:00 ({best.mae:,.0f} MW)."
    )

    worst_day = days.sort_values("mae").iloc[-1]
    findings.append(
        f"The worst day was {worst_day.delivery_date:%d %b} "
        f"(average miss {worst_day.mae:,.0f} MW)."
    )

    levels = results["by_wind_level"].set_index("level")
    t = results["wind_thresholds"]
    findings.append(
        f"By wind level, the average miss is {levels.loc['low', 'mae']:,.0f} MW "
        f"when wind is low (up to {t['low_max_mw']:,.0f} MW), "
        f"{levels.loc['medium', 'mae']:,.0f} MW when medium and "
        f"{levels.loc['high', 'mae']:,.0f} MW when high "
        f"(above {t['medium_max_mw']:,.0f} MW)."
    )

    horizon = results["by_horizon"].dropna(subset=["mae"])
    if not horizon.empty:
        horizon_text = ", ".join(
            f"{r.bucket} {r.mae:,.0f} MW" for r in horizon.itertuples()
        )
        findings.append(
            f"Average miss by how far ahead the forecast was made: {horizon_text}."
        )
        if (horizon["bias"] > 0).all():
            shortest = horizon.iloc[0]
            findings.append(
                f"The forecast is too high at every lead time, even "
                f"{shortest.bucket} ahead (by {shortest.bias:,.0f} MW on average), "
                f"so the over-forecast is not only a long-range effect."
            )

    sens = results["cutoff_sensitivity"].dropna(subset=["mae"])
    if len(sens) > 1:
        first, last = sens.iloc[0], sens.iloc[-1]
        findings.append(
            f"Moving the cutoff from {first.cutoff} to {last.cutoff} changes the "
            f"average miss from {first.mae:,.0f} MW to {last.mae:,.0f} MW and the "
            f"90% buffer from {first.buffer_90:,.0f} MW to {last.buffer_90:,.0f} MW."
        )

    b = results["baseline"]
    if b["n"]:
        findings.append(
            f'A naive guess ("same as two days earlier") misses by '
            f"{b['baseline_mae']:,.0f} MW on average over the same {b['n']} hours, "
            f"against {b['forecast_mae']:,.0f} MW for the forecast."
        )

    findings.append(
        f"Caveat: this is a small sample ({n_days} delivery days in one winter "
        f"month). Errors in neighbouring hours move together, so there are far "
        f"fewer independent data points than hours. Treat these figures as "
        f"indicative, not as long-run guarantees."
    )
    return findings
