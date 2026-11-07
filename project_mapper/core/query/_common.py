"""
project_mapper.core.query._common
Shared query infrastructure: entity-map construction, entity resolution/stub
formatting, the reverse-impact adjacency builder, and cross-query constants.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


IMPACT_INCOMING_KINDS: frozenset[str] = frozenset(
    {
        "calls",
        "imports",
        "depends_on",
        "uses",
        "reads_from",
        "writes_to",
        "triggered_by",
        "implements",
        "extends",
        "configured_by",
        "tests",
    }
)


_SEMANTIC_EDGE_KINDS: frozenset[str] = frozenset(
    {
        "calls",
        "extends",
        "implements",
        "uses",
        "reads_from",
        "writes_to",
        "triggered_by",
        "configured_by",
        "tests",
    }
)


_EXCEPTION_NAME_PAT: re.Pattern = re.compile(
    r"(Error|Exception|Warning|NotFound|NotSupported|Forbidden|Denied|Invalid)$",
    re.IGNORECASE,
)


_ORPHAN_ENTRY_NAMES: frozenset[str] = frozenset(
    {
        "main",
        "run",
        "start",
        "setup",
        "teardown",
        "configure",
        "create_app",
        "application",
        "app",
        "wsgi",
        "asgi",
        "celery",
        "init_app",
    }
)


_ORPHAN_SKIP_FILES: tuple[str, ...] = (
    "setup.py",
    "conftest.py",
    "wsgi.py",
    "asgi.py",
    "__init__.py",
    "__main__.py",
    "manage.py",
    "cli.py",
)


_ORPHAN_VENDOR_DIRS: frozenset[str] = frozenset(
    {
        "vendor",
        "node_modules",
        "bower_components",
    }
)


_UNITY_IMPLICIT_BASES: frozenset[str] = frozenset(
    {
        "Editor",
        "EditorWindow",
        "PropertyDrawer",
        "DecoratorDrawer",
        "ScriptableWizard",
        "AssetPostprocessor",
        "ScriptedImporter",
        "ScriptableRendererFeature",
        "ScriptableRenderPass",
        "VolumeComponent",
    }
)


_UNITY_IMPLICIT_DECORATORS: frozenset[str] = frozenset(
    {
        "CustomEditor",
        "CustomPropertyDrawer",
        "InitializeOnLoad",
        "InitializeOnLoadMethod",
        "RuntimeInitializeOnLoadMethod",
        "MenuItem",
        "SettingsProvider",
    }
)


_DUNDER_PAT: re.Pattern = re.compile(r"^__[a-z_]+__$")


def build_entity_map(writer: Any) -> dict[str, dict]:
    """
    Load all non-deleted entities into a dict keyed by entity_id.
    Expensive the first time; cache at the call site if making multiple queries.
    """
    return {e["id"]: e for e in writer.list_all(include_deleted=False)}


def _resolve_entity(
    name_or_id: str,
    entity_map: dict[str, dict],
    index: Any,
) -> dict | None:
    """Resolve a name or ID to an entity dict."""
    # Try direct ID lookup first
    if name_or_id in entity_map:
        return entity_map[name_or_id]
    # Try NameIndex
    eid = index.get(name_or_id)
    if eid and eid in entity_map:
        return entity_map[eid]
    return None


def _entity_stub(
    entity: dict,
    hop: int = 0,
    via: str = "",
    slim: bool = False,
    max_summary: int = 180,
) -> dict:
    """
    Return an agent-friendly representation of an entity.

    slim=False (default) — full stub: id, name, type, kind, status, summary,
                           tags, file_path, architectural_pattern, hop, via.
    slim=True            — minimal stub: name, file_path only (+ hop/via when
                           present).  ~16 tokens per entity vs ~90 for full.
    max_summary          — maximum characters of the summary field to include
                           (default 180, full).  Pass 0 to strip the summary
                           entirely.  Ignored when slim=True.
    """
    props = entity.get("sections", {}).get("properties", {})

    if slim:
        stub: dict[str, Any] = {"name": entity.get("name", "")}
        if props.get("file_path"):
            stub["file_path"] = props["file_path"]
        if props.get("line_start"):
            stub["line"] = props["line_start"]
        if hop > 0:
            stub["hop"] = hop
        if via:
            stub["via"] = via
        return stub

    core = entity.get("sections", {}).get("core", {})
    summary = core.get("summary", "")
    stub = {
        "id": entity["id"],
        "name": entity.get("name", ""),
        "type": entity.get("type", ""),
        "kind": entity.get("kind"),
        "status": entity.get("status", "active"),
        "tags": core.get("tags", [])[:5],
    }
    if max_summary > 0 and summary:
        stub["summary"] = summary[:max_summary]
    if props.get("file_path"):
        stub["file_path"] = props["file_path"]
    if props.get("line_start"):
        stub["line"] = props["line_start"]
    if props.get("architectural_pattern"):
        stub["architectural_pattern"] = props["architectural_pattern"]
    if hop > 0:
        stub["hop"] = hop
    if via:
        stub["via"] = via
    return stub


def _is_test_entity(entity: dict) -> bool:
    """Return True if the entity lives in a test file or test directory."""
    file_path = entity.get("sections", {}).get("properties", {}).get("file_path", "")
    if not file_path:
        return False
    return "tests/" in file_path or "/test_" in file_path or file_path.startswith("test_")


def build_reverse_impact_adj(
    entity_map: dict[str, dict],
) -> dict[str, list[tuple[str, str, str]]]:
    """
    Build a reverse adjacency map for impact traversal.

    Returns  { target_id → [(source_id, source_name, relation_kind)] }
    for all entities whose relation kind is in IMPACT_INCOMING_KINDS.
    """
    rev: dict[str, list[tuple[str, str, str]]] = {}
    for eid, entity in entity_map.items():
        ename = entity.get("name", eid)
        for rel in entity.get("sections", {}).get("relations", []):
            kind = rel.get("kind", "")
            target_id = rel.get("target_id", "")
            if kind in IMPACT_INCOMING_KINDS and target_id:
                rev.setdefault(target_id, []).append((eid, ename, kind))
    return rev


def find_method_callers(
    class_id: str,
    class_name: str,
    method_name: str,
    entity_map: dict[str, dict],
) -> list[dict[str, Any]]:
    """
    Find all entities in *entity_map* that invoke *method_name* on *class_name* (*class_id*).

    Checks both:
      1. Outbound relations to *class_id* with `called_methods` or UnityEvent `note` metadata.
      2. Entity `properties["called_methods"]` entries `[[receiver_hint, called_method, via_method], ...]`.

    Returns a list of caller dicts with `id`, `name`, `type`, `via`, `file_path`, and `line_start`
    (resolved to the calling method's `line_start` when available).
    """
    method_lower = method_name.strip().lower()
    class_lower = class_name.strip().lower()
    callers: list[dict[str, Any]] = []
    seen_callers: set[tuple[str, str]] = set()

    for eid, caller in entity_map.items():
        if eid == class_id or caller.get("status") in ("deleted", "stub"):
            continue
        props = caller.get("sections", {}).get("properties", {})
        relations = caller.get("sections", {}).get("relations", [])
        fp = props.get("file_path", "")
        default_line = props.get("line_start", "")

        # Map of caller method name (lower) -> line_start
        method_lines: dict[str, int] = {}
        for md in props.get("method_details", []):
            if isinstance(md, dict) and md.get("name") and md.get("line_start"):
                method_lines[str(md["name"]).lower()] = int(md["line_start"])

        matched_vias: list[tuple[str, Any]] = []

        # 1. Check called_methods property for exact (receiver, method, via_fn) triples
        for item in props.get("called_methods", []):
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            recv_hint = str(item[0] or "")
            mname = str(item[1] or "")
            via_fn = str(item[2] or "") if len(item) > 2 else ""
            if mname.lower() != method_lower:
                continue
            has_rel_to_class = any(r.get("target_id") == class_id for r in relations)
            if not recv_hint or recv_hint.lower() == class_lower or has_rel_to_class:
                line = method_lines.get(via_fn.lower(), default_line) if via_fn else default_line
                via_desc = f"calls {method_name} (in {via_fn})" if via_fn else f"calls {method_name}"
                matched_vias.append((via_desc, line))

        # 2. Check relations targeting class_id (covers UnityEvents and relation-level called_methods)
        if not matched_vias:
            for rel in relations:
                if rel.get("target_id") != class_id:
                    continue
                rel_methods = [str(m).lower() for m in rel.get("called_methods", [])]
                note = str(rel.get("note", ""))
                if method_lower in rel_methods:
                    matched_vias.append((f"calls {method_name}", default_line))
                elif method_lower in note.lower():
                    matched_vias.append((f"{rel.get('kind', 'uses')} ({note})", default_line))

        for via_desc, line in matched_vias:
            dedup_key = (eid, via_desc)
            if dedup_key in seen_callers:
                continue
            seen_callers.add(dedup_key)
            callers.append(
                {
                    "id": eid,
                    "name": caller.get("name", ""),
                    "type": caller.get("type", ""),
                    "via": via_desc,
                    "file_path": fp,
                    "line_start": line,
                }
            )

    return callers


def resolve_method_definitions(
    query_name: str,
    entity_map: dict[str, dict],
    index: Any,
) -> tuple[str, list[tuple[dict, dict]]]:
    """
    Resolve a method query (`Class.method`, `Class::method`, or bare `method`) to
    matching `(class_entity, method_detail_dict)` pairs.
    """
    method_name = query_name.strip()
    class_hint = ""
    if "::" in method_name:
        class_hint, method_name = method_name.rsplit("::", 1)
    elif "." in method_name and not method_name.startswith("."):
        class_hint, method_name = method_name.rsplit(".", 1)

    method_name = method_name.strip()
    method_lower = method_name.lower()
    if not method_lower:
        return "", []

    matches: list[tuple[dict, dict]] = []
    seen_ids: set[str] = set()

    def _extract_method_detail(entity: dict) -> dict | None:
        props = entity.get("sections", {}).get("properties", {})
        methods_str = props.get("methods", "")
        if not methods_str:
            return None
        method_list = [m.strip() for m in methods_str.split(",") if m.strip()]
        canonical_name = next((m for m in method_list if m.lower() == method_lower), None)
        if canonical_name is None:
            return None
        for md in props.get("method_details", []):
            if isinstance(md, dict) and str(md.get("name", "")).lower() == method_lower:
                return md
        return {
            "name": canonical_name,
            "signature": f"{canonical_name}()",
            "line_start": props.get("line_start", ""),
            "line_end": props.get("line_end", ""),
        }

    if class_hint:
        entity = _resolve_entity(class_hint.strip(), entity_map, index)
        if entity and entity.get("status") not in ("deleted", "stub"):
            md = _extract_method_detail(entity)
            if md is not None:
                seen_ids.add(entity["id"])
                matches.append((entity, md))

    if not matches:
        for eid, entity in entity_map.items():
            if eid in seen_ids or entity.get("status") in ("deleted", "stub"):
                continue
            if class_hint and entity.get("name", "").lower() != class_hint.strip().lower():
                continue
            md = _extract_method_detail(entity)
            if md is not None:
                seen_ids.add(eid)
                matches.append((entity, md))

    return method_name, matches
