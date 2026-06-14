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

## Step 3 — Run pm-setup

```bash
pm-setup codex
```

`pm-setup` finds `~/.codex/config.json`, reads it safely, adds the Project Mapper entry under `mcpServers`, and writes back — without touching any of your existing settings. If the file or folder doesn't exist yet it creates them.

---

## Step 4 — Restart Codex CLI

Start a new Codex CLI session. MCP servers are launched automatically at session start.

---

## Step 5 — Smoke test

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

---

## Manual setup (alternative to pm-setup)

If you prefer to edit the config yourself, open `~/.codex/config.json` in any text editor (create the file and folder if they don't exist) and add the `mcpServers` block:

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

> Codex CLI MCP support was introduced in 2025. If the config format has changed in a newer release, check the [official Codex CLI docs](https://github.com/openai/codex) for the latest MCP configuration reference.

If the file already has other settings, add only the `"mcpServers"` key alongside them — do not replace the whole file.
