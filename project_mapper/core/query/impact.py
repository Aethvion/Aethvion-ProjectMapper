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
    find_method_callers,
    resolve_method_definitions,
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

    Supports both top-level entities (classes, functions, modules) and class
    methods (`MethodName`, `Class.MethodName`, `Class::MethodName`).

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
      subject      — the resolved entity or method stub (always full)
      affected     — list of affected entity stubs (with hop + via)
      total        — count of affected entities
      depth_used   — actual depth reached
      not_found    — True if subject could not be resolved
    """
    max_depth = max(1, min(max_depth, 4))
    rev_adj = build_reverse_impact_adj(entity_map)

    subject_entity = _resolve_entity(subject, entity_map, index)
    if subject_entity is None:
        method_name, method_defs = resolve_method_definitions(subject, entity_map, index)
        if not method_defs:
            return {
                "subject": None,
                "affected": [],
                "total": 0,
                "depth_used": 0,
                "not_found": True,
            }
        return _method_impact_query(
            method_name=method_name,
            method_defs=method_defs,
            entity_map=entity_map,
            rev_adj=rev_adj,
            max_depth=max_depth,
            via_kinds=via_kinds,
            exclude_tests=exclude_tests,
            slim=slim,
            summary_depth=summary_depth,
        )

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


def _method_impact_query(
    method_name: str,
    method_defs: list[tuple[dict, dict]],
    entity_map: dict[str, dict],
    rev_adj: dict[str, list[tuple[str, str, str]]],
    max_depth: int,
    via_kinds: list[str] | None,
    exclude_tests: bool,
    slim: bool,
    summary_depth: int,
) -> dict[str, Any]:
    """Run impact analysis starting from a class method definition."""
    primary_cls, primary_md = method_defs[0]
    cls_props = primary_cls.get("sections", {}).get("properties", {})
    cls_core = primary_cls.get("sections", {}).get("core", {})
    canonical_method = primary_md.get("name", method_name)

    subject_stub: dict[str, Any] = {
        "id": primary_cls["id"],
        "name": f"{primary_cls.get('name', '')}.{canonical_method}",
        "type": "method",
        "kind": "software.method",
        "status": primary_cls.get("status", "active"),
        "tags": cls_core.get("tags", [])[:5],
        "summary": primary_md.get("signature") or cls_core.get("summary", "")[:180],
    }
    if cls_props.get("file_path"):
        subject_stub["file_path"] = cls_props["file_path"]
    if primary_md.get("line_start") or cls_props.get("line_start"):
        subject_stub["line"] = primary_md.get("line_start") or cls_props.get("line_start")

    defining_ids = {cls_ent["id"] for cls_ent, _ in method_defs}
    hop1_callers: list[dict[str, Any]] = []
    for cls_ent, _md in method_defs:
        hop1_callers.extend(
            find_method_callers(cls_ent["id"], cls_ent.get("name", ""), canonical_method, entity_map)
        )

    affected: list[dict[str, Any]] = []
    visited: dict[str, tuple[int, str]] = {}
    queue: deque[tuple[str, int, str]] = deque()

    if hop1_callers:
        for caller_info in hop1_callers:
            cid = caller_info["id"]
            caller_ent = entity_map.get(cid)
            if not caller_ent:
                continue
            if exclude_tests and _is_test_entity(caller_ent):
                continue
            via_desc = caller_info.get("via", f"calls {canonical_method}")
            ms = 180 if 1 <= summary_depth else 0
            stub = _entity_stub(caller_ent, hop=1, via=via_desc, slim=slim, max_summary=ms)
            if caller_info.get("line_start"):
                stub["line"] = caller_info["line_start"]
            affected.append(stub)
            if cid not in visited:
                visited[cid] = (1, via_desc)
                if max_depth >= 2:
                    queue.append((cid, 1, via_desc))
    else:
        # Fall back to class-level incoming relations if no method-level call sites were recorded
        for def_id in defining_ids:
            queue.append((def_id, 0, ""))

    while queue:
        current_id, hop, via_path = queue.popleft()
        if hop >= max_depth:
            continue

        for source_id, _source_name, rel_kind in rev_adj.get(current_id, []):
            if source_id in defining_ids or source_id in visited:
                continue
            if via_kinds is not None and rel_kind not in via_kinds:
                continue
            current_name = entity_map.get(current_id, {}).get("name", current_id)
            via = f"{via_path} -> {rel_kind}" if via_path else f"{rel_kind} -> {current_name}"
            visited[source_id] = (hop + 1, via)
            e = entity_map.get(source_id)
            if e and not (exclude_tests and _is_test_entity(e)):
                ms = 180 if (hop + 1) <= summary_depth else 0
                affected.append(_entity_stub(e, hop=hop + 1, via=via, slim=slim, max_summary=ms))
            if hop + 1 < max_depth:
                queue.append((source_id, hop + 1, via))

    return {
        "subject": subject_stub,
        "affected": affected,
        "total": len(affected),
        "depth_used": max_depth,
        "not_found": False,
    }
