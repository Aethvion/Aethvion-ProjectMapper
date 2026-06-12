"""
project_mapper/cleanup.py
DB-mutation helpers for retiring stale entities after incremental scans.

Three distinct operations
-------------------------
1. retire_entity()           — soft-delete one entity + append a timeline event.
2. retire_file_entities()    — retire the module entity AND all contained child
                               entities (classes / functions) for a deleted source
                               file, then remove the file from the FileManifest.
3. prune_removed_symbols()   — retire class/function entities that were removed
                               from a modified source file (called per-file, inline
                               during a scan pass).
4. run_deletion_cleanup()    — full pass: find every manifest entry whose file no
                               longer exists on disk and call retire_file_entities().
                               Called automatically at the end of an incremental scan.

None of these functions perform filesystem writes outside of AethvionDB.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .scanner import SUPPORTED_EXTENSIONS, _EXCLUDED_DIRS

if TYPE_CHECKING:
    from .db.entity_writer import EntityWriter
    from .db.name_index import NameIndex
    from .db.file_manifest import FileManifest

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 1. Retire a single entity
# ---------------------------------------------------------------------------

def retire_entity(
    entity_id: str,
    reason:    str,
    writer:    "EntityWriter",
) -> bool:
    """
    Soft-delete *entity_id*: mark status='deleted' and append a timeline event.

    Returns True if the entity was found and retired, False if it didn't exist
    or was already deleted.
    """
    entity = writer.get(entity_id)
    if not entity:
        return False
    if entity.get("status") == "deleted":
        return False   # already retired — idempotent

    # Mark deleted via top-level status field
    writer.update(entity_id, {"status": "deleted"})

    # Append a dated timeline event so the reason is preserved historically
    event: dict[str, Any] = {
        "date":  _now_iso(),
        "event": f"[ProjectMapper] Retired — {reason}",
    }
    try:
        writer.update(entity_id, {"sections": {"timeline": [event]}})
    except Exception as exc:
        logger.debug(f"[Cleanup] Could not append timeline event for {entity_id}: {exc}")

    logger.debug(f"[Cleanup] Retired {entity_id}: {reason}")
    return True


# ---------------------------------------------------------------------------
# 2. Retire all entities for a deleted file
# ---------------------------------------------------------------------------

@dataclass
class RetireFileResult:
    path:          str
    entity_ids:    list[str]
    retired_count: int
    errors:        list[str] = field(default_factory=list)


def retire_file_entities(
    path:          str,
    file_manifest: "FileManifest",
    writer:        "EntityWriter",
) -> RetireFileResult:
    """
    Retire all entities associated with *path* (a deleted source file).

    Steps:
    1. Look up entity IDs from the FileManifest.
    2. Call retire_entity() for each module entity.
    3. Retire child entities (classes / functions) contained by the module
       via prune_removed_symbols(module_id, [], writer) — passing an empty
       new_child_ids list retires ALL children since nothing survives from
       a deleted file.
    4. Remove each entity ID from the manifest (entries with no remaining
       entity_ids are automatically pruned by FileManifest.remove_entity()).
    """
    entity_ids = file_manifest.entity_ids_for(path)
    result = RetireFileResult(
        path=path,
        entity_ids=list(entity_ids),
        retired_count=0,
    )

    for eid in entity_ids:
        try:
            if retire_entity(eid, reason=f"source file deleted: {path}", writer=writer):
                result.retired_count += 1
            # Retire child entities (classes / functions) this module contained.
            # new_child_ids=[] means "no survivors" — all children are retired.
            pruned = prune_removed_symbols(eid, [], writer)
            result.retired_count += pruned
        except Exception as exc:
            result.errors.append(f"retire {eid}: {exc}")

        # Remove from manifest regardless of whether the entity file existed
        try:
            file_manifest.remove_entity(eid)
        except Exception as exc:
            result.errors.append(f"manifest remove {eid}: {exc}")

    try:
        file_manifest.remove_file(path)
    except Exception as exc:
        result.errors.append(f"manifest remove file {path}: {exc}")

    return result


# ---------------------------------------------------------------------------
# 3. Prune removed symbols from a changed file
# ---------------------------------------------------------------------------

def prune_removed_symbols(
    module_entity_id: str,
    new_child_ids:    list[str],
    writer:           "EntityWriter",
) -> int:
    """
    After re-scanning a modified module, retire child entities (classes /
    functions) that are no longer present in the updated source.

    Algorithm
    ---------
    1. Load the module entity; collect all its "contains" relation targets
       → these are the children from the *previous* scan.
    2. Diff against *new_child_ids* → orphaned children.
    3. For each orphan, retire it only if:
         a. source == "project_mapper"  (we created it, not the user)
         b. The entity's file_path property matches the module's own file_path
            (guards against retiring a same-named entity from a different file)
    4. Rebuild the module's "contains" relations list, excluding retired orphans.
    5. Return the count of entities actually retired.

    Parameters
    ----------
    module_entity_id : ID of the module entity that was just re-ingested.
    new_child_ids    : Entity IDs produced by the fresh ingest pass
                       (class_entity_ids + function_entity_ids).
    writer           : EntityWriter for the target database.
    """
    module = writer.get(module_entity_id)
    if not module:
        return 0

    module_file = (
        module.get("sections", {})
              .get("properties", {})
              .get("file_path", "")
    )
    all_relations: list[dict[str, Any]] = module.get("sections", {}).get("relations", [])

    old_contains  = [r for r in all_relations if r.get("kind") == "contains"]
    new_set       = set(new_child_ids)
    orphaned_rels = [r for r in old_contains if r.get("target_id") not in new_set]

    if not orphaned_rels:
        return 0

    # Start with all relations; we'll selectively re-add orphans we decide to keep
    surviving: list[dict[str, Any]] = [r for r in all_relations if r not in orphaned_rels]
    retired   = 0

    for rel in orphaned_rels:
        eid = rel.get("target_id", "")
        if not eid:
            continue

        child = writer.get(eid)
        if not child:
            continue   # already gone — just drop the relation

        # Only retire entities that project_mapper owns
        if child.get("source") != "project_mapper":
            surviving.append(rel)   # keep relation; entity is user-managed
            continue

        # Only retire if the entity came from this specific file
        child_file = (
            child.get("sections", {})
                 .get("properties", {})
                 .get("file_path", "")
        )
        if child_file != module_file:
            surviving.append(rel)   # different file, leave it alone
            continue

        if retire_entity(eid, reason=f"symbol removed from {module_file}", writer=writer):
            retired += 1
        # Don't re-add the relation — orphan is now deleted

    # Rewrite the module's relations list (replace, not append)
    if retired > 0:
        try:
            writer.update(
                module_entity_id,
                {"sections": {"relations": surviving}},
                merge_sections=False,
            )
        except Exception as exc:
            logger.warning(
                f"[Cleanup] Could not rewrite relations for {module_entity_id}: {exc}"
            )

    if retired:
        logger.debug(f"[Cleanup] Pruned {retired} removed symbols from {module_file}")
    return retired


# ---------------------------------------------------------------------------
# 4. Full deletion-cleanup pass
# ---------------------------------------------------------------------------

@dataclass
class CleanupResult:
    deleted_file_count: int = 0
    retired_count:      int = 0
    deleted_files:      list[str] = field(default_factory=list)
    errors:             list[str] = field(default_factory=list)


def run_deletion_cleanup(
    project_root:  "str | Path",
    file_manifest: "FileManifest",
    writer:        "EntityWriter",
    index:         "NameIndex",       # reserved for future use (symbol index update)
) -> CleanupResult:
    """
    Walk the manifest and retire entities for every file that no longer exists
    on disk under *project_root*.

    Called automatically at the end of each incremental scan.  Can also be
    triggered manually via the POST /api/project-mapper/cleanup endpoint.

    Does **not** prune removed symbols inside changed files — that is handled
    per-file by prune_removed_symbols() during the scan pass itself.

    Parameters
    ----------
    project_root  : The project directory that was (or is being) scanned.
    file_manifest : FileManifest for the target database.
    writer        : EntityWriter for the target database.
    index         : NameIndex (currently unused; included for future symbol cleanup).
    """
    root   = Path(project_root)
    result = CleanupResult()

    # Build the set of files currently on disk in one pass
    existing_paths: set[str] = set()
    if root.exists():
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in _EXCLUDED_DIRS
            ]
            for fn in files:
                fp  = Path(dirpath) / fn
                if fp.suffix.lower() in SUPPORTED_EXTENSIONS:
                    # Mirror scanner.py's size filter so minified bundles don't show
                    # up as perpetual "new files" after every scan
                    try:
                        if fp.stat().st_size > 250_000:
                            continue
                    except OSError:
                        pass
                    rel = str(fp.relative_to(root)).replace("\\", "/")
                    existing_paths.add(rel)

    # Check every manifest entry against the live filesystem
    for entry in file_manifest.list_all():
        path = entry.get("path", "")
        if not path:
            continue
        if path in existing_paths:
            continue   # file still exists — nothing to do

        # File is gone
        result.deleted_files.append(path)
        result.deleted_file_count += 1

        retire_result = retire_file_entities(path, file_manifest, writer)
        result.retired_count += retire_result.retired_count
        result.errors.extend(retire_result.errors)

    if result.deleted_file_count:
        logger.info(
            f"[Cleanup] Deletion cleanup: {result.deleted_file_count} missing file(s), "
            f"{result.retired_count} entit{'y' if result.retired_count == 1 else 'ies'} retired"
        )
    else:
        logger.debug("[Cleanup] Deletion cleanup: no missing files")

    return result


# ---------------------------------------------------------------------------
# 5. Stub resolution pass
# ---------------------------------------------------------------------------

@dataclass
class StubResolveResult:
    stubs_checked:  int = 0
    stubs_resolved: int = 0
    relations_rewired: int = 0
    errors: list[str] = field(default_factory=list)


def resolve_stubs(
    writer: "EntityWriter",
    index:  "NameIndex",
) -> StubResolveResult:
    """
    Post-scan pass: find stub entities whose name can now be matched to a
    real active entity and re-wire all incoming relations to point at the
    real entity.  Marks resolved stubs as "retired" afterward.

    Two resolution strategies are tried in order:

    1. **Dotted-path → file-path conversion** (for module stubs created by
       the import ingestor):
       ``core.companions.engine.history``  →  ``core/companions/engine/history.py``
       This covers the common case where an import stub was created before
       the target file was scanned.

    2. **Name index lookup** (for class/function stubs):
       If an active entity now exists in the name index under the stub's
       name, re-wire to it.  This covers forward-reference stubs whose
       target class was scanned in a later file.

    External-package stubs (``openai``, ``abc``, ``typing``, …) that cannot
    be resolved by either strategy are left unchanged — they correctly
    represent external dependencies.
    """
    result = StubResolveResult()

    # Build a fast lookup: active entity name → id
    # Also load all entities into memory for relation scanning.
    all_entities: list[dict[str, Any]] = writer.list_all(include_deleted=False)
    active_by_name: dict[str, str] = {
        e["name"]: e["id"]
        for e in all_entities
        if e.get("status") == "active"
    }

    stubs = [e for e in all_entities if e.get("status") == "stub"]
    result.stubs_checked = len(stubs)

    if not stubs:
        logger.debug("[StubResolver] No stubs to resolve")
        return result

    # --- Build stub_id → real_id resolution map ---
    to_resolve: dict[str, str] = {}  # stub_id → real_id

    for stub in stubs:
        stub_id   = stub["id"]
        stub_name = stub["name"]
        real_id:  str | None = None

        # Strategy 1: dotted module path → file path
        if "." in stub_name and "/" not in stub_name:
            candidate_fp = stub_name.replace(".", "/") + ".py"
            real_id = active_by_name.get(candidate_fp)

        # Strategy 2: name index lookup (catches late-scanned forward refs)
        if real_id is None:
            indexed_id = index.get(stub_name)
            if indexed_id and indexed_id != stub_id:
                # Confirm the indexed entity is active, not another stub
                target = writer.get(indexed_id)
                if target and target.get("status") == "active":
                    real_id = indexed_id

        # Strategy 2b: dotted-name last-segment lookup.
        # Handles the common pattern where a base class is referenced with its
        # module prefix (e.g. "class Foo(models.Model):" stores the base as
        # "models.Model", but the real entity is indexed under "Model").
        # Only applied to names with exactly one dot whose last segment starts
        # with an uppercase letter (UpperCamelCase class name), to avoid false
        # matches on deeply-nested module paths like "xml.etree.ElementTree".
        if real_id is None and stub_name.count(".") == 1:
            last_seg = stub_name.rsplit(".", 1)[-1]
            if last_seg and last_seg[0].isupper():
                indexed_id = index.get(last_seg)
                if indexed_id and indexed_id != stub_id:
                    target = writer.get(indexed_id)
                    if target and target.get("status") == "active":
                        real_id = indexed_id

        if real_id:
            to_resolve[stub_id] = real_id

    if not to_resolve:
        logger.debug(f"[StubResolver] {len(stubs)} stubs checked, none resolvable")
        return result

    # --- Re-wire incoming relations across all entities ---
    for entity in all_entities:
        eid  = entity["id"]
        rels = entity.get("sections", {}).get("relations", [])
        if not rels:
            continue

        new_rels: list[dict[str, Any]] = []
        changed = False
        seen_pairs: set[tuple[str, str]] = set()  # (kind, target_id) dedup

        # First pass: keep existing non-stub relations, building seen set
        for rel in rels:
            tid  = rel.get("target_id", "")
            kind = rel.get("kind", "")
            if tid not in to_resolve:
                pair = (kind, tid)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    new_rels.append(rel)

        # Second pass: add re-wired relations (skip if already present)
        for rel in rels:
            tid  = rel.get("target_id", "")
            kind = rel.get("kind", "")
            if tid in to_resolve:
                new_tid = to_resolve[tid]
                pair    = (kind, new_tid)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    new_rel = {**rel, "target_id": new_tid}
                    new_rels.append(new_rel)
                    result.relations_rewired += 1
                    changed = True

        if changed:
            try:
                writer.update(eid, {"sections": {"relations": new_rels}}, merge_sections=False)
            except Exception as exc:
                result.errors.append(f"re-wire {eid}: {exc}")

    # --- Delete resolved stubs (they are superseded by their real entity) ---
    for stub_id in to_resolve:
        try:
            writer.update(stub_id, {"status": "deleted"})
        except Exception as exc:
            result.errors.append(f"delete stub {stub_id}: {exc}")

    result.stubs_resolved = len(to_resolve)
    logger.info(
        f"[StubResolver] Resolved {result.stubs_resolved}/{result.stubs_checked} stubs, "
        f"re-wired {result.relations_rewired} relations"
    )
    return result
