"""
project_mapper/setup/agents/claude_code.py
Claude Code reads MCP server config from ~/.claude.json -- never from
~/.claude/settings.json, which it silently ignores (the bug that took down
the previous pm-setup). Rather than write that file ourselves, we shell out
to `claude mcp add`, the same command the docs already tell users to run by
hand -- Claude Code owns the correctness of its own config format.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..mcp_config import register_in_json_config
from .base import Agent


def detect() -> bool:
    return shutil.which("claude") is not None


def register_mcp(project_root: Path, global_only: bool = False) -> str:
    claude = shutil.which("claude")
    if claude is None:
        if global_only:
            # --global means no per-project file, anywhere. Without the CLI
            # we have no way to write user-scoped ~/.claude.json ourselves
            # (see module docstring) -- refuse rather than silently writing
            # a project-level .mcp.json into whatever the cwd happens to be.
            return (
                "failed: `claude` CLI not found on PATH -- required to register at user scope "
                "for --global. Install it / add it to PATH, or omit --global to fall back to "
                "a project-level .mcp.json"
            )
        # No CLI on PATH -- fall back to a project-level .mcp.json, which
        # Claude Code also reads.
        return register_in_json_config(project_root / ".mcp.json")

    try:
        result = subprocess.run(
            [
                claude,
                "mcp",
                "add",
                "-s",
                "user",
                "project-mapper",
                "--",
                "pm-mcp",
                "--db",
                "workspace",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"failed: could not run `claude mcp add` ({exc})"

    output = (result.stdout + result.stderr).lower()
    if result.returncode == 0:
        return "registered"
    if "already exists" in output:
        return "already-registered"
    return f"failed: {(result.stderr or result.stdout).strip()}"


def rules_path(project_root: Path) -> Path:
    return project_root / "CLAUDE.md"


def global_rules_path() -> Path:
    """~/.claude/CLAUDE.md -- loaded into every session regardless of project,
    concatenated after any project-level CLAUDE.md. Confirmed against
    https://code.claude.com/docs/en/memory.md."""
    return Path.home() / ".claude" / "CLAUDE.md"


AGENT = Agent(
    key="claude-code",
    label="Claude Code",
    detect=detect,
    register_mcp=register_mcp,
    rules_path=rules_path,
    global_rules_path=global_rules_path,
)
