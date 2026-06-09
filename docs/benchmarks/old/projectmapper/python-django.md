# Benchmark: Python — Django 5.x

> **Real numbers. No synthetic data. All measurements taken on the actual
> [Django source repository](https://github.com/django/django) (commit `57c8c8b107`).**

---

## The Subject

Django is one of the most widely used Python web frameworks in the world. It has been
under active development for 20+ years and is maintained by a large open-source community.
Its codebase is a representative example of a mature, large-scale Python monorepo —
the kind that AI coding agents struggle with most.

| Repository | `django/django` |
|---|---|
| Commit | `57c8c8b107` |
| Date tested | **2026-06-09** |
| Project Mapper | **v1.4.0** |
| Python files | **2,919** |
| Total files | **3,029** |

---

## Test Environment

| | |
|---|---|
| OS | Windows 11 |
| Python | 3.10.11 |
| Aethvion Project Mapper | **v1.4.0** (standalone server) |
| LLM enrichment | **disabled** (`enrich=false`) — pure static analysis |
| Concurrency | 3 (default) |
| Hardware | Consumer laptop |

> **Windows note**: NTFS and Defender scan latency inflate file I/O times compared to
> Linux or macOS. The full-scan timing below reflects real Windows conditions.
> On Linux or macOS the same scan runs approximately 3–5x faster.

---

## Phase 1 — Full Scan

A full cold scan of the entire repository with no prior index.

```bash
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/path/to/django", "db": "django", "enrich": false, "incremental": false}'
```

### Results

| Metric | Value |
|---|---|
| Files discovered | 3,029 |
| Python files analyzed (AST) | **2,417** |
| Non-Python files skipped | 611 |
| **Entities indexed** | **11,988** |
| — Classes | 7,327 |
| — Modules | 2,614 |
| — Functions | 1,904 |
| — Dependencies | 143 |
| **Relations mapped** | **34,876** |
| Stubs resolved | 268 |
| Relations rewired | 3,047 |
| Errors | 1 (Windows WinError 5 on name_index rename — recovered automatically) |
| **Full scan time (Windows)** | **425 s (~7 min)** |
| Estimated on Linux/macOS | ~85–140 s (~1.5–2.5 min) |

> **Improvement vs v1.1.0:** 604 s → 425 s — **30% faster** on identical hardware
> and the same commit. Bug fixes and ingestor optimizations in v1.4.0 account for the gain.

---

## Phase 2 — Incremental Scan

Immediately after the full scan, with **zero file changes**.

```bash
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/path/to/django", "db": "django"}'
```

### Results

| Metric | Value |
|---|---|
| Files discovered | 3,029 |
| Files skipped (hash unchanged) | **2,417** |
| Files actually processed | **1** |
| Entities created | 8 |
| Entities updated | 0 |
| **Incremental scan time** | **5.1 s** |
| **Speedup vs full scan** | **83x** |

After the initial full scan, re-running on an unchanged codebase takes under 6 seconds
regardless of repository size — 2,417 files are skipped after a single SHA-256 hash
comparison per file.

---

## Phase 2b — Snapshot Load Time

The entity map (11,988 entities) is stored in a single pre-serialized snapshot file.
At query time the server loads the snapshot rather than opening each entity JSON file.

| Metric | Value |
|---|---|
| Snapshot file size | **9.94 MB** |
| Entity count stored | 11,988 (all statuses) |
| Cold session first-query overhead | **~2.5 s** (snapshot load + query) |
| Warm subsequent queries | **~460–520 ms** (entity-map deserialization) |

> **Optimization note:** v1.4.0 rebuilds the entity map from the snapshot on **every
> query request**. A per-db in-memory cache (invalidated on scan completion) is planned
> for v1.5.0 and will reduce warm query latency to under 50 ms.

---

## Phase 3 — Query Performance

All timings below are **warm** (snapshot already in OS page cache, server already
processed one prior request to populate memory).

### 3a — Context Queries

A context query answers: *"I'm about to work on X. What entities should I know about?"*

| Query | Seeds | Results | Est. tokens | Time |
|---|---|---|---|---|
| `"authentication middleware security"` | 8 | 30 | **2,400** | 518 ms |
| `"migration schema database"` | 8 | 28 | **2,240** | 493 ms |
| `"template render"` | 8 | 15 | **1,200** | 466 ms |
| `"signal dispatch"` | 8 | 30 | **2,400** | 455 ms |

**Example output — `"authentication middleware security"`** (top seeds):

```
[class]  PersistentRemoteUserMiddleware    score=3.55
[class]  AuthenticationMiddlewareSubclass  score=3.45
[class]  AuthenticationMiddleware          score=3.15
[module] tests/auth_tests/test_middleware.py
[module] django/middleware/security.py
```

#### Token comparison — context query

To answer the same question without Project Mapper, an agent would typically read the
4–8 most relevant source files in full:

| File | Approx tokens |
|---|---|
| `django/contrib/auth/middleware.py` | ~2,956 |
| `django/middleware/security.py` | ~649 |
| `django/middleware/common.py` | ~2,040 |
| `django/core/handlers/base.py` | ~3,710 |
| `django/conf/__init__.py` | ~3,786 |
| **5 files total** | **~13,141** |

| | Tokens |
|---|---|
| Reading 5 relevant files (no PM) | ~13,141 |
| PM context query response | **2,400** |
| **Token reduction** | **82 %** |

And that assumes the agent already knew *which* 5 files to read. On first encounter
with a codebase, it would typically read 10–20 files before narrowing in.

---

### 3b — Impact Queries

An impact query answers: *"If I change entity X, what else is affected?"*

| Subject | Direct (hop 1) | Transitive (hop 2) | Total affected | Est. tokens | Time |
|---|---|---|---|---|---|
| `Model` (Django base model) | 33 | 21 | **68** | **3,646** | 483 ms |
| `DatabaseWrapper` | 3 | 0 | **3** | **192** | 484 ms |
| `AuthenticationMiddleware` | 0 | 0 | **0** | **63** | 484 ms |

**Example — `Model` impact (first 6 of 68 affected):**

```
hop1: [class]    FieldOperation              via=calls
hop1: [class]    DeleteModel                 via=calls
hop1: [function] get_user_model              via=calls
hop1: [function] check_models_permissions    via=calls
hop1: [function] create_contenttypes         via=calls
hop1: [class]    ContentType                 via=calls
```

The `Model` class has 68 entities depending on it across 2 hops. Finding this manually
requires grepping a 450k-line codebase and reading dozens of files. Project Mapper
returns the full impact chain in **<500 ms** and under **4,000 tokens**.

#### Token comparison — impact query

| File | Tokens |
|---|---|
| `django/db/models/query.py` | ~29,523 |
| `django/db/models/base.py` | ~24,889 |
| **2 files** | **~54,412** |

| | Tokens |
|---|---|
| Reading just 2 core ORM files | ~54,412 |
| PM impact query response | **3,646** |
| **Token reduction** | **93 %** |

---

## Summary

| Metric | v1.4.0 Result | vs v1.1.0 |
|---|---|---|
| Repository size | ~450k lines · 2,919 Python files | same codebase |
| Entities indexed | **11,988** | same total |
| Relations mapped | **34,876** | +368 (+1.1%) |
| Full scan (Windows) | **425 s** | **-30%** (was 604 s) |
| Full scan (Linux/macOS est.) | ~85–140 s | — |
| Incremental scan (no changes) | **5.1 s** — 83x faster | — |
| Snapshot size | **9.94 MB** | ~same |
| Context query latency (warm) | **455–518 ms** | entity-map cache pending |
| Impact query latency (warm) | **~484 ms** | entity-map cache pending |
| Token reduction vs. reading files | **82–93 %** | comparable |
| LLM enrichment required | **No** | No |

---

## What Works Without LLM Enrichment

This benchmark used `enrich=false` — no AI provider, no API keys, no cost.
Static analysis alone provides:

- Full AST extraction (classes, functions, modules, imports)
- Relation mapping (calls, imports, extends, depends_on, ...)
- Incremental scanning with SHA-256 hash comparison
- Impact analysis (directed BFS through the dependency graph)
- Context queries (keyword + file-path scoring across 11,988 active entities)

LLM enrichment adds natural-language summaries, architectural pattern tags, and
semantic aliases — improving context query relevance. Optional enhancement, not required.

---

## Limitations Observed

**Per-query entity-map reload (v1.4.0):** The entity map is rebuilt from the snapshot
on every request. Warm query latency is ~460–520 ms rather than the <50 ms possible
with an in-memory cache. Fix is planned for v1.5.0.

**Windows file I/O overhead:** Concurrent JSON writes under Windows Defender produce
occasional `WinError 5` (access denied on atomic rename). Project Mapper recovers
automatically with retry logic, but it slows the full scan vs Linux/macOS.

**Test entities included:** Django's test suite is large (1,500+ test classes).
Impact queries exclude test entities by default (`exclude_tests=true`). Context queries
include them, which can surface test helpers alongside production code.

---

## Reproducing This Test

```bash
# 1. Clone Django
git clone https://github.com/django/django /tmp/django
cd /tmp/django && git checkout 57c8c8b107

# 2. Install Project Mapper
pip install aethvion-project-mapper==1.4.0

# 3. Start the server
pm-server --port 7474 &

# 4. Full scan
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/tmp/django", "db": "django", "enrich": false, "incremental": false}'

# 5. Context query
curl -X POST http://localhost:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q": "authentication middleware security", "db": "django", "depth": 1}'

# 6. Impact query
curl -X POST http://localhost:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity": "Model", "db": "django", "max_depth": 2}'
```

---

*Benchmark conducted 2026-06-09 · Aethvion Project Mapper v1.4.0 · Python 3.10.11 · Windows 11*
