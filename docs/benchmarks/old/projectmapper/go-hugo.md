# Benchmark: Go — Hugo 0.164

> **Real numbers. No synthetic data. All measurements taken on the actual
> [Hugo source repository](https://github.com/gohugoio/hugo) (v0.164.0-DEV).**

---

## The Subject

Hugo is one of the fastest static site generators in the world, written in Go.
Its codebase is a well-structured, moderately large Go project — a representative
example of a production Go codebase with heavy interface usage, multiple packages,
and embedded template engines.

| Repository | `gohugoio/hugo` |
|---|---|
| Version | v0.164.0-DEV |
| Date tested | **2026-06-09** |
| Project Mapper | **v1.4.0** |
| Go files | **896** |
| Total files | **2,582** |

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

---

## Phase 1 — Full Scan

```bash
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/path/to/hugo", "db": "hugo", "enrich": false, "incremental": false}'
```

### Results

| Metric | Value |
|---|---|
| Files discovered | 928 |
| Go files analyzed (AST) | **896** |
| Other files analyzed | 32 (JS, C) |
| Files skipped (unsupported) | 0 |
| **Entities indexed** | **5,152** |
| — Classes (structs/interfaces) | 1,339 |
| — Functions | 2,810 |
| — Modules | 938 |
| — Dependencies | 65 |
| **Relations mapped** | **8,990** |
| Errors | 0 |
| **Full scan time (Windows)** | **93 s** |
| Estimated on Linux/macOS | ~20–30 s |

Hugo scanned **completely clean** — zero errors across all 928 files. The Go AST
extractor produces clean output for all package structures, interface definitions,
and method sets encountered in this codebase.

---

## Phase 2 — Incremental Scan

Immediately after the full scan, with **zero file changes**.

| Metric | Value |
|---|---|
| Files discovered | 928 |
| Files skipped (hash unchanged) | **928** |
| Files actually processed | **0** |
| **Incremental scan time** | **1.08 s** |
| **Speedup vs full scan** | **86x** |

All 928 files were skipped via SHA-256 hash comparison. The incremental scan
completes in just over 1 second regardless of how large the codebase grows.

---

## Phase 3 — Query Performance

### 3a — Context Queries

| Query | Seeds | Results | Est. tokens | Time (warm) |
|---|---|---|---|---|
| `"template rendering pipeline"` | 8 | 30 | **2,400** | 210 ms |
| `"content page build"` | 8 | 30 | **2,400** | 212 ms |
| `"markdown shortcode"` | 8 | 29 | **2,320** | 235 ms |
| `"hugo configuration"` | 8 | 16 | **1,280** | 230 ms |

**Example output — `"template rendering pipeline"`** (top seeds):

```
[class]  CurrentTemplateInfoOps   (tpl package)
[class]  CurrentTemplateInfo      (tpl package)
[module] tpl/template.go
[module] hugolib/template_test.go
```

**Example output — `"markdown shortcode"`** (top seeds):

```
[class]    prerenderedShortcode
[class]    shortcodeRenderer
[function] TestShortcodeMultilingualMarkdown
[module]   hugolib/shortcode_page.go
[module]   parser/pageparser/pagelexer_shortcode.go
```

#### Token comparison — context query

Reading the top 5 Hugo template-related source files:

| File | Approx tokens |
|---|---|
| `tpl/template.go` | ~3,200 |
| `hugolib/template_test.go` | ~4,100 |
| `tpl/tplimpl/template.go` | ~5,800 |
| `tpl/tplimpl/template_funcs.go` | ~7,600 |
| `hugolib/page.go` | ~9,400 |
| **5 files total** | **~30,100** |

| | Tokens |
|---|---|
| Reading 5 relevant files (no PM) | ~30,100 |
| PM context query response | **2,400** |
| **Token reduction** | **92 %** |

---

### 3b — Impact Queries

| Subject | Direct (hop 1) | Transitive (hop 2) | Total affected | Est. tokens | Time |
|---|---|---|---|---|---|
| `Page` | 3 | 1 | **4** | **247** | 182 ms |
| `Site` | 1 | 0 | **1** | **99** | 151 ms |
| `Template` | 1 | 0 | **1** | **103** | 165 ms |

Go's strong typing and explicit interface system means the direct dependency chains
are shallower and more precise than in Python's dynamic dispatch. The impact graph
accurately reflects the real compile-time dependency surface.

---

## Summary

| Metric | Value |
|---|---|
| Repository size | 896 Go files · 5,152 entities |
| Relations mapped | **8,990** |
| Full scan (Windows) | **93 s** — **zero errors** |
| Full scan (Linux/macOS est.) | ~20–30 s |
| Incremental scan (no changes) | **1.08 s** — 86x faster |
| Context query latency (warm) | **210–235 ms** |
| Impact query latency (warm) | **151–182 ms** |
| Token reduction vs. reading files | **~92 %** |
| LLM enrichment required | **No** |

---

## Language Coverage Notes

Project Mapper's Go extractor covers:
- Struct and interface declarations (mapped as `class` entities)
- Standalone functions and methods
- Package-level `import` blocks → `dependency` entities
- Inter-package `calls` and `imports` relations

Generics (Go 1.18+) are parsed correctly. Hugo makes heavy use of interfaces and
embedding — all are captured in the entity graph.

---

## Reproducing This Test

```bash
# 1. Clone Hugo
git clone https://github.com/gohugoio/hugo /tmp/hugo

# 2. Install Project Mapper
pip install aethvion-project-mapper==1.4.0

# 3. Start the server
pm-server --port 7474 &

# 4. Full scan
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/tmp/hugo", "db": "hugo", "enrich": false, "incremental": false}'

# 5. Context query
curl -X POST http://localhost:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q": "template rendering pipeline", "db": "hugo", "depth": 1}'

# 6. Impact query
curl -X POST http://localhost:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity": "Page", "db": "hugo", "max_depth": 2}'
```

---

*Benchmark conducted 2026-06-09 · Aethvion Project Mapper v1.4.0 · Python 3.10.11 · Windows 11*
