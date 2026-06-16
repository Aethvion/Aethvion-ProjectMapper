"""project_mapper.core.query.impact — impact query."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from ._common import (
    _entity_stub,
    _is_test_entity,
    _resolve_entity,
    build_reverse_impact_adj,
)

logger = logging.getLogger(__name__)


def impact_query(
    subject: str,
    entity_map: dict[str, dict],
    index: Any,
    max_depth: int = 2,
    via_kinds: list[str] | None = None,
    exclude_tests: bool = True,
    slim: bool = False,
    summary_depth: int = 1,
) -> dict[str, Any]:
    """
    Find all entities that would be affected if *subject* changes.

    via_kinds, when provided, restricts which incoming relation types are
    followed during traversal.

    exclude_tests=True (default) removes entities whose file_path lives inside
    a tests/ directory or whose filename starts with test_.

    slim=True returns only name + file_path (+ hop/via) per affected entity,
    cutting per-entity token cost from ~90 to ~16.

    summary_depth controls how far out summaries are included (ignored when
    slim=True). Default is 1: hop=1 entities get full summaries, hop=2+
    entities have their summary stripped.

    Returns a dict with:
      subject      — the resolved entity (always full, regardless of slim)
      affected     — list of affected entity stubs (with hop + via)
      total        — count of affected entities
      depth_used   — actual depth reached
      not_found    — True if subject could not be resolved
    """
    subject_entity = _resolve_entity(subject, entity_map, index)
    if subject_entity is None:
        return {
            "subject": None,
            "affected": [],
            "total": 0,
            "depth_used": 0,
            "not_found": True,
        }

    max_depth = max(1, min(max_depth, 4))
    rev_adj = build_reverse_impact_adj(entity_map)
    subject_id = subject_entity["id"]

    visited: dict[str, tuple[int, str]] = {}  # entity_id → (hop, via_path)
    queue: deque[tuple[str, int, str]] = deque()
    queue.append((subject_id, 0, ""))

    while queue:
        current_id, hop, via_path = queue.popleft()
        if hop > max_depth:
            break

        for source_id, source_name, rel_kind in rev_adj.get(current_id, []):
            if source_id == subject_id or source_id in visited:
                continue
            if via_kinds is not None and rel_kind not in via_kinds:
                continue
            current_name = entity_map.get(current_id, {}).get("name", current_id)
            via = f"{rel_kind} -> {current_name}" if via_path else rel_kind
            if via_path:
                via = f"{via_path} -> {rel_kind}"
            visited[source_id] = (hop + 1, via)
            if hop + 1 <= max_depth:
                queue.append((source_id, hop + 1, via))

    affected = []
    for eid, (hop, via) in sorted(visited.items(), key=lambda x: x[1][0]):
        e = entity_map.get(eid)
        if e:
            if exclude_tests and _is_test_entity(e):
                continue
            ms = 180 if hop <= summary_depth else 0
            affected.append(_entity_stub(e, hop=hop, via=via, slim=slim, max_summary=ms))

    return {
        "subject": _entity_stub(subject_entity),  # subject always full
        "affected": affected,
        "total": len(affected),
        "depth_used": max_depth,
        "not_found": False,
    }
