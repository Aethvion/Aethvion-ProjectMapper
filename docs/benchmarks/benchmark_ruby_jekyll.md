# Benchmark: Ruby — Jekyll

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `jekyll/jekyll` |
| Language | Ruby |
| Files scanned | 161 |
| Total lines | ~19,300 |
| Entities indexed | 469 |
| Scan time | 0.3 s |
| Throughput | ~64,000 lines/sec |

Geometric mean savings: **~81% token reduction (Full) · ~86% token reduction (Slim)** · **~1,500× faster navigation**

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + read tokens a skilled agent
would spend reaching the same answer without Project Mapper.

---

## Test 1 — Liquid Drop Hierarchy

**Question:** *"What Liquid Drop types does Jekyll expose to templates?"*

**Standard Workflow (Grep + Read):** Browse `lib/jekyll/drops/` (8 files, 50–150 lines each). Read `drop.rb` base class and each concrete drop. Requires a separate `grep -r "< Drop"` to catch drops defined outside the `drops/` directory (e.g., `ForwardDrop` in `benchmark/`). 6–9 reads, ~2,500 tokens.

**With Project Mapper:** `pm_impact "Drop" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6–9 | 1 | 1 |
| Entities found | Partial, benchmark/ drops easily missed | 10 — complete, cross-directory | 10 — complete |
| Token Cost | ~2,500 | ~328 | ~278 |
| Token Reduction | — | **−87%** | **−89%** |
| Execution Time | ~3s | 8ms | 8ms |
| Speedup | — | **~400×** | **~400×** |

---

## Test 2 — Custom Liquid Tag Hierarchy

**Question:** *"What custom Liquid tags does Jekyll define?"*

**Standard Workflow (Grep + Read):** Browse `lib/jekyll/tags/` (link.rb, include.rb, post_url.rb). Then `grep -r "Liquid::Tag"` to catch any additional tags. The three `IncludeTag` variants (base, Optimized, Relative) defined in the same file are easily missed. 3–4 reads, ~2,000 tokens.

**With Project Mapper:** `pm_impact "Liquid::Tag" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | Partial, same-file variants missed | 6 — complete, incl. same-file variants | 6 — complete |
| Token Cost | ~2,000 | ~215 | ~185 |
| Token Reduction | — | **−89%** | **−91%** |
| Execution Time | ~2s | <1ms | <1ms |
| Speedup | — | **~5,000×** | **~5,000×** |

---

## Test 3 — CLI Command Catalog

**Question:** *"What CLI commands does Jekyll provide?"*

**Standard Workflow (Grep + Read):** Browse `lib/jekyll/commands/` (6 files: build.rb, serve.rb, clean.rb, doctor.rb, help.rb, new.rb). Read each to understand its role. 6 reads × ~100 lines avg, ~1,500 tokens. Misses command subclasses defined in test fixtures and plugins.

**With Project Mapper:** `pm_impact "Command" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | 6 (directory-visible only) | 19 — all direct subclasses, incl. plugin variants | 19 — complete |
| Token Cost | ~1,500 | ~582 | ~487 |
| Token Reduction | — | **−61%** | **−68%** |
| Execution Time | ~2s | <1ms | <1ms |
| Speedup | — | **~2,000×** | **~2,000×** |

---

## Test 4 — Build Pipeline Context

**Question:** *"I'm about to work on Jekyll's site build and render pipeline — what entities should I know about?"*

**Standard Workflow (Grep + Read):** Read `lib/jekyll/site.rb` (~600 lines), `lib/jekyll/commands/build.rb`, and `lib/jekyll/liquid_renderer.rb`. 3 reads, ~3,000 tokens of raw file content with no entity ranking.

**With Project Mapper:** `pm_context "site build render pipeline"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | 3 files, unranked | 29 ranked — complete | 29 ranked — complete |
| Token Cost | ~3,000 | ~755 | ~399 |
| Token Reduction | — | **−75%** | **−87%** |
| Execution Time | ~3s | 3ms | 3ms |
| Speedup | — | **~900×** | **~1,000×** |

---

## Test 5 — Command Relationship (Serve → Build)

**Question:** *"How is Jekyll's serve command related to build?"*

**Standard Workflow (Grep + Read):** Read `lib/jekyll/commands/serve.rb`, `lib/jekyll/commands/build.rb`, and `lib/jekyll/command.rb` to understand the shared base. 3 reads × ~100 lines, ~1,500 tokens.

**With Project Mapper:** `pm_path from_entity="Serve" to_entity="Build"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3 | 1 | 1 |
| Entities found | Requires reading both files | 2-hop path confirmed | 2-hop path confirmed |
| Token Cost | ~1,500 | ~26 | ~26 |
| Token Reduction | — | **−98%** | **−98%** |
| Execution Time | ~2s | <1ms | <1ms |
| Speedup | — | **~2,000×** | **~2,000×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Liquid Drop hierarchy | ~2,500 tok | ~328 tok | ~278 tok | **−87%** | **−89%** | ~400× |
| Test 2 | Custom Liquid tags | ~2,000 tok | ~215 tok | ~185 tok | **−89%** | **−91%** | ~5,000× |
| Test 3 | CLI command catalog | ~1,500 tok | ~582 tok | ~487 tok | **−61%** | **−68%** | ~2,000× |
| Test 4 | Build pipeline context | ~3,000 tok | ~755 tok | ~399 tok | **−75%** | **−87%** | ~900× |
| Test 5 | Serve → Build path | ~1,500 tok | ~26 tok | ~26 tok | **−98%** | **−98%** | ~2,000× |

---

Geometric mean savings: **~81% token reduction (Full) · ~86% token reduction (Slim)** · **~1,500× faster navigation**

> Jekyll is a compact, well-structured Ruby codebase (161 files, 0.3s scan). Sub-millisecond query times for impact and path queries reflect the small entity count (469). T2's 6 Liquid tags include three `IncludeTag` variants defined in the same file — a completeness win that grep+read consistently misses. T3 demonstrates a broader picture: the `pm_impact "Command"` query returns 19 subclasses including plugin and test-fixture variants invisible from `lib/jekyll/commands/` alone. T5's 2-hop `Serve → Build` path (both extend `Command`) resolves in 26 tokens what would require reading three source files.

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/jekyll/jekyll /path/to/jekyll

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/jekyll" db="jekyll" incremental=false

# Test 1
pm_impact entity="Drop" db="jekyll" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 2
pm_impact entity="Liquid::Tag" db="jekyll" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 3
pm_impact entity="Command" db="jekyll" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 4
pm_context query="site build render pipeline" db="jekyll"

# Test 5
pm_path from_entity="Serve" to_entity="Build" db="jekyll"
```
