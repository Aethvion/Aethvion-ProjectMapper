# Benchmark: PHP — WordPress

**PM version:** v1.8.0 · **Date:** 2026-06-13 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `WordPress/WordPress` |
| Language | PHP |
| Files scanned | 2,295 |
| Total lines | ~520,000 |
| Entities indexed | 7,757 |
| Scan time | 12.0 s |
| Throughput | ~43,300 lines/sec |

Geometric mean savings: **~92% token reduction (Full) · ~93% token reduction (Slim)** · **~1,050× faster navigation**

---

## Test 1 — Widget Hierarchy

**Question:** *"What widget types does WordPress provide?"*

**Standard Workflow (Grep + Read):** `grep -r "extends WP_Widget"` across `wp-includes/widgets/` and `wp-content/themes/`. Read the `WP_Widget` base class plus 5–6 concrete widget files. Each is 100–250 lines PHP; theme-bundled widgets in `wp-content/` are easily missed without an explicit directory search.

**With Project Mapper:** `pm_impact "WP_Widget" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | Partial, misses theme widgets | 22 — complete, cross-directory | 22 — complete |
| Token Cost | ~8,000 | ~630 | ~580 |
| Token Reduction | — | **−92%** | **−93%** |
| Execution Time | ~4s | 4ms | 3ms |
| Speedup | — | **~1,000×** | **~1,333×** |

---

## Test 2 — REST API Controller Catalog

**Question:** *"What REST API endpoints does WordPress provide?"*

**Standard Workflow (Grep + Read):** Browse `wp-includes/rest-api/endpoints/` (~40 PHP files, 300–700 lines each). Read the base `WP_REST_Controller` class, then browse individual controllers for Posts, Users, Terms, Comments, Settings, Templates, Menus, Fonts, and more. 8+ reads, newer additions (Font Families, Global Styles) easily missed.

**With Project Mapper:** `pm_impact "WP_REST_Controller" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 8+ | 1 | 1 |
| Entities found | Partial, misses recent additions | 44 — complete, full catalog | 44 — complete |
| Token Cost | ~20,000 | ~1,572 | ~1,475 |
| Token Reduction | — | **−92%** | **−93%** |
| Execution Time | ~6s | 3ms | 2ms |
| Speedup | — | **~2,000×** | **~3,000×** |

---

## Test 3 — Customizer Control Hierarchy

**Question:** *"What Customizer control types does WordPress provide?"*

**Standard Workflow (Grep + Read):** Browse `wp-includes/customize/` for classes extending `WP_Customize_Control`. The directory mixes panels, sections, and controls — easy to conflate. Read the large base class file plus several concrete control files. 6+ reads, ~7,500 tokens.

**With Project Mapper:** `pm_impact "WP_Customize_Control" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | Partial, directory mixes panels/sections/controls | 20 — complete hierarchy | 20 — complete |
| Token Cost | ~7,500 | ~705 | ~662 |
| Token Reduction | — | **−91%** | **−91%** |
| Execution Time | ~4s | 4ms | 5ms |
| Speedup | — | **~1,000×** | **~800×** |

---

## Test 4 — Admin List Table Hierarchy

**Question:** *"What admin list table types does WordPress provide?"*

**Standard Workflow (Grep + Read):** Search `wp-admin/includes/` for `class-wp-*-list-table.php` files (15 files). Read the base `WP_List_Table` class, then concrete implementations for Posts, Users, Comments, Plugins, Themes, Media, Terms. Multisite `MS_*` tables in the same directory are easily overlooked. 6+ reads.

**With Project Mapper:** `pm_impact "WP_List_Table" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | Partial, misses multisite MS_* tables | 21 — complete, inc. multisite | 21 — complete |
| Token Cost | ~7,500 | ~603 | ~560 |
| Token Reduction | — | **−92%** | **−93%** |
| Execution Time | ~4s | 5ms | 5ms |
| Speedup | — | **~800×** | **~800×** |

---

## Test 5 — Walker Tree-Renderer Hierarchy

**Question:** *"What tree-rendering Walker implementations does WordPress provide?"*

**Standard Workflow (Grep + Read):** `grep -r "extends Walker"` across `wp-includes/` and `wp-admin/includes/`. Walker is used for menus, categories, comments, and page dropdowns — spread across multiple files. Read the base Walker class plus 5–6 concrete implementations. Theme walkers in `wp-content/` require a separate search. 6+ reads.

**With Project Mapper:** `pm_impact "Walker" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | Partial, theme walkers in wp-content/ missed | 10 — complete, inc. theme walkers | 10 — complete |
| Token Cost | ~4,000 | ~313 | ~290 |
| Token Reduction | — | **−92%** | **−93%** |
| Execution Time | ~3s | 5ms | 5ms |
| Speedup | — | **~600×** | **~600×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Widget hierarchy | ~8,000 tok | ~630 tok | ~580 tok | **−92%** | **−93%** | ~1,000× |
| Test 2 | REST API controller catalog | ~20,000 tok | ~1,572 tok | ~1,475 tok | **−92%** | **−93%** | ~2,000× |
| Test 3 | Customizer control hierarchy | ~7,500 tok | ~705 tok | ~662 tok | **−91%** | **−91%** | ~1,000× |
| Test 4 | Admin list table hierarchy | ~7,500 tok | ~603 tok | ~560 tok | **−92%** | **−93%** | ~800× |
| Test 5 | Walker tree-renderer hierarchy | ~4,000 tok | ~313 tok | ~290 tok | **−92%** | **−93%** | ~600× |

---

Geometric mean savings: **~92% token reduction (Full) · ~93% token reduction (Slim)** · **~1,050× faster navigation**

> WordPress is primarily procedural PHP — its extension system uses function-based hooks (`add_action` / `add_filter`) rather than class inheritance. PM indexes WordPress's OOP subsystems (Widgets, REST API, Customizer, Admin, Walker) where class hierarchies exist. The speed advantage is extreme (600–2,000×) because the small, warm entity graph (7,757 entities) answers these queries in 2–5ms flat.

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/WordPress/WordPress /path/to/wordpress

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/wordpress" db="wordpress" incremental=false

# Test 1
pm_impact entity="WP_Widget" db="wordpress" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 2
pm_impact entity="WP_REST_Controller" db="wordpress" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 3
pm_impact entity="WP_Customize_Control" db="wordpress" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 4
pm_impact entity="WP_List_Table" db="wordpress" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 5
pm_impact entity="Walker" db="wordpress" depth=1 via_kinds=["extends"] exclude_tests=true
```
