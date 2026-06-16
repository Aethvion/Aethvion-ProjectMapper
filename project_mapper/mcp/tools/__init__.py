"""
project_mapper.mcp.tools
MCP tool schemas + handlers, one module per tool. Assembles the flat
TOOL_SCHEMAS list and HANDLERS dict the server expects; re-exports MCPContext.
"""

from . import (
    context,
    contribute,
    delta,
    find,
    impact,
    orphans,
    path,
    scan,
    security,
    stats,
    visualize,
)
from .base import MCPContext

TOOL_SCHEMAS = [
    context.SCHEMA,
    impact.SCHEMA,
    path.SCHEMA,
    contribute.SCHEMA,
    stats.SCHEMA,
    delta.SCHEMA,
    find.SCHEMA,
    orphans.SCHEMA,
    visualize.SCHEMA,
    scan.SCHEMA,
    security.SCHEMA,
    security.SCHEMA_TRIAGE,
]

HANDLERS = {
    "pm_context": context.handle_pm_context,
    "pm_impact": impact.handle_pm_impact,
    "pm_path": path.handle_pm_path,
    "pm_contribute": contribute.handle_pm_contribute,
    "pm_stats": stats.handle_pm_stats,
    "pm_delta": delta.handle_pm_delta,
    "pm_find": find.handle_pm_find,
    "pm_orphans": orphans.handle_pm_orphans,
    "pm_visualize": visualize.handle_pm_visualize,
    "pm_scan": scan.handle_pm_scan,
    "pm_security": security.handle_pm_security,
    "pm_security_triage": security.handle_pm_security_triage,
}

__all__ = ["MCPContext", "TOOL_SCHEMAS", "HANDLERS"]
