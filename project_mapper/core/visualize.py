"""
project_mapper.core.visualize
Subgraph diagram builder (Mermaid / DOT). Transport-agnostic: given an entity
map and a centre entity, build its relation neighbourhood and render it.

Used by both the pm_visualize MCP tool and the HTTP /query/visualize endpoint —
neither contains diagram logic itself.
"""
from __future__ import annotations

from collections import deque
from typing import Any

_VIZ_DEFAULT_KINDS: frozenset[str] = frozenset({
    "calls", "imports", "uses", "extends", "implements", "depends_on",
})


def _viz_node_id(entity_id: str) -> str:
    """Safe Mermaid/DOT node identifier derived from entity ID."""
    return "n" + entity_id.replace("ws_", "").replace("-", "_")


def _viz_node_label(entity: dict) -> str:
    name  = entity.get("name", "?")
    etype = entity.get("type", "")
    return f"{name}\\n[{etype}]" if etype else name


def _viz_mermaid(center_id: str, nodes: dict, edges: list, truncated: bool) -> str:
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


def _viz_dot(center_id: str, nodes: dict, edges: list, truncated: bool) -> str:
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


def build_diagram(
    entity_map: dict[str, dict],
    index: Any,
    entity: str,
    depth: int = 2,
    direction: str = "both",
    relations: list[str] | None = None,
    fmt: str = "mermaid",
    max_nodes: int = 40,
) -> dict[str, Any]:
    """Build a subgraph diagram centred on *entity*.

    Returns a status dict, one of:
      {"status": "empty"}
      {"status": "not_found", "entity": <name>}
      {"status": "ambiguous", "candidates": [<name>, ...]}
      {"status": "no_relations", "center": <name>, "kinds": [...]}
      {"status": "ok", "center", "center_type", "nodes", "edges", "depth",
       "format", "diagram", "truncated", "max_nodes"}
    """
    depth     = max(1, min(4, int(depth or 2)))
    direction = (direction or "both").lower()
    rel_kinds = frozenset(relations or []) or _VIZ_DEFAULT_KINDS
    fmt       = (fmt or "mermaid").lower()
    max_nodes = max(5, min(150, int(max_nodes or 40)))

    if not entity_map:
        return {"status": "empty"}

    # Name resolution — exact via index, then substring fallback
    center: dict | None = None
    eid = index.get(entity)
    if eid and eid in entity_map:
        center = entity_map[eid]
    if center is None:
        lower_q = entity.lower()
        matches = [e for e in entity_map.values() if lower_q in e.get("name", "").lower()]
        if len(matches) == 1:
            center = matches[0]
        elif matches:
            return {"status": "ambiguous", "candidates": [e["name"] for e in matches]}
    if center is None:
        return {"status": "not_found", "entity": entity}

    center_id = center["id"]

    # Forward + reverse adjacency filtered by rel_kinds
    fwd: dict[str, list[tuple[str, str]]] = {}
    rev: dict[str, list[tuple[str, str]]] = {}
    for eid2, e in entity_map.items():
        for rel in e.get("sections", {}).get("relations", []):
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
        return {"status": "no_relations", "center": center["name"], "kinds": sorted(rel_kinds)}

    edge_count = len({(s, t, k) for s, t, k in collected_edges})
    diagram = (
        _viz_dot(center_id, nodes, collected_edges, truncated)
        if fmt == "dot"
        else _viz_mermaid(center_id, nodes, collected_edges, truncated)
    )
    return {
        "status":      "ok",
        "center":      center["name"],
        "center_type": center.get("type", "entity"),
        "nodes":       len(nodes),
        "edges":       edge_count,
        "depth":       depth,
        "format":      fmt,
        "diagram":     diagram,
        "truncated":   truncated,
        "max_nodes":   max_nodes,
    }
