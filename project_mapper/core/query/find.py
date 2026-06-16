"""project_mapper.core.query.find — find query."""

from __future__ import annotations

import logging
import re
from typing import Any

from ._common import (
    _resolve_entity,
    build_reverse_impact_adj,
)

logger = logging.getLogger(__name__)


def find_query(
    name: str,
    entity_map: dict[str, dict],
    index: Any,
    max_results: int = 10,
) -> dict[str, Any]:
    """
    Look up a symbol by exact or partial name.

    Match priority (lowest number wins):
      0 — case-insensitive exact match on entity name
      1 — entity name ends with .<name> or _<name>  (method/suffix match)
      2 — entity name contains <name>  (substring)

    Returns up to max_results matches, each with full location context,
    callers (inbound dependency relations), and callees (outbound relations).
    """
    name_lower = name.lower()
    scored: list[tuple[int, str]] = []

    for eid, entity in entity_map.items():
        if entity.get("status") == "deleted":
            continue
        ename = entity.get("name", "").lower()
        if ename == name_lower:
            scored.append((0, eid))
        elif ename.endswith(f".{name_lower}") or ename.endswith(f"_{name_lower}"):
            scored.append((1, eid))
        elif name_lower in ename:
            # Guard: for "::" qualified queries, block partial-suffix matches.
            # "DBImpl::Write" must not match "DBImpl::Writer" (Write is a prefix
            # of Writer). Require the match is not followed by an alphanumeric char.
            if "::" in name_lower and re.search(re.escape(name_lower) + r"[a-z0-9_]", ename):
                continue
            scored.append((2, eid))

    if not scored:
        return {"query": name, "matches": [], "total": 0, "not_found": True}

    scored.sort(key=lambda x: x[0])
    seen: set[str] = set()
    ordered: list[str] = []
    for _, eid in scored:
        if eid not in seen:
            seen.add(eid)
            ordered.append(eid)
    ordered = ordered[:max_results]

    rev_adj = build_reverse_impact_adj(entity_map)
    _OUTBOUND = frozenset({"calls", "imports", "depends_on", "uses", "extends", "implements"})

    _STD_PROPS = frozenset(
        {
            "file_path",
            "line_start",
            "line_end",
            "signature",
            "architectural_pattern",
            "language",
            "size",
            "last_scanned",
            "hash",
        }
    )

    matches: list[dict] = []
    for eid in ordered:
        entity = entity_map[eid]
        props = entity.get("sections", {}).get("properties", {})
        core = entity.get("sections", {}).get("core", {})
        relations = entity.get("sections", {}).get("relations", [])

        callers: list[dict] = []
        for caller_id, _cname, rel_kind in rev_adj.get(eid, [])[:8]:
            caller = entity_map.get(caller_id)
            if caller:
                callers.append(
                    {
                        "name": caller.get("name", ""),
                        "type": caller.get("type", ""),
                        "via": rel_kind,
                        "file_path": caller.get("sections", {})
                        .get("properties", {})
                        .get("file_path", ""),
                    }
                )

        callees: list[dict] = []
        for rel in relations[:8]:
            if rel.get("kind") in _OUTBOUND:
                target = entity_map.get(rel.get("target_id", ""))
                if target:
                    callees.append(
                        {
                            "name": target.get("name", ""),
                            "type": target.get("type", ""),
                            "via": rel.get("kind", ""),
                        }
                    )

        custom = {k: v for k, v in props.items() if k not in _STD_PROPS and v}
        timeline = entity.get("sections", {}).get("timeline", [])

        matches.append(
            {
                "id": eid,
                "name": entity.get("name", ""),
                "type": entity.get("type", ""),
                "kind": entity.get("kind"),
                "status": entity.get("status", "active"),
                "file_path": props.get("file_path", ""),
                "line_start": props.get("line_start", ""),
                "line_end": props.get("line_end", ""),
                "summary": core.get("summary", "")[:200],
                "signature": props.get("signature", ""),
                "tags": core.get("tags", [])[:6],
                "callers": callers,
                "callees": callees,
                "custom_properties": custom,
                "timeline": timeline[-3:],
            }
        )

    return {
        "query": name,
        "matches": matches,
        "total": len(matches),
        "not_found": False,
    }


def find_by_method(
    name: str,
    entity_map: dict[str, dict],
    index: Any,
    max_results: int = 5,
) -> dict[str, Any]:
    """
    Fall-back for find_query when no entity name matches *name*.

    Searches the 'methods' property of all entities for a method whose name
    (case-insensitive) matches the query or its method component.

    Handles three patterns:
      "Class::method"  (C++/Rust) — resolves Class first, confirms the method
      "Class.method"   (Python/Java/JS) — same
      "method_name"    (bare)  — scans every entity's methods property

    Returns a result dict in the same shape as find_query, plus:
      "method_hint":    True
      "matched_method": the bare method name that was matched
    """
    method_name = name
    class_hint = ""
    if "::" in name:
        class_hint, method_name = name.rsplit("::", 1)
    elif "." in name and not name.startswith("."):
        class_hint, method_name = name.rsplit(".", 1)

    method_lower = method_name.strip().lower()
    if not method_lower:
        return {"query": name, "matches": [], "total": 0, "not_found": True, "method_hint": False}

    seen: set[str] = set()
    priority: list[tuple[int, str]] = []

    # Priority 0 — class hint resolves and that entity has this method
    if class_hint:
        entity = _resolve_entity(class_hint, entity_map, index)
        if entity and entity.get("status") != "deleted":
            props = entity.get("sections", {}).get("properties", {})
            method_list = [m.strip() for m in props.get("methods", "").split(",") if m.strip()]
            if any(m.lower() == method_lower for m in method_list):
                seen.add(entity["id"])
                priority.append((0, entity["id"]))

    # Priority 1 — any entity whose methods property contains the method name
    # (only run when class hint didn't produce a match)
    if not priority:
        for eid, entity in entity_map.items():
            if entity.get("status") == "deleted" or eid in seen:
                continue
            props = entity.get("sections", {}).get("properties", {})
            methods_str = props.get("methods", "")
            if not methods_str:
                continue
            if any(m.strip().lower() == method_lower for m in methods_str.split(",") if m.strip()):
                seen.add(eid)
                priority.append((1, eid))

    if not priority:
        return {"query": name, "matches": [], "total": 0, "not_found": True, "method_hint": False}

    ordered = [eid for _, eid in sorted(priority)[:max_results]]

    rev_adj = build_reverse_impact_adj(entity_map)
    _OUTBOUND = frozenset({"calls", "imports", "depends_on", "uses", "extends", "implements"})
    _STD_PROPS = frozenset(
        {
            "file_path",
            "line_start",
            "line_end",
            "signature",
            "architectural_pattern",
            "language",
            "size",
            "last_scanned",
            "hash",
        }
    )

    matches: list[dict] = []
    for eid in ordered:
        entity = entity_map[eid]
        props = entity.get("sections", {}).get("properties", {})
        core = entity.get("sections", {}).get("core", {})
        relations = entity.get("sections", {}).get("relations", [])

        callers: list[dict] = []
        for caller_id, _cname, rel_kind in rev_adj.get(eid, [])[:8]:
            caller = entity_map.get(caller_id)
            if caller:
                callers.append(
                    {
                        "name": caller.get("name", ""),
                        "type": caller.get("type", ""),
                        "via": rel_kind,
                        "file_path": caller.get("sections", {})
                        .get("properties", {})
                        .get("file_path", ""),
                    }
                )

        callees: list[dict] = []
        for rel in relations[:8]:
            if rel.get("kind") in _OUTBOUND:
                target = entity_map.get(rel.get("target_id", ""))
                if target:
                    callees.append(
                        {
                            "name": target.get("name", ""),
                            "type": target.get("type", ""),
                            "via": rel.get("kind", ""),
                        }
                    )

        custom = {k: v for k, v in props.items() if k not in _STD_PROPS and v}
        timeline = entity.get("sections", {}).get("timeline", [])

        matches.append(
            {
                "id": eid,
                "name": entity.get("name", ""),
                "type": entity.get("type", ""),
                "kind": entity.get("kind"),
                "status": entity.get("status", "active"),
                "file_path": props.get("file_path", ""),
                "line_start": props.get("line_start", ""),
                "line_end": props.get("line_end", ""),
                "summary": core.get("summary", "")[:200],
                "signature": props.get("signature", ""),
                "tags": core.get("tags", [])[:6],
                "callers": callers,
                "callees": callees,
                "custom_properties": custom,
                "timeline": timeline[-3:],
            }
        )

    return {
        "query": name,
        "matches": matches,
        "total": len(matches),
        "not_found": False,
        "method_hint": True,
        "matched_method": method_name,
    }
