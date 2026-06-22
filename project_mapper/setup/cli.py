"""
project_mapper/setup/cli.py
pm-setup entry point. Registers Project Mapper as an MCP server with one or
more coding agents, and writes the "prefer this tool" rules file each one
reads into context at the start of every session.

Usage
-----
    pm-setup --claude-code
    pm-setup --cursor --antigravity
    pm-setup --all
    pm-setup                         # no flags: detect what's installed, confirm interactively

Safe to run more than once -- every step checks for an existing entry before
writing anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agents import AGENTS, Agent
from .rules import append_directive


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pm-setup",
        description="Register Project Mapper with your AI coding agent and configure it "
        "to use it by default.",
    )
    for agent in AGENTS.values():
        parser.add_argument(
            f"--{agent.key}",
            action="store_true",
            help=f"Configure {agent.label}",
        )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Configure every detected agent without prompting",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project to write the rules file into (default: current directory)",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    flags = {agent.key: getattr(args, agent.key.replace("-", "_")) for agent in AGENTS.values()}

    if args.all:
        chosen = list(AGENTS.values())
    elif any(flags.values()):
        chosen = [AGENTS[key] for key, selected in flags.items() if selected]
    else:
        chosen = _interactive_pick()

    if not chosen:
        print("Nothing selected. Run with --claude-code, --cursor, --antigravity, --codex, "
              "or --all.")
        sys.exit(1)

    print(f"Configuring Project Mapper for: {project_root}\n")
    any_failed = False
    for agent in chosen:
        any_failed |= _configure(agent, project_root)
    sys.exit(1 if any_failed else 0)


def _interactive_pick() -> list[Agent]:
    detected = [agent for agent in AGENTS.values() if agent.detect()]
    if not detected:
        print("Couldn't auto-detect any supported agent on this machine.")
        print("Available: " + ", ".join(f"--{a.key}" for a in AGENTS.values()))
        return []

    print("Detected:")
    for agent in detected:
        print(f"  - {agent.label}")
    answer = input(f"\nConfigure Project Mapper for {'these' if len(detected) > 1 else 'this'}? [Y/n] ")
    if answer.strip().lower() in ("", "y", "yes"):
        return detected
    return []


def _configure(agent: Agent, project_root: Path) -> bool:
    """Run both steps for one agent. Returns True if anything failed."""
    mcp_status = agent.register_mcp(project_root)
    rules_status = append_directive(agent.rules_path(project_root), frontmatter=agent.rules_frontmatter)

    failed = mcp_status.startswith("failed")
    mark = "x" if failed else "+"
    print(f"[{mark}] {agent.label}: MCP {mcp_status}")
    print(f"[{'+' if not failed else 'x'}] {agent.label}: rules file {rules_status} "
          f"({agent.rules_path(project_root)})")
    return failed


if __name__ == "__main__":
    main()
