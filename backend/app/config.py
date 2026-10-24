"""Project-wide constants. All times are UTC (equal to UK time in January)."""

from datetime import UTC, date, datetime, time
from pathlib import Path

# Delivery days the portal supports.
MIN_DATE = date(2026, 1, 1)
MAX_DATE = date(2026, 1, 31)

# Decision cutoff on D-1 (Section 5.1) and the options offered in the UI.
DEFAULT_CUTOFF = time(9, 0)
CUTOFF_OPTIONS = [time(h, 0) for h in range(6, 13)]

# Ingestion windows (Section 10, Phase 2).
ACTUALS_FROM = MIN_DATE
ACTUALS_TO = MAX_DATE
# Two extra days of actuals for the naive D-2 baseline (Section 6.4).
BASELINE_ACTUALS_FROM = date(2025, 12, 30)
BASELINE_ACTUALS_TO = date(2025, 12, 31)
FORECASTS_PUBLISHED_FROM = datetime(2025, 12, 29, tzinfo=UTC)
FORECASTS_PUBLISHED_TO = datetime(2026, 1, 31, tzinfo=UTC)

# Elexon Insights API (Section 4). Only used by the offline ingest script.
ELEXON_BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
ACTUALS_CSV = PROCESSED_DIR / "actuals_half_hourly.csv"
BASELINE_ACTUALS_CSV = PROCESSED_DIR / "actuals_half_hourly_baseline.csv"
FORECASTS_CSV = PROCESSED_DIR / "forecasts.csv"
