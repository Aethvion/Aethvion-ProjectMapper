"""
project_mapper/setup/mcp_config.py
Read-merge-write helper for agents that store MCP server config as a plain
JSON file with an "mcpServers" key, instead of exposing a CLI for it
(Cursor, Antigravity, Codex). Never overwrites the file wholesale -- only
ever adds the "project-mapper" entry, preserving anything else already
there.
"""

from __future__ import annotations

import json
from pathlib import Path

SERVER_ENTRY = {
    "type": "stdio",
    "command": "pm-mcp",
    "args": ["--db", "workspace"],
}


def register_in_json_config(path: Path) -> str:
    """Add the project-mapper MCP entry to a JSON config file at `path`.

    Returns "registered", "already-registered", or "failed: <reason>".
    """
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return f"failed: {path} is not valid JSON ({exc}); fix it manually and re-run"
        if not isinstance(config, dict):
            return f"failed: {path} does not contain a JSON object at the top level"
    else:
        config = {}

    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        return f"failed: {path}'s \"mcpServers\" key is not an object"

    if "project-mapper" in servers:
        return "already-registered"

    servers["project-mapper"] = dict(SERVER_ENTRY)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return "registered"
