import pandas as pd
import pytest

from app import config


@pytest.fixture(scope="session")
def real_forecasts() -> pd.DataFrame:
    """The committed WINDFOR data, used for regression tests."""
    return pd.read_csv(config.FORECASTS_CSV, parse_dates=["publish_time", "start_time"])


@pytest.fixture(scope="session")
def real_actuals() -> pd.DataFrame:
    """The committed January FUELHH WIND data."""
    return pd.read_csv(config.ACTUALS_CSV, parse_dates=["start_time", "publish_time"])
