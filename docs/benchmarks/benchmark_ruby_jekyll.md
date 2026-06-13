# Benchmark: Ruby — Jekyll

**PM version:** v1.8.0 · **Date:** 2026-06-13 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `jekyll/jekyll` |
| Language | Ruby |
| Files scanned | 161 |
| Total lines | ~14,000 |
| Entities indexed | 468 |
| Scan time | 0.4 s |
| Throughput | ~35,000 lines/sec |

Geometric mean savings: **−87% token reduction (Full) · −90% token reduction (Slim)** · **~2,000×+ faster navigation**

---

## Test 1 — Liquid Drop Hierarchy

**Question:** *"What Liquid Drop types does Jekyll expose to templates?"*

**Standard Workflow (Grep + Read):** Browse `lib/jekyll/drops/` (8 files, 50–150 lines each). Read `drop.rb` base class and each concrete drop. Requires a separate `grep -r "< Drop"` to catch drops defined outside the `drops/` directory (e.g., `ForwardDrop` in `benchmark/`). 6–9 reads, ~2,500 tokens.

**With Project Mapper:** `pm_impact "Drop" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6–9 | 1 | 1 |
| Entities found | Partial, benchmark/ drops easily missed | 10 — complete, cross-directory | 10 — complete |
| Token Cost | ~2,500 | ~252 | ~230 |
| Token Reduction | — | **−90%** | **−91%** |
| Execution Time | ~3s | <1ms | <1ms |
| Speedup | — | **~3,000×+** | **~3,000×+** |

---

## Test 2 — Custom Liquid Tag Hierarchy

**Question:** *"What custom Liquid tags does Jekyll define?"*

**Standard Workflow (Grep + Read):** Browse `lib/jekyll/tags/` (link.rb, include.rb, post_url.rb). Then `grep -r "Liquid::Tag"` to catch any additional tags. The three `IncludeTag` variants (base, Optimized, Relative) defined in the same file are easily missed. 3–4 reads, ~2,000 tokens.

**With Project Mapper:** `pm_impact "Liquid::Tag" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | Partial, same-file variants missed | 6 — complete, incl. same-file variants | 6 — complete |
| Token Cost | ~2,000 | ~169 | ~155 |
| Token Reduction | — | **−92%** | **−92%** |
| Execution Time | ~2s | <1ms | <1ms |
| Speedup | — | **~2,000×+** | **~2,000×+** |

---

## Test 3 — CLI Command Catalog

**Question:** *"What CLI commands does Jekyll provide?"*

**Standard Workflow (Grep + Read):** Browse `lib/jekyll/commands/` (6 files: build.rb, serve.rb, clean.rb, doctor.rb, help.rb, new.rb). Read each to understand its role. 6 reads × ~100 lines avg, ~1,500 tokens.

**With Project Mapper:** `pm_impact "Command" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | All (directory is obvious) | 6 — complete, with file paths | 6 — complete |
| Token Cost | ~1,500 | ~317 | ~286 |
| Token Reduction | — | **−79%** | **−81%** |
| Execution Time | ~2s | <1ms | <1ms |
| Speedup | — | **~2,000×+** | **~2,000×+** |

---

## Test 4 — Build Pipeline Context

**Question:** *"I'm about to work on Jekyll's site build and render pipeline — what entities should I know about?"*

**Standard Workflow (Grep + Read):** Read `lib/jekyll/site.rb` (~600 lines), `lib/jekyll/commands/build.rb`, and `lib/jekyll/liquid_renderer.rb`. 3 reads, ~3,000 tokens of raw file content with no entity ranking.

**With Project Mapper:** `pm_context "site build render pipeline"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | 3 files, unranked | 21 ranked — complete | 21 ranked — complete |
| Token Cost | ~3,000 | ~670 | ~353 |
| Token Reduction | — | **−78%** | **−88%** |
| Execution Time | ~3s | 3ms | 3ms |
| Speedup | — | **~1,000×** | **~1,000×** |

---

## Test 5 — Command Relationship (Serve → Build)

**Question:** *"How is Jekyll's serve command related to build?"*

**Standard Workflow (Grep + Read):** Read `lib/jekyll/commands/serve.rb`, `lib/jekyll/commands/build.rb`, and `lib/jekyll/command.rb` to understand the shared base. 3 reads × ~100 lines, ~1,500 tokens.

**With Project Mapper:** `pm_path from_entity="Serve" to_entity="Build"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3 | 1 | 1 |
| Entities found | Requires reading both files | 2-hop path confirmed | 2-hop path confirmed |
| Token Cost | ~1,500 | ~25 | ~25 |
| Token Reduction | — | **−98%** | **−98%** |
| Execution Time | ~2s | 1ms | 1ms |
| Speedup | — | **~2,000×** | **~2,000×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Liquid Drop hierarchy | ~2,500 tok | ~252 tok | ~230 tok | **−90%** | **−91%** | ~3,000×+ |
| Test 2 | Custom Liquid tags | ~2,000 tok | ~169 tok | ~155 tok | **−92%** | **−92%** | ~2,000×+ |
| Test 3 | CLI command catalog | ~1,500 tok | ~317 tok | ~286 tok | **−79%** | **−81%** | ~2,000×+ |
| Test 4 | Build pipeline context | ~3,000 tok | ~670 tok | ~353 tok | **−78%** | **−88%** | ~1,000× |
| Test 5 | Serve → Build path | ~1,500 tok | ~25 tok | ~25 tok | **−98%** | **−98%** | ~2,000× |

---

Geometric mean savings: **−87% token reduction (Full) · −90% token reduction (Slim)** · **~2,000×+ faster navigation**

> Jekyll is the smallest codebase in this suite (161 Ruby files, 0.4s scan). Query times are sub-millisecond for hierarchy and path queries — speedups are measured in thousands of times faster rather than tens or hundreds. The token reduction (−78% to −98%) reflects how well-structured Jekyll's OOP design is: every query returns a precise, complete answer.

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
