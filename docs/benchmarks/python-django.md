# Benchmark: Python — Django 5.x

**Date:** 2026-06-12 · **Project Mapper:** v1.6.0

> Real numbers from the [Django source repository](https://github.com/django/django) (main branch). No synthetic data.

---

## The Subject

| | |
|:---|:---|
| Repository | `django/django` |
| Date tested | **2026-06-12** |
| Project Mapper | **v1.6.0** |
| Python files | **2,915** |
| JavaScript files | **109** |
| Total files tracked | **3,024** |

---

## Test Environment

| | |
|:---|:---|
| OS | Windows 11 |
| Python | 3.10.11 |
| Hardware | Desktop PC · Intel i9-13900K (24C/32T) · RTX 4090 |
| PM server | Standalone MCP stdio (`python -m project_mapper`) |
| Analysis | Static AST only (no LLM calls) |

> **Windows note:** NTFS and Defender I/O overhead inflates scan time vs Linux/macOS (est. 3–5× faster on Linux).

---

## v1.6.0 Improvements over v1.5.0

| | v1.5.0 | v1.6.0 |
|:---|:---|:---|
| Docstring stealing | Functions near documented functions inherit wrong docstring | Fixed — backwards scan stops at first non-doc line |
| TS/JS call graph | `obj.method()` calls missing from call graph | Fixed — `member_expression` branch added |
| C preprocessor | Typedefs inside `#ifdef` blocks not indexed | Fixed — recursive `_walk_c_scope` walker |
| C++ typedef | `typedef struct Foo Bar;` forward refs not indexed | Fixed — registered as minimal entity |
| Scan prefilter | 1 `asyncio.to_thread` per file for stat | Fixed — single synchronous `_prefilter()` pass |
| Windows UTF-8 | Startup log could crash on narrow codepages (cp1252) | Fixed — wrap before first log line |

---

## Indexing

### Full Scan (cold start)

| | |
|:---|:---|
| Files tracked | **3,024** (Python: 2,915 · JavaScript: 109) |
| Entities indexed | **10,809 active** (+ 427 stubs) |
| Breakdown | class: 6,237 · module: 2,447 · function: 1,980 · dependency: 145 |
| **Full scan time** | **76.9 s** |

> Django's source has grown ~500 Python files since the v1.5.0 benchmark (commit `57c8c8b107` in June 2026 vs earlier checkout). The full scan time scales with file count.

### Warm Scan (no file changes)

| | |
|:---|:---|
| Files skipped (unchanged) | **2,413** |
| Files re-processed | **0** |
| **Warm scan time** | **12.8 s** |

> **Known bottleneck:** 3,024 sequential `stat()` syscalls on Windows cost ~4 ms each. The v1.5.18 `_prefilter()` fix eliminated the parallel `asyncio.to_thread` overhead (which dominated for small projects), but Django-scale projects on Windows are still bounded by raw stat throughput. Target for v1.7.x: switch to `os.scandir()` `DirEntry.stat()` which reuses cached OS data from the directory listing.

---

## Query Performance

> All query times measured on warm cache (in-memory, after first query post-scan).

| Query | Time | Output tokens |
|:---|---:|---:|
| `pm_find "Model"` | **31 ms** | 224 |
| `pm_context slim "database model migrations orm query"` | **125 ms** | 427 |
| `pm_context full "database model migrations orm query"` | **125 ms** | 1,163 |
| `pm_impact "Field"` | **16 ms** | 10,481 |
| `pm_path "Model" → "Field"` | **47 ms** | — |

---

## Agent Navigation Speed

How fast can an agent locate relevant code for a task?

| Method | Tool calls | Time | Output |
|:---|---:|---:|:---|
| Raw grep for `"Model"` | 1 | **1.22 s** | 14,678 raw text matches across 7,063 files — agent must still read and filter |
| `pm_find "Model"` | 1 | **31 ms** | Exact definition at `django/db/models/base.py:499`, callers, callees — ready to act |
| `pm_context slim` | 1 | **125 ms** | 30 ranked entities with file:line — no file reads needed |
| `pm_context full` | 1 | **125 ms** | 30 ranked entities with docstrings and summaries |

| Comparison | Speedup |
|:---|---:|
| `pm_find` vs grep | **39×** |
| `pm_context slim` vs grep | **10×** |
| `pm_context full` vs grep | **10×** |

> Speed savings are multiplicative with token savings — the agent reaches the right code faster *and* uses fewer context tokens to understand it.

### slim vs full

Both `pm_context slim` and `pm_context full` returned results in **125 ms** for Django. At this scale the bottleneck is graph traversal, not serialization. The difference lies in output size (427 vs 1,163 tokens) and content: slim returns name + file:line; full adds docstrings and method summaries. Use slim for navigation, full when you need to understand an entity without reading the source file.

---

## Token Reduction (v1.5.0 / v1.6.0 queries)

> The primary purpose of Project Mapper is **token reduction**. Each test compares what an AI agent would consume without PM (Grep + Read source files) against a single PM API call.

---

### D1 — ORM & Forms Field Hierarchy

**Question:** *"What field types does Django's ORM and forms system provide?"*

**Normal approach:** `grep "class.*Field"` across `django/db/models/fields/`, `django/forms/`, `django/contrib/postgres/fields/`, `django/contrib/gis/`. 6+ reads, misses GIS and Postgres fields unless explicitly targeted.

**PM approach:** `pm_impact "Field"`

**90 production Field subclasses returned:**
```
ORM core:   DecimalField, JSONField, BooleanField, UUIDField, AutoField, ...
Form:       BaseTemporalField, MultiValueField, ComboField, ...
GIS:        BaseSpatialField, ExtentField, OFTString, OFTInteger, OFTReal, ... (14 types)
Postgres:   JSONField, HStoreField, ArrayField, ArrayAgg, ...
```

| Metric | Normal (Grep/Read) | PM Full | PM Slim |
|:---|:---|:---|:---|
| Tool calls | 6+ | **1** | **1** |
| Tokens consumed | ~35,000 | **~4,613** | **~2,190** |
| Field types found | Partial (misses GIS/Postgres) | **90 — complete** | **90 — complete** |
| Savings | — | **~7.6×** | **~16×** |

---

### D2 — Cross-App Path: Admin → ORM

**Question:** *"How does Django's admin connect to the ORM model layer?"*

**PM approach:** `pm_path "ModelAdmin" "Model"`

```
ModelAdmin --[calls]--> Model   (via response_add)
```

| Metric | Normal (Grep/Read) | PM Full | PM Slim |
|:---|:---|:---|:---|
| Tool calls | 3 | **1** | **1** |
| Tokens consumed | ~13,200 | **~114** | **~46** |
| Savings | — | **~116×** | **~287×** |

---

### D3 — Management Command Catalog

**PM approach:** `pm_impact "BaseCommand"`

| Metric | Normal (Grep/Read) | PM Full | PM Slim |
|:---|:---|:---|:---|
| Tool calls | 4+ | **1** | **1** |
| Tokens consumed | ~4,100 | **~386** | **~162** |
| Savings | — | **~10.6×** | **~25.3×** |

---

### D4 — Pre-Task Context: Authentication & Middleware

**PM approach:** `pm_context "authentication middleware"`

| Metric | Normal (Grep/Read) | PM Full | PM Slim |
|:---|:---|:---|:---|
| Tool calls | 5 | **1** | **1** |
| Tokens consumed | ~13,479 | **~1,573** | **~512** |
| Savings | — | **~8.6×** | **~26.3×** |

---

### D5 — Class-Based View Hierarchy

**PM approach:** `pm_impact "View"`

**45 production CBVs returned (complete, cross-app):**
```
Generic:  TemplateView, RedirectView, ListView, DetailView, FormView, ...
Dates:    BaseDateListView, WeekArchiveView, MonthArchiveView, ...
Admin:    AutocompleteJsonView, ModelIndexView, ...
Auth:     LogoutView, PasswordChangeDoneView, ...
i18n:     JavaScriptCatalog, JSONCatalog
```

| Metric | Normal (Grep/Read) | PM Full | PM Slim |
|:---|:---|:---|:---|
| Tool calls | 4–5 | **1** | **1** |
| Tokens consumed | ~10,000 | **~2,398** | **~1,204** |
| CBVs found | ~15 (generic only) | **45 — complete, all apps** | **45 — complete** |
| Savings | — | **~4.2×** | **~8.3×** |

---

## Headline Numbers

| Test | Question | Normal | PM Full | PM Slim | Savings Full | Savings Slim |
|:---|:---|:---|:---|:---|:---|:---|
| D1 | ORM/form Field types | ~35,000 tok | ~4,613 tok | ~2,190 tok | **7.6×** | **16×** |
| D2 | ModelAdmin → Model path | ~13,200 tok | ~114 tok | ~46 tok | **116×** | **287×** |
| D3 | Management commands | ~4,100 tok | ~386 tok | ~162 tok | **10.6×** | **25.3×** |
| D4 | Auth/middleware context | ~13,479 tok | ~1,573 tok | ~512 tok | **8.6×** | **26.3×** |
| D5 | CBV hierarchy | ~10,000 tok | ~2,398 tok | ~1,204 tok | **4.2×** | **8.3×** |

**Geometric mean savings:** PM Full **~13×** · PM Slim **~30×**

---

*Benchmark conducted 2026-06-12 · Aethvion Project Mapper v1.6.0 · Python 3.10.11 · Windows 11 · i9-13900K · RTX 4090*
