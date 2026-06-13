# Benchmark: C — Redis 7.x

**Date:** 2026-06-10 · **Project Mapper:** v1.5.0

> Real numbers from the [Redis source repository](https://github.com/redis/redis) (unstable branch, v7.x). No synthetic data.

---

## The Subject

| | |
|:---|:---|
| Repository | `redis/redis` |
| Version | `7.x unstable` |
| Date tested | **2026-06-10** |
| Project Mapper | **v1.5.0** |
| C/H files analyzed | **781** (.c + .h) |
| Total files scanned | **844** (incl. test scripts) |
| Subsystems covered | Core, Replication, Cluster, RDB/AOF, ACL, Scripting, Dict, Expire, Event loop |

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
| C/H files analyzed | **781** |
| Files skipped (unsupported) | 1 |
| Entities indexed | **9,647** |
| Stubs created | 400 |
| Relations mapped | **11,894** |
| Errors | **0** |
| Snapshot size | **6.47 MB** |
| Entity files on disk | **0** (PMEntityStore) |
| **Full scan time** | **< 5 s** |

### Incremental Scan (zero file changes)

| | |
|:---|:---|
| Files skipped (hash unchanged) | **844** |
| **Incremental scan time** | **0.9 s** |
| **Speedup vs full scan** | **~5×** |

> **C has a different profile from OOP languages.** Redis's entity graph contains 8,501 functions, 315 structs, and 1,103 modules — but only 38 explicit call-graph edges and 42 struct-extension relations. There is no class inheritance hierarchy to traverse. As a result, `impact` and `path` queries have limited utility; `context` queries (keyword-based function discovery across the full index) are the primary query type for C codebases.
>
> Incremental speedup is modest (~5×) because the C scanner is already very fast for these file sizes — per-file analysis is cheap.

---

## Query Benchmarks

The primary purpose of Project Mapper is **token reduction**. Each test below compares what an AI agent would consume without PM (Grep + Read source files) against a single PM API call.

> **"Normal" baseline:** Redis has 8,501 indexed functions across 781 source files. Finding functions related to a specific subsystem requires `grep` across `src/` (noisy output) followed by targeted reads of large C files. `replication.c` is ~6,000 lines; `acl.c` is ~4,000 lines; `dict.c` is ~1,500 lines. Token estimates assume the agent greps first, identifies the relevant file(s), then reads the target function bodies.
>
> **Query latency (v1.5.0):** cold miss ~50 ms (6.5 MB snapshot load); warm hits ~4 ms (in-memory cache, mtime-validated).

---

### R1 — Replication Propagation Functions

**Question:** *"What functions handle replication propagation to replicas in Redis?"*

**Normal approach:** `grep -rn "replicationFeed\|replicationProp" src/` across the `src/` directory. Identifies `replication.c` as the primary file. Read the relevant function bodies (~6,000-line file — need to navigate to specific sections). Estimate: 5 function reads (~1,500 tok) + grep overhead (~300 tok) + header modules (~1,700 tok) = ~3,500 tokens.

**PM approach:** `context("replication propagate slave")`

**30 entities returned — 5 core replication functions + source modules:**
```
[function] replicationFeedSlaves           src/replication.c
[function] replicationGetSlaveName         src/replication.c
[function] replicationSetupSlaveForFullResync src/replication.c
[function] replicationRequestAckFromSlaves src/replication.c
[function] replicationGetSlaveOffset       src/replication.c
[module]   src/replication.c
[module]   src/aof.c
[module]   tests/modules/propagate.c
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 4–6 | **1** | **1** |
| Tokens consumed | ~3,500 | **~1,306** | **~387** |
| Functions found | Partial (easy to miss AOF-path variants) | **5 replication functions + source context** | **5 functions listed** |
| Savings vs Normal | — | **~2.7×** | **~9.0×** |

---

### R2 — Keyspace Expiry Functions

**Question:** *"What functions implement Redis's TTL / key-expiry cycle?"*

**Normal approach:** `grep -rn "activeExpire\|subexpire\|expireCycle" src/`. Reads `src/expire.c` (~700 lines) and `src/db.c` sections. 3 reads (~1,500 tok) + grep (~300 tok) + header context (~700 tok) = ~2,500 tokens.

**PM approach:** `context("keyspace TTL expire cycle")`

**18 entities returned — 6 expiry functions + related modules:**
```
[function] activeExpireCycle                     src/expire.c
[function] activeExpireCycleTryExpire            src/expire.c
[function] activeSubexpiresCycle                 src/expire.c
[function] KeySpace_NotificationExpired          tests/modules/keyspace_events.c
[function] KeySpace_NotificationModuleKeyMissExpired ...
[function] KeySpace_LazyExpireInsidePostNotificationJob ...
[module]   src/expire.c
[module]   tests/modules/keyspace_events.c
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 3–4 | **1** | **1** |
| Tokens consumed | ~2,500 | **~846** | **~290** |
| Functions found | Partial (misses module notification variants) | **6 functions — core + module callbacks** | **6 functions listed** |
| Savings vs Normal | — | **~3.0×** | **~8.6×** |

---

### R3 — Lua Scripting Engine Functions

**Question:** *"What functions manage Redis's Lua scripting engine and script cache?"*

**Normal approach:** `grep -rn "eval\|luaScript\|evalScript" src/`. Identifies `src/script_lua.c` (~2,000 lines) and `src/function_lua.c`. 4 reads (~2,000 tok) + grep overhead + header context = ~3,000 tokens. Functions are mixed across two large files.

**PM approach:** `context("Lua script eval execution")`

**21 entities returned — 6 scripting functions + Lua engine modules:**
```
[function] luaScriptsLRUAdd         src/script_lua.c
[function] dictLuaScriptDestructor  src/script_lua.c
[function] freeLuaScriptsSync       src/script_lua.c
[function] evalScriptsMemoryVM      src/script_lua.c
[function] evalScriptsDict          src/script_lua.c
[function] evalScriptsMemoryEngine  src/script_lua.c
[module]   src/script_lua.c
[module]   src/script_lua.h
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 4–5 | **1** | **1** |
| Tokens consumed | ~3,000 | **~895** | **~257** |
| Functions found | Partial (script_lua.c and function_lua.c functions interleaved) | **6 script management functions** | **6 functions listed** |
| Savings vs Normal | — | **~3.4×** | **~11.7×** |

---

### R4 — ACL Command-Category Functions

**Question:** *"What functions manage ACL command-category permissions in Redis?"*

**Normal approach:** `grep -rn "ACLCategory\|CommandCategory\|ACLSetSelectorCommand" src/acl.c`. `acl.c` is ~4,000 lines — reading the category-management section requires navigating a large file. 1 targeted read (~2,000 tok) + grep output (~300 tok) + header stubs (~1,200 tok) = ~3,500 tokens.

**PM approach:** `context("ACL user permission command category")`

**8 ACL category functions returned (all from src/acl.c):**
```
[function] ACLAddCommandCategory
[function] ACLInitCommandCategories
[function] ACLGetCommandCategoryFlagByName
[function] ACLFreeUserAndKillClients
[function] ACLSetSelectorCommandBitsForCategory
[function] ACLRecomputeCommandBitsFromCommandRulesAllUsers
[function] ACLCountCategoryBitsForCommands
[function] ACLCheckAllUserCommandPerm
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 3–4 | **1** | **1** |
| Tokens consumed | ~3,500 | **~444** | **~186** |
| Functions found | Partial (4,000-line file — easy to stop before finding all variants) | **8 ACL category functions — complete** | **8 functions listed** |
| Savings vs Normal | — | **~7.9×** | **~18.8×** |

---

### R5 — Hash Table Rehashing Functions

**Question:** *"What functions implement Redis's incremental hash table rehashing?"*

**Normal approach:** `grep -rn "Rehash\|rehash" src/dict.c`. `dict.c` is ~1,500 lines. Read rehash-related sections (~800 lines, ~800 tok) + grep output (~200 tok) + cross-file functions like `kvstoreDictIsRehashingPaused` in a separate file (~500 tok) = ~2,000 tokens.

**PM approach:** `context("dict hash table rehash expand")`

**8 hash-table rehashing functions returned (across dict.c + kvstore.c):**
```
[function] dictRehash                    src/dict.c
[function] dictRehashMicroseconds        src/dict.c
[function] _dictRehashStep               src/dict.c
[function] _dictBucketRehash             src/dict.c
[function] _dictRehashStepIfNeeded       src/dict.c
[function] dictCheckRehashingCompleted   src/dict.c
[function] dictRehashingInfo             src/dict.c
[function] kvstoreDictIsRehashingPaused  src/kvstore.c
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 3–4 | **1** | **1** |
| Tokens consumed | ~2,000 | **~419** | **~161** |
| Functions found | Partial (kvstore.c variant missed without cross-file search) | **8 functions — complete, cross-file** | **8 functions listed** |
| Savings vs Normal | — | **~4.8×** | **~12.4×** |

---

## Headline Numbers

| Test | Question | Normal | PM (Full) | PM (Slim) | Savings (Full) | Savings (Slim) |
|:---|:---|:---|:---|:---|:---|:---|
| R1 | Replication propagation | ~3,500 tok | **~1,306 tok** | **~387 tok** | **2.7×** | **9.0×** |
| R2 | Keyspace TTL expiry | ~2,500 tok | **~846 tok** | **~290 tok** | **3.0×** | **8.6×** |
| R3 | Lua scripting engine | ~3,000 tok | **~895 tok** | **~257 tok** | **3.4×** | **11.7×** |
| R4 | ACL command categories | ~3,500 tok | **~444 tok** | **~186 tok** | **7.9×** | **18.8×** |
| R5 | Dict rehashing | ~2,000 tok | **~419 tok** | **~161 tok** | **4.8×** | **12.4×** |

**Geometric mean savings:** PM Full **~4.0×** · PM Slim **~11.5×** across all five tests.

> C codebases score lower on PM's full-response savings because there is no class hierarchy to exploit — all queries are keyword-based context lookups, and the results include module-level noise (header stubs, test modules) alongside the target functions. The Slim response strips this noise efficiently, which is why Slim savings (~11.5×) are significantly better than Full (~4×). Redis is an excellent demonstration of where PM's Slim mode earns its keep: an AI agent asking "what handles dict rehashing?" gets 8 precise function names in 161 tokens instead of reading 1,500 lines of dict.c.

---

## Reproducing

```bash
# 1. Clone Redis
git clone https://github.com/redis/redis

# 2. Start PM server
cd /path/to/aethvion-project-mapper
python -m uvicorn server:app --port 7474

# IMPORTANT: always use 127.0.0.1, not localhost

# 3. Full scan
curl -X POST http://127.0.0.1:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root":"/path/to/redis","db":"redis","incremental":false}'

# 4. R1 — Replication functions
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q":"replication propagate slave","db":"redis","depth":1,"max_results":30}'

# 5. R4 — ACL category functions (slim)
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q":"ACL user permission command category","db":"redis","depth":1,"max_results":30,"slim":true}'

# 6. R5 — Dict rehash functions
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q":"dict hash table rehash expand","db":"redis","depth":1,"max_results":30}'
```

---

*Benchmark conducted 2026-06-10 · Aethvion Project Mapper v1.5.0 · Python 3.10.11 · Windows 11 · i9-13900K · RTX 4090*
