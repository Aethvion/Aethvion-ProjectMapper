"""
project_mapper/setup/cli.py
pm-setup entry point. Registers Project Mapper as an MCP server with one or
more coding agents, and writes the "prefer this tool" rules file each one
reads into context at the start of every session.

Usage
-----
    pm-setup --claude-code --global  # Claude Code: one-time, every project, forever
    pm-setup --claude-code
    pm-setup --cursor --antigravity
    pm-setup --all
    pm-setup                         # no flags: detect what's installed, confirm interactively

Safe to run more than once -- every step checks for an existing entry before
writing anything. --global writes the rules file to the agent's user-level
rules file (currently only Claude Code: ~/.claude/CLAUDE.md) instead of the
project's, matching the MCP registration, which is already user-scoped for
every agent. Agents without a verified global rules path refuse rather than
guess at one.
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
        help="Project to write the rules file into (default: current directory). "
        "Ignored for the rules file when --global is set.",
    )
    parser.add_argument(
        "--global",
        dest="use_global",
        action="store_true",
        help="Write the 'prefer this tool' directive to the agent's user-level rules "
        "file (e.g. ~/.claude/CLAUDE.md) instead of the project's. Since MCP "
        "registration is already user-scoped, this makes the whole setup a "
        "true one-time, run-from-anywhere command -- no per-project repeat needed.",
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
        any_failed |= _configure(agent, project_root, use_global=args.use_global)
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


def _configure(agent: Agent, project_root: Path, *, use_global: bool = False) -> bool:
    """Run both steps for one agent. Returns True if anything failed."""
    mcp_status = agent.register_mcp(project_root, use_global)
    mcp_failed = mcp_status.startswith("failed")
    print(f"[{'x' if mcp_failed else '+'}] {agent.label}: MCP {mcp_status}")

    if use_global:
        if agent.global_rules_path is None:
            print(f"[x] {agent.label}: no verified global rules file for this agent yet -- "
                  f"omit --global to write {agent.rules_path(project_root)} per-project instead")
            return True
        rules_path = agent.global_rules_path()
    else:
        rules_path = agent.rules_path(project_root)

    rules_status = append_directive(rules_path, frontmatter=agent.rules_frontmatter)
    print(f"[+] {agent.label}: rules file {rules_status} ({rules_path})")
    return mcp_failed


if __name__ == "__main__":
    main()
