"""impact MCP tool."""
from __future__ import annotations

from typing import Any, Optional

from .base import MCPContext


SCHEMA = {'name': 'pm_impact',
 'description': 'Find all entities that would be affected if the named entity changes. '
                'Traverses dependency-propagating relations (calls, imports, depends_on, uses, '
                'reads_from, etc.) outward from the subject. Use before refactoring or '
                'deleting a module/class to understand the blast radius.',
 'inputSchema': {'type': 'object',
                 'properties': {'entity': {'type': 'string',
                                           'description': 'Name or ID of the entity to '
                                                          'analyse.'},
                                'depth': {'type': 'integer',
                                          'description': 'BFS depth: 1=direct dependents, '
                                                         '2=transitive (default), 3–4=wide '
                                                         'radius.',
                                          'default': 2},
                                'slim': {'type': 'boolean',
                                         'description': 'Slim output: one line per entity '
                                                        'showing name + file:line only. Cuts '
                                                        'token cost ~65% vs full mode.',
                                         'default': False}},
                 'required': ['entity']}}


def handle_pm_impact(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.query import build_entity_map, impact_query

    entity_name = args.get("entity", "").strip()
    depth       = max(1, min(int(args.get("depth", 2)), 4))
    slim        = bool(args.get("slim", False))

    if not entity_name:
        raise ValueError("'entity' is required")

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = impact_query(entity_name, entity_map, ctx.index, max_depth=depth, slim=slim)

    if result.get("not_found"):
        return (
            f"Entity {entity_name!r} not found in the graph.\n"
            "Check spelling or run pm_stats to see what's indexed."
        )

    # subject is an _entity_stub dict (name, type, kind, …)
    subject_raw = result.get("subject", {})
    subject     = subject_raw.get("name", entity_name) if isinstance(subject_raw, dict) else str(subject_raw)
    affected    = result.get("affected", [])
    total    = result.get("total", 0)

    if total == 0:
        return (
            f"Impact analysis for: {subject}\n\n"
            "No dependents found. Nothing in the graph depends on this entity."
        )

    lines = [
        f"Impact analysis for: {subject}",
        f"Depth: {depth} hops  |  Affected: {total} entit{'y' if total == 1 else 'ies'}",
        "",
    ]

    # Group by hop
    by_hop: dict[int, list[dict]] = {}
    for item in affected:
        h = item.get("hop", 1)
        by_hop.setdefault(h, []).append(item)

    for hop in sorted(by_hop):
        items = by_hop[hop]
        label = "direct dependent" if hop == 1 else f"transitive (hop {hop})"
        lines.append(f"HOP {hop} — {label} ({len(items)}):")
        for item in items:
            name  = item.get("name", item.get("entity_id", "?"))
            via   = item.get("via", "")
            via_str = f"  (via: {via})" if via else ""
            if slim or ("type" not in item and "entity_id" not in item):
                fp   = item.get("file_path", "")
                line = item.get("line", "")
                loc  = f" — {fp}:{line}" if fp and line else (f" — {fp}" if fp else "")
                lines.append(f"  * {name}{loc}{via_str}")
            else:
                etype = item.get("type", "")
                summary = item.get("summary", "")
                fp    = item.get("file_path", "")
                line  = item.get("line", "")
                loc   = f"  ({fp}:{line})" if fp and line else (f"  ({fp})" if fp else "")
                desc  = f" — {summary[:60]}" if summary else ""
                lines.append(f"  * {name} [{etype}]{loc}{desc}{via_str}")
        lines.append("")

    lines.append(
        "If you change or delete this entity, review all listed dependents."
    )
    return "\n".join(lines).rstrip()
