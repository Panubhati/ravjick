"""Decision-time forecast selection: the core of the portal.

The buying decision for delivery day D is made at a cutoff time on D-1. Only
forecasts published at or before that moment were available, so for each target
hour we take the most recent of those. Taking a newer forecast would leak
information from the future (look-ahead bias).

Pure pandas, no web framework, so it is easy to test and explain.
"""

from datetime import UTC, date, datetime, time, timedelta

import pandas as pd

OUTPUT_COLUMNS = ["target_time", "forecast_mw", "publish_time", "horizon_h", "missing"]


def cutoff_datetime(delivery_date: date, cutoff: time) -> pd.Timestamp:
    """The moment the decision is made: `cutoff` on the day before delivery (UTC)."""
    return pd.Timestamp(
        datetime.combine(delivery_date - timedelta(days=1), cutoff, UTC)
    )


def select_decision_forecast(
    forecasts: pd.DataFrame, delivery_date: date, cutoff: time
) -> pd.DataFrame:
    """Return the forecast available at the cutoff for each hour of `delivery_date`.

    `forecasts` has columns publish_time, start_time (UTC) and generation_mw.

    The result always has 24 rows, one per target hour, with columns
    target_time, forecast_mw, publish_time, horizon_h and missing. If no
    forecast was published by the cutoff for an hour, that hour is flagged
    missing. It is never filled from a later publish.
    """
    decision_time = cutoff_datetime(delivery_date, cutoff)
    target_hours = pd.date_range(
        datetime.combine(delivery_date, time(0, 0), UTC), periods=24, freq="h"
    )

    # 1. Keep only forecasts for this day that were published by the cutoff.
    available = forecasts[
        (forecasts["publish_time"] <= decision_time)
        & (forecasts["start_time"].isin(target_hours))
    ]

    # 2. For each target hour, keep the most recently published of those.
    latest = available.sort_values("publish_time").groupby("start_time").tail(1)

    # 3. Line up against all 24 hours so gaps show up as missing rows.
    result = pd.DataFrame({"target_time": target_hours}).merge(
        latest, left_on="target_time", right_on="start_time", how="left"
    )
    result["forecast_mw"] = result["generation_mw"].astype("float64")
    result["publish_time"] = pd.to_datetime(result["publish_time"], utc=True)
    result["horizon_h"] = (
        result["target_time"] - result["publish_time"]
    ).dt.total_seconds() / 3600
    result["missing"] = result["forecast_mw"].isna()
    return result[OUTPUT_COLUMNS]
