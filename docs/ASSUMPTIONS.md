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

## Phase 5: API

| # | Assumption | How checked or why |
|---|---|---|
| D1 | *(Revised in the improvement pass, see F1.)* The API originally accepted any valid `HH:MM` cutoff. | Spec 8 only requires the HH:MM format. |
| D2 | The shortfall buffer in `/api/decision-forecast` comes from the January errors at the *same cutoff* as the request. | Spec 8: "based on the whole-January error distribution". Using the same cutoff keeps the buffer consistent with the forecast shown. |
| D3 | `/api/error-by-horizon` and `/api/cutoff-sensitivity` take no cutoff parameter. | By definition they use all forecasts, or all cutoffs. |
| D4 | `from` and `to` default to the whole of January. `delivery_date` is required. A range where `from` is after `to` returns 422. | Spec 9.2: the default range is the whole month. |
| D5 | Results are cached in memory for each (range, cutoff). | The data is static. The first full `/api/metrics` call takes about 1.5 s; repeat calls are instant. |
| D6 | `CORS_ORIGINS` (comma-separated) defaults to `http://localhost:5173`, the Vite dev server. `STATIC_DIR` defaults to `frontend/dist`, which is only mounted if it exists. | Spec 8: CORS origins come from the environment. |
| D7 | Our own range errors return 422 with a string `detail`. FastAPI's format errors return 422 with a list `detail`. | Both are 422, as spec 8 requires. The front end displays either kind. |
| D8 | Metric fields keep the metrics-module names (`mae`, `bias`, `buffer_90`), with MW stated in the OpenAPI descriptions. Per-hour values use a `_mw` suffix. | This keeps names identical across code, API and docs. |

## Phase 6: front end

| # | Assumption | How checked or why |
|---|---|---|
| E1 | The Decision Planner opens on delivery day 15 January at the 09:00 cutoff. | A mid-month day that shows a typical forecast. The user can change both. |
| E2 | The cutoff and the date range are shared across the three views. | Switching tabs keeps the user's choices, so the views stay consistent. |
| E3 | The shaded band runs from forecast − 90% buffer up to the forecast, and never goes below 0 MW. | Spec 9.1. Wind output cannot be negative. |
| E4 | The error histogram uses 500 MW bins, built in the browser from `/api/series`. | This avoids an extra endpoint. 744 values are a small payload. |
| E5 | Date pickers are the browser's native date input, so the date format follows the viewer's locale (for example 15-01-2026). Every time shown in text and charts is formatted in UTC. | Native inputs are accessible and work on phones. Times never use the viewer's local time zone. |
| E6 | The Methodology panel mentions the unexplained over-forecast (see DATA_NOTES, open question) as a known caveat. | Honest reporting. It does not claim a cause. |
| E7 | In development, Vite forwards `/api` to `http://localhost:8000`. `VITE_API_BASE_URL` is empty when one server hosts both the front end and the API. | Spec 9.4. |

## Improvement pass (performance, security, UI, accuracy)

| # | Assumption | How checked or why |
|---|---|---|
| F1 | The API accepts only the 7 listed cutoffs (06:00 to 12:00 on the hour). Other well-formed times return 422 and list the allowed values. | This limits the work any request can cause: an attacker could otherwise keep the server busy with new cutoff values. It also matches the UI. Agreed with the project owner. |
| F2 | 90% confidence ranges for MAE, bias and the 90% buffer come from resampling whole delivery days (1,000 resamples, fixed seed 0, so results are repeatable). | Whole days are resampled, not single hours, because errors in neighbouring hours move together. Unit-tested on hand-made data. |
| F3 | The shortfall buffer stays calibrated on the whole of January, as the spec asks. It is labelled as a hindsight estimate in the UI, the findings and the Methodology panel. | Using errors from days after the decision is look-ahead. A live system would use only errors already known at decision time. |
| F4 | The "Typical bias" card on the Planner shows the January bias at the selected cutoff. | It tells the buyer the forecast usually ran high, which a single buffer number hides. |
| F5 | Results for the default range are computed at start-up (about 2.3 s). Other ranges are computed on first request and cached. | This keeps first page loads fast. Hosting platforms allow far longer start-up times. |
| F6 | Responses over 1 KB are gzipped. Hashed static assets are cached for a year; `index.html` is always revalidated. | Standard practice. Asset file names change on every build. |
| F7 | Security headers: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and a strict Content-Security-Policy. The CSP allows inline styles because the chart library needs them. `/docs` and `/redoc` are exempt from the CSP. | Swagger UI loads its scripts from a CDN, and the spec requires `/docs` to work. The browser check showed no CSP violations. |
| F8 | The browser keeps successful API responses for the life of the page, and forgets failed ones so Retry works. | The data is static. Switching tabs makes no new requests (verified). |
| F9 | The view (tab, date, cutoff, range) is mirrored in the URL. Invalid values fall back to defaults one field at a time. | Links can be shared and bookmarked, which also helps in the demo video. |
| F10 | Back-end direct dependencies are pinned to exact versions. | Builds are reproducible and auditable. npm already uses `package-lock.json`. |
| F11 | The bias explanation is based on documentation only: coverage mismatch not supported, curtailment likely but unproven. See DATA_NOTES, which also records an unresolved one-hour offset between documented and observed publish times (the default 09:00 cutoff is safe either way). | No new datasets were added, in line with the agreed scope. |
| F12 | Headings named in the spec are used exactly as written: the views (Decision Planner, Forecast Performance, Error Insights), the Methodology panel, the banner wording, the KPI labels (Peak forecast hour, Average forecast, Shortfall buffer (90%), MAE, RMSE, Bias, Normalised MAE), Hourly values, Key findings and the Error Insights chart titles. Subtitles, hints, explanations and the footer use plain language for non-technical buyers. | Requested by the project owner: keep spec headings, explain them in everyday words. |

## Extras (beyond the spec)

| # | Assumption | How checked or why |
|---|---|---|
| G1 | Look-ahead check: the "cheating" comparison uses, for each target hour, the newest forecast published strictly before the hour began (horizon > 0). | It shows what look-ahead leakage would do to the numbers. Unit-tested. Real data: MAE 1,814 MW vs 2,142 MW at the 09:00 cutoff. |
| G2 | Buffer without hindsight: for delivery day D, the 90% buffer uses the decision errors of all days up to D-2. D-1 is not yet complete at a morning cutoff. The window grows over time, and the 30-31 December decisions provide the first history. At least 2 complete earlier days are required, so 1 January has no value. | No look-ahead. Unit-tested, including that future days never change an earlier buffer. Real data: average 4,104 MW, covered 86% of hours against a 90% target over 30 days. |
| G3 | Buy calculator: demand is one flat MW figure for all 24 hours, entered by the user (default 30,000 MW, an example only). Buy = demand − forecast; with buffer = demand − max(0, forecast − buffer). Hours with no forecast count on no wind. Daily totals are in MWh (hourly MW summed). | This turns the example in spec Section 2 into a tool. No price or demand data is added; the user supplies the demand figure. |
| G4 | Key findings show the first 4 sentences plus the closing small-sample caveat, with "Show all" for the rest. On the Decision Planner the KPI cards stay above the chart (the project owner preferred them as a summary at the top), and the buy calculator is collapsed by default. After 4 s of loading, a note says the server may be waking up. | UX pass: lead with the main message, keep the honesty caveat always visible, and handle cold starts on free hosting (spec Section 12). |

## Phase 7: Docker and deployment

| # | Assumption | How checked or why |
|---|---|---|
| H1 | One Docker image: Node 22 builds the front end; python:3.12-slim serves the API and the built files with uvicorn on `$PORT` (default 8000), as a non-root user. `CORS_ORIGINS` is empty in the image because one origin serves everything. | Built and run locally with docker compose (281 MB image, health check healthy). All browser checks pass against the container. |
| H2 | `docker-compose.yml` publishes `${HOST_PORT:-8000}`, so a machine where port 8000 is taken can use another port, e.g. `HOST_PORT=8090`. | Port 8000 is taken on the development machine. |
| H3 | Deployment target: **Vercel** (the spec's fallback). Heroku, the spec's primary target, no longer has a free plan. The React build is served as static files; FastAPI runs as one Python serverless function (`api/index.py`) bundled with the processed CSVs. Heroku is not used, so there is no Heroku config; the Docker image runs on any container host. | Chosen by the project owner. The entry point was tested without the start-up hook (the cold-start case): all endpoints return 200. |
| H4 | On Vercel, security headers for static files are set in `vercel.json`, mirroring the app's own headers, with `/docs` and `/redoc` exempt from the CSP. `.vercelignore` keeps local-only files (the spec document, the phase-1 script and the root `data/` folder) from being uploaded. | Anonymity requirement (spec Section 0) and consistent security headers. |
