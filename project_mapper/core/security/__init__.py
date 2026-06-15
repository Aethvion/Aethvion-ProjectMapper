"""
project_mapper.core.security
Standalone SAST scanner (OWASP Top 10). `patterns` holds the catalog,
`scanner` runs it per file, and `scan` orchestrates a project-level scan with a
findings snapshot + triage. Public API re-exported here.
"""
from .patterns import SecurityFinding
from .scanner import scan_file_security, is_route_handler_file
from .scan import scan_project, triage_findings, snapshot_path_for, finding_id

__all__ = [
    "SecurityFinding",
    "scan_file_security",
    "is_route_handler_file",
    "scan_project",
    "triage_findings",
    "snapshot_path_for",
    "finding_id",
]
