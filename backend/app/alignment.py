"""Turn half-hourly actual wind generation into hourly values.

Forecasts are hourly: a forecast at 10:00 is the average MW for 10:00-11:00.
Actuals are half-hourly, so the hourly actual for 10:00 is the mean of the
10:00 and 10:30 values. If either half-hour is missing, the hourly value is
null. We never guess it from one half.
"""

import pandas as pd


def hourly_actuals(half_hourly: pd.DataFrame) -> pd.DataFrame:
    """Convert half-hourly actuals to hourly averages.

    `half_hourly` has columns start_time (UTC) and generation_mw.

    Returns columns target_time (start of the hour) and actual_mw, sorted by
    hour. It has one row for every hour that has at least one half-hour.
    actual_mw is null unless both half-hours are present.
    """
    if half_hourly["start_time"].duplicated().any():
        raise ValueError("half-hourly actuals contain duplicate start_time values")

    hour = half_hourly["start_time"].dt.floor("h")
    grouped = half_hourly.groupby(hour)["generation_mw"]
    result = pd.DataFrame({"actual_mw": grouped.mean(), "half_hours": grouped.count()})
    result.loc[result["half_hours"] != 2, "actual_mw"] = float("nan")
    result = result.rename_axis("target_time").reset_index()
    return result[["target_time", "actual_mw"]]
