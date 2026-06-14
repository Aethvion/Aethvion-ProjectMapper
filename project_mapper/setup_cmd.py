"""
pm-setup — configure an AI coding agent to use Project Mapper.

Usage:
    pm-setup <agent>

Agents:
    claude-code    Claude Code (CLI + desktop)
    cursor         Cursor IDE
    antigravity    Google Antigravity
    codex          OpenAI Codex CLI

The command locates the agent's MCP config file, reads it safely,
adds a project-mapper entry under mcpServers, and writes back.
It never removes or overwrites existing settings.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ── Agent registry ────────────────────────────────────────────────────────────
# Each entry maps a CLI name to:
#   label   — human-readable agent name (for output)
#   config  — absolute path to the MCP config file
#   key     — top-level JSON key that holds the mcpServers dict
#   entry   — the value to insert under mcpServers["project-mapper"]

_AGENTS: dict[str, dict] = {
    "claude-code": {
        "label":  "Claude Code",
        "config": Path.home() / ".claude" / "settings.json",
        "key":    "mcpServers",
        "entry":  {
            "type":    "stdio",
            "command": "pm-mcp",
            "args":    ["--db", "workspace"],
        },
    },
    "cursor": {
        "label":  "Cursor",
        "config": Path.home() / ".cursor" / "mcp.json",
        "key":    "mcpServers",
        # Cursor infers stdio automatically — no "type" field needed.
        "entry":  {
            "command": "pm-mcp",
            "args":    ["--db", "workspace"],
        },
    },
    "antigravity": {
        "label":  "Antigravity (Google)",
        "config": Path.home() / ".gemini" / "antigravity" / "mcp_config.json",
        "key":    "mcpServers",
        "entry":  {
            "type":    "stdio",
            "command": "pm-mcp",
            "args":    ["--db", "workspace"],
        },
    },
    "codex": {
        "label":  "Codex CLI",
        "config": Path.home() / ".codex" / "config.json",
        "key":    "mcpServers",
        "entry":  {
            "type":    "stdio",
            "command": "pm-mcp",
            "args":    ["--db", "workspace"],
        },
    },
}

_SERVER_NAME = "project-mapper"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _usage() -> None:
    print("Usage: pm-setup <agent>\n")
    print("Agents:")
    for name, info in _AGENTS.items():
        print(f"  {name:<14} {info['label']}")
    print()


def _err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        _usage()
        sys.exit(0)

    agent_key = args[0].lower()
    if agent_key not in _AGENTS:
        _err(f"Unknown agent: {agent_key!r}\n")
        _usage()
        sys.exit(1)

    agent       = _AGENTS[agent_key]
    config_path = Path(agent["config"])
    mcp_key     = agent["key"]
    entry       = agent["entry"]

    print(f"\nProject Mapper Setup")
    print(f"Agent:       {agent['label']}")
    print(f"Config file: {config_path}\n")

    # ── Step 1: read existing config ─────────────────────────────────────────
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8").strip()
        if raw:
            try:
                existing: dict = json.loads(raw)
            except json.JSONDecodeError as exc:
                _err(f"{config_path.name} contains invalid JSON — cannot modify safely.")
                _err(f"Please fix the file first, then re-run pm-setup.")
                _err(f"JSON error: {exc}")
                sys.exit(1)

            if not isinstance(existing, dict):
                _err(f"{config_path.name} is valid JSON but not an object — cannot merge.")
                sys.exit(1)
        else:
            existing = {}
        print(f"  Found existing {config_path.name}")
    else:
        existing = {}
        print(f"  No existing {config_path.name} — will create it")

    # ── Step 2: check if already configured ──────────────────────────────────
    if _SERVER_NAME in existing.get(mcp_key, {}):
        print(f"\n  project-mapper is already configured.")
        print(f"  Nothing to do — restart {agent['label']} if it was recently updated.\n")
        sys.exit(0)

    # ── Step 3: merge (only adds; never removes) ──────────────────────────────
    if mcp_key not in existing:
        existing[mcp_key] = {}

    existing[mcp_key][_SERVER_NAME] = entry

    # ── Step 4: write back ────────────────────────────────────────────────────
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    print(f"  Added project-mapper to {mcp_key}")
    print(f"\nDone. Restart {agent['label']} to activate Project Mapper.")
    print(f"Then ask: \"scan this project with Project Mapper\"\n")
