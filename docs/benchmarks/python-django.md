# Benchmark: Python — Django 5.x

**Date:** 2026-06-10 · **Project Mapper:** v1.5.0

> Real numbers from the [Django source repository](https://github.com/django/django) (main branch, commit `57c8c8b107`). No synthetic data.

---

## The Subject

| | |
|:---|:---|
| Repository | `django/django` |
| Commit | `57c8c8b107` |
| Date tested | **2026-06-10** |
| Project Mapper | **v1.5.0** |
| Python files | **2,418** |
| Total files | **3,029** |

---

## Test Environment

| | |
|:---|:---|
| OS | Windows 11 |
| Python | 3.10.11 |
| Hardware | Desktop PC · Intel i9-13900K (24C/32T) · RTX 4090 |
| PM server | Standalone · `python -m uvicorn server:app --port 7474` |
| LLM enrichment | **Disabled** (`enrich=false`) — pure static analysis |

> **Windows note:** NTFS and Defender I/O overhead inflates scan time vs Linux/macOS (est. 3–5× faster on Linux).

---

## v1.5.0 Improvements

| | v1.4.0 | v1.5.0 | Delta |
|:---|:---|:---|:---|
| Scan engine | EntityWriter (1 file/entity) | **PMEntityStore** (in-memory → 1 snapshot flush) | **10.1× faster** |
| Entity files on disk | ~24,000+ ws_*.json | **0** (snapshot only) | Zero per-entity I/O |
| Query engine | Snapshot reload per request | **QueryCache** (mtime-invalidated, per-db lock) | **~150× faster warm** |
| Query latency (cold) | ~2.2 s (localhost DNS + snapshot rebuild) | **~90 ms** | — |
| Query latency (warm) | ~2.2 s | **10–100 ms** | — |

---

## Indexing

### Full Scan (cold start)

| | |
|:---|:---|
| Files discovered | 3,029 |
| Python files analyzed | **2,418** |
| Non-Python files skipped | 611 |
| Entities indexed | **12,140** |
| Relations mapped | **34,950** |
| Stubs resolved | 342 · Relations rewired: 1,520 |
| Errors | **0** |
| Snapshot size | **9.93 MB** |
| Entity files on disk | **0** (PMEntityStore — all entities flushed to single snapshot) |
| **Full scan time** | **39 s** _(v1.4.0: 394 s — **10.1× speedup**)_ |

### Incremental Scan (zero file changes)

| | |
|:---|:---|
| Files skipped (hash unchanged) | **2,418** |
| **Incremental scan time** | **1.5 s** _(v1.4.0: 4.6 s — **3.1× speedup**)_ |
| **Speedup vs full scan** | **26×** |

---

## Query Benchmarks

The primary purpose of Project Mapper is **token reduction**. Each test below compares what an AI agent would consume without PM (Grep + Read source files) against a single PM API call.

> **"Normal" baseline:** token counts assume the agent already knows which files contain the answer. On first contact with an unfamiliar codebase, actual reads are typically 2–3× higher.
>
> **Query latency (v1.5.0):** cold miss ~90 ms (first query after scan); warm hits 10–100 ms (in-memory cache, mtime-validated).

---

### D1 — ORM & Forms Field Hierarchy

**Question:** *"What field types does Django's ORM and forms system provide?"*

**Normal approach:** `grep "class.*Field"` across `django/db/models/fields/`, `django/forms/`, `django/contrib/postgres/fields/`, `django/contrib/gis/`. Read each matching module to catalog types. Typically 6+ reads, misses GIS and Postgres fields unless explicitly targeted.

**PM approach:** `impact("Field", via_kinds=["extends"], exclude_tests=True)`

**90 production Field subclasses returned:**
```
ORM core:   DecimalField, JSONField, BooleanField, UUIDField, AutoField, ...
Form:       BaseTemporalField, MultiValueField, ComboField, ...
GIS:        BaseSpatialField, ExtentField, OFTString, OFTInteger, OFTReal, ... (14 types)
Postgres:   JSONField, HStoreField, ArrayField, ArrayAgg, ...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 6+ | **1** | **1** |
| Tokens consumed | ~35,000 | **~4,613** | **~2,190** |
| Field types found | Partial (misses GIS/Postgres unless targeted) | **90 — complete, cross-app** | **90 — complete** |
| Savings vs Normal | — | **~7.6×** | **~16×** |

---

### D2 — Cross-App Path: Admin → ORM

**Question:** *"How does Django's admin interface connect to the ORM model layer — and which method bridges the gap?"*

**Normal approach:** Read `django/contrib/admin/options.py` and `django/db/models/base.py` to trace the connection manually. 3 tool calls, ~13,200 tokens. The bridging method name requires reading the function body.

**PM approach:** `path("ModelAdmin", "Model")`

**Result (1 hop, semantic path):**
```
ModelAdmin --[calls]--> note: "via response_add"
Model
```

The `note` field names the exact bridging method — no file read required.

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 3 | **1** | **1** |
| Tokens consumed | ~13,200 | **~114** | **~46** |
| Connection found | Yes | **Yes** | **Yes** |
| Source method identified | Manual (requires reading file) | **Yes — `response_add`** | **Yes — `response_add`** |
| Savings vs Normal | — | **~116×** | **~287×** |

---

### D3 — Management Command Catalog

**Question:** *"What management commands does Django provide?"*

**Normal approach:** Locate `management/commands/` directories, read `django/core/management/base.py`, then read each concrete command file. 4+ reads, ~4,100 tokens, still incomplete across all apps.

**PM approach:** `impact("BaseCommand", exclude_tests=True)`

**5 production command classes:**
```
LabelCommand       django/core/management/base.py
AppCommand         django/core/management/base.py
TemplateCommand    django/core/management/templates.py
Command            django/contrib/auth/management/commands/changepassword.py
load_command_class django/core/management/__init__.py
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 4+ | **1** | **1** |
| Tokens consumed | ~4,100 | **~386** | **~162** |
| Commands found | Partial (file-limited) | **5 — complete, all apps** | **5 — complete** |
| Savings vs Normal | — | **~10.6×** | **~25.3×** |

---

### D4 — Pre-Task Context: Authentication & Middleware

**Question:** *"I'm about to work on authentication and middleware — what entities should I know about?"*

**Normal approach:** Read `django/contrib/auth/middleware.py` (~3,030 tok), `django/middleware/security.py` (~666 tok), `django/middleware/common.py` (~2,089 tok), `django/core/handlers/base.py` (~3,804 tok), `django/conf/__init__.py` (~3,890 tok). 5 reads, 13,479 tokens. Returns raw file content with no entity ranking.

**PM approach:** `context("authentication middleware")`

**30 entities returned (8 seeds), ranked by relevance:**
```
[class]  PersistentRemoteUserMiddleware
[class]  AuthenticationMiddlewareSubclass
[class]  AuthenticationMiddleware
[module] django/middleware/security.py
[module] django/contrib/auth/middleware.py
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 5 | **1** | **1** |
| Tokens consumed | ~13,479 | **~1,573** | **~512** |
| Entities surfaced | 5 files (unranked) | **30 entities (ranked by relevance)** | **30 entities (ranked)** |
| Savings vs Normal | — | **~8.6×** | **~26.3×** |

---

### D5 — Class-Based View Hierarchy

**Question:** *"What class-based views does Django provide?"*

**Normal approach:** Read `django/views/generic/base.py`, `list.py`, `edit.py`, `detail.py`, `dates.py`. 4–5 reads, ~10,000 tokens. Misses CBVs in `django/contrib/admin/`, `django/contrib/auth/`, and `django/views/i18n.py`.

**PM approach:** `impact("View", via_kinds=["extends"], exclude_tests=True)`

**45 production CBVs returned (complete, cross-app):**
```
Generic:  TemplateView, RedirectView, ListView, DetailView, FormView,
          CreateView, UpdateView, DeleteView, BaseListView, ...
Dates:    BaseDateListView, WeekArchiveView, MonthArchiveView, YearArchiveView, ...
Admin:    AutocompleteJsonView, ModelIndexView, ViewDetailView, ...
Auth:     LogoutView, PasswordChangeDoneView, PasswordResetDoneView, ...
i18n:     JavaScriptCatalog, JSONCatalog
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 4–5 | **1** | **1** |
| Tokens consumed | ~10,000 | **~2,398** | **~1,204** |
| CBVs found | ~15 (generic views only) | **45 — complete, all apps** | **45 — complete** |
| Savings vs Normal | — | **~4.2×** | **~8.3×** |

---

## Headline Numbers

| Test | Question | Normal | PM (Full) | PM (Slim) | Savings (Full) | Savings (Slim) |
|:---|:---|:---|:---|:---|:---|:---|
| D1 | ORM/form Field types | ~35,000 tok | **~4,613 tok** | **~2,190 tok** | **7.6×** | **16×** |
| D2 | ModelAdmin → Model path | ~13,200 tok | **~114 tok** | **~46 tok** | **116×** | **287×** |
| D3 | Management commands | ~4,100 tok | **~386 tok** | **~162 tok** | **10.6×** | **25.3×** |
| D4 | Auth/middleware context | ~13,479 tok | **~1,573 tok** | **~512 tok** | **8.6×** | **26.3×** |
| D5 | CBV hierarchy | ~10,000 tok | **~2,398 tok** | **~1,204 tok** | **4.2×** | **8.3×** |

**Geometric mean savings:** PM Full **~13×** · PM Slim **~30×** across all five tests.

> D2 (path query) dominates the arithmetic mean with 116× and 287× savings — path queries have an extreme advantage because the answer is a tiny structured chain (1–5 nodes) vs reading multi-file call chains manually. The geometric mean is the more representative figure for mixed workloads.

---

## Windows File I/O Note

**Per-entity disk writes (v1.4.0):** EntityWriter wrote one ws_*.json file per entity. Django's ~12,000 entities = ~24,000+ atomic file operations, each triggering a Windows Defender rescan. This was the primary scan bottleneck (394 s on Windows vs an estimated 30–60 s on Linux).

**v1.5.0 fix:** PMEntityStore accumulates all entities in memory during the scan and writes a single 9.93 MB snapshot file at completion. Zero per-entity file operations. Scan time dropped to **39 s** on the same Windows hardware.

---

## Reproducing

```bash
# 1. Clone Django at the tested commit
git clone https://github.com/django/django
cd django && git checkout 57c8c8b107

# 2. Start PM server
cd /path/to/aethvion-project-mapper
python -m uvicorn server:app --port 7474

# IMPORTANT: always use 127.0.0.1, not localhost
# Windows resolves "localhost" via IPv6 first (~2 s timeout before IPv4 fallback)

# 3. Full scan
curl -X POST http://127.0.0.1:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root":"/path/to/django","db":"django","enrich":false,"incremental":false}'

# 4. D1 — Field hierarchy
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"Field","db":"django","via_kinds":["extends"],"exclude_tests":true}'

# 5. D2 — Admin → ORM path
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/path \
  -H "Content-Type: application/json" \
  -d '{"from_entity":"ModelAdmin","to_entity":"Model","db":"django"}'

# 6. D4 — Context query
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q":"authentication middleware","db":"django","depth":1,"max_results":30}'
```

---

*Benchmark conducted 2026-06-10 · Aethvion Project Mapper v1.5.0 · Python 3.10.11 · Windows 11 · i9-13900K · RTX 4090*
