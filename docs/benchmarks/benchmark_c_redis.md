# Benchmark: C — Redis

**PM version:** v1.8.0 · **Date:** 2026-06-13 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `redis/redis` |
| Language | C |
| Files scanned | 781 |
| Total lines | ~175,000 |
| Entities indexed | 11,093 |
| Scan time | 5.5 s |
| Throughput | ~31,800 lines/sec |

Geometric mean savings: **−84% token reduction (Full) · −92% token reduction (Slim)** · **~32× faster navigation**

---

## Test 1 — Replication Propagation Functions

**Question:** *"What functions handle replication propagation to replicas in Redis?"*

**Standard Workflow (Grep + Read):** `grep -rn "replicationFeed\|replicationProp" src/`. Identifies `replication.c` as the primary file. Navigate a ~6,000-line file to find the relevant function bodies. AOF-path variants in `aof.c` require a separate search. 4–6 reads, ~3,500 tokens.

**With Project Mapper:** `pm_context "replication propagate slave"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–6 | 1 | 1 |
| Entities found | Partial, misses AOF-path variants | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~3,500 | ~543 | ~281 |
| Token Reduction | — | **−84%** | **−92%** |
| Execution Time | ~3s | 74ms | 73ms |
| Speedup | — | **~41×** | **~41×** |

---

## Test 2 — Keyspace Expiry Functions

**Question:** *"What functions implement Redis's TTL / key-expiry cycle?"*

**Standard Workflow (Grep + Read):** `grep -rn "activeExpire\|subexpire\|expireCycle" src/`. Reads `src/expire.c` (~700 lines) and `src/db.c` sections. Module notification variants in `tests/modules/` require an additional search. 3–4 reads, ~2,500 tokens.

**With Project Mapper:** `pm_context "keyspace TTL expire cycle"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | Partial, misses module notification variants | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~2,500 | ~580 | ~319 |
| Token Reduction | — | **−77%** | **−87%** |
| Execution Time | ~2s | 76ms | 76ms |
| Speedup | — | **~26×** | **~26×** |

---

## Test 3 — Lua Scripting Engine Functions

**Question:** *"What functions manage Redis's Lua scripting engine and script cache?"*

**Standard Workflow (Grep + Read):** `grep -rn "eval\|luaScript\|evalScript" src/`. Identifies `src/script_lua.c` (~2,000 lines) and `src/function_lua.c`. Functions are interleaved across both large files. 4–5 reads, ~3,000 tokens.

**With Project Mapper:** `pm_context "Lua script eval execution"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4–5 | 1 | 1 |
| Entities found | Partial, script_lua.c and function_lua.c interleaved | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~3,000 | ~409 | ~194 |
| Token Reduction | — | **−86%** | **−94%** |
| Execution Time | ~3s | 78ms | 76ms |
| Speedup | — | **~38×** | **~39×** |

---

## Test 4 — ACL Command-Category Functions

**Question:** *"What functions manage ACL command-category permissions in Redis?"*

**Standard Workflow (Grep + Read):** `grep -rn "ACLCategory\|ACLSetSelectorCommand" src/acl.c`. `acl.c` is ~4,000 lines — finding all category-management variants requires navigating a large file. 3–4 reads, ~3,500 tokens.

**With Project Mapper:** `pm_context "ACL user permission command category"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | Partial, 4,000-line file easy to miss variants | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~3,500 | ~378 | ~199 |
| Token Reduction | — | **−89%** | **−94%** |
| Execution Time | ~3s | 85ms | 86ms |
| Speedup | — | **~35×** | **~35×** |

---

## Test 5 — Hash Table Rehashing Functions

**Question:** *"What functions implement Redis's incremental hash table rehashing?"*

**Standard Workflow (Grep + Read):** `grep -rn "Rehash\|rehash" src/dict.c`. `dict.c` is ~1,500 lines. Cross-file variant `kvstoreDictIsRehashingPaused` in `src/kvstore.c` requires a separate search. 3–4 reads, ~2,000 tokens.

**With Project Mapper:** `pm_context "dict hash table rehash expand"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 3–4 | 1 | 1 |
| Entities found | Partial, kvstore.c variant missed without cross-file search | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~2,000 | ~278 | ~148 |
| Token Reduction | — | **−86%** | **−93%** |
| Execution Time | ~2s | 78ms | 79ms |
| Speedup | — | **~26×** | **~25×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Replication propagation | ~3,500 tok | ~543 tok | ~281 tok | **−84%** | **−92%** | ~41× |
| Test 2 | Keyspace TTL expiry | ~2,500 tok | ~580 tok | ~319 tok | **−77%** | **−87%** | ~26× |
| Test 3 | Lua scripting engine | ~3,000 tok | ~409 tok | ~194 tok | **−86%** | **−94%** | ~38× |
| Test 4 | ACL command categories | ~3,500 tok | ~378 tok | ~199 tok | **−89%** | **−94%** | ~35× |
| Test 5 | Dict rehashing | ~2,000 tok | ~278 tok | ~148 tok | **−86%** | **−93%** | ~26× |

---

Geometric mean savings: **−84% token reduction (Full) · −92% token reduction (Slim)** · **~32× faster navigation**

> Redis is a procedural C codebase — no class hierarchy to traverse, so all queries use `pm_context`. Slim mode is particularly effective here: it strips module-level noise (header stubs, test modules) and returns just the ranked function names, delivering −92% token reduction vs −84% for Full. An agent asking "what handles dict rehashing?" gets 8 precise function names in 148 tokens instead of navigating 1,500 lines of dict.c.

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/redis/redis /path/to/redis

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/redis" db="redis" incremental=false

# Test 1
pm_context query="replication propagate slave" db="redis"

# Test 2
pm_context query="keyspace TTL expire cycle" db="redis"

# Test 3
pm_context query="Lua script eval execution" db="redis"

# Test 4
pm_context query="ACL user permission command category" db="redis"

# Test 5
pm_context query="dict hash table rehash expand" db="redis"
```
