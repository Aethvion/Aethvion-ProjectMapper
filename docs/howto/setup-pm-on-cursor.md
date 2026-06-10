# Setting up Project Mapper with Cursor

## Prerequisites

- Python 3.10+ installed and available as `python` on your PATH
- The [Aethvion-ProjectMapper](https://github.com/Aethvion/Aethvion-ProjectMapper) repo cloned somewhere on your machine
- Cursor installed

---

## Step 1 — Find your MCP config file

Cursor uses a dedicated MCP config file separate from its main settings.

| Scope | OS | Path |
|---|---|---|
| Global (all projects) | Windows | `C:\Users\<YourUsername>\.cursor\mcp.json` |
| Global (all projects) | Linux / macOS | `~/.cursor/mcp.json` |
| Project-only | Any | `.cursor/mcp.json` inside the project folder |

For most users the **global** file is the right choice — it makes Project Mapper available in every workspace without repeating the config.

**How to get there:**

- **Windows** — Open File Explorer and paste `%USERPROFILE%\.cursor` into the address bar.
- **macOS** — Finder → Go → Go to Folder → `~/.cursor`.
- **Linux** — `cd ~/.cursor` in a terminal.

---

## Step 2 — Open or create the file

If `mcp.json` does not exist yet, create it. If the `.cursor` folder also doesn't exist, create that first.

Start with an empty object:

```json
{}
```

---

## Step 3 — Add the mcpServers block

**Windows** — replace `C:\\example-path\\Aethvion-ProjectMapper` with your actual clone path:

```json
{
  "mcpServers": {
    "project-mapper": {
      "command": "python",
      "args": [
        "-m", "project_mapper.mcp_server",
        "--db", "workspace"
      ],
      "cwd": "C:\\example-path\\Aethvion-ProjectMapper"
    }
  }
}
```

**Linux / macOS** — replace `/home/you/Aethvion-ProjectMapper` with your actual clone path:

```json
{
  "mcpServers": {
    "project-mapper": {
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

> **Note:** Cursor does not require a `"type"` field — it infers `stdio` automatically.

> **Windows path note:** Backslashes must be doubled in JSON. So
> `C:\Aethvion\Aethvion-ProjectMapper` becomes `C:\\Aethvion\\Aethvion-ProjectMapper`.

---

## Step 4 — Restart Cursor

Save the file and fully restart Cursor. You can also reload MCP servers via **Cursor Settings → MCP** without a full restart.

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
      "command": "python",
      "args": [
        "-m", "project_mapper.mcp_server",
        "--db", "workspace"
      ],
      "cwd": "C:\\example-path\\Aethvion-ProjectMapper",
      "env": { "PM_PROJECT_ROOT": "C:\\path\\to\\your\\project" }
    }
  }
}
```

---

## Troubleshooting

**`python` not found** — confirm Python 3.10+ is installed and the `python` command works in a new terminal. Change `"command": "python"` to `"command": "python3"` if your system uses that name.

**Server not appearing in Cursor** — check **Cursor Settings → MCP** to see if the server shows a connection error. A red dot usually means a path is wrong or Python can't be found.

**`cwd` path errors** — the path must point to the repo root (the folder containing `project_mapper/`), not to `project_mapper/` itself.
