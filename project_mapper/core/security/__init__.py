"""
project_mapper.core.security
Standalone SAST scanner (OWASP Top 10). `patterns` holds the catalog;
`scanner` runs it. Public API re-exported here.
"""
from .patterns import SecurityFinding
from .scanner import scan_file_security, is_route_handler_file

__all__ = ["SecurityFinding", "scan_file_security", "is_route_handler_file"]
