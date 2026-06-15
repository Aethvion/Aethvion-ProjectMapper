"""visualize MCP tool."""
from __future__ import annotations

from typing import Any, Optional

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


def _viz_node_id(entity_id: str) -> str:
    """Safe Mermaid/DOT node identifier derived from entity ID."""
    return "n" + entity_id.replace("ws_", "").replace("-", "_")


def _viz_node_label(entity: dict) -> str:
    name  = entity.get("name", "?")
    etype = entity.get("type", "")
    return f"{name}\\n[{etype}]" if etype else name


def _viz_mermaid(
    center_id: str,
    nodes: dict,
    edges: list,
    truncated: bool,
) -> str:
    lines = ["```mermaid", "graph TD"]
    for eid, entity in nodes.items():
        nid   = _viz_node_id(eid)
        label = _viz_node_label(entity).replace('"', "'")
        lines.append(f'    {nid}["{label}"]')
    lines.append("")
    seen: set = set()
    for src_id, tgt_id, kind in edges:
        if src_id not in nodes or tgt_id not in nodes:
            continue
        key = (src_id, tgt_id, kind)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"    {_viz_node_id(src_id)} -->|{kind}| {_viz_node_id(tgt_id)}")
    lines.append("")
    lines.append(
        f"    style {_viz_node_id(center_id)} "
        "fill:#4a90d9,color:#fff,stroke:#2c5282,stroke-width:2px"
    )
    if truncated:
        lines.append("    %% Graph truncated — increase max_nodes to show more")
    lines.append("```")
    return "\n".join(lines)


def _viz_dot(
    center_id: str,
    nodes: dict,
    edges: list,
    truncated: bool,
) -> str:
    lines = [
        "```dot",
        "digraph pm_visualize {",
        '    rankdir=LR',
        '    node [shape=box fontname="Helvetica"]',
    ]
    for eid, entity in nodes.items():
        nid   = _viz_node_id(eid)
        label = _viz_node_label(entity).replace('"', "'")
        if eid == center_id:
            lines.append(
                f'    {nid} [label="{label}" style=filled '
                'fillcolor="#4a90d9" fontcolor=white]'
            )
        else:
            lines.append(f'    {nid} [label="{label}"]')
    lines.append("")
    seen: set = set()
    for src_id, tgt_id, kind in edges:
        if src_id not in nodes or tgt_id not in nodes:
            continue
        key = (src_id, tgt_id, kind)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f'    {_viz_node_id(src_id)} -> {_viz_node_id(tgt_id)} [label="{kind}"]')
    if truncated:
        lines.append("    // Graph truncated — increase max_nodes to show more")
    lines.append("}")
    lines.append("```")
    return "\n".join(lines)


def handle_pm_visualize(args: dict[str, Any], ctx: MCPContext) -> str:
    from collections import deque
    from ...core.query import build_entity_map

    entity_name = (args.get("entity") or "").strip()
    depth       = max(1, min(4, int(args.get("depth") or 2)))
    direction   = (args.get("direction") or "both").lower()
    rel_kinds   = frozenset(args.get("relations") or []) or _VIZ_DEFAULT_KINDS
    fmt         = (args.get("format") or "mermaid").lower()
    max_nodes   = max(5, min(150, int(args.get("max_nodes") or 40)))

    if not entity_name:
        raise ValueError("'entity' is required")

    entity_map = build_entity_map(ctx.writer)
    if not entity_map:
        return "Knowledge graph is empty. Run pm_scan first."

    # Name resolution — exact via index, then substring fallback
    center: Optional[dict] = None
    eid = ctx.index.get(entity_name)
    if eid and eid in entity_map:
        center = entity_map[eid]
    if center is None:
        lower_q = entity_name.lower()
        matches = [e for e in entity_map.values() if lower_q in e.get("name", "").lower()]
        if len(matches) == 1:
            center = matches[0]
        elif matches:
            names = ", ".join(e["name"] for e in matches[:6])
            return (
                f"Ambiguous: {len(matches)} entities match {entity_name!r}. "
                f"Be more specific. Candidates: {names}"
            )
    if center is None:
        return (
            f"Entity {entity_name!r} not found in the knowledge graph. "
            "Try pm_find to locate it, or run pm_scan if the project hasn't been indexed."
        )

    center_id = center["id"]

    # Build forward and reverse adjacency filtered by rel_kinds
    fwd: dict[str, list[tuple[str, str]]] = {}  # eid → [(target_id, kind)]
    rev: dict[str, list[tuple[str, str]]] = {}  # eid → [(source_id, kind)]
    for eid2, entity in entity_map.items():
        for rel in entity.get("sections", {}).get("relations", []):
            kind      = rel.get("kind", "")
            target_id = rel.get("target_id", "")
            if not kind or not target_id or kind not in rel_kinds:
                continue
            fwd.setdefault(eid2, []).append((target_id, kind))
            rev.setdefault(target_id, []).append((eid2, kind))

    # BFS from centre, respecting direction and depth
    visited: dict[str, int] = {center_id: 0}
    queue: deque = deque([center_id])
    collected_edges: list[tuple[str, str, str]] = []

    while queue and len(visited) < max_nodes:
        curr_id  = queue.popleft()
        curr_hop = visited[curr_id]
        if curr_hop >= depth:
            continue
        neighbors: list[tuple[str, str, str]] = []
        if direction in ("out", "both"):
            for tgt_id, kind in fwd.get(curr_id, []):
                neighbors.append((curr_id, tgt_id, kind))
        if direction in ("in", "both"):
            for src_id, kind in rev.get(curr_id, []):
                neighbors.append((src_id, curr_id, kind))
        for src_id, tgt_id, kind in neighbors:
            neighbor_id = tgt_id if src_id == curr_id else src_id
            if neighbor_id not in entity_map:
                continue
            collected_edges.append((src_id, tgt_id, kind))
            if neighbor_id not in visited:
                visited[neighbor_id] = curr_hop + 1
                if len(visited) < max_nodes:
                    queue.append(neighbor_id)

    truncated = bool(queue)
    nodes = {eid2: entity_map[eid2] for eid2 in visited if eid2 in entity_map}

    if len(nodes) <= 1 and not collected_edges:
        kinds_str = ", ".join(sorted(rel_kinds))
        return (
            f"Entity {center['name']!r} has no {kinds_str} relations in the graph. "
            "Run pm_scan if the project hasn't been indexed, or broaden the relations filter."
        )

    edge_count = len({(s, t, k) for s, t, k in collected_edges})
    header = (
        f"Diagram: {center['name']} ({center.get('type', 'entity')})\n"
        f"Nodes: {len(nodes)}  Edges: {edge_count}  Depth: {depth}\n\n"
    )

    if fmt == "dot":
        diagram = _viz_dot(center_id, nodes, collected_edges, truncated)
    else:
        diagram = _viz_mermaid(center_id, nodes, collected_edges, truncated)

    trailer = (
        f"\nGraph capped at {max_nodes} nodes — pass max_nodes={max_nodes * 2} to expand."
        if truncated else ""
    )
    return header + diagram + trailer
