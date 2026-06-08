"""
server.py
Development shim — re-exports the app from project_mapper.app.

Usage (local development, from repo root):
    uvicorn server:app --reload --port 7474
    uvicorn server:app --host 0.0.0.0 --port 7474 --workers 2

For production use the installed CLI command instead:
    pm-server
    pm-server --port 8080 --workers 2
"""

from project_mapper.app import app  # noqa: F401  re-exported for uvicorn

__all__ = ["app"]
