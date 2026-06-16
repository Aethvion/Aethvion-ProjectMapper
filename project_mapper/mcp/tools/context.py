"""context MCP tool."""
from __future__ import annotations

from typing import Any

from .base import MCPContext, _entity_block

SCHEMA = {'name': 'pm_context',
 'description': 'Retrieve a focused context package relevant to a coding task. Keyword-scores '
                'all entities in the knowledge graph against the task description, seeds from '
                'the best matches (and any named anchor entities), then expands by following '
                'relations. Use this BEFORE starting any non-trivial feature or refactor so '
                'you understand the existing architecture and avoid breaking changes.',
 'inputSchema': {'type': 'object',
                 'properties': {'query': {'type': 'string',
                                          'description': 'Natural-language description of the '
                                                         "task, e.g. 'add rate limiting to the "
                                                         "auth endpoints'."},
                                'entities': {'type': 'array',
                                             'items': {'type': 'string'},
                                             'description': 'Optional list of entity names to '
                                                            'anchor the search on (boosted in '
                                                            'scoring).',
                                             'default': []},
                                'detail_level': {'type': 'string',
                                                 'enum': ['high', 'medium', 'low'],
                                                 'description': 'high=modules/services/decisions/goals/constraints, '
                                                                'medium=+classes/components, '
                                                                'low=+functions/endpoints/models '
                                                                '(default: medium)',
                                                 'default': 'medium'},
                                'depth': {'type': 'integer',
                                          'description': 'Relation-expansion hops beyond '
                                                         'keyword seeds (0–2). Default 1.',
                                          'default': 1},
                                'max_results': {'type': 'integer',
                                                'description': 'Maximum entities to include '
                                                               '(default 30).',
                                                'default': 30},
                                'slim': {'type': 'boolean',
                                         'description': 'Slim output: one line per entity '
                                                        'showing name + file:line only. Cuts '
                                                        'token cost ~65% vs full mode. Use '
                                                        'when you only need to know what files '
                                                        'to read, not what the entities do.',
                                         'default': False}},
                 'required': ['query']}}


def handle_pm_context(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.query import build_entity_map, context_query

    q            = args.get("query", "").strip()
    anchors      = args.get("entities") or []
    detail_level = args.get("detail_level", "medium")
    depth        = max(0, min(int(args.get("depth", 1)), 2))
    max_results  = min(int(args.get("max_results", 30)), 60)
    slim         = bool(args.get("slim", False))

    if not q:
        raise ValueError("'query' is required")

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "The knowledge graph is empty. Run pm_scan first."

    result = context_query(
        q, entity_map, ctx.index,
        anchor_names=anchors,
        max_seeds=10,
        expansion_hops=depth,
        detail_level=detail_level,
        max_results=max_results,
        slim=slim,
    )

    if not result.get("total"):
        return f"No entities found for: {q!r}\nTry running pm_scan to populate the graph."

    lines = [
        f"Context for task: {q!r}",
        f"Detail level: {detail_level}  |  Entities: {result['total']}  |  ~{result.get('token_estimate', 0)} tokens",
        "",
    ]

    by_type: dict[str, list[dict]] = result.get("by_type", {})
    # Sort by type priority
    type_order = ["decision", "goal", "constraint", "service", "module",
                  "workflow", "component", "class", "config", "dependency",
                  "function", "endpoint", "model"]
    ordered_types = [t for t in type_order if t in by_type] + \
                    [t for t in by_type if t not in type_order]

    for etype in ordered_types:
        entities = by_type[etype]
        if not entities:
            continue
        heading = etype.upper() + ("S" if not etype.endswith("s") else "")
        lines.append(f"{heading} ({len(entities)}):")
        for e in entities:
            lines.append(_entity_block(e))
        lines.append("")

    return "\n".join(lines).rstrip()
