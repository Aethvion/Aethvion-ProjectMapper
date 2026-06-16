"""project_mapper.core.query.path — path query."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from ._common import (
    _EXCEPTION_NAME_PAT,
    _SEMANTIC_EDGE_KINDS,
    _entity_stub,
    _resolve_entity,
)

logger = logging.getLogger(__name__)

_HUB_CALLS_THRESHOLD = 20


def _build_adjacency(
    entity_map: dict[str, dict],
    allowed_kinds: frozenset[str] | None,
) -> tuple[dict[str, list[tuple[str, str, str]]], dict[str, list[tuple[str, str, str]]]]:
    """
    Build forward and reverse adjacency dicts from the entity graph.

    Each adjacency entry is a 3-tuple: (neighbor_id, relation_kind, note).
    The *note* field carries the optional annotation stored on the relation
    (e.g. "via method_name" for calls edges).
    """
    fwd: dict[str, list[tuple[str, str, str]]] = {}
    rev: dict[str, list[tuple[str, str, str]]] = {}
    for eid, entity in entity_map.items():
        for rel in entity.get("sections", {}).get("relations", []):
            tid = rel.get("target_id", "")
            kind = rel.get("kind", "related_to")
            note = rel.get("note", "")
            if tid and tid in entity_map:
                if allowed_kinds is None or kind in allowed_kinds:
                    fwd.setdefault(eid, []).append((tid, kind, note))
                    rev.setdefault(tid, []).append((eid, kind, note))
    return fwd, rev


def _compute_skip_ids(
    entity_map: dict[str, dict],
    from_id: str,
    to_id: str,
) -> frozenset[str]:
    """
    Return entity IDs that should be skipped as BFS intermediaries.

    Skips: exception-named classes, test-file entities, high-fanin hub nodes.
    Source and destination are NEVER skipped.
    """
    protected = {from_id, to_id}
    skip: set[str] = set()

    calls_in_degree: dict[str, int] = {}
    for entity in entity_map.values():
        for rel in entity.get("sections", {}).get("relations", []):
            if rel.get("kind") == "calls":
                tid = rel.get("target_id", "")
                if tid and tid not in protected:
                    calls_in_degree[tid] = calls_in_degree.get(tid, 0) + 1

    for eid, entity in entity_map.items():
        if eid in protected:
            continue
        name = entity.get("name", "")
        file_path = entity.get("sections", {}).get("properties", {}).get("file_path", "")
        if _EXCEPTION_NAME_PAT.search(name):
            skip.add(eid)
        elif file_path and (
            "tests/" in file_path or "/test_" in file_path or file_path.startswith("test_")
        ):
            skip.add(eid)
        elif calls_in_degree.get(eid, 0) >= _HUB_CALLS_THRESHOLD:
            skip.add(eid)

    return frozenset(skip)


def _bfs_path(
    from_id: str,
    to_id: str,
    to_entity: dict,
    entity_map: dict[str, dict],
    fwd: dict[str, list[tuple[str, str, str]]],
    rev: dict[str, list[tuple[str, str, str]]],
    max_hops: int,
    skip_ids: frozenset[str] = frozenset(),
    slim: bool = False,
) -> list[dict] | None:
    """
    BFS from *from_id* to *to_id* using the given adjacency dicts.
    Returns the path as a list of entity stubs, or None if no path is found.
    """
    visited: set[str] = {from_id}
    # path step: (neighbor_id, rel_kind, edge_note, is_reverse)
    queue: deque[tuple[str, list[tuple[str, str, str, bool]]]] = deque()
    queue.append((from_id, []))

    while queue:
        current_id, path_so_far = queue.popleft()
        if len(path_so_far) >= max_hops:
            continue

        fwd_nb = [(nid, kind, note, False) for nid, kind, note in fwd.get(current_id, [])]
        rev_nb = [(nid, kind, note, True) for nid, kind, note in rev.get(current_id, [])]
        for neighbor_id, rel_kind, edge_note, is_reverse in fwd_nb + rev_nb:
            if neighbor_id in visited:
                continue
            if neighbor_id != to_id and neighbor_id in skip_ids:
                continue
            visited.add(neighbor_id)
            new_path = path_so_far + [(neighbor_id, rel_kind, edge_note, is_reverse)]

            if neighbor_id == to_id:
                path_entities: list[dict] = []
                prev_id = from_id
                for step_id, edge_label, note, edge_rev in new_path:
                    node = _entity_stub(entity_map.get(prev_id, {}), slim=slim)
                    node["relation"] = edge_label
                    node["relation_reverse"] = edge_rev
                    if note:
                        node["note"] = note
                    path_entities.append(node)
                    prev_id = step_id
                path_entities.append(_entity_stub(to_entity, slim=slim))
                return path_entities

            queue.append((neighbor_id, new_path))

    return None


def shortest_path(
    from_entity: str,
    to_entity: str,
    entity_map: dict[str, dict],
    index: Any,
    max_hops: int = 6,
    slim: bool = False,
) -> dict[str, Any]:
    """
    Find the shortest meaningful path between two entities.

    Two-phase search:
      Phase 1 — semantic edges only (calls, extends, implements, …).
      Phase 2 — all edges including structural ones (contains, imports, …).

    path_type field: "semantic" | "structural" | "none"
    """
    from_e = _resolve_entity(from_entity, entity_map, index)
    to_e = _resolve_entity(to_entity, entity_map, index)

    if not from_e:
        return {"found": False, "error": f"Entity not found: {from_entity!r}"}
    if not to_e:
        return {"found": False, "error": f"Entity not found: {to_entity!r}"}

    from_id = from_e["id"]
    to_id = to_e["id"]

    if from_id == to_id:
        return {
            "found": True,
            "path": [_entity_stub(from_e, slim=slim)],
            "length": 0,
            "path_type": "semantic",
        }

    skip_ids = _compute_skip_ids(entity_map, from_id, to_id)

    # ---- Phase 1: semantic edges only -----------------------------------
    fwd_sem, rev_sem = _build_adjacency(entity_map, _SEMANTIC_EDGE_KINDS)
    path = _bfs_path(
        from_id, to_id, to_e, entity_map, fwd_sem, rev_sem, max_hops, skip_ids, slim=slim
    )
    if path is None and skip_ids:
        path = _bfs_path(from_id, to_id, to_e, entity_map, fwd_sem, rev_sem, max_hops, slim=slim)
    if path is not None:
        return {
            "found": True,
            "path": path,
            "length": len(path) - 1,
            "path_type": "semantic",
        }

    # ---- Phase 2: full graph (semantic + structural) --------------------
    fwd_all, rev_all = _build_adjacency(entity_map, None)
    path = _bfs_path(
        from_id, to_id, to_e, entity_map, fwd_all, rev_all, max_hops, skip_ids, slim=slim
    )
    if path is None and skip_ids:
        path = _bfs_path(from_id, to_id, to_e, entity_map, fwd_all, rev_all, max_hops, slim=slim)
    if path is not None:
        return {
            "found": True,
            "path": path,
            "length": len(path) - 1,
            "path_type": "structural",
        }

    return {
        "found": False,
        "path": [],
        "length": 0,
        "path_type": "none",
        "error": f"No path found between {from_entity!r} and {to_entity!r} within {max_hops} hops",
    }
