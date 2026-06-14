"""
project_mapper/db/entity_schema.py
Canonical schema for AethvionDB Layer-1 entity files.

Every entity shares this identical envelope. No facts are duplicated:
cross-entity relationships are always expressed as ID references, never
copied text.

Schema
------
{
  "id":      "ws_<hex>",
  "type":    "person|place|module|service|...",
  "kind":    "software.module",
  "name":    "Canonical Name",
  "status":  "active|stub|deleted|planned|deprecated|experimental",
  "version": 1,
  "created": "ISO-8601",
  "updated": "ISO-8601",
  "source":  "wikipedia|manual|expansion|import",
  "sections": {
    "core": {
      "summary":    "1-3 sentence essence",
      "aliases":    ["alt name", ...],
      "categories": ["Science", "History", ...],
      "tags":       ["keyword", ...]
    },
    "timeline": [
      { "date": "YYYY or YYYY-MM-DD", "event": "Short description", "ref_ids": ["ws_..."] }
    ],
    "relations": [
      { "kind": "parent_of|calls|depends_on|...", "target_id": "ws_...", "note": "" }
    ],
    "properties": {
      # Type-specific structured facts — free key/value, values are strings or simple lists
    },
    "stubs": [
      "Sub-topic name that needs its own entity",
      ...
    ]
  }
}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any


VALID_STATUSES = {
    # Core lifecycle
    "active", "stub", "deleted",
    # Extended lifecycle (ProjectMapper / software domains)
    "planned",       # intended but not yet implemented
    "deprecated",    # exists but being phased out
    "experimental",  # in development / unstable
}

VALID_TYPES = {
    # General / worldbuilding
    "person", "place", "event", "concept", "organization",
    "artifact", "creature", "substance", "process", "phenomenon",
    "work",       # book, film, song, game …
    "species",
    "universe",   # fictional or cosmological containers
    "other",
    # Software / project domain
    "module",       # file, package, or logical code grouping
    "service",      # deployable service, microservice, or external integration
    "component",    # UI, architectural, or functional unit
    "class",        # code class, interface, or abstract type
    "function",     # function, method, procedure, or callable
    "endpoint",     # API endpoint, route, or RPC method
    "model",        # data model, schema, database table, or type definition
    "workflow",     # process, pipeline, job, or sequence of steps
    "config",       # configuration, environment settings, or feature flags
    "dependency",   # external library, package, framework, or tool
    "decision",     # architectural decision record (ADR), tech decision
    "goal",         # roadmap item, planned feature, milestone, or objective
    "constraint",   # technical constraint, performance requirement, limitation
}

RELATION_KINDS = {
    # General / narrative
    "parent_of", "child_of",
    "member_of", "contains",
    "created_by", "created",
    "located_in", "location_of",
    "part_of", "has_part",
    "preceded_by", "followed_by",
    "related_to",
    "instance_of", "has_instance",
    "influenced_by", "influenced",
    "participated_in", "has_participant",
    # Software / structural
    "calls", "called_by",
    "imports", "imported_by",
    "depends_on", "dependency_of",
    "implements", "implemented_by",
    "extends", "extended_by",
    "uses", "used_by",
    "exposes", "exposed_by",
    "configures", "configured_by",
    "tests", "tested_by",
    "documents", "documented_by",
    "replaced_by", "replaces",
    "deprecated_by", "deprecates",
    "owns", "owned_by",
    "reads_from", "read_by",
    "writes_to", "written_by",
    "triggers", "triggered_by",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    """Generate a stable 'ws_' prefixed 16-hex ID."""
    return "ws_" + uuid.uuid4().hex[:16]


def make_empty(
    name: str,
    entity_type: str = "other",
    source: str = "manual",
    entity_id: str | None = None,
    kind: "str | list[str] | None" = None,
    status: str = "active",
) -> dict[str, Any]:
    """
    Return a minimal valid entity dict.
    Use PMEntityStore.create() to persist to the knowledge graph.
    """
    now = _now_iso()
    entity: dict[str, Any] = {
        "id":      entity_id or _new_id(),
        "type":    entity_type if entity_type in VALID_TYPES else "other",
        "name":    name,
        "status":  status if status in VALID_STATUSES else "active",
        "version": 1,
        "created": now,
        "updated": now,
        "source":  source,
        "sections": {
            "core": {
                "summary":    "",
                "aliases":    [],
                "categories": [],
                "tags":       [],
            },
            "timeline":     [],
            "relations":    [],
            "properties":   {},
            "stubs":        [],
            "vectors":      {},
            "source_files": [],   # [{ path, hash, lines, language, size, scanned_at }]
        },
    }
    if kind is not None:
        entity["kind"] = kind
    return entity


def validate(entity: dict[str, Any]) -> list[str]:
    """
    Structural validation only (schema shape, required keys, enum values).
    Returns a list of error strings; empty list means valid.
    """
    errors: list[str] = []

    for key in ("id", "type", "name", "status", "version", "created", "updated", "source", "sections"):
        if key not in entity:
            errors.append(f"Missing required key: {key!r}")

    if "status" in entity and entity["status"] not in VALID_STATUSES:
        errors.append(f"Invalid status {entity['status']!r}; must be one of {VALID_STATUSES}")

    if "type" in entity and entity["type"] not in VALID_TYPES:
        errors.append(f"Unknown entity type {entity['type']!r}")

    if "kind" in entity:
        k = entity["kind"]
        if not isinstance(k, (str, list)):
            errors.append("'kind' must be a string or list of strings")
        elif isinstance(k, list) and not all(isinstance(x, str) for x in k):
            errors.append("All items in 'kind' must be strings")

    secs = entity.get("sections", {})
    for sec in ("core", "timeline", "relations", "properties", "stubs"):
        if sec not in secs:
            errors.append(f"Missing section: {sec!r}")

    if isinstance(secs.get("timeline"), list):
        for i, ev in enumerate(secs["timeline"]):
            if not isinstance(ev, dict) or "date" not in ev or "event" not in ev:
                errors.append(f"timeline[{i}] must have 'date' and 'event' keys")

    if isinstance(secs.get("relations"), list):
        for i, rel in enumerate(secs["relations"]):
            if not isinstance(rel, dict) or "kind" not in rel or "target_id" not in rel:
                errors.append(f"relations[{i}] must have 'kind' and 'target_id' keys")

    return errors
