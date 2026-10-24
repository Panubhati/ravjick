# Assumptions

Every assumption made while building the portal is listed here. Each entry
gives the phase it was made in and how it was checked.

## Given by the specification

| # | Assumption | Notes |
|---|---|---|
| S1 | All times are UTC. In January this equals UK local time (GMT). | Confirmed: all API timestamps end in `Z`. |
| S2 | The default decision cutoff is 09:00 UTC on D-1, adjustable from 06:00 to 12:00. | Day-ahead auctions close on the morning of D-1. |

## Phase 2: ingestion

| # | Assumption | How checked or why |
|---|---|---|
| A1 | `settlementDateFrom` and `settlementDateTo` on FUELHH are both inclusive. | A 7-day range returned 7 x 48 = 336 rows. |
| A2 | It doesn't matter whether `publishDateTimeTo` on WINDFOR is inclusive. | Weekly chunks share boundary instants, and dedupe removes any overlap. All chunk boundaries are at 00:00, when nothing is published, so no overlap occurred. |
| A3 | The deduplication key is `start_time` for actuals (one value per half-hour) and `(start_time, publish_time)` for forecasts. | Exact duplicates are dropped. If one key has two different values, ingestion stops with an error instead of picking one. No duplicates of either kind were seen. |
| A4 | The API fields are exactly those in Section 4. | The pydantic models use `extra="forbid"`, so a new or renamed field stops ingestion instead of being silently ignored. |
| A5 | The late-December actuals (2025-12-30 and 2025-12-31) are fetched now, so the optional D-2 baseline (Section 6.4) needs no new ingestion. | Agreed with the project owner. They are stored in a separate file, so the January file stays at exactly 1,488 rows. |
| A6 | `forecasts.csv` keeps every row in the publish window, including target hours outside January (2025-12-28 to 2026-02-01). | The ingest step does not filter by target hour. Filtering happens in the analysis code, so the stored data matches the source. |
| A7 | The constant columns `dataset` and `fuelType` are validated, then dropped from the CSVs. | They carry no information after validation. |
| A8 | The coverage check in ingestion only tests whether data is *available* (at least one publish at or before the cutoff for each target hour). | The per-hour selection is implemented and tested separately in `app/decision.py` (Phase 3). |
| A9 | The 12:25 publish on 2026-01-15 is a late 11:30 publish. It is kept as-is, with no adjustment. | It is the only publish not at :30, and the 11:30 slot that day is empty. It only changes which forecast is selected for delivery 2026-01-16 at cutoff 12:00. |

## Phase 3: core logic

| # | Assumption | How checked or why |
|---|---|---|
| B1 | A WINDFOR value at `startTime` H is the average MW over the hour H to H+1. | Given in spec 5.4. It is the basis for comparing it with the mean of the H and H+30min actuals. |
| B2 | A forecast can be used the moment it is published. `publish_time <= cutoff` (inclusive) is the only availability test, with no allowance for delivery delay. | Spec 5.2. In this data, the publish used at each cutoff is always at least 0.5 h before it. |
| B3 | A delivery day is 24 hours, 00:00 to 23:00 UTC. | January has no clock change, so every day has 24 hours. |
| B4 | A missing forecast hour has `forecast_mw`, `publish_time` and `horizon_h` set to null and `missing = true`. It is never filled from a later publish or by interpolation. | Unit-tested. No hours are missing in January at any cutoff. |
| B5 | `hourly_actuals` returns rows only for hours that have at least one half-hour. Callers left-join on `target_time`, so hours with no actuals at all also come out as null. | Unit-tested. All 744 January hours are complete. |

## Phase 4: metrics

| # | Assumption | How checked or why |
|---|---|---|
| C1 | Percentiles and quantiles use linear interpolation (the pandas/numpy default). | Unit tests use hand-computed values with the same method. |
| C2 | Normalised MAE = MAE / mean actual over the matched hours in the selected range. | Spec 6.1. |
| C3 | Wind-level terciles are computed from the matched actuals in the selected range, so the thresholds change with the range. Low means actual <= first threshold; medium means actual <= second threshold; high is anything above. | Spec 6.2 asks for the thresholds to be returned, so the UI can show them. |
| C4 | Horizon buckets include their upper edge, (0, 6], (6, 12] and so on, and 48h+ is anything above 48 h. | All real horizons end in .5 h, so no value falls on an edge. |
| C5 | The horizon analysis filters on target hours in the date range and ignores the cutoff. | Spec 6.3: it uses all forecast rows, not only the decision forecast. |
| C6 | The baseline is the actual at the same hour two days earlier. It is compared with the forecast on exactly the same hours. | Spec 6.4. The D-2 actual is fully known at a D-1 morning cutoff. |
| C7 | The findings describe how consistent the bias is (share of hours and days over-forecast) but include no significance test. | Errors in neighbouring hours are strongly correlated, so a naive test would overstate certainty. The caveat sentence says so. |
| C8 | `n_missing_actual` counts every hour in the range with no actual, including hours that also have no forecast. | No hours are missing in January, so this has no effect on results. |
