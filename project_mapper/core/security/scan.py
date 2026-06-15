"""
project_mapper.core.security.scan
Project-level security scan orchestration: walk the tree, run the pattern
catalog per file, maintain a findings snapshot with stable content-hash IDs and
triage status, auto-resolve disappeared findings, and rank the results.

Transport-agnostic. Used by the pm_security / pm_security_triage MCP tools and
the HTTP /security endpoints — neither contains scan orchestration itself.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ...config import DATA_DIR
from .scanner import scan_file_security, is_route_handler_file


# Old snapshot status names → current lifecycle vocabulary (backward compat on load)
_STATUS_NORM = {
    "open":         "unreviewed",
    "fixed":        "resolved",
    "acknowledged": "verified_vulnerability",
}
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_SEVERITY_THRESHOLD = {
    "critical": {"critical"},
    "high":     {"critical", "high"},
    "medium":   {"critical", "high", "medium"},
    "low":      {"critical", "high", "medium", "low"},
    "all":      {"critical", "high", "medium", "low"},
}
_SEV_PTS = {"critical": 10, "high": 6, "medium": 2, "low": 1}

TRIAGE_STATUSES = {"false_positive", "verified_vulnerability", "resolved", "unreviewed"}

_EXT_LANG: dict[str, str] = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
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


def finding_id(rel_path: str, pattern_id: str, snippet: str) -> str:
    """Stable 8-char hex ID for a finding (file + pattern + snippet content)."""
    key = f"{rel_path}:{pattern_id}:{snippet.strip()[:120]}"
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def snapshot_path_for(project_root: Path) -> Path:
    """Snapshot file path for a project root (kept in DATA_DIR, never the project)."""
    root_hash = hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:10]
    sec_dir = DATA_DIR / "security"
    sec_dir.mkdir(parents=True, exist_ok=True)
    return sec_dir / f"{project_root.resolve().name}_{root_hash}.securitysnapshot"


def scan_project(
    project_root: str,
    severity: str = "medium",
    language: Optional[str] = None,
    owasp: Optional[str] = None,
    file: Optional[str] = None,
    max_results: int = 50,
    include_false_positives: bool = False,
    pm_version: str = "",
) -> dict[str, Any]:
    """Scan a project tree for security issues.

    Returns a status dict:
      {"status": "no_project_root"}
      {"status": "bad_root", "root": <arg>}
      {"status": "ok", ...rich result...}
    """
    project_root_arg = (project_root or "").strip()
    if not project_root_arg:
        return {"status": "no_project_root"}

    root = Path(project_root_arg)
    if not root.is_dir():
        return {"status": "bad_root", "root": project_root_arg}

    severity_filter    = (severity or "medium").lower()
    lang_filter        = (language or "").lower().strip()
    owasp_filter       = (owasp or "").lower().strip()
    file_filter        = (file or "").lower().strip()
    max_results        = min(int(max_results or 50), 500)
    include_fp         = bool(include_false_positives)
    allowed_severities = _SEVERITY_THRESHOLD.get(severity_filter, {"critical", "high", "medium"})

    # ── Walk + scan ──────────────────────────────────────────────────────────
    raw_findings: list[dict] = []
    files_scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for filename in filenames:
            if ".min." in filename.lower():
                continue
            ext = os.path.splitext(filename)[1].lower()
            lang = _EXT_LANG.get(ext)
            if not lang:
                continue
            full_path = os.path.join(dirpath, filename)
            try:
                rel = os.path.relpath(full_path, root).replace("\\", "/")
            except ValueError:
                continue
            try:
                with open(full_path, encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except Exception:
                continue
            try:
                for f in scan_file_security(rel, content, lang):
                    raw_findings.append(f.to_dict())
                files_scanned += 1
            except Exception:
                continue

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot_path = snapshot_path_for(root)

    # ── Load existing snapshot (carry triage status across rescans) ──────────
    old_by_id: dict[str, dict] = {}
    if snapshot_path.exists():
        try:
            old_snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
            for old_f in old_snap.get("findings", []):
                fid = old_f.get("id", "")
                is_stable = len(fid) == 8 and all(c in "0123456789abcdef" for c in fid)
                if not is_stable:
                    fid = finding_id(old_f.get("file", ""), old_f.get("pattern_id", ""), old_f.get("snippet", ""))
                old_status = old_f.get("status", "unreviewed")
                old_f["status"] = _STATUS_NORM.get(old_status, old_status)
                old_by_id[fid] = old_f
        except Exception:
            pass

    raw_findings.sort(key=lambda f: (
        _SEVERITY_RANK.get(f.get("severity", "low"), 9), f.get("file", ""), f.get("line", 0),
    ))

    # ── Assign stable IDs + carry forward triage status ──────────────────────
    findings_out: list[dict] = []
    for f in raw_findings:
        pid   = f.get("id", "")
        fpath = f.get("file", "")
        snip  = f.get("snippet", "")
        sid   = finding_id(fpath, pid, snip)
        old_f = old_by_id.get(sid, {})
        old_status = old_f.get("status", "unreviewed")
        if old_status == "resolved":  # a resolved finding that reappears needs fresh review
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

    # Auto-resolve triaged findings that no longer appear
    new_ids = {f["id"] for f in findings_out}
    resolved_findings: list[dict] = []
    for sid, old_f in old_by_id.items():
        if sid not in new_ids and old_f.get("status") in ("verified_vulnerability", "false_positive"):
            rc = dict(old_f)
            rc["status"] = "resolved"
            rc["last_seen"] = now_iso
            resolved_findings.append(rc)

    counts: dict[str, int] = {}
    for f in findings_out:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    summary = {
        "critical":                   counts.get("critical", 0),
        "high":                       counts.get("high", 0),
        "medium":                     counts.get("medium", 0),
        "low":                        counts.get("low", 0),
        "total":                      len(findings_out),
        "files_scanned":              files_scanned,
        "taint_reachable":            sum(1 for f in findings_out if f["taint_reachable"]),
        "false_positive_suppressed":  sum(1 for f in findings_out if f["status"] == "false_positive"),
        "resolved_since_last_scan":   len(resolved_findings),
        "new_since_last_scan":        sum(1 for f in findings_out if f["id"] not in old_by_id),
    }

    snapshot = {
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
        snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        snapshot_written = True
    except Exception:
        pass

    # ── Display filters ──────────────────────────────────────────────────────
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

    # ── Risk scoring + aggregates ────────────────────────────────────────────
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

    file_risk: dict[str, int] = {}
    file_sev:  dict[str, list[str]] = {}
    for f in findings_out:
        fp = f["file"]
        file_risk[fp] = file_risk.get(fp, 0) + f["risk_score"]
        file_sev.setdefault(fp, []).append(f["severity"])
    top_files = sorted(file_risk, key=lambda k: -file_risk[k])[:5]

    owasp_counts: dict[str, int] = {}
    for f in findings_out:
        cat = f.get("owasp", "Other").split(":")[0]
        owasp_counts[cat] = owasp_counts.get(cat, 0) + 1

    return {
        "status":           "ok",
        "project":          root.resolve().name,
        "project_root":     project_root_arg,
        "files_scanned":    files_scanned,
        "risk_level":       risk_level,
        "counts":           counts,
        "summary":          summary,
        "findings":         shown,            # displayed + capped
        "all_findings":     findings_out,     # full set (with risk_score)
        "resolved":         resolved_findings,
        "total_displayed":  total_displayed,
        "top_files":        [{"file": fp, "score": file_risk[fp], "severities": file_sev[fp]} for fp in top_files],
        "owasp_counts":     owasp_counts,
        "snapshot_path":    str(snapshot_path),
        "snapshot_written": snapshot_written,
        "filters": {
            "severity": severity_filter, "language": lang_filter, "owasp": owasp_filter,
            "file": file_filter, "include_false_positives": include_fp, "max_results": max_results,
        },
    }


def triage_findings(
    project_root: str,
    status: str,
    finding_id_arg: Optional[str] = None,
    file: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Update the review status of one or more findings in the snapshot.

    Returns a status dict:
      {"status": "invalid_status", "valid": [...]}
      {"status": "need_id_or_file"}
      {"status": "no_project_root"}
      {"status": "no_snapshot"}
      {"status": "read_error", "error": ...}
      {"status": "none_matched", "by": "id"|"file", "value": ...}
      {"status": "save_error", "error": ..., "updated": [...]}
      {"status": "ok", "updated": [...], "count": N}
    """
    new_status = (status or "").strip()
    fid        = (finding_id_arg or "").strip()
    file_pat   = (file or "").strip().lower()
    notes      = (notes or "").strip()
    project_root_arg = (project_root or "").strip()

    if new_status not in TRIAGE_STATUSES:
        return {"status": "invalid_status", "valid": sorted(TRIAGE_STATUSES)}
    if not fid and not file_pat:
        return {"status": "need_id_or_file"}
    if not project_root_arg:
        return {"status": "no_project_root"}

    snapshot_path = snapshot_path_for(Path(project_root_arg))
    if not snapshot_path.exists():
        return {"status": "no_snapshot"}

    try:
        snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "read_error", "error": str(exc)}

    findings = snap.get("findings", [])
    updated: list[dict] = []
    for f in findings:
        if (fid and f.get("id") == fid) or (file_pat and file_pat in f.get("file", "").lower()):
            f["status"] = new_status
            if notes:
                f["notes"] = notes
            updated.append(f)

    if not updated:
        return {"status": "none_matched", "by": "id" if fid else "file", "value": fid or file_pat}

    snap["findings"] = findings
    try:
        snapshot_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        return {"status": "save_error", "error": str(exc), "updated": updated}

    return {"status": "ok", "updated": updated, "count": len(updated), "new_status": new_status, "notes": notes}
