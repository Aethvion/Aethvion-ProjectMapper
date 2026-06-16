"""
project_mapper.core.security.scanner
The scan engine: applies the pattern catalog to file content and produces
SecurityFinding results. Public API: scan_file_security, is_route_handler_file.
"""
from __future__ import annotations

from pathlib import Path

from .patterns import _BY_LANGUAGE, _CWE_FIX, SecurityFinding

_TEST_PATH_FRAGMENTS = frozenset({
    "test", "tests", "spec", "specs", "__tests__", "mock", "mocks",
    "fixture", "fixtures", "e2e", "integration",
})


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
            cwe, fix = _CWE_FIX.get(pat.id, ("", ""))
            findings.append(SecurityFinding(
                pattern_id=pat.id,
                severity=severity,
                file=rel_path,
                line=line_no,
                language=language,
                description=pat.description,
                snippet=snippet,
                owasp=pat.owasp,
                cwe=cwe,
                fix=fix,
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
