"""project_mapper.setup.agents -- the registry cli.py selects from."""

from __future__ import annotations

from . import antigravity, claude_code, codex, cursor
from .base import Agent

AGENTS: dict[str, Agent] = {
    claude_code.AGENT.key: claude_code.AGENT,
    cursor.AGENT.key: cursor.AGENT,
    antigravity.AGENT.key: antigravity.AGENT,
    codex.AGENT.key: codex.AGENT,
}

__all__ = ["AGENTS", "Agent"]
