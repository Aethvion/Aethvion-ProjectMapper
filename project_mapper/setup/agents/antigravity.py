"""
project_mapper/setup/agents/antigravity.py
Antigravity reads MCP config from ~/.gemini/antigravity/mcp_config.json and
rules from a project-level AGENTS.md (the cross-tool standard it shares with
Codex), or ~/.gemini/GEMINI.md for a global override.
"""

from __future__ import annotations

from pathlib import Path

from ..mcp_config import register_in_json_config
from .base import Agent


def detect() -> bool:
    return (Path.home() / ".gemini" / "antigravity").exists()


def register_mcp(project_root: Path, global_only: bool = False) -> str:  # noqa: ARG001 -- already global
    return register_in_json_config(Path.home() / ".gemini" / "antigravity" / "mcp_config.json")


def rules_path(project_root: Path) -> Path:
    return project_root / "AGENTS.md"


AGENT = Agent(
    key="antigravity",
    label="Antigravity",
    detect=detect,
    register_mcp=register_mcp,
    rules_path=rules_path,
)
