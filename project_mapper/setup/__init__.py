"""
project_mapper.setup
One-time, idempotent configuration: register Project Mapper as an MCP server
with the user's coding agent, and write the "prefer this tool" rules file
the agent reads into context at the start of every session. See cli.py for
the pm-setup entry point.
"""

from .rules import append_directive

__all__ = ["append_directive"]
