"""
project_mapper/security_patterns.py
SAST-style security scanner for Project Mapper.

Regex-pattern-based security analysis run on every file during scan.
No additional parsing overhead — patterns are applied to the already-read
source text and line numbers are extracted from match positions.

Coverage: OWASP Top 10 (2021) across Python, JS/TS, PHP, Ruby, Go, Java, C/C++.
Results are stored in ProjectMapper.SECURITY alongside the entity database
and surfaced via the pm_security and pm_security_max MCP tools.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SECURITY_STORE_VERSION = "1.0"
SECURITY_FILE = "ProjectMapper.SECURITY"

_TEST_PATH_FRAGMENTS = frozenset({
    "test", "tests", "spec", "specs", "__tests__", "mock", "mocks",
    "fixture", "fixtures", "e2e", "integration",
})


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class SecurityFinding:
    pattern_id: str
    severity: str       # "critical" | "high" | "medium" | "low"
    file: str           # relative path
    line: int
    language: str
    description: str
    snippet: str        # ≤ 120 chars of source context
    owasp: str

    def to_dict(self) -> dict:
        return {
            "id": self.pattern_id,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "language": self.language,
            "description": self.description,
            "snippet": self.snippet,
            "owasp": self.owasp,
        }


@dataclass
class _Pattern:
    id: str
    severity: str
    owasp: str
    description: str
    languages: frozenset[str]
    regex: re.Pattern
    noise_terms: tuple[str, ...] = field(default_factory=tuple)


def _pat(pid, sev, owasp, desc, langs, pat, noise=(), flags=re.IGNORECASE):
    return _Pattern(
        id=pid, severity=sev, owasp=owasp, description=desc,
        languages=frozenset(langs),
        regex=re.compile(pat, flags),
        noise_terms=tuple(noise),
    )


# ─── Pattern library ──────────────────────────────────────────────────────────
#
# Each pattern targets a specific OWASP Top 10 (2021) category.
# Skip noise_terms suppress findings where the matched snippet contains
# the given substring — used to eliminate comment-only lines and
# common false-positive contexts (config file reads, env vars, etc.).

_PATTERNS: list[_Pattern] = [

    # ── A03 Injection — SQL ───────────────────────────────────────────────────

    _pat("js_sql_tpl_literal", "critical", "A03:2021 Injection",
         "SQL query built with template literal — injection risk",
         {"javascript", "typescript"},
         r'\.(?:query|execute|run)\s*\(\s*`[^`]*\$\{',
         ),

    _pat("js_sql_concat", "critical", "A03:2021 Injection",
         "SQL query built with string concatenation — injection risk",
         {"javascript", "typescript"},
         r'\.(?:query|execute|run)\s*\(\s*(?:"[^"]*"|\'[^\']*\')\s*\+',
         ),

    _pat("py_sql_fstring", "critical", "A03:2021 Injection",
         "SQL query built with f-string — injection risk",
         {"python"},
         r'\.execute\s*\(\s*f["\']',
         noise=()),

    _pat("py_sql_format", "critical", "A03:2021 Injection",
         "SQL query built with % format or .format() — injection risk",
         {"python"},
         r'\.execute\s*\(\s*["\'][^"\']*["\']\.format\s*\(|'
         r'\.execute\s*\(\s*["\'][^"\']*%[sd]',
         noise=()),

    _pat("py_sql_concat", "critical", "A03:2021 Injection",
         "SQL query built with string concatenation — injection risk",
         {"python"},
         r'\.execute\s*\(\s*["\'][^"\']*["\']\s*\+',
         noise=()),

    _pat("php_sql_input", "critical", "A03:2021 Injection",
         "SQL query with direct superglobal input — injection risk",
         {"php"},
         r'(?:mysqli?_query|->query)\s*\([^,)]*\$_(?:GET|POST|REQUEST|COOKIE)',
         noise=()),

    _pat("java_sql_concat", "critical", "A03:2021 Injection",
         "SQL statement built with string concatenation",
         {"java"},
         r'(?:executeQuery|executeUpdate|execute)\s*\(\s*"[^"]*"\s*\+',
         noise=()),

    _pat("go_sql_sprintf", "critical", "A03:2021 Injection",
         "SQL query built with fmt.Sprintf — injection risk",
         {"go"},
         r'\.(?:Query|Exec|QueryRow)\w*\s*\(\s*fmt\.Sprintf',
         noise=()),

    _pat("rb_sql_interp", "critical", "A03:2021 Injection",
         "SQL query with string interpolation of request params",
         {"ruby"},
         r'(?:execute|find_by_sql|where)\s*\(\s*"[^"]*#\{(?:params|request)',
         noise=()),

    # ── A03 Injection — Command execution ─────────────────────────────────────

    _pat("js_eval_dynamic", "high", "A03:2021 Injection",
         "eval() with dynamic argument — code injection risk",
         {"javascript", "typescript"},
         r'\beval\s*\(\s*(?![\s\n]*[\'"])',
         noise=()),

    _pat("js_vm_runin", "high", "A03:2021 Injection",
         "vm.runInContext/NewContext — remote code execution risk",
         {"javascript", "typescript"},
         r'vm\.(?:runInContext|runInNewContext|runInThisContext)\s*\(',
         noise=()),

    _pat("js_child_proc_dynamic", "high", "A03:2021 Injection",
         "child_process exec/spawn with dynamic argument — command injection risk",
         {"javascript", "typescript"},
         r'\b(?:exec|execSync|spawn|spawnSync)\s*\(\s*(?:[^\'",)\n]{0,80}'
         r'(?:req\.|request\.|params|query|body|\$\{)|`[^`]*\$\{)',
         noise=()),

    _pat("py_eval_exec", "high", "A03:2021 Injection",
         "eval() or exec() with non-literal — code execution risk",
         {"python"},
         r'\b(?:eval|exec)\s*\(\s*(?![\s\n]*["\'])',
         noise=()),

    _pat("py_subprocess_shell_true", "high", "A03:2021 Injection",
         "subprocess with shell=True — command injection risk",
         {"python"},
         r'subprocess\.(?:call|run|Popen|check_output|check_call)\s*\([^)]*shell\s*=\s*True',
         noise=()),

    _pat("py_os_system", "high", "A03:2021 Injection",
         "os.system() with dynamic argument — command injection risk",
         {"python"},
         r'\bos\.(?:system|popen)\s*\(\s*(?![\s\n]*["\'])',
         noise=()),

    _pat("php_shell_exec_dynamic", "high", "A03:2021 Injection",
         "PHP shell execution with dynamic argument — command injection risk",
         {"php"},
         r'\b(?:system|exec|shell_exec|passthru|popen|proc_open)\s*\(\s*\$',
         noise=()),

    _pat("php_eval_dynamic", "high", "A03:2021 Injection",
         "PHP eval() with dynamic content — code execution risk",
         {"php"},
         r'\beval\s*\(\s*\$',
         noise=()),

    _pat("rb_eval_dynamic", "high", "A03:2021 Injection",
         "eval/instance_eval with dynamic argument",
         {"ruby"},
         r'\b(?:eval|instance_eval|class_eval|module_eval)\s*\(\s*(?![\s\n]*["\'])',
         noise=()),

    _pat("rb_system_interp", "high", "A03:2021 Injection",
         "Ruby system() or backtick with param interpolation — command injection",
         {"ruby"},
         r'(?:`[^`]*#\{(?:params|request|input|@)|'
         r'system\s*\(\s*"[^"]*#\{(?:params|request))',
         noise=()),

    _pat("c_dangerous_str_funcs", "high", "A03:2021 Injection",
         "Unsafe C string function — buffer overflow risk",
         {"c", "cpp"},
         r'\b(?:strcpy|strcat|gets|sprintf|vsprintf)\s*\(',
         noise=()),

    _pat("c_system_dynamic", "high", "A03:2021 Injection",
         "C system() with potentially dynamic argument",
         {"c", "cpp"},
         r'\bsystem\s*\(\s*(?![\s\n]*")',
         noise=()),

    _pat("c_printf_fmt_vuln", "critical", "A03:2021 Injection",
         "printf/fprintf with variable format string — format string vulnerability",
         {"c", "cpp"},
         r'\b(?:printf|fprintf|dprintf)\s*\(\s*(?![\s\n]*")',
         noise=("stderr,", "stdout,", "stderr ,", "stdout ,")),

    _pat("go_exec_dynamic", "high", "A03:2021 Injection",
         "exec.Command with dynamic argument — command injection risk",
         {"go"},
         r'exec\.Command\s*\([^)]*(?:fmt\.Sprintf|\bos\.Args|\+)',
         noise=()),

    _pat("java_runtime_exec", "high", "A03:2021 Injection",
         "Runtime.getRuntime().exec() — command injection risk",
         {"java"},
         r'Runtime\.getRuntime\(\)\.exec\s*\(',
         noise=()),

    # ── A03 Injection — NoSQL ─────────────────────────────────────────────────

    _pat("js_nosql_where_tpl", "high", "A03:2021 Injection",
         "MongoDB $where with template literal — NoSQL injection risk",
         {"javascript", "typescript"},
         r'\$where\s*:\s*`[^`]*\$\{',
         noise=()),

    _pat("js_nosql_input", "high", "A03:2021 Injection",
         "MongoDB query with request object as filter — NoSQL injection risk",
         {"javascript", "typescript"},
         r'(?:find|findOne|update|updateOne|deleteOne|remove)\s*\(\s*(?:req|request)\.',
         noise=()),

    # ── A03 Injection — SSTI ──────────────────────────────────────────────────

    _pat("py_ssti_render_string", "critical", "A03:2021 Injection",
         "Flask render_template_string with dynamic content — SSTI risk",
         {"python"},
         r'render_template_string\s*\(\s*(?![\s\n]*["\'])',
         noise=()),

    # ── A03 Injection — XSS ───────────────────────────────────────────────────

    _pat("js_innerhtml_dynamic", "high", "A03:2021 Injection",
         "innerHTML assignment with dynamic content — XSS risk",
         {"javascript", "typescript"},
         r'\.innerHTML\s*(?:\+=|=)\s*(?![\s\n]*[\'";])',
         noise=("\"\"", "''")),

    _pat("js_bypass_trust_html", "high", "A03:2021 Injection",
         "bypassSecurityTrustHtml() bypasses Angular XSS protection",
         {"javascript", "typescript"},
         r'bypassSecurityTrust(?:Html|Script|Style|Url|ResourceUrl)\s*\(',
         noise=()),

    _pat("php_echo_unsanitized", "high", "A03:2021 Injection",
         "PHP echo/print of raw superglobal input — XSS risk",
         {"php"},
         r'(?:echo|print)\s+\$_(?:GET|POST|REQUEST|COOKIE)',
         noise=("htmlspecialchars", "htmlentities", "esc_html", "esc_attr")),

    # ── A02 Cryptographic Failures ────────────────────────────────────────────

    _pat("js_weak_hash", "medium", "A02:2021 Cryptographic Failures",
         "MD5 or SHA1 — weak hash, insecure for passwords/signatures",
         {"javascript", "typescript"},
         r'createHash\s*\(\s*["\'](?:md5|sha1)["\']',
         noise=()),

    _pat("py_weak_hash", "medium", "A02:2021 Cryptographic Failures",
         "MD5 or SHA1 — insecure for passwords",
         {"python"},
         r'hashlib\.(?:md5|sha1)\s*\(',
         noise=()),

    _pat("js_jwt_alg_none", "critical", "A02:2021 Cryptographic Failures",
         "JWT algorithm set to 'none' — signature verification bypassed",
         {"javascript", "typescript"},
         r'algorithm(?:s)?\s*:\s*["\']none["\']',
         noise=()),

    _pat("py_jwt_no_verify", "high", "A02:2021 Cryptographic Failures",
         "JWT decoded with signature verification disabled",
         {"python"},
         r'jwt\.decode\s*\([^)]*verify_signature\s*[=:]\s*False',
         noise=()),

    _pat("rb_jwt_alg_none", "critical", "A02:2021 Cryptographic Failures",
         "JWT algorithm set to none — signature verification bypassed",
         {"ruby"},
         r'algorithm\s*[:=]\s*["\']none["\']',
         noise=()),

    _pat("any_hardcoded_secret", "medium", "A02:2021 Cryptographic Failures",
         "Possible hardcoded credential or API key",
         {"python", "javascript", "typescript", "php", "ruby", "go", "java"},
         r'(?:password|passwd|secret|api_key|apikey|access_token|auth_token|'
         r'private_key|client_secret)\s*[=:]\s*["\'][A-Za-z0-9+/!@#$%^&*_\-]{8,}["\']',
         noise=("your_", "example", "placeholder", "TODO", "FIXME",
                "process.env", "os.environ", "getenv", "config.", "settings.",
                "ENV[", "dummy", "fake", "test", "sample", "replace")),

    # ── A01 Broken Access Control ─────────────────────────────────────────────

    _pat("js_open_redirect", "high", "A01:2021 Broken Access Control",
         "Open redirect — res.redirect() with unvalidated request parameter",
         {"javascript", "typescript"},
         r'res\.redirect\s*\(\s*(?:req|request)\.',
         noise=()),

    _pat("py_open_redirect", "high", "A01:2021 Broken Access Control",
         "Open redirect with unvalidated request parameter",
         {"python"},
         r'(?:redirect|HttpResponseRedirect)\s*\(\s*(?:request|req)\.',
         noise=()),

    _pat("js_path_traversal", "medium", "A01:2021 Broken Access Control",
         "path.join/resolve with user-controlled input — path traversal risk",
         {"javascript", "typescript"},
         r'path\.(?:join|resolve)\s*\([^)]*(?:req\.|request\.|params|query|body)',
         noise=()),

    _pat("py_path_traversal", "medium", "A01:2021 Broken Access Control",
         "open() with user-controlled path — path traversal risk",
         {"python"},
         r'open\s*\(\s*(?:request\.|req\.)',
         noise=()),

    _pat("php_file_inclusion", "high", "A01:2021 Broken Access Control",
         "PHP include/require with user input — file inclusion vulnerability",
         {"php"},
         r'\b(?:include|include_once|require|require_once)\s*\(\s*\$_(?:GET|POST|REQUEST|COOKIE)',
         noise=()),

    _pat("php_extract_superglobal", "high", "A01:2021 Broken Access Control",
         "PHP extract() from superglobal — variable injection risk",
         {"php"},
         r'\bextract\s*\(\s*\$_(?:GET|POST|REQUEST|COOKIE|SERVER)',
         noise=()),

    _pat("rb_dynamic_send", "high", "A01:2021 Broken Access Control",
         "Dynamic method dispatch via send() with user input",
         {"ruby"},
         r'\.send\s*\(\s*params\[',
         noise=()),

    # ── A08 Software and Data Integrity Failures ──────────────────────────────

    _pat("py_pickle_load", "high", "A08:2021 Software and Data Integrity Failures",
         "pickle.loads/load — arbitrary code execution with untrusted data",
         {"python"},
         r'pickle\.(?:loads?|Unpickler)\s*\(',
         noise=()),

    _pat("py_yaml_unsafe_load", "high", "A08:2021 Software and Data Integrity Failures",
         "yaml.load() without SafeLoader — arbitrary code execution risk",
         {"python"},
         r'\byaml\.load\s*\(',
         noise=("SafeLoader", "safe_load", "CSafeLoader", "BaseLoader")),

    _pat("php_unserialize_input", "high", "A08:2021 Software and Data Integrity Failures",
         "PHP unserialize() from user input — deserialization attack risk",
         {"php"},
         r'\bunserialize\s*\(\s*\$_(?:GET|POST|REQUEST|COOKIE)',
         noise=()),

    _pat("java_object_stream", "high", "A08:2021 Software and Data Integrity Failures",
         "ObjectInputStream deserialization — potential gadget chain attack",
         {"java"},
         r'new\s+ObjectInputStream\s*\(',
         noise=()),

    _pat("rb_yaml_load_unsafe", "high", "A08:2021 Software and Data Integrity Failures",
         "YAML.load without safe flag — code execution risk",
         {"ruby"},
         r'\bYAML\.load\s*\(',
         noise=("safe_load", "YAML.safe_load", "permitted_classes")),

    # ── A10 Server-Side Request Forgery ───────────────────────────────────────

    _pat("js_ssrf_fetch", "high", "A10:2021 Server-Side Request Forgery",
         "fetch() with URL from request parameter — SSRF risk",
         {"javascript", "typescript"},
         r'\bfetch\s*\(\s*(?:req|request)\.',
         noise=()),

    _pat("js_ssrf_axios", "high", "A10:2021 Server-Side Request Forgery",
         "axios request with URL from request parameter — SSRF risk",
         {"javascript", "typescript"},
         r'axios\.(?:get|post|put|delete|request)\s*\(\s*(?:req|request)\.',
         noise=()),

    _pat("py_ssrf_requests", "high", "A10:2021 Server-Side Request Forgery",
         "requests.get/post with URL from request parameter — SSRF risk",
         {"python"},
         r'requests\.(?:get|post|put|delete|request)\s*\(\s*(?:request|req)\.',
         noise=()),

    # ── A05 Security Misconfiguration ─────────────────────────────────────────

    _pat("js_cors_wildcard", "medium", "A05:2021 Security Misconfiguration",
         "CORS wildcard origin (*) — any origin accepted",
         {"javascript", "typescript"},
         r'(?:"Access-Control-Allow-Origin"\s*[:=]\s*["\']?\*|'
         r'cors\s*\(\s*\{[^}]*origin\s*:\s*["\']?\*)',
         noise=()),

    _pat("js_xxe_noent", "medium", "A05:2021 Security Misconfiguration",
         "XML parser with external entity processing enabled — XXE risk",
         {"javascript", "typescript"},
         r'(?:xml2js|libxmljs|DOMParser|parseString)[^;]{0,200}noent\s*:\s*true',
         noise=()),

    _pat("php_preg_replace_e", "high", "A05:2021 Security Misconfiguration",
         "preg_replace with /e modifier — executes arbitrary PHP code",
         {"php"},
         r"preg_replace\s*\(\s*['\"][^'\"]*\/e",
         noise=()),

    # ── A07 Authentication Failures ───────────────────────────────────────────

    _pat("py_assert_auth", "medium",
         "A07:2021 Identification and Authentication Failures",
         "assert for auth/permission check — disabled in Python -O mode",
         {"python"},
         r'\bassert\b[^\n]*(?:auth|login|admin|permission|role|is_staff|is_superuser|token)',
         noise=("test", "pytest", "unittest")),
]

# Per-language index for fast lookup
_BY_LANGUAGE: dict[str, list[_Pattern]] = {}
for _p in _PATTERNS:
    for _lang in _p.languages:
        _BY_LANGUAGE.setdefault(_lang, []).append(_p)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_DOWNGRADE      = {"critical": "high", "high": "medium", "medium": "low", "low": "info"}


# ─── Public scanner function ──────────────────────────────────────────────────

def _is_test_file(rel_path: str) -> bool:
    parts = {p.lower() for p in Path(rel_path).parts}
    if parts & _TEST_PATH_FRAGMENTS:
        return True
    stem = Path(rel_path).stem.lower()
    return any(frag in stem for frag in (".test", ".spec", "_test", "_spec"))


def _is_comment_line(line: str) -> bool:
    s = line.lstrip()
    return s.startswith(("//", "#", "/*", " *", "<!--", "--"))


def scan_file_security(
    rel_path: str,
    content: str,
    language: str,
) -> list[SecurityFinding]:
    """
    Scan a single file for security issues.
    Returns a list of SecurityFinding sorted by severity (critical first).
    Never raises — exceptions return an empty list.
    """
    try:
        return _scan_impl(rel_path, content, language)
    except Exception:
        return []


def _scan_impl(rel_path: str, content: str, language: str) -> list[SecurityFinding]:
    patterns = _BY_LANGUAGE.get(language)
    if not patterns or not content.strip():
        return []

    is_test = _is_test_file(rel_path)
    lines   = content.splitlines()
    findings: list[SecurityFinding] = []
    seen: set[tuple[str, int]] = set()   # (pattern_id, line_no) dedup

    for pat in patterns:
        for m in pat.regex.finditer(content):
            pos     = m.start()
            line_no = content[:pos].count("\n") + 1
            key     = (pat.id, line_no)
            if key in seen:
                continue

            source_line = lines[line_no - 1] if line_no <= len(lines) else m.group(0)

            if _is_comment_line(source_line):
                continue

            snippet = source_line.strip()[:120]

            if any(noise in snippet for noise in pat.noise_terms):
                continue

            severity = pat.severity
            if is_test:
                severity = _DOWNGRADE.get(severity, "low")
                if severity in ("low", "info"):
                    continue

            seen.add(key)
            findings.append(SecurityFinding(
                pattern_id=pat.id,
                severity=severity,
                file=rel_path,
                line=line_no,
                language=language,
                description=pat.description,
                snippet=snippet,
                owasp=pat.owasp,
            ))

    findings.sort(key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))
    return findings


# ─── Route-handler heuristic (used by pm_security_max) ───────────────────────

_ROUTE_HANDLER_DIRS = frozenset({
    "routes", "route", "controllers", "controller", "api", "apis",
    "endpoints", "endpoint", "handlers", "handler", "actions",
    "views",    # Flask/Django views.py
    "middleware",
})

_ROUTE_HANDLER_STEMS = frozenset({
    "route", "router", "routes", "controller", "handler", "handlers",
    "endpoint", "endpoints", "view", "views", "action", "actions",
    "middleware", "api",
})


def is_route_handler_file(rel_path: str) -> bool:
    parts = {p.lower() for p in Path(rel_path).parts[:-1]}
    if parts & _ROUTE_HANDLER_DIRS:
        return True
    stem = Path(rel_path).stem.lower()
    return stem in _ROUTE_HANDLER_STEMS or any(
        stem.startswith(s) or stem.endswith(s)
        for s in ("route", "controller", "handler", "view", "endpoint")
    )


# ─── SECURITY file storage ────────────────────────────────────────────────────

def read_security_store(db_root: Path) -> dict:
    """Read the SECURITY findings file. Returns empty store on missing/corrupt."""
    p = db_root / SECURITY_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": SECURITY_STORE_VERSION, "findings_by_file": {}}


def write_security_store(
    db_root: Path,
    findings_by_file: dict[str, list],
    pm_version: str = "",
) -> None:
    """Write the SECURITY findings file atomically."""
    data: dict = {
        "version":          SECURITY_STORE_VERSION,
        "scanned_at":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "findings_by_file": findings_by_file,
    }
    if pm_version:
        data["pm_version"] = pm_version
    (db_root / SECURITY_FILE).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
