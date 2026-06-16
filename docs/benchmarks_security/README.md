# Security Benchmarks

Three-test security audits comparing manual analysis, `pm_security`, and `pm_security + pm` on deliberately vulnerable codebases.

---

## Benchmark format

Each benchmark runs three independent tests on the same target. Each test is standalone — not a follow-up to the previous one.

| Phase | Method | Goal |
|:---|:---|:---|
| 1 — Manual | Grep + Read + Glob only | Establish baseline: what a skilled agent finds without PM tools |
| 2 — pm_security | Single `pm_security` call | Full pattern coverage — OWASP Top 10, 140+ rules, 100% file scan |
| 3 — pm_security + pm | pm_security + targeted PM queries | Close logic/architecture gaps that patterns miss |

**No hiding behind favourable results.** If manual finds something PM misses, it's listed. If PM finds something manual misses, it's listed. Both gaps appear in every benchmark.

---

## Token accounting

**Research tokens only** — tokens the agent reads to discover vulnerabilities:
- Test 1: file content returned from Read calls
- Test 2: pm_security stdout
- Test 3: pm_security stdout + PM query results

Report-writing tokens (generating the markdown) are **not counted** in any phase. This isolates the cost of *finding* vulnerabilities from the cost of *documenting* them.

---

## Benchmarks

| Target | Lang/Stack | Files | Model | Test 1 | Test 2 | Test 3 | Report |
|:---|:---|---:|:---|---:|---:|---:|:---|
| OWASP Juice Shop | Node.js/Express + Angular + MongoDB | 632 | Claude Sonnet 4.6 High | 30 findings, ~10,200 tokens, ~8 min | 35 prod findings, ~4,401 tokens, < 5 s | ~49 findings, ~11,149 tokens, < 60 s | [pm-security-benchmark-juice-shop.md](pm-security-benchmark-juice-shop.md) |

---

## Key results (Juice Shop)

| | Test 1 — Manual | Test 2 — pm_security | Test 3 — pm_security + pm |
|:---|---:|---:|---:|
| Files covered | 48% | **100%** | **100%** |
| Research tokens | ~10,200 | **~4,401** | ~11,149 |
| Unique findings | 30 | 35 (prod) | **~49** |
| Elapsed time | ~8 min | **< 5 s** | **< 60 s** |
| Angular XSS surface | ✗ | **✓** | **✓** |
| PEM private keys found | **✓** | **✓** | **✓** |
| Logic / IDOR flaws | **✓ 13** | ✗ | **✓ 21** |
| Non-PEM secrets (HMAC, credentials) | **✓** | ✗ | ⚠ partial |

**What no phase found automatically:** HMAC secret literals, plaintext credential strings, FTP sensitive file contents. These require non-PEM secret-literal detection patterns or file-system enumeration — documented honestly in each report.

---

## Approach strengths

| Tool | What it's best at | What it misses |
|:---|:---|:---|
| **pm_security** | Pattern-detectable OWASP Top 10 — SQLi, XSS, eval/RCE, JWT, cookies, localStorage | Secrets, SSRF, logic flaws, LLM vulns, race conditions |
| **pm_context** | Navigating to logic flaw surface without reading all files | Can't read literal values; impact trace misses internal functions |
| **Manual audit** | Secrets, FTP enumeration, challenge-conditional logic | Coverage gap — 48% of files in 8 min on a medium codebase |

The most efficient path: **pm_security → targeted pm_context → 1–2 file reads for HMAC/credential secrets** — roughly 12,600 research tokens, ~3 minutes, ~49 findings.
