"""project_mapper.core.query.orphans — orphans query."""

from __future__ import annotations

import logging
from typing import Any

from ._common import (
    _DUNDER_PAT,
    _ORPHAN_ENTRY_NAMES,
    _ORPHAN_SKIP_FILES,
    _ORPHAN_VENDOR_DIRS,
    _UNITY_IMPLICIT_BASES,
    _UNITY_IMPLICIT_DECORATORS,
    IMPACT_INCOMING_KINDS,
    _is_test_entity,
)

logger = logging.getLogger(__name__)


def _is_unity_implicit_entry(props: dict[str, Any]) -> bool:
    """Return True if a C# class is invoked implicitly by the Unity Editor or runtime."""
    bases = [b.strip().split("<")[0].split(".")[-1] for b in props.get("base_classes", "").split(",") if b.strip()]
    if any(b in _UNITY_IMPLICIT_BASES for b in bases):
        return True
    decs = [d.strip().split("(")[0].split(".")[-1] for d in props.get("decorators", "").split(",") if d.strip()]
    return any(d in _UNITY_IMPLICIT_DECORATORS for d in decs)


def orphan_query(
    entity_map: dict[str, dict],
    types: list[str] | None = None,
    include_modules: bool = False,
    max_results: int = 100,
) -> dict[str, Any]:
    """
    Find entities with no inbound dependency-forming relations — potential dead code.

    An entity is an orphan if no other entity has a relation in
    IMPACT_INCOMING_KINDS pointing to it. Known false positives are filtered:
      - dunder methods  (__init__, __str__, …)
      - named entry points  (main, run, create_app, …)
      - test entities  (test_* files / tests/ directories)
      - entities living in framework entry-point files  (wsgi.py, manage.py, …)
      - Unity Editor / pipeline implicit entry classes (Editor, EditorWindow, [CustomEditor], …)
      - module-level entities  (unless include_modules=True)
    """
    referenced_ids: set[str] = set()
    for entity in entity_map.values():
        for rel in entity.get("sections", {}).get("relations", []):
            if rel.get("kind") in IMPACT_INCOMING_KINDS:
                tid = rel.get("target_id", "")
                if tid:
                    referenced_ids.add(tid)

    allowed_types = set(types) if types else None
    orphans: list[dict] = []
    skipped_count: int = 0

    for eid, entity in entity_map.items():
        if entity.get("status") in ("deleted", "stub"):
            continue
        if eid in referenced_ids:
            continue

        etype = entity.get("type", "")
        if etype == "module" and not include_modules:
            continue
        if allowed_types and etype not in allowed_types:
            continue

        name = entity.get("name", "")
        props = entity.get("sections", {}).get("properties", {})
        file_path = props.get("file_path", "")

        fp_parts = set(file_path.replace("\\", "/").split("/"))
        is_false_positive = (
            name.lower() in _ORPHAN_ENTRY_NAMES
            or bool(_DUNDER_PAT.match(name))
            or _is_test_entity(entity)
            or any(file_path.endswith(skip) for skip in _ORPHAN_SKIP_FILES)
            or bool(fp_parts & _ORPHAN_VENDOR_DIRS)
            or _is_unity_implicit_entry(props)
        )
        if is_false_positive:
            skipped_count += 1
            continue

        orphans.append(
            {
                "id": eid,
                "name": name,
                "type": etype,
                "kind": entity.get("kind"),
                "file_path": file_path,
                "line_start": props.get("line_start", ""),
                "summary": entity.get("sections", {}).get("core", {}).get("summary", "")[:120],
            }
        )

    orphans.sort(key=lambda x: (x["type"], x["name"]))

    return {
        "orphans": orphans[:max_results],
        "total": len(orphans),
        "skipped_count": skipped_count,
        "referenced_count": len(referenced_ids),
    }
