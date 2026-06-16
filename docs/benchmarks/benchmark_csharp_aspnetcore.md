# Benchmark: C# — ASP.NET Core

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `dotnet/aspnetcore` |
| Language | C# |
| Files scanned | 10,437 |
| Total lines | ~1,622,500 |
| Entities indexed | 22,923 |
| Scan time | 36.9 s |
| Throughput | ~44,000 lines/sec |

Geometric mean savings: **~89% token reduction (Full) · ~92% token reduction (Slim)** · **~45× faster navigation**

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + read tokens a skilled agent
would spend reaching the same answer without Project Mapper.

---

## Test 1 — Authentication Handler Hierarchy

**Question:** *"What authentication handler types does ASP.NET Core provide?"*

**Standard Workflow (Grep + Read):** Search `src/Http/Authentication.*` and `src/Security/Authentication.*` for `IAuthenticationHandler` implementations. Each handler lives in its own NuGet-boundary package (Cookie, JwtBearer, OAuth, OpenIdConnect, Negotiate). Requires 6+ reads across separate package directories; cross-package results are easily missed.

**With Project Mapper:** `pm_impact "IAuthenticationHandler" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | Partial, package-by-package | 31 — complete, cross-package | 31 — complete |
| Token Cost | ~7,500 | ~1,111 | ~956 |
| Token Reduction | — | **−85%** | **−87%** |
| Execution Time | ~5s | 37ms | 37ms |
| Speedup | — | **~135×** | **~135×** |

---

## Test 2 — Action Result Type Catalog

**Question:** *"What IActionResult types does ASP.NET Core MVC provide?"*

**Standard Workflow (Grep + Read):** Browse `src/Mvc/Mvc.Core/src/` and `src/Mvc/Mvc.*/src/` for result types. Read `ObjectResult.cs`, `StatusCodeResult.cs`, `ContentResult.cs`, `FileResult.cs`, `ViewResult.cs`, and more. 8–10 reads across MVC subsystems; Razor Pages variants easily missed.

**With Project Mapper:** `pm_impact "IActionResult" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 8–10 | 1 | 1 |
| Entities found | Partial, misses ViewResult/Razor variants | 43 — complete, all MVC subsystems | 43 — complete |
| Token Cost | ~12,000 | ~1,537 | ~1,322 |
| Token Reduction | — | **−87%** | **−89%** |
| Execution Time | ~6s | 37ms | 38ms |
| Speedup | — | **~162×** | **~158×** |

---

## Test 3 — Middleware Pipeline Discovery

**Question:** *"What middleware does ASP.NET Core provide?"*

**Standard Workflow (Grep + Read):** Browse `src/Middleware/` and `src/Http/` directories. Read CORS, routing, diagnostics, static files, HTTPS redirection, and session middleware files individually. 6+ reads scattered across subsystems; middleware in Blazor, gRPC, and SignalR easily missed.

**With Project Mapper:** `pm_context "middleware pipeline"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | Partial, directory-by-directory | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~9,000 | ~1,189 | ~738 |
| Token Reduction | — | **−87%** | **−92%** |
| Execution Time | ~5s | 256ms | 253ms |
| Speedup | — | **~20×** | **~20×** |

---

## Test 4 — Authentication & Authorization Context

**Question:** *"I'm about to work on ASP.NET Core auth — what components should I know about?"*

**Standard Workflow (Grep + Read):** Read `IAuthenticationService.cs`, `AuthorizationPolicy.cs`, `IAuthorizationHandler.cs`, `ClaimsPrincipal.cs`, `AuthenticationSchemeProvider.cs`. 5 reads across multiple packages, returned as raw file content with no entity ranking.

**With Project Mapper:** `pm_context "authentication authorization"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | 5 files, unranked | 22 ranked — complete | 22 ranked — complete |
| Token Cost | ~7,500 | ~968 | ~656 |
| Token Reduction | — | **−87%** | **−91%** |
| Execution Time | ~4s | 306ms | 306ms |
| Speedup | — | **~13×** | **~13×** |

---

## Test 5 — DI Wiring Path (IApplicationBuilder → IServiceProvider)

**Question:** *"How does the ASP.NET Core application builder connect to the DI service provider?"*

**Standard Workflow (Grep + Read):** Read `WebApplication.cs` (large composite file), `ApplicationBuilder.cs`, `ServiceCollectionServiceExtensions.cs`. Manually trace through the implementation to understand how services are composed and exposed. 4+ reads, ~6,000 tokens.

**With Project Mapper:** `pm_path from_entity="IApplicationBuilder" to_entity="IServiceProvider"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4+ | 1 | 1 |
| Entities found | Requires reading WebApplication.cs | 4-hop path confirmed | 4-hop path confirmed |
| Token Cost | ~6,000 | ~45 | ~45 |
| Token Reduction | — | **−99%** | **−99%** |
| Execution Time | ~4s | 128ms | 132ms |
| Speedup | — | **~31×** | **~30×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Auth handler hierarchy | ~7,500 tok | ~1,111 tok | ~956 tok | **−85%** | **−87%** | ~135× |
| Test 2 | IActionResult types | ~12,000 tok | ~1,537 tok | ~1,322 tok | **−87%** | **−89%** | ~162× |
| Test 3 | Middleware discovery | ~9,000 tok | ~1,189 tok | ~738 tok | **−87%** | **−92%** | ~20× |
| Test 4 | Auth/authorization context | ~7,500 tok | ~968 tok | ~656 tok | **−87%** | **−91%** | ~13× |
| Test 5 | IApplicationBuilder → IServiceProvider | ~6,000 tok | ~45 tok | ~45 tok | **−99%** | **−99%** | ~31× |

---

Geometric mean savings: **~89% token reduction (Full) · ~92% token reduction (Slim)** · **~45× faster navigation**

> ASP.NET Core is one of the largest codebases in this suite — 10,437 .cs files across dozens of packages (MVC, Blazor, SignalR, Identity, gRPC, Kestrel). The package-boundary problem is where PM pays off most: `IAuthenticationHandler` spans Cookie, JwtBearer, OAuth, OpenIdConnect, and Negotiate packages — a grep + read workflow finds handlers one package at a time and stops when it runs out of obvious directories. PM returns all 31 in a single call. T3 and T4 take 250–300ms because the context engine ranks across the full 22,923-entity index. T5's 4-hop path resolves in 45 tokens what would require reading WebApplication.cs and chasing several indirection layers.

## Reproducing

```
# 1. Clone the target repository
git clone https://github.com/dotnet/aspnetcore /path/to/aspnetcore

# 2. Scan with Project Mapper
pm_scan project_root="/path/to/aspnetcore" db="aspnetcore" incremental=false

# Test 1
pm_impact entity="IAuthenticationHandler" db="aspnetcore" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 2
pm_impact entity="IActionResult" db="aspnetcore" depth=1 via_kinds=["extends"] exclude_tests=true

# Test 3
pm_context query="middleware pipeline" db="aspnetcore"

# Test 4
pm_context query="authentication authorization" db="aspnetcore"

# Test 5
pm_path from_entity="IApplicationBuilder" to_entity="IServiceProvider" db="aspnetcore"
```
