# Data notes

All times are UTC. In January the UK is on GMT, so UTC equals UK local time.

Source: Elexon Insights API, `https://data.elexon.co.uk/bmrs/api/v1` (no key).
The data is fetched once by `backend/scripts/ingest.py` and committed as CSV
files in `backend/data/processed/`. The app never calls Elexon at runtime.

To re-run ingestion (from `backend/`): `python -m scripts.ingest`. It prints the
validation report summarised below and exits non-zero if a check fails.

## Files

| File | Rows | Content |
|---|---|---|
| `actuals_half_hourly.csv` | 1,488 | FUELHH, fuel type WIND, settlement dates 2026-01-01 to 2026-01-31 |
| `actuals_half_hourly_baseline.csv` | 96 | Same, 2025-12-30 to 2025-12-31 (for the optional D-2 baseline) |
| `forecasts.csv` | 19,272 | WINDFOR, published 2025-12-29T00:00Z to 2026-01-31T00:00Z |

Columns:

- Actuals: `start_time`, `publish_time`, `settlement_date`, `settlement_period`, `generation_mw`
- Forecasts: `publish_time`, `start_time`, `generation_mw`

Timestamps are ISO 8601 with a `Z` suffix. The constant columns `dataset` and
`fuelType` are validated during ingestion, then dropped.

## Validation results (ingestion run on 2026-10-24)

### Actuals (FUELHH WIND)

- 1,488 January rows, which is 31 days x 48 periods. There are no missing
  half-hours, no duplicate `start_time` values and no nulls.
- Every row satisfies `start_time = settlement_date + (settlement_period - 1) x 30 min`.
  Because January is on GMT, there are no 46- or 50-period clock-change days.
- Generation ranges from 1,695 MW (2026-01-08 12:30) to 17,805 MW. The mean is 11,581 MW.
- The late-December baseline file has all 96 expected rows.

### Forecasts (WINDFOR)

- There are 19,272 rows from 264 distinct publishes. There are no duplicate
  `(start_time, publish_time)` pairs and no negative values.
- **Every publish has exactly 73 hourly target rows.** This is why each
  7-day request returned exactly 4,088 rows (8 publishes x 7 days x 73 rows).
  The constant count is a property of the data, not a response cap: 264
  publishes x 73 rows = 19,272, the same as the total fetched.
- **Publish schedule:** 8 publishes per day, at 02:30, 04:30, 07:30, 09:30,
  11:30, 15:30, 18:30 and 22:30 UTC.
- **Quirk:** on 2026-01-15 the 11:30 publish is missing. A publish at **12:25**
  appears in its place. It is the only publish not at :30. See the cutoff
  table below for its effect.
- All target times are on the hour (hourly resolution). Actuals are half-hourly.
- Horizon (`start_time - publish_time`) runs from -25.5 h to +66.5 h. Each
  publish covers about 25 h in the past to about 66 h ahead. 3,961 rows (21%)
  have a negative horizon. The cutoff filter removes them automatically.
- All 744 January target hours have forecasts. 14,287 January-target rows have
  a positive horizon and are available for the horizon analysis (Section 6.3).
- Each target hour has between 8 and 32 forecasts (median 24).

### Decision-forecast coverage

All 31 January delivery days have all 24 target hours covered at **every**
cutoff from 06:00 to 12:00. There are no exceptions to log.

Because the publish schedule is fixed, each cutoff maps to one publish on D-1:

| Cutoff (D-1) | Publish used | Age at cutoff |
|---|---|---|
| 06:00, 07:00 | 04:30 | 1.5 h, 2.5 h |
| 08:00, 09:00 | 07:30 | 0.5 h, 1.5 h |
| 10:00, 11:00 | 09:30 | 0.5 h, 1.5 h |
| 12:00 | 11:30 | 0.5 h (exception: delivery 2026-01-16 uses 09:30, because the 11:30 publish was late) |

This table comes from the publish schedule. The checker confirmed it at
09:00: every day's latest eligible publish was exactly 1.5 h before the cutoff.
Phase 3 will confirm it per hour using `decision.py`.

Consequence for analysis: the 7 cutoffs in the sensitivity analysis only
produce **4 distinct forecasts** per day. The analysis will be step-shaped and
should be presented that way.

Golden example (Section 4.3) reproduced: for delivery 2026-01-03 at cutoff
09:00, the latest eligible publish is 2026-01-02T07:30Z and covers 24 of 24 hours.
