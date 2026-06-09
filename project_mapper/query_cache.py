"""
project_mapper/query_cache.py
In-memory entity_map + NameIndex cache for PM query endpoints.

Problem
-------
Every query endpoint calls build_entity_map(writer) → writer.list_all()
→ load 10.4 MB snapshot from disk → parse JSON → build dict[id → entity].
On the Django database (~12,000 entities) this takes ~2.2 s per request.
Five queries from a single agent turn = 11 seconds of pure I/O overhead.

Solution
--------
A module-level cache keyed by db_root holds the last-built entity_map and
NameIndex per database.  Freshness is checked passively against the snapshot
file's mtime — if it hasn't changed, the cached objects are returned in
<1 ms.  A new scan writes a new snapshot, which automatically makes the
cache stale for the next query without any explicit invalidation.

Thundering herd protection (Gemini-reviewed)
--------------------------------------------
Parallel LLM tool calls frequently hit a cache miss simultaneously (e.g.
three impact queries fired at once right after a scan).  A naive cache would
rebuild the entity_map three times concurrently, spiking CPU and memory.

Fix: one asyncio.Lock per db_root.  When a miss occurs, the first request
acquires the lock and rebuilds.  Concurrent requests block on the lock, then
execute the double-check (check → lock → re-check) — they find the cache
warm and return immediately without doing any disk I/O themselves.

Cache size cap
--------------
At most MAX_CACHED_DBS databases are held in memory simultaneously.  When
the cap would be exceeded, the least-recently-used database is evicted
(accessed via last_used timestamp).  Prevents unbounded memory growth when
the server scans many different projects over its lifetime.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Optional

from .db import snapshot as _snapshot
from .db.name_index import NameIndex
from .db.utils import get_logger

logger = get_logger(__name__)

MAX_CACHED_DBS: int = 5


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------

class _CacheEntry:
    """Holds the cached state for one database."""

    __slots__ = ("entity_map", "index", "snap_mtime", "last_used")

    def __init__(
        self,
        entity_map: dict[str, Any],
        index:      NameIndex,
        snap_mtime: float,
    ) -> None:
        self.entity_map: dict[str, Any] = entity_map
        self.index:      NameIndex      = index
        self.snap_mtime: float          = snap_mtime
        self.last_used:  float          = time.monotonic()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class QueryCache:
    """
    Per-db entity_map + NameIndex cache with thundering-herd protection
    and LRU eviction.

    Typical usage in a query endpoint:
        cache       = get_query_cache()
        entity_map, index = await cache.get(db_root)
        result      = await asyncio.to_thread(impact_query, ..., entity_map, index, ...)
    """

    def __init__(self, max_dbs: int = MAX_CACHED_DBS) -> None:
        self._cache:     dict[str, _CacheEntry]  = {}
        self._db_locks:  dict[str, asyncio.Lock] = {}
        self._max_dbs:   int                     = max_dbs
        # _meta_lock guards mutations to _cache and _db_locks dicts themselves.
        # Lock ordering: always acquire _meta_lock BEFORE a db_lock, never inside one.
        self._meta_lock: asyncio.Lock            = asyncio.Lock()

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _get_db_lock(self, key: str) -> asyncio.Lock:
        """Return the per-db asyncio.Lock, creating it if necessary."""
        async with self._meta_lock:
            if key not in self._db_locks:
                self._db_locks[key] = asyncio.Lock()
            return self._db_locks[key]

    def _snap_mtime(self, db_root: Path) -> float:
        """Current mtime of the snapshot file, or 0.0 if it doesn't exist."""
        try:
            return _snapshot.snapshot_path(db_root).stat().st_mtime
        except OSError:
            return 0.0

    def _is_fresh(self, key: str, db_root: Path) -> bool:
        """True if the cached entry exists and the snapshot hasn't changed."""
        entry = self._cache.get(key)
        if entry is None:
            return False
        return self._snap_mtime(db_root) == entry.snap_mtime

    async def _evict_lru(self, incoming_key: str) -> None:
        """Evict the LRU database when the cache is full and a new key arrives."""
        async with self._meta_lock:
            if len(self._cache) >= self._max_dbs and incoming_key not in self._cache:
                lru = min(self._cache, key=lambda k: self._cache[k].last_used)
                del self._cache[lru]
                self._db_locks.pop(lru, None)
                logger.info(f"[QueryCache] Evicted LRU database: {lru}")

    def _build(self, db_root: Path) -> tuple[dict[str, Any], NameIndex, float]:
        """Synchronous helper — load snapshot and build objects.  Runs in a thread."""
        snap_mtime = self._snap_mtime(db_root)
        entities   = _snapshot.load(db_root)
        entity_map = {e["id"]: e for e in entities}
        index      = NameIndex(index_path=db_root / "name_index.json")
        # Force-load now (in this thread) so the first query doesn't block.
        index._ensure_loaded()
        return entity_map, index, snap_mtime

    # ── Public API ────────────────────────────────────────────────────────────

    async def get(self, db_root: Path) -> tuple[dict[str, Any], NameIndex]:
        """
        Return (entity_map, NameIndex) for db_root.

        Cache hit  → <1 ms, pure in-memory.
        Cache miss → load snapshot + name_index.json once, populate cache.

        Thundering-herd safe: concurrent misses for the same db_root
        serialise on the per-db lock.  The first acquirer rebuilds;
        subsequent waiters re-check and serve from the populated cache.
        """
        key = str(db_root)

        # ── Fast path: cache hit (no lock needed — reads are concurrent-safe) ──
        if self._is_fresh(key, db_root):
            entry = self._cache[key]
            entry.last_used = time.monotonic()
            return entry.entity_map, entry.index

        # ── Slow path: cache miss — acquire per-db lock ───────────────────────
        db_lock = await self._get_db_lock(key)
        async with db_lock:
            # Double-check: another waiter may have rebuilt while we held the queue.
            if self._is_fresh(key, db_root):
                entry = self._cache[key]
                entry.last_used = time.monotonic()
                logger.debug(
                    f"[QueryCache] Lock-wait hit for '{db_root.name}' "
                    "— served from cache, no disk I/O"
                )
                return entry.entity_map, entry.index

            # Confirmed miss — we do the rebuild.
            logger.info(
                f"[QueryCache] Cache miss — loading snapshot for '{db_root.name}'"
            )
            entity_map, index, snap_mtime = await asyncio.to_thread(
                self._build, db_root
            )

            await self._evict_lru(key)

            async with self._meta_lock:
                self._cache[key] = _CacheEntry(entity_map, index, snap_mtime)

            logger.info(
                f"[QueryCache] Cached {len(entity_map)} entities"
                f" for '{db_root.name}' (snap_mtime={snap_mtime:.3f})"
            )
            return entity_map, index

    def stats(self) -> dict[str, Any]:
        """Diagnostic snapshot of the current cache state."""
        now = time.monotonic()
        return {
            "cached_dbs":  len(self._cache),
            "max_dbs":     self._max_dbs,
            "entries": [
                {
                    "db":           k,
                    "entity_count": len(v.entity_map),
                    "last_used_s":  round(now - v.last_used, 1),
                }
                for k, v in sorted(
                    self._cache.items(),
                    key=lambda kv: kv[1].last_used,
                    reverse=True,
                )
            ],
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_query_cache = QueryCache()


def get_query_cache() -> QueryCache:
    """Return the shared QueryCache singleton."""
    return _query_cache
