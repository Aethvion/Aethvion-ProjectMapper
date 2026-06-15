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


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def handle_pm_security(args: dict[str, Any], ctx: MCPContext) -> str:
    from ...core.security import scan_project
    try:
        from ..server import SERVER_VERSION as _sv
    except Exception:
        _sv = ""

    project_root_arg = (args.get("project_root") or ctx.project_root or "").strip()
    r = scan_project(
        project_root_arg,
        severity=args.get("severity", "medium"),
        language=args.get("language"),
        owasp=args.get("owasp"),
        file=args.get("file"),
        max_results=int(args.get("max_results", 50)),
        include_false_positives=bool(args.get("include_false_positives", False)),
        pm_version=_sv,
    )
    if r["status"] == "no_project_root":
        return "No project root configured. Pass project_root= or run pm_scan first."
    if r["status"] == "bad_root":
        return f"project_root does not exist or is not a directory: {r['root']}"

    counts          = r["counts"]
    summary         = r["summary"]
    files_scanned   = r["files_scanned"]
    risk_level      = r["risk_level"]
    owasp_counts    = r["owasp_counts"]
    snapshot_written = r["snapshot_written"]
    snapshot_path   = r["snapshot_path"]
    shown           = r["findings"]
    total_displayed = r["total_displayed"]
    flt             = r["filters"]
    severity_filter = flt["severity"]
    lang_filter     = flt["language"]
    owasp_filter    = flt["owasp"]
    file_filter     = flt["file"]
    max_results     = flt["max_results"]

    count_str = "  ".join(
        f"{sev}: {n}"
        for sev, n in sorted(counts.items(), key=lambda kv: _SEVERITY_RANK.get(kv[0], 9))
    ) or "0"

    lines = [
        f"╔══ ProjectMapper Security Report ══════════════════════════════════╗",
        f"  Project : {r['project']}",
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

    if r["top_files"]:
        lines.append("Top files by risk score:")
        for i, tf in enumerate(r["top_files"], 1):
            sevs   = tf["severities"]
            c_cnt  = sevs.count("critical")
            h_cnt  = sevs.count("high")
            detail = "  ".join(filter(None, [
                f"{c_cnt} critical" if c_cnt else "",
                f"{h_cnt} high"     if h_cnt else "",
            ])) or f"{len(sevs)} finding(s)"
            lines.append(f"  {i}. {tf['file']:<55}  score:{tf['score']:>3}  [{detail}]")
        lines.append("")

    if owasp_counts:
        lines.append("OWASP Top 10 coverage:")
        for cat in sorted(owasp_counts):
            n   = owasp_counts[cat]
            bar = "█" * min(n, 20)
            lines.append(f"  {cat}  {bar}  {n}")
        lines.append("")

    if snapshot_written:
        lines.append(f"Snapshot: {snapshot_path}")
        lines.append("  Use pm_security_triage to mark findings: false_positive | verified_vulnerability")
        lines.append("  Re-run pm_security after code changes to auto-resolve fixed findings.")
        lines.append("")

    if total_displayed == 0:
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

    seen_patterns: dict[str, dict] = {}
    for f in shown:
        if f["pattern_id"] not in seen_patterns:
            seen_patterns[f["pattern_id"]] = f

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
        by_owasp.setdefault(f.get("owasp", "Other"), []).append(f)

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


def handle_pm_security_triage(args: dict[str, Any], ctx: MCPContext) -> str:
    """Update the review status of one or more findings in the security snapshot."""
    from ...core.security import triage_findings

    file_arg = (args.get("file") or "").strip()
    notes    = (args.get("notes") or "").strip()
    project_root_arg = (args.get("project_root") or ctx.project_root or "").strip()

    r = triage_findings(
        project_root_arg,
        status=(args.get("status") or "").strip(),
        finding_id_arg=(args.get("id") or "").strip(),
        file=file_arg,
        notes=notes,
    )

    st = r["status"]
    if st == "invalid_status":
        raise ValueError(f"status must be one of: {', '.join(r['valid'])}")
    if st == "need_id_or_file":
        raise ValueError("Provide id (stable finding ID) or file (substring to bulk-update)")
    if st == "no_project_root":
        return "No project root configured. Pass project_root= or run pm_security first."
    if st == "no_snapshot":
        return "No security snapshot found for this project. Run pm_security first to create one."
    if st == "read_error":
        return f"Failed to read snapshot: {r['error']}"
    if st == "none_matched":
        if r["by"] == "id":
            return (
                f"No finding with id={r['value']!r} in snapshot.\n"
                "Run pm_security to see current finding IDs."
            )
        return f"No findings matching file={r['value']!r} in snapshot."
    if st == "save_error":
        return f"Snapshot updated in memory but failed to save: {r['error']}"

    updated    = r["updated"]
    new_status = r["new_status"]
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
        + (f"  (file filter: {file_arg.lower()!r})" if file_arg else "")
        + (f"\n  Notes: {notes}" if notes else "")
    )
