"""
project_mapper/db/pm_store.py
In-memory entity store for Project Mapper scan sessions.

Problem
-------
EntityWriter writes one ws_*.json file per entity during a scan.
For a codebase with ~12,000 entities that is 12,000 atomic file operations,
each of which Windows Defender scans before the rename completes.
NameIndex._save() is called on every get_or_create(), adding another 12,000
writes to name_index.json. Combined, these dominate scan time on Windows
(measured: 394 s for a 2,417-file Python codebase).

Solution
--------
PMEntityStore keeps all entities in a dict[id → entity] for the duration
of the scan.  No ws_*.json files are written.  At scan completion, flush()
writes a single AethvionDB snapshot file and the name index in two file
operations (vs. 24,000+).

PMNameIndex is a NameIndex subclass that overrides _save() to a no-op during
the scan, deferring the single final write to flush_to_disk().

AethvionDB is untouched — this is a PM-specific layer only.

Compatibility
-------------
All public methods match the EntityWriter interface so that scanner.py,
ingestor.py, cleanup.py, and routes.py work without modification beyond the
injection point at start_project_scan().

The snapshot written by flush() is identical in format to the one written by
EntityWriter — queries use it transparently via snapshot.load().

An AethvionDB.PMSTORE marker file is written alongside the snapshot so that
snapshot.is_fresh() can return True even with no ws_*.json entity files on
disk (see snapshot.py).

Incremental scans
-----------------
Use PMEntityStore.from_snapshot() to pre-populate the store from an existing
snapshot.  Entities for unchanged files are already in the store; the scanner
re-creates / updates only the entities for changed files.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from .entity_schema import make_empty, _new_id, _now_iso, VALID_STATUSES
from .name_index import NameIndex
from .utils import get_logger, atomic_json_write
from . import snapshot as _snapshot

logger = get_logger(__name__)

# Written by flush() so that snapshot.is_fresh() knows there are no entity files.
# Canonical definition lives in snapshot.py — re-exported here for convenience.
PM_MARKER_FILE = _snapshot.PM_MARKER_FILE


# ---------------------------------------------------------------------------
# PMNameIndex
# ---------------------------------------------------------------------------

class PMNameIndex(NameIndex):
    """NameIndex variant that batches all disk writes to a single flush.

    During a PM scan, get_or_create() / register() / register_aliases() are
    called once per entity (12,000+ times for large codebases).  The base
    NameIndex calls atomic_json_write() (temp-file + rename + Defender scan)
    on every such call.  PMNameIndex overrides _save() to a no-op and defers
    the single final write to flush_to_disk().

    Thread-safety: inherits threading.Lock from NameIndex.  All in-memory
    mutations still happen under the lock — only the disk write is deferred.
    """

    def _save(self) -> None:
        """No-op during a PM scan.  Call flush_to_disk() to persist."""

    def flush_to_disk(self) -> None:
        """Write the complete name index to disk exactly once."""
        self._ensure_loaded()
        with self._lock:
            atomic_json_write(self._path, self._data, sort_keys=True)


# ---------------------------------------------------------------------------
# PMEntityStore
# ---------------------------------------------------------------------------

class PMEntityStore:
    """
    Drop-in replacement for EntityWriter during PM scan sessions.

    All entities live in self._store (dict[id → entity]) for the duration of
    the scan.  No ws_*.json files are ever written.  A single snapshot is
    built at flush() time.

    Interface: identical to EntityWriter for the methods called by scanner,
    ingestor, and cleanup (create, get, update, delete, list_all, list_stubs,
    get_stub_names_for, count, exists, get_by_name, search_by_type,
    search_by_kind, search_by_tag).

    Incremental scans: pre-populate self._store from the existing snapshot via
    from_snapshot() so that entities for unchanged files survive intact.
    """

    def __init__(
        self,
        db_root: Path,
        index: PMNameIndex,
    ) -> None:
        self._store:   dict[str, dict[str, Any]] = {}
        self._db_root: Path     = db_root
        self._index:   PMNameIndex = index
        self._lock:    threading.Lock = threading.Lock()  # guards create()

    @classmethod
    def from_snapshot(cls, db_root: Path, index: PMNameIndex) -> "PMEntityStore":
        """Create a PMEntityStore pre-populated from an existing snapshot.

        Used for incremental scans so that entities belonging to unchanged
        files are preserved without re-creating them.
        """
        store = cls(db_root, index)
        existing = _snapshot.load(db_root)
        if existing:
            for entity in existing:
                store._store[entity["id"]] = entity
        return store

    # ── EntityWriter-compatible API ─────────────────────────────────────────

    def exists(self, entity_id: str) -> bool:
        return entity_id in self._store

    def get(self, entity_id: str) -> Optional[dict[str, Any]]:
        return self._store.get(entity_id)

    def get_by_name(self, name: str) -> Optional[dict[str, Any]]:
        eid = self._index.get(name)
        if not eid:
            return None
        return self._store.get(eid)

    def create(
        self,
        name: str,
        entity_type:       str = "other",
        source:            str = "manual",
        sections_override: Optional[dict[str, Any]]  = None,
        extra_aliases:     Optional[list[str]]        = None,
        kind:              "str | list[str] | None"   = None,
        status:            str = "active",
    ) -> tuple[dict[str, Any], bool]:
        """Create a new entity in memory, or return the existing one.

        Returns (entity_dict, was_created).  Thread-safe: the index lookup
        and store insertion are atomic under self._lock.
        """
        candidate_id  = _new_id()
        resolved_status = status if status in VALID_STATUSES else "active"

        with self._lock:
            entity_id, was_new = self._index.get_or_create(name, candidate_id)

            if not was_new:
                existing = self._store.get(entity_id)
                if existing:
                    if existing.get("status") in ("deleted", "retired"):
                        # Reactivate soft-deleted entity, mirror EntityWriter behaviour.
                        existing["status"] = resolved_status
                        if sections_override:
                            self._apply_sections(existing, sections_override)
                        return existing, True
                    return existing, False
                # Index entry exists but store entry missing — recreate below.
                logger.warning(
                    f"[PMEntityStore] Index entry for '{name}' → {entity_id} "
                    "exists but not in store; recreating."
                )

            entity = make_empty(
                name, entity_type, source, entity_id,
                kind=kind, status=resolved_status,
            )

            if sections_override:
                self._apply_sections(entity, sections_override)

            aliases = entity["sections"]["core"].get("aliases", [])
            if extra_aliases:
                aliases.extend(extra_aliases)
            if aliases:
                self._index.register_aliases(entity_id, aliases)

            self._store[entity_id] = entity
            return entity, True

    def update(
        self,
        entity_id:     str,
        mutations:     dict[str, Any],
        merge_sections: bool = True,
    ) -> dict[str, Any]:
        """Update an entity in memory.  Mirrors EntityWriter.update() semantics."""
        with self._lock:
            entity = self._store.get(entity_id)
            if entity is None:
                raise FileNotFoundError(
                    f"[PMEntityStore] Entity {entity_id!r} not found in store"
                )

            protected = {"id", "created", "version", "sections"}
            old_name  = entity.get("name")
            for k, v in mutations.items():
                if k not in protected:
                    entity[k] = v

            new_name = entity.get("name")
            if new_name and new_name != old_name:
                self._index.register(new_name, entity_id)
                if old_name:
                    self._index.unregister(old_name)

            incoming_sections = mutations.get("sections", {})
            if incoming_sections:
                if merge_sections:
                    for sec, val in incoming_sections.items():
                        existing = entity["sections"].get(sec)
                        if isinstance(existing, dict) and isinstance(val, dict):
                            existing.update(val)
                        elif isinstance(existing, list) and isinstance(val, list):
                            seen = {json.dumps(x, sort_keys=True) for x in existing}
                            for item in val:
                                key = json.dumps(item, sort_keys=True)
                                if key not in seen:
                                    existing.append(item)
                                    seen.add(key)
                        else:
                            entity["sections"][sec] = val
                else:
                    entity["sections"].update(incoming_sections)

            entity["version"] = entity.get("version", 0) + 1
            entity["updated"] = _now_iso()

            aliases = entity["sections"]["core"].get("aliases", [])
            if aliases:
                self._index.register_aliases(entity_id, aliases)

            return entity

    def delete(self, entity_id: str, *, soft: bool = True) -> bool:
        """Soft- or hard-delete an entity from the store."""
        with self._lock:
            entity = self._store.get(entity_id)
            if not entity:
                return False
            if soft:
                entity["status"]  = "deleted"
                entity["updated"] = _now_iso()
            else:
                del self._store[entity_id]
            return True

    def list_all(
        self,
        include_deleted: bool = False,
        use_snapshot:    bool = True,   # accepted for API compat; in-memory always used
    ) -> list[dict[str, Any]]:
        """Return entities from memory.  O(N) — no disk I/O."""
        entities = list(self._store.values())
        if not include_deleted:
            return [e for e in entities if e.get("status") != "deleted"]
        return entities

    def list_stubs(self) -> list[dict[str, Any]]:
        return [e for e in self.list_all() if e.get("status") == "stub"]

    def get_stub_names_for(self, entity_id: str) -> list[str]:
        entity = self.get(entity_id)
        if not entity:
            return []
        stubs  = entity["sections"].get("stubs", [])
        result: list[str] = []
        for name in stubs:
            existing_id = self._index.get(name)
            if not existing_id:
                result.append(name)
            else:
                existing = self.get(existing_id)
                if existing and existing.get("status") == "stub":
                    result.append(name)
        return result

    def count(self, include_deleted: bool = False) -> int:
        if include_deleted:
            return len(self._store)
        return sum(1 for e in self._store.values() if e.get("status") != "deleted")

    def search_by_type(self, entity_type: str) -> list[dict[str, Any]]:
        return [e for e in self.list_all() if e.get("type") == entity_type]

    def search_by_kind(self, kind: str) -> list[dict[str, Any]]:
        def _matches(e: dict[str, Any]) -> bool:
            ek = e.get("kind")
            return (kind in ek) if isinstance(ek, list) else (ek == kind)
        return [e for e in self.list_all() if _matches(e)]

    def search_by_tag(self, tag: str) -> list[dict[str, Any]]:
        tag_lower = tag.lower()
        return [
            e for e in self.list_all()
            if any(
                t.lower() == tag_lower
                for t in e["sections"]["core"].get("tags", [])
            )
        ]

    # ── PM-specific ──────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Write snapshot + name index to disk exactly once.

        Called by scanner.py at scan completion instead of the normal
        list_all() + snapshot.build() two-step.  Writes:

          1. AethvionDB.SNAPSHOT  — single JSON array, identical format to
             EntityWriter's snapshot (queries work transparently).
          2. AethvionDB.SNAPSHOT.meta.json — count + timestamp metadata.
          3. name_index.json — the accumulated name→ID map.
          4. AethvionDB.PMSTORE — marker file so snapshot.is_fresh() returns
             True even though no ws_*.json entity files exist.
        """
        entities = list(self._store.values())
        _snapshot.build(self._db_root, entities)
        self._index.flush_to_disk()

        # Write PM-store marker so snapshot.is_fresh() knows there are no
        # entity files (this is by design, not an error).
        marker = self._db_root / PM_MARKER_FILE
        try:
            marker.write_text("pm-store\n", encoding="utf-8")
        except Exception as exc:
            logger.warning(f"[PMEntityStore] Could not write PM marker: {exc}")

        logger.info(
            f"[PMEntityStore] Flushed {len(entities)} entities → snapshot"
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _apply_sections(
        entity:           dict[str, Any],
        sections_override: dict[str, Any],
    ) -> None:
        """Merge sections_override into entity['sections'] in-place."""
        for sk, sv in sections_override.items():
            if sk in entity["sections"]:
                if isinstance(entity["sections"][sk], dict) and isinstance(sv, dict):
                    entity["sections"][sk].update(sv)
                else:
                    entity["sections"][sk] = sv
            else:
                entity["sections"][sk] = sv
