"""
project_mapper/app.py
Aethvion Project Mapper — FastAPI application factory + CLI entry point.

This module is the single source of truth for the HTTP app so it can be
imported both by the installed ``pm-server`` CLI command and by the
development shim ``server.py``.

Usage
-----
    # Installed CLI (after pip install aethvion-project-mapper)
    pm-server
    pm-server --port 8080
    pm-server --host 127.0.0.1 --port 7474 --workers 2

    # Development (from repo root, without installing)
    uvicorn server:app --reload --port 7474
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("aethvion-project-mapper")
except Exception:
    __version__ = "1.1.0"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, os.environ.get("PM_LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Aethvion Project Mapper",
    description=(
        "Static code analysis + knowledge-graph API for AI coding agents. "
        "Scan any project, query entities, trace impact, find paths."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe — always returns 200."""
    return {"status": "ok", "service": "aethvion-project-mapper"}


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Aethvion Project Mapper",
        "version": __version__,
        "docs":    "/docs",
        "health":  "/health",
        "api":     "/api/project-mapper",
    }


# ---------------------------------------------------------------------------
# CLI entry point  (pm-server)
# ---------------------------------------------------------------------------

def serve() -> None:
    """Start the HTTP API server. Installed as the ``pm-server`` CLI command."""
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(
        prog="pm-server",
        description="Aethvion Project Mapper - HTTP API server",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("PM_HOST", "0.0.0.0"),
        help="Bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PM_PORT", "7474")),
        help="Port (default: 7474)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("PM_WORKERS", "1")),
        help="Number of worker processes (default: 1; use >= 2 for production)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (dev only, incompatible with --workers > 1)",
    )
    args = parser.parse_args()

    print(f"  Aethvion Project Mapper v{__version__}")
    print(f"  http://{args.host}:{args.port}  |  docs: http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "project_mapper.app:app",
        host=args.host,
        port=args.port,
        workers=args.workers if not args.reload else 1,
        reload=args.reload,
    )
