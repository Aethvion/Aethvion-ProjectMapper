"""
project_mapper/setup/agents/codex.py
Codex CLI reads MCP config from ~/.codex/config.json and rules from a
project-level AGENTS.md -- the convention this standard originated from.
"""

from __future__ import annotations

from pathlib import Path

from ..mcp_config import register_in_json_config
from .base import Agent


def detect() -> bool:
    return (Path.home() / ".codex").exists()


def register_mcp(project_root: Path) -> str:  # noqa: ARG001 -- config is global, not per-project
    return register_in_json_config(Path.home() / ".codex" / "config.json")


def rules_path(project_root: Path) -> Path:
    return project_root / "AGENTS.md"


AGENT = Agent(
    key="codex",
    label="Codex",
    detect=detect,
    register_mcp=register_mcp,
    rules_path=rules_path,
)
