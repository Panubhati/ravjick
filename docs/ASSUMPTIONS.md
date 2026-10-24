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
