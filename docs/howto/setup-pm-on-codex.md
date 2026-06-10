# Setting up Project Mapper with OpenAI Codex CLI

## Prerequisites

- OpenAI Codex CLI installed (`npm install -g @openai/codex` or via the official installer)
- Internet connection (for the one-time download)

No Python installation needed — `uv` handles everything.

---

## Step 1 — Install `uv`

| OS | Command |
|---|---|
| **macOS / Linux** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Windows (PowerShell)** | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| **Already have Python** | `pip install uv` |

After installing, open a **new terminal window** so the `uv` command is on your PATH.

---

## Step 2 — Install Project Mapper

```bash
uv tool install "aethvion-project-mapper[languages]"
```

This downloads Project Mapper and all language parsers (~30 seconds on first run). When it finishes, `pm-mcp` is available as a global command.

**Verify it worked:**

```bash
pm-mcp --help
```

---

## Step 3 — Find your config file

Codex CLI reads its configuration from:

| OS | Path |
|---|---|
| Windows | `C:\Users\<YourUsername>\.codex\config.json` |
| Linux / macOS | `~/.codex/config.json` |

**How to get there:**

- **Windows** — Open File Explorer and paste `%USERPROFILE%\.codex` into the address bar.
- **macOS** — Finder → Go → Go to Folder → `~/.codex`.
- **Linux** — `cd ~/.codex` in a terminal.

---

## Step 4 — Add the mcpServers block

Open `config.json` in any text editor. If it doesn't exist yet, create it (and the `.codex` folder if needed). The config is the same on every OS:

```json
{
  "mcpServers": {
    "project-mapper": {
      "type": "stdio",
      "command": "pm-mcp",
      "args": ["--db", "workspace"]
    }
  }
}
```

> **Note:** Codex CLI MCP support was introduced in 2025. If the config format has changed
> in a newer release, check the [official Codex CLI docs](https://github.com/openai/codex) for
> the latest MCP configuration reference.

---

## Step 5 — Restart Codex CLI

Start a new Codex CLI session. MCP servers are launched automatically at session start.

---

## Step 6 — Smoke test

Open any project and say:

> "Use Project Mapper to scan this project."

The agent will call `pm_scan` with the current directory. Once indexed, try:

> "What should I know before touching the auth system?"  
> "What breaks if I change UserService?"

---

## Optional — pin to a specific project

Add `PM_PROJECT_ROOT` via the `env` field if you always work in the same codebase:

```json
{
  "mcpServers": {
    "project-mapper": {
      "type": "stdio",
      "command": "pm-mcp",
      "args": ["--db", "workspace"],
      "env": { "PM_PROJECT_ROOT": "/path/to/your/project" }
    }
  }
}
```

---

## Troubleshooting

**`pm-mcp` not found** — open a **new** terminal window after installing. Run `uv tool list` to confirm the install succeeded.

**MCP server not connecting** — run `codex --version` to confirm your Codex CLI version supports MCP, then verify the JSON in `config.json` is valid using [jsonlint.com](https://jsonlint.com).

**Updating to a new version** — run `uv tool upgrade aethvion-project-mapper`.
