# Benchmark: C — Redis

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `redis/redis` |
| Language | C |
| Files scanned | 273 |
| Total lines | ~223,000 |
| Entities indexed | 10,133 |
| Scan time | 6.2 s |
| Throughput | ~36,000 lines/sec |

Geometric mean savings: **~83% token reduction (Full) · ~87% token reduction (Slim)** · **~141× faster navigation**

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + read tokens a skilled agent
would spend reaching the same answer without Project Mapper.

---

## Test 1 — addReply Blast Radius

**Question:** *"What does changing Redis's addReply response-serializer affect?"*

**Standard Workflow (Grep + Read):** `grep -r "addReply" src/` returns hundreds of matches across every command implementation file — t_string.c, t_hash.c, t_list.c, t_set.c, t_zset.c, server.c, networking.c and dozens more. Reading networking.c alone (~2,600 lines) plus 3–4 type files to build a mental model = 8,000–12,000 tokens, and still misses 80+ of the 135 direct callers spread across the codebase.

**With Project Mapper:** `pm_impact "addReply" depth=1`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 8+ | 1 | 1 |
| Entities found | ~50, majority missed | 135 — all direct callers and wrappers | 135 — complete |
| Token Cost | ~12,000 | ~3,592 | ~2,917 |
| Token Reduction | — | **−70%** | **−76%** |
| Execution Time | ~8s | 12ms | 13ms |
| Speedup | — | **~667×** | **~615×** |

---

## Test 2 — lookupKeyRead Blast Radius

**Question:** *"What Redis operations go through the read-key path?"*

**Standard Workflow (Grep + Read):** `grep -r "lookupKeyRead" src/` finds calls in t_string.c, t_list.c, t_hash.c, t_set.c, t_zset.c, debug.c, cluster.c. Reading those files to trace which commands depend on the read-key path = ~8,000 tokens. The transitive callers (commands that call wrappers that call lookupKeyRead) are invisible without further manual tracing.

**With Project Mapper:** `pm_impact "lookupKeyRead" depth=1`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5–7 | 1 | 1 |
| Entities found | ~30 direct, transitive invisible | 103 — direct + transitive | 103 — complete |
| Token Cost | ~8,000 | ~2,735 | ~2,220 |
| Token Reduction | — | **−66%** | **−72%** |
| Execution Time | ~5s | 13ms | 11ms |
| Speedup | — | **~385×** | **~455×** |

---

## Test 3 — Client → Database Struct Relationship

**Question:** *"How does a Redis client connection relate to the database?"*

**Standard Workflow (Grep + Read):** Read `src/server.h` (~4,000 lines) to find the `client` struct and the `redisDb` struct and understand how they relate. Navigating the largest header file in the codebase to extract structural layout costs ~4,000 tokens, and the link between `client` and `redisDb` still requires careful reading.

**With Project Mapper:** `pm_path from_entity="client" to_entity="redisDb"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 2–3 | 1 | 1 |
| Entities found | Requires reading server.h | 2-hop via server.h confirmed | 2-hop confirmed |
| Token Cost | ~4,000 | ~30 | ~30 |
| Token Reduction | — | **−99%** | **−99%** |
| Execution Time | ~3s | 51ms | 53ms |
| Speedup | — | **~59×** | **~57×** |

---

## Test 4 — Persistence System (RDB + AOF)

**Question:** *"What components make up Redis's persistence system?"*

**Standard Workflow (Grep + Read):** Read `rdb.h`, `aof.h`, the opening sections of `rdb.c` and `aof.c`, and the persistence-related fields in `server.h`. 5+ reads, ~8,000 tokens, and the interaction between RDB snapshots and AOF logging (rewrite triggering, BGSAVE sequencing) is spread across multiple files with no obvious entry point.

**With Project Mapper:** `pm_context "persistence RDB AOF snapshot save"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | Partial, RDB/AOF interaction invisible | 25 ranked — complete | 25 ranked — complete |
| Token Cost | ~8,000 | ~553 | ~322 |
| Token Reduction | — | **−93%** | **−96%** |
| Execution Time | ~5s | 89ms | 87ms |
| Speedup | — | **~56×** | **~57×** |

---

## Test 5 — Cluster & Replication Architecture

**Question:** *"What components handle Redis clustering and replication?"*

**Standard Workflow (Grep + Read):** Read `cluster.h` (~500 lines), `replication.c` overview, `sentinel.c` overview. 3+ large reads, ~8,000 tokens. The interplay between Redis Cluster and Sentinel (two separate HA approaches) and how replication is shared between them is not obvious without reading both extensively.

**With Project Mapper:** `pm_context "cluster replication replica failover"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3+ | 1 | 1 |
| Entities found | Partial, Cluster/Sentinel distinction unclear | 29 ranked — complete, both systems | 29 ranked — complete |
| Token Cost | ~8,000 | ~633 | ~350 |
| Token Reduction | — | **−92%** | **−96%** |
| Execution Time | ~5s | 75ms | 74ms |
| Speedup | — | **~67×** | **~68×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | addReply blast radius | ~12,000 tok | ~3,592 tok | ~2,917 tok | **−70%** | **−76%** | ~667× |
| Test 2 | lookupKeyRead blast radius | ~8,000 tok | ~2,735 tok | ~2,220 tok | **−66%** | **−72%** | ~385× |
| Test 3 | client → redisDb path | ~4,000 tok | ~30 tok | ~30 tok | **−99%** | **−99%** | ~59× |
| Test 4 | Persistence (RDB + AOF) | ~8,000 tok | ~553 tok | ~322 tok | **−93%** | **−96%** | ~56× |
| Test 5 | Cluster & replication | ~8,000 tok | ~633 tok | ~350 tok | **−92%** | **−96%** | ~67× |

---

Geometric mean savings: **~83% token reduction (Full) · ~87% token reduction (Slim)** · **~141× faster navigation**

> C's impact queries return larger token counts than other languages because C codebases use a small set of shared primitives everywhere — `addReply` has 135 direct dependents across virtually every command file. Even so, PM's output (3,592 tokens) is 70% smaller than a grep + manual read that still misses most of the picture. Context queries are where C shines: the persistence and cluster queries return 25–29 ranked entities in 553–633 tokens Full versus 5+ large file reads — a 92–93% reduction. T3 is the structural highlight: the `client → redisDb` relationship is buried inside the 4,000-line `server.h`, but PM resolves it in 30 tokens via the entity graph's contains edges.

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/redis/redis /path/to/redis

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/redis" db="redis" incremental=false

# Test 1
pm_impact entity="addReply" db="redis" depth=1

# Test 2
pm_impact entity="lookupKeyRead" db="redis" depth=1

# Test 3
pm_path from_entity="client" to_entity="redisDb" db="redis"

# Test 4
pm_context query="persistence RDB AOF snapshot save" db="redis"

# Test 5
pm_context query="cluster replication replica failover" db="redis"
```
