# Benchmark: Python — Django

**PM version:** v1.8.0 · **Date:** 2026-06-13 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `django/django` |
| Language | Python |
| Files scanned | 2,411 |
| Total lines | ~420,000 |
| Entities indexed | 12,066 |
| Scan time | 9.5 s |
| Throughput | ~44,200 lines/sec |

Geometric mean savings: **~91% token reduction (Full) · ~93% token reduction (Slim)** · **~97× faster navigation**

---

## Test 1 — ORM Field Hierarchy

**Question:** *"What field types does Django's ORM and forms system provide?"*

**Standard Workflow (Grep + Read):** `grep "class.*Field"` across `django/db/models/fields/`, `django/forms/`, `django/contrib/postgres/fields/`, `django/contrib/gis/`. Requires 6+ targeted reads; easily misses GIS and Postgres contrib fields unless each subdirectory is explicitly searched.

**With Project Mapper:** `pm_impact "Field" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | ~50–80, misses GIS/Postgres | 150 — complete | 150 — complete |
| Token Cost | ~35,000 | ~3,662 | ~3,129 |
| Token Reduction | — | **−90%** | **−91%** |
| Execution Time | ~4s | 21ms | 39ms |
| Speedup | — | **~190×** | **~103×** |

---

## Test 2 — Cross-App Path (ModelAdmin → Model)

**Question:** *"How does Django's admin interface connect to the ORM model layer?"*

**Standard Workflow (Grep + Read):** Read `ModelAdmin` source in `django/contrib/admin/options.py`, trace method calls into `django/db/models/base.py`. Requires 3+ reads and manual call-graph tracing across packages.

**With Project Mapper:** `pm_path from_entity="ModelAdmin" to_entity="Model"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3+ | 1 | 1 |
| Entities found | Yes, via manual tracing | 1-hop confirmed | 1-hop confirmed |
| Token Cost | ~13,200 | ~21 | ~21 |
| Token Reduction | — | **−99.8%** | **−99.8%** |
| Execution Time | ~2s | 42ms | 42ms |
| Speedup | — | **~48×** | **~48×** |

---

## Test 3 — Management Command Catalog

**Question:** *"What management commands does Django provide?"*

**Standard Workflow (Grep + Read):** `grep "class.*Command"` inside `django/core/management/commands/` and each `contrib/*/management/commands/` directory. Misses cross-app commands without explicitly listing all contrib apps.

**With Project Mapper:** `pm_impact "BaseCommand" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4+ | 1 | 1 |
| Entities found | Partial, misses cross-app | 6 prod + 2 transitive — complete | 6 prod + 2 transitive — complete |
| Token Cost | ~4,100 | ~309 | ~210 |
| Token Reduction | — | **−93%** | **−95%** |
| Execution Time | ~3s | 14ms | 14ms |
| Speedup | — | **~214×** | **~214×** |

---

## Test 4 — Authentication & Middleware Context

**Question:** *"Which components handle authentication and middleware in Django?"*

**Standard Workflow (Grep + Read):** `grep "authentication\|middleware"` across `django/contrib/auth/` and `django/middleware/`. Returns raw text matches across dozens of files; agent must still read and filter 5+ files to build a useful picture.

**With Project Mapper:** `pm_context "authentication middleware"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | Partial | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~13,479 | ~1,102 | ~444 |
| Token Reduction | — | **−92%** | **−97%** |
| Execution Time | ~4s | 86ms | 86ms |
| Speedup | — | **~47×** | **~47×** |

---

## Test 5 — Class-Based View Hierarchy

**Question:** *"What class-based views does Django provide across all apps?"*

**Standard Workflow (Grep + Read):** `grep "class.*View"` in `django/views/generic/`. Misses views in `django/contrib/admin/`, `django/contrib/auth/`, and `django/views/i18n` without additional targeted searches.

**With Project Mapper:** `pm_impact "View" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–5 | 1 | 1 |
| Entities found | ~15, generic only | 43 — complete, all apps | 43 — complete, all apps |
| Token Cost | ~10,000 | ~1,133 | ~896 |
| Token Reduction | — | **−89%** | **−91%** |
| Execution Time | ~3s | 15ms | 14ms |
| Speedup | — | **~200×** | **~214×** |

---

## Test 6 — Signal & Dispatch System

**Question:** *"What components make up Django's signal and event dispatch system?"*

**Standard Workflow (Grep + Read):** `grep "Signal\|receiver\|dispatch"` across `django/dispatch/`, then read `django/db/models/signals.py` and related files. Signal usage is scattered; requires 5+ reads to map the full system.

**With Project Mapper:** `pm_context "signal dispatch receiver"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | Partial | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~8,000 | ~973 | ~374 |
| Token Reduction | — | **−88%** | **−95%** |
| Execution Time | ~3s | 78ms | 78ms |
| Speedup | — | **~38×** | **~38×** |

---

## Test 7 — Production Model Subclasses

**Question:** *"What concrete models does Django define? (excluding tests)"*

**Standard Workflow (Grep + Read):** `grep "class.*models.Model"` across all `django/contrib/*/models.py` files. Misses indirect inheritance (model → abstract model → Model) and requires reading each file individually. 5+ reads minimum.

**With Project Mapper:** `pm_impact "models.Model" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | Partial, misses abstract chain | 386 — complete | 386 — complete |
| Token Cost | ~40,000 | ~9,565 | ~8,157 |
| Token Reduction | — | **−76%** | **−80%** |
| Execution Time | ~5s | 42ms | 17ms |
| Speedup | — | **~119×** | **~294×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | ORM Field types | ~35,000 tok | ~3,662 tok | ~3,129 tok | **−90%** | **−91%** | ~190× |
| Test 2 | Admin → ORM path | ~13,200 tok | ~21 tok | ~21 tok | **−99.8%** | **−99.8%** | ~48× |
| Test 3 | Management commands | ~4,100 tok | ~309 tok | ~210 tok | **−93%** | **−95%** | ~214× |
| Test 4 | Auth/middleware context | ~13,479 tok | ~1,102 tok | ~444 tok | **−92%** | **−97%** | ~47× |
| Test 5 | CBV hierarchy | ~10,000 tok | ~1,133 tok | ~896 tok | **−89%** | **−91%** | ~200× |
| Test 6 | Signal dispatch | ~8,000 tok | ~973 tok | ~374 tok | **−88%** | **−95%** | ~38× |
| Test 7 | Model subclasses | ~40,000 tok | ~9,565 tok | ~8,157 tok | **−76%** | **−80%** | ~119× |

---

Geometric mean savings: **~91% token reduction (Full) · ~93% token reduction (Slim)** · **~97× faster navigation**

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/django/django /path/to/django

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/django" db="django" incremental=false

# Test 1
pm_impact entity="Field" db="django" depth=1 exclude_tests=true

# Test 2
pm_path from_entity="ModelAdmin" to_entity="Model" db="django"

# Test 3
pm_impact entity="BaseCommand" db="django" depth=1 exclude_tests=true

# Test 4
pm_context query="authentication middleware" db="django"

# Test 5
pm_impact entity="View" db="django" depth=1 exclude_tests=true

# Test 6
pm_context query="signal dispatch receiver" db="django"

# Test 7
pm_impact entity="models.Model" db="django" depth=1 via_kinds=["extends"] exclude_tests=true
```
