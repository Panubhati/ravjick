"""Vercel entry point: exposes the FastAPI app as a Python serverless function.

The React build is served by Vercel as static files; requests to /api, /docs
and /openapi.json are rewritten to this function (see vercel.json). The same
app runs unchanged in Docker.
"""

import sys
from pathlib import Path

# The back-end package lives in backend/app; make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402

__all__ = ["app"]
