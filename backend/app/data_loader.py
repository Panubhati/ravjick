"""Load the processed CSV files written by scripts/ingest.py."""

from dataclasses import dataclass
from functools import cache

import pandas as pd

from app import config
from app.alignment import hourly_actuals


def load_forecasts() -> pd.DataFrame:
    """All WINDFOR rows: publish_time, start_time (UTC), generation_mw."""
    return pd.read_csv(config.FORECASTS_CSV, parse_dates=["publish_time", "start_time"])


def load_half_hourly_actuals() -> pd.DataFrame:
    """January FUELHH WIND rows, half-hourly."""
    return pd.read_csv(config.ACTUALS_CSV, parse_dates=["start_time", "publish_time"])


def load_hourly_actuals() -> pd.DataFrame:
    """Hourly actuals for January plus 30-31 December (for the D-2 baseline)."""
    half_hourly = pd.concat(
        [
            pd.read_csv(config.BASELINE_ACTUALS_CSV, parse_dates=["start_time"]),
            load_half_hourly_actuals(),
        ],
        ignore_index=True,
    )
    return hourly_actuals(half_hourly)


@dataclass(frozen=True)
class Dataset:
    forecasts: pd.DataFrame
    hourly_actuals: pd.DataFrame
    n_half_hourly_actuals: int


@cache
def get_dataset() -> Dataset:
    """Load everything once and keep it in memory. The data never changes."""
    return Dataset(
        forecasts=load_forecasts(),
        hourly_actuals=load_hourly_actuals(),
        n_half_hourly_actuals=len(load_half_hourly_actuals()),
    )
