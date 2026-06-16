# Benchmark: TypeScript/JS — Zod

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `colinhacks/zod` |
| Language | TypeScript |
| Files scanned | 406 |
| Total lines | ~74,000 |
| Entities indexed | 1,688 |
| Scan time | 4.5 s |
| Throughput | ~16,500 lines/sec |

Geometric mean savings: **~87% token reduction (Full) · ~90% token reduction (Slim)** · **~1,071× faster navigation**

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + read tokens a skilled agent
would spend reaching the same answer without Project Mapper.

---

## Test 1 — Complete Schema Type Catalog

**Question:** *"What schema types does Zod provide?"*

**Standard Workflow (Grep + Read):** `grep -r "extends ZodType"` across `packages/zod/src/v3/`, `v4/classic/`, and `v4/mini/`. Identifies multiple large TypeScript files (schemas.ts, types.ts) in each sub-package. 8–12 reads across the monorepo; v4-specific numeric formats (`ZodInt32`, `ZodFloat64`), `ZodCodec`, and `ZodTemplateLiteral` routinely missed. ~15,000 tokens.

**With Project Mapper:** `pm_impact "ZodType" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 8–12 | 1 | 1 |
| Entities found | ~35–40, misses v4 additions + mini variants | 54 — complete, all versions | 54 — complete |
| Token Cost | ~15,000 | ~2,462 | ~2,082 |
| Token Reduction | — | **−84%** | **−86%** |
| Execution Time | ~8s | 1ms | 1ms |
| Speedup | — | **~8,000×** | **~8,000×** |

---

## Test 2 — Validation Error Type Catalog

**Question:** *"What validation error (issue) types does Zod produce?"*

**Standard Workflow (Grep + Read):** Read the v4 issue definitions file and the v3 issues file. Each is ~500–800 lines. v3 and v4 issue types have different shapes but overlap — easy to conflate or miss types defined inline. 2–3 reads, ~3,500 tokens.

**With Project Mapper:** `pm_impact "ZodIssueBase" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 2–3 | 1 | 1 |
| Entities found | Partial, v3/v4 shape differences cause confusion | 16 — complete, canonical list | 16 — complete |
| Token Cost | ~3,500 | ~549 | ~469 |
| Token Reduction | — | **−84%** | **−87%** |
| Execution Time | ~2s | 1ms | 1ms |
| Speedup | — | **~2,000×** | **~2,000×** |

---

## Test 3 — Union & Discriminated Union Types

**Question:** *"What union-related schema types does Zod provide, and where are they defined?"*

**Standard Workflow (Grep + Read):** Read `ZodUnion` and `ZodDiscriminatedUnion` in v4 classic, then check v4 mini and v3 for equivalents. Internal `$ZodUnionDef`/`$ZodUnionInternals` types never surface from a file read. 3–5 reads, ~5,000 tokens.

**With Project Mapper:** `pm_context "union discriminated intersection"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–5 | 1 | 1 |
| Entities found | Partial, internal Def/Internals types always missed | 19 ranked — incl. internals + mini variants | 19 ranked — complete |
| Token Cost | ~5,000 | ~773 | ~495 |
| Token Reduction | — | **−85%** | **−90%** |
| Execution Time | ~4s | 11ms | 11ms |
| Speedup | — | **~364×** | **~364×** |

---

## Test 4 — Coercion & Transform Types

**Question:** *"What coercion and transform types does Zod provide, and where do they live in the monorepo?"*

**Standard Workflow (Grep + Read):** `grep -r "coerce\|preprocess"` across all packages. Finds `v4/classic/coerce.ts`, `v4/mini/coerce.ts`, `v3/` coerce files, and ZodEffects for transforms. 4–5 reads across packages, ~5,000 tokens. `v4/mini/coerce.ts` easily overlooked.

**With Project Mapper:** `pm_context "transform coerce preprocess"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–5 | 1 | 1 |
| Entities found | Partial, v4/mini/coerce.ts easily overlooked | 19 ranked — all 3 API surfaces mapped | 19 ranked — complete |
| Token Cost | ~5,000 | ~803 | ~517 |
| Token Reduction | — | **−84%** | **−90%** |
| Execution Time | ~4s | 11ms | 11ms |
| Speedup | — | **~364×** | **~364×** |

---

## Test 5 — ZodEffects Inheritance Path

**Question:** *"Is ZodEffects (transforms/refinements) a proper schema type — does it participate in the full ZodType pipeline?"*

**Standard Workflow (Grep + Read):** Find where `ZodEffects` is defined across the monorepo. It lives inside a large schemas or types file. Read that file (~2,000+ lines) to locate the class declaration and confirm `extends ZodType`. Even targeted: ~2,000 tokens.

**With Project Mapper:** `pm_path from_entity="ZodEffects" to_entity="ZodType"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 2–3 | 1 | 1 |
| Entities found | Requires reading a large file | 1-hop confirmed | 1-hop confirmed |
| Token Cost | ~2,000 | ~30 | ~30 |
| Token Reduction | — | **−98%** | **−98%** |
| Execution Time | ~2s | 3ms | 3ms |
| Speedup | — | **~667×** | **~667×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Schema type catalog | ~15,000 tok | ~2,462 tok | ~2,082 tok | **−84%** | **−86%** | ~8,000× |
| Test 2 | Validation error types | ~3,500 tok | ~549 tok | ~469 tok | **−84%** | **−87%** | ~2,000× |
| Test 3 | Union & discriminated union | ~5,000 tok | ~773 tok | ~495 tok | **−85%** | **−90%** | ~364× |
| Test 4 | Coercion & transform types | ~5,000 tok | ~803 tok | ~517 tok | **−84%** | **−90%** | ~364× |
| Test 5 | ZodEffects inheritance | ~2,000 tok | ~30 tok | ~30 tok | **−98%** | **−98%** | ~667× |

---

Geometric mean savings: **~87% token reduction (Full) · ~90% token reduction (Slim)** · **~1,071× faster navigation**

> T1 completeness is the headline: without PM, cataloguing all Zod schema types across v3, v4 classic, and v4 mini routinely stops short — missing v4-specific numeric formats, `ZodCodec`, and `ZodTemplateLiteral`. T5's −98% reduction confirms one inheritance relationship in 30 tokens vs reading a 2,000-line file. Zod's monorepo structure (three parallel API surfaces) is exactly the scenario where PM's cross-file entity graph pays off most.

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/colinhacks/zod /path/to/zod

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/zod" db="zod" incremental=false

# Test 1
pm_impact entity="ZodType" db="zod" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 2
pm_impact entity="ZodIssueBase" db="zod" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 3
pm_context query="union discriminated intersection" db="zod"

# Test 4
pm_context query="transform coerce preprocess" db="zod"

# Test 5
pm_path from_entity="ZodEffects" to_entity="ZodType" db="zod"
```
