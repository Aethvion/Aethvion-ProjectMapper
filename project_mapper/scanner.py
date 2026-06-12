"""
project_mapper/scanner.py
ProjectMapper entry point — walks a project directory and ingests it into AethvionDB.

Persistence model
-----------------
  ProjectMapper.SCANINFO — JSON job metadata + progress (in the database root)

The scan runs as an asyncio background task.  Call:
  start_scan(...)   — launch the background task
  scan_status(...)  — read current progress
  cancel_scan(...)  — cancel a running scan
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .code_analyzer import analyze_file
from .ingestor import ProjectIngestor

logger = logging.getLogger(__name__)

SCANINFO = "ProjectMapper.SCANINFO"

# Supported extensions for static analysis
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs",
    ".java", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp",
    ".rb", ".go", ".rs", ".php", ".cs", ".swift", ".kt",
})

# Directory names excluded from all filesystem walks
_EXCLUDED_DIRS: frozenset[str] = frozenset({
    "__pycache__", "node_modules", ".venv", "venv",
    ".git", "dist", "build", ".tox", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".eggs", ".cache",
})

# In-process task registry
_active_scans: dict[str, asyncio.Task] = {}   # key: str(db_root)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fmt_size(b: int) -> str:
    if b < 1024:      return f"{b} B"
    if b < 1024 ** 2: return f"{b / 1024:.1f} KB"
    return f"{b / 1024 ** 2:.1f} MB"


def _content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_scaninfo(db_root: Path) -> dict[str, Any]:
    p = db_root / SCANINFO
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_scaninfo(db_root: Path, data: dict[str, Any]) -> None:
    try:
        (db_root / SCANINFO).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning(f"[Scanner] Could not write {SCANINFO}: {exc}")


def _update_scaninfo(db_root: Path, **kwargs: Any) -> None:
    info = _read_scaninfo(db_root)
    info.update(kwargs)
    info["last_updated"] = _now_iso()
    _write_scaninfo(db_root, info)


# ---------------------------------------------------------------------------
# Public status / control API
# ---------------------------------------------------------------------------

def scan_status(db_root: Path) -> dict[str, Any]:
    """Return the current scan status dict."""
    info = _read_scaninfo(db_root)
    if not info:
        return {"status": "idle", "db_root": str(db_root)}
    info["is_running"] = str(db_root) in _active_scans
    return info


def is_running(db_root: Path) -> bool:
    return str(db_root) in _active_scans


def cancel_scan(db_root: Path) -> dict[str, Any]:
    """Cancel the running scan task (if any)."""
    key  = str(db_root)
    task = _active_scans.get(key)
    if task:
        task.cancel()
        _active_scans.pop(key, None)
        _update_scaninfo(db_root, status="cancelled")
        return {"cancelled": True}
    return {"cancelled": False, "reason": "No active scan"}


# ---------------------------------------------------------------------------
# Pre-scan folder scan (sync, for route preview)
# ---------------------------------------------------------------------------

def scan_folder_preview(project_root: str) -> dict[str, Any]:
    """Walk the folder and count files without scanning them."""
    root = Path(project_root)
    if not root.exists():
        raise FileNotFoundError(f"Not found: {project_root}")
    total = supported = 0
    ext_counts: dict[str, int] = {}
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _EXCLUDED_DIRS]
        for fn in files:
            fp   = Path(dirpath) / fn
            ext  = fp.suffix.lower()
            total += 1
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            if ext in SUPPORTED_EXTENSIONS:
                supported += 1
    top_ext = sorted(ext_counts.items(), key=lambda x: -x[1])[:10]
    return {
        "project_root": project_root,
        "total_files":  total,
        "supported_files": supported,
        "top_extensions": [{"ext": e or "(none)", "count": c, "supported": e in SUPPORTED_EXTENSIONS} for e, c in top_ext],
    }


# ---------------------------------------------------------------------------
# Main background scan task
# ---------------------------------------------------------------------------

async def run_scan(
    db_root:      Path,
    project_root: str,
    db_name:      str,
    writer:       Any,
    index:        Any,
    file_manifest: Any,
    concurrency:  int = 3,
    incremental:  bool = True,
) -> None:
    """
    Background task: walk project_root, analyse all supported files,
    ingest into AethvionDB via static AST analysis.

    incremental=True (default): skip files whose hash hasn't changed since
    the last scan (uses FileManifest.needs_rescan).
    """
    key = str(db_root)
    root = Path(project_root)

    # On a full (non-incremental) scan, purge all stub entities that have no
    # file_path.  These accumulate when multiple projects are scanned into the
    # same database and cause cross-project relation contamination.
    if not incremental:
        try:
            stubs_purged = 0
            for entity in writer.list_all(include_deleted=False):
                if entity.get("status") == "stub":
                    writer.update(entity["id"], {"status": "deleted"})
                    stubs_purged += 1
            if stubs_purged:
                logger.info(f"[Scanner] Full scan: purged {stubs_purged} stale stubs")
        except Exception as exc:
            logger.warning(f"[Scanner] Stub purge failed: {exc}")

    ingestor = ProjectIngestor(
        db_root=db_root,
        writer=writer,
        index=index,
        file_manifest=file_manifest,
    )

    # --- Collect file list (skip hidden/cache dirs) ---
    file_paths: list[Path] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _EXCLUDED_DIRS]
        for fn in sorted(files):
            fp = Path(dirpath) / fn
            if fp.suffix.lower() in SUPPORTED_EXTENSIONS:
                file_paths.append(fp)

    total = len(file_paths)
    stats: dict[str, Any] = {
        "files_total":             total,
        "files_scanned":           0,
        "files_skipped_unchanged": 0,
        "files_skipped_unsupported": 0,
        "entities_created":        0,
        "entities_updated":        0,
        "entities_pruned":         0,   # symbols removed from changed files
        "relations_created":       0,
        "files_deleted":           0,   # set during deletion cleanup pass
        "entities_retired":        0,   # set during deletion cleanup pass
        "errors":                  [],
    }

    _write_scaninfo(db_root, {
        "project_root":  project_root,
        "db":            db_name,
        "status":        "running",
        "started_at":    _now_iso(),
        "last_updated":  _now_iso(),
        "total_files":   total,
        "current_file":  "",
        "stats":         stats,
    })

    logger.info(f"[Scanner] Starting scan of {project_root} ({total} files, concurrency={concurrency})")

    # --- Process files in batches ---
    semaphore = asyncio.Semaphore(concurrency)

    async def _process_one(fp: Path) -> None:
        rel = str(fp.relative_to(root)).replace("\\", "/")

        # Skip node_modules — always third-party packages, never project code.
        # Check before reading to avoid the I/O cost entirely.
        if "node_modules" in fp.parts:
            stats["files_skipped_unsupported"] += 1
            return

        try:
            content = await asyncio.to_thread(fp.read_text, encoding="utf-8", errors="replace")
        except Exception as exc:
            stats["errors"].append({"path": rel, "error": f"read: {exc}"})
            return

        # Skip binary — null bytes heuristic for files read in text mode.
        # Record in manifest (no entities) so pm_delta doesn't re-flag as new.
        if len(content) > 100 and content.count("\x00") / len(content) > 0.1:
            stats["files_skipped_unsupported"] += 1
            file_manifest.record(rel, _content_hash(content), [])
            return

        # Skip oversized files — minified bundles and generated assets can exceed
        # hundreds of KB as a single line, stalling tree-sitter and spiking memory.
        # NOT recorded in manifest: delta's walk excludes >250KB files, so a
        # manifest entry would be flagged as perpetually "deleted" instead.
        if len(content) > 250_000:
            stats["files_skipped_unsupported"] += 1
            return
        # Minification heuristic: substantial content with almost no line breaks.
        # Recorded in manifest — delta walks these files (they pass its size
        # filter), so without a record they'd show as "new" on every delta.
        if len(content) > 10_000 and content.count("\n") < 5:
            stats["files_skipped_unsupported"] += 1
            file_manifest.record(rel, _content_hash(content), [])
            return

        file_hash = _content_hash(content)

        # Empty file (e.g. __init__.py) — record in manifest with no entities so
        # pm_delta doesn't re-flag it as new on every run.
        if not content.strip():
            stats["files_skipped_unsupported"] += 1
            file_manifest.record(rel, file_hash, [])
            return

        # Incremental: skip unchanged files
        if incremental and not file_manifest.needs_rescan(rel, file_hash):
            stats["files_skipped_unchanged"] += 1
            return

        try:
            file_size = fp.stat().st_size
        except OSError:
            file_size = 0

        from .code_analyzer import detect_language_for_path  # inline to avoid circular
        language = detect_language_for_path(str(fp))
        analysis = await asyncio.to_thread(analyze_file, rel, content, language)

        _update_scaninfo(db_root, current_file=rel)

        async with semaphore:
            ingest_result = await asyncio.to_thread(
                ingestor.ingest, analysis, root, file_hash, file_size
            )

        if ingest_result.errors:
            stats["errors"].extend([{"path": rel, "error": e} for e in ingest_result.errors])

        if ingest_result.was_created:
            stats["entities_created"] += 1 + len(ingest_result.class_entity_ids) + len(ingest_result.function_entity_ids)
        else:
            stats["entities_updated"] += 1
            # Prune symbols that were removed from this file since last scan
            if ingest_result.module_entity_id:
                from .cleanup import prune_removed_symbols
                all_new_ids = (
                    ingest_result.class_entity_ids
                    + ingest_result.function_entity_ids
                )
                pruned = await asyncio.to_thread(
                    prune_removed_symbols,
                    ingest_result.module_entity_id,
                    all_new_ids,
                    writer,
                )
                stats["entities_pruned"] += pruned

        stats["relations_created"] += ingest_result.relations_created
        stats["files_scanned"]     += 1

    # Process all files — gather with cancellation support
    try:
        tasks = [asyncio.create_task(_process_one(fp)) for fp in file_paths]
        for i, task in enumerate(asyncio.as_completed(tasks)):
            try:
                await task
            except asyncio.CancelledError:
                # Propagate cancellation
                for t in tasks:
                    t.cancel()
                raise
            except Exception as exc:
                stats["errors"].append({"path": "unknown", "error": str(exc)[:200]})
            # Persist progress every 10 files
            if i % 10 == 0:
                _update_scaninfo(db_root, stats=dict(stats))

    except asyncio.CancelledError:
        _write_scaninfo(db_root, {
            **_read_scaninfo(db_root),
            "status": "cancelled",
            "last_updated": _now_iso(),
            "stats": stats,
        })
        _active_scans.pop(key, None)
        logger.info(f"[Scanner] Scan cancelled ({stats['files_scanned']}/{total} processed)")
        return

    # --- Deletion cleanup pass (all scans) ---
    # Retire entities whose source files have been removed from the project.
    # Runs on full scans too: after a root switch, the manifest still holds the
    # previous project's files, which would otherwise stay active forever.
    try:
        from .cleanup import run_deletion_cleanup
        _update_scaninfo(db_root, status="cleanup", current_file="[deletion cleanup]")
        cleanup = await asyncio.to_thread(
            run_deletion_cleanup, root, file_manifest, writer, index
        )
        stats["files_deleted"]   = cleanup.deleted_file_count
        stats["entities_retired"] = cleanup.retired_count
        if cleanup.errors:
            stats["errors"].extend([{"path": "cleanup", "error": e} for e in cleanup.errors])
    except Exception as exc:
        logger.warning(f"[Scanner] Deletion cleanup failed (non-critical): {exc}")

    # --- Stub resolution pass (always, every full scan) ---
    # Re-wire relations from stubs to real entities where the target was
    # scanned in a later file.  Safe to run after every scan.
    try:
        from .cleanup import resolve_stubs
        _update_scaninfo(db_root, status="cleanup", current_file="[stub resolution]")
        stub_result = await asyncio.to_thread(resolve_stubs, writer, index)
        if stub_result.stubs_resolved:
            stats["stubs_resolved"]   = stub_result.stubs_resolved
            stats["relations_rewired"] = stub_result.relations_rewired
        if stub_result.errors:
            stats["errors"].extend([{"path": "stub_resolve", "error": e}
                                     for e in stub_result.errors])
    except Exception as exc:
        logger.warning(f"[Scanner] Stub resolution failed (non-critical): {exc}")

    # --- Orphan stub pruning (always) ---
    # Delete stubs that no active entity references — they accumulate when
    # project roots change in a shared database and pollute stats/search.
    try:
        from .cleanup import prune_orphan_stubs
        _update_scaninfo(db_root, status="cleanup", current_file="[stub pruning]")
        stubs_pruned = await asyncio.to_thread(prune_orphan_stubs, writer)
        if stubs_pruned:
            stats["stubs_pruned"] = stubs_pruned
    except Exception as exc:
        logger.warning(f"[Scanner] Stub pruning failed (non-critical): {exc}")

    _write_scaninfo(db_root, {
        **_read_scaninfo(db_root),
        "status":       "completed",
        "completed_at": _now_iso(),
        "last_updated": _now_iso(),
        "current_file": "",
        "stats":        stats,
    })
    _active_scans.pop(key, None)
    logger.info(
        f"[Scanner] Scan completed — "
        f"scanned={stats['files_scanned']} skipped={stats['files_skipped_unchanged']} "
        f"created={stats['entities_created']}"
    )

    # Build snapshot so the next list_all() call uses the fast single-file path
    # instead of reading N individual entity files.  This runs after the scan
    # key is popped so it does not block start_scan() for the same db_root.
    #
    # PMEntityStore provides flush() which writes the snapshot + name index in
    # one call (no entity files to read back first).  EntityWriter falls back
    # to the original list_all() + snapshot.build() two-step.
    try:
        if hasattr(writer, "flush"):
            # PMEntityStore: single in-memory → snapshot write
            await asyncio.to_thread(writer.flush)
        else:
            # EntityWriter: read all entity files, then build snapshot
            from .db import snapshot as _snap
            all_for_snap = await asyncio.to_thread(
                writer.list_all, True, False   # include_deleted=True, use_snapshot=False
            )
            await asyncio.to_thread(_snap.build, db_root, all_for_snap)
    except Exception as exc:
        logger.warning(f"[Scanner] Snapshot build failed (non-critical): {exc}")


def start_scan(
    db_root:       Path,
    project_root:  str,
    db_name:       str,
    writer:        Any,
    index:         Any,
    file_manifest: Any,
    concurrency:   int = 3,
    incremental:   bool = True,
) -> bool:
    """
    Launch the scan as a background asyncio task.
    Returns True if the task was started, False if one was already running.
    """
    key = str(db_root)
    if key in _active_scans:
        return False

    task = asyncio.create_task(
        run_scan(
            db_root=db_root,
            project_root=project_root,
            db_name=db_name,
            writer=writer,
            index=index,
            file_manifest=file_manifest,
            concurrency=concurrency,
            incremental=incremental,
        )
    )

    def _on_done(t: asyncio.Task) -> None:
        _active_scans.pop(key, None)
        if t.cancelled():
            logger.info(f"[Scanner] Task cancelled for {db_root}")
        elif t.exception():
            logger.error(f"[Scanner] Task failed for {db_root}: {t.exception()}")

    task.add_done_callback(_on_done)
    _active_scans[key] = task
    return True
