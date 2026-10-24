"""FastAPI application: API under /api, built front end (if present) at /.

Run locally (from backend/):
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.data_loader import get_dataset
from app.routes import router, warm_caches

# Strict policy for the app itself. Inline styles are needed by the chart
# library; the favicon is a data: URI. Swagger UI (/docs) loads from a CDN,
# so it is exempt.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'none'"
)
DOCS_PATHS = ("/docs", "/redoc")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_dataset()  # load the CSVs into memory once, at start-up
    warm_caches()  # compute the default views so first requests are fast
    yield


app = FastAPI(
    title="Wind Forecast Portal API",
    description=(
        "Day-ahead wind forecasts as they stood at the buying decision, and "
        "their accuracy, for January 2026 (Elexon data). Power in MW, times in "
        "UTC. error = forecast - actual (positive = wind was over-forecast)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def add_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if not path.startswith(DOCS_PATHS):
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    # Built assets have content hashes in their names, so they never change.
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif not path.startswith("/api") and not path.startswith(DOCS_PATHS):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.include_router(router, prefix="/api")

# Mounted last, so /api routes take priority.
if config.STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
