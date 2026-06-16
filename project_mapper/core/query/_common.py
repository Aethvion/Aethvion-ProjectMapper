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
