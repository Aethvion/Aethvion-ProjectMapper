"""
Tests for the DB layer: PMEntityStore, PMNameIndex, FileManifest, and snapshot
persistence. These verify the in-memory store works correctly and that a
flush() + from_snapshot() round-trip preserves all entities faithfully.
"""
import pytest

from project_mapper.db.pm_store import PMEntityStore, PMNameIndex
from project_mapper.db.file_manifest import FileManifest
from project_mapper.db import snapshot as _snap


# ── PMEntityStore ─────────────────────────────────────────────────────────────

class TestPMEntityStore:
    def test_create_and_retrieve(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        entity, created = store.create("MyClass", entity_type="class", source="test")

        assert created is True
        assert entity["name"] == "MyClass"
        assert entity["type"] == "class"
        assert entity["status"] == "active"
        assert entity["id"].startswith("ws_")

    def test_create_idempotent(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        e1, created1 = store.create("MyClass", entity_type="class")
        e2, created2 = store.create("MyClass", entity_type="class")

        assert created1 is True
        assert created2 is False
        assert e1["id"] == e2["id"]

    def test_get_by_id(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        entity, _ = store.create("FooFunc", entity_type="function")
        retrieved = store.get(entity["id"])
        assert retrieved is not None
        assert retrieved["name"] == "FooFunc"

    def test_get_by_name(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        store.create("BarService", entity_type="class")
        retrieved = store.get_by_name("BarService")
        assert retrieved is not None
        assert retrieved["name"] == "BarService"

    def test_soft_delete(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        entity, _ = store.create("ToDelete", entity_type="function")
        eid = entity["id"]

        store.delete(eid, soft=True)
        assert store.get(eid)["status"] == "deleted"

    def test_list_all_excludes_deleted(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        e1, _ = store.create("Alive", entity_type="function")
        e2, _ = store.create("Dead", entity_type="function")
        store.delete(e2["id"], soft=True)

        names = [e["name"] for e in store.list_all()]
        assert "Alive" in names
        assert "Dead" not in names

    def test_list_all_with_deleted(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        e1, _ = store.create("Alive", entity_type="function")
        e2, _ = store.create("Dead", entity_type="function")
        store.delete(e2["id"], soft=True)

        names = [e["name"] for e in store.list_all(include_deleted=True)]
        assert "Alive" in names
        assert "Dead" in names

    def test_count(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        store.create("A", entity_type="function")
        store.create("B", entity_type="function")
        store.create("C", entity_type="function")

        assert store.count() == 3

    def test_update_property(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        entity, _ = store.create("Updateable", entity_type="function")
        store.update(entity["id"], {"kind": "utility"})

        updated = store.get(entity["id"])
        assert updated["kind"] == "utility"

    def test_sections_override_applied(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        entity, _ = store.create(
            "Documented",
            entity_type="function",
            sections_override={"core": {"summary": "Does something useful"}},
        )
        assert entity["sections"]["core"]["summary"] == "Does something useful"

    def test_search_by_type(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        store.create("ClassA", entity_type="class")
        store.create("FuncA", entity_type="function")
        store.create("ClassB", entity_type="class")

        classes = store.search_by_type("class")
        assert len(classes) == 2
        assert all(e["type"] == "class" for e in classes)


# ── Snapshot round-trip ───────────────────────────────────────────────────────

class TestSnapshotRoundtrip:
    def test_flush_and_reload(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        store.create("Alpha", entity_type="module", sections_override={
            "core": {"summary": "Alpha module"},
        })
        store.create("Beta", entity_type="class")
        store.flush()

        assert _snap.snapshot_path(tmp_db).exists()

        index2 = PMNameIndex(index_path=tmp_db / "name_index.json")
        store2 = PMEntityStore.from_snapshot(tmp_db, index2)

        names = {e["name"] for e in store2.list_all()}
        assert "Alpha" in names
        assert "Beta" in names

    def test_flush_preserves_relations(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        caller, _ = store.create("Caller", entity_type="function")
        callee, _ = store.create("Callee", entity_type="function")
        store.update(caller["id"], {
            "sections": {"relations": [{"kind": "calls", "target_id": callee["id"]}]},
        })
        store.flush()

        index2 = PMNameIndex(index_path=tmp_db / "name_index.json")
        store2 = PMEntityStore.from_snapshot(tmp_db, index2)
        reloaded = store2.get_by_name("Caller")
        rels = reloaded["sections"]["relations"]
        assert any(r["kind"] == "calls" and r["target_id"] == callee["id"] for r in rels)

    def test_name_index_survives_reload(self, tmp_db, name_index):
        store = PMEntityStore(tmp_db, name_index)
        entity, _ = store.create("LookupMe", entity_type="function")
        store.flush()

        index2 = PMNameIndex(index_path=tmp_db / "name_index.json")
        eid = index2.get("LookupMe")
        assert eid == entity["id"]


# ── FileManifest ──────────────────────────────────────────────────────────────

class TestFileManifest:
    def test_record_and_get(self, tmp_db):
        fm = FileManifest(tmp_db)
        fm.record("src/main.py", "abc123", ["ws_001", "ws_002"])
        entry = fm.get("src/main.py")
        assert entry is not None
        assert entry["hash"] == "abc123"
        assert "ws_001" in entry["entity_ids"]

    def test_stats_counts_languages(self, tmp_db):
        fm = FileManifest(tmp_db)
        fm.record("a.py", "h1", [])
        fm.record("b.py", "h2", [])
        fm.record("c.ts", "h3", [])

        stats = fm.stats()
        assert stats["total_files"] == 3
        assert stats["by_language"]["python"] == 2
        assert stats["by_language"]["typescript"] == 1

    def test_remove_file(self, tmp_db):
        fm = FileManifest(tmp_db)
        fm.record("temp.py", "deadbeef", [])
        fm.remove_file("temp.py")
        assert fm.get("temp.py") is None

    def test_list_all(self, tmp_db):
        fm = FileManifest(tmp_db)
        fm.record("one.py", "h1", [])
        fm.record("two.py", "h2", [])
        paths = {e["path"] for e in fm.list_all()}
        assert "one.py" in paths
        assert "two.py" in paths

    def test_needs_rescan_unknown_file(self, tmp_db):
        fm = FileManifest(tmp_db)
        assert fm.needs_rescan("never_seen.py", "anyhash") is True

    def test_needs_rescan_unchanged(self, tmp_db):
        fm = FileManifest(tmp_db)
        fm.record("stable.py", "sha256:abc", [])
        assert fm.needs_rescan("stable.py", "sha256:abc") is False

    def test_needs_rescan_changed(self, tmp_db):
        fm = FileManifest(tmp_db)
        fm.record("changed.py", "sha256:old", [])
        assert fm.needs_rescan("changed.py", "sha256:new") is True
