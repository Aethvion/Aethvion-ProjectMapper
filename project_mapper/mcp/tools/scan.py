"""scan MCP tool."""
from __future__ import annotations

from typing import Any, Optional

from .base import MCPContext


SCHEMA = {'name': 'pm_scan',
 'description': 'Scan a project directory and populate the knowledge graph via static AST '
                'analysis. Creates module/class/function entities and wires their relations. '
                'With incremental=true (default) only changed files are reprocessed. By '
                'default this call BLOCKS until the scan completes. Pass background=true to '
                'return immediately and poll pm_stats for progress — recommended for large '
                'projects (500+ files) over MCP to avoid timeouts.',
 'inputSchema': {'type': 'object',
                 'properties': {'project_root': {'type': 'string',
                                                 'description': 'Absolute path to the project '
                                                                'directory to scan.'},
                                'incremental': {'type': 'boolean',
                                                'description': "Skip files whose hash hasn't "
                                                               'changed (default true).',
                                                'default': True},
                                'concurrency': {'type': 'integer',
                                                'description': 'Parallel file processing limit '
                                                               '(default 4).',
                                                'default': 4},
                                'background': {'type': 'boolean',
                                               'description': 'Start scan in a background '
                                                              'thread and return immediately '
                                                              '(default false). Use '
                                                              'background=true for large '
                                                              'projects to avoid MCP client '
                                                              'timeouts; then call pm_stats to '
                                                              'check when the scan completes.',
                                               'default': False}},
                 'required': ['project_root']}}


def handle_pm_scan(args: dict[str, Any], ctx: MCPContext) -> str:
    import asyncio, threading, time
    from ...core.scanner import run_scan

    project_root = args.get("project_root") or ctx.project_root
    incremental  = bool(args.get("incremental", True))
    concurrency  = max(1, min(int(args.get("concurrency", 4)), 8))
    background   = bool(args.get("background", False))

    if not project_root:
        raise ValueError(
            "project_root is required (or start the server with --project-root)"
        )

    project_path = Path(project_root).resolve()
    project_root = str(project_path)
    if not project_path.exists():
        raise ValueError(f"Project root does not exist: {project_root}")
    if not project_path.is_dir():
        raise ValueError(f"Not a directory: {project_root}")

    # Warn if this database was previously scanned from a different project.
    # The scan's deletion-cleanup pass will retire the previous project's
    # entities and prune their stubs, but the agent should know it happened.
    project_mismatch_warning = ""
    try:
        from ...core.scanner import _read_scaninfo
        prev_info = _read_scaninfo(ctx.db_root)
        prev_root = prev_info.get("project_root", "")
        if prev_root and str(Path(prev_root).resolve()) != project_root:
            project_mismatch_warning = (
                f"\nNote: This database previously indexed a different project "
                f"('{Path(prev_root).name}'). That project's entities will be "
                "retired by this scan — use one database per project to keep "
                "both indexed."
            )
    except Exception:
        pass

    lock = ctx.scan_lock

    if background:
        # Non-blocking: start scan in background thread, return immediately
        def _run_bg():
            if lock is not None:
                lock.acquire()
            try:
                asyncio.run(
                    run_scan(
                        db_root=ctx.db_root,
                        project_root=project_root,
                        db_name=ctx.db_name,
                        writer=ctx.writer,
                        index=ctx.index,
                        file_manifest=ctx.file_manifest,
                        concurrency=concurrency,
                        incremental=incremental,
                    )
                )
            finally:
                if lock is not None:
                    lock.release()

        t = threading.Thread(target=_run_bg, daemon=True)
        t.start()
        mode = "incremental" if incremental else "full"
        msg = (
            f"Scan started ({mode}): {project_root}\n"
            f"Database: {ctx.db_name}\n\n"
            "Scan is running in the background.\n"
            "Call pm_stats to check progress — status will change from 'scanning' to 'completed'."
        )
        if project_mismatch_warning:
            msg += project_mismatch_warning
        return msg

    # Blocking mode (default)
    if lock is not None:
        lock.acquire()
    t0 = time.monotonic()
    try:
        asyncio.run(
            run_scan(
                db_root=ctx.db_root,
                project_root=project_root,
                db_name=ctx.db_name,
                writer=ctx.writer,
                index=ctx.index,
                file_manifest=ctx.file_manifest,
                concurrency=concurrency,
                incremental=incremental,
            )
        )
    finally:
        elapsed = time.monotonic() - t0
        if lock is not None:
            lock.release()

    # Read the final scan stats
    from ...core.scanner import scan_status
    status = scan_status(ctx.db_root)
    stats  = status.get("stats", {})

    lines = [
        f"Scan {'completed' if status.get('status') == 'completed' else status.get('status', '?')}: "
        f"{project_root}",
        f"Database:   {ctx.db_name}",
        f"Duration:   {elapsed:.1f}s",
        "",
        f"Files:    {stats.get('files_scanned', 0)} scanned  "
        f"{stats.get('files_skipped_unchanged', 0)} skipped (unchanged)  "
        f"{stats.get('files_skipped_unsupported', 0)} skipped (binary/empty)  "
        f"{stats.get('files_deleted', 0)} deleted",
        f"Entities: {stats.get('entities_created', 0)} created  "
        f"{stats.get('entities_updated', 0)} updated  "
        f"{stats.get('entities_pruned', 0)} pruned  "
        f"{stats.get('entities_retired', 0)} retired",
    ]
    errs = stats.get("errors", [])
    if errs:
        lines.append(f"Errors:   {len(errs)} (first: {errs[0].get('error', '')[:80]})")

    if project_mismatch_warning:
        lines.append(project_mismatch_warning)

    return "\n".join(lines)
