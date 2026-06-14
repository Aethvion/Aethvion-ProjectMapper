"""
project_mapper/routes.py
FastAPI routes for the ProjectMapper module.

Prefix: /api/project-mapper
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .scanner import (
    scan_folder_preview,
    scan_status,
    start_scan,
    cancel_scan,
    is_running,
    SCANINFO,
    _read_scaninfo,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/project-mapper", tags=["project-mapper"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _db_root(db: str = "default", path: Optional[str] = None) -> Path:
    if path:
        return Path(path)
    if not _SAFE_RE.match(db):
        raise HTTPException(400, f"Invalid database name {db!r}")
    from .db.db_registry import resolve_db_root
    return resolve_db_root(db)


def _get_scan_writer(
    db:          str  = "default",
    path:        Optional[str] = None,
    incremental: bool = False,
) -> tuple:
    """Return (PMEntityStore, PMNameIndex) for scan operations.

    All entities live in memory during the scan; flush() writes a single
    snapshot file at completion.  Both objects share the same PMNameIndex
    instance so the scanner, ingestor, and stub-resolver all see the same
    in-memory state.

    Incremental scans pre-populate the store from the existing snapshot so
    entities for unchanged files survive intact.
    """
    from .db.pm_store import PMEntityStore, PMNameIndex
    from .db import snapshot as _snap
    root  = _db_root(db, path)
    index = PMNameIndex(index_path=root / "name_index.json")
    if incremental and _snap.snapshot_path(root).exists():
        writer = PMEntityStore.from_snapshot(root, index)
    else:
        writer = PMEntityStore(root, index)
    return writer, index


def _get_mutation_writer(db: str = "default", path: Optional[str] = None) -> tuple:
    """Return (PMEntityStore, PMNameIndex) for mutations outside a scan.

    Loads the full snapshot into memory.  The caller must call
    writer.flush() to persist changes back to the snapshot file.
    """
    from .db.pm_store import PMEntityStore, PMNameIndex
    root  = _db_root(db, path)
    index = PMNameIndex(index_path=root / "name_index.json")
    writer = PMEntityStore.from_snapshot(root, index)
    return writer, index


def _get_file_manifest(db: str = "default", path: Optional[str] = None):
    from .db.file_manifest import FileManifest
    return FileManifest(_db_root(db, path))


def _ensure_db(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "chunks").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    project_root: str                    # absolute path to the project directory
    db:           str = "default"        # target database name
    db_path:      Optional[str] = None   # custom db path (overrides db name)
    concurrency:  int = 3                # parallel file processing
    incremental:  bool = True            # skip files with unchanged hashes


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/preview")
async def preview_project(
    project_root: str = Query(..., description="Absolute path to the project directory"),
):
    """
    Walk the project directory and count files by type — no scanning or entity creation.
    Use this before /scan to understand what will be processed.
    """
    try:
        result = await asyncio.to_thread(scan_folder_preview, project_root)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(400, str(exc))
    return result


@router.post("/scan")
async def start_project_scan(req: ScanRequest):
    """
    Start a background scan of the given project directory.
    Ingests the project structure into the specified database.

    Static AST analysis creates module/class/function entities and wires
    their relations.  If incremental=True, files with unchanged hashes are
    skipped.

    Returns immediately. Poll /scan/status for progress.
    """
    root = _db_root(req.db, req.db_path)
    _ensure_db(root)

    if is_running(root):
        raise HTTPException(409, "A scan is already running for this database. Cancel it first.")

    project_path = Path(req.project_root)
    if not project_path.exists():
        raise HTTPException(400, f"Project root does not exist: {req.project_root}")
    if not project_path.is_dir():
        raise HTTPException(400, f"Project root is not a directory: {req.project_root}")

    # --- Project-root mismatch guard ---
    # Each database should belong to exactly one project.  If this database
    # was previously scanned for a DIFFERENT project root, refuse the request
    # rather than silently mixing two codebases into the same entity graph.
    existing_info = _read_scaninfo(root)
    recorded_root = existing_info.get("project_root", "")
    if recorded_root and Path(recorded_root).resolve() != Path(req.project_root).resolve():
        suggest = Path(req.project_root).name.lower().replace(" ", "_").replace("-", "_")
        raise HTTPException(
            409,
            f"Database '{req.db}' already contains a scan for '{recorded_root}'. "
            f"Scanning a different project into the same database would mix their "
            f"entities and produce incorrect results. "
            f"Use a different db name — e.g. db='{suggest}'. "
            f"To start fresh, delete or rename the existing database directory first."
        )

    # Use PMEntityStore for scan operations — eliminates per-entity disk I/O.
    # Both writer and index share the same PMNameIndex instance.
    writer, index = _get_scan_writer(req.db, req.db_path, req.incremental)
    file_manifest = _get_file_manifest(req.db, req.db_path)

    started = start_scan(
        db_root=root,
        project_root=req.project_root,
        db_name=req.db,
        writer=writer,
        index=index,
        file_manifest=file_manifest,
        concurrency=max(1, min(req.concurrency, 8)),
        incremental=req.incremental,
    )

    if not started:
        raise HTTPException(409, "Could not start scan — another task may have started concurrently.")

    return {
        "status":       "started",
        "project_root": req.project_root,
        "db":           req.db,
        "incremental":  req.incremental,
    }


@router.get("/scan/status")
async def get_scan_status(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Return the current (or most recent) scan status and progress stats."""
    root = _db_root(db, path)
    return scan_status(root)


@router.post("/scan/cancel")
async def cancel_project_scan(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Cancel the running scan for this database."""
    root = _db_root(db, path)
    return cancel_scan(root)


@router.get("/stats")
async def project_mapper_stats(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Return a combined view: last scan info + file manifest stats +
    entity count breakdown by ProjectMapper-created types.
    """
    root   = _db_root(db, path)
    status = scan_status(root)

    fm_stats = _get_file_manifest(db, path).stats()

    writer, _ = _get_mutation_writer(db, path)
    pm_types = {"module", "class", "function", "service", "endpoint", "model",
                "workflow", "config", "dependency", "decision", "goal", "constraint"}
    type_counts: dict[str, int] = {}
    total_pm_entities = 0
    try:
        for e in writer.list_all():
            t = e.get("type", "other")
            if t in pm_types:
                type_counts[t] = type_counts.get(t, 0) + 1
                total_pm_entities += 1
    except Exception:
        pass

    return {
        "last_scan":          status,
        "file_manifest":      fm_stats,
        "entity_counts":      type_counts,
        "total_pm_entities":  total_pm_entities,
    }


# ---------------------------------------------------------------------------
# Query endpoints
# ---------------------------------------------------------------------------

class ImpactRequest(BaseModel):
    entity:        str                         # entity name or ID to analyse
    db:            str = "default"
    path:          Optional[str] = None
    depth:         int = 2                     # 1–4 hops
    via_kinds:     Optional[list[str]] = None  # restrict to these relation kinds
    exclude_tests:  bool = True                # filter test-file entities from results
    slim:           bool = False               # return name+file_path only (~16 tok/entity)
    summary_depth:  int  = 1                   # include summaries only for hop <= this value


class ContextRequest(BaseModel):
    q:            str                                # natural language task description
    db:           str = "default"
    path:         Optional[str] = None
    entities:     Optional[list[str]] = None        # explicit anchor entity names
    depth:        int = 1                           # expansion hops (0–2)
    detail_level: str = "medium"                    # "high" | "medium" | "low"
    max_results:  int = 40
    slim:         bool = False                       # return name+file_path only (~16 tok/entity)


class PathRequest(BaseModel):
    from_entity: str                  # name or ID of starting entity
    to_entity:   str                  # name or ID of destination entity
    db:          str = "default"
    path:        Optional[str] = None
    max_hops:    int = 6
    slim:        bool = False          # return name+file_path only per path node


class ContributeRequest(BaseModel):
    entity_name: str                              # name of the entity to update
    db:          str = "default"
    path:        Optional[str] = None
    properties:  dict[str, str] = {}              # key-value property updates
    relations:   list[dict[str, str]] = []         # [{ kind, target_name, note }]
    rationale:   str = ""                          # free-text explanation (stored as timeline event)
    source:      str = "agent"                     # caller identifier


@router.get("/query/cache")
async def query_cache_stats(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Return the current state of the in-memory query cache."""
    from .query_cache import get_query_cache
    return get_query_cache().stats()


@router.post("/query/impact")
async def query_impact(req: ImpactRequest):
    """
    Find all entities that would be affected if the given entity changes.

    Traverses only the relation kinds that represent real code dependencies
    (calls, imports, depends_on, uses, etc.) — not structural relations like
    parent_of or contains. Results are grouped by hop distance from the subject.

    depth 1 = direct dependents only
    depth 2 = dependents of dependents (default)
    depth 3–4 = wider blast radius (can be slow on large graphs)
    """
    from .query import impact_query
    from .query_cache import get_query_cache

    depth      = max(1, min(req.depth, 4))
    root       = _db_root(req.db, req.path)
    entity_map, index = await get_query_cache().get(root)

    result = await asyncio.to_thread(
        impact_query, req.entity, entity_map, index, depth,
        req.via_kinds, req.exclude_tests, req.slim, req.summary_depth,
    )

    if result.get("not_found"):
        raise HTTPException(404, f"Entity {req.entity!r} not found in database {req.db!r}")
    return result


@router.post("/query/context")
async def query_context(req: ContextRequest):
    """
    Return a focused context package for an agent working on a described task.

    Keyword-scores all entities against the query, seeds from the best matches
    (and any explicitly anchored entities), then expands by following relations
    to surface closely connected architecture.

    detail_level controls which entity types are included:
      high   — modules, services, decisions, goals, constraints
      medium — + classes, components, workflows, configs, dependencies
      low    — + functions, endpoints, models (full implementation detail)
    """
    from .query import context_query
    from .query_cache import get_query_cache

    depth      = max(0, min(req.depth, 2))
    root       = _db_root(req.db, req.path)
    entity_map, index = await get_query_cache().get(root)

    result = await asyncio.to_thread(
        context_query,
        req.q,
        entity_map,
        index,
        req.entities,
        8,            # max_seeds
        depth,
        req.detail_level,
        req.max_results,
        req.slim,
    )
    return result


@router.post("/query/path")
async def query_path(req: PathRequest):
    """
    Find the shortest path between two entities in the knowledge graph.

    Traverses all relation kinds in both directions (undirected).
    Useful for answering "how does the auth system connect to the payment flow?"
    """
    from .query import shortest_path
    from .query_cache import get_query_cache

    root       = _db_root(req.db, req.path)
    entity_map, index = await get_query_cache().get(root)

    result = await asyncio.to_thread(
        shortest_path,
        req.from_entity,
        req.to_entity,
        entity_map,
        index,
        max(2, min(req.max_hops, 8)),
        req.slim,
    )
    return result


@router.get("/delta")
async def project_delta(
    project_root:   str  = Query(..., description="Absolute path to the project directory"),
    db:             str  = Query("default"),
    path:           Optional[str] = Query(None),
    compute_hashes: bool = Query(True,  description="Compute file hashes to detect modifications (slower)"),
    include_lists:  bool = Query(False, description="Include full file lists in response (can be large)"),
):
    """
    Compare the project directory against the FileManifest and return a
    structured diff — no database writes.

    Returns counts of new / modified / deleted / unchanged files.
    Pass include_lists=true to get the full file paths in each bucket.

    Typical use cases
    -----------------
    - Preview what an incremental scan will process before running it.
    - Detect deleted files to manually trigger a cleanup.
    - CI pipelines that need to know if a re-scan is necessary.
    """
    from .delta import compute_delta

    file_manifest = _get_file_manifest(db, path)
    try:
        delta = await asyncio.to_thread(
            compute_delta,
            project_root,
            file_manifest,
            compute_hashes=compute_hashes,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(400, str(exc))

    response = delta.summary()

    if include_lists:
        response["new_file_paths"]      = [f.path for f in delta.new_files]
        response["modified_file_paths"] = [
            {"path": f.path, "old_hash": f.old_hash[:16] + "…", "entity_ids": f.entity_ids}
            for f in delta.modified_files
        ]
        response["deleted_file_paths"]  = delta.deleted_files

    return response


@router.post("/cleanup")
async def run_cleanup(
    project_root: str = Query(..., description="Absolute path to the project directory"),
    db:           str = Query("default"),
    path:         Optional[str] = Query(None),
):
    """
    Retire entities whose source files have been deleted from the project.

    Walks the FileManifest and checks each recorded file against the live
    filesystem.  For every file that no longer exists:
      - Marks its associated entities as status='deleted'.
      - Appends a timeline event with the deletion reason.
      - Removes the file entry from the FileManifest.

    This runs automatically at the end of every incremental scan, but can also
    be triggered manually (e.g. after manually deleting files outside a scan).

    Returns a summary of how many files and entities were retired.
    """
    from .cleanup import run_deletion_cleanup

    root          = _db_root(db, path)
    writer, index = _get_mutation_writer(db, path)
    file_manifest = _get_file_manifest(db, path)

    project_path = Path(project_root)
    if not project_path.exists():
        raise HTTPException(400, f"Project root does not exist: {project_root}")

    try:
        result = await asyncio.to_thread(
            run_deletion_cleanup,
            project_path,
            file_manifest,
            writer,
            index,
        )
        # PM-store databases: persist retirements to the snapshot.
        # Skip the flush when nothing changed to avoid a pointless
        # snapshot rewrite + query-cache invalidation.
        if result.retired_count and hasattr(writer, "flush"):
            await asyncio.to_thread(writer.flush)
    except Exception as exc:
        raise HTTPException(500, f"Cleanup failed: {exc}")

    return {
        "project_root":       project_root,
        "db":                 db,
        "deleted_file_count": result.deleted_file_count,
        "retired_count":      result.retired_count,
        "deleted_files":      result.deleted_files,
        "errors":             result.errors,
    }


@router.get("/mcp/tools")
async def list_mcp_tools():
    """
    Return the MCP tool schemas for all ProjectMapper tools.

    These are the same schemas exposed by the standalone MCP server
    (project_mapper.mcp_server) and published in tools.json.
    Useful for Cursor, Antigravity, and other HTTP-based MCP hosts.
    """
    from .mcp_tools import TOOL_SCHEMAS
    return {
        "schema_version": "2024-11-05",
        "server":         "project-mapper",
        "tools":          TOOL_SCHEMAS,
        "tool_count":     len(TOOL_SCHEMAS),
        "stdio_command":  "pm-mcp --db <db_name>",
    }


@router.post("/contribute")
async def agent_contribute(req: ContributeRequest):
    """
    Write agent-discovered knowledge back into the graph.

    Accepts a structured contribution: property updates, new relations, and a
    free-text rationale. The rationale is stored as a timeline event so the
    history of why decisions were made is preserved.

    Designed for AI coding agents (Claude Code, Cursor, etc.) to call after
    implementing a feature or making an architectural decision.
    """
    from .query import build_entity_map, apply_contribution, _resolve_entity

    writer, index = _get_mutation_writer(req.db, req.path)

    entity_map = await asyncio.to_thread(build_entity_map, writer)
    entity = _resolve_entity(req.entity_name, entity_map, index)
    if not entity:
        raise HTTPException(404, f"Entity {req.entity_name!r} not found in database {req.db!r}")

    result = await asyncio.to_thread(
        apply_contribution,
        entity,
        req.properties,
        req.relations,
        req.rationale,
        req.source,
        writer,
        index,
    )

    # PM-store databases: persist the in-memory mutations to the snapshot.
    if hasattr(writer, "flush"):
        await asyncio.to_thread(writer.flush)

    return result
