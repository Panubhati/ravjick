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

### Uncertainty of the headline numbers

90% ranges from resampling whole delivery days (1,000 resamples, seed 0; `metrics.bootstrap_ci`). Whole days are resampled because errors in neighbouring hours move together:

| Metric (09:00 cutoff) | Value | 90% range |
|---|---|---|
| MAE | 2,142 MW | 1,789 to 2,544 MW |
| Bias | +1,852 MW | +1,406 to +2,340 MW |
| 90% shortfall buffer | 4,300 MW | 3,433 to 5,285 MW |

The bias is clearly above zero even at the bottom of its range. The buffer, however, could plausibly be anywhere from about 3.4 to 5.3 GW on this sample.

### Why is the forecast too high so consistently? (documentation research)

A bias of about +1.5 GW even for forecasts made 0 to 6 hours ahead looks more like the two datasets measuring slightly different things than like poor forecasting. We researched the documentation only; no new datasets were used.

**A coverage mismatch is not supported.** Both datasets are documented as covering wind farms with operational metering, which excludes embedded (distribution-connected) wind:

- WINDFOR: "This provides wind generation forecast for wind farms which are visible to the ESO and have operational metering." (Elexon Insights API specification, https://data.elexon.co.uk/swagger/v1/swagger.json)
- FUELHH: National Grid's generation-by-fuel-type data uses "half-hourly operational metering", and "generation units connected to the low voltage distribution system ('embedded' generation) are excluded from operational metering." (DECC Energy Trends article, September 2012, https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/65923/6487-nat-grid-metering-data-et-article-sep12.pdf)

Small differences in exactly which wind farms are included remain possible but are not documented.

**Curtailment is the likely cause, but not proven.**

- When NESO measures the accuracy of its own day-ahead wind forecast, it compares against metered output only for sites that "did not have a bid-offer acceptance (BOA)", i.e. sites that were not instructed to change output (NESO RIIO-2 BP2 Incentives Report, November 2024, metric 1C, https://www.neso.energy/document/350301/download). This suggests the forecast predicts output *before* curtailment, while FUELHH records metered output *after* it.
- Curtailment is large: "In 2024/25, wind curtailment volumes increased to 13% of hypothetical wind outturn (wind outturn if no curtailment had taken place)" (NESO Annual Balancing Costs Report 2025, https://www.neso.energy/document/362561/download).

13% of ~11.6 GW would be about 1.5 GW, roughly the size of the bias, and curtailment is concentrated at high wind, where our bias is largest. These two points are our inference, not a documented fact. No document says outright that WINDFOR is an unconstrained forecast.

**How it could be proven later (outside the current scope):** add curtailed volumes back to FUELHH, for example from bid-offer acceptance data for wind units, and check whether the gap closes.

**What the portal does:** it reports errors exactly as defined. The buffer therefore includes this bias, which is the right number for a buyer who relies on this forecast as published. The Methodology panel describes curtailment as the likely, unproven cause.

### Possible publish-time offset (not resolved)

The same API specification says WINDFOR is "published by NGESO up to 8 times a day at 03:30, 05:30, 08:30, 10:30, 12:30, 16:30, 19:30 and 23:30". Our data carries `publishTime` values exactly one hour earlier: 02:30, 04:30, 07:30 and so on, in UTC. The documented times may be UK summer time (BST = UTC+1), which would match our data exactly. We have not confirmed this.

If instead forecasts became available an hour after their `publishTime`, the cutoffs at 08:00, 10:00 and 12:00 would be using forecasts that were not yet available, i.e. look-ahead. **The default 09:00 cutoff is safe either way**: its forecast is stamped 07:30, which is no later than 08:30 even with the offset. The 06:00, 07:00 and 11:00 cutoffs are also safe.

### Extras: look-ahead check and buffer without hindsight (09:00 cutoff)

| | At the 09:00 cutoff (what the buyer had) | Newest forecast before each hour (look-ahead) |
|---|---|---|
| MAE | 2,142 MW | 1,814 MW |
| Bias | +1,852 MW | +1,608 MW |
| 90% buffer | 4,300 MW | 3,781 MW |
| Median hours ahead | 28 | 1.5 |

Peeking at later forecasts would make the forecast look about 15% more accurate. The portal never does this.

**Buffer without hindsight.** Each day's buffer was built only from errors of days up to D-2. It averaged 4,104 MW and covered the shortfall in 86% of hours, against a 90% target, over 30 days. The first days are weak: on 2 January only two December days of history were available, so the buffer was 1,183 MW and covered none of that day's 24 hours. From 3 January it stays between 3,852 and 4,749 MW. A live service would want a longer history before relying on it.
