"""FastAPI application: API under /api, built front end (if present) at /.

Run locally (from backend/):
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.data_loader import get_dataset
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_dataset()  # load the CSVs into memory once, at start-up
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

app.include_router(router, prefix="/api")

# Mounted last, so /api routes take priority.
if config.STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
