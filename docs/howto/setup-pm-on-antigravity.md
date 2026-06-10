# Setting up Project Mapper with Antigravity (Google)

## Prerequisites

- Antigravity installed and set up with your Google account
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

## Step 3 — Find your MCP config file

Antigravity reads MCP server configuration from:

| OS | Path |
|---|---|
| Windows | `C:\Users\<YourUsername>\.gemini\antigravity\mcp_config.json` |
| Linux / macOS | `~/.gemini/antigravity/mcp_config.json` |

**How to get there:**

- **Windows** — Open File Explorer and paste `%USERPROFILE%\.gemini\antigravity` into the address bar.
- **macOS** — Finder → Go → Go to Folder → `~/.gemini/antigravity`.
- **Linux** — `cd ~/.gemini/antigravity` in a terminal.

---

## Step 4 — Add the mcpServers block

Open `mcp_config.json` in any text editor. If the file or the `.gemini/antigravity` folder doesn't exist yet, create them. The config is the same on every OS:

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

---

## Step 5 — Restart Antigravity

Save the file and restart Antigravity. MCP servers are loaded at startup.

---

## Step 6 — Smoke test

Open any project and tell the agent:

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

**Config file not picked up** — make sure the file is named exactly `mcp_config.json` inside the `antigravity` subfolder, not `mcp.json` or `settings.json`.

**Updating to a new version** — run `uv tool upgrade aethvion-project-mapper`.
