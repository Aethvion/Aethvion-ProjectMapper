"""
Shared fixtures for the Project Mapper test suite.

Provides a minimal but realistic in-memory knowledge graph (3 entities, 1 call
relation) so tool-handler and query tests don't need to touch the filesystem
beyond a tmp_path scratch directory.
"""

import threading

import pytest

from project_mapper.db.file_manifest import FileManifest
from project_mapper.db.pm_store import PMEntityStore, PMNameIndex
from project_mapper.mcp.tools.base import MCPContext

# ── Storage fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_db(tmp_path):
    db = tmp_path / "testdb"
    db.mkdir()
    return db


@pytest.fixture()
def name_index(tmp_db):
    return PMNameIndex(index_path=tmp_db / "name_index.json")


@pytest.fixture()
def file_manifest(tmp_db):
    return FileManifest(tmp_db)


@pytest.fixture()
def empty_store(tmp_db, name_index):
    return PMEntityStore(tmp_db, name_index)


@pytest.fixture()
def populated_store(tmp_db, name_index):
    """
    Three entities with one call relation:
      get_user  (function)
      UserService  (class)  — calls get_user
      auth_module  (module) — no outbound relations (orphan candidate)
    """
    store = PMEntityStore(tmp_db, name_index)

    func, _ = store.create(
        "get_user",
        entity_type="function",
        source="test",
        sections_override={
            "core": {"summary": "Fetches a user by ID from the database"},
            "properties": {"file_path": "auth/user.py", "line_start": "10", "line_end": "20"},
        },
    )

    store.create(
        "UserService",
        entity_type="class",
        source="test",
        sections_override={
            "core": {"summary": "Service layer for user account management"},
            "properties": {"file_path": "auth/service.py", "line_start": "1"},
            "relations": [{"kind": "calls", "target_id": func["id"]}],
        },
    )

    store.create(
        "auth_module",
        entity_type="module",
        source="test",
        sections_override={
            "core": {"summary": "Top-level authentication package"},
            "properties": {"file_path": "auth/__init__.py", "line_start": "1"},
        },
    )

    return store


# ── MCPContext fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def empty_ctx(tmp_db, empty_store, name_index, file_manifest):
    return MCPContext(
        db_root=tmp_db,
        db_name="test",
        writer=empty_store,
        index=name_index,
        file_manifest=file_manifest,
        project_root=None,
        scan_lock=threading.Lock(),
    )


@pytest.fixture()
def ctx(tmp_db, populated_store, name_index, file_manifest):
    return MCPContext(
        db_root=tmp_db,
        db_name="test",
        writer=populated_store,
        index=name_index,
        file_manifest=file_manifest,
        project_root=None,
        scan_lock=threading.Lock(),
    )
