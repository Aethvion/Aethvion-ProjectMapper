"""
project_mapper/security_patterns.py
SAST-style security scanner for Project Mapper.

Regex-pattern-based static analysis — patterns are applied to source text,
no AST or extra parsing required.  Run on-demand via the pm_security MCP tool
(never during normal pm_scan so it adds zero overhead there).

Coverage: OWASP Top 10 (2021), ~112 patterns across Python, JS/TS, PHP, Ruby,
Go, Java, C#, and C/C++.  Findings are written to .SECURITYSNAPSHOT in the
project root for persistent tracking (open / fixed / acknowledged / false_positive).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

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

    # ── C# (ASP.NET / .NET) ───────────────────────────────────────────────────
    # A03 Injection — SQL

    _pat("cs_sql_concat", "critical", "A03:2021 Injection",
         "SqlCommand built with string concatenation — SQL injection risk",
         {"csharp"},
         r'new\s+Sql(?:Command|DataAdapter)\s*\(\s*(?:"[^"]*"\s*\+|'
         r'\$"[^"]*\{|string\.Format\s*\()',
         noise=()),

    _pat("cs_sql_interpolation", "critical", "A03:2021 Injection",
         "SqlCommand with interpolated string — SQL injection risk",
         {"csharp"},
         r'(?:CommandText|\.Query)\s*[+]?=\s*\$"[^"]*\{',
         noise=()),

    _pat("cs_ef_raw_sql", "critical", "A03:2021 Injection",
         "Entity Framework raw SQL with string interpolation — injection risk",
         {"csharp"},
         r'\.(?:FromSqlRaw|ExecuteSqlRaw|ExecuteSqlCommand)\s*\(\s*(?:\$"|'
         r'[A-Za-z_]\w*\s*\+|string\.Format)',
         noise=()),

    # A03 Injection — Command / Code

    _pat("cs_process_start_dynamic", "high", "A03:2021 Injection",
         "Process.Start with dynamic argument — command injection risk",
         {"csharp"},
         r'Process\.Start\s*\(\s*(?![\s\n]*@?")',
         noise=()),

    _pat("cs_response_write_raw", "high", "A03:2021 Injection",
         "Response.Write with unencoded value — XSS risk",
         {"csharp"},
         r'Response\.Write\s*\(\s*(?![\s\n]*@?")',
         noise=("HtmlEncode", "Encode", "Sanitize")),

    _pat("cs_html_raw", "high", "A03:2021 Injection",
         "@Html.Raw() bypasses Razor HTML encoding — XSS risk",
         {"csharp"},
         r'Html\.Raw\s*\(\s*(?![\s\n]*@?")',
         noise=()),

    _pat("cs_ldap_injection", "high", "A03:2021 Injection",
         "DirectorySearcher filter built with concatenation — LDAP injection risk",
         {"csharp"},
         r'new\s+DirectorySearcher\s*\(\s*(?:[^)]*\+|'
         r'\$"[^"]*\{)',
         noise=()),

    # A02 Cryptographic Failures

    _pat("cs_weak_hash", "medium", "A02:2021 Cryptographic Failures",
         "Weak hash algorithm (MD5/SHA1/DES/RC2/TripleDES) — insecure for passwords/signatures",
         {"csharp"},
         r'\b(?:MD5|SHA1|DESCrypto|RC2Crypto|TripleDES|RijndaelManaged)'
         r'(?:CryptoServiceProvider|Managed|\.Create)\s*[\(\.]',
         noise=()),

    _pat("cs_ssl_validation_disabled", "high", "A02:2021 Cryptographic Failures",
         "TLS/SSL certificate validation disabled — MITM attack risk",
         {"csharp"},
         r'(?:ServerCertificateValidationCallback\s*=(?:[^;]{0,80}true|'
         r'[^;]{0,80}DangerousAcceptAny)|'
         r'ServicePointManager\.(?:ServerCertificateValidationCallback|SecurityProtocol))',
         noise=()),

    _pat("cs_jwt_validation_disabled", "high", "A02:2021 Cryptographic Failures",
         "JWT validation flag disabled — token verification bypassed",
         {"csharp"},
         r'(?:ValidateSignature|RequireSignedTokens|ValidateIssuer|'
         r'ValidateAudience|ValidateLifetime)\s*=\s*false',
         noise=()),

    # A08 Software and Data Integrity Failures

    _pat("cs_binary_formatter", "critical", "A08:2021 Software and Data Integrity Failures",
         "BinaryFormatter.Deserialize — arbitrary code execution (banned in .NET 5+)",
         {"csharp"},
         r'\bBinaryFormatter\b',
         noise=()),

    _pat("cs_json_type_handling", "high", "A08:2021 Software and Data Integrity Failures",
         "Newtonsoft.Json TypeNameHandling.All — unsafe deserialization risk",
         {"csharp"},
         r'TypeNameHandling\s*=\s*TypeNameHandling\.(?:All|Objects|Arrays|Auto)',
         noise=()),

    _pat("cs_object_state_formatter", "high", "A08:2021 Software and Data Integrity Failures",
         "ObjectStateFormatter/NetDataContractSerializer — unsafe deserialization",
         {"csharp"},
         r'\b(?:ObjectStateFormatter|NetDataContractSerializer|'
         r'SoapFormatter|LosFormatter)\s*[\(\.]',
         noise=()),

    # A01 Broken Access Control

    _pat("cs_path_traversal", "medium", "A01:2021 Broken Access Control",
         "File I/O with user-controlled path — path traversal risk",
         {"csharp"},
         r'(?:File\.(?:ReadAllText|ReadAllBytes|OpenRead|WriteAllText|WriteAllBytes|'
         r'AppendAllText)|Path\.Combine|new\s+FileStream)\s*\([^)]*'
         r'(?:Request\.|HttpContext\.|query\[|route\[|param)',
         noise=()),

    _pat("cs_open_redirect", "high", "A01:2021 Broken Access Control",
         "Response.Redirect with request-derived URL — open redirect risk",
         {"csharp"},
         r'(?:Response\.Redirect|Redirect(?:Permanent)?)\s*\([^)]*'
         r'(?:Request\.|HttpContext\.Request|query\[|route\[|\burl\b)',
         noise=("IsLocalUrl", "Url.IsLocal", "localRedirect", "LocalRedirect")),

    # A05 Security Misconfiguration

    _pat("cs_cors_allow_any", "medium", "A05:2021 Security Misconfiguration",
         "CORS AllowAnyOrigin() — unrestricted cross-origin access",
         {"csharp"},
         r'\.AllowAnyOrigin\s*\(\s*\)',
         noise=()),

    _pat("cs_developer_exception_page", "low", "A05:2021 Security Misconfiguration",
         "UseDeveloperExceptionPage() — may expose stack traces in production",
         {"csharp"},
         r'app\.UseDeveloperExceptionPage\s*\(\s*\)',
         noise=("env.IsDevelopment", "IsDevelopment", "isDevelopment")),

    # A07 Authentication Failures

    _pat("cs_allow_anonymous", "medium",
         "A07:2021 Identification and Authentication Failures",
         "[AllowAnonymous] on method/controller — auth intentionally bypassed",
         {"csharp"},
         r'\[AllowAnonymous\]',
         noise=()),

    _pat("cs_ignore_antiforgery", "medium",
         "A07:2021 Identification and Authentication Failures",
         "[IgnoreAntiForgeryToken] disables CSRF protection",
         {"csharp"},
         r'\[IgnoreAntiforgeryToken\]',
         noise=()),

    # A10 Server-Side Request Forgery

    _pat("cs_ssrf_httpclient", "high", "A10:2021 Server-Side Request Forgery",
         "HttpClient request with user-controlled URL — SSRF risk",
         {"csharp"},
         r'(?:_?httpClient|HttpClient\b)[^;]{0,60}'
         r'\.(?:GetAsync|PostAsync|SendAsync|GetStringAsync)\s*\([^)]*'
         r'(?:Request\.|query\[|route\[|\burl\b|\buri\b)',
         noise=()),

    # ── Java additions ────────────────────────────────────────────────────────

    _pat("java_weak_hash", "medium", "A02:2021 Cryptographic Failures",
         "Weak hash algorithm (MD5/SHA-1) — insecure for passwords/signatures",
         {"java"},
         r'MessageDigest\.getInstance\s*\(\s*"(?:MD5|SHA-1|SHA1)"',
         noise=()),

    _pat("java_ssl_trust_all", "high", "A02:2021 Cryptographic Failures",
         "X509TrustManager with empty or trivially trusting body — MITM attack risk",
         {"java"},
         r'(?:checkClientTrusted|checkServerTrusted|getAcceptedIssuers)'
         r'[^}]{0,80}\{\s*(?:return\s*null\s*;?\s*)?\}',
         noise=()),

    _pat("java_xxe_enabled", "high", "A05:2021 Security Misconfiguration",
         "XML parser with external entity processing enabled — XXE risk",
         {"java"},
         r'setFeature\s*\(\s*"[^"]*(?:FEATURE_EXTERNAL|external.general.entities)',
         noise=("false",)),

    _pat("java_ssrf_urlopen", "high", "A10:2021 Server-Side Request Forgery",
         "URL.openConnection() with request-derived value — SSRF risk",
         {"java"},
         r'new\s+URL\s*\([^)]*(?:request\.getParameter|getQueryString|'
         r'getHeader|pathVariable)\s*\(',
         noise=()),

    _pat("java_open_redirect", "high", "A01:2021 Broken Access Control",
         "response.sendRedirect() with request parameter — open redirect risk",
         {"java"},
         r'(?:response|resp)\.sendRedirect\s*\([^)]*'
         r'request\.getParameter\s*\(',
         noise=("isLocalUrl", "validateRedirect")),

    _pat("java_path_traversal", "medium", "A01:2021 Broken Access Control",
         "new File() with user-controlled path — path traversal risk",
         {"java"},
         r'new\s+File\s*\([^)]*request\.getParameter\s*\(',
         noise=()),

    # ── Go additions ──────────────────────────────────────────────────────────

    _pat("go_weak_hash", "medium", "A02:2021 Cryptographic Failures",
         "Weak hash algorithm (MD5/SHA1) — insecure for passwords/signatures",
         {"go"},
         r'\b(?:md5|sha1)\.New\s*\(',
         noise=()),

    _pat("go_ssrf_http_get", "high", "A10:2021 Server-Side Request Forgery",
         "http.Get/Post with request-derived URL — SSRF risk",
         {"go"},
         r'http\.(?:Get|Post|Do)\s*\([^)]*r\.(?:URL|Form|PostForm|'
         r'URL\.Query|FormValue)',
         noise=()),

    _pat("go_cors_wildcard", "medium", "A05:2021 Security Misconfiguration",
         "CORS AllowOrigins with wildcard — unrestricted cross-origin access",
         {"go"},
         r'AllowOrigins\s*:\s*\[\s*]string\s*\{[^}]*"\*"',
         noise=()),

    # ── A02 Cryptographic Failures — Insecure random / cipher ─────────────────

    _pat("js_math_random_token", "high", "A02:2021 Cryptographic Failures",
         "Math.random() for security token/secret — not cryptographically secure",
         {"javascript", "typescript"},
         r'(?:const|let|var)\s+\w*(?:token|secret|password|nonce|csrf|otp|salt)\w*\s*=\s*[^;\n]*Math\.random\s*\(',
         noise=()),

    _pat("js_crypto_create_cipher", "medium", "A02:2021 Cryptographic Failures",
         "crypto.createCipher() is deprecated (no IV) — use createCipheriv() with an explicit IV",
         {"javascript", "typescript"},
         r'\bcrypto\.createCipher\s*\(',
         noise=("createCipheriv",)),

    _pat("go_tls_insecure_skip", "high", "A02:2021 Cryptographic Failures",
         "InsecureSkipVerify: true — TLS certificate validation disabled, MITM attack risk",
         {"go"},
         r'InsecureSkipVerify\s*:\s*true',
         noise=()),

    _pat("java_ecb_mode", "high", "A02:2021 Cryptographic Failures",
         "AES/ECB cipher mode — deterministic, leaks data patterns",
         {"java"},
         r'Cipher\.getInstance\s*\(\s*"[^"]*ECB',
         noise=()),

    _pat("cs_ecb_mode", "high", "A02:2021 Cryptographic Failures",
         "ECB cipher mode — deterministic, leaks identical plaintext blocks",
         {"csharp"},
         r'\.Mode\s*=\s*CipherMode\.ECB',
         noise=()),

    # ── A03 Injection — Function constructor / document.write / React ─────────

    _pat("js_function_constructor", "high", "A03:2021 Injection",
         "new Function() with arguments — equivalent to eval(), arbitrary code execution risk",
         {"javascript", "typescript"},
         r'\bnew\s+Function\s*\(\s*(?![\s\n]*\))',
         noise=()),

    _pat("js_document_write_dyn", "high", "A03:2021 Injection",
         "document.write() with dynamic content — XSS risk",
         {"javascript", "typescript"},
         r'document\.write\s*\(\s*(?![\s\n]*[\'"])',
         noise=()),

    _pat("js_dangerously_set_html", "high", "A03:2021 Injection",
         "dangerouslySetInnerHTML — bypasses React XSS protection",
         {"javascript", "typescript"},
         r'dangerouslySetInnerHTML\s*=',
         noise=()),

    # ── A03 Injection — Prototype pollution ───────────────────────────────────

    _pat("js_proto_pollution_lodash", "high", "A03:2021 Injection",
         "Lodash merge/extend/defaultsDeep with request body — prototype pollution risk",
         {"javascript", "typescript"},
         r'_\s*\.\s*(?:merge|extend|defaultsDeep)\s*\([^)]*(?:req\.|request\.|\.body|\.query|\.params)',
         noise=()),

    _pat("js_proto_pollution_assign", "high", "A03:2021 Injection",
         "Object.assign() with request body as source — prototype pollution risk",
         {"javascript", "typescript"},
         r'Object\.assign\s*\(\s*[^,)]+,\s*(?:req|request)\.',
         noise=()),

    # ── A03 Injection — NoSQL ReDoS ───────────────────────────────────────────

    _pat("js_nosql_regex_input", "medium", "A03:2021 Injection",
         "MongoDB $regex from request parameter — ReDoS and injection risk",
         {"javascript", "typescript"},
         r'\$regex\s*:\s*(?:req\.|request\.|new\s+RegExp\s*\(\s*(?:req|request))',
         noise=()),

    # ── A03 Injection — Python format string / Jinja2 ─────────────────────────

    _pat("py_format_star_kwargs", "high", "A03:2021 Injection",
         "str.format() with unpacked request data — format string injection risk",
         {"python"},
         r'\.format\s*\(\s*\*\*\s*(?:request|req)\.',
         noise=()),

    _pat("py_jinja2_no_autoescape", "high", "A03:2021 Injection",
         "Jinja2 Environment with autoescape=False — XSS risk for HTML output",
         {"python"},
         r'(?:Environment|jinja2\.Environment)\s*\([^)]*autoescape\s*=\s*False',
         noise=()),

    # ── A03 Injection — Go template bypass ────────────────────────────────────

    _pat("go_template_html_cast", "high", "A03:2021 Injection",
         "template.HTML/JS/CSS/URL cast — marks user content as safe, bypasses escaping",
         {"go"},
         r'\btemplate\.(?:HTML|CSS|JS|URL|Attr)\s*\(',
         noise=()),

    # ── A03 Injection — Java/C# XPath injection ───────────────────────────────

    _pat("java_xpath_injection", "high", "A03:2021 Injection",
         "XPath expression built with request parameter — XPath injection risk",
         {"java"},
         r'(?:compile|evaluate|selectNodes?)\s*\([^)]*request\.getParameter\s*\(',
         noise=()),

    _pat("cs_xpath_injection", "high", "A03:2021 Injection",
         "XPath expression with user-controlled input — XPath injection risk",
         {"csharp"},
         r'(?:SelectNodes?|SelectSingleNode|XPathExpression\.Compile)\s*\([^)]*'
         r'(?:Request\.|query\[|route\[)',
         noise=()),

    # ── A03 Injection — Log4Shell attack surface ──────────────────────────────

    _pat("java_log_user_input", "high", "A03:2021 Injection",
         "Logging request data directly — Log4Shell (CVE-2021-44228) JNDI attack surface",
         {"java"},
         r'(?:log|LOG|logger|LOGGER)\.(?:info|warn|error|debug|trace|fatal)\s*\([^)]*'
         r'request\.get(?:Parameter|Header|QueryString)\s*\(',
         noise=()),

    # ── A05 Security Misconfiguration — Debug mode ────────────────────────────

    _pat("py_flask_debug_true", "medium", "A05:2021 Security Misconfiguration",
         "Flask debug mode enabled — exposes interactive debugger and code in production",
         {"python"},
         r'app\.(?:run\s*\([^)]*debug\s*=\s*True|debug\s*=\s*True)',
         noise=()),

    _pat("py_django_debug_true", "low", "A05:2021 Security Misconfiguration",
         "Django DEBUG = True — exposes full tracebacks and settings to end users",
         {"python"},
         r'^\s*DEBUG\s*=\s*True',
         noise=("local", "test", "dev", "development", "#"),
         flags=re.IGNORECASE | re.MULTILINE),

    # ── A05 Security Misconfiguration — Info leakage / cookie flags ───────────

    _pat("js_error_stack_exposed", "medium", "A05:2021 Security Misconfiguration",
         "Error stack trace sent in HTTP response — exposes internal paths and dependencies",
         {"javascript", "typescript"},
         r'res\.(?:send|json)\s*\([^)]*(?:err|error)\.stack',
         noise=()),

    _pat("js_httponly_false", "medium", "A05:2021 Security Misconfiguration",
         "Cookie httpOnly: false — readable by JavaScript, stolen by XSS",
         {"javascript", "typescript"},
         r'httpOnly\s*:\s*false',
         noise=()),

    _pat("js_secure_false", "low", "A05:2021 Security Misconfiguration",
         "Cookie secure: false — session cookie transmitted over plain HTTP",
         {"javascript", "typescript"},
         r'(?:res\.cookie|cookie\s*\(|cookies\.set)\s*\([^)]*\bsecure\s*:\s*false',
         noise=()),

    # ── A05 Security Misconfiguration — XML / PHP ─────────────────────────────

    _pat("cs_xml_dtd_parse", "high", "A05:2021 Security Misconfiguration",
         "XmlDocument DtdProcessing.Parse — external entity loading enabled, XXE risk",
         {"csharp"},
         r'DtdProcessing\s*=\s*DtdProcessing\.Parse',
         noise=()),

    _pat("cs_xml_url_resolver", "high", "A05:2021 Security Misconfiguration",
         "XmlUrlResolver set on XML reader — enables external entity resolution, XXE risk",
         {"csharp"},
         r'XmlResolver\s*=\s*new\s+XmlUrlResolver',
         noise=()),

    _pat("php_xxe_libxml", "high", "A05:2021 Security Misconfiguration",
         "libxml_disable_entity_loader(false) — XML external entity loading enabled",
         {"php"},
         r'libxml_disable_entity_loader\s*\(\s*false\s*\)',
         noise=()),

    # ── A07 Identification and Authentication Failures ─────────────────────────

    _pat("js_jwt_no_expiry", "medium",
         "A07:2021 Identification and Authentication Failures",
         "jwt.sign() — verify expiresIn is set to prevent non-expiring tokens",
         {"javascript", "typescript"},
         r'\bjwt\.sign\s*\(',
         noise=("expiresIn", "exp:")),

    _pat("js_localstorage_auth", "medium",
         "A07:2021 Identification and Authentication Failures",
         "Auth token stored in localStorage — accessible to any JS on the page, XSS risk",
         {"javascript", "typescript"},
         r'localStorage\.setItem\s*\([^)]*(?:token|auth|jwt|Bearer|session)',
         noise=()),

    # ── A01 Broken Access Control — Rails mass assignment ─────────────────────

    _pat("rb_mass_assignment", "medium", "A01:2021 Broken Access Control",
         "Mass assignment without strong parameters — unintended attributes may be set",
         {"ruby"},
         r'(?:create|update|update_attributes|build|new)\s*\(\s*params(?:\s*\)|\s*\[)',
         noise=(".permit(", ".require(", "ActionController")),

    # ── A03 Injection — NoSQL operator injection via full request object ───────
    # Passing the entire req.body/query as a MongoDB filter lets attackers inject
    # operators like {"$gt": ""} to bypass auth or dump data — not just $where.

    _pat("js_nosql_full_req_query", "high", "A03:2021 Injection",
         "MongoDB query with full request object — attacker can inject query operators ($gt, $ne, $regex...)",
         {"javascript", "typescript"},
         r'\.(?:find|findOne|findById|updateOne?|deleteOne?|replaceOne|count(?:Documents)?)\s*\(\s*(?:req|request)\.(?:body|query|params)\s*[,)]',
         noise=()),

    # ── A01 Broken Access Control — JS/Node mass assignment ───────────────────
    # Any ORM (Sequelize, Mongoose, TypeORM, Prisma) that accepts a plain object
    # from req.body will set every field the attacker passes, including role/isAdmin.

    _pat("js_mass_assignment", "high", "A01:2021 Broken Access Control",
         "ORM create/build with full request body — unintended fields (role, isAdmin) may be set",
         {"javascript", "typescript"},
         r'\.(?:create|build|upsert|findOrCreate|insert|save)\s*\(\s*req\.body\b',
         noise=()),

    # ── A03 Injection — Template engine SSTI ──────────────────────────────────
    # Any template engine that compiles or renders a *string* coming from user
    # input is an SSTI surface, regardless of which engine is used.

    _pat("js_template_engine_user_input", "critical", "A03:2021 Injection",
         "Template engine render/compile with user-controlled string — SSTI / RCE risk",
         {"javascript", "typescript"},
         r'(?:pug|jade|ejs|nunjucks|Handlebars|handlebars|swig|mustache|dot|eta)'
         r'\.(?:render|compile|renderString|renderFile|render_string)\s*\([^)]*'
         r'(?:req\.|request\.|\.body|\.query|\.params)',
         noise=()),

    # ── A03 Injection — outerHTML / insertAdjacentHTML XSS ────────────────────
    # Additional DOM sinks beyond innerHTML that are frequently missed in reviews.

    _pat("js_outerhtml_dynamic", "high", "A03:2021 Injection",
         "outerHTML assigned dynamic content — XSS risk",
         {"javascript", "typescript"},
         r'\.outerHTML\s*(?:\+=|=)\s*(?![\s\n]*[\'"])',
         noise=()),

    _pat("js_insert_adjacent_html", "high", "A03:2021 Injection",
         "insertAdjacentHTML with dynamic second argument — XSS risk",
         {"javascript", "typescript"},
         r'\.insertAdjacentHTML\s*\(\s*["\'][^"\']+["\']\s*,\s*(?![\s\n]*[\'"])',
         noise=()),

    # ── A02 Cryptographic Failures — JWT algorithm confusion ──────────────────
    # jwt.verify() without an explicit 'algorithms' list accepts tokens signed
    # with any algorithm — enables RS256→HS256 downgrade and 'none' attacks.

    _pat("js_jwt_verify_no_alg", "high", "A02:2021 Cryptographic Failures",
         "jwt.verify() without explicit algorithms list — algorithm confusion / downgrade attack risk",
         {"javascript", "typescript"},
         r'\bjwt\.verify\s*\(',
         noise=("algorithms",)),

    # ── A02 Cryptographic Failures — Hardcoded JWT secret ─────────────────────
    # Second argument of jwt.sign/verify is the secret. A string literal here
    # means the secret is in source control and identical across all deployments.

    _pat("js_jwt_hardcoded_secret", "high", "A02:2021 Cryptographic Failures",
         "jwt.sign/verify with hardcoded string secret — secret exposed in source code",
         {"javascript", "typescript"},
         r'jwt\.(?:sign|verify)\s*\(\s*[^,]+,\s*["\'][A-Za-z0-9+/!@#$%^&*_\-]{8,}["\']',
         noise=()),

    # ── A01 Broken Access Control — Client-side unvalidated redirect ───────────
    # window.location set to any non-literal is an open redirect and potential XSS
    # (javascript: URIs). Covers both full location replacement and href.

    _pat("js_window_location_dynamic", "medium", "A01:2021 Broken Access Control",
         "window.location set to dynamic value — open redirect or javascript: XSS risk",
         {"javascript", "typescript"},
         r'window\.location(?:\.href)?\s*=\s*(?![\s\n]*[\'"])',
         noise=("encodeURI", "isLocalUrl", "validateRedirect", "sanitize")),

    # ── A01 Broken Access Control — File serving with user-controlled path ─────
    # res.sendFile / res.download with any path derived from request parameters
    # allows path traversal to read arbitrary server files.

    _pat("js_res_sendfile_user_path", "high", "A01:2021 Broken Access Control",
         "res.sendFile/download with user-controlled path — path traversal risk",
         {"javascript", "typescript"},
         r'res\.(?:sendFile|download)\s*\([^)]*(?:req\.|request\.|params|query|body)',
         noise=("path.basename", "normalize", "sanitize", "resolve")),

    # ── A08 Software and Data Integrity — JS deserialization RCE ─────────────
    # Any call to unserialize() (node-serialize and similar) may execute embedded
    # IIFEs in the payload — critical if the input comes from an untrusted source.

    _pat("js_unserialize_call", "critical", "A08:2021 Software and Data Integrity Failures",
         "unserialize() — executes embedded IIFEs in payload, arbitrary code execution risk",
         {"javascript", "typescript"},
         r'\bunserialize\s*\(',
         noise=()),

    # ── A03 Injection — Rails inline template injection ───────────────────────
    # render inline: renders an ERB string at request time. If the string comes
    # from params, it is a direct SSTI / RCE surface.

    _pat("rb_render_inline_params", "critical", "A03:2021 Injection",
         "Rails render inline: with request params — SSTI / RCE risk",
         {"ruby"},
         r'render\s+inline\s*:\s*(?:params|request)\[',
         noise=()),
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


# ─── Route-handler heuristic (used by pm_security taint analysis) ───────────

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


