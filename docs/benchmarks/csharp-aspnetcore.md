# Benchmark: C# — ASP.NET Core 11

**Date:** 2026-06-10 · **Project Mapper:** v1.5.0

> Real numbers from the [ASP.NET Core source repository](https://github.com/dotnet/aspnetcore) (main branch, SDK `11.0.100-preview`). No synthetic data.

---

## The Subject

| | |
|:---|:---|
| Repository | `dotnet/aspnetcore` |
| Version | ASP.NET Core 11 (11.0.100-preview) |
| Date tested | **2026-06-10** |
| Project Mapper | **v1.5.0** |
| C# files analyzed | **11,083** |
| Areas covered | Http, Mvc, Middleware, Security, SignalR, Blazor, gRPC, Identity, … |

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
| C# files analyzed | **11,083** |
| Files skipped (unsupported) | 7 |
| Entities indexed | **32,936** |
| Relations mapped | **63,002** |
| Stubs resolved | 2 · Relations rewired: 2 |
| Errors | **0** |
| Snapshot size | **26.46 MB** |
| Entity files on disk | **0** (PMEntityStore) |
| **Full scan time** | **464 s (~7.7 min)** |

### Incremental Scan (zero file changes)

| | |
|:---|:---|
| Files skipped (hash unchanged) | **11,083** |
| **Incremental scan time** | **5.4 s** |
| **Speedup vs full scan** | **86×** |

> ASP.NET Core is the largest project in this benchmark suite (32,936 entities, 63,002 relations). Its `src/` tree spans 30+ subsystems — Http, Mvc, Middleware, Security, SignalR, Blazor, gRPC, and more — with deeply nested directories.

---

## Query Benchmarks

The primary purpose of Project Mapper is **token reduction**. Each test below compares what an AI agent would consume without PM (Grep + Read source files) against a single PM API call.

> **"Normal" baseline:** ASP.NET Core's source is split across 30+ subsystems under `src/`. Finding interface implementations requires grepping across many directories and reading large C# files (often 300–800 lines each). Token estimates assume the agent already knows which subsystem to search.
>
> **Query latency (v1.5.0):** cold miss ~360 ms (26 MB snapshot load); warm hits 25–330 ms.

---

### A1 — Authentication Handler Hierarchy

**Question:** *"What authentication handler types does ASP.NET Core provide?"*

**Normal approach:** Search `src/Http/Authentication.*`, `src/Security/Authentication.*` for classes implementing `IAuthenticationHandler`. Read `AuthenticationHandler.cs`, then browse subclasses in Cookie, JwtBearer, OAuth, OpenIdConnect, and Negotiate handler packages. 6+ reads across multiple NuGet-boundary packages.

**PM approach:** `impact("IAuthenticationHandler", via_kinds=["extends"], exclude_tests=True)`

**38 handler types returned (cross-package):**
```
IAuthenticationSignOutHandler    IAuthenticationRequestHandler
IAuthenticationSignInHandler     AuthenticationHandler<TOptions>
CookieAuthenticationHandler      JwtBearerHandler
OAuthHandler<TOptions>           OpenIdConnectHandler
NegotiateHandler                 RemoteCertificateAuthenticationHandler
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 6+ | **1** | **1** |
| Tokens consumed | ~7,500 | **~2,315** | **~1,360** |
| Handler types found | Partial (package-by-package) | **38 — complete, cross-package** | **38 — complete** |
| Savings vs Normal | — | **~3.2×** | **~5.5×** |

---

### A2 — Action Result Type Catalog

**Question:** *"What IActionResult types does ASP.NET Core MVC provide?"*

**Normal approach:** Browse `src/Mvc/Mvc.Core/src/` and `src/Mvc/Mvc.*/src/` for result types. Read `ObjectResult.cs` (~380 lines), `StatusCodeResult.cs`, `ContentResult.cs`, `FileResult.cs`, `ViewResult.cs`, and more. 8–10 reads across MVC subsystems.

**PM approach:** `impact("IActionResult", via_kinds=["extends"], exclude_tests=True)`

**60 result types returned (complete, cross-MVC):**
```
ObjectResult      StatusCodeResult    ContentResult
FileResult        ViewResult          JsonResult
RedirectResult    ChallengeResult     ForbidResult
LocalRedirectResult   PartialViewResult   EmptyResult
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 8–10 | **1** | **1** |
| Tokens consumed | ~12,000 | **~2,935** | **~1,497** |
| Result types found | Partial (easily misses ViewResult, Razor Pages variants) | **60 — complete** | **60 — complete** |
| Savings vs Normal | — | **~4.1×** | **~8.0×** |

---

### A3 — Middleware Pipeline Discovery

**Question:** *"What middleware does ASP.NET Core provide?"*

**Normal approach:** Browse `src/Middleware/` and `src/Http/` directories. Read CORS, routing, diagnostics, static files, HTTPS redirection, and session middleware files individually. 6+ reads scattered across subsystems, easy to miss middleware in non-obvious locations (Blazor, gRPC, SignalR).

**PM approach:** `context("middleware pipeline")`

**30 entities returned (8 seeds), ranked by relevance:**
```
[module] src/Middleware/CORS/src/EnableCorsAttribute.cs
[module] src/Middleware/CORS/src/CORSLoggerExtensions.cs
[module] src/Middleware/MiddlewareAnalysis/src/AnalysisBuilder.cs
[class]  ApplicationBuilder
[class]  AnalysisBuilder
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 6+ | **1** | **1** |
| Tokens consumed | ~9,000 | **~1,588** | **~683** |
| Middleware discovered | Partial (directory-by-directory) | **30 entities (ranked by relevance)** | **30 entities (ranked)** |
| Savings vs Normal | — | **~5.7×** | **~13.2×** |

---

### A4 — Pre-Task Context: Authentication & Authorization

**Question:** *"I'm about to work on ASP.NET Core authentication and authorization — what entities should I know about?"*

**Normal approach:** Read `IAuthenticationService.cs`, `AuthorizationPolicy.cs`, `IAuthorizationHandler.cs`, `ClaimsPrincipal.cs`, `AuthenticationSchemeProvider.cs`. 5 reads across multiple packages, ~7,500 tokens. Returns raw file content with no entity ranking.

**PM approach:** `context("authentication authorization")`

**18 entities returned (8 seeds), ranked by relevance:**
```
[class]  IAuthenticationHandler
[class]  AuthenticationHandler
[class]  IAuthorizationHandler
[module] src/Http/Authentication.Abstractions/…
[class]  ClaimsPrincipal
...
```

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 5 | **1** | **1** |
| Tokens consumed | ~7,500 | **~1,218** | **~665** |
| Entities surfaced | 5 files (unranked) | **18 entities (ranked by relevance)** | **18 entities (ranked)** |
| Savings vs Normal | — | **~6.2×** | **~11.3×** |

---

### A5 — DI Wiring Path: IApplicationBuilder → IServiceProvider

**Question:** *"How does the ASP.NET Core application builder connect to the DI service provider?"*

**Normal approach:** Read `WebApplication.cs` (large file combining host + builder), `ApplicationBuilder.cs`, `ServiceCollectionServiceExtensions.cs`. Trace through the implementation manually to understand where services are composed and exposed. 4 reads, ~6,000 tokens.

**PM approach:** `path("IApplicationBuilder", "IServiceProvider")`

**Result (4-hop semantic path):**
```
IApplicationBuilder
  --[extends via WebApplication]--> IAsyncDisposable
  --[extends]--> AsyncDisposableServiceProvider
  --[extends]--> IServiceProvider
```

`WebApplication` implements both `IApplicationBuilder` and `IAsyncDisposable`; its `Services` property is backed by `AsyncDisposableServiceProvider` which wraps the DI container.

| Metric | Normal (Grep/Read) | PM (Full) | PM (Slim) |
|:---|:---|:---|:---|
| Tool calls | 4 | **1** | **1** |
| Tokens consumed | ~6,000 | **~242** | **~119** |
| Connection found | Requires reading WebApplication.cs | **Yes — 4-hop path surfaced** | **Yes** |
| Savings vs Normal | — | **~24.8×** | **~50.4×** |

---

## Headline Numbers

| Test | Question | Normal | PM (Full) | PM (Slim) | Savings (Full) | Savings (Slim) |
|:---|:---|:---|:---|:---|:---|:---|
| A1 | Auth handler hierarchy | ~7,500 tok | **~2,315 tok** | **~1,360 tok** | **3.2×** | **5.5×** |
| A2 | IActionResult types | ~12,000 tok | **~2,935 tok** | **~1,497 tok** | **4.1×** | **8.0×** |
| A3 | Middleware discovery | ~9,000 tok | **~1,588 tok** | **~683 tok** | **5.7×** | **13.2×** |
| A4 | Auth/authorization context | ~7,500 tok | **~1,218 tok** | **~665 tok** | **6.2×** | **11.3×** |
| A5 | IApplicationBuilder → IServiceProvider | ~6,000 tok | **~242 tok** | **~119 tok** | **24.8×** | **50.4×** |

**Geometric mean savings:** PM Full **~6.5×** · PM Slim **~13×** across all five tests.

> A5 (path query) delivers 24.8× savings — WebApplication's dual implementation of IApplicationBuilder + IAsyncDisposable isn't obvious from filenames alone, and tracing it manually requires reading a large composite file. The geometric mean is lower than the Python/Java benchmarks because the large, test-heavy ASP.NET Core codebase inflates response sizes for hierarchy queries (A1/A2 include entities from embedded test projects).

---

## Reproducing

```bash
# 1. Clone ASP.NET Core
git clone https://github.com/dotnet/aspnetcore

# 2. Start PM server
cd /path/to/aethvion-project-mapper
python -m uvicorn server:app --port 7474

# IMPORTANT: always use 127.0.0.1, not localhost

# 3. Full scan
curl -X POST http://127.0.0.1:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root":"/path/to/aspnetcore","db":"aspnetcore","incremental":false}'

# 4. A2 — IActionResult hierarchy
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/impact \
  -H "Content-Type: application/json" \
  -d '{"entity":"IActionResult","db":"aspnetcore","via_kinds":["extends"],"exclude_tests":true}'

# 5. A5 — DI wiring path
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/path \
  -H "Content-Type: application/json" \
  -d '{"from_entity":"IApplicationBuilder","to_entity":"IServiceProvider","db":"aspnetcore"}'

# 6. A4 — Auth context
curl -X POST http://127.0.0.1:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q":"authentication authorization","db":"aspnetcore","depth":1,"max_results":30}'
```

---

*Benchmark conducted 2026-06-10 · Aethvion Project Mapper v1.5.0 · Python 3.10.11 · Windows 11 · i9-13900K · RTX 4090*
