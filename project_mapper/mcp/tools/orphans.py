"""orphans MCP tool."""
from __future__ import annotations

from typing import Any, Optional

from .base import MCPContext


SCHEMA = {'name': 'pm_orphans',
 'description': 'Find entities that have no inbound calls, imports, or dependencies — '
                'potential dead code. Entry points, dunder methods, and test functions are '
                'filtered out automatically. Use before a cleanup pass to identify candidates '
                'for removal. Note: dynamic dispatch, decorator-registered handlers, and '
                "public API won't have graph callers — review results before deleting "
                'anything.',
 'inputSchema': {'type': 'object',
                 'properties': {'types': {'type': 'array',
                                          'items': {'type': 'string'},
                                          'description': 'Limit to specific entity types, e.g. '
                                                         "['function', 'class']. Returns all "
                                                         'code types if omitted.',
                                          'default': []},
                                'include_modules': {'type': 'boolean',
                                                    'description': 'Include module-level '
                                                                   'entities (files/packages, '
                                                                   'often entry points). '
                                                                   'Default false.',
                                                    'default': False},
                                'max_results': {'type': 'integer',
                                                'description': 'Maximum entities to return '
                                                               '(default 100).',
                                                'default': 100}},
                 'required': []}}


def handle_pm_orphans(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.query import build_entity_map, orphan_query

    types_filter    = args.get("types") or None
    include_modules = bool(args.get("include_modules", False))
    max_results     = min(int(args.get("max_results", 100)), 200)

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = orphan_query(
        entity_map,
        types=types_filter,
        include_modules=include_modules,
        max_results=max_results,
    )

    total     = result.get("total", 0)
    skipped   = result.get("skipped_count", 0)
    orphans   = result.get("orphans", [])

    if total == 0:
        return (
            "No orphaned entities found — everything has at least one inbound dependency.\n"
            f"({skipped} entry points / dunder methods / test functions filtered out.)"
        )

    lines = [
        f"Orphaned entities (no inbound calls/imports): {total}",
        f"Filtered out: {skipped} entry points / dunder methods / test functions",
        "",
        "Note: dynamic callers (decorators, dynamic dispatch, reflection) won't",
        "      appear in the graph. Review before removing anything.",
        "",
    ]

    by_type: dict[str, list[dict]] = {}
    for o in orphans:
        by_type.setdefault(o.get("type", "other"), []).append(o)

    type_order = ["class", "function", "endpoint", "model", "service",
                  "component", "workflow", "config", "module", "other"]
    ordered_types = [t for t in type_order if t in by_type] + \
                    [t for t in by_type if t not in type_order]

    for etype in ordered_types:
        items = by_type[etype]
        heading = etype.upper() + ("S" if not etype.endswith("s") else "")
        lines.append(f"{heading} ({len(items)}):")
        for o in items:
            name    = o.get("name", "?")
            fp      = o.get("file_path", "")
            line    = str(o.get("line_start", ""))
            loc     = f"  {fp}:{line}" if fp and line else f"  {fp}" if fp else ""
            summary = o.get("summary", "")
            desc    = f"\n      {summary[:80]}" if summary else ""
            lines.append(f"  * {name}{loc}{desc}")
        lines.append("")

    return "\n".join(lines).rstrip()
