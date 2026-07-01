# docs/howto/

Step-by-step setup guides for connecting Project Mapper to your AI coding agent. Each guide covers installation, configuration, making the agent actually prefer Project Mapper over its built-in tools, and a quick verification that everything is working.

For background on what Project Mapper is and how MCP tools work, see [`docs/explained/`](../explained/).

---

**Fastest path:** after installing (`uv tool install "aethvion-project-mapper[languages]" --python 3.10`), run `pm-setup --claude-code` (or `--cursor` / `--antigravity` / `--codex` / `--all`) — it registers the MCP server and writes the rules file that makes the agent prefer Project Mapper by default, in one idempotent command. On Claude Code, add `--global` to write that rules file to `~/.claude/CLAUDE.md` instead of the current project's — one run, every project, forever, matching the MCP registration (already user-scoped). Run it yourself, or tell your agent to. Each guide below also covers the manual steps it automates, in case you'd rather do it by hand or want to understand exactly what changes on your machine.

---

| Guide | Agent |
|:---|:---|
| [Setup on Claude Code](setup-pm-on-claude-code.md) | Anthropic Claude Code (CLI + desktop) |
| [Setup on Cursor](setup-pm-on-cursor.md) | Cursor IDE |
| [Setup on Antigravity](setup-pm-on-antigravity.md) | Google Antigravity |
| [Setup on Codex](setup-pm-on-codex.md) | OpenAI Codex CLI |

---

All guides follow the same shape: install `pm-mcp` via `uv`, then either run `pm-setup` or add the MCP server config and rules file by hand. No Python installation is required — `uv` manages the environment automatically.
