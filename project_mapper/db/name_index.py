"""
project_mapper/db/name_index.py
Global name-to-ID lookup for AethvionDB entities.

The index MUST exist and be consulted before any entity file is created.
This prevents duplicate entity files for the same real-world thing.

Storage: <DATA_DIR>/default/name_index.json  (or per-db path when constructed explicitly)
Format:  { "<normalized_name>": "<ws_id>", ... }

Normalization: lowercase, strip outer whitespace, collapse internal whitespace.

Thread-safety: Uses a threading.Lock around all reads and writes.
               Not safe for multi-process scenarios (use SQLite if needed).
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Optional

from .utils import get_logger, atomic_json_write
from ..config import DATA_DIR

logger = get_logger(__name__)

_WHITESPACE = re.compile(r"\s+")
_DEFAULT_INDEX_PATH = DATA_DIR / "default" / "name_index.json"


def _normalize(name: str) -> str:
    """Canonical form for index lookup: lowercase, collapsed whitespace."""
    return _WHITESPACE.sub(" ", name.strip()).lower()


class NameIndex:
    """
    Singleton-like thread-safe name→ID registry.

    Usage
    -----
    idx = NameIndex()
    ws_id = idx.get("Albert Einstein")          # None if not found
    ws_id = idx.get_or_create("Albert Einstein", default_id="ws_abc123")
    idx.register("Albert Einstein", "ws_abc123")
    idx.register_aliases("ws_abc123", ["Einstein", "AE"])
    """

    def __init__(self, index_path: Optional[Path] = None) -> None:
        self._path = index_path or _DEFAULT_INDEX_PATH
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}
        self._loaded = False

    # Loading

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._path.exists():
                try:
                    self._data = json.loads(self._path.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning(f"[NameIndex] Could not load {self._path}: {e} — starting fresh")
                    self._data = {}
            else:
                self._data = {}
            self._loaded = True

    def _save(self) -> None:
        """Atomically write the index to disk. Must be called under _lock."""
        atomic_json_write(self._path, self._data, sort_keys=True)

    # Public API

    def get(self, name: str) -> Optional[str]:
        """Return the entity ID for *name*, or None if not indexed."""
        self._ensure_loaded()
        return self._data.get(_normalize(name))

    def get_or_create(self, name: str, default_id: str) -> tuple[str, bool]:
        """
        Return (id, created).
        If *name* is already indexed, returns the existing ID (created=False).
        Otherwise registers *default_id* and returns it (created=True).
        """
        self._ensure_loaded()
        key = _normalize(name)
        with self._lock:
            if key in self._data:
                return self._data[key], False
            self._data[key] = default_id
            self._save()
            return default_id, True

    def register(self, name: str, entity_id: str) -> None:
        """Register a single name→ID mapping. Overwrites silently if already present."""
        self._ensure_loaded()
        key = _normalize(name)
        with self._lock:
            self._data[key] = entity_id
            self._save()
        logger.debug(f"[NameIndex] registered {name!r} → {entity_id}")

    def register_aliases(self, entity_id: str, aliases: list[str]) -> None:
        """Register multiple alias names for the same entity ID."""
        self._ensure_loaded()
        with self._lock:
            for alias in aliases:
                key = _normalize(alias)
                if key and key not in self._data:
                    self._data[key] = entity_id
            self._save()

    def unregister(self, name: str) -> bool:
        """Remove a name from the index. Returns True if it was present."""
        self._ensure_loaded()
        key = _normalize(name)
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._save()
                return True
            return False

    def list_all(self) -> dict[str, str]:
        """Return a snapshot of the full index (name → id)."""
        self._ensure_loaded()
        with self._lock:
            return dict(self._data)

    def count(self) -> int:
        self._ensure_loaded()
        return len(self._data)

    def reload(self) -> None:
        """Force re-read from disk (e.g. after external mutation)."""
        with self._lock:
            self._loaded = False
        self._ensure_loaded()


# Module-level singleton — import and share this across the package
_default_index: Optional[NameIndex] = None


def get_index() -> NameIndex:
    """Return the shared module-level NameIndex instance."""
    global _default_index
    if _default_index is None:
        _default_index = NameIndex()
    return _default_index
