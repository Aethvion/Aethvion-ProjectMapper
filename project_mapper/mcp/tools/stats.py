"""stats MCP tool."""
from __future__ import annotations

from typing import Any, Optional

from .base import MCPContext


SCHEMA = {'name': 'pm_stats',
 'description': 'Return a quick overview of the ProjectMapper database: entity counts by type, '
                'file manifest coverage, and last scan status. Use at the start of a session '
                "to understand what's already been indexed.",
 'inputSchema': {'type': 'object', 'properties': {}, 'required': []}}


def handle_pm_stats(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.scanner import scan_status, SCANINFO

    scan = scan_status(ctx.db_root)
    fm   = ctx.file_manifest.stats()

    pm_types = {
        "module", "service", "component", "class", "function",
        "endpoint", "model", "workflow", "config", "dependency",
        "decision", "goal", "constraint",
    }
    type_counts: dict[str, int] = {}
    total = 0
    stubs = 0
    try:
        for e in ctx.writer.list_all():
            t = e.get("type", "other")
            if t in pm_types:
                type_counts[t] = type_counts.get(t, 0) + 1
                total += 1
        for e in ctx.writer.list_stubs():
            if e.get("type") in pm_types:
                stubs += 1
    except Exception:
        pass

    lines = [
        f"Database: {ctx.db_name}",
        f"Root:     {ctx.db_root}",
        "",
        f"Entities: {total} active  ({stubs} stubs)",
    ]

    if type_counts:
        by_count = sorted(type_counts.items(), key=lambda x: -x[1])
        lines.append("  Breakdown: " + "  ".join(f"{t}:{c}" for t, c in by_count))

    lines.append("")
    lines.append(f"Files tracked: {fm.get('total_files', 0)}")
    by_lang = fm.get("by_language", {})
    if by_lang:
        lang_str = "  ".join(f"{lang}:{n}" for lang, n in list(by_lang.items())[:5])
        lines.append(f"  By language: {lang_str}")

    lines.append("")
    status    = scan.get("status", "never run")
    started   = scan.get("started_at", "")
    completed = scan.get("completed_at", "")
    proj      = scan.get("project_root", "")
    lines.append(f"Last scan: {status}")
    if proj:
        lines.append(f"  Project:   {proj}")
    if started:
        lines.append(f"  Started:   {started}")
    if completed:
        lines.append(f"  Completed: {completed}")

    scan_stats = scan.get("stats", {})
    if scan_stats:
        lines.append(
            f"  Files:     {scan_stats.get('files_scanned', 0)} scanned  "
            f"{scan_stats.get('files_skipped_unchanged', 0)} skipped  "
            f"{scan_stats.get('files_deleted', 0)} deleted"
        )
        lines.append(
            f"  Entities:  {scan_stats.get('entities_created', 0)} created  "
            f"{scan_stats.get('entities_updated', 0)} updated  "
            f"{scan_stats.get('entities_pruned', 0)} pruned"
        )

    lines.append("")
    if ctx.auto_scanner is not None:
        ws = ctx.auto_scanner.status_dict()
        state = "active" if ws["active"] else "stopped"
        lines.append(
            f"Auto-scan: {state}  "
            f"(poll={ws['poll_interval_s']:.0f}s  debounce={ws['debounce_s']:.0f}s)"
        )
        lines.append(f"  Project:    {ws['project_root']}")
        lines.append(f"  Scans run:  {ws['scan_count']}")
        last_scan_info = ws["last_scan"]
        if ws["last_scan_files"] and ws["last_scan"] != "never":
            last_scan_info += f"  ({ws['last_scan_files']} file(s))"
        lines.append(
            f"  Last check: {ws['last_check']}  |  Last scan: {last_scan_info}"
        )
    else:
        lines.append("Auto-scan: off  (start server with --watch to enable)")

    return "\n".join(lines)
