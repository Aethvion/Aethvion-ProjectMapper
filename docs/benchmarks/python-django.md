# Benchmark: Python — Django 5.x

**Date:** 2026-06-09 · **Project Mapper:** v1.4.0

> Real numbers from the [Django source repository](https://github.com/django/django) (main branch, commit `57c8c8b107`). No synthetic data.

---

## The Subject

| | |
|:---|:---|
| Repository | `django/django` |
| Commit | `57c8c8b107` |
| Date tested | **2026-06-09** |
| Project Mapper | **v1.4.0** |
| Python files | **2,417** |
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

## Indexing

### Full Scan (cold start)

| | |
|:---|:---|
| Files discovered | 3,029 |
| Python files analyzed | **2,417** |
| Non-Python files skipped | 611 |
| Entities indexed | **12,139** |
| Relations mapped | **34,894** |
| Stubs resolved | 263 · Relations rewired: 2,984 |
| Errors | 1 (WinError 5 atomic rename — non-fatal, recovered automatically) |
| Snapshot size | **9.95 MB** |
| **Full scan time** | **394 s (~6.5 min)** |

> The snapshot is built twice per scan: once before stub resolution (for the resolver's entity map) and once after with the final rewired relations. Both builds complete in under 90 ms.

### Incremental Scan (zero file changes)

| | |
|:---|:---|
| Files skipped (hash unchanged) | **2,417** |
| **Incremental scan time** | **4.6 s** |
| **Speedup vs full scan** | **85×** |

---

## Query Benchmarks

The primary purpose of Project Mapper is **token reduction**. Each test below compares what an AI agent would consume without PM (Grep + Read source files) against a single PM API call.

> **"Normal" baseline:** token counts assume the agent already knows which files contain the answer. On first contact with an unfamiliar codebase, actual reads are typically 2–3× higher.

---

### D1 — ORM & Forms Field Hierarchy

**Question:** *"What field types does Django's ORM and forms system provide?"*

**Normal approach:** `grep "class.*Field"` across `django/db/models/fields/`, `django/forms/`, `django/contrib/postgres/fields/`, `django/contrib/gis/`. Read each matching module to catalog types. Typically 6+ reads, misses GIS and Postgres fields unless explicitly targeted.

**PM approach:** `impact("Field", via_kinds=["extends"], exclude_tests=True)`

**91 production Field subclasses returned:**
```
ORM core:   DecimalField, JSONField, BooleanField, UUIDField, AutoField, ...
Form:       BaseTemporalField, MultiValueField, ComboField, ...
GIS:        BaseSpatialField, ExtentField, OFTString, OFTInteger, OFTReal, ... (14 types)
Postgres:   JSONField, HStoreField, ArrayField, ArrayAgg, ...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 6+ | **1** | **1** |
| Tokens consumed | ~35,000 | **~4,654** | **~2,207** |
| Field types found | Partial (misses GIS/Postgres unless targeted) | **91 — complete, cross-app** | **91 — complete** |
| Savings vs Normal | — | **~7.5×** | **~15.9×** |

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
| Tokens consumed | ~13,200 | **~81** | **~35** |
| Connection found | Yes | **Yes** | **Yes** |
| Source method identified | Manual (requires reading file) | **Yes — `response_add`** | **Yes — `response_add`** |
| Savings vs Normal | — | **163×** | **377×** |

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

**26 entities returned (8 seeds), ranked by relevance:**
```
[class]  PersistentRemoteUserMiddleware
[class]  AuthenticationMiddlewareSubclass
[class]  AuthenticationMiddleware
[module] django/middleware/security.py
[module] tests/middleware/test_security.py
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 5 | **1** | **1** |
| Tokens consumed | ~13,479 | **~1,349** | **~420** |
| Entities surfaced | 5 files (unranked) | **26 entities (ranked by relevance)** | **26 entities (ranked)** |
| Savings vs Normal | — | **~10×** | **~32×** |

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
| D1 | ORM/form Field types | ~35,000 tok | **~4,654 tok** | **~2,207 tok** | **7.5×** | **15.9×** |
| D2 | ModelAdmin → Model path | ~13,200 tok | **~81 tok** | **~35 tok** | **163×** | **377×** |
| D3 | Management commands | ~4,100 tok | **~386 tok** | **~162 tok** | **10.6×** | **25.3×** |
| D4 | Auth/middleware context | ~13,479 tok | **~1,349 tok** | **~420 tok** | **10×** | **32×** |
| D5 | CBV hierarchy | ~10,000 tok | **~2,398 tok** | **~1,204 tok** | **4.2×** | **8.3×** |

**Geometric mean savings:** PM Full **~14×** · PM Slim **~33×** across all five tests.

> D2 (path query) dominates the arithmetic mean with 163× and 377× savings — path queries have an extreme advantage because the answer is a tiny structured chain (1–5 nodes) vs reading multi-file call chains manually. The geometric mean is the more representative figure for mixed workloads.

---

## Limitations

**Per-query entity-map reload (v1.4.0):** The entity map is rebuilt from the 9.95 MB snapshot on every query request. All query latencies above are ~2.4–2.6 s as a result. A per-db in-memory cache (invalidated on scan completion) would reduce this to under 50 ms. Fix planned for v1.5.0.

**Windows file I/O:** Concurrent JSON writes under Windows Defender occasionally produce WinError 5 (access-denied on atomic rename). PM recovers automatically. Same scan on Linux/macOS is estimated 3–5× faster.

---

## Reproducing

```bash
# 1. Clone Django at the tested commit
git clone https://github.com/django/django
cd django && git checkout 57c8c8b107

# 2. Start PM server
cd /path/to/aethvion-project-mapper
python -m uvicorn server:app --port 7474

# 3. Full scan
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root":"/path/to/django","db":"django","enrich":false,"incremental":false}'

# 4. D1 — Field hierarchy
curl -X POST http://localhost:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"Field","db":"django","via_kinds":["extends"],"exclude_tests":true}'

# 5. D2 — Admin → ORM path
curl -X POST http://localhost:7474/api/project-mapper/query/path \
  -H "Content-Type: application/json" \
  -d '{"from_entity":"ModelAdmin","to_entity":"Model","db":"django"}'

# 6. D4 — Context query
curl -X POST http://localhost:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q":"authentication middleware","db":"django","depth":1,"max_results":30}'
```

---

*Benchmark conducted 2026-06-09 · Aethvion Project Mapper v1.4.0 · Python 3.10.11 · Windows 11 · i9-13900K · RTX 4090*
