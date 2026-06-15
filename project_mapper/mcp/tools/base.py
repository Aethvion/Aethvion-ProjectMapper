"""
project_mapper.mcp.tools.base
Shared context object (MCPContext) and entity-formatting helpers used across
the individual tool modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class MCPContext:
    db_root:        Path
    db_name:        str
    writer:         Any    # PMEntityStore
    index:          Any    # NameIndex
    file_manifest:  Any    # FileManifest
    project_root:   Optional[str] = None   # default project dir for scan/delta
    scan_lock:      Optional[Any] = None   # threading.Lock — shared with AutoScanner
    auto_scanner:   Optional[Any] = None   # AutoScanner instance (when --watch active)


def _prop_line(entity: dict[str, Any]) -> str:
    """Single-line label: 'Name [type/kind] — summary'"""
    name    = entity.get("name", "?")
    etype   = entity.get("type", "")
    kind    = entity.get("kind", "")
    summary = entity.get("sections", {}).get("core", {}).get("summary", "")
    label   = kind if kind and kind != etype else etype
    summary_part = f" — {summary[:80]}" if summary else ""
    return f"  * {name} [{label}]{summary_part}"


def _entity_block(entity: dict[str, Any], *, show_relations: bool = False) -> str:
    """Multi-line entity description for context results."""
    # Slim stub: returned by _entity_stub(slim=True) — only name + file_path + line.
    # No id, no type, no sections. Render as a compact single line.
    if "sections" not in entity and "id" not in entity and "type" not in entity:
        name = entity.get("name", "?")
        fp   = entity.get("file_path", "")
        line = entity.get("line", "")
        via  = entity.get("via", "")
        loc  = f" — {fp}:{line}" if fp and line else (f" — {fp}" if fp else "")
        via_part = f" (via: {via})" if via else ""
        return f"  * {name}{loc}{via_part}"

    name      = entity.get("name", "?")
    etype     = entity.get("type", "")
    kind      = entity.get("kind", "")
    status    = entity.get("status", "active")

    if "sections" in entity:
        core      = entity["sections"].get("core", {})
        props     = entity["sections"].get("properties", {})
        relations = entity["sections"].get("relations", [])
    else:
        # Flat stub from context_query / _entity_stub() — fields live at root level
        core      = entity
        props     = entity
        relations = []

    label = kind if kind and kind != etype else etype
    if status not in ("active", ""):
        label += f", {status}"

    lines = [f"  [{name}] ({label})"]

    if "sections" in entity or isinstance(props, dict):
        fp   = props.get("file_path", "")
        line = props.get("line_start", "") or props.get("line", "")
        if fp:
            loc = f"{fp}:{line}" if line else fp
            lines.append(f"    File:    {loc}")

    summary = core.get("summary", "")
    if summary:
        lines.append(f"    Summary: {summary[:200]}")

    tags = core.get("tags", [])
    if tags:
        lines.append(f"    Tags:    {', '.join(tags[:8])}")

    # Exclude stub meta-fields so they don't appear as spurious properties
    _SKIP = {"file_path", "line_start", "line_end", "line", "id", "name", "type",
              "kind", "status", "tags", "summary", "relevance_score", "hop", "via"}
    useful_props = {k: v for k, v in props.items() if k not in _SKIP and v}
    if useful_props:
        for k, v in list(useful_props.items())[:4]:
            lines.append(f"    {k}: {str(v)[:80]}")

    if show_relations and relations:
        for r in relations[:5]:
            lines.append(f"    -> {r.get('kind')} {r.get('target_name', r.get('target_id', '?'))}")

    if "sections" in entity:
        timeline = entity["sections"].get("timeline", [])
        if timeline:
            lines.append("    Timeline:")
            for entry in timeline[-3:]:
                lines.append(f"      [{entry.get('date', '')}] {entry.get('event', '')[:120]}")

    return "\n".join(lines)
