"""
project_mapper/setup/agents/base.py
The Agent contract every platform module implements. cli.py only ever talks
to this shape -- it doesn't know or care whether a given agent is configured
via a CLI command or a hand-edited JSON file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Agent:
    key: str
    """CLI flag name, e.g. "claude-code" for --claude-code."""

    label: str
    """Human-readable name, e.g. "Claude Code"."""

    detect: Callable[[], bool]
    """Best-effort check for whether this agent looks installed on the
    machine. Used only to drive the interactive prompt when pm-setup is run
    with no flags -- never blocks an explicit --flag invocation."""

    register_mcp: Callable[[Path], str]
    """project_root -> "registered" | "already-registered" | "failed: <reason>"."""

    rules_path: Callable[[Path], Path]
    """project_root -> path to the rules file this agent reads at session start."""

    rules_frontmatter: str = ""
    """Prepended to a newly-created rules file (Cursor's .mdc needs YAML
    frontmatter to auto-apply; CLAUDE.md/AGENTS.md need none)."""
