"""
project_mapper/db/utils.py
Minimal stdlib-only utilities extracted from Aethvion Suite.

Provides the three helpers that the DB layer depends on:
  get_logger       — standard logging.getLogger wrapper
  atomic_json_write — write JSON atomically (temp-file + rename)
  load_json         — load JSON from a path with a safe default on error
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Union


def get_logger(name: str) -> logging.Logger:
    """Return a standard library logger for the given name."""
    return logging.getLogger(name)


def atomic_json_write(
    path: Union[str, Path],
    data: Union[dict, list],
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
) -> None:
    """Write *data* as JSON to *path* atomically.

    Writes to a temporary file in the same directory, then renames it into
    place. This prevents a partial/corrupt file being left on disk if the
    process is killed mid-write. ``os.replace()`` is atomic on POSIX and
    near-atomic on Windows (uses MoveFileEx MOVEFILE_REPLACE_EXISTING).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii, sort_keys=sort_keys)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_json(
    path: Union[str, Path],
    default=None,
) -> Union[dict, list, None]:
    """Load JSON from *path*, returning *default* on missing file or parse error."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to load %s: %s", path, exc)
        return default
