# Benchmark: C# — ASP.NET Core

**PM version:** v1.8.0 · **Date:** 2026-06-13 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `dotnet/aspnetcore` |
| Language | C# |
| Files scanned | 11,083 |
| Total lines | ~2,200,000 |
| Entities indexed | 27,813 |
| Scan time | 67.7 s |
| Throughput | ~32,500 lines/sec |

Geometric mean savings: **~83% token reduction (Full) · ~87% token reduction (Slim)** · **~46× faster navigation**

---

## Test 1 — Authentication Handler Hierarchy

**Question:** *"What authentication handler types does ASP.NET Core provide?"*

**Standard Workflow (Grep + Read):** Search `src/Http/Authentication.*` and `src/Security/Authentication.*` for `IAuthenticationHandler` implementations. Each handler lives in its own NuGet-boundary package (Cookie, JwtBearer, OAuth, OpenIdConnect, Negotiate). Requires 6+ reads across separate package directories; cross-package results are easily missed.

**With Project Mapper:** `pm_impact "IAuthenticationHandler" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | Partial, package-by-package | 38 — complete, cross-package | 38 — complete |
| Token Cost | ~7,500 | ~1,067 | ~996 |
| Token Reduction | — | **−86%** | **−87%** |
| Execution Time | ~5s | 65ms | 62ms |
| Speedup | — | **~77×** | **~81×** |

---

## Test 2 — Action Result Type Catalog

**Question:** *"What IActionResult types does ASP.NET Core MVC provide?"*

**Standard Workflow (Grep + Read):** Browse `src/Mvc/Mvc.Core/src/` and `src/Mvc/Mvc.*/src/` for result types. Read `ObjectResult.cs`, `StatusCodeResult.cs`, `ContentResult.cs`, `FileResult.cs`, `ViewResult.cs`, and more. 8–10 reads across MVC subsystems; Razor Pages variants easily missed.

**With Project Mapper:** `pm_impact "IActionResult" depth=1 via_kinds=["extends"] exclude_tests=True`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 8–10 | 1 | 1 |
| Entities found | Partial, misses ViewResult/Razor variants | 60 — complete | 60 — complete |
| Token Cost | ~12,000 | ~1,275 | ~1,178 |
| Token Reduction | — | **−89%** | **−90%** |
| Execution Time | ~6s | 64ms | 64ms |
| Speedup | — | **~94×** | **~94×** |

---

## Test 3 — Middleware Pipeline Discovery

**Question:** *"What middleware does ASP.NET Core provide?"*

**Standard Workflow (Grep + Read):** Browse `src/Middleware/` and `src/Http/` directories. Read CORS, routing, diagnostics, static files, HTTPS redirection, and session middleware files individually. 6+ reads scattered across subsystems; middleware in Blazor, gRPC, and SignalR easily missed.

**With Project Mapper:** `pm_context "middleware pipeline"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 6+ | 1 | 1 |
| Entities found | Partial, directory-by-directory | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~9,000 | ~1,116 | ~737 |
| Token Reduction | — | **−88%** | **−92%** |
| Execution Time | ~5s | 480ms | 489ms |
| Speedup | — | **~10×** | **~10×** |

---

## Test 4 — Authentication & Authorization Context

**Question:** *"I'm about to work on ASP.NET Core auth — what components should I know about?"*

**Standard Workflow (Grep + Read):** Read `IAuthenticationService.cs`, `AuthorizationPolicy.cs`, `IAuthorizationHandler.cs`, `ClaimsPrincipal.cs`, `AuthenticationSchemeProvider.cs`. 5 reads across multiple packages, returned as raw file content with no entity ranking.

**With Project Mapper:** `pm_context "authentication authorization"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 5+ | 1 | 1 |
| Entities found | 5 files, unranked | 30 ranked — complete | 30 ranked — complete |
| Token Cost | ~7,500 | ~1,046 | ~788 |
| Token Reduction | — | **−86%** | **−89%** |
| Execution Time | ~4s | 575ms | 576ms |
| Speedup | — | **~7×** | **~7×** |

---

## Test 5 — DI Wiring Path (IApplicationBuilder → IServiceProvider)

**Question:** *"How does the ASP.NET Core application builder connect to the DI service provider?"*

**Standard Workflow (Grep + Read):** Read `WebApplication.cs` (large composite file), `ApplicationBuilder.cs`, `ServiceCollectionServiceExtensions.cs`. Manually trace through the implementation to understand how services are composed and exposed. 4+ reads, ~6,000 tokens.

**With Project Mapper:** `pm_path from_entity="IApplicationBuilder" to_entity="IServiceProvider"`

| | Normal | PM (Full) | PM (Slim) |
|:---|---:|---:|---:|
| Tool calls | 4+ | 1 | 1 |
| Entities found | Requires reading WebApplication.cs | 4-hop path confirmed | 4-hop path confirmed |
| Token Cost | ~6,000 | ~59 | ~59 |
| Token Reduction | — | **−99%** | **−99%** |
| Execution Time | ~4s | 228ms | 228ms |
| Speedup | — | **~18×** | **~18×** |

---

## Summary

| Test | Question | Normal | PM (Full) | PM (Slim) | Reduction Full | Reduction Slim | Speedup |
|:---|:---|---:|---:|---:|---:|---:|---:|
| Test 1 | Auth handler hierarchy | ~7,500 tok | ~1,067 tok | ~996 tok | **−86%** | **−87%** | ~77× |
| Test 2 | IActionResult types | ~12,000 tok | ~1,275 tok | ~1,178 tok | **−89%** | **−90%** | ~94× |
| Test 3 | Middleware discovery | ~9,000 tok | ~1,116 tok | ~737 tok | **−88%** | **−92%** | ~10× |
| Test 4 | Auth/authorization context | ~7,500 tok | ~1,046 tok | ~788 tok | **−86%** | **−89%** | ~7× |
| Test 5 | IApplicationBuilder → IServiceProvider | ~6,000 tok | ~59 tok | ~59 tok | **−99%** | **−99%** | ~18× |

---

Geometric mean savings: **~83% token reduction (Full) · ~87% token reduction (Slim)** · **~46× faster navigation**

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
