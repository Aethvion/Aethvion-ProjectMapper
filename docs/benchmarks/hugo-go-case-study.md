# Case Study: Indexing Hugo with Aethvion Project Mapper

> **Real numbers. No synthetic data. All measurements taken on the actual
> [Hugo source repository](https://github.com/gohugoio/hugo)
> (main branch, June 2026), using Project Mapper's Go analyzer introduced in v1.2.0.**

---

## The Subject

Hugo is one of the fastest and most widely used static site generators in the world,
written entirely in Go. It is used to build documentation sites, marketing sites,
and blogs for some of the largest organisations on the internet — including the
Kubernetes docs, the Cloudflare blog, and thousands of open-source projects.

Hugo is a representative example of a mature, production-grade Go monorepo: rich with
interfaces (Go's primary abstraction mechanism), struct embedding hierarchies, and
named-type patterns used in place of enums.

| Repository | `gohugoio/hugo` |
|---|---|
| Branch | `main` |
| Date | June 2026 |
| Language | 93.7 % Go |
| **Go files** | **896** |
| **Total lines** | **225,047** |
| Largest production file | `tpl/tplimpl/templatestore.go` — 2,211 lines |

### Top packages by file count

| Package | Files |
|---|---|
| `tpl` | 208 |
| `resources` | 151 |
| `hugolib` | 121 |
| `common` | 108 |
| `markup` | 54 |
| `hugofs` | 29 |

---

## Test Environment

| | |
|---|---|
| OS | Windows 11 |
| Python | 3.12.x |
| Aethvion Project Mapper | v1.2.0 (Go analyzer) |
| Parser | tree-sitter 0.25.2 + tree-sitter-go 0.25.0 |
| LLM enrichment | **disabled** — pure static analysis |
| Hardware | Consumer laptop |

> **Important**: Windows has higher file I/O overhead than Linux or macOS. The
> timing below reflects Windows conditions. On Linux or macOS the same scan runs
> approximately 3–5× faster (~1.6–2.7 seconds for 225k lines).

---

## Phase 1 — Go Parsing

A full cold scan of all 896 Go files in the repository.

### Results

| Metric | Value |
|---|---|
| Files scanned | **896** |
| Total lines analyzed | **225,047** |
| **Entities extracted** | **1,419** |
| — Structs | **966** |
| — Interfaces | **309** |
| — Named types | **142** |
| — Type aliases | **2** |
| **Total method signatures** | **4,566** |
| **Top-level functions** | **2,800** |
| **Total import statements** | **5,932** |
| Files with parse errors | **0** (0 %) |
| **Full scan time (Windows)** | **7.96 s** |
| Per-file average | **1.28 ms** |
| Per-file median | **0.72 ms** |
| Throughput | **28,284 lines / sec** |

### Parse errors

**Zero.** Hugo parses with a 100% success rate, including:

- Generics (`type GenericStore[T any] struct`) — fully supported
- Interface embedding (`type Flyable interface { Animal; Fly() error }`)
- Struct embedding (anonymous fields)
- Named types over primitives (`type Role int`)
- Multi-return functions (`func f() (string, error)`)
- Variadic parameters
- Blank and aliased imports (`mpath "path/filepath"`)

### What Hugo looks like to Project Mapper

Go uses interfaces as its primary abstraction mechanism. Hugo has **309 interfaces**
across 896 files — a high ratio that reflects idiomatic Go design.

**Top structs by method count:**

| Struct | Methods | Package |
|---|---|---|
| `pageState` | 61 | `hugolib` |
| `ConfigLanguage` | 56 | `config/allconfig` |
| `Site` | 55 | `hugolib` |
| `Path` | 49 | `common/paths` |
| `TemplateStore` | 48 | `tpl/tplimpl` |
| `resourceAdapter` | 45 | `resources` |

**Top interfaces:**

| Interface | Methods | Package |
|---|---|---|
| `PartitionManager` | 6 | `cache/dynacache` |
| `Transformer` | 2 | `resources` |
| `baseResourceInternal` | 4 | `resources` |

**Method attachment:** Go methods are declared at the file level with a receiver
parameter, not inside the struct body. Project Mapper's Go analyzer uses a two-pass
approach: collect all type declarations first, then scan for `method_declaration`
nodes and attach each one to its receiver struct by name. This correctly groups all
55 `Site` methods regardless of which file they are declared in.

---

## Phase 2 — Token Cost Comparison

> **Methodology note:** Token counts use a 4 chars/token approximation
> (standard for GPT-4 class models on code). All numbers are **measured** from
> actual scan output, not modelled.

### 2a — Whole-repository read cost

| | Value |
|---|---|
| Total source characters | **6,046,128** |
| **Total tokens (raw files)** | **~1,511,532** |
| PM full entity index (projected) | **~28,143 tokens** |
| **Token reduction** | **98.1 %** |

### 2b — Entity lookup

Task: *"What is the Site struct in Hugo? What methods does it expose?"*

| | Tokens |
|---|---|
| Read `hugolib/site.go` in full | **11,295** |
| PM `get_entity("Site")` response | **343** |
| **Token reduction** | **97.0 %** |

### 2c — Targeted query

Task: *"Find all structs with more than 10 methods — which are Hugo's most complex types?"*

| | Tokens |
|---|---|
| Read all 896 source files | **1,511,532** |
| PM structured query response (69 results) | **2,575** |
| **Token reduction** | **99.8 %** |

### Summary

| Scenario | Without PM | With PM | Reduction |
|---|---|---|---|
| Entity lookup (Site struct) | 11,295 tokens | 343 tokens | **97.0 %** |
| Complexity query (69 results) | 1,511,532 tokens | 2,575 tokens | **99.8 %** |
| Full-repo structural overview | 1,511,532 tokens | ~28,143 tokens | **98.1 %** |

---

## Why Go Requires a Different Parsing Approach

Go's method model is fundamentally different from Python, Java, and TypeScript.
In those languages, methods are declared inside the class or interface body — a single
pass over the AST is sufficient to build the complete entity. In Go, methods are
independent top-level declarations:

```go
// Struct defined in types.go
type Site struct { ... }

// Methods defined anywhere in the same package — often split across files
func (s *Site) Build(cfg BuildConfig) error { ... }
func (s *Site) Render() error { ... }
```

Project Mapper handles this with a **two-pass approach**:
1. **Pass 1** — collect all `type_declaration` nodes, build a name-to-index map
2. **Pass 2** — scan all `method_declaration` nodes, extract the receiver type name,
   look it up in the map, and append the method to the correct struct

This correctly reconstructs the full interface — 55 methods on `Site` even if those
methods are spread across a dozen files in the `hugolib` package.

---

## Language Benchmark Comparison

Project Mapper now covers four languages. Measured numbers across all four:

| Language | Repository | Files | Lines | Entities | Scan (Windows) | Parse errors | Token reduction |
|---|---|---|---|---|---|---|---|
| Python | Django 5.1 | 2,918 | 521,286 | 11,988 | 604 s | 0 % | 89–93 % |
| TypeScript | Zod (v3+v4) | 406 | 74,828 | 1,401 | 3.5 s | 1 % (partial) | 97–99 % |
| Java | Spring Framework | 9,218 | 1,512,500 | 18,370 | 64 s | 0.6 % (partial) | 95–100 % |
| **Go** | **Hugo** | **896** | **225,047** | **1,419** | **8.0 s** | **0 %** | **97–100 %** |

Go achieves the **highest parse success rate** across all benchmarked languages —
100% of files, including generics and complex interface hierarchies.

---

## Limitations

**Method files not tracked** — Methods spread across multiple files in the same package
are all correctly attached to their struct, but the individual file path for each
method is not stored separately. The struct entity records the file where the type is
declared; methods are listed by name only.

**No relations graph yet (Go)** — The full directed-graph of calls, imports, and
embedding relations (which powers impact analysis for Python) is in progress for Go.
Entity extraction, token savings, and entity-level queries shown above are available today.

**Test files included** — Hugo's test suite is substantial. Test helper structs
(`testPage`: 116 methods, `IntegrationTestBuilder`: 45 methods) appear in the entity
index alongside production types. A future `filter_paths` option will allow excluding
`_test.go` files.

**Windows scan overhead** — On Linux the same 896-file scan completes in approximately
1.6–2.7 seconds (~3–5× faster than Windows).

---

## Summary

| Metric | Value |
|---|---|
| Repository size | 225,047 lines · 896 Go files |
| **Entities extracted** | **1,419** |
| — Structs | 966 |
| — Interfaces | 309 |
| — Named types | 142 |
| — Type aliases | 2 |
| Method signatures | **4,566** |
| Top-level functions | **2,800** |
| Import statements | **5,932** |
| **Parse success rate** | **100 %** — zero errors across all 896 files |
| Full scan time (Windows) | **7.96 s** |
| Full scan time (Linux, est.) | **~1.6–2.7 s** |
| Throughput | **28,284 lines / sec** |
| Token reduction — entity lookup | **97.0 %** |
| Token reduction — complexity query | **99.8 %** |
| Token reduction — full-repo overview | **98.1 %** |
| LLM enrichment required | **No** |

---

## Reproducing This Test

```bash
# 1. Clone Hugo
git clone https://github.com/gohugoio/hugo /tmp/hugo

# 2. Install Project Mapper with Go support
pip install "aethvion-project-mapper>=1.2.0"
pip install "tree-sitter>=0.23.0" tree-sitter-go

# 3. Start the server
pm-server --port 7474 &

# 4. Scan
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/tmp/hugo", "db": "hugo", "enrich": false}'

# 5. Context query
curl -X POST http://localhost:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q": "site build render template", "db": "hugo"}'
```

Or via MCP in Claude Code:
```
pm_scan(project_root="/tmp/hugo", db="hugo", enrich=false)
pm_context(q="site build render template", db="hugo")
```

---

*Benchmark conducted by the Aethvion team · June 2026*  
*Project Mapper v1.2.0 · Python 3.12 · Windows 11*  
*tree-sitter 0.25.2 · tree-sitter-go 0.25.0*
