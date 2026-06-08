"""
server.py
Aethvion Project Mapper — HTTP API server.

Usage
-----
    # Development
    uvicorn server:app --reload --port 7474

    # Production
    uvicorn server:app --host 0.0.0.0 --port 7474 --workers 2

    # Docker
    docker compose up

Environment
-----------
    PM_DATA_DIR   — root directory for all databases
                    (default: ~/.aethvion_pm/data)
    PM_LOG_LEVEL  — log level: DEBUG | INFO | WARNING | ERROR
                    (default: INFO)

API prefix: /api/project-mapper
Docs:       http://localhost:7474/docs
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from project_mapper.routes import router

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
    version="1.0.0",
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


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe — always returns 200."""
    return {"status": "ok", "service": "aethvion-project-mapper"}


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Aethvion Project Mapper",
        "version": "1.0.0",
        "docs":    "/docs",
        "health":  "/health",
        "api":     "/api/project-mapper",
    }
