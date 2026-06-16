# Benchmark: Go — Hugo

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `gohugoio/hugo` |
| Language | Go |
| Files scanned | 896 |
| Total lines | ~224,000 |
| Entities indexed | 5,075 |
| Scan time | 3.2 s |
| Throughput | ~70,000 lines/sec |

Geometric mean savings: **~69% token reduction (Full) · ~87% token reduction (Slim)** · **~191× faster navigation**

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + read tokens a skilled agent
would spend reaching the same answer without Project Mapper.

---

## Test 1 — Page Type Hierarchy

**Question:** *"What concrete Page types does Hugo provide?"*

**Standard Workflow (Grep + Read):** `grep -r "Page" hugolib/` and `resources/page/`. Hugo's `Page` is a large interface defined across multiple files. Identifying concrete implementations requires reading `page.go`, `page_nop.go`, and `hugolib/page.go` separately. 4+ reads, easy to miss NopPage and wrapper types.

**With Project Mapper:** `pm_impact "Page" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4+ | 1 | 1 |
| Entities found | Partial, misses NopPage and wrappers | 4 — complete | 4 — complete |
| Token Cost | ~3,000 | ~401 | ~236 |
| Token Reduction | — | **−87%** | **−92%** |
| Execution Time | ~3s | 2ms | 2ms |
| Speedup | — | **~1,500×** | **~1,500×** |

---

## Test 2 — Template Rendering Pipeline

**Question:** *"What components make up Hugo's template rendering pipeline?"*

**Standard Workflow (Grep + Read):** `grep -r "render\|Render" tpl/` and `resources/`. Hugo's rendering is split across `tpl/tplimpl/`, `output/`, and `hugolib/`. 5+ reads across multiple packages; the connection between template execution and output format selection is not obvious from filenames.

**With Project Mapper:** `pm_context "template render output"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | Partial, cross-package connections missed | 18 ranked — complete | 18 ranked — complete |
| Token Cost | ~5,000 | ~1,547 | ~638 |
| Token Reduction | — | **−69%** | **−87%** |
| Execution Time | ~4s | 39ms | 38ms |
| Speedup | — | **~103×** | **~105×** |

---

## Test 3 — Shortcode System

**Question:** *"What components handle Hugo's shortcode processing?"*

**Standard Workflow (Grep + Read):** `grep -r "shortcode\|Shortcode" tpl/` and `hugolib/`. Shortcode handling spans `tpl/tplimpl/shortcodes.go`, `hugolib/shortcode.go`, and template lookup logic. 4+ reads; the interplay between shortcode registration and template resolution is spread across packages.

**With Project Mapper:** `pm_context "shortcode handler template"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4+ | 1 | 1 |
| Entities found | Partial, registration and resolution spread across packages | 26 ranked — complete | 26 ranked — complete |
| Token Cost | ~4,000 | ~2,066 | ~732 |
| Token Reduction | — | **−48%** | **−82%** |
| Execution Time | ~3s | 40ms | 39ms |
| Speedup | — | **~75×** | **~77×** |

---

## Test 4 — Content Source & Filesystem Abstraction

**Question:** *"What components handle Hugo's content sources and filesystem mounting?"*

**Standard Workflow (Grep + Read):** `grep -r "filesystem\|mount\|source" hugofs/` and `modules/`. Hugo's virtual filesystem layer (`hugofs`) is separate from its content source abstraction (`source/`). 4+ reads across both packages; the mount system in `modules/` adds another layer.

**With Project Mapper:** `pm_context "content source filesystem mount"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4+ | 1 | 1 |
| Entities found | Partial, hugofs and source packages not obviously connected | 19 ranked — complete | 19 ranked — complete |
| Token Cost | ~4,000 | ~1,575 | ~610 |
| Token Reduction | — | **−61%** | **−85%** |
| Execution Time | ~3s | 41ms | 41ms |
| Speedup | — | **~73×** | **~73×** |

---

## Test 5 — Build Pipeline Path (Site → Page)

**Question:** *"How does Hugo's Site connect to a Page in the build pipeline?"*

**Standard Workflow (Grep + Read):** Read `hugolib/site.go` (large file), trace through `hugolib/page_collections.go` to understand how the site owns its page collection. Requires reading 3+ large files to map the connection. ~3,000 tokens.

**With Project Mapper:** `pm_path from_entity="Site" to_entity="Page"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3+ | 1 | 1 |
| Entities found | Requires reading site.go | Path confirmed | Path confirmed |
| Token Cost | ~3,000 | ~313 | ~313 |
| Token Reduction | — | **−90%** | **−90%** |
| Execution Time | ~3s | 10ms | 10ms |
| Speedup | — | **~300×** | **~300×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Page type hierarchy | ~3,000 tok | ~401 tok | ~236 tok | **−87%** | **−92%** | ~1,500× |
| Test 2 | Template rendering pipeline | ~5,000 tok | ~1,547 tok | ~638 tok | **−69%** | **−87%** | ~103× |
| Test 3 | Shortcode system | ~4,000 tok | ~2,066 tok | ~732 tok | **−48%** | **−82%** | ~75× |
| Test 4 | Content source & filesystem | ~4,000 tok | ~1,575 tok | ~610 tok | **−61%** | **−85%** | ~73× |
| Test 5 | Site → Page build path | ~3,000 tok | ~313 tok | ~313 tok | **−90%** | **−90%** | ~300× |

---

Geometric mean savings: **~69% token reduction (Full) · ~87% token reduction (Slim)** · **~191× faster navigation**

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
