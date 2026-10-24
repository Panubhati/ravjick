# CLAUDE.md

Wind forecast portal (take-home pilot): React + Python/FastAPI, Docker, built on
Elexon wind data for January 2026 delivery days. Shows the forecast that was
available at the D-1 decision cutoff and quantifies forecast error.

## Source of truth

- Full spec: `Wind Forecast Portal Build Specification (1).docx` in the repo root
  (local only, gitignored). Read it before starting a phase. Section 10 = phases
  and acceptance criteria, Section 11 = required tests.
- Section 4 of the spec (API endpoints and fields) is verified. Never invent API
  fields or parameters; if reality differs, stop and report it.
- `docs/DATA_NOTES.md`: what the data actually looks like (publish schedule, quirks).
- `docs/ASSUMPTIONS.md`: log every new assumption here as it is made.

## Working rules

- One phase at a time, in Section 10 order. When a phase's acceptance criteria
  pass, show the results and wait for the user's go-ahead before the next phase.
- One git commit per phase.
- Write tests before the logic that depends on them.
- Ask the user when something is ambiguous instead of guessing.
- Scope: only the FUELHH (WIND) and WINDFOR datasets. No other data sources.
- Prefer plain, readable code; it is walked through in a review video. Few,
  mainstream dependencies. Total budget is 16 hours, so don't gold-plate.

## Anonymity (hard requirement)

- No real names, emails, usernames or employer names in any committed file,
  comment, package metadata or git history. Watch out for local paths like
  `C:\Users\<name>\...` in output files.
- Git identity is set repo-locally to `Panubhati` with the GitHub noreply email
  (the owner's choice, so commits count for their account). Never use the
  global git config, which contains a real name and email.
- Before each commit, grep staged files for personal identifiers.
- Commit messages: subject + body only. No "Co-Authored-By: Claude" or other AI
  attribution trailer (AI use is stated in the README instead).
- Phase 1 leftovers (`featch.py`, root `data/`) and the spec `.docx` are
  gitignored on purpose; keep them out of the repo.

## Status

- Phase 1 (discovery): done.
- Phase 2 (ingestion): done.
- Phase 3 (core logic): done.
- Phase 4 (metrics): done.
- Phase 5 (API): done.
- Phase 6 (front end): done.
- Improvement pass (perf, security, UI, honest stats): done.
- UI wording: spec headings kept exactly; plain-language subtitles, hints, footer (ASSUMPTIONS F12). Do not rename spec headings.
- Extras: look-ahead check, buffer without hindsight, buy calculator (ASSUMPTIONS G1-G3).
- Phase 7 (Docker + Vercel config): Docker verified locally; Vercel import pending (owner).
- Phase 8 (README, ARCHITECTURE, CI, audits): done. Add live URL to README after deploy.
  Next: Phase 9 (docs/VIDEO_SCRIPT.md with real numbers and screens).

Update this section when a phase completes.

## Commands (Windows; run from `backend/`)

```sh
.venv/Scripts/python -m pip install -r requirements-dev.txt   # deps
.venv/Scripts/python -m pytest -q                              # tests
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
.venv/Scripts/python -m scripts.ingest                         # re-fetch data (network)
.venv/Scripts/python -m scripts.analyse                        # full Section 6 analysis
.venv/Scripts/python -m uvicorn app.main:app --reload          # API on :8000, docs at /docs
```

Use `python -m scripts.ingest`, not `python scripts/ingest.py`: the script
imports `app.config`, so it only works when run as a module.

## Layout and conventions

- `backend/app/config.py`: date bounds, default cutoff (09:00), cutoff options
  (06:00 to 12:00), file paths. Use these constants instead of hard-coding them.
- `backend/scripts/ingest.py`: offline fetch, validation and CSV writer. The app
  never calls Elexon at runtime.
- `backend/data/processed/`: committed CSVs (`actuals_half_hourly.csv`,
  `actuals_half_hourly_baseline.csv`, `forecasts.csv`). Columns are snake_case,
  timestamps are ISO 8601 UTC with `Z`, and values are in `generation_mw`.
- All times are UTC (equal to UK time in January).
- Decision rule: for target hour T, take the forecast with the greatest
  `publish_time <= cutoff on D-1` (inclusive). Never fall back to a later
  publish; flag the hour as missing instead.
- Error sign: `error_mw = forecast_mw - actual_mw`. Positive means wind was
  over-forecast, so the buyer is short.
- `decision.py` must stay pure: no web-framework imports.
- Python 3.12, pandas, pydantic v2, pytest, ruff (config in
  `backend/pyproject.toml`). Line endings are LF (`.gitattributes`).

## Front end (run from `frontend/`)

```sh
npm install
npm run dev     # http://localhost:5173, proxies /api to :8000 (start uvicorn first)
npm test        # Vitest unit tests for src/lib
npm run build   # type-check + production build to frontend/dist
```

- `src/api/types.ts` mirrors `backend/app/schemas.py`; keep them in sync.
- Pure helpers live in `src/lib/` and are unit-tested; pages are in `src/pages/`.
- When `frontend/dist` exists, FastAPI serves it at `/` (see `STATIC_DIR`).
- API only accepts the 7 listed cutoffs (06:00-12:00); others return 422.
- On the development machine, port 8000 is taken by another local service. Run
  uvicorn on another port (for example `--port 8765`) for local checks.
