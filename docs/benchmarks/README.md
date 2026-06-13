# Project Mapper Benchmarks

Real-world benchmarks across 11 languages and open-source projects (v1.8.0).

**Date:** 2026-06-13

---

## Summary (Geometric Mean across all 11 projects)

| Mode | Token Reduction | Speedup vs Normal |
|:---|:---|:---|
| **PM Full** | **~87%** | **~380×** faster |
| **PM Slim** | **~92%** | **~380×** faster |

At 100,000 input tokens, PM typically uses **~13,000** (Full) or **~8,000** (Slim) tokens.

---

## Table 1 — Token Reduction

How many tokens does an agent consume to answer a question with and without PM?
**Normal** = Grep + file reads (3–10 tool calls). PM answers in **1 call**.
Geomean token reduction across 5 representative queries per project.

| Project | Language | Files | Entities | Scan | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| [django](benchmark_python_django.md) | Python | 2,411 | 12,066 | 9.5 s | **−91%** | **−93%** | ~97× |
| [spring-framework](benchmark_javaandkotlin_spring_framework.md) | Java / Kotlin | 9,622 | 25,060 | 20.8 s | **−90%** | **−91%** | ~76× |
| [aspnetcore](benchmark_csharp_aspnetcore.md) | C# | 11,083 | 27,813 | 67.7 s | **−83%** | **−87%** | ~46× |
| [wordpress](benchmark_php_wordpress.md) | PHP | 2,295 | 7,757 | 12.0 s | **−92%** | **−93%** | ~1,050× |
| [redis](benchmark_c_redis.md) | C | 781 | 11,093 | 5.5 s | **−84%** | **−92%** | ~32× |
| [hugo](benchmark_go_hugo.md) | Go | ~750 | 5,076 | 3.2 s | **−90%** | **−93%** | ~163× |
| [jekyll](benchmark_ruby_jekyll.md) | Ruby | 161 | 468 | 0.4 s | **−87%** | **−90%** | ~2,000×+ |
| [zod](benchmark_typescriptjs_zod.md) | TypeScript | 405 | 1,688 | 4.5 s | **−90%** | **−93%** | ~1,010× |
| [ripgrep](benchmark_rust_ripgrep.md) | Rust | 100 | 849 | 0.5 s | **−82%** | **−92%** | ~1,500× |
| [leveldb](benchmark_cplusplus_leveldb.md) | C++ | 132 | 603 | 0.4 s | **−88%** | **−94%** | ~1,800× |
| [swift-algorithms](benchmark_swift_algorithms.md) | Swift | 57 | 197 | 0.2 s | **−83%** | **−89%** | ~2,400× |

> Geomean token reduction: **−87% Full** · **−92% Slim** across all 11 projects.
> At 100,000 input tokens, PM Full costs ~13,000 tokens and PM Slim costs ~8,000 — cutting context by **87–92%**.

Scan times measured on Windows 11 (Intel i9-13900K). All scans are cold-start (incremental=false).

---

## Table 2 — Navigation Speed

How fast does PM locate relevant code vs a normal grep + read workflow?

| Project | Language | Normal workflow | PM query time | Speedup |
|:---|:---|---:|---:|---:|
| [django](benchmark_python_django.md) | Python | ~5–10 s | 5–125 ms | **~97×** |
| [spring-framework](benchmark_javaandkotlin_spring_framework.md) | Java / Kotlin | ~5–10 s | 3–125 ms | **~76×** |
| [aspnetcore](benchmark_csharp_aspnetcore.md) | C# | ~5–10 s | 1–100 ms | **~46×** |
| [wordpress](benchmark_php_wordpress.md) | PHP | ~3–6 s | 2–5 ms | **~1,050×** |
| [redis](benchmark_c_redis.md) | C | ~2–3 s | 73–86 ms | **~32×** |
| [hugo](benchmark_go_hugo.md) | Go | ~3–4 s | 3–43 ms | **~163×** |
| [jekyll](benchmark_ruby_jekyll.md) | Ruby | ~2–3 s | <1–3 ms | **~2,000×+** |
| [zod](benchmark_typescriptjs_zod.md) | TypeScript | ~2–8 s | 1–11 ms | **~1,010×** |
| [ripgrep](benchmark_rust_ripgrep.md) | Rust | ~3.5–5 s | 1–5 ms | **~1,500×** |
| [leveldb](benchmark_cplusplus_leveldb.md) | C++ | ~2–4 s | <1–6 ms | **~1,800×** |
| [swift-algorithms](benchmark_swift_algorithms.md) | Swift | ~3–6 s | <1–7 ms | **~2,400×** |

> **Normal workflow:** Grep + read returns thousands of unstructured line matches; agent must still filter and understand them. Time estimate covers grep + reading 3–10 source files.
> **PM query time:** single MCP tool call returning ranked, structured results with entity name · file · line · relations. No additional file reads needed to get started.
> **Speedup note:** Django, Spring, and ASP.NET Core have lower speedups because their context queries hit a warm in-memory cache but still need to rank ~25,000+ entities. Smaller projects (LevelDB 603 entities, Jekyll 468) resolve in under 1ms, producing 1,000×+ speedups. The token reduction is consistently high across all sizes.

---

## Per-Project Reports

Each report includes: project stats · 5 query benchmarks · Full + Slim token comparison · reproducing instructions.

- [benchmark_python_django.md](benchmark_python_django.md) — Python · Django
- [benchmark_javaandkotlin_spring_framework.md](benchmark_javaandkotlin_spring_framework.md) — Java / Kotlin · Spring Framework
- [benchmark_csharp_aspnetcore.md](benchmark_csharp_aspnetcore.md) — C# · ASP.NET Core
- [benchmark_php_wordpress.md](benchmark_php_wordpress.md) — PHP · WordPress
- [benchmark_c_redis.md](benchmark_c_redis.md) — C · Redis
- [benchmark_go_hugo.md](benchmark_go_hugo.md) — Go · Hugo
- [benchmark_ruby_jekyll.md](benchmark_ruby_jekyll.md) — Ruby · Jekyll
- [benchmark_typescriptjs_zod.md](benchmark_typescriptjs_zod.md) — TypeScript · Zod
- [benchmark_rust_ripgrep.md](benchmark_rust_ripgrep.md) — Rust · ripgrep
- [benchmark_cplusplus_leveldb.md](benchmark_cplusplus_leveldb.md) — C++ · LevelDB
- [benchmark_swift_algorithms.md](benchmark_swift_algorithms.md) — Swift · swift-algorithms
