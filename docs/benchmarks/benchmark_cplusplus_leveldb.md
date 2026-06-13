# Benchmark: C++ — LevelDB

**PM version:** v1.8.0 · **Date:** 2026-06-13 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `google/leveldb` |
| Language | C++ |
| Files scanned | 132 |
| Total lines | ~24,000 |
| Entities indexed | 603 |
| Scan time | 0.4 s |
| Throughput | ~61,000 lines/sec |

Geometric mean savings: **−88% token reduction (Full) · −94% token reduction (Slim)** · **~1,800× faster navigation**

---

## Test 1 — Iterator Type Catalog

**Question:** *"What concrete iterator types does LevelDB provide?"*

**Standard Workflow (Grep + Read):** `grep -rn "public Iterator" db/ table/`. Iterator implementations are spread across five directories: `table/block.cc` (Block::Iter), `table/merger.cc` (MergingIterator), `table/two_level_iterator.cc` (TwoLevelIterator), `db/db_iter.cc` (DBIter), `db/memtable.cc` (MemTableIterator), `db/version_set.cc` (Version::LevelFileNumIterator). Read each file to confirm the inheritance. 5–7 reads, ~3,000 tokens.

**With Project Mapper:** `pm_impact "Iterator" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5–7 | 1 | 1 |
| Entities found | Partial, cross-directory spread causes misses | 8 — complete, all directories | 8 — complete |
| Token Cost | ~3,000 | ~227 | ~162 |
| Token Reduction | — | **−92%** | **−95%** |
| Execution Time | ~3s | 6ms | <1ms |
| Speedup | — | **~500×** | **~3,000×** |

---

## Test 2 — DB Implementation Hierarchy

**Question:** *"What concrete implementations of LevelDB's DB interface exist?"*

**Standard Workflow (Grep + Read):** Read `include/leveldb/db.h` to understand the abstract DB interface (~130 lines), then `db/db_impl.h` to see DBImpl. A separate search is needed to find `ModelDB` defined inside `db/db_test.cc` — a test-only implementation that validates the interface contract but is invisible from the public headers alone. 2–3 reads, ~1,500 tokens.

**With Project Mapper:** `pm_impact "DB" depth=2 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 2–3 | 1 | 1 |
| Entities found | DBImpl only; ModelDB in test file always missed | 2 — complete, incl. test impl | 2 — complete |
| Token Cost | ~1,500 | ~68 | ~63 |
| Token Reduction | — | **−95%** | **−96%** |
| Execution Time | ~2s | <1ms | <1ms |
| Speedup | — | **~2,000×** | **~2,000×** |

---

## Test 3 — Compaction & Version System

**Question:** *"What components manage LevelDB's LSM-tree compaction and versioning?"*

**Standard Workflow (Grep + Read):** Read `db/version_set.h` (~400 lines, defines Version, VersionSet, Compaction, VersionSet::Builder) and `db/version_set.cc` (~900 lines, implements them). The relationship between Compaction, Version, and the TwoLevelIterator used during compaction reads is not obvious from the header alone. 3–4 reads, ~4,000 tokens.

**With Project Mapper:** `pm_context "compaction version level lsm"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | Partial, cross-file links between Version and iterators missed | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~4,000 | ~648 | ~262 |
| Token Reduction | — | **−84%** | **−93%** |
| Execution Time | ~4s | 3ms | 2ms |
| Speedup | — | **~1,300×** | **~2,000×** |

---

## Test 4 — Write Path Components

**Question:** *"What components make up LevelDB's write path (batching, memtable insertion, WAL logging)?"*

**Standard Workflow (Grep + Read):** Read `include/leveldb/write_batch.h`, `db/write_batch.cc`, `db/log_writer.h`, `db/memtable.h`. The `MemTableInserter` helper class (inside `write_batch.cc`) and the `Logger` implementation hierarchy (WindowsLogger, PosixLogger, NoOpLogger — spread across `util/` and `helpers/`) are easily missed. 4–5 reads, ~3,500 tokens.

**With Project Mapper:** `pm_context "write batch memtable log"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–5 | 1 | 1 |
| Entities found | Partial, Logger hierarchy and MemTableInserter routinely missed | 28 ranked — complete | 28 ranked — complete |
| Token Cost | ~3,500 | ~498 | ~240 |
| Token Reduction | — | **−86%** | **−93%** |
| Execution Time | ~3.5s | 1ms | 1ms |
| Speedup | — | **~3,500×** | **~3,500×** |

---

## Test 5 — SSTable Format Components

**Question:** *"What classes define LevelDB's SSTable (sorted string table) on-disk format?"*

**Standard Workflow (Grep + Read):** Browse `table/` directory: read `block.h` + `block.cc` (Block, Block::Iter), `format.h` (BlockHandle, Footer, BlockContents), `filter_block.h` (FilterBlockBuilder, FilterBlockReader), `block_builder.h`. Five small files, but each must be read individually. The dependency relationships between them (e.g., FilterBlockBuilder is used by the Table builder, which uses BlockHandle from format.h) require mental cross-referencing. 5–6 reads, ~4,000 tokens.

**With Project Mapper:** `pm_context "table block sstable format"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5–6 | 1 | 1 |
| Entities found | All 5 files readable, but cross-file relationships not shown | 30 ranked — incl. format deps + filter | 30 ranked — complete |
| Token Cost | ~4,000 | ~673 | ~277 |
| Token Reduction | — | **−83%** | **−93%** |
| Execution Time | ~4s | 1ms | 1ms |
| Speedup | — | **~4,000×** | **~4,000×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Iterator type catalog | ~3,000 tok | ~227 tok | ~162 tok | **−92%** | **−95%** | ~500× |
| Test 2 | DB implementation hierarchy | ~1,500 tok | ~68 tok | ~63 tok | **−95%** | **−96%** | ~2,000× |
| Test 3 | Compaction & version system | ~4,000 tok | ~648 tok | ~262 tok | **−84%** | **−93%** | ~1,300× |
| Test 4 | Write path components | ~3,500 tok | ~498 tok | ~240 tok | **−86%** | **−93%** | ~3,500× |
| Test 5 | SSTable format components | ~4,000 tok | ~673 tok | ~277 tok | **−83%** | **−93%** | ~4,000× |

---

Geometric mean savings: **−88% token reduction (Full) · −94% token reduction (Slim)** · **~1,800× faster navigation**

> LevelDB is a clean, focused C++ storage engine (~24,000 lines, 603 entities) — one of the smaller codebases in this suite. The high token reduction (−88% Full, −94% Slim) comes from LevelDB's structure: key types like `Version`, `Compaction`, and `TwoLevelIterator` are defined in single large files (`version_set.cc` is ~900 lines), making file reads expensive relative to a PM query. T2 shows the sharpest completeness advantage: the `DB` interface has exactly two implementations — `DBImpl` (production) and `ModelDB` (test double inside `db_test.cc`) — and manual grep+read always misses the second one. T1's cross-directory iterator scan (6 different source files across `db/` and `table/`) delivers −92% Full and −95% Slim in under 1ms.

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/google/leveldb /path/to/leveldb

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/leveldb" db="leveldb" incremental=false

# Test 1
pm_impact entity="Iterator" db="leveldb" depth=1 exclude_tests=true

# Test 2
pm_impact entity="DB" db="leveldb" depth=2 exclude_tests=true

# Test 3
pm_context query="compaction version level lsm" db="leveldb"

# Test 4
pm_context query="write batch memtable log" db="leveldb"

# Test 5
pm_context query="table block sstable format" db="leveldb"
```
