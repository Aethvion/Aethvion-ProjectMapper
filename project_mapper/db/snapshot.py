"""
project_mapper/db/snapshot.py
Fast-load snapshot for AethvionDB entity maps.

Problem
-------
``EntityWriter.list_all()`` opens and parses N individual ``ws_*.json`` files.
For large databases (10 000+ entities) this costs 1–2 s per call on Windows
(NTFS + Defender latency × N file syscalls).

Solution
--------
After each scan, serialise the complete entity map to a single JSON file.
Subsequent ``list_all()`` calls load the one snapshot file instead of N
individual files — ~10× faster in practice (measured: 2 038 ms → 205 ms
for ~12 000 entities on Windows).

Snapshot files
--------------
  <db_root>/AethvionDB.SNAPSHOT            — compact JSON array of all entities
  <db_root>/AethvionDB.SNAPSHOT.meta.json  — build metadata (count, timestamp)

The snapshot stores ALL entities including ``status="deleted"`` ones so that
filtering by ``include_deleted`` can happen at load time without needing to
rebuild.

Stale detection (``is_fresh``)
------------------------------
The snapshot is considered stale and bypassed when any of the following is true:

  1. The snapshot or meta file is missing.
  2. Any ``ws_*.json`` in *entities_dir* has an mtime **newer** than the
     snapshot — catches creates and in-place updates.
  3. The count of ``ws_*.json`` files differs from the stored ``entity_count``
     in the meta file — catches hard deletes (file removed, no mtime to check).

Thread safety
-------------
Writes use an atomic temp-file → ``replace()`` pattern, identical to the
entity writer itself.  A partial snapshot write can never be read.

Layout note
-----------
Entities live in ``<db_root>/entities/``, so the snapshot files land in
``<db_root>/`` (i.e. ``entities_dir.parent``).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .utils import get_logger

logger = get_logger(__name__)

# ── File name constants ───────────────────────────────────────────────────────

SNAPSHOT_FILE = "AethvionDB.SNAPSHOT"
META_FILE     = "AethvionDB.SNAPSHOT.meta.json"

# Written by PMEntityStore.flush() — signals that this database was built by
# the in-memory PM store (no ws_*.json entity files exist by design).
# is_fresh() uses this marker to skip the entity-file count check.
PM_MARKER_FILE = "AethvionDB.PMSTORE"


# ── Path helpers ──────────────────────────────────────────────────────────────

def snapshot_path(db_root: Path) -> Path:
    """Absolute path to the snapshot data file."""
    return db_root / SNAPSHOT_FILE


def meta_path(db_root: Path) -> Path:
    """Absolute path to the snapshot metadata file."""
    return db_root / META_FILE


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Public API ────────────────────────────────────────────────────────────────

def is_fresh(db_root: Path, entities_dir: Path) -> bool:
    """Return ``True`` if the snapshot exists and is up-to-date.

    Parameters
    ----------
    db_root:      Directory that contains the snapshot files.
    entities_dir: Directory that contains the ``ws_*.json`` entity files.
    """
    snap = snapshot_path(db_root)
    meta = meta_path(db_root)

    if not snap.exists() or not meta.exists():
        return False

    # PM-store mode: no ws_*.json entity files exist by design.
    # The snapshot written by PMEntityStore.flush() is the sole source of truth.
    if (db_root / PM_MARKER_FILE).exists():
        return True

    try:
        snap_mtime = snap.stat().st_mtime
    except OSError:
        return False

    # Collect entity files once (used for both mtime check and count check)
    try:
        entity_files = list(entities_dir.glob("ws_*.json"))
    except OSError:
        return False

    # Check 2 — any entity file newer than the snapshot?
    for ef in entity_files:
        try:
            if ef.stat().st_mtime > snap_mtime:
                return False
        except OSError:
            return False  # file disappeared mid-check — be conservative

    # Check 3 — entity count matches stored value?
    try:
        stored_meta = json.loads(meta.read_text(encoding="utf-8"))
        if stored_meta.get("entity_count") != len(entity_files):
            return False
    except Exception:
        return False

    return True


def build(db_root: Path, entities: list[dict[str, Any]]) -> None:
    """Serialise *entities* (all statuses) to the snapshot file atomically.

    Parameters
    ----------
    db_root:  Directory where snapshot files will be written.
    entities: Complete entity list — should include deleted entities so that
              ``include_deleted`` filtering works at load time.
    """
    t0   = time.perf_counter()
    snap = snapshot_path(db_root)
    tmp  = snap.with_suffix(".tmp")

    try:
        tmp.write_text(
            json.dumps(entities, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(snap)
    except Exception as exc:
        logger.warning(f"[Snapshot] Write failed: {exc}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    meta = {
        "v":            1,
        "built_at":     _now_iso(),
        "entity_count": len(entities),
        "elapsed_ms":   elapsed_ms,
    }
    try:
        meta_path(db_root).write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning(f"[Snapshot] Meta write failed: {exc}")

    logger.info(
        f"[Snapshot] Built: {len(entities)} entities in {elapsed_ms} ms"
        f" → {snap.name}"
    )


def load(db_root: Path) -> list[dict[str, Any]]:
    """Load and return all entities from the snapshot file.

    Returns an empty list if the snapshot is missing or corrupt; the caller
    should fall back to ``EntityWriter._raw_list_all()`` in that case.
    """
    snap = snapshot_path(db_root)
    if not snap.exists():
        return []
    try:
        return json.loads(snap.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"[Snapshot] Read failed: {exc}")
        return []


def invalidate(db_root: Path) -> None:
    """Delete the snapshot files so the next ``list_all()`` rebuilds from source.

    Useful when bulk operations outside the normal write path modify entities.
    """
    for p in (snapshot_path(db_root), meta_path(db_root)):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    logger.debug("[Snapshot] Invalidated")
