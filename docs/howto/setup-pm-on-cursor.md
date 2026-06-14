# Setting up Project Mapper with Cursor

## Prerequisites

- Cursor installed
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
pm-setup cursor
```

`pm-setup` finds `~/.cursor/mcp.json`, reads it safely, adds the Project Mapper entry under `mcpServers`, and writes back — without touching any of your existing settings. If the file doesn't exist yet it creates it.

---

## Step 4 — Restart Cursor

Fully restart Cursor. You can also reload MCP servers via **Cursor Settings → MCP** without a full restart.

---

## Step 5 — Smoke test

Open any project in Cursor and tell the AI:

> "Use Project Mapper to scan this project."

The agent will call `pm_scan` with the current directory. Once indexed, try:

> "What should I know before touching the auth system?"  
> "What breaks if I change UserService?"

---

## Optional — pin to a specific project

Add `PM_PROJECT_ROOT` via the `env` field so the AI always knows which project to scan without being told:

```json
{
  "mcpServers": {
    "project-mapper": {
      "command": "pm-mcp",
      "args": ["--db", "workspace"],
      "env": { "PM_PROJECT_ROOT": "/path/to/your/project" }
    }
  }
}
```

---

## Troubleshooting

**`pm-mcp` not found** — open a **new** terminal window after installing. The PATH update only takes effect in new sessions. If it still fails, run `uv tool list` to confirm the install succeeded.

**Server not appearing in Cursor** — check **Cursor Settings → MCP** to see if the server shows a connection error. Verify the JSON in `mcp.json` is valid using [jsonlint.com](https://jsonlint.com).

**Updating to a new version** — run `uv tool upgrade aethvion-project-mapper`.

---

## Manual setup (alternative to pm-setup)

If you prefer to edit the config yourself, open `~/.cursor/mcp.json` in any text editor (create it if it doesn't exist) and add the `mcpServers` block:

```json
{
  "mcpServers": {
    "project-mapper": {
      "command": "pm-mcp",
      "args": ["--db", "workspace"]
    }
  }
}
```

> Cursor does not require a `"type"` field — it infers `stdio` automatically.

If the file already has other settings, add only the `"mcpServers"` key alongside them — do not replace the whole file.
