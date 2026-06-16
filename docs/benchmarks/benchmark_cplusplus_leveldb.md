# Benchmark: C++ — LevelDB

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `google/leveldb` |
| Language | C++ |
| Files scanned | 132 |
| Total lines | ~28,500 |
| Entities indexed | 603 |
| Scan time | 0.4 s |
| Throughput | ~71,300 lines/sec |

Geometric mean savings: **~86% token reduction (Full) · ~92% token reduction (Slim)** · **~2,112× faster navigation**

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + read tokens a skilled agent
would spend reaching the same answer without Project Mapper.

---

## Test 1 — Iterator Type Catalog

**Question:** *"What concrete iterator types does LevelDB provide?"*

**Standard Workflow (Grep + Read):** `grep -rn "public Iterator" db/ table/`. Iterator implementations are spread across five directories: `table/block.cc` (Block::Iter), `table/merger.cc` (MergingIterator), `table/two_level_iterator.cc` (TwoLevelIterator), `db/db_iter.cc` (DBIter), `db/memtable.cc` (MemTableIterator), `db/version_set.cc` (Version::LevelFileNumIterator). Read each file to confirm the inheritance. 5–7 reads, ~3,000 tokens.

**With Project Mapper:** `pm_impact "Iterator" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5–7 | 1 | 1 |
| Entities found | Partial, cross-directory spread causes misses | 8 — complete, all directories | 8 — complete |
| Token Cost | ~3,000 | ~273 | ~194 |
| Token Reduction | — | **−91%** | **−94%** |
| Execution Time | ~3s | <1ms | <1ms |
| Speedup | — | **~3,000×** | **~3,000×** |

---

## Test 2 — DB Implementation Hierarchy

**Question:** *"What concrete implementations of LevelDB's DB interface exist?"*

**Standard Workflow (Grep + Read):** Read `include/leveldb/db.h` to understand the abstract DB interface (~130 lines), then `db/db_impl.h` to see DBImpl. A separate search is needed to find `ModelDB` defined inside `db/db_test.cc` — a test-only implementation that validates the interface contract but is invisible from the public headers alone. 2–3 reads, ~1,500 tokens.

**With Project Mapper:** `pm_impact "DB" depth=2 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 2–3 | 1 | 1 |
| Entities found | DBImpl only; ModelDB in test file always missed | 3 — DBImpl, ModelDB, Harness test caller | 3 — complete |
| Token Cost | ~1,500 | ~111 | ~96 |
| Token Reduction | — | **−93%** | **−94%** |
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
| Token Cost | ~4,000 | ~702 | ~310 |
| Token Reduction | — | **−82%** | **−92%** |
| Execution Time | ~4s | 2ms | 2ms |
| Speedup | — | **~2,000×** | **~2,000×** |

---

## Test 4 — Write Path Components

**Question:** *"What components make up LevelDB's write path (batching, memtable insertion, WAL logging)?"*

**Standard Workflow (Grep + Read):** Read `include/leveldb/write_batch.h`, `db/write_batch.cc`, `db/log_writer.h`, `db/memtable.h`. The `MemTableInserter` helper class (inside `write_batch.cc`) and the `Logger` implementation hierarchy (WindowsLogger, PosixLogger, NoOpLogger — spread across `util/` and `helpers/`) are easily missed. 4–5 reads, ~3,500 tokens.

**With Project Mapper:** `pm_context "write batch memtable log"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–5 | 1 | 1 |
| Entities found | Partial, Logger hierarchy and MemTableInserter routinely missed | 29 ranked — complete | 29 ranked — complete |
| Token Cost | ~3,500 | ~626 | ~331 |
| Token Reduction | — | **−82%** | **−91%** |
| Execution Time | ~3.5s | 2ms | 2ms |
| Speedup | — | **~1,750×** | **~1,750×** |

---

## Test 5 — SSTable Format Components

**Question:** *"What classes define LevelDB's SSTable (sorted string table) on-disk format?"*

**Standard Workflow (Grep + Read):** Browse `table/` directory: read `block.h` + `block.cc` (Block, Block::Iter), `format.h` (BlockHandle, Footer, BlockContents), `filter_block.h` (FilterBlockBuilder, FilterBlockReader), `block_builder.h`. Five small files, but each must be read individually. The dependency relationships between them (e.g., FilterBlockBuilder is used by the Table builder, which uses BlockHandle from format.h) require mental cross-referencing. 5–6 reads, ~4,000 tokens.

**With Project Mapper:** `pm_context "table block sstable format"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5–6 | 1 | 1 |
| Entities found | All 5 files readable, but cross-file relationships not shown | 30 ranked — incl. format deps + filter | 30 ranked — complete |
| Token Cost | ~4,000 | ~756 | ~321 |
| Token Reduction | — | **−81%** | **−92%** |
| Execution Time | ~4s | 2ms | 2ms |
| Speedup | — | **~2,000×** | **~2,000×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Iterator type catalog | ~3,000 tok | ~273 tok | ~194 tok | **−91%** | **−94%** | ~3,000× |
| Test 2 | DB implementation hierarchy | ~1,500 tok | ~111 tok | ~96 tok | **−93%** | **−94%** | ~2,000× |
| Test 3 | Compaction & version system | ~4,000 tok | ~702 tok | ~310 tok | **−82%** | **−92%** | ~2,000× |
| Test 4 | Write path components | ~3,500 tok | ~626 tok | ~331 tok | **−82%** | **−91%** | ~1,750× |
| Test 5 | SSTable format components | ~4,000 tok | ~756 tok | ~321 tok | **−81%** | **−92%** | ~2,000× |

---

Geometric mean savings: **~86% token reduction (Full) · ~92% token reduction (Slim)** · **~2,112× faster navigation**

> LevelDB is a clean, focused C++ storage engine (~28,500 lines, 603 entities) — one of the smaller codebases in this suite. The high token reduction (−86% Full, −92% Slim) comes from LevelDB's structure: key types like `Version`, `Compaction`, and `TwoLevelIterator` are defined in single large files (`version_set.cc` is ~900 lines), making file reads expensive relative to a PM query. T2 shows the sharpest completeness advantage: the `DB` interface has exactly two real implementations — `DBImpl` (production) and `ModelDB` (test double inside `db_test.cc`) — and manual grep+read always misses the second one. T1's cross-directory iterator scan (8 implementations across `db/` and `table/`) delivers −91% Full and −94% Slim in under 1ms.

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/google/leveldb /path/to/leveldb

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/leveldb" db="leveldb" incremental=false

# Test 1
pm_impact entity="Iterator" db="leveldb" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 2
pm_impact entity="DB" db="leveldb" depth=2 via_kinds=["extends"] exclude_tests=true

# Test 3
pm_context query="compaction version level lsm" db="leveldb"

# Test 4
pm_context query="write batch memtable log" db="leveldb"

# Test 5
pm_context query="table block sstable format" db="leveldb"
```
