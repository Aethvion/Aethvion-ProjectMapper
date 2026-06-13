# Benchmark: Go — Hugo

**PM version:** v1.8.0 · **Date:** 2026-06-13 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `gohugoio/hugo` |
| Language | Go |
| Files scanned | ~750 |
| Total lines | ~200,000 |
| Entities indexed | 5,076 |
| Scan time | 3.2 s |
| Throughput | ~62,500 lines/sec |

Geometric mean savings: **~90% token reduction (Full) · ~93% token reduction (Slim)** · **~163× faster navigation**

---

## Test 1 — Page Type Hierarchy

**Question:** *"What concrete Page types does Hugo provide?"*

**Standard Workflow (Grep + Read):** `grep -r "Page" hugolib/` and `resources/page/`. Hugo's `Page` is a large interface defined across multiple files. Identifying concrete implementations requires reading `page.go`, `page_nop.go`, and `hugolib/page.go` separately. 4+ reads, easy to miss NopPage and wrapper types.

**With Project Mapper:** `pm_impact "Page" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4+ | 1 | 1 |
| Entities found | Partial, misses NopPage and wrappers | Complete | Complete |
| Token Cost | ~3,000 | ~123 | ~113 |
| Token Reduction | — | **−96%** | **−96%** |
| Execution Time | ~3s | 4ms | 3ms |
| Speedup | — | **~750×** | **~1,000×** |

---

## Test 2 — Template Rendering Pipeline

**Question:** *"What components make up Hugo's template rendering pipeline?"*

**Standard Workflow (Grep + Read):** `grep -r "render\|Render" tpl/` and `resources/`. Hugo's rendering is split across `tpl/tplimpl/`, `output/`, and `hugolib/`. 5+ reads across multiple packages; the connection between template execution and output format selection is not obvious from filenames.

**With Project Mapper:** `pm_context "template render output"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | Partial, cross-package connections missed | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~5,000 | ~654 | ~380 |
| Token Reduction | — | **−87%** | **−92%** |
| Execution Time | ~4s | 41ms | 40ms |
| Speedup | — | **~98×** | **~100×** |

---

## Test 3 — Shortcode System

**Question:** *"What components handle Hugo's shortcode processing?"*

**Standard Workflow (Grep + Read):** `grep -r "shortcode\|Shortcode" tpl/` and `hugolib/`. Shortcode handling spans `tpl/tplimpl/shortcodes.go`, `hugolib/shortcode.go`, and template lookup logic. 4+ reads; the interplay between shortcode registration and template resolution is spread across packages.

**With Project Mapper:** `pm_context "shortcode handler template"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4+ | 1 | 1 |
| Entities found | Partial, registration and resolution spread across packages | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~4,000 | ~713 | ~376 |
| Token Reduction | — | **−82%** | **−91%** |
| Execution Time | ~3s | 41ms | 40ms |
| Speedup | — | **~73×** | **~75×** |

---

## Test 4 — Content Source & Filesystem Abstraction

**Question:** *"What components handle Hugo's content sources and filesystem mounting?"*

**Standard Workflow (Grep + Read):** `grep -r "filesystem\|mount\|source" hugofs/` and `modules/`. Hugo's virtual filesystem layer (`hugofs`) is separate from its content source abstraction (`source/`). 4+ reads across both packages; the mount system in `modules/` adds another layer.

**With Project Mapper:** `pm_context "content source filesystem mount"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4+ | 1 | 1 |
| Entities found | Partial, hugofs and source packages not obviously connected | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~4,000 | ~602 | ~358 |
| Token Reduction | — | **−85%** | **−91%** |
| Execution Time | ~3s | 43ms | 42ms |
| Speedup | — | **~70×** | **~71×** |

---

## Test 5 — Build Pipeline Path (Site → Page)

**Question:** *"How does Hugo's Site connect to a Page in the build pipeline?"*

**Standard Workflow (Grep + Read):** Read `hugolib/site.go` (large file), trace through `hugolib/page_collections.go` to understand how the site owns its page collection. Requires reading 3+ large files to map the connection. ~3,000 tokens.

**With Project Mapper:** `pm_path from_entity="Site" to_entity="Page"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3+ | 1 | 1 |
| Entities found | Requires reading site.go | Path confirmed | Path confirmed |
| Token Cost | ~3,000 | ~33 | ~33 |
| Token Reduction | — | **−99%** | **−99%** |
| Execution Time | ~3s | 12ms | 12ms |
| Speedup | — | **~250×** | **~250×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Page type hierarchy | ~3,000 tok | ~123 tok | ~113 tok | **−96%** | **−96%** | ~750× |
| Test 2 | Template rendering pipeline | ~5,000 tok | ~654 tok | ~380 tok | **−87%** | **−92%** | ~98× |
| Test 3 | Shortcode system | ~4,000 tok | ~713 tok | ~376 tok | **−82%** | **−91%** | ~73× |
| Test 4 | Content source & filesystem | ~4,000 tok | ~602 tok | ~358 tok | **−85%** | **−91%** | ~70× |
| Test 5 | Site → Page build path | ~3,000 tok | ~33 tok | ~33 tok | **−99%** | **−99%** | ~250× |

---

Geometric mean savings: **~90% token reduction (Full) · ~93% token reduction (Slim)** · **~163× faster navigation**

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/gohugoio/hugo /path/to/hugo

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/hugo" db="hugo" incremental=false

# Test 1
pm_impact entity="Page" db="hugo" depth=1 exclude_tests=true

# Test 2
pm_context query="template render output" db="hugo"

# Test 3
pm_context query="shortcode handler template" db="hugo"

# Test 4
pm_context query="content source filesystem mount" db="hugo"

# Test 5
pm_path from_entity="Site" to_entity="Page" db="hugo"
```
