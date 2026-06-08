"""
project_mapper/db/db_registry.py
Database registry — maps named databases to filesystem paths and stores
per-database metadata (description, backup settings, etc.).

Registry file: <DATA_DIR>/_db_registry.json

Format (v2)
-----------
{
  "version": 2,
  "databases": {
    "default": {
      "name": "default",
      "path": "/absolute/path/to/default",
      "description": "",
      "created": "2024-01-01T00:00:00+00:00",
      "backup": {
        "enabled": false,
        "keep_count": 5
      }
    }
  }
}
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils import get_logger, load_json
from ..config import DATA_DIR

logger = get_logger(__name__)

_REGISTRY_FILE = DATA_DIR / "_db_registry.json"
_SAFE_RE       = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_db_entry(name: str, path: str) -> dict:
    return {
        "name":        name,
        "path":        path,
        "description": "",
        "created":     _now_iso(),
        "backup": {
            "enabled":    False,
            "keep_count": 5,
        },
    }


# Internal helpers

def _read_raw() -> dict:
    """Read the registry file; returns {} on any error."""
    return load_json(_REGISTRY_FILE, default={})


def _migrate(raw: dict) -> dict:
    """Migrate v1 {name: path} format to v2 in-place."""
    if raw.get("version") == 2:
        return raw

    databases: dict[str, dict] = {}
    for k, v in raw.items():
        if k == "version":
            continue
        if isinstance(v, str):
            databases[k] = _default_db_entry(k, v)
        elif isinstance(v, dict) and "path" in v:
            entry = _default_db_entry(k, v["path"])
            for fk in ("description", "created", "backup"):
                if fk in v:
                    entry[fk] = v[fk]
            databases[k] = entry

    return {"version": 2, "databases": databases}


def _read() -> dict:
    """Read, migrate if needed, and return the v2 registry dict."""
    raw      = _read_raw()
    migrated = _migrate(raw)
    if migrated is not raw:
        _write(migrated)
    return migrated


def _write(registry: dict) -> None:
    """Persist the registry; silently ignores write errors."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _REGISTRY_FILE.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.debug(f"[DBRegistry] Write failed: {exc}")


# Public API

def register_db(
    name:        str,
    path:        str | Path,
    description: str = "",
    *,
    overwrite:   bool = True,
) -> dict:
    """Add or update a database entry in the registry.

    When *overwrite* is False the existing entry is returned unchanged if
    a database with that name is already registered.

    Returns the (possibly updated) entry dict.
    """
    reg      = _read()
    dbs      = reg.setdefault("databases", {})
    path_str = str(path)

    if name in dbs:
        if not overwrite:
            return dbs[name]
        dbs[name]["path"] = path_str
        if description:
            dbs[name]["description"] = description
    else:
        dbs[name] = _default_db_entry(name, path_str)
        if description:
            dbs[name]["description"] = description

    _write(reg)
    logger.debug(f"[DBRegistry] Registered {name!r} → {path_str}")
    return dbs[name]


def update_db(name: str, **kwargs: Any) -> dict | None:
    """Update metadata fields on an existing database entry."""
    reg = _read()
    dbs = reg.get("databases", {})
    if name not in dbs:
        return None

    entry = dbs[name]
    if "description" in kwargs:
        entry["description"] = str(kwargs["description"])
    if "backup" in kwargs and isinstance(kwargs["backup"], dict):
        entry.setdefault("backup", {}).update(kwargs["backup"])

    _write(reg)
    return entry


def remove_db(name: str) -> bool:
    """Remove a database from the registry.

    Returns True if the entry existed and was removed, False otherwise.
    The database files on disk are NOT deleted — only the registry entry.
    """
    reg = _read()
    dbs = reg.get("databases", {})
    if name not in dbs:
        return False
    del dbs[name]
    _write(reg)
    return True


def get_db(name: str) -> dict | None:
    """Return the metadata dict for a single database, or None."""
    return _read().get("databases", {}).get(name)


def list_dbs() -> list[dict]:
    """Return all registered databases as a list of entry dicts."""
    return list(_read().get("databases", {}).values())


def resolve_db_root(db: str) -> Path:
    """Return the filesystem root for a named database.

    Lookup order:
      1. Registry entry whose path still exists on disk
      2. DATA_DIR/<db>  (default fallback)
    """
    entry = get_db(db)
    if entry:
        p = Path(entry["path"])
        if p.exists():
            logger.debug(f"[DBRegistry] Resolved {db!r} → {p} (registry)")
            return p
        logger.debug(f"[DBRegistry] Stale registry entry for {db!r}: path gone ({p})")

    return DATA_DIR / db


def register_path_db(path: str | Path) -> None:
    """Register a path-based database by its folder name (legacy shim)."""
    try:
        p    = Path(path)
        name = p.name
        if not name or not _SAFE_RE.match(name):
            return
        register_db(name, p, overwrite=True)
    except Exception as exc:
        logger.debug(f"[DBRegistry] Could not register {path!r}: {exc}")


def list_registered() -> dict[str, str]:
    """Return {name: path} for all registered databases (legacy compat)."""
    return {e["name"]: e["path"] for e in list_dbs()}
