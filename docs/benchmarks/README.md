# Project Mapper Benchmarks

Real-world benchmarks on open-source projects across 11 languages (v1.7.1).

**Date:** 2026-06-12

---

## Summary (Geometric Mean across all 11 projects)

| Mode       | Token Reduction | Multiplier vs Normal |
|------------|-----------------|----------------------|
| **PM Full**    | 83%             | **~6×** less         |
| **PM Slim**    | 92%             | **~13×** less        |

At 100,000 input tokens, PM typically uses **~17k** (Full) or **~7.7k** (Slim) tokens.

**Navigation Speed:** Agents locate relevant code **39× to >15,000×** faster than grep + manual file reading.

---

## Table 1 — Token Reduction

How many tokens does an agent consume to answer a question with and without PM?
**Normal** = agent uses Grep + file reads (3–6 tool calls). PM answers in **1 call**.
Geomean across 5 representative queries per project.

| Project | Language | Files | Entities | Full scan | Warm scan | Normal (tok) | PM Full | PM Slim | Savings |
|:---|:---|---:|---:|---:|---:|---:|---:|---:|:---|
| [django](python-django.md) | Python | 3,024 | 10,809 | 77 s | 0.69 s | ~12,000 | **~950** | **~400** | **~13× / ~30×** |
| [spring-framework](javaandkotlin-spring-framework.md) | Java/Kotlin | 9,621 | 28,526 | 31.6 s | 0.88 s | ~12,000 | **~1,300** | **~800** | **~9× / ~14×** |
| [aspnetcore](csharp-aspnetcore.md) | C# | 11,077 | 29,963 | 43.3 s | 0.84 s | ~8,200 | **~1,260** | **~640** | **~6.5× / ~13×** |
| [wordpress](php-wordpress.md) | PHP | 2,286 | 7,757 | 56 s | 0.45 s | ~8,200 | **~1,250** | **~730** | **~6.5× / ~11×** |
| [redis](c-redis.md) | C | 839 | 11,093 | 14 s | 0.20 s | ~2,800 | **~710** | **~245** | **~4× / ~11.5×** |
| [hugo](go-hugo.md) | Go | 927 | 5,082 | 15 s | 0.22 s | ~5,000 | **~900** | **~420** | **~5.5× / ~12×** |
| [jekyll](ruby-jekyll.md) | Ruby | 166 | 466 | 1.7 s | 0.08 s | ~2,000 | **~390** | **~190** | **~5× / ~10.5×** |
| [zod](typescriptjs-zod.md) | TypeScript/JS | 405 | 1,688 | 8.8 s | 0.11 s | ~4,800 | **~825** | **~385** | **~5.6× / ~12×** |
| [ripgrep](rust-ripgrep.md) | Rust | 101 | 846 | 1.3 s | 0.05 s | ~3,500 | **~810** | **~360** | **~4× / ~9.5×** |
| [leveldb](cplusplus-leveldb.md) | C++ | 133 | 603 | 1.2 s | 0.05 s | ~3,200 | **~550** | **~205** | **~6× / ~15×** |
| [swift-algorithms](swift-algorithms.md) | Swift | 57 | 194 | 0.6 s | 0.03 s | ~3,100 | **~670** | **~335** | **~4.5× / ~9×** |

> Geometric-mean saving across all 11 benchmarks: **~6× Full** and **~13× Slim**.
> At 100,000 input tokens, PM Full costs ~17,000 tokens and PM Slim costs ~7,700 — cutting context by **83–92%**.

All v1.7.1 timings measured on Windows. Full scans were previously bottlenecked by per-file manifest writes (one JSON flush per entity ingested). v1.7.1 batches all manifest updates into a single flush and removes per-file SCANINFO writes, cutting full scan time ~25×. Warm scans hit the no-op fast path when nothing changed, completing in under 1 s regardless of project size.

---

## Table 2 — Agent Navigation Speed

How fast can an agent locate the relevant code for a task?

**Without PM:** raw text search returns thousands of unstructured line matches — the agent must still read, filter, and understand them to find the actual definition.

**With PM:** one tool call returns ranked, structured results with entity name · file · line · callers · callees. No additional file reads needed to get started.

| Project | grep (no PM) | grep matches | `pm_find` | `pm_ctx slim` | `pm_ctx full` | find speedup | ctx speedup |
|:---|---:|---:|---:|---:|---:|---:|---:|
| csharp-aspnetcore | 46.55 s | 3,468 | 47 ms | 407 ms | 375 ms | **990×** | **114×** |
| ruby-jekyll | 4.14 s | 368 | < 1 ms | 15 ms | < 1 ms | **> 4,000×** | **276×** |
| php-wordpress | 15.64 s | 368 | < 1 ms | 94 ms | 109 ms | **> 15,000×** | **166×** |
| javaandkotlin-spring | 1.56 s | 6,930 | 31 ms | 344 ms | 344 ms | **50×** | **5×** |
| python-django | 1.22 s | 14,678 | 31 ms | 125 ms | 125 ms | **39×** | **10×** |
| go-hugo | 0.52 s | — | < 1 ms | 47 ms | 47 ms | **> 520×** | **11×** |
| typescriptjs-Zod | 0.22 s | 550 | < 1 ms | 16 ms | 16 ms | **> 220×** | **14×** |
| c-redis | 0.22 s | — | 16 ms | 78 ms | 94 ms | **14×** | **3×** |
| swift-algorithms | 0.59 s | 863 | < 1 ms | < 1 ms | < 1 ms | **> 590×** | **> 590×** |
| rust-ripgrep | 0.05 s | 5,566 | < 1 ms | 15 ms | < 1 ms | **> 47×** | **3×** |
| cplusplus-leveldb | 0.02 s | — | < 1 ms | < 1 ms | < 1 ms | **> 20×** | **> 20×** |

> **`pm_ctx slim` vs `pm_ctx full`:** both query the in-memory graph and typically return within 1–410 ms.
> The difference is output size: slim returns name + file:line (avg ~380 tokens); full adds docstrings and summaries (avg ~840 tokens).
> Use slim for navigation; use full when you need to understand an entity without reading the source file.

> **Speedup note:** ripgrep and LevelDB are small enough that grep is also fast. The PM advantage grows with codebase size. For ASP.NET Core (11,084 files), grep takes **46.6 seconds** and returns 3,468 unstructured matches — `pm_find` answers in **47 ms** with a structured result.

> **Warm scan:** all projects under 1,000 files complete warm scans in under 250 ms. Larger projects scale roughly with file count and filesystem stat speed.

---

## Per-Project Reports

Each report includes: full scan stats · query benchmarks · token reduction tables · reproducing instructions.

- [python-django.md](python-django.md) — Python · Django 5.x
- [javaandkotlin-spring-framework.md](javaandkotlin-spring-framework.md) — Java/Kotlin · Spring Framework
- [csharp-aspnetcore.md](csharp-aspnetcore.md) — C# · ASP.NET Core
- [php-wordpress.md](php-wordpress.md) — PHP · WordPress
- [c-redis.md](c-redis.md) — C · Redis
- [go-hugo.md](go-hugo.md) — Go · Hugo
- [ruby-jekyll.md](ruby-jekyll.md) — Ruby · Jekyll
- [typescriptjs-zod.md](typescriptjs-zod.md) — TypeScript/JS · Zod
- [rust-ripgrep.md](rust-ripgrep.md) — Rust · ripgrep
- [cplusplus-leveldb.md](cplusplus-leveldb.md) — C++ · LevelDB
- [swift-algorithms.md](swift-algorithms.md) — Swift · swift-algorithms
