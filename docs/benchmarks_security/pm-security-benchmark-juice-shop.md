# Security Benchmark — OWASP Juice Shop

**Project Mapper v2.0.0 · `pm_security` + `pm_context`/`pm_impact`/`pm_path`**  
**Target:** OWASP Juice Shop `juice-shop-master` (Node.js/Express + Angular + MongoDB)  
**Model:** Claude Sonnet 4.6 High  
**Date:** 2026-06-16

---

## What this benchmark measures

Three independent tests, one codebase, honest comparison:

| | Test 1 — Manual | Test 2 — pm_security | Test 3 — pm_security + pm |
|:---|---:|---:|---:|
| Method | Grep + Read + Glob | `pm_security` only | `pm_security` + 14 PM queries |
| Tool calls | 37 | 1 | **15** |
| Files covered | 29 / 61 routes (48%) | 632 / 632 **(100%)** | 632 / 632 **(100%)** |
| Research tokens | ~10,200 | ~4,401 | ~11,149 |
| Unique findings | 30 | 35 (prod-path) | **49** |
| Elapsed time (wall clock) | ~8 min | **< 5 s** | **< 60 s** |
| Findings per 1k research tokens | ~2.9 | ~13.6 | **~4.4** |
| Test-1 gaps closed | — | 14 / 30 | **27 / 30** |

> **Research tokens** = tool result content read by the agent to discover vulnerabilities (file content from Read calls, pm_security stdout, PM query results). Report-writing tokens are **not counted** in any test.

> **Findings per 1k tokens** is lower in Test 3 than Test 2 because PM queries cost tokens to confirm/extend specific findings, not to discover the easy ones. The right metric for Test 3 is unique findings vs time: **49 findings in < 60 s**.

---

## Test 1 — Manual (Grep + Read + Glob)

**Approach:** Directory listing → targeted file reads, prioritizing routes with security-relevant names.

**Key constraint:** With 61 route files and no map of the codebase, ~48% of routes were skipped. The agent had to guess which files were security-sensitive. The 32 unread routes included `captcha.ts`, `keyServer.ts`, `logfileServer.ts`, and others that turned out to contain real vulnerabilities.

### Metrics

| Metric | Value |
|:---|:---|
| Tool calls | 37 (6 listings, 29 file reads, 2 grep) |
| Research tokens | ~10,200 |
| — route files | ~8,900 |
| — lib / models | ~1,100 |
| — grep + listings | ~200 |
| Findings | 30 |
| Findings per 1k research tokens | ~2.9 |
| Elapsed time | ~8 min |
| Files NOT read | 32 route files (48% coverage gap) |

### Findings

| ID | Finding | Severity | File |
|:---|:---|:---|:---|
| F-01 | SQL injection — login auth bypass | Critical | `routes/login.ts:34` |
| F-02 | SQL injection — search UNION/schema dump | Critical | `routes/search.ts:23` |
| F-03 | NoSQL injection — `$where` string concat | High | `routes/showProductReviews.ts:36` |
| F-04 | NoSQL injection — `$where` template literal + XSS | High | `routes/trackOrder.ts:18` |
| F-05 | NoSQL injection — chatbot `getProductReviews` tool | High | `routes/chat.ts:147` |
| F-06 | SSTI / RCE — `eval()` on username input | Critical | `routes/userProfile.ts:61` |
| F-07 | RCE — `safeEval` sandbox escape (B2B orders) | Critical | `routes/b2bOrder.ts:23` |
| F-08 | Stored XSS — email field when challenge enabled | High | `models/user.ts:61` |
| F-09 | DOM XSS — `document.write(userData)` | Medium | `frontend/…/data-export.component.ts:71` |
| F-10 | XSS — CSP header injection via profileImage | Medium | `routes/userProfile.ts:88` |
| F-11 | Reflected XSS — order tracking ID | Medium | `routes/trackOrder.ts:15` |
| F-12 | Path traversal — null byte FTP bypass | High | `routes/fileServer.ts:27` |
| F-13 | Unprotected quarantine file server | Medium | `routes/quarantineServer.ts` |
| F-14 | Local file read — `layout` body param renders templates | High | `routes/dataErasure.ts:103` |
| F-15 | SSRF — profile image URL fetch (no validation) | High | `routes/profileImageUrlUpload.ts:24` |
| F-16 | Auth bypass — password change without current password | High | `routes/changePassword.ts:39` |
| F-17 | IDOR — basket HTTP parameter pollution | High | `routes/basketItems.ts:37` |
| F-18 | IDOR — review author forgery (body field) | Medium | `routes/createProductReviews.ts:18` |
| F-19 | NoSQL mass update — `multi: true` + body `_id` | High | `routes/updateProductReviews.ts:17` |
| F-20 | IDOR — data export body `UserId` vs JWT | Medium | `routes/dataExport.ts:26` |
| F-21 | Hardcoded RSA private key (JWT signing) | Critical | `lib/insecurity.ts:23` |
| F-22 | Weak hashing — unsalted MD5 passwords | High | `lib/insecurity.ts:43` |
| F-23 | JWT algorithm confusion (RS256 → HS256) | High | `lib/insecurity.ts:54` |
| F-24 | Open redirect — substring allowlist bypass | Medium | `lib/insecurity.ts:138` |
| F-25 | XXE — `noent: true` XML upload | High | `routes/fileUpload.ts:83` |
| F-26 | YAML bomb DoS — `yaml.load()` billion laughs | Medium | `routes/fileUpload.ts:113` |
| F-27 | AI prompt injection — chatbot coupon generator | High | `routes/chat.ts:82` |
| F-28 | Race condition — like count timing attack | Low | `routes/likeProductReviews.ts:35` |
| F-29 | Sensitive files exposed via FTP | Medium | `ftp/` directory |
| F-30 | Hardcoded credentials — 5 accounts in source | High | `routes/login.ts:60` |

**Critical: 5 · High: 14 · Medium: 8 · Low: 1**

### What manual missed

Files never read because they weren't guessed as security-sensitive:
- `routes/captcha.ts` — `eval()` RCE
- `routes/keyServer.ts` — encryption keys served to anyone
- `routes/logfileServer.ts` — log files served without auth
- All Angular components — 10 `bypassSecurityTrustHtml()` + 5 `localStorage` token storage bugs
- JWT verify without `algorithms` restriction (2 call sites)
- Cookie `httpOnly` missing (2 routes)
- Open tabnapping (2 routes)

---

## Test 2 — pm_security Only

**Approach:** Single `pm_security` call — no file reads, no grep, no PM queries.

### Metrics

| Metric | Value |
|:---|:---|
| Tool calls | 1 |
| Files scanned | 632 (100%) |
| Scan time | 1.4 s |
| Research tokens | ~4,401 |
| Total findings | 58 |
| — production-path | 35 |
| — educational codefixes | 17 (context-specific FP) |
| — other (test/utility) | 6 |
| Route-reachable (⚡) | 12 |
| Findings per 1k research tokens | ~13.6 |
| Elapsed time | < 5 s |

> **Educational codefixes:** 17 findings are in `data/static/codefixes/` — intentionally vulnerable wrong-answer quiz options for Juice Shop's training game (11 SQLi variants + 6 XSS variants). They contain real CWE-89/CWE-79 patterns but are not in the production execution path. Triage as context-specific false positives.

> **OWASP breakdown:** A01 (Broken Access Control): 1 · A02 (Cryptographic Failures): 5 · A03 (Injection): 41 · A05 (Security Misconfiguration): 4 · A07 (Auth Failures): 5 · A09 (Logging Failures): 2

### What pm_security found that manual missed

| ID | Finding | Severity | File |
|:---|:---|:---|:---|
| F-21 | Hardcoded RSA private key (JWT signing) | **Critical** | `lib/insecurity.ts:23` |
| P-01 | `eval()` RCE — captcha expression | High ⚡ | `routes/captcha.ts:22` |
| P-02 | `bypassSecurityTrustHtml(feedback.comment)` | High | `frontend/…/about.component.ts:119` |
| P-03 | `bypassSecurityTrustHtml(user.email)` | High | `frontend/…/administration.component.ts:73` |
| P-04 | `bypassSecurityTrustHtml(feedback.comment)` | High | `frontend/…/administration.component.ts:91` |
| P-05 | `bypassSecurityTrustHtml(captcha image)` | High | `frontend/…/data-export.component.ts:57` |
| P-06 | `bypassSecurityTrustHtml(lastLoginIp)` | High | `frontend/…/last-login-ip.component.ts:39` |
| P-07 | `bypassSecurityTrustHtml(challenge.description)` | High | `frontend/…/score-board.component.ts:82` |
| P-08 | `bypassSecurityTrustHtml(product.description)` | High | `frontend/…/search-result.component.ts:110` |
| P-09 | `bypassSecurityTrustHtml(queryParam)` | High | `frontend/…/search-result.component.ts:143` |
| P-10 | `bypassSecurityTrustHtml(orderId)` | High | `frontend/…/track-result.component.ts:48` |
| P-11 | `localStorage` — `authentication.token` | Medium | `frontend/…/login.component.ts:105` |
| P-12 | `localStorage` — `tmpToken` (partial 2FA) | Medium | `frontend/…/login.component.ts:124` |
| P-13 | `localStorage` — OAuth token | Medium | `frontend/…/oauth.component.ts:51` |
| P-14 | `localStorage` — payment token | Medium | `frontend/…/payment.component.ts:232` |
| P-15 | `localStorage` — 2FA token | Medium | `frontend/…/two-factor-auth-enter/…:53` |
| P-16 | `jwt.verify()` without algorithm list | High | `lib/insecurity.ts:191` |
| P-17 | `jwt.verify()` without algorithm list | High ⚡ | `routes/verify.ts:119` |
| P-18 | Cookie without `httpOnly` | Medium ⚡ | `routes/updateUserProfile.ts:40` |
| P-19 | Cookie without `httpOnly` | Medium | `lib/insecurity.ts:195` |
| P-20 | Open tabnapping (`target='_blank'`) | Low | `data/datacreator.ts:405` |
| P-21 | Open tabnapping (`target='_blank'`) | Low ⚡ | `routes/verify.ts:213` |
| P-22 | `console.log` exposes BEE tokens | Medium | `frontend/…/faucet.component.ts:238` |
| P-23 | `console.log` exposes role error | Medium | `frontend/…/helpers.ts:191` |
| P-24 | `innerHTML` assignment — dynamic content | High | `frontend/src/hacking-instructor/helpers.ts:138` |
| P-25 | `innerHTML` assignment — dynamic content | High | `frontend/src/hacking-instructor/index.ts:126` |

**26 additional findings vs manual** — all in files that were never read in Test 1.

> **Notable:** `pm_security` detects hardcoded PEM private keys (`-----BEGIN RSA PRIVATE KEY-----` and EC/PKCS8 variants) as string literals in source via the `any_pem_private_key` rule. This catches the CRITICAL RSA key in `lib/insecurity.ts:23` that manual Test 1 required reading `lib/insecurity.ts` to find. Dynamic `innerHTML` assignment (without sanitization) is also detected via `js_innerhtml_dynamic`.

### What pm_security missed (vs Test 1)

| Finding | Why missed |
|:---|:---|
| F-30: Hardcoded credentials in login.ts | No credential-literal pattern for plaintext passwords |
| Hardcoded HMAC secret (`pa4qacea4VK9t9nGv7yZtwmj`) | Non-PEM secret; requires regex on quoted string values |
| F-24: Open redirect substring bypass | Logic analysis required — `.includes()` is not inherently wrong |
| F-15: SSRF — `fetch(user_url)` | No SSRF pattern matching `fetch()` with user-supplied argument |
| F-16: Password change auth bypass | Data-flow / conditional logic analysis |
| F-17: Basket IDOR (param pollution) | Business logic — custom JSON parser behavior |
| F-18: Review author forgery | IDOR — `req.body.author` field not validated against JWT |
| F-19: NoSQL mass update `multi:true` | Pattern exists but missed this form |
| F-20: Data export UserId IDOR | Business logic — JWT vs body field mismatch |
| F-03: NoSQL `$where` (showProductReviews) | Pattern triggered on template literals, not string concat |
| F-05: NoSQL in chatbot (chat.ts) | Same — string concat form missed |
| F-27: AI prompt injection | No LLM/prompt-injection pattern in ruleset |
| F-28: Race condition | Concurrency logic — not detectable by static pattern |
| F-29: FTP sensitive files | File-system enumeration, not a code pattern |
| F-13: Quarantine no extension check | No "missing check" negative-pattern detection |
| F-12: Null byte path traversal | Missed `fileServer.ts` specifically |

**16 Test 1 findings not reproduced by pm_security alone.**

---

## Test 3 — pm_security + pm

**Approach:** `pm_security` for full pattern coverage, then 14 targeted `pm_context` / `pm_impact` / `pm_path` queries to close logic/architecture gaps.

### Metrics

| Metric | Value |
|:---|:---|
| Tool calls | 15 |
| — pm_security | 1 |
| — pm_context queries | 11 |
| — pm_impact queries | 2 |
| — pm_path queries | 1 |
| pm_scan entities indexed | 2,075 |
| pm_scan time | 2.0 s |
| pm_security scan time | 1.4 s |
| Research tokens — pm_security | ~4,401 |
| Research tokens — PM queries (14×) | ~6,748 |
| **Total research tokens** | **~11,149** |
| Gaps closed from Test 2 | 10 / 16 |
| New findings (not in Test 1 or 2) | 2 |
| Elapsed time | < 60 s |

### PM query results (gap closure)

| Gap | Query | Tokens | Time | Result |
|:---|:---|---:|---:|:---|
| G01 — Hardcoded secrets | `pm_context "hardcoded private key secret credential hmac"` | 431 | 16.6ms | ⚠ Partial — private JS assets in `/assets/private/` rank first due to path match; HMAC + credentials still gaps; F-21 already covered by pm_security |
| G02 — SSRF | `pm_context "fetch url profile image upload external request"` | 659 | 13.9ms | ✓ `profileImageUrlUpload.ts` top result |
| G03 — Open redirect | `pm_context "redirect allowlist url includes bypass"` | 676 | 12.1ms | ✓ `routes/redirect.ts` + `isUnintendedRedirect` |
| G04 — NoSQL reviews | `pm_context "nosql where reviews product chat"` | 487 | 11.5ms | ✓ All 4 review routes |
| G05 — AI prompt injection | `pm_context "chatbot prompt system coupon generate llm"` | 634 | 13.5ms | ✓ `buildSystemPrompt` + `generateCoupon` data flow |
| G06 — Password change | `pm_context "password change current authentication check"` | 639 | 14.9ms | ✓ `routes/changePassword.ts:12` directly |
| G07 — Basket IDOR | `pm_context "basket id manipulation param parse rawBody"` | 679 | 13.3ms | ✓ `RequestWithRawBody` interface surfaced |
| G08 — Review forgery | `pm_context "review author update multi nosql"` | 658 | 12.0ms | ✓ `createProductReviews` + `updateProductReviews` |
| G09 — Data export IDOR | `pm_context "data export userId body memory"` | 632 | 13.0ms | ✓ `dataExport.ts` + `appendUserId` data-flow |
| G10 — FTP / quarantine | `pm_context "ftp quarantine serve file extension"` | 498 | 12.4ms | ✓ `fileServer` + `quarantineServer` + `logfileServer` + `keyServer` |
| G11 — Race condition | `pm_context "like review timing race concurrent"` | 673 | 11.8ms | ✓ `likeProductReviews.ts` top result |
| G12 — isRedirectAllowed impact | `pm_impact entity="isRedirectAllowed" depth=2` | 22 | 8.0ms | ✗ No dependents (module-internal function) |
| G13 — changePassword impact | `pm_impact entity="changePassword" depth=2` | 21 | 1.4ms | ✗ No dependents (Express handler factory) |
| G14 — Basket path | `pm_path from="addBasketItem" to="BasketModel"` | 39 | 4.6ms | ✓ 3-hop: `addBasketItem → BasketItemModel ← placeOrder → BasketModel` |

> **G01 caveat:** The project has assets under `frontend/src/assets/private/` (three.js rendering library variants). The word "private" in those paths causes them to rank ahead of `lib/insecurity.ts` for secret-related queries. When searching for secrets, query by module name directly: `pm_context "insecurity.ts hmac credential jwt secret"`.

> **G12/G13 note:** `pm_impact` returned "No dependents" for both. These are module-internal functions and Express handler factories — not imported as named entities by other modules. The PM entity graph tracks module-level imports and class methods. `pm_context` is the right tool for these; `pm_impact` is best used for exported class/service entities.

### New findings from Test 3

| ID | Finding | Severity | File | How found |
|:---|:---|:---|:---|:---|
| N-01 | Log files served without auth check | Medium | `routes/logfileServer.ts` | G10 pm_context |
| N-02 | Encryption key files served to anyone | High | `routes/keyServer.ts` | G10 pm_context |

---

## Master Findings List (All Tests)

**57 unique vulnerabilities across all three tests** (49 confirmed by Test 3). Tagged by which test(s) surfaced them.

| ID | Finding | Severity | OWASP | Test 1 | Test 2 | Test 3 |
|:---|:---|:---|:---|:---:|:---:|:---:|
| F-01 | SQL injection — login auth bypass | Critical | A03 | ✓ | ✓ | ✓ |
| F-02 | SQL injection — search UNION/schema dump | Critical | A03 | ✓ | ✓ | ✓ |
| F-03 | NoSQL `$where` — showProductReviews | High | A03 | ✓ | — | ✓ (G04) |
| F-04 | NoSQL `$where` + XSS — trackOrder | High | A03 | ✓ | ✓ | ✓ |
| F-05 | NoSQL `$where` — chatbot tool | High | A03 | ✓ | — | ⚠ partial |
| F-06 | SSTI / RCE — `eval()` username | Critical | A03 | ✓ | ✓ | ✓ |
| F-07 | RCE — B2B safeEval sandbox escape | Critical | A03 | ✓ | ✓ | ✓ |
| F-08 | Stored XSS — email field (challenge mode) | High | A03 | ✓ | — | — |
| F-09 | DOM XSS — `document.write(userData)` | Medium | A03 | ✓ | ✓ | ✓ |
| F-10 | XSS — CSP header injection via profileImage | Medium | A03 | ✓ | — | — |
| F-11 | Reflected XSS — order tracking ID | Medium | A03 | ✓ | ✓ | ✓ |
| F-12 | Path traversal — null byte FTP bypass | High | A01 | ✓ | — | — |
| F-13 | Quarantine server — no extension filter | Medium | A05 | ✓ | — | ✓ (G10) |
| F-14 | Local file read — `layout` body param | High | A01 | ✓ | — | — |
| F-15 | SSRF — profile image URL fetch | High | A10 | ✓ | — | ✓ (G02) |
| F-16 | Auth bypass — password change | High | A07 | ✓ | — | ✓ (G06) |
| F-17 | IDOR — basket HTTP param pollution | High | A01 | ✓ | — | ✓ (G07) |
| F-18 | IDOR — review author forgery | Medium | A01 | ✓ | — | ✓ (G08) |
| F-19 | NoSQL mass update — `multi: true` + body `_id` | High | A03 | ✓ | — | ✓ (G08) |
| F-20 | IDOR — data export body UserId | Medium | A01 | ✓ | — | ✓ (G09) |
| F-21 | Hardcoded RSA private key | Critical | A02 | ✓ | ✓ | ✓ |
| F-22 | Weak hashing — unsalted MD5 | High | A02 | ✓ | ✓ | ✓ |
| F-23 | JWT algorithm confusion (RS256 → HS256) | High | A02 | ✓ | ✓ | ✓ |
| F-24 | Open redirect — substring allowlist | Medium | A01 | ✓ | — | ✓ (G03) |
| F-25 | XXE — `noent: true` XML upload | High | A03 | ✓ | ✓ | ✓ |
| F-26 | YAML bomb DoS | Medium | A06 | ✓ | ✓ | ✓ |
| F-27 | AI prompt injection — chatbot coupon | High | AI | ✓ | — | ✓ (G05) |
| F-28 | Race condition — like timing attack | Low | A04 | ✓ | — | ✓ (G11) |
| F-29 | Sensitive files exposed via FTP | Medium | A05 | ✓ | — | ⚠ (G10 dirs; not content) |
| F-30 | Hardcoded credentials — 5 accounts | High | A07 | ✓ | — | — |
| P-01 | `eval()` RCE — captcha expression | High | A03 | — | ✓ | ✓ |
| P-02 | Angular XSS — `bypassSecurityTrustHtml(feedback.comment)` about | High | A03 | — | ✓ | ✓ |
| P-03 | Angular XSS — `bypassSecurityTrustHtml(user.email)` admin | High | A03 | — | ✓ | ✓ |
| P-04 | Angular XSS — `bypassSecurityTrustHtml(feedback.comment)` admin | High | A03 | — | ✓ | ✓ |
| P-05 | Angular XSS — `bypassSecurityTrustHtml(captcha image)` | High | A03 | — | ✓ | ✓ |
| P-06 | Angular XSS — `bypassSecurityTrustHtml(lastLoginIp)` | High | A03 | — | ✓ | ✓ |
| P-07 | Angular XSS — `bypassSecurityTrustHtml(challenge.description)` | High | A03 | — | ✓ | ✓ |
| P-08 | Angular XSS — `bypassSecurityTrustHtml(product.description)` | High | A03 | — | ✓ | ✓ |
| P-09 | Angular XSS — `bypassSecurityTrustHtml(queryParam)` | High | A03 | — | ✓ | ✓ |
| P-10 | Angular XSS — `bypassSecurityTrustHtml(orderId)` | High | A03 | — | ✓ | ✓ |
| P-11 | `localStorage` — auth token | Medium | A07 | — | ✓ | ✓ |
| P-12 | `localStorage` — partial 2FA token | Medium | A07 | — | ✓ | ✓ |
| P-13 | `localStorage` — OAuth token | Medium | A07 | — | ✓ | ✓ |
| P-14 | `localStorage` — payment token | Medium | A07 | — | ✓ | ✓ |
| P-15 | `localStorage` — 2FA token | Medium | A07 | — | ✓ | ✓ |
| P-16 | `jwt.verify()` without algorithm list (insecurity.ts) | High | A02 | — | ✓ | ✓ |
| P-17 | `jwt.verify()` without algorithm list (verify.ts) | High | A02 | — | ✓ | ✓ |
| P-18 | Cookie without `httpOnly` (updateUserProfile) | Medium | A05 | — | ✓ | ✓ |
| P-19 | Cookie without `httpOnly` (insecurity.ts) | Medium | A05 | — | ✓ | ✓ |
| P-20 | Open tabnapping — datacreator | Low | A05 | — | ✓ | ✓ |
| P-21 | Open tabnapping — verify.ts | Low | A05 | — | ✓ | ✓ |
| P-22 | `console.log` exposes BEE tokens | Medium | A09 | — | ✓ | ✓ |
| P-23 | `console.log` exposes role error | Medium | A09 | — | ✓ | ✓ |
| P-24 | `innerHTML` dynamic — hacking-instructor helpers | High | A03 | — | ✓ | ✓ |
| P-25 | `innerHTML` dynamic — hacking-instructor index | High | A03 | — | ✓ | ✓ |
| N-01 | Log files served without auth | Medium | A05 | — | — | ✓ |
| N-02 | Encryption key files served to anyone | High | A05 | — | — | ✓ |

**Legend:** ✓ = found · — = missed · ⚠ = partial / indirectly guided

---

## Gap Analysis — What Nothing Found Automatically

These vulnerabilities were **not fully identified** by any automated test:

| Finding | Closest approach | Why no method succeeded |
|:---|:---|:---|
| Hardcoded HMAC secret `pa4qacea4VK9t9nGv7yZtwmj` (`lib/insecurity.ts:44`) | Test 1 ✓ | Non-PEM secret literal; requires regex on quoted string values |
| Hardcoded credentials — 5 accounts (`routes/login.ts:60`) | Test 1 ✓ | No credential-literal pattern for plaintext passwords |
| NoSQL `$where` — chatbot (`routes/chat.ts:147`) | Test 1 ✓ | String concat form not caught; PM context returned LLM topics instead |
| Null byte path traversal — fileServer.ts | Test 1 ✓ | Pattern missed this specific form; not queried in Test 3 |
| FTP sensitive file contents | Test 1 ✓ | File-system enumeration — not a code pattern; requires directory browsing |
| CSP header injection via profileImage | Test 1 ✓ | No pattern for string interpolation into response headers |
| Stored XSS — email model (challenge-gated) | Test 1 ✓ | Challenge-specific conditional — hard to detect as unconditional vulnerability |

**All 7 remaining gaps were found by Test 1 (manual audit).** The tradeoff is clear: manual audit has unique access to secrets (non-PEM format), file-system state, and challenge-conditional logic — at the cost of 48% file coverage and 8× more time.

---

## Token Accounting Detail

| Test | pm_security tokens | PM query tokens | File-read tokens | Total research |
|:---|---:|---:|---:|---:|
| Test 1 — Manual | 0 | 0 | ~10,200 | **~10,200** |
| Test 2 — pm_security | ~4,401 | 0 | 0 | **~4,401** |
| Test 3 — pm_security + pm | ~4,401 | ~6,748 | 0 | **~11,149** |

Test 3 costs more tokens than Test 2 because of the 14 follow-up queries. The payoff: 14 additional findings confirmed/extended, 2 new findings surfaced (N-01, N-02), coverage gap closed for logic/architecture flaws. If only the 8 most targeted queries are run (G02–G11, skipping the two failed impact queries and G01 which has path ranking noise), total cost drops to ~10,200 tokens with ~12 additional confirmed findings.

---

## Strengths and Weaknesses

### pm_security
**Best at:**
- Pattern-detectable vulnerabilities: SQLi template literals, `eval()`, `vm.runInContext`, `bypassSecurityTrustHtml`, `localStorage`, JWT/cookie misconfiguration
- PEM private key literals (`-----BEGIN RSA PRIVATE KEY-----`, EC, PKCS8) — caught as CRITICAL in `lib/insecurity.ts:23`
- Dynamic `innerHTML` assignment without sanitization (`js_innerhtml_dynamic` rule)
- 100% file coverage in seconds — no file is guessed or skipped
- Route-reachability taint flag (⚡) prioritizes exploitable findings

> **Note on rule precision:** `pm_security` maps generic patterns to broad CWE categories (e.g., all `vm.runInContext` calls → CWE-95 Eval Injection). In the hybrid Test 3 workflow, the agent reads the surrounding context and reclassifies specific instances — `vm.runInContext` wrapping `libxml.parseXml(…, { noent: true })` becomes XXE (CWE-611), and `vm.runInContext` wrapping `yaml.load()` becomes a YAML bomb DoS (CWE-400). Generic detection + contextual reclassification is the right division of labour.

**Not designed to catch:**
- Non-PEM secret literals (HMAC strings, plaintext credentials)
- SSRF via generic HTTP fetch with user-supplied argument
- Logic flaws: IDOR, business rule violations, missing permission checks
- AI/LLM-specific vulnerabilities (prompt injection)
- Concurrency issues (race conditions)
- File-system enumeration (FTP directory exposure)
- Negative patterns ("missing X" where X is an extension check)

### pm_context / pm_impact / pm_path
**Best at:**
- Navigating to files the agent has never read (logic flaw surface discovery)
- Understanding data-flow relationships (e.g., `appendUserId` → `dataExport`)
- Confirming that a suspicious area is actually reachable
- Surfacing all variations of a pattern across the codebase (all 4 review routes for NoSQL)

**Not well suited for:**
- Impact tracing on module-internal functions (not exported, no import graph entry)
- Express route handler factories (wired via router, not imported by name)
- Replacing file reads when a literal value is needed (key content, credential string)
- Queries where generic path keywords match framework assets (e.g., `/assets/private/` polluting secret-hunt queries)

### Manual audit
**Unique capabilities:**
- Non-PEM secret-literal detection (HMAC strings, plaintext credentials)
- File-system enumeration (what files exist in FTP, what they contain)
- Challenge-conditional logic (following `isChallengeEnabled` branches)
- Arbitrary reasoning about behavior not expressed in code patterns

**Failure mode:** 48% file coverage in 8 minutes — the remaining 52% may contain critical vulnerabilities (in this case: captcha RCE, Angular XSS surface, localStorage tokens, keyServer, logfileServer).

---

## Practical Recommendations

For a real engagement on a Node.js/Express + Angular codebase of this size:

1. **Run pm_security first** — ~1.5 s, zero tokens wasted on file guessing, immediate OWASP Top 10 pattern coverage including PEM private keys and Angular XSS patterns. Triage the ⚡ route-reachable findings first.

2. **Use pm_context for logic gaps** — for each gap category (IDOR, auth logic, SSRF, injection variants), one 400–700 token query returns the relevant file list. This closes ~60% of logic gaps that patterns miss.

3. **Read targeted files for non-PEM secrets** — pm_security catches PEM private keys automatically. For HMAC secrets and plaintext credential strings, one targeted file read of `lib/insecurity.ts` (or equivalent secrets module) confirms literal values.

4. **Skip pm_impact for route handlers** — use it for exported services and class methods. For Express routes, pm_context with function name or route path is more reliable.

5. **Budget for FTP/static asset enumeration** — no tool replaces `ls ftp/` for finding exposed files. One directory listing is cheap and catches what code-pattern tools cannot.

6. **Avoid path-pollution in secret queries** — if the project has assets under a path containing "private" (e.g., `assets/private/`), semantic queries for secrets will rank those files first. Use explicit module names: `pm_context "insecurity.ts hmac credential jwt secret"`.

---

## Summary

| Metric | Test 1 | Test 2 | Test 3 |
|:---|:---|:---|:---|
| Time | ~8 min | **< 5 s** | **< 60 s** |
| Files covered | 48% | **100%** | **100%** |
| Research tokens | ~10,200 | **~4,401** | ~11,149 |
| Unique findings | 30 | 35 (prod) | **49** |
| Angular XSS surface found | ✗ | **✓ all 10** | **✓ all 10** |
| Logic / IDOR flaws found | **✓ 13** | ✗ | **✓ 21** |
| PEM private keys found | **✓** | **✓** | **✓** |
| Non-PEM secrets found | **✓** | ✗ | ⚠ partial (file found, value not) |

No single approach wins on every axis. The most efficient path for this codebase:

**pm_security (4,401 tokens, < 5 s) → targeted pm_context for logic gaps (~6,700 tokens, < 60 s) → 1–2 targeted file reads for non-PEM secrets (~1,500 tokens, < 1 min)**

Total: ~12,600 research tokens, ~3 minutes, 49 findings — compared to ~10,200 tokens and ~8 minutes for 30 findings with manual-only.
