"""path MCP tool."""

from __future__ import annotations

from typing import Any

from .base import MCPContext

SCHEMA = {
    "name": "pm_path",
    "description": "Find the shortest connection between two entities in the knowledge graph. "
    "Traverses all relation kinds in both directions (undirected). Useful for "
    "answering 'how does the auth system connect to the payment flow?' or tracing "
    "why a change in one module might affect another.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "from_entity": {"type": "string", "description": "Name or ID of the starting entity."},
            "to_entity": {"type": "string", "description": "Name or ID of the destination entity."},
            "max_hops": {
                "type": "integer",
                "description": "Maximum path length to search (default 6).",
                "default": 6,
            },
        },
        "required": ["from_entity", "to_entity"],
    },
}


def handle_pm_path(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.query import build_entity_map, shortest_path

    from_name = args.get("from_entity", "").strip()
    to_name = args.get("to_entity", "").strip()
    max_hops = max(2, min(int(args.get("max_hops", 6)), 8))

    if not from_name or not to_name:
        raise ValueError("'from_entity' and 'to_entity' are required")

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = shortest_path(from_name, to_name, entity_map, ctx.index, max_hops=max_hops)

    not_found_msg = result.get("not_found_message", "")
    if not_found_msg:
        return f"Could not find path: {from_name!r} -> {to_name!r}\n{not_found_msg}"

    if not result.get("found"):
        return (
            f"No path found between {from_name!r} and {to_name!r} "
            f"within {max_hops} hops.\n"
            "They may be in disconnected parts of the graph."
        )

    path = result.get("path", [])
    length = result.get("length", 0)

    lines = [
        f"Shortest path: {from_name} -> {to_name}",
        f"Length: {length} hop{'s' if length != 1 else ''}",
        "",
        "Chain:",
    ]

    # Path steps are _entity_stub dicts: {name, type, kind, relation, relation_reverse}
    # relation_reverse=True means this node was reached via a reversed edge —
    # i.e. the actual graph edge points the other way.
    chain_parts = []
    for step in path:
        node = step.get("name", step.get("id", "?"))
        rel = step.get("relation", "")
        is_rev = step.get("relation_reverse", False)
        if rel:
            chain_parts.append(f"{node} {'<--' + rel + '--' if is_rev else '--' + rel + '-->'}")
        else:
            chain_parts.append(node)

    # Format chain: wrap at ~80 chars
    chain_str = " ".join(chain_parts)
    lines.append(f"  {chain_str}")

    return "\n".join(lines)
