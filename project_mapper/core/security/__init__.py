"""
project_mapper.core.security
Standalone SAST scanner (OWASP Top 10). `patterns` holds the catalog,
`scanner` runs it per file, and `scan` orchestrates a project-level scan with a
findings snapshot + triage. Public API re-exported here.
"""
from .patterns import SecurityFinding
from .scan import finding_id, scan_project, snapshot_path_for, triage_findings
from .scanner import is_route_handler_file, scan_file_security

__all__ = [
    "SecurityFinding",
    "scan_file_security",
    "is_route_handler_file",
    "scan_project",
    "triage_findings",
    "snapshot_path_for",
    "finding_id",
]
