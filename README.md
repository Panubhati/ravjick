# Wind Forecast Portal

A pilot web portal for the day-ahead power-buying team of a UK energy utility. The team decides
on the morning before delivery how much electricity to buy; whatever wind does not cover must
be bought elsewhere. The portal shows **the wind forecast exactly as it stood at that decision
moment**, never a newer one that would leak information from the future, and measures how far
those forecasts missed in January 2026. From the misses it derives a **shortfall buffer** buyers
can add as a safety margin. National wind only, Elexon data only.

**Live app:** _link added after deployment_
· **API docs:** `/docs` on the same host

## What you can do

| View | Purpose |
|---|---|
| **Decision Planner** | Pick a delivery day and a cutoff (06:00–12:00 on the day before). See which forecast was available and when it was published, the 24-hour forecast with a 90% shortfall band, KPI cards, a "how much to buy" calculator, and an hourly table with CSV download. A toggle overlays what actually happened. |
| **Forecast Performance** | Forecast vs actual over any January range, MAE / RMSE / bias / normalised MAE with 90% uncertainty ranges, and the signed error per day. |
| **Error Insights** | Key findings, error histogram with the buffer marked, error by hour, wind level and forecast horizon, cutoff sensitivity, a look-ahead check and a buffer built without hindsight. |

Selections live in the URL, so any view can be shared as a link.

## Quick start

**Docker** (production-like: one container serves the API and the built front end):

```sh
docker compose up --build          # open http://localhost:8000
HOST_PORT=8090 docker compose up --build   # if port 8000 is taken
```

**Local development** (two terminals):

```sh
# 1. API on :8000 (Python 3.12)
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt      # Windows: .venv\Scripts\pip
.venv/bin/uvicorn app.main:app --reload

# 2. Front end on :5173 (Node 22); Vite forwards /api to :8000
cd frontend
npm install
npm run dev
```

If the API runs on another port, start the front end with `VITE_API_BASE_URL=http://localhost:<port>`.

## Data and re-running ingestion

The app never calls Elexon at runtime. `backend/scripts/ingest.py` fetched the data once, in
weekly chunks with retries, validated every row with pydantic and wrote
`backend/data/processed/*.csv`, which are committed:

| File | Rows | Content |
|---|---|---|
| `actuals_half_hourly.csv` | 1,488 | FUELHH, fuel type WIND, 1–31 Jan 2026 (no gaps) |
| `actuals_half_hourly_baseline.csv` | 96 | Same, 30–31 Dec 2025 (history for baseline and no-hindsight buffer) |
| `forecasts.csv` | 19,272 | WINDFOR, published 29 Dec 2025 – 31 Jan 2026 |

```sh
cd backend
.venv/bin/python -m scripts.ingest     # re-fetch (network), validate, print report
.venv/bin/python -m scripts.analyse    # reproduce every number and finding
```

Data quirks (fixed publish schedule, one late publish, possible documented-time offset) are in
[docs/DATA_NOTES.md](docs/DATA_NOTES.md).

## Key design decisions

- **Decision-time selection (no look-ahead).** For each hour of delivery day D, take the forecast
  with the latest `publish_time` **at or before the cutoff on D-1**. If none exists, the hour is
  flagged missing and never filled from a later forecast. This lives in a pure, separately tested
  module: `backend/app/decision.py`.
- **Hourly alignment.** Forecasts are hourly, actuals half-hourly. The actual for hour H is the
  mean of H and H+30 min; if either is missing the hour is excluded.
- **Sign convention.** `error = forecast − actual`. Positive means less wind than forecast: the
  buyer is short and must buy extra.
- **Shortfall buffer (90%).** `max(0, 90th percentile of error)`: buying this much extra would
  have covered 9 hours in 10. It is measured over all of January (hindsight), so the portal also
  shows a **buffer without hindsight** built only from days already finished at each cutoff.
- **Times are UTC**, which equals UK time in January.
- **Static data, cached results.** CSVs load once at start-up; results are cached per date range
  and cutoff. The API only accepts the seven listed cutoffs, which bounds the work per request.

Every assumption, with how it was checked, is in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).
How the pieces fit together is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Headline results (09:00 cutoff, January 2026)

- Average miss (MAE) **2,142 MW**, 18.5% of average wind output (90% range 1,789–2,544 MW).
- The forecast ran **high in 85% of hours** (bias +1,852 MW). The documentation suggests wind
  curtailment as the likely, unproven cause; a coverage mismatch is not supported.
- **Shortfall buffer: 4,300 MW.** Built without hindsight it covered 86% of hours (target 90%).
- Peeking at forecasts published after the cutoff would make the MAE look like 1,814 MW: the
  look-ahead trap the portal avoids.
- The forecast halves the error of a naive "same as two days earlier" guess (4,303 MW).

## Repository guide

```
backend/
  app/            FastAPI app: main.py (app, middleware, static files), routes.py (endpoints),
                  schemas.py (response models), config.py (constants), data_loader.py,
                  decision.py (forecast selection), alignment.py (hourly actuals),
                  metrics.py (all statistics and findings)
  scripts/        ingest.py (fetch + validate + write CSVs), analyse.py (full analysis)
  data/processed/ the committed CSVs
  tests/          pytest: ingestion, decision, alignment, metrics, API
frontend/
  src/api/        typed API client and types mirroring backend/app/schemas.py
  src/lib/        pure helpers (formatting, buy plan, URL state, ...) with Vitest tests
  src/pages/      DecisionPlanner, Performance, Insights
  src/components/ shared UI, controls, Methodology panel
api/index.py      Vercel entry point (wraps the same FastAPI app)
docs/             ARCHITECTURE.md, ASSUMPTIONS.md, DATA_NOTES.md
Dockerfile, docker-compose.yml, heroku.yml, vercel.json
.github/workflows/ci.yml
```

## Testing

```sh
cd backend && .venv/bin/python -m pytest -q          # 93 tests
cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
cd frontend && npm test                              # 23 tests
cd frontend && npm run build                         # type-check + production build
```

Tests were written before the logic they cover. They include every case in spec Section 11.1,
the golden example (delivery 2026-01-03, cutoff 09:00 → forecast published 2026-01-02 07:30,
24/24 hours), hand-computed metrics, and API happy paths plus validation errors. CI runs all of
this, a Docker build and dependency audits on every push.

## Deployment

The app is deployed on **Vercel**: the React build is served as static files and FastAPI runs as
a Python serverless function with the CSVs bundled (`vercel.json`, `api/index.py`). Heroku, the
spec's primary target, no longer has a free plan; `heroku.yml` is included so the same Docker
image can be deployed there with `heroku stack:set container` and `git push heroku main`.

**First load:** after a period without visitors the function starts cold and the first request
can take several seconds; the page says so while it waits. Later requests are fast.

## Known limitations

- **Small sample:** 31 delivery days in one winter month. Errors in neighbouring hours move
  together, so treat all figures as indicative.
- The over-forecast's cause is not proven (likely curtailment). Checking it would need extra
  datasets, which are outside this pilot's scope.
- The shortfall buffer uses hindsight by design (spec); the no-hindsight version is weaker in
  early January because it has little history.
- The documented WINDFOR publish times are one hour later than the `publishTime` values in the
  data. If forecasts became available an hour after their timestamp, the 08:00, 10:00 and 12:00
  cutoffs would be optimistic. The default 09:00 cutoff is safe either way.
- The buy calculator assumes the same demand every hour.
- Data is static (January 2026 only); nothing updates live.

## Use of AI tools

This project was built with the help of an AI coding assistant, **Claude Code (Anthropic)**. It was
used to write code, tests and documentation, to run the analysis and checks, and to research the
Elexon documentation. All output was reviewed, run and checked against the data and the
specification. Decisions on scope and design were made by the project owner.
