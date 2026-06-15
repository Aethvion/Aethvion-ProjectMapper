"""delta MCP tool."""
from __future__ import annotations

from typing import Any, Optional

from .base import MCPContext


SCHEMA = {'name': 'pm_delta',
 'description': 'Show what has changed in the project since the last scan — new files, '
                'modified files, and deleted files — without making any database changes. Use '
                'to decide whether a re-scan is needed, or to preview what an incremental scan '
                'would process.',
 'inputSchema': {'type': 'object',
                 'properties': {'project_root': {'type': 'string',
                                                 'description': 'Absolute path to the project '
                                                                'directory. Uses the server '
                                                                'default if omitted.'}},
                 'required': []}}


def handle_pm_delta(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.delta import compute_delta

    project_root = args.get("project_root") or ctx.project_root
    if not project_root:
        return (
            "No project_root specified and no default configured.\n"
            "Pass project_root or start the server with --project-root."
        )

    project_root = str(Path(project_root).resolve())

    try:
        delta = compute_delta(project_root, ctx.file_manifest)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ValueError(str(exc))

    lines = [
        f"Delta for: {project_root}",
        f"Database:  {ctx.db_name}",
        "",
        f"  New files:      {len(delta.new_files)}",
        f"  Modified files: {len(delta.modified_files)}",
        f"  Deleted files:  {len(delta.deleted_files)}",
        f"  Unchanged:      {delta.unchanged_count}",
        f"  Total on disk:  {delta.total_on_disk}",
        f"  In manifest:    {delta.total_in_manifest}",
        "",
    ]

    if not delta.has_changes:
        lines.append("No changes detected — graph is up to date.")
        return "\n".join(lines)

    lines.append("Changes detected:")

    if delta.modified_files:
        lines.append(f"\nModified ({len(delta.modified_files)}):")
        for f in delta.modified_files[:20]:
            eids = f.entity_ids
            note = f"  [{len(eids)} entit{'y' if len(eids) == 1 else 'ies'}]" if eids else ""
            lines.append(f"  * {f.path}{note}")
        if len(delta.modified_files) > 20:
            lines.append(f"  ... and {len(delta.modified_files) - 20} more")

    if delta.new_files:
        lines.append(f"\nNew ({len(delta.new_files)}):")
        for f in delta.new_files[:20]:
            lines.append(f"  + {f.path}")
        if len(delta.new_files) > 20:
            lines.append(f"  ... and {len(delta.new_files) - 20} more")

    if delta.deleted_files:
        lines.append(f"\nDeleted ({len(delta.deleted_files)}):")
        for path in delta.deleted_files[:20]:
            lines.append(f"  - {path}")
        if len(delta.deleted_files) > 20:
            lines.append(f"  ... and {len(delta.deleted_files) - 20} more")

    lines.append("")
    lines.append("Run pm_scan with incremental=true to process these changes.")
    return "\n".join(lines)
