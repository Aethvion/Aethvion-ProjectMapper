"""contribute MCP tool."""
from __future__ import annotations

from typing import Any

from .base import MCPContext

SCHEMA = {'name': 'pm_contribute',
 'description': 'Record agent-discovered knowledge back into the project graph. Accepts '
                'property updates, new relation declarations, and a free-text rationale that '
                'is stored as a dated timeline event. Call this after implementing a feature '
                'or making an architectural decision so future agents (and developers) can see '
                'why things are the way they are.',
 'inputSchema': {'type': 'object',
                 'properties': {'entity_name': {'type': 'string',
                                                'description': 'Name of the entity to update.'},
                                'properties': {'type': 'object',
                                               'additionalProperties': {'type': 'string'},
                                               'description': 'Key-value property updates to '
                                                              'merge into the entity.',
                                               'default': {}},
                                'relations': {'type': 'array',
                                              'items': {'type': 'object',
                                                        'properties': {'kind': {'type': 'string'},
                                                                       'target_name': {'type': 'string'},
                                                                       'note': {'type': 'string'}},
                                                        'required': ['kind', 'target_name']},
                                              'description': 'New relations to add, e.g. '
                                                             '[{kind: depends_on, target_name: '
                                                             'RateLimiter}].',
                                              'default': []},
                                'rationale': {'type': 'string',
                                              'description': 'Free-text explanation stored as '
                                                             'a timeline event.',
                                              'default': ''},
                                'source': {'type': 'string',
                                           'description': 'Identifier for the calling agent '
                                                          "(default: 'agent').",
                                           'default': 'agent'}},
                 'required': ['entity_name']}}


def handle_pm_contribute(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.query import _resolve_entity, apply_contribution, build_entity_map

    entity_name = args.get("entity_name", "").strip()
    properties  = args.get("properties", {}) or {}
    relations   = args.get("relations", []) or []
    rationale   = args.get("rationale", "") or ""
    source      = args.get("source", "agent") or "agent"

    if not entity_name:
        raise ValueError("'entity_name' is required")

    entity_map = build_entity_map(ctx.writer)
    entity     = _resolve_entity(entity_name, entity_map, ctx.index)
    if not entity:
        return (
            f"Entity {entity_name!r} not found. "
            "Check spelling or run pm_stats to see what's indexed."
        )

    summary = apply_contribution(
        entity, properties, relations, rationale, source,
        ctx.writer, ctx.index,
    )

    # Both properties_set and relations_added are lists of strings
    props_set  = summary.get("properties_set", [])
    rels_added = summary.get("relations_added", [])
    props_count = len(props_set) if isinstance(props_set, list) else int(props_set)
    rels_count  = len(rels_added) if isinstance(rels_added, list) else int(rels_added)

    lines = [
        f"Contribution recorded for: {entity_name}",
        f"  Entity ID: {summary.get('entity_id', '?')}",
        f"  Properties set: {props_count}",
        f"  Relations added: {rels_count}",
    ]

    if rationale:
        lines.append(f"  Timeline event: {rationale[:120]}")

    if not summary.get("changes_made", True):
        lines.append("  (no new changes — everything was already up to date)")

    return "\n".join(lines)
