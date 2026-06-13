# docs/howto/

Step-by-step setup guides for connecting Project Mapper to your AI coding agent. Each guide covers installation, configuration, and a quick verification that everything is working.

For background on what Project Mapper is and how MCP tools work, see [`docs/explained/`](../explained/).

---

| Guide | Agent |
|:---|:---|
| [Setup on Claude Code](setup-pm-on-claude-code.md) | Anthropic Claude Code (CLI + desktop) |
| [Setup on Cursor](setup-pm-on-cursor.md) | Cursor IDE |
| [Setup on Antigravity](setup-pm-on-antigravity.md) | Google Antigravity |
| [Setup on Codex](setup-pm-on-codex.md) | OpenAI Codex CLI |

---

All guides follow the same two steps: install `pm-mcp` via `uv`, then add the MCP server config to your agent's settings file. No Python installation is required — `uv` manages the environment automatically.
