"""visualize MCP tool."""
from __future__ import annotations

from typing import Any

from .base import MCPContext


SCHEMA = {'name': 'pm_visualize',
 'description': 'Generate a Mermaid or DOT subgraph diagram centred on a named entity. Shows '
                "the entity's call/import/dependency neighbourhood up to a configurable depth. "
                'Useful for understanding blast radius, explaining a subsystem visually, or '
                'producing architecture diagrams for docs and PRs. Output is a fenced Mermaid '
                'code block by default — renders natively in GitHub/GitLab markdown, VS Code '
                'Mermaid extension, and Obsidian.',
 'inputSchema': {'type': 'object',
                 'properties': {'entity': {'type': 'string',
                                           'description': 'Name of the entity to centre the '
                                                          "diagram on (e.g. 'UserService', "
                                                          "'auth.py')."},
                                'depth': {'type': 'integer',
                                          'description': 'Traversal hops from the centre '
                                                         'entity (1–4, default 2).',
                                          'default': 2},
                                'direction': {'type': 'string',
                                              'enum': ['out', 'in', 'both'],
                                              'description': 'out = what this entity '
                                                             'calls/imports; in = who '
                                                             'calls/imports this entity; both '
                                                             '= full neighbourhood (default).',
                                              'default': 'both'},
                                'relations': {'type': 'array',
                                              'items': {'type': 'string'},
                                              'description': 'Relation kinds to include. '
                                                             'Default: calls, imports, uses, '
                                                             'extends, implements, depends_on. '
                                                             "Pass ['calls'] for a pure call "
                                                             "graph or ['imports'] for "
                                                             'dependencies only.',
                                              'default': []},
                                'format': {'type': 'string',
                                           'enum': ['mermaid', 'dot'],
                                           'description': "Output format: 'mermaid' (default) "
                                                          "or 'dot' (Graphviz).",
                                           'default': 'mermaid'},
                                'max_nodes': {'type': 'integer',
                                              'description': 'Maximum nodes to include in the '
                                                             'diagram (default 40).',
                                              'default': 40},
                                'project_root': {'type': 'string',
                                                 'description': 'Absolute path to the project '
                                                                'root (needed if not set '
                                                                'globally).'}},
                 'required': ['entity']}}


def handle_pm_visualize(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.query import build_entity_map
    from ...core.visualize import build_diagram

    entity_name = (args.get("entity") or "").strip()
    if not entity_name:
        raise ValueError("'entity' is required")

    entity_map = build_entity_map(ctx.writer)
    res = build_diagram(
        entity_map, ctx.index, entity_name,
        depth=args.get("depth", 2),
        direction=args.get("direction", "both"),
        relations=args.get("relations") or None,
        fmt=args.get("format", "mermaid"),
        max_nodes=args.get("max_nodes", 40),
    )

    status = res["status"]
    if status == "empty":
        return "Knowledge graph is empty. Run pm_scan first."
    if status == "not_found":
        return (
            f"Entity {entity_name!r} not found in the knowledge graph. "
            "Try pm_find to locate it, or run pm_scan if the project hasn't been indexed."
        )
    if status == "ambiguous":
        names = ", ".join(res["candidates"][:6])
        return (
            f"Ambiguous: {len(res['candidates'])} entities match {entity_name!r}. "
            f"Be more specific. Candidates: {names}"
        )
    if status == "no_relations":
        kinds_str = ", ".join(res["kinds"])
        return (
            f"Entity {res['center']!r} has no {kinds_str} relations in the graph. "
            "Run pm_scan if the project hasn't been indexed, or broaden the relations filter."
        )

    header = (
        f"Diagram: {res['center']} ({res['center_type']})\n"
        f"Nodes: {res['nodes']}  Edges: {res['edges']}  Depth: {res['depth']}\n\n"
    )
    trailer = (
        f"\nGraph capped at {res['max_nodes']} nodes — pass max_nodes={res['max_nodes'] * 2} to expand."
        if res["truncated"] else ""
    )
    return header + res["diagram"] + trailer
