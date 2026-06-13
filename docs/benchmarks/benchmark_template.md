# Benchmark: [Language] — [Project Name]

**PM version:** v0.0.0 · **Date:** YYYY-MM-DD · **Hardware:** [CPU] · [OS]

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `owner/repo` |
| Language | [Language] |
| Files scanned | 0 |
| Total lines | 0 |
| Entities indexed | 0 |
| Scan time | 0.0 s |
| Throughput | 0 lines/sec |

Geometric mean savings: ~0% token reduction · ~× faster navigation

---

## Test 1 — [Title]

**Question:** *"[What an agent would be trying to answer about this codebase]"*

**Standard Workflow (Grep + Read):** [Describe the manual process — grep patterns, which directories, how many file reads, and what it would easily miss.]

**With Project Mapper:** `pm_[tool] "[entity]" [flags]`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 0 | 1 | 1 |
| Entities found | Partial (misses X) | [x] - complete | [x] - complete |
| Token Cost | ~0 | ~0 | ~0 |
| Token Reduction | — | **−0%** | **−0%** |
| Execution Time | ~0s | 0ms | 0ms |
| Speedup | - | 0x | 0x |

---

## Test 2 — [Title]

**Question:** *"[What an agent would be trying to answer about this codebase]"*

**Standard Workflow (Grep + Read):** [Describe the manual process — grep patterns, which directories, how many file reads, and what it would easily miss.]

**With Project Mapper:** `pm_[tool] "[entity]" [flags]`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 0 | 1 | 1 |
| Entities found | Partial (misses X) | [x] - complete | [x] - complete |
| Token Cost | ~0 | ~0 | ~0 |
| Token Reduction | — | **−0%** | **−0%** |
| Execution Time | ~0s | 0ms | 0ms |
| Speedup | - | 0x | 0x |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | [short label] | ~0 tok | ~0 tok | ~0 tok | **−0%** | **−0%** | 0x |
| Test 2 | [short label] | ~0 tok | ~0 tok | ~0 tok | **−0%** | **−0%** | 0x |

---

Geometric mean savings: ~0% token reduction · ~× faster navigation

## Reproducing

```
# 1. Clone Repository
git clone [https://github.com/owner/repo](https://github.com/owner/repo)

# 2. Start PM server
python -m uvicorn server:app --port 7474

# 3. Full scan
curl -X POST [http://127.0.0.1:7474/api/project-mapper/scan](http://127.0.0.1:7474/api/project-mapper/scan) \
  -H "Content-Type: application/json" \
  -d '{"project_root":"/path/to/repo","db":"repo_name","incremental":false}'

# 4. Test 1
pm_[tool] "[entity]" [flags]
```
