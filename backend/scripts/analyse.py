"""Reproduce the full January analysis (spec Section 6) from the committed CSVs.

Usage (from the backend/ folder):
    python -m scripts.analyse            # default cutoff 09:00
    python -m scripts.analyse 10:00      # another cutoff

Prints the result tables and the headline findings.
"""

import sys
from datetime import time

import pandas as pd

from app import config
from app.data_loader import load_forecasts, load_hourly_actuals
from app.metrics import headline_findings, run_analysis


def table(df: pd.DataFrame) -> str:
    return df.to_string(index=False, float_format=lambda x: f"{x:,.0f}")


def main() -> int:
    cutoff = (
        time.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else config.DEFAULT_CUTOFF
    )
    results = run_analysis(
        load_forecasts(),
        load_hourly_actuals(),
        config.MIN_DATE,
        config.MAX_DATE,
        cutoff,
        sensitivity_cutoffs=config.CUTOFF_OPTIONS,
    )

    period = f"{config.MIN_DATE} to {config.MAX_DATE}"
    print(f"# Analysis: {period}, cutoff {cutoff:%H:%M} UTC\n")
    print("## Overall\n")
    overall = pd.DataFrame([results["overall"]]).T.reset_index()
    overall.columns = ["metric", "value"]
    print(overall.to_string(index=False))
    print("\n## By hour of day\n")
    print(table(results["by_hour"]))
    print("\n## By wind level\n")
    print(f"Thresholds: {results['wind_thresholds']}\n")
    print(table(results["by_wind_level"]))
    print("\n## By delivery day\n")
    print(table(results["by_day"]))
    print("\n## By forecast horizon (all forecasts, horizon > 0)\n")
    print(table(results["by_horizon"]))
    print("\n## Cutoff sensitivity\n")
    print(table(results["cutoff_sensitivity"]))
    print("\n## Baseline (actual two days earlier)\n")
    print(results["baseline"])
    print("\n## Headline findings\n")
    for finding in headline_findings(results):
        print(f"- {finding}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
