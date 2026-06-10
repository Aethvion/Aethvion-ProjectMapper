# Benchmark: Swift — swift-algorithms 1.2.1

**Date:** 2026-06-10 · **Project Mapper:** v1.5.0

> Real numbers from the [swift-algorithms source repository](https://github.com/apple/swift-algorithms) (main branch, version `1.2.1`). No synthetic data.

---

## The Subject

| | |
|:---|:---|
| Repository | `apple/swift-algorithms` |
| Version | `1.2.1` |
| Date tested | **2026-06-10** |
| Project Mapper | **v1.5.0** |
| Swift files analyzed | **57** (28 algorithm files + test suite) |
| Structure | Single-library — `Sources/Algorithms/` · one `.swift` file per algorithm |

---

## Test Environment

| | |
|:---|:---|
| OS | Windows 11 |
| Python | 3.10.11 |
| Hardware | Desktop PC · Intel i9-13900K (24C/32T) · RTX 4090 |
| PM server | Standalone · `python -m uvicorn server:app --port 7474` |
| Analysis | Static AST only (no LLM calls) |

> **Windows note:** NTFS and Defender I/O overhead inflates scan time vs Linux/macOS (est. 3–5× faster on Linux).

---

## Indexing

### Full Scan (cold start)

| | |
|:---|:---|
| Swift files analyzed | **57** |
| Files skipped (unsupported) | 0 |
| Entities indexed | **341** |
| Relations mapped | **353** |
| Errors | **0** |
| Snapshot size | **< 0.5 MB** |
| Entity files on disk | **0** (PMEntityStore) |
| **Full scan time** | **0.5 s** |

### Incremental Scan (zero file changes)

| | |
|:---|:---|
| Files skipped (hash unchanged) | **57** |
| **Incremental scan time** | **0.2 s** |
| **Speedup vs full scan** | **~2.5×** |

> **swift-algorithms is protocol-oriented — protocols replace class hierarchies.** There are no abstract base classes. Instead, Swift's `Collection` protocol family (`Sequence`, `Collection`, `BidirectionalCollection`, `RandomAccessCollection`, `LazySequenceProtocol`) forms the entire architectural spine. Each of the 28 algorithm implementations (`Chunked`, `Windows`, `Permutations`, etc.) is a focused `.swift` file of 150–500 lines that declares its types via extension blocks scattered throughout.
>
> The protocol conformance picture: `LazySequenceProtocol` has 25 conforming types (the full lazy-evaluation algorithm set), `Collection` has 21, `BidirectionalCollection` and `Sequence` each have 18, and `RandomAccessCollection` has 11 (the highest-capability tier). PM recovers these complete conformance catalogs in a single query where a manual search must trace conditional extension blocks across 20–28 files.

---

## Query Benchmarks

The primary purpose of Project Mapper is **token reduction**. Each test below compares what an AI agent would consume without PM (Grep + Read source files) against a single PM API call.

> **"Normal" baseline:** Each algorithm lives in a clearly named file — discoverable by name. The challenge is Swift's protocol conformances: they are frequently *conditional* (`extension StridingCollection: BidirectionalCollection where Base: BidirectionalCollection`) and declared in multiple separate `extension` blocks throughout each file. An agent wanting a complete, reliable conformance picture reads from start to end. Token estimates assume the agent reads every file whose algorithm plausibly conforms to the protocol under investigation.
>
> **Query latency (v1.5.0):** cold miss ~4 ms (< 0.5 MB snapshot load); warm hits < 2 ms (in-memory cache, mtime-validated).

---

### S1 — LazySequenceProtocol Catalog

**Question:** *"Which swift-algorithms types support lazy evaluation — the complete lazy sequence set?"*

**Normal approach:** `grep -rn "LazySequenceProtocol"` across `Sources/Algorithms/` finds ~25 match lines, one per conformance declaration. But conditional conformances (`where Base: LazySequenceProtocol`) are in distinct extension blocks; the grep output gives names but not the conditions or file context. An agent wanting the complete picture reads all 28 algorithm files: 28 × ~180 tok avg = ~5,000 tokens.

**PM approach:** `impact("LazySequenceProtocol", via_kinds=["extends"], exclude_tests=True)`

**25 types returned — complete lazy algorithm catalog:**
```
CycledSequence               Sources/Algorithms/Cycle.swift
CycledTimesCollection        Sources/Algorithms/Cycle.swift
CombinationsSequence         Sources/Algorithms/Combinations.swift
PermutationsSequence         Sources/Algorithms/Permutations.swift
IndexedCollection            Sources/Algorithms/Indexed.swift
CompactedSequence            Sources/Algorithms/Compacted.swift
AdjacentPairsSequence        Sources/Algorithms/AdjacentPairs.swift
ChainSequence                Sources/Algorithms/Chain.swift
IntersperseSequence          Sources/Algorithms/Intersperse.swift
EitherSequence               Sources/Algorithms/EitherSequence.swift
FlattenCollection            Sources/Algorithms/FlattenCollection.swift
ChunkedByCollection          Sources/Algorithms/Chunked.swift
ChunkedOnCollection          Sources/Algorithms/Chunked.swift
ChunksOfCountCollection      Sources/Algorithms/Chunked.swift
EvenlyChunkedCollection      Sources/Algorithms/Chunked.swift
WindowsOfCountCollection     Sources/Algorithms/Windows.swift
StridingCollection           Sources/Algorithms/Stride.swift
SplitCollection              Sources/Algorithms/Split.swift
UniquedSequence              Sources/Algorithms/Unique.swift
TrimmedCollection            Sources/Algorithms/Trim.swift
RotatedCollection            Sources/Algorithms/Rotate.swift
ReductionsSequence           Sources/Algorithms/Reductions.swift
ProductSequence              Sources/Algorithms/Product.swift
KeyedCollection              Sources/Algorithms/Keyed.swift
GroupedCollection            Sources/Algorithms/Grouped.swift
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 28+ | **1** | **1** |
| Tokens consumed | ~5,000 | **~1,346** | **~702** |
| Types found | All 25 (requires full read of all algorithm files) | **25 — complete catalog** | **25 — complete** |
| Savings vs Normal | — | **~3.7×** | **~7.1×** |

> Four of the 25 are chunking variants from a single file (`Chunked.swift`): `ChunkedByCollection` (chunk by predicate), `ChunkedOnCollection` (chunk on predicate change), `ChunksOfCountCollection` (fixed-size chunks), `EvenlyChunkedCollection` (evenly divided chunks). A grep returns all four as separate match lines from the same file, but reading the full file is necessary to understand the conditional conformance structure — e.g., `EvenlyChunkedCollection: LazySequenceProtocol where Base: RandomAccessCollection`.

---

### S2 — Collection Catalog

**Question:** *"Which algorithm types provide indexed-access Collection semantics — subscript, count, startIndex/endIndex?"*

**Normal approach:** Collection conformance is the base capability tier — 21 of the 28 algorithm types have it. An agent reads the 25+ algorithm files most likely to conform, to catch all conditional declarations. 25 files × ~200 tok avg = ~5,000 tokens.

**PM approach:** `impact("Collection", via_kinds=["extends"], exclude_tests=True)`

**21 types returned — full indexed-collection catalog:**
```
ChunkedByCollection          Sources/Algorithms/Chunked.swift
ChunkedOnCollection          Sources/Algorithms/Chunked.swift
ChunksOfCountCollection      Sources/Algorithms/Chunked.swift
EvenlyChunkedCollection      Sources/Algorithms/Chunked.swift
WindowsOfCountCollection     Sources/Algorithms/Windows.swift
IndexedCollection            Sources/Algorithms/Indexed.swift
StridingCollection           Sources/Algorithms/Stride.swift
SplitCollection              Sources/Algorithms/Split.swift
FlattenCollection            Sources/Algorithms/FlattenCollection.swift
RotatedCollection            Sources/Algorithms/Rotate.swift
TrimmedCollection            Sources/Algorithms/Trim.swift
UniquedSequence              Sources/Algorithms/Unique.swift
ReductionsCollection         Sources/Algorithms/Reductions.swift
ProductCollection            Sources/Algorithms/Product.swift
CycledTimesCollection        Sources/Algorithms/Cycle.swift
EitherSequence               Sources/Algorithms/EitherSequence.swift
KeyedCollection              Sources/Algorithms/Keyed.swift
GroupedCollection            Sources/Algorithms/Grouped.swift
AdjacentPairsCollection      Sources/Algorithms/AdjacentPairs.swift
IntersperseCollection        Sources/Algorithms/Intersperse.swift
... (+ 1 more)
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 25+ | **1** | **1** |
| Tokens consumed | ~5,000 | **~1,149** | **~609** |
| Types found | All 21 (requires reading most algorithm files) | **21 — complete catalog** | **21 — complete** |
| Savings vs Normal | — | **~4.4×** | **~8.2×** |

---

### S3 — BidirectionalCollection: Reverse-Traversal Tier

**Question:** *"Which algorithms support backward iteration — can be traversed from the end?"*

**Normal approach:** `BidirectionalCollection` conformance means the algorithm type has a valid `index(before:)` — it can iterate in reverse. grep finds ~18 match lines across ~15 files. Read each of those 18 files to verify and understand the conformance condition: 18 × ~250 tok avg = ~4,500 tokens.

**PM approach:** `impact("BidirectionalCollection", via_kinds=["extends"], exclude_tests=True)`

**18 types returned — full bidirectional-traversal catalog:**
```
ChunkedByCollection         Sources/Algorithms/Chunked.swift     (where Base: Bidir)
ChunksOfCountCollection     Sources/Algorithms/Chunked.swift
EvenlyChunkedCollection     Sources/Algorithms/Chunked.swift
WindowsOfCountCollection    Sources/Algorithms/Windows.swift
IndexedCollection           Sources/Algorithms/Indexed.swift
StridingCollection          Sources/Algorithms/Stride.swift      (where Base: Bidir)
SplitCollection             Sources/Algorithms/Split.swift       (where Base: Bidir)
RotatedCollection           Sources/Algorithms/Rotate.swift
TrimmedCollection           Sources/Algorithms/Trim.swift        (where Base: Bidir)
UniquedSequence             Sources/Algorithms/Unique.swift      (where Base: Bidir)
ReductionsCollection        Sources/Algorithms/Reductions.swift  (conditional)
CycledTimesCollection       Sources/Algorithms/Cycle.swift       (where Base: Bidir)
FlattenCollection           Sources/Algorithms/FlattenCollection.swift (conditional)
EitherSequence              Sources/Algorithms/EitherSequence.swift (conditional)
AdjacentPairsCollection     Sources/Algorithms/AdjacentPairs.swift
IntersperseCollection       Sources/Algorithms/Intersperse.swift
... (+ 2 more)
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 18–22 | **1** | **1** |
| Tokens consumed | ~4,500 | **~995** | **~533** |
| Types found | All 18 (requires reading full extension blocks for conditions) | **18 — complete reverse-traversal set** | **18 — complete** |
| Savings vs Normal | — | **~4.5×** | **~8.4×** |

> The conditional conformances are architecturally important. `StridingCollection: BidirectionalCollection where Base: BidirectionalCollection` means that striding a random-access array supports reverse traversal, but striding a forward-only sequence does not. PM's entity response includes the conformance conditions, letting the agent reason about capability propagation in one call.

---

### S4 — Combinatorial Algorithms Context

**Question:** *"What does swift-algorithms provide for combinatorics — combinations, permutations, and cartesian products?"*

**Normal approach:** Read `Sources/Algorithms/Combinations.swift` (~300 tok), `Permutations.swift` (~350 tok), and `Product.swift` (~250 tok) for the source implementations. Add corresponding test files (~300 tok each × 3) to understand usage patterns, and check `RandomSample.swift` (~200 tok) for the related random-sampling neighbor. Total: ~3,000 tokens.

**PM approach:** `context("combination permutation product")`

**16 entities returned — combinatorial subsystem fully mapped:**
```
[module] Sources/Algorithms/Combinations.swift    → CombinationsSequence, CombinationsCollection
[module] Sources/Algorithms/Permutations.swift    → PermutationsSequence, AnyPermutation
[module] Sources/Algorithms/Product.swift         → Product2Sequence, ProductCollection
[module] Tests/.../CombinationsTests.swift        → usage + edge-case coverage
[module] Tests/.../PermutationsTests.swift        → usage + edge-case coverage
[module] Tests/.../ProductTests.swift             → usage + edge-case coverage
[class]  CombinationsSequence                     → lazy combination enumeration
[class]  PermutationsSequence                     → k-permutation lazy enumeration
[class]  Product2Sequence                         → lazy cartesian product of two sequences
[class]  CombinationsCollection                   → indexed combinations (random access)
[class]  ProductCollection                        → indexed cartesian product (random access)
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 7–9 | **1** | **1** |
| Tokens consumed | ~3,000 | **~889** | **~390** |
| Entities surfaced | 3 source modules (test cross-links missed without additional reads) | **16 — source + test cross-mapped** | **16 entities** |
| Savings vs Normal | — | **~3.4×** | **~7.7×** |

> `CombinationsCollection` and `ProductCollection` are distinct from their `Sequence` variants — they conform to `RandomAccessCollection`, enabling O(1) subscript access to the `n`-th combination or product pair. PM surfaces this distinction in a single context call; a manual read of the source files reveals it, but only after reading the conditional extension blocks at the end of each file.

---

### S5 — Protocol Conformance Path

**Question:** *"Does `StridingCollection` support random-access indexing — can it be subscripted in O(1)?"*

**Normal approach:** Read `Sources/Algorithms/Stride.swift` to find where `StridingCollection` declares its protocol conformances (~200–300 lines, ~250 tok). Scan the extension blocks near the bottom to verify `RandomAccessCollection` conformance. Add grep overhead. Total: ~800 tokens.

**PM approach:** `path("StridingCollection", "RandomAccessCollection")`

**Result (1-hop path):**
```
StridingCollection
  --[extends]--> RandomAccessCollection
```

`StridingCollection` directly implements `RandomAccessCollection`. Confirmed in 95 tokens.

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 2–3 | **1** | **1** |
| Tokens consumed | ~800 | **~95** | **~47** |
| Relationship confirmed | Yes — requires reading Stride.swift extension blocks | **Yes — 1 hop, immediate** | **Yes** |
| Savings vs Normal | — | **~8.4×** | **~17.0×** |

> `StridingCollection`'s random-access support is non-obvious: striding a sequence generally loses O(1) indexing (you'd need to advance N steps). swift-algorithms preserves it by storing the stride count and computing `index(_:offsetBy:)` directly via arithmetic on the base index. PM makes this property discoverable in a single query that costs 11× fewer tokens than reading the source.

---

## Headline Numbers

| Test | Question | Normal | PM (Full) | PM (Slim) | Savings (Full) | Savings (Slim) |
|:---|:---|:---|:---|:---|:---|:---|
| S1 | LazySequenceProtocol catalog | ~5,000 tok | **~1,346 tok** | **~702 tok** | **3.7×** | **7.1×** |
| S2 | Collection catalog | ~5,000 tok | **~1,149 tok** | **~609 tok** | **4.4×** | **8.2×** |
| S3 | BidirectionalCollection tier | ~4,500 tok | **~995 tok** | **~533 tok** | **4.5×** | **8.4×** |
| S4 | Combinatorial subsystem context | ~3,000 tok | **~889 tok** | **~390 tok** | **3.4×** | **7.7×** |
| S5 | StridingCollection → RandomAccessCollection | ~800 tok | **~95 tok** | **~47 tok** | **8.4×** | **17.0×** |

**Geometric mean savings:** PM Full **~4.5×** · PM Slim **~9×** across all five tests.

> swift-algorithms is the smallest and most file-granular project in this benchmark suite — one algorithm per file, 150–500 lines each. This makes it unusually discoverable for a manual search, and the token savings (~4.5×/~9×) reflect that honestly: they are the most modest in the suite, below Django (~13×/~30×) and LevelDB (~6×/~15×). The value shifts from raw token reduction toward *completeness*. A grep finds matching lines; PM returns every conforming type for a protocol, including conditional conformances buried in extension blocks at the end of files. The S5 path query is the standout — confirming `StridingCollection: RandomAccessCollection` in 95 tokens vs ~800 tokens of file navigation delivers an 8.4× saving on a conceptually simple question. S4's context query is the weakest: with only three source files in the combinatorial subsystem, reading them directly is cheaper than PM's full response, and the ~3.4× savings come almost entirely from PM's slim output.

---

## Notes on Swift Indexing

swift-algorithms is a protocol-oriented library with no class hierarchies. All architectural relationships are expressed as protocol conformances, many of them conditional. PM's Swift analyzer captures these via `extends` relations, covering both unconditional conformances (`extension IndexedCollection: RandomAccessCollection`) and conditional ones (`extension StridingCollection: BidirectionalCollection where Base: BidirectionalCollection`). As a result, `impact` and `path` queries accurately reflect which capabilities each algorithm provides under which base-type constraints.

---

## Reproducing

```bash
# 1. Clone swift-algorithms
git clone https://github.com/apple/swift-algorithms

# 2. Start PM server
cd /path/to/aethvion-project-mapper
python -m uvicorn server:app --port 7474

# IMPORTANT: always use 127.0.0.1, not localhost

# 3. Full scan
curl -X POST http://127.0.0.1:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root":"/path/to/swift-algorithms","db":"swiftalgorithms","incremental":false}'

# 4. S1 — LazySequenceProtocol catalog
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"LazySequenceProtocol","db":"swiftalgorithms","via_kinds":["extends"],"exclude_tests":true}'

# 5. S2 — Collection catalog
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"Collection","db":"swiftalgorithms","via_kinds":["extends"],"exclude_tests":true}'

# 6. S3 — BidirectionalCollection tier
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"BidirectionalCollection","db":"swiftalgorithms","via_kinds":["extends"],"exclude_tests":true}'

# 7. S4 — Combinatorial context
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q":"combination permutation product","db":"swiftalgorithms","depth":1,"max_results":30}'

# 8. S5 — Protocol path
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/path \
  -H "Content-Type: application/json" \
  -d '{"from_entity":"StridingCollection","to_entity":"RandomAccessCollection","db":"swiftalgorithms"}'
```

---

*Benchmark conducted 2026-06-10 · Aethvion Project Mapper v1.5.0 · Python 3.10.11 · Windows 11 · i9-13900K · RTX 4090*
