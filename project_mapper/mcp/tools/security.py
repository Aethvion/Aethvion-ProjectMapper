"""security MCP tool."""
from __future__ import annotations

from typing import Any, Optional

from .base import MCPContext


SCHEMA = {'name': 'pm_security',
 'description': 'Standalone security scanner: walks the project files and runs OWASP Top 10 '
                'pattern matching across Python, JavaScript/TypeScript, PHP, Ruby, Go, Java, '
                'C#, and C/C++. Covers SQL/command/NoSQL injection, XSS, open redirect, path '
                'traversal, insecure deserialization, SSRF, weak crypto, and hardcoded '
                'secrets. Completely decoupled from pm_scan — run on-demand whenever you want '
                'a security review. Persists findings to a snapshot with stable IDs and triage '
                'statuses (unreviewed / verified_vulnerability / false_positive / resolved). '
                'false_positive findings are hidden by default to save tokens. Use '
                'pm_security_triage to update statuses after investigating.',
 'inputSchema': {'type': 'object',
                 'properties': {'project_root': {'type': 'string',
                                                 'description': 'Project root to scan. '
                                                                'Defaults to configured '
                                                                'project root.'},
                                'severity': {'type': 'string',
                                             'enum': ['critical',
                                                      'high',
                                                      'medium',
                                                      'low',
                                                      'all'],
                                             'description': 'Minimum severity to include. '
                                                            "'critical' = critical only; 'all' "
                                                            '= every finding. Default: '
                                                            "'medium'.",
                                             'default': 'medium'},
                                'language': {'type': 'string',
                                             'description': 'Filter to a specific language '
                                                            "(e.g. 'python', 'typescript'). "
                                                            'Omit for all.'},
                                'owasp': {'type': 'string',
                                          'description': 'Filter by OWASP category prefix '
                                                         "(e.g. 'A03' or 'Injection'). "
                                                         'Case-insensitive.'},
                                'file': {'type': 'string',
                                         'description': 'Show findings for a specific file '
                                                        'path only (substring match).'},
                                'max_results': {'type': 'integer',
                                                'description': 'Maximum findings to show in '
                                                               'output (default 50). Full list '
                                                               'goes to snapshot.',
                                                'default': 50},
                                'include_false_positives': {'type': 'boolean',
                                                            'description': 'Include findings '
                                                                           'marked '
                                                                           'false_positive '
                                                                           '(hidden by '
                                                                           'default). Default: '
                                                                           'false.',
                                                            'default': False}},
                 'required': []}}

SCHEMA_TRIAGE = {'name': 'pm_security_triage',
 'description': 'Update the review status of one or more security findings in the snapshot. '
                "Statuses: 'unreviewed' (default, needs investigation), 'false_positive' "
                '(confirmed safe — hidden from future pm_security output to save tokens), '
                "'verified_vulnerability' (confirmed real bug — kept visible as a reminder "
                "until fixed), 'resolved' (auto-set when a triaged finding disappears from the "
                'codebase). Use pm_security first to get finding IDs, then call this after '
                'investigating each finding. Bulk-update all findings in a file with the '
                "'file' argument.",
 'inputSchema': {'type': 'object',
                 'properties': {'status': {'type': 'string',
                                           'enum': ['false_positive',
                                                    'verified_vulnerability',
                                                    'resolved',
                                                    'unreviewed'],
                                           'description': 'New lifecycle status to assign to '
                                                          'the matching finding(s).'},
                                'id': {'type': 'string',
                                       'description': 'Stable 8-char hex finding ID from '
                                                      'pm_security output. Identifies one '
                                                      'specific finding.'},
                                'file': {'type': 'string',
                                         'description': 'File path substring — updates ALL '
                                                        'findings whose file path contains '
                                                        'this string.'},
                                'notes': {'type': 'string',
                                          'description': 'Investigation notes explaining the '
                                                         'decision (stored in snapshot, shown '
                                                         'in output).'},
                                'project_root': {'type': 'string',
                                                 'description': 'Project root (defaults to '
                                                                'configured project root).'}},
                 'required': ['status']}}


def _security_finding_id(rel_path: str, pattern_id: str, snippet: str) -> str:
    """Stable 8-char hex ID for a security finding.

    Keyed on file path + pattern ID + first 120 chars of the matched snippet.
    Stable across line-number shifts caused by unrelated code changes above the
    finding — the ID only changes when the vulnerable code itself changes, which
    is the correct signal for re-review.
    """
    import hashlib as _hl
    key = f"{rel_path}:{pattern_id}:{snippet.strip()[:120]}"
    return _hl.sha256(key.encode()).hexdigest()[:8]


# Old snapshot status names → new lifecycle names (backward compat on load)
_STATUS_NORM: dict[str, str] = {
    "open":         "unreviewed",
    "fixed":        "resolved",
    "acknowledged": "verified_vulnerability",
}

# ---------------------------------------------------------------------------
# pm_security / pm_security_max handlers
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_SEVERITY_THRESHOLD = {
    "critical": {"critical"},
    "high":     {"critical", "high"},
    "medium":   {"critical", "high", "medium"},
    "low":      {"critical", "high", "medium", "low"},
    "all":      {"critical", "high", "medium", "low"},
}


def handle_pm_security(args: dict[str, Any], ctx: MCPContext) -> str:
    import json as _json
    import os
    from datetime import datetime, timezone
    from pathlib import Path as _Path
    from ...core.security_patterns import scan_file_security, is_route_handler_file

    project_root_arg = (args.get("project_root") or ctx.project_root or "").strip()
    if not project_root_arg:
        return (
            "No project root configured. Pass project_root= or run pm_scan first."
        )

    project_root = _Path(project_root_arg)
    if not project_root.is_dir():
        return f"project_root does not exist or is not a directory: {project_root_arg}"

    severity_filter    = args.get("severity", "medium").lower()
    lang_filter        = (args.get("language") or "").lower().strip()
    owasp_filter       = (args.get("owasp") or "").lower().strip()
    file_filter        = (args.get("file") or "").lower().strip()
    max_results        = min(int(args.get("max_results", 50)), 500)
    include_fp         = bool(args.get("include_false_positives", False))
    allowed_severities = _SEVERITY_THRESHOLD.get(severity_filter, {"critical", "high", "medium"})

    _EXT_LANG: dict[str, str] = {
        ".py": "python", ".pyw": "python",
        ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".php": "php",
        ".rb": "ruby", ".rake": "ruby",
        ".go": "go",
        ".java": "java",
        ".cs": "csharp",
        ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
        ".c": "c", ".h": "c", ".hpp": "cpp",
    }
    _SKIP_DIRS = {
        ".git", ".svn", ".hg", "node_modules", "__pycache__",
        ".venv", "venv", "env", ".env",
        "vendor", "dist", "build", ".next", ".nuxt",
        "target", "out", "bin", "obj",
        "coverage", ".cache", ".pytest_cache", ".mypy_cache",
        ".tox", "htmlcov",
    }

    raw_findings: list[dict] = []
    files_scanned = 0

    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for filename in filenames:
            if ".min." in filename.lower():
                continue
            ext = os.path.splitext(filename)[1].lower()
            language = _EXT_LANG.get(ext)
            if not language:
                continue
            full_path = os.path.join(dirpath, filename)
            try:
                rel = os.path.relpath(full_path, project_root).replace("\\", "/")
            except ValueError:
                continue
            try:
                with open(full_path, encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except Exception:
                continue
            try:
                findings = scan_file_security(rel, content, language)
                for f in findings:
                    raw_findings.append(f.to_dict())
                files_scanned += 1
            except Exception:
                continue

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Snapshot lives in the PM data directory, not the project root.
    # Storing it in the project root risks accidental commits exposing all
    # security findings publicly.  Path is keyed by a hash of the absolute
    # project root so different projects never share a file.
    import hashlib as _hashlib
    from ...config import DATA_DIR as _DATA_DIR
    _abs_root   = str(project_root.resolve())
    _root_hash  = _hashlib.sha256(_abs_root.encode()).hexdigest()[:10]
    _sec_dir    = _DATA_DIR / "security"
    _sec_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = _sec_dir / f"{project_root.resolve().name}_{_root_hash}.securitysnapshot"

    # Load existing snapshot; index by stable content-hash ID so statuses survive
    # rescans even when line numbers shift.  Old SEC-XXXX IDs are re-hashed from
    # content on the fly for backward compatibility.
    old_by_id: dict[str, dict] = {}

    if snapshot_path.exists():
        try:
            old_snap = _json.loads(snapshot_path.read_text(encoding="utf-8"))
            for old_f in old_snap.get("findings", []):
                fid = old_f.get("id", "")
                is_stable = len(fid) == 8 and all(c in "0123456789abcdef" for c in fid)
                if not is_stable:
                    fid = _security_finding_id(
                        old_f.get("file", ""),
                        old_f.get("pattern_id", ""),
                        old_f.get("snippet", ""),
                    )
                # Normalise old status names to the current lifecycle vocabulary
                old_status = old_f.get("status", "unreviewed")
                old_f["status"] = _STATUS_NORM.get(old_status, old_status)
                old_by_id[fid] = old_f
        except Exception:
            pass

    # Sort: critical first
    raw_findings.sort(key=lambda f: (
        _SEVERITY_RANK.get(f.get("severity", "low"), 9),
        f.get("file", ""),
        f.get("line", 0),
    ))

    # Build output findings: assign stable content-hash IDs and carry forward
    # any triage status (false_positive / verified_vulnerability) from the snapshot.
    findings_out: list[dict] = []
    for f in raw_findings:
        pid   = f.get("id", "")
        fpath = f.get("file", "")
        snip  = f.get("snippet", "")
        sid   = _security_finding_id(fpath, pid, snip)
        old_f = old_by_id.get(sid, {})
        old_status = old_f.get("status", "unreviewed")
        # A previously-resolved finding that reappears needs fresh review
        if old_status == "resolved":
            old_status = "unreviewed"
        findings_out.append({
            "id":              sid,
            "pattern_id":      pid,
            "severity":        f.get("severity", "medium"),
            "owasp":           f.get("owasp", ""),
            "cwe":             f.get("cwe", ""),
            "fix":             f.get("fix", ""),
            "file":            fpath,
            "line":            f.get("line", 0),
            "language":        f.get("language", ""),
            "description":     f.get("description", ""),
            "snippet":         snip,
            "taint_reachable": is_route_handler_file(fpath),
            "status":          old_status,
            "notes":           old_f.get("notes"),
            "first_seen":      old_f.get("first_seen", now_iso),
            "last_seen":       now_iso,
        })

    # Auto-resolve findings that have been triaged (verified or false_positive)
    # and no longer appear in the current scan — they were either fixed or
    # the matched code was removed.
    new_ids = {f["id"] for f in findings_out}
    resolved_findings: list[dict] = []
    for sid, old_f in old_by_id.items():
        if sid not in new_ids and old_f.get("status") in ("verified_vulnerability", "false_positive"):
            resolved_copy = dict(old_f)
            resolved_copy["status"]    = "resolved"
            resolved_copy["last_seen"] = now_iso
            resolved_findings.append(resolved_copy)

    counts: dict[str, int] = {}
    for f in findings_out:
        sev = f["severity"]
        counts[sev] = counts.get(sev, 0) + 1

    fp_hidden  = sum(1 for f in findings_out if f["status"] == "false_positive")
    summary = {
        "critical":                   counts.get("critical", 0),
        "high":                       counts.get("high", 0),
        "medium":                     counts.get("medium", 0),
        "low":                        counts.get("low", 0),
        "total":                      len(findings_out),
        "files_scanned":              files_scanned,
        "taint_reachable":            sum(1 for f in findings_out if f["taint_reachable"]),
        "false_positive_suppressed":  fp_hidden,
        "resolved_since_last_scan":   len(resolved_findings),
        "new_since_last_scan":        sum(1 for f in findings_out if f["id"] not in old_by_id),
    }

    try:
        from ..server import SERVER_VERSION as _sv
        pm_version = _sv
    except Exception:
        pm_version = ""

    snapshot: dict = {
        "format_version": "1.0",
        "pm_version":     pm_version,
        "generated_at":   now_iso,
        "project_root":   project_root_arg,
        "severity_floor": severity_filter,
        "findings":       findings_out + resolved_findings,
        "summary":        summary,
    }

    snapshot_written = False
    try:
        snapshot_path.write_text(
            _json.dumps(snapshot, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        snapshot_written = True
    except Exception:
        pass

    # Apply display filters.  false_positive findings are hidden by default to
    # avoid burning agent tokens re-investigating already-triaged findings.
    display_findings = [
        f for f in findings_out
        if f["severity"] in allowed_severities
        and (include_fp or f["status"] != "false_positive")
        and (not lang_filter  or f["language"] == lang_filter)
        and (not owasp_filter or owasp_filter in f["owasp"].lower())
        and (not file_filter  or file_filter  in f["file"].lower())
    ]
    total_displayed = len(display_findings)
    shown = display_findings[:max_results]

    # ── Risk scoring ─────────────────────────────────────────────────────────
    # Per-finding score: severity points × taint multiplier.
    # Project risk level driven by highest-severity finding count.
    _SEV_PTS = {"critical": 10, "high": 6, "medium": 2, "low": 1}
    for f in findings_out:
        pts = _SEV_PTS.get(f["severity"], 1)
        if f["taint_reachable"]:
            pts = min(10, round(pts * 1.5))
        f["risk_score"] = pts

    if counts.get("critical", 0):
        risk_level = "CRITICAL"
    elif counts.get("high", 0):
        risk_level = "HIGH"
    elif counts.get("medium", 0):
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    # Top-5 riskiest files (aggregate risk score per file)
    file_risk: dict[str, int] = {}
    file_sev:  dict[str, list[str]] = {}
    for f in findings_out:
        fp = f["file"]
        file_risk[fp] = file_risk.get(fp, 0) + f["risk_score"]
        file_sev.setdefault(fp, []).append(f["severity"])
    top_files = sorted(file_risk, key=lambda k: -file_risk[k])[:5]

    # OWASP category summary (all findings, not just displayed)
    owasp_counts: dict[str, int] = {}
    for f in findings_out:
        cat = f.get("owasp", "Other").split(":")[0]  # "A03:2021 Injection" → "A03"
        owasp_counts[cat] = owasp_counts.get(cat, 0) + 1

    count_str = "  ".join(
        f"{sev}: {n}"
        for sev, n in sorted(counts.items(), key=lambda kv: _SEVERITY_RANK.get(kv[0], 9))
    ) or "0"

    proj_name = project_root.resolve().name

    lines = [
        f"╔══ ProjectMapper Security Report ══════════════════════════════════╗",
        f"  Project : {proj_name}",
        f"  Files   : {files_scanned} scanned",
        f"  Risk    : {risk_level}  ({count_str})",
        f"  Taint   : {summary['taint_reachable']} finding(s) reachable from route handlers",
        f"  Delta   : +{summary['new_since_last_scan']} new  ✓{summary['resolved_since_last_scan']} resolved since last scan",
    ]
    if summary["false_positive_suppressed"]:
        lines.append(
            f"  Hidden  : {summary['false_positive_suppressed']} false_positive"
            " (pass include_false_positives=true to show)"
        )
    lines += [
        f"╚════════════════════════════════════════════════════════════════════╝",
        "",
    ]

    if top_files:
        lines.append("Top files by risk score:")
        for i, fp in enumerate(top_files, 1):
            sevs   = file_sev[fp]
            c_cnt  = sevs.count("critical")
            h_cnt  = sevs.count("high")
            detail = "  ".join(filter(None, [
                f"{c_cnt} critical" if c_cnt else "",
                f"{h_cnt} high"     if h_cnt else "",
            ])) or f"{len(sevs)} finding(s)"
            lines.append(f"  {i}. {fp:<55}  score:{file_risk[fp]:>3}  [{detail}]")
        lines.append("")

    if owasp_counts:
        lines.append("OWASP Top 10 coverage:")
        for cat in sorted(owasp_counts):
            n    = owasp_counts[cat]
            bar  = "█" * min(n, 20)
            lines.append(f"  {cat}  {bar}  {n}")
        lines.append("")

    if snapshot_written:
        lines.append(f"Snapshot: {snapshot_path}")
        lines.append("  Use pm_security_triage to mark findings: false_positive | verified_vulnerability")
        lines.append("  Re-run pm_security after code changes to auto-resolve fixed findings.")
        lines.append("")

    if not display_findings:
        filter_desc = f"severity≥{severity_filter}"
        if lang_filter:  filter_desc += f", language={lang_filter}"
        if owasp_filter: filter_desc += f", owasp={owasp_filter}"
        if file_filter:  filter_desc += f", file={file_filter}"
        lines.append(f"No findings matching filters ({filter_desc}).")
        if summary["total"]:
            lines.append(f"There are {summary['total']} finding(s) at other severity levels.")
        return "\n".join(lines).rstrip()

    lines.append(
        f"Showing {len(shown)}/{total_displayed} findings"
        + (f" (severity≥{severity_filter})" if severity_filter != "all" else "")
        + ":"
    )
    lines.append("")

    # Rule reference — description/fix printed once per pattern, not per finding
    seen_patterns: dict[str, dict] = {}
    for f in shown:
        pid = f["pattern_id"]
        if pid not in seen_patterns:
            seen_patterns[pid] = f

    lines.append("Rule Reference:")
    for pid in sorted(seen_patterns):
        rf      = seen_patterns[pid]
        cwe_str = f"  {rf['cwe']}" if rf.get("cwe") else ""
        owasp_s = f"  {rf.get('owasp', '')}" if rf.get("owasp") else ""
        desc    = rf.get("description", "")
        fix     = f"  Fix: {rf['fix']}" if rf.get("fix") else ""
        lines.append(f"  [{pid}]{cwe_str}{owasp_s}  {desc}{fix}")
    lines.append("")

    by_owasp: dict[str, list[dict]] = {}
    for f in shown:
        cat = f.get("owasp", "Other")
        by_owasp.setdefault(cat, []).append(f)

    for cat in sorted(by_owasp):
        lines.append(f"── {cat} ──")
        for f in by_owasp[cat]:
            fid    = f.get("id", "")[:8]
            sev    = f["severity"].upper()
            reach  = "  ⚡" if f["taint_reachable"] else ""
            status = {
                "verified_vulnerability": "  [CONFIRMED]",
                "false_positive":         "  [FALSE-POS]",
                "resolved":               "  [RESOLVED]",
            }.get(f["status"], "")
            lines.append(
                f"  {fid}  {sev:<8}  {f['pattern_id']:<28}  {f['file']}:{f['line']}{reach}{status}"
            )
            if f.get("snippet"):
                lines.append(f"    »  {f['snippet']}")
            if f.get("notes"):
                lines.append(f"    Note: {f['notes']}")
        lines.append("")

    if total_displayed > max_results:
        lines.append(
            f"… {total_displayed - max_results} more findings not shown. "
            f"Use max_results={total_displayed} or apply filters to narrow down."
        )

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# pm_security_triage handler
# ---------------------------------------------------------------------------

def handle_pm_security_triage(args: dict[str, Any], ctx: MCPContext) -> str:
    """Update the review status of one or more findings in the security snapshot."""
    import json as _json
    import hashlib as _hl
    from pathlib import Path as _Path
    from ...config import DATA_DIR as _DATA_DIR

    new_status  = (args.get("status") or "").strip()
    finding_id  = (args.get("id") or "").strip()
    file_pat    = (args.get("file") or "").strip().lower()
    notes       = (args.get("notes") or "").strip()
    project_root_arg = (args.get("project_root") or ctx.project_root or "").strip()

    _VALID = {"false_positive", "verified_vulnerability", "resolved", "unreviewed"}
    if new_status not in _VALID:
        raise ValueError(f"status must be one of: {', '.join(sorted(_VALID))}")

    if not finding_id and not file_pat:
        raise ValueError("Provide id (stable finding ID) or file (substring to bulk-update)")

    if not project_root_arg:
        return "No project root configured. Pass project_root= or run pm_security first."

    project_root = _Path(project_root_arg)
    _root_hash   = _hl.sha256(str(project_root.resolve()).encode()).hexdigest()[:10]
    snapshot_path = _DATA_DIR / "security" / f"{project_root.resolve().name}_{_root_hash}.securitysnapshot"

    if not snapshot_path.exists():
        return "No security snapshot found for this project. Run pm_security first to create one."

    try:
        snap = _json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"Failed to read snapshot: {exc}"

    findings = snap.get("findings", [])
    updated: list[dict] = []

    for f in findings:
        match = False
        if finding_id and f.get("id") == finding_id:
            match = True
        elif file_pat and file_pat in f.get("file", "").lower():
            match = True

        if match:
            f["status"] = new_status
            if notes:
                f["notes"] = notes
            updated.append(f)

    if not updated:
        if finding_id:
            return (
                f"No finding with id={finding_id!r} in snapshot.\n"
                "Run pm_security to see current finding IDs."
            )
        return f"No findings matching file={file_pat!r} in snapshot."

    snap["findings"] = findings
    try:
        snapshot_path.write_text(
            _json.dumps(snap, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        return f"Snapshot updated in memory but failed to save: {exc}"

    if len(updated) == 1:
        f = updated[0]
        out = [
            f"Triaged finding {f['id']}  →  {new_status}",
            f"  File    : {f['file']}:{f.get('line', '?')}",
            f"  Pattern : {f.get('pattern_id', '')}",
        ]
        if notes:
            out.append(f"  Notes   : {notes}")
        return "\n".join(out)

    return (
        f"Triaged {len(updated)} finding(s) → {new_status}"
        + (f"  (file filter: {file_pat!r})" if file_pat else "")
        + (f"\n  Notes: {notes}" if notes else "")
    )
