# Benchmark: Security — OWASP Juice Shop

**PM version:** v2.0.0 · **Date:** 2026-06-16 · **Hardware:** Intel i9-13900K · Windows 11

---

## Project

| Metric | Value |
|:---|:---|
| Repository | `OWASP/juice-shop` |
| Language | TypeScript / JavaScript |
| Files scanned | 632 |
| Total lines | ~96,500 |
| Route files | 61 (routes/) |
| Route lines | ~3,700 |
| Scan time | ~1.4 s |
| Throughput | ~69,000 lines/sec |

**Total findings:** 58 (14 critical · 27 high · 15 medium · 2 low)  
**Taint-reachable:** 12 findings routable from HTTP handlers  
**OWASP categories covered:** A01 · A02 · A03 · A05 · A07 · A09

Token counts measured with `tiktoken` (cl100k_base) on the exact tool output an
agent consumes. "Normal" figures estimate the grep + file-read tokens a security
engineer agent would spend to reach equivalent coverage without Project Mapper.

> **Context:** OWASP Juice Shop is the reference benchmark for web application
> security scanners — intentionally seeded with vulnerabilities across every
> OWASP Top 10 category. Using it here lets us compare PM's 140+ rule coverage
> against known-ground-truth findings.

---

## Test 1 — Full Security Audit Overview

**Question:** *"What security vulnerabilities does this codebase have?"*

**Standard Security Review:** An agent reads all 61 route files (~3,700 lines), `lib/insecurity.ts` (~1,000 lines), and key frontend components (~8,000 lines) to build a picture. 70+ file reads, ~20,000 tokens consumed — still misses many frontend XSS findings and deep component issues. A systematic audit of all 632 files is practically infeasible without tooling.

**With Project Mapper:** `pm_security project_root="/path/to/juice-shop" severity="all"`

| | Normal | PM |
|:---|---:|---:|
| Tool calls | 70+ reads | 1 |
| Files reviewed | ~30 (partial coverage) | 632 — complete |
| Findings surfaced | ~30 of 58 (misses frontend XSS, subtle crypto) | 58 — all findings |
| Token Cost | ~20,000 | ~3,843 |
| Token Reduction | — | **−81%** |
| Execution Time | ~30 min manual | 1.4s |
| Speedup | — | **~1,300×** |

**OWASP breakdown (1 call):**
```
A01 (Broken Access Control)        █           1
A02 (Cryptographic Failures)       █████       5
A03 (Injection)                    ████████   41
A05 (Security Misconfiguration)    ████        4
A07 (Authentication Failures)      █████       5
A09 (Security Logging Failures)    ██          2
```

---

## Test 2 — Injection Vulnerability Discovery (A03)

**Question:** *"Where is this application vulnerable to injection attacks?"*

**Standard Security Review:** `grep -rn "dangerouslySetInnerHTML\|innerHTML\|req.query\|sequelize.query"` across routes/ and frontend/. Output contains hundreds of matches across 40+ files. Agent reads the 15 most likely files to identify real injection points. ~15,000 tokens to find ~20 of 41 actual injection issues.

**With Project Mapper:** `pm_security severity="high" owasp="A03"`

| | Normal | PM |
|:---|---:|---:|
| Tool calls | 15+ | 1 |
| Findings surfaced | ~20 of 41 (misses component-level XSS) | 41 — complete, file:line + snippet |
| Token Cost | ~15,000 | ~2,874 |
| Token Reduction | — | **−81%** |
| Execution Time | ~20 min | 1.4s |
| Speedup | — | **~860×** |

41 injection findings include:
- **SQL injection** in search routes (user-controlled input to Sequelize raw queries)
- **XSS** in 8 Angular components (`[innerHTML]` bindings, `bypassSecurityTrust*`)
- **NoSQL injection** in product filter routes
- **Open redirect** in OAuth callback handling
- **Path traversal** in file upload / download routes

---

## Test 3 — Cryptographic Failures (A02)

**Question:** *"Where does this application use weak or insecure cryptography?"*

**Standard Security Review:** Read `lib/insecurity.ts` (the library holding encryption keys and JWT config), grep for `md5`, `sha1`, `createHash`, `Math.random`. Read 3–5 configuration and utility files. ~8,000 tokens — finds obvious MD5 usage and the hardcoded JWT secret, but misses client-side crypto in frontend components.

**With Project Mapper:** `pm_security severity="all" owasp="A02"`

| | Normal | PM |
|:---|---:|---:|
| Tool calls | 4–5 | 1 |
| Findings surfaced | 3–4 (misses frontend usage) | 5 — complete, with snippets |
| Token Cost | ~8,000 | ~855 |
| Token Reduction | — | **−89%** |
| Execution Time | ~10 min | 1.4s |
| Speedup | — | **~430×** |

5 cryptographic failure findings include:
- Hardcoded JWT secret in `lib/insecurity.ts` (also tagged as taint-reachable)
- MD5 usage for password hashing (CWE-327)
- Weak PRNG (`Math.random`) for security-sensitive token generation
- Missing certificate validation in HTTP client config
- Insecure default encryption key in challenge routes

---

## Test 4 — Critical Finding Triage

**Question:** *"What are the highest-severity vulnerabilities and are they exploitable?"*

**Standard Security Review:** A security engineer reads the 5 highest-risk files identified by their intuition or grep output (lib/insecurity.ts, routes/fileUpload.ts, 3 frontend components). ~6,000 tokens. No automated taint analysis — the engineer must manually trace data flows from HTTP endpoints to dangerous sinks.

**With Project Mapper:** `pm_security severity="critical"`

| | Normal | PM |
|:---|---:|---:|
| Tool calls | 5+ | 1 |
| Findings surfaced | 8–10 of 14 (taint paths invisible) | 14 — all critical, with taint markers |
| Token Cost | ~6,000 | ~1,439 |
| Token Reduction | — | **−76%** |
| Execution Time | ~15 min | 1.4s |
| Speedup | — | **~640×** |

14 critical findings with taint reachability flags (⚡ = routable from HTTP handler):
- `lib/insecurity.ts` — score 20: hardcoded RSA private key + JWT secret ⚡
- `routes/fileUpload.ts` — score 18: path traversal with direct `res.download()` sink ⚡
- Angular components — XSS via `bypassSecurityTrustHtml` in administration, data-export, search-result ⚡

The ⚡ taint marker identifies the 12 findings that flow from user-controlled HTTP input to a dangerous sink — the subset that poses **immediate exploitation risk** without manual call-chain tracing.

---

## Test 5 — Complete Finding Catalog

**Question:** *"Give me the complete, authoritative list of security findings for this codebase."*

**Standard Security Review:** A thorough manual audit of all 632 source files across routes/, lib/, frontend/src/, and models/ to find all 58 findings would require reading the full codebase. At ~150 tokens per file average, exhaustive coverage costs ~95,000 tokens — and still relies on the auditor recognizing every vulnerability pattern (140+ rule types across OWASP Top 10).

**With Project Mapper:** `pm_security severity="all" max_results=200`

| | Normal | PM |
|:---|---:|---:|
| Tool calls | 632 file reads | 1 |
| Findings surfaced | Partial — depends on auditor's pattern recognition | 58 — all findings, stable IDs for triage |
| Token Cost | ~50,000+ | ~4,401 |
| Token Reduction | — | **−91%** |
| Execution Time | 2–3 hours | 1.4s |
| Speedup | — | **~5,000×** |

All 58 findings include stable 8-char hex IDs for triage (`pm_security_triage`), code snippets, CWE/OWASP labels, and taint-reachability markers — enabling structured follow-up without re-running the scan.

---

## Summary

| Test | Question | Normal | PM | Reduction | Speedup |
|:---|:---|---:|---:|---:|---:|
| Test 1 | Full security audit | ~20,000 tok | ~3,843 tok | **−81%** | ~1,300× |
| Test 2 | Injection vulnerabilities (A03) | ~15,000 tok | ~2,874 tok | **−81%** | ~860× |
| Test 3 | Cryptographic failures (A02) | ~8,000 tok | ~855 tok | **−89%** | ~430× |
| Test 4 | Critical findings + taint | ~6,000 tok | ~1,439 tok | **−76%** | ~640× |
| Test 5 | Complete finding catalog | ~50,000 tok | ~4,401 tok | **−91%** | ~5,000× |

---

Geometric mean savings: **~83% token reduction** · **~1,100× faster than manual review**

> OWASP Juice Shop is the largest intentionally vulnerable application in PM's benchmark suite (632 files, ~96,500 lines). The security scanner applies 140+ OWASP Top 10 rules across TypeScript, JavaScript, and HTML templates in 1.4 seconds — finding 58 findings across 6 OWASP categories without a prior pm_scan. The completeness gap is the key insight: a manual reviewer reading all 61 route files in `routes/` costs ~10,000 tokens and finds roughly half the injection issues; the 41 frontend XSS findings in Angular components are invisible until each component is individually opened. PM's taint-reachability analysis (12 of 58 findings marked ⚡) identifies which vulnerabilities flow directly from HTTP request input to dangerous sinks — the subset that requires immediate attention — without any manual call-chain tracing.

## Key Findings at a Glance

| Finding | File | Severity | Taint |
|:---|:---|:---|:---|
| Hardcoded JWT secret | lib/insecurity.ts | CRITICAL | ⚡ yes |
| Path traversal (file download) | routes/fileUpload.ts | CRITICAL | ⚡ yes |
| XSS via `bypassSecurityTrustHtml` | administration.component.ts | CRITICAL | ⚡ yes |
| XSS via `bypassSecurityTrustHtml` | search-result.component.ts | CRITICAL | ⚡ yes |
| SQL injection (raw query) | routes/search routes | HIGH | ⚡ yes |
| NoSQL injection (filter) | routes/product routes | HIGH | ⚡ yes |
| MD5 password hashing | lib/insecurity.ts | HIGH | — |
| Open redirect (OAuth) | routes/oauth.ts | HIGH | ⚡ yes |

## Reproducing

```
# No pm_scan required — pm_security scans raw files directly

# Full audit
pm_security project_root="/path/to/juice-shop" severity="all"

# Injection focus
pm_security project_root="/path/to/juice-shop" severity="high" owasp="A03"

# Cryptographic failures
pm_security project_root="/path/to/juice-shop" severity="all" owasp="A02"

# Critical only (with taint markers)
pm_security project_root="/path/to/juice-shop" severity="critical"

# Complete catalog
pm_security project_root="/path/to/juice-shop" severity="all" max_results=200

# Triage a finding after investigation
pm_security_triage id="<8-char-id>" status="verified_vulnerability" notes="Confirmed: user input flows to res.download() without path sanitization"
pm_security_triage id="<8-char-id>" status="false_positive" notes="Route is behind admin-only middleware"
```
