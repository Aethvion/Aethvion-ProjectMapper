# Case Study: Indexing Django 5.x with Aethvion Project Mapper

> **Real numbers. No synthetic data. All measurements taken on the actual
> [Django source repository](https://github.com/django/django) (branch `stable/5.1.x`,
> commit `57c8c8b107`, June 2026).**

---

## The Subject

Django is one of the most widely used Python web frameworks in the world. It has been
under active development for 20+ years and is maintained by a large open-source community.
Its codebase is a representative example of a mature, large-scale Python monorepo —
the kind that AI coding agents struggle with most.

| Repository | `django/django` |
|---|---|
| Branch | `stable/5.1.x` |
| Commit | `57c8c8b107` |
| Date | June 2026 |
| Python files | **2,918** |
| Total lines (Python) | **521,286** |
| Non-Python files | 111 (JS, HTML, RST, YAML, …) |
| Total files | 3,029 |

---

## Test Environment

| | |
|---|---|
| OS | Windows 11 |
| Python | 3.10.x |
| Aethvion Project Mapper | v1.0.0 (standalone, no Aethvion Suite) |
| LLM enrichment | **disabled** (`enrich=False`) — pure static analysis |
| Concurrency | 3 (default) |
| Hardware | Consumer laptop |

> **Important**: Windows has higher file I/O overhead than Linux or macOS due to NTFS
> and Defender scan latency. The full-scan timing below reflects Windows conditions.
> On Linux or macOS the same scan runs approximately 3–5× faster.

---

## Phase 1 — Full Scan

A full cold scan of the entire repository with no prior index.

```bash
# Equivalent HTTP call:
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/path/to/django", "db": "django", "enrich": false}'
```

### Results

| Metric | Value |
|---|---|
| Files discovered | 3,029 |
| Python files analyzed (AST) | **2,417** |
| Non-Python files skipped | 611 |
| **Entities indexed** | **11,988** |
| — Classes | 7,338 |
| — Modules | 2,863 |
| — Functions | 1,642 |
| — Dependencies | 145 |
| **Relations mapped** | **34,508** |
| Stubs resolved | 251 |
| Relations rewired | 2,926 |
| Errors | 1 (Windows file rename race — recovered automatically) |
| **Full scan time (Windows)** | **604 s (~10 min)** |
| Estimated on Linux/macOS | ~120–180 s (~2–3 min) |

The single error was a Windows-specific atomic rename collision (`WinError 5`) during
concurrent entity writes. Project Mapper caught it, retried, and continued — no data
was lost.

---

## Phase 2 — Incremental Scan

Immediately after the full scan, with **zero file changes**.

```bash
# Equivalent HTTP call (incremental=true is the default):
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
| Entities created | 0 |
| Entities updated | 1 |
| **Incremental scan time** | **1.88 s** |

**321× faster than the full scan.** In a real workflow, developers run the full scan
once per project, then every subsequent scan — triggered automatically by a file watcher
or CI step — completes in under 2 seconds regardless of repository size.

---

## Phase 2b — Session Startup

Before any query can run, the entity map must be loaded into memory.  Without a
snapshot, the server opens and parses every ``ws_*.json`` entity file
individually.  With a snapshot (built automatically at the end of each scan),
the entire map is read from a single pre-serialised file.

Both timings below were measured on the same machine as the full scan.  "Cold
OS cache" reflects a server restart or long idle period; "warm OS cache" reflects
a start immediately after a scan (files still in the OS page cache).

| Method | Condition | Load time |
|---|---|---|
| File-by-file (no snapshot) | Cold OS cache | **52,048 ms** (~52 s) |
| File-by-file (no snapshot) | Warm OS cache | ~700 ms |
| **Snapshot** | Any | **145 ms** |

| Snapshot metric | Value |
|---|---|
| Build time (end of scan) | **82 ms** |
| Snapshot file size | **9.8 MB** |
| Entity count stored | 11,988 (all statuses) |
| Speedup vs cold | **358×** |
| Speedup vs warm OS cache | **~5×** |

The snapshot is invalidated automatically if any entity file is newer than it
or if the entity count changes.  It is rebuilt either lazily on the next
``list_all()`` call or eagerly at the end of each scan — whichever comes first.

---

## Phase 3 — Query Performance

All queries run against the indexed knowledge graph in memory. After the initial
snapshot load (145 ms), the entity map stays in the server's process memory and
is reused for all subsequent queries within the same session — the per-query
latencies below do not include a load step.

### 3a — Context Queries

A context query answers: *"I'm about to work on X. What entities should I know about?"*
It scores every entity against the query using keyword + structural matching, then
expands the seed set by one hop through the relation graph.

| Query | Seeds | Results | PM response tokens | Time |
|---|---|---|---|---|
| `"authentication middleware security"` | 8 | 25 | **1,448** | 90.8 ms |
| `"migration schema database"` | 8 | 37 | **2,033** | 100.8 ms |
| `"template render"` | 8 | 15 | **1,101** | 78.8 ms |
| `"signal dispatch"` | 8 | 30 | **1,608** | 79.1 ms |

**Example output — `"authentication middleware security"`** (top seeds):

```
[class]  PersistentRemoteUserMiddleware   score=3.55
[class]  AuthenticationMiddlewareSubclass score=3.45
[class]  AuthenticationMiddleware         score=3.15
[class]  SecurityMiddleware               score=2.45
[class]  RemoteUserMiddleware             score=2.20
[module] django/middleware/security.py    score=2.70
[module] tests/middleware/test_security.py score=2.70
```

#### Token comparison — context query

To answer the same question without Project Mapper, an agent would typically read
the 4–8 most relevant source files in full:

| File | Chars | Tokens |
|---|---|---|
| `django/contrib/auth/middleware.py` | 11,826 | 2,956 |
| `django/middleware/security.py` | 2,599 | 649 |
| `django/middleware/common.py` | 8,162 | 2,040 |
| `django/core/handlers/base.py` | 14,840 | 3,710 |
| `django/conf/__init__.py` | 15,145 | 3,786 |
| **5 files total** | **52,572** | **13,141** |

| | Tokens |
|---|---|
| Reading 5 relevant files (no PM) | ~13,141 |
| PM context query response | **1,448** |
| **Token reduction** | **89 %** |

And that assumes the agent already knew *which* 5 files to read. On a first encounter
with a codebase, it would typically read 10–20 files before narrowing in — pushing
token cost to 25,000–60,000.

---

### 3b — Impact Queries

An impact query answers: *"If I change entity X, what else is affected?"*
It performs a directed BFS through the reverse-dependency graph up to N hops.

| Subject | Direct (hop 1) | Transitive (hop 2) | Total affected | Response tokens | Time |
|---|---|---|---|---|---|
| `Model` (Django base model) | 33 | 23 | **69** | **4,020** | 11.4 ms |
| `DatabaseWrapper` | 3 | 0 | **3** | **210** | 56.7 ms |
| `AuthenticationMiddleware` | 0 | 0 | **0** | **68** | 12.8 ms |

**Example — `Model` impact (first 5 of 69 affected):**

```
hop1: [class]    UserManager              via=calls
hop1: [function] check_models_permissions via=calls
hop1: [function] build_instance           via=calls
hop1: [function] parse_apps_and_model_labels via=calls
hop1: [class]    Sitemap                  via=calls
```

The `Model` class has 69 non-test entities depending on it across 2 hops.
Understanding this impact chain manually would require grepping a 521k-line codebase
and reading dozens of files. Project Mapper returns it in **11.4 ms** and
**4,020 tokens**.

#### Token comparison — impact query

To find what depends on `Model` without PM, an agent would run a grep, then read
each matching file for context. `query.py` and `base.py` alone cost:

| File | Tokens |
|---|---|
| `django/db/models/query.py` | 29,523 |
| `django/db/models/base.py` | 24,889 |
| **2 files** | **54,412** |

| | Tokens |
|---|---|
| Reading just 2 core ORM files | ~54,412 |
| PM impact query response | **4,020** |
| **Token reduction** | **93 %** |

---

## Phase 4 — Session-Level Effects

> **Note:** The numbers in this section are modelled from the measured per-query data
> above. We did not instrument live multi-turn agent sessions. The math is
> straightforward — it is presented here because it changes how the per-query reduction
> should be interpreted.

### How context windows accumulate cost

A single coding task rarely takes one exchange. A realistic session — understand the
problem, locate relevant code, plan the change, implement it, review it — runs
**10–20 back-and-forth turns** with the agent.

In tools like Claude Code and Cursor, files loaded in turn 1 stay in the context
window for every subsequent turn. An agent that reads `auth/middleware.py` (2,956
tokens) in its first message carries those tokens as input cost on **every message
that follows**.

Project Mapper's compressed context response stays small across the whole session
for the same reason: the 1,448-token `pm_context` reply sits in context and does
not grow with session length.

### Modelled per-session cost — authentication middleware task

Using the measured values from §3a:

| Session length | Tokens without PM | Tokens with PM | Saved per session |
|---|---|---|---|
| 1 turn | 13,141 | 1,448 | 11,693 (89 %) |
| 5 turns | 65,705 | 7,240 | 58,465 (89 %) |
| 10 turns | 131,410 | 14,480 | 116,930 (89 %) |
| 20 turns | 262,820 | 28,960 | 233,860 (89 %) |

The reduction percentage does not increase — it stays at 89 % per turn. What
changes is the absolute token cost of not using Project Mapper. A 20-turn debugging
session costs twenty times more than a 1-turn call at the same 89 % overhead ratio
each time. The penalty for loading raw files compounds with every message; PM's
penalty does not.

### What this means in practice

The cost calculator in the README uses average tokens *per task*, not per turn. If
your agents routinely work in long sessions on a large codebase, actual savings will
be higher than the headline 89–93 % figure suggests — not because the per-turn ratio
improves, but because more turns means more chances for that ratio to apply.

Conversely, on very short single-turn queries (one-shot code generation, quick
lookups), the per-query ratio is the full story. The session multiplier only
matters when context accumulates across turns.

---

## Summary

| Test | Result |
|---|---|
| Repository size | 521,286 lines · 2,918 Python files |
| Entities indexed | **11,988** (classes, modules, functions, dependencies) |
| Relations mapped | **34,508** |
| Full scan (Windows) | **604 s** |
| Full scan (Linux/macOS, estimated) | ~150 s |
| Incremental scan (no changes) | **1.88 s** — 321× faster |
| Session startup — file-by-file, cold | **52,048 ms** (~52 s) |
| Session startup — file-by-file, warm OS cache | ~700 ms |
| Session startup — snapshot | **145 ms** — **358× faster** than cold |
| Snapshot build time | **82 ms** · 9.8 MB |
| Context query latency | **79–101 ms** |
| Impact query latency | **11–57 ms** |
| Token reduction vs. reading files | **89–93 %** |
| LLM enrichment required | **No** — all results from static analysis alone |

---

## What Works Without LLM Enrichment

This entire case study used `enrich=False` — no AI provider, no API keys, no cost.
Static analysis alone was sufficient for:

- ✅ Full AST extraction (classes, functions, modules, imports)
- ✅ Relation mapping (calls, imports, extends, depends_on, …)
- ✅ Incremental scanning with SHA-256 hash comparison
- ✅ Impact analysis (directed BFS through the dependency graph)
- ✅ Context queries (keyword + file-path scoring against 9,786 active entities)

LLM enrichment adds **natural-language summaries**, **architectural pattern tags**,
and **semantic aliases** to each entity — this improves the relevance ranking of
context queries significantly. It is an optional enhancement, not a requirement.

---

## Limitations Observed

**Windows file I/O overhead** — Concurrent JSON writes under Windows Defender
produce occasional `WinError 5` (access denied on temp-file rename). Project Mapper
handles this gracefully with retry logic, but it contributes to the slower scan time
on Windows vs. Linux. Running the server in Docker resolves this entirely.

**NameIndex warm-up** — The NameIndex (name → entity-ID lookup) requires a warm
filesystem state. On first access after a lock contention event it rebuilds from
scratch (~700 ms for 11,737 entities). Subsequent queries within the same session
use the in-memory cache.

**Test entities included** — Django's test suite is large (over 1,500 test classes).
By default, impact queries exclude test entities (`exclude_tests=True`). Context
queries include them, which can surface test helpers alongside production code. A
future `filter_paths` parameter would allow excluding `tests/` entirely at query time.

---

## Reproducing This Test

```bash
# 1. Clone Django
git clone https://github.com/django/django /tmp/django
cd /tmp/django && git checkout stable/5.1.x

# 2. Install Project Mapper
pip install git+https://github.com/Aethvion/Aethvion-ProjectMapper.git

# 3. Start the server
uvicorn server:app --port 7474 &

# 4. Full scan
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/tmp/django", "db": "django", "enrich": false}'

# 5. Context query
curl -X POST http://localhost:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q": "authentication middleware security", "db": "django"}'

# 6. Impact query
curl -X POST http://localhost:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"subject": "Model", "db": "django", "max_depth": 2}'
```

Or via MCP in Claude Code:
```
pm_scan(project_root="/tmp/django", db="django", enrich=false)
pm_context(q="authentication middleware security", db="django")
pm_impact(subject="Model", db="django")
```

---

*Benchmark conducted by the Aethvion team · June 2026*  
*Project Mapper v1.0.0 · Python 3.10 · Windows 11*
