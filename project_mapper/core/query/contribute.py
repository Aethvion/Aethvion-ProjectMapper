"""project_mapper.core.query.contribute — contribute query."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def apply_contribution(
    entity:      dict,
    properties:  dict[str, str],
    relations:   list[dict],
    rationale:   str,
    source:      str,
    writer:      Any,
    index:       Any,
) -> dict[str, Any]:
    """
    Apply a structured agent contribution to an existing entity.

    - Merges new property key-values.
    - Adds new relations (resolves target_name → ID, creating stubs if needed).
    - Appends a timeline event with the rationale.

    Returns a summary of what changed.
    """
    entity_id  = entity["id"]
    mutations:  dict[str, Any] = {}
    added_rels: list[str] = []
    now_iso    = datetime.now(timezone.utc).isoformat(timespec="seconds")[:10]

    if properties:
        mutations.setdefault("sections", {})["properties"] = properties

    if relations:
        existing_rels = entity.get("sections", {}).get("relations", [])
        existing_pairs = {(r["kind"], r["target_id"]) for r in existing_rels}
        new_rels: list[dict] = []
        for rel_spec in relations:
            kind        = rel_spec.get("kind", "related_to")
            target_name = rel_spec.get("target_name", "")
            note        = rel_spec.get("note", "")
            if not target_name:
                continue
            target_id = index.get(target_name)
            if not target_id:
                stub, _ = writer.create(
                    name=target_name, entity_type="other",
                    source="stub", status="stub",
                )
                target_id = stub["id"]
            if (kind, target_id) not in existing_pairs:
                entry: dict[str, Any] = {"kind": kind, "target_id": target_id}
                if note:
                    entry["note"] = note
                new_rels.append(entry)
                added_rels.append(f"{kind} -> {target_name}")
        if new_rels:
            mutations.setdefault("sections", {})["relations"] = new_rels

    if rationale:
        timeline_event = {
            "date":  now_iso,
            "event": f"[{source}] {rationale[:300]}",
        }
        mutations.setdefault("sections", {})["timeline"] = [timeline_event]

    changes_made = bool(mutations)
    if changes_made:
        writer.update(entity_id, mutations)

    return {
        "entity_id":      entity_id,
        "entity_name":    entity.get("name"),
        "properties_set": list(properties.keys()),
        "relations_added": added_rels,
        "rationale_stored": bool(rationale),
        "changes_made":   changes_made,
    }
