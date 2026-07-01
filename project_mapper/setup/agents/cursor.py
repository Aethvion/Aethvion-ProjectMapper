"""
project_mapper/setup/agents/cursor.py
Cursor has no CLI for MCP config -- it's a hand-edited JSON file at
~/.cursor/mcp.json, and rules live in .cursor/rules/*.mdc with YAML
frontmatter that tells Cursor to always apply the rule.
"""

from __future__ import annotations

from pathlib import Path

from ..mcp_config import register_in_json_config
from ..rules import CURSOR_FRONTMATTER
from .base import Agent


def detect() -> bool:
    return (Path.home() / ".cursor").exists()


def register_mcp(project_root: Path, global_only: bool = False) -> str:  # noqa: ARG001 -- already global
    return register_in_json_config(Path.home() / ".cursor" / "mcp.json")


def rules_path(project_root: Path) -> Path:
    return project_root / ".cursor" / "rules" / "project-mapper.mdc"


AGENT = Agent(
    key="cursor",
    label="Cursor",
    detect=detect,
    register_mcp=register_mcp,
    rules_path=rules_path,
    rules_frontmatter=CURSOR_FRONTMATTER,
)
