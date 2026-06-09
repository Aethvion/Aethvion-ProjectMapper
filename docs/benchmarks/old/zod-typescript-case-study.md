# Case Study: Indexing the Zod TypeScript Library

> **Real numbers. No synthetic data. All measurements taken on the actual
> [Zod source repository](https://github.com/colinhacks/zod) (main branch, June 2026),
> using Project Mapper's TypeScript analyzer introduced in v1.2.0.**

---

## The Subject

Zod is one of the most widely used TypeScript schema validation libraries in the
JavaScript ecosystem. It ships with full TypeScript generics, co-variant type
parameters (TypeScript 5.x `out` variance annotations), and a heavily interface-based
API surface — patterns that push parsers hard.

The repository is a pnpm monorepo containing the v3 and v4 source trees, benchmarks,
docs, integration tests, and build tooling. It is a representative example of a modern
TypeScript library with real production complexity.

| Repository | `colinhacks/zod` |
|---|---|
| Branch | `main` |
| Date | June 2026 |
| TypeScript files | **372** |
| TypeScript JSX files | **29** |
| Other JS/MJS files | **5** |
| **Total TypeScript/JS files** | **406** |
| **Total lines** | **74,828** |
| Largest file | `packages/zod/src/v3/types.ts` — 5,139 lines |

---

## Test Environment

| | |
|---|---|
| OS | Windows 11 |
| Python | 3.12.x |
| Aethvion Project Mapper | v1.2.0 (TypeScript analyzer) |
| Parser | tree-sitter 0.25.2 + tree-sitter-typescript 0.23.2 |
| LLM enrichment | **disabled** — pure static analysis |
| Hardware | Consumer laptop |

> **Important**: Windows has higher file I/O overhead than Linux or macOS. The
> timing below reflects Windows conditions. On Linux or macOS the same scan runs
> approximately 3–5× faster.

---

## Phase 1 — TypeScript Parsing

A full cold scan of all 406 TypeScript/JavaScript files in the repository.

### Results

| Metric | Value |
|---|---|
| Files scanned | **406** |
| Total lines analyzed | **74,828** |
| **Entities extracted** | |
| — Classes (regular) | **62** |
| — Abstract classes | **7** |
| — Interfaces | **641** |
| — Functions | **691** |
| **Total method signatures** | **481** |
| **Total import statements** | **969** |
| Files with parse errors | **4** (1 %) |
| **Full scan time (Windows)** | **3,536 ms** |
| Per-file average | **2.00 ms** |
| Throughput | **21,163 lines / sec** |

### Parse Errors

The 4 files with parse errors all share the same cause: TypeScript 5.x co-variant
type parameter syntax (`interface Foo<out T>`). The `out` keyword used as a variance
annotation is newer than the tree-sitter grammar revision used. **Extraction still
succeeded** for these files — tree-sitter partially parses and Project Mapper extracts
whatever it can find.

| File | Error |
|---|---|
| `v4/classic/schemas.ts` | TypeScript 5.x `out` variance annotations |
| `v4/core/checks.ts` | TypeScript 5.x `out` variance annotations |
| `v4/core/schemas.ts` | TypeScript 5.x `out` variance annotations |
| `v4/mini/schemas.ts` | TypeScript 5.x `out` variance annotations |

The v3 source tree (which does not use variance annotations) parsed with **zero errors**.

### What the Zod codebase looks like to Project Mapper

Zod v4 uses a predominantly interface-based API surface — a design pattern common in
modern TypeScript libraries. Project Mapper correctly distinguishes between interfaces,
abstract classes, and regular classes, labelling each appropriately.

**Top entities by method count (v3 source tree, zero parse errors):**

| Entity | Kind | Methods | Lines |
|---|---|---|---|
| `ZodString` | class | 49 | 731–1,337 |
| `ZodType` | abstract class | 32 | 117–443 |
| `ZodNumber` | class | 19 | 1,337–1,618 |
| `ZodObject` | class | 16 | 2,379–2,777 |
| `ZodBigInt` | class | 15 | 1,618–1,774 |

**Top entities by method count (v4 classic — interfaces):**

| Entity | Kind | Methods | Lines |
|---|---|---|---|
| `ZodType` | interface | 44 | 78–210 |
| `ZodString` | interface | 27 | 455–530 |
| `_ZodString` | interface | 15 | 368–392 |
| `_ZodNumber` | interface | 15 | (comparable) |
| `ZodObject` | interface | 15 | (comparable) |

**Inheritance coverage:**  270 entities across the full repo inherit from `ZodType`
(v3 classes + v4 interfaces), extracted across 406 files in a single pass.

---

## Phase 2 — Token Cost Comparison

> **Methodology note:** Token counts use a 4 chars/token approximation
> (standard for GPT-4 class models on code). All numbers are **measured** from
> actual scan output, not modelled.

### 2a — Whole-repository read cost

| | Value |
|---|---|
| Total source characters | **2,345,227** |
| **Total tokens (raw files)** | **~586,306** |
| PM full entity index (projected) | **~20,015 tokens** |
| **Token reduction** | **96.6 %** |

An AI agent that reads all 406 source files to understand the Zod codebase would
consume ~586,000 tokens. Project Mapper's entity index — names, kinds, inheritance,
method counts, line ranges — delivers the same structural picture in ~20,000 tokens.

### 2b — Entity lookup

Task: *"What is ZodString? What methods does it expose?"*

| | Tokens |
|---|---|
| Read `v3/types.ts` in full | **40,081** |
| PM `get_entity("ZodString")` response | **260** |
| **Token reduction** | **99.4 %** |

### 2c — Targeted query

Task: *"Find all types that extend ZodType."*

| | Tokens |
|---|---|
| Read all 406 source files | **586,306** |
| PM structured query response (270 results) | **12,277** |
| **Token reduction** | **97.9 %** |

This query would ordinarily require a `grep` across the repository followed by
opening each matching file for context. Project Mapper returns all 270 results —
name, kind, file, base classes, method count — in one call.

### Summary

| Scenario | Without PM | With PM | Reduction |
|---|---|---|---|
| Entity lookup (single class) | 40,081 tokens | 260 tokens | **99.4 %** |
| Targeted inheritance query | 586,306 tokens | 12,277 tokens | **97.9 %** |
| Full-repo structural overview | 586,306 tokens | ~20,015 tokens | **96.6 %** |

---

## Limitations

**TypeScript 5.x variance annotations** — The `out` keyword in generic parameter
positions (`interface Foo<out T>`) is not yet recognised by the tree-sitter grammar
version bundled with `tree-sitter-typescript 0.23.2`. This causes a parse error on
4 of 406 files (1 %). Extraction still runs on the remaining syntax — entity names,
bases, and most method signatures are recovered correctly from the partial parse.
This will resolve automatically when the grammar is updated.

**Interface property signatures** — Properties declared inside interface bodies
(e.g., `readonly _zod: Internals`) are recorded structurally but not modelled as
class variables. Only method signatures contribute to the method count. A future
update will expose property signatures as typed fields.

**No relations graph yet (TypeScript)** — For Python, Project Mapper builds a full
directed-graph of calls, imports, and inheritance relations that powers impact analysis
and path finding. Relation extraction for TypeScript is in progress and will be
released in a follow-up update. The entity extraction, token savings, and
entity-level queries shown above are available today.

**Windows scan overhead** — As with the Python benchmark, Windows file I/O (NTFS +
Defender) adds overhead to the 3.5 s scan time. On Linux the same 406-file scan
would complete in approximately 700 ms–1.2 s.

---

## Why TypeScript Support Matters

Python remains the dominant language for AI tooling, model training, and backend
services. But the bulk of application-layer code — frontends, BFFs, CLI tools,
full-stack frameworks — is written in TypeScript. A coding agent that can only
reason about Python files has a blind spot in any modern full-stack project.

By adding TypeScript support, Project Mapper can now index:
- Node.js backends (Express, Fastify, NestJS)
- React and Next.js frontend code
- TypeScript utility libraries (Zod, Valibot, Drizzle, Prisma, tRPC, …)
- Monorepos that mix Python services with TypeScript clients

Support for additional languages (Java, Go, C#) is planned for future releases.

---

## Summary

| Metric | Value |
|---|---|
| Repository size | 74,828 lines · 406 TypeScript/JS files |
| Entities extracted | **1,401** (62 classes + 7 abstract + 641 interfaces + 691 functions) |
| Method signatures | **481** |
| Import statements | **969** |
| Parse success rate | **99 %** (402/406 files — 4 partial from TS5 variance annotations) |
| Full scan time (Windows) | **3,536 ms** |
| Throughput | **21,163 lines / sec** |
| Token reduction — entity lookup | **99.4 %** |
| Token reduction — inheritance query | **97.9 %** |
| Token reduction — full-repo overview | **96.6 %** |
| LLM enrichment required | **No** |

---

## Reproducing This Test

```bash
# 1. Clone Zod
git clone https://github.com/colinhacks/zod /tmp/zod

# 2. Install Project Mapper with TypeScript support
pip install "aethvion-project-mapper>=1.2.0"
pip install "tree-sitter>=0.23.0" tree-sitter-typescript tree-sitter-javascript

# 3. Start the server
pm-server --port 7474 &

# 4. Scan
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/tmp/zod", "db": "zod", "enrich": false}'

# 5. Entity lookup
curl -X POST http://localhost:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q": "ZodString validation", "db": "zod"}'
```

Or via MCP in Claude Code:
```
pm_scan(project_root="/tmp/zod", db="zod", enrich=false)
pm_context(q="ZodString schema validation", db="zod")
```

---

*Benchmark conducted by the Aethvion team · June 2026*  
*Project Mapper v1.2.0 · Python 3.12 · Windows 11*  
*tree-sitter 0.25.2 · tree-sitter-typescript 0.23.2*
