# Setting up Project Mapper with Antigravity (Google)

## Prerequisites

- Python 3.10+ installed and available as `python` on your PATH
- The [Aethvion-ProjectMapper](https://github.com/Aethvion/Aethvion-ProjectMapper) repo cloned somewhere on your machine
- Antigravity installed and set up with your Google account

---

## Step 1 — Find your MCP config file

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

## Step 2 — Open or create the file

If the file (or the `.gemini/antigravity` folder) doesn't exist yet, create it. Start with an empty object:

```json
{}
```

---

## Step 3 — Add the mcpServers block

**Windows** — replace `C:/example-path/Aethvion-ProjectMapper` with your actual clone path:

```json
{
  "mcpServers": {
    "project-mapper": {
      "type": "stdio",
      "command": "python",
      "args": [
        "-m", "project_mapper.mcp_server",
        "--db", "workspace"
      ],
      "cwd": "C:/example-path/Aethvion-ProjectMapper"
    }
  }
}
```

**Linux / macOS** — replace `/home/you/Aethvion-ProjectMapper` with your actual clone path:

```json
{
  "mcpServers": {
    "project-mapper": {
      "type": "stdio",
      "command": "python",
      "args": [
        "-m", "project_mapper.mcp_server",
        "--db", "workspace"
      ],
      "cwd": "/home/you/Aethvion-ProjectMapper"
    }
  }
}
```

> **Windows path note:** Antigravity accepts forward slashes on Windows (`C:/path/to/repo`),
> which avoids the need to double backslashes. Both styles work.

---

## Step 4 — Restart Antigravity

Save the file and restart Antigravity. MCP servers are loaded at startup.

---

## Step 5 — Smoke test

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
      "command": "python",
      "args": [
        "-m", "project_mapper.mcp_server",
        "--db", "workspace"
      ],
      "cwd": "C:/example-path/Aethvion-ProjectMapper",
      "env": { "PM_PROJECT_ROOT": "C:/path/to/your/project" }
    }
  }
}
```

---

## Troubleshooting

**`python` not found** — confirm Python 3.10+ is installed. Change `"command": "python"` to `"command": "python3"` if your system uses that name.

**Config file not picked up** — make sure the file is named exactly `mcp_config.json` inside the `antigravity` subfolder, not `mcp.json` or `settings.json`.

**`cwd` path errors** — the path must point to the repo root (the folder containing `project_mapper/`), not to `project_mapper/` itself.
