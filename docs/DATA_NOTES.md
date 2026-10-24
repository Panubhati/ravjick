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
Phase 3 confirmed it per hour with `decision.py`: all 744 hours at every cutoff use the publish shown (12:00: 720 hours use 11:30, the 24 hours of 2026-01-16 use 09:30).

Consequence for analysis: the 7 cutoffs in the sensitivity analysis only
produce **4 distinct forecasts** per day. The analysis will be step-shaped and
should be presented that way.

Golden example (Section 4.3) reproduced: for delivery 2026-01-03 at cutoff
09:00, the latest eligible publish is 2026-01-02T07:30Z and covers 24 of 24 hours.

## Headline findings (Phase 4)

Reproduce with `python -m scripts.analyse` from `backend/` (cutoff 09:00, 1 to 31 January).

- Across 31 delivery days (744 hours), the forecast available at the 09:00 cutoff on the day before was off by 2,142 MW on average. That is 18.5% of average wind output (11,581 MW). RMSE is 2,612 MW.
- On average the forecast was 1,852 MW too high. Wind came in below forecast in 85% of hours, and on 27 of 31 days the forecast was too high on average.
- To be covered in 9 hours out of 10, plan for up to 4,300 MW less wind than forecast (5,307 MW for 19 hours out of 20).
- Errors are largest at 05:00 (2,535 MW), 03:00 (2,516 MW) and 04:00 (2,507 MW) UTC, and smallest at 21:00 (1,883 MW). The over-forecast is larger overnight (bias about 2,400 MW at 02:00 to 06:00) than in the afternoon (about 1,400 MW).
- The worst day was 28 January (average miss 5,375 MW). The best was 19 January (736 MW, and one of only 4 days with a negative bias).
- By wind level, the average miss is 1,886 MW when wind is low (up to 9,367 MW), 2,097 MW when medium and 2,443 MW when high (above 14,670 MW).
- Average miss by how far ahead the forecast was made: 0-6h 1,791 MW, 6-12h 1,846 MW, 12-24h 2,005 MW, 24-36h 2,136 MW, 36-48h 2,351 MW, 48h+ 2,381 MW. Accuracy gets steadily worse with lead time.
- The forecast is too high at every lead time, even 0 to 6 hours ahead (by 1,558 MW on average), so the over-forecast is not only a long-range effect.
- The cutoff matters little. Moving it from 06:00 to 12:00 changes the average miss from 2,139 MW to 2,018 MW and the 90% buffer from 4,329 MW to 4,001 MW. From 06:00 to 11:00 the average miss stays within 2,123 to 2,142 MW.
- A naive guess ("same as two days earlier") misses by 4,303 MW on average over the same 744 hours, against 2,142 MW for the forecast. The forecast halves the error.
- Caveat: this is a small sample (31 delivery days in one winter month). Errors in neighbouring hours move together, so there are far fewer independent data points than hours. Treat these figures as indicative, not as long-run guarantees.

Note on percentiles: the absolute and signed P90 and P95 are identical (4,300 and 5,307 MW), because every one of the largest 10% of misses is an over-forecast. The largest under-forecast is 3,550 MW.

### Open question: why is the forecast too high so consistently?

A bias of about +1.5 GW even for forecasts made 0 to 6 hours ahead looks more like the two datasets measuring slightly different things than like forecasting skill. Possible explanations, **none verified**:

- The two datasets may not cover exactly the same set of wind farms.
- The actuals may reflect output after wind farms were told to reduce output (curtailment), while the forecast may describe what the wind could have produced. The bias is larger at high wind, which fits this explanation.

Checking either one needs Elexon documentation or other datasets, both outside the agreed scope. Until then, the portal reports errors exactly as defined, and the buffer includes this bias, which is the right number for a buyer who relies on this forecast.
