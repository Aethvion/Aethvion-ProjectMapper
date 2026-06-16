# Benchmark: Swift — swift-algorithms

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `apple/swift-algorithms` |
| Language | Swift |
| Files scanned | 57 |
| Total lines | ~12,200 |
| Entities indexed | 197 |
| Scan time | 0.2 s |
| Throughput | ~61,000 lines/sec |

Geometric mean savings: **~81% token reduction (Full) · ~88% token reduction (Slim)** · **~1,900× faster navigation**

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + read tokens a skilled agent
would spend reaching the same answer without Project Mapper.

---

## Test 1 — Complete Sequence Type Catalog

**Question:** *"What sequence types does swift-algorithms provide?"*

**Standard Workflow (Grep + Read):** swift-algorithms stores one algorithm per file in `Sources/Algorithms/`. `grep -rn ": Sequence" Sources/` returns noisy output across all files. An agent typically reads 5–8 files (Chain.swift, Joined.swift, Cycle.swift, Permutations.swift, etc.) and stops short, missing types defined further down the directory. Types with both a sequence and a collection variant (e.g., `JoinedBySequence` + `JoinedByCollection` in the same file, `StridingSequence` + `StridingCollection`) are routinely undercounted. 8+ reads, ~5,000 tokens.

**With Project Mapper:** `pm_impact "Sequence" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 8+ | 1 | 1 |
| Entities found | Partial (~10–12), paired variants missed | 23 — complete, all conformances | 23 — complete |
| Token Cost | ~5,000 | ~685 | ~570 |
| Token Reduction | — | **−86%** | **−89%** |
| Execution Time | ~5s | 9ms | 9ms |
| Speedup | — | **~560×** | **~560×** |

---

## Test 2 — Lazy Sequence Type Catalog

**Question:** *"Which algorithm types support lazy evaluation?"*

**Standard Workflow (Grep + Read):** `grep -rn "LazySequenceProtocol\|LazyCollectionProtocol" Sources/`. Conformances are scattered across 20+ files — Chunked.swift alone has four types conforming. With 57 files total, reading the relevant ones takes 10+ reads and still misses 30–40% of conformances, especially types that conform via conditional extension rather than direct declaration. ~6,000 tokens.

**With Project Mapper:** `pm_impact "LazySequenceProtocol" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 10+ | 1 | 1 |
| Entities found | Partial (~15–18), conditional conformances missed | 27 — complete, all conformances | 27 — complete |
| Token Cost | ~6,000 | ~799 | ~664 |
| Token Reduction | — | **−87%** | **−89%** |
| Execution Time | ~6s | <1ms | <1ms |
| Speedup | — | **~6,000×** | **~6,000×** |

---

## Test 3 — Windowing & Chunking Algorithms

**Question:** *"What windowed and chunked iteration algorithms does the library provide?"*

**Standard Workflow (Grep + Read):** Read `Sources/Algorithms/Chunked.swift` — this single file defines four different chunking strategies: `ChunkedByCollection`, `ChunkedOnCollection`, `EvenlyChunkedCollection`, and `ChunksOfCountCollection`, each with their own `Index` types. Also read `Sources/Algorithms/Windows.swift` and `Sources/Algorithms/Stride.swift`. 3 reads, ~4,000 tokens — but Chunked.swift is the largest file in the library, requiring the agent to parse it fully to find all four types.

**With Project Mapper:** `pm_context "chunked windows sliding stride"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3+ | 1 | 1 |
| Entities found | All accessible but one large file to parse | 30 ranked — all variants surfaced | 30 ranked — complete |
| Token Cost | ~4,000 | ~939 | ~541 |
| Token Reduction | — | **−77%** | **−86%** |
| Execution Time | ~4s | 2ms | 2ms |
| Speedup | — | **~2,000×** | **~2,000×** |

---

## Test 4 — Combinatorics Algorithms

**Question:** *"What combinatorics algorithms does the library provide?"*

**Standard Workflow (Grep + Read):** Read `Sources/Algorithms/Permutations.swift` (PermutationsSequence + UniquePermutationsSequence), `Sources/Algorithms/Combinations.swift` (CombinationsSequence), `Sources/Algorithms/Product.swift` (Product2Sequence). 3 reads, ~4,000 tokens. The `Rotate.swift` connection (MutableCollection.rotate is used internally by permutation algorithms) is invisible from reading these files directly.

**With Project Mapper:** `pm_context "permutation combination product"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3 | 1 | 1 |
| Entities found | 3 files, cross-file connections invisible | 24 ranked — incl. Rotate dependency | 24 ranked — complete |
| Token Cost | ~4,000 | ~697 | ~401 |
| Token Reduction | — | **−83%** | **−90%** |
| Execution Time | ~4s | 2ms | 2ms |
| Speedup | — | **~2,000×** | **~2,000×** |

---

## Test 5 — Sequence Combining Algorithms

**Question:** *"What algorithms combine or interleave multiple sequences?"*

**Standard Workflow (Grep + Read):** Read `Sources/Algorithms/Chain.swift` (Chain2Sequence), `Sources/Algorithms/Joined.swift` (JoinedBySequence, JoinedByClosureSequence, JoinedByCollection, JoinedByClosureCollection — four types in one file), `Sources/Algorithms/Intersperse.swift` (InterspersedSequence + InterspersedMapSequence). 3 reads, ~3,500 tokens. The four Joined variants in a single file are commonly undercounted.

**With Project Mapper:** `pm_context "chain join intersperse merge"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3 | 1 | 1 |
| Entities found | Partial, 4 Joined variants in one file undercounted | 29 ranked — all variants surfaced | 29 ranked — complete |
| Token Cost | ~3,500 | ~849 | ~490 |
| Token Reduction | — | **−76%** | **−86%** |
| Execution Time | ~3.5s | 2ms | 2ms |
| Speedup | — | **~1,750×** | **~1,750×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Sequence type catalog | ~5,000 tok | ~685 tok | ~570 tok | **−86%** | **−89%** | ~560× |
| Test 2 | Lazy sequence catalog | ~6,000 tok | ~799 tok | ~664 tok | **−87%** | **−89%** | ~6,000× |
| Test 3 | Windowing & chunking | ~4,000 tok | ~939 tok | ~541 tok | **−77%** | **−86%** | ~2,000× |
| Test 4 | Combinatorics algorithms | ~4,000 tok | ~697 tok | ~401 tok | **−83%** | **−90%** | ~2,000× |
| Test 5 | Sequence combining | ~3,500 tok | ~849 tok | ~490 tok | **−76%** | **−86%** | ~1,750× |

---

Geometric mean savings: **~81% token reduction (Full) · ~88% token reduction (Slim)** · **~1,900× faster navigation**

> swift-algorithms is the smallest codebase in this suite (57 files, 0.2s scan, 197 entities) and the only one structured as a flat algorithm collection — one Swift file per algorithm — rather than a layered application. The completeness advantage dominates: T1 and T2 demonstrate that a one-file-per-algorithm layout makes exhaustive cataloguing hard for a normal grep workflow, because there are 23+ Sequence conformances and 27+ LazySequenceProtocol conformances spread across 20+ files with no central registry. PM returns the complete list in under 1ms (T2) or 9ms (T1). T3's story is the inverse: Chunked.swift is the largest file in the library, defining four distinct chunking strategies in one place — PM surfaces all of them along with Windows and Stride types in 541 Slim tokens vs parsing a large multi-type file.

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/apple/swift-algorithms /path/to/swift-algorithms

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/swift-algorithms" db="swift-algorithms" incremental=false

# Test 1
pm_impact entity="Sequence" db="swift-algorithms" depth=1 exclude_tests=true

# Test 2
pm_impact entity="LazySequenceProtocol" db="swift-algorithms" depth=1 exclude_tests=true

# Test 3
pm_context query="chunked windows sliding stride" db="swift-algorithms"

# Test 4
pm_context query="permutation combination product" db="swift-algorithms"

# Test 5
pm_context query="chain join intersperse merge" db="swift-algorithms"
```
