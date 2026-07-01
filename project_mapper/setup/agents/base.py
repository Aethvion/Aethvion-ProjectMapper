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

    register_mcp: Callable[[Path, bool], str]
    """(project_root, global_only) -> "registered" | "already-registered" |
    "failed: <reason>". global_only is True when --global was passed to
    pm-setup: agents whose registration can silently fall back to a
    project-scoped file (Claude Code without the `claude` CLI on PATH) must
    refuse instead of writing into whatever the cwd happens to be."""

    rules_path: Callable[[Path], Path]
    """project_root -> path to the project-scoped rules file this agent reads
    at session start. Must be re-written in every project you want it in."""

    rules_frontmatter: str = ""
    """Prepended to a newly-created rules file (Cursor's .mdc needs YAML
    frontmatter to auto-apply; CLAUDE.md/AGENTS.md need none)."""

    global_rules_path: Callable[[], Path] | None = None
    """() -> path to a user-scoped rules file this agent loads in every
    session regardless of project, if one exists. None if the agent has no
    verified global rules mechanism -- --global then refuses rather than
    guessing at an unverified path."""
