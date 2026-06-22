"""
project_mapper/setup/rules.py
The "prefer Project Mapper over built-in search" directive block, and an
idempotent function to write it into an agent's rules file (CLAUDE.md,
AGENTS.md, or a Cursor .mdc rule).

The HTML-comment marker lets re-runs detect "already configured" without
string-matching the full body, so the wording can change in a later release
without breaking detection on existing installs.
"""

from __future__ import annotations

from pathlib import Path

DIRECTIVE_MARKER = "<!-- project-mapper:rules -->"

DIRECTIVE_BODY = """## Code navigation

This project has Project Mapper (MCP) indexed. Always prefer `pm_find`,
`pm_context`, and `pm_impact` over built-in grep/glob/file-read tools when
locating symbols, understanding code structure, or assessing change impact —
they return precise, ranked results at a fraction of the token cost. Use
built-in file tools only for editing files or reading ones you've already
located."""

DIRECTIVE_BLOCK = f"{DIRECTIVE_MARKER}\n{DIRECTIVE_BODY}\n{DIRECTIVE_MARKER}\n"

# Cursor's .mdc rule format needs YAML frontmatter to auto-apply; everything
# else (CLAUDE.md, AGENTS.md) is read as plain Markdown.
CURSOR_FRONTMATTER = """---
description: Prefer Project Mapper over built-in search
alwaysApply: true
---

"""


def append_directive(path: Path, *, frontmatter: str = "") -> str:
    """Write the directive block into `path` if it isn't already there.

    Returns one of:
      "created"          -- file didn't exist, created with the directive
      "added"             -- file existed, directive appended
      "already-present"   -- file already contains the marker, untouched
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(frontmatter + DIRECTIVE_BLOCK, encoding="utf-8")
        return "created"

    text = path.read_text(encoding="utf-8")
    if DIRECTIVE_MARKER in text:
        return "already-present"

    separator = "" if not text.strip() else text.rstrip("\n") + "\n\n"
    path.write_text(separator + DIRECTIVE_BLOCK, encoding="utf-8")
    return "added"
