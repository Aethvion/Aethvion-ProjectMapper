# Benchmark: Rust — ripgrep

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `BurntSushi/ripgrep` |
| Language | Rust |
| Files scanned | 100 |
| Total lines | ~52,000 |
| Entities indexed | 845 |
| Scan time | 0.5 s |
| Throughput | ~104,700 lines/sec |

Geometric mean savings: **~80% token reduction (Full) · ~90% token reduction (Slim)** · **~1,700× faster navigation**

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + read tokens a skilled agent
would spend reaching the same answer without Project Mapper.

---

## Test 1 — Matcher Trait Implementations

**Question:** *"What types implement ripgrep's Matcher trait, and what does changing Matcher affect?"*

**Standard Workflow (Grep + Read):** `grep -rn "impl Matcher for" crates/`. Finds the main `RegexMatcher` impl in `crates/regex/src/matcher.rs`. To understand full impact, also read `crates/matcher/src/lib.rs` (the 1,133-line trait definition file) and `crates/searcher/src/searcher/core.rs`. The cross-crate propagation — that changing Matcher ripples through `search`, `search_parallel`, and CLI flag handlers — is invisible without tracing calls manually. 3–4 reads, ~3,500 tokens.

**With Project Mapper:** `pm_impact "Matcher" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | ~2 impls, call-chain propagation invisible | 31 — 6 direct + 25 transitive | 31 — complete |
| Token Cost | ~3,500 | ~974 | ~733 |
| Token Reduction | — | **−72%** | **−79%** |
| Execution Time | ~3.5s | <1ms | <1ms |
| Speedup | — | **~3,500×** | **~3,500×** |

---

## Test 2 — Sink Trait Implementations

**Question:** *"What types implement ripgrep's Sink trait (output targets), and what would changing Sink break?"*

**Standard Workflow (Grep + Read):** `grep -rn "impl Sink for" crates/`. Finds `StandardSink`, `SummarySink`, `JSONSink` in `crates/printer/`. Read `crates/printer/src/standard.rs` (~600 lines) and `crates/printer/src/summary.rs` (~400 lines). The `Box<S>` and `&mut S` blanket implementations in `crates/searcher/src/sink.rs` are invisible without reading that file separately. 3–4 reads, ~4,000 tokens.

**With Project Mapper:** `pm_impact "Sink" depth=1 exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | Partial, misses Box/&mut S blanket impls | 19 — direct + transitive | 19 — complete |
| Token Cost | ~4,000 | ~641 | ~462 |
| Token Reduction | — | **−84%** | **−88%** |
| Execution Time | ~4s | <1ms | <1ms |
| Speedup | — | **~4,000×** | **~4,000×** |

---

## Test 3 — Search Engine Components

**Question:** *"What components make up ripgrep's search engine?"*

**Standard Workflow (Grep + Read):** Read `crates/core/search.rs` (SearchWorker, SearchResult, Printer), `crates/searcher/src/searcher/mod.rs` (Searcher, SearcherBuilder, BinaryDetection), and `crates/regex/src/matcher.rs` (RegexMatcher, RegexMatcherBuilder). Cross-crate wiring between them is not obvious from file reads alone. 4–6 reads, ~6,000 tokens.

**With Project Mapper:** `pm_context "search engine grep regex"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–6 | 1 | 1 |
| Entities found | Partial, cross-crate wiring invisible | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~6,000 | ~1,374 | ~407 |
| Token Reduction | — | **−77%** | **−93%** |
| Execution Time | ~5s | 5ms | 5ms |
| Speedup | — | **~1,000×** | **~1,000×** |

---

## Test 4 — Output Formatting & Color System

**Question:** *"What components handle ripgrep's output formatting, color configuration, and printer types?"*

**Standard Workflow (Grep + Read):** Browse `crates/printer/` — read `color.rs` (~200 lines), `standard.rs` (~600 lines), `path.rs` (~300 lines), `summary.rs` (~400 lines). The `hyperlink/` sub-directory adds another layer. 4–5 reads, ~7,000 tokens. Color spec parsing (`SpecType`, `OutType`) and `FormatBuilder` are buried in the color file.

**With Project Mapper:** `pm_context "printer output format color"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–5 | 1 | 1 |
| Entities found | Partial, hyperlink/ sub-module easily missed | 30 ranked — incl. hyperlink and color internals | 30 ranked — complete |
| Token Cost | ~7,000 | ~1,326 | ~399 |
| Token Reduction | — | **−81%** | **−94%** |
| Execution Time | ~5s | 5ms | 5ms |
| Speedup | — | **~1,000×** | **~1,000×** |

---

## Test 5 — Directory Walking & Ignore System

**Question:** *"What components handle ripgrep's directory traversal, glob matching, and ignore-file processing?"*

**Standard Workflow (Grep + Read):** Read `crates/ignore/src/walk.rs` — this file is ~2,000 lines and contains `Walk`, `WalkParallel`, `WalkBuilder`, `WalkEventIter`, `WalkState`, `DirEntry`, and more. Then read `crates/ignore/src/gitignore.rs` (~700 lines) and `crates/globset/src/lib.rs` (~900 lines). 3 reads, ~8,000 tokens — and navigating a 2,000-line file for context is itself expensive.

**With Project Mapper:** `pm_context "walk directory glob ignore"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3+ | 1 | 1 |
| Entities found | Buried in 2,000-line file; globset link invisible | 30 ranked — complete, cross-crate | 30 ranked — complete |
| Token Cost | ~8,000 | ~1,183 | ~395 |
| Token Reduction | — | **−85%** | **−95%** |
| Execution Time | ~5s | 5ms | 5ms |
| Speedup | — | **~1,000×** | **~1,000×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Matcher trait implementations | ~3,500 tok | ~974 tok | ~733 tok | **−72%** | **−79%** | ~3,500× |
| Test 2 | Sink trait implementations | ~4,000 tok | ~641 tok | ~462 tok | **−84%** | **−88%** | ~4,000× |
| Test 3 | Search engine components | ~6,000 tok | ~1,374 tok | ~407 tok | **−77%** | **−93%** | ~1,000× |
| Test 4 | Output formatting & color | ~7,000 tok | ~1,326 tok | ~399 tok | **−81%** | **−94%** | ~1,000× |
| Test 5 | Directory walking & ignore | ~8,000 tok | ~1,183 tok | ~395 tok | **−85%** | **−95%** | ~1,000× |

---

Geometric mean savings: **~80% token reduction (Full) · ~90% token reduction (Slim)** · **~1,700× faster navigation**

> Rust is where **Slim mode matters most**: Rust doc comments are long and structured, so Full output is noticeably more verbose than Slim for the same entity set (e.g., T3: 1,374 Full → 407 Slim). Use Slim for orientation and navigation; switch to Full only when you need the docstring detail. The multi-crate workspace is where PM's cross-crate graph pays off regardless — a normal grep + read workflow requires jumping between `crates/core/`, `crates/searcher/`, `crates/printer/`, `crates/ignore/`, and `crates/regex/` to trace any relationship. PM answers cross-crate queries in a single call in under 5ms. T5 is the clearest example: `walk.rs` is a 2,000-line file — PM returns 30 ranked entities across `ignore/` and `globset/` in 395 tokens (Slim).

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/BurntSushi/ripgrep /path/to/ripgrep

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/ripgrep" db="ripgrep" incremental=false

# Test 1
pm_impact entity="Matcher" db="ripgrep" depth=1 exclude_tests=true

# Test 2
pm_impact entity="Sink" db="ripgrep" depth=1 exclude_tests=true

# Test 3
pm_context query="search engine grep regex" db="ripgrep"

# Test 4
pm_context query="printer output format color" db="ripgrep"

# Test 5
pm_context query="walk directory glob ignore" db="ripgrep"
```
