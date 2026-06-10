# Setting up Project Mapper with OpenAI Codex CLI

## Prerequisites

- Python 3.10+ installed and available as `python` on your PATH
- The [Aethvion-ProjectMapper](https://github.com/Aethvion/Aethvion-ProjectMapper) repo cloned somewhere on your machine
- OpenAI Codex CLI installed (`npm install -g @openai/codex` or via the official installer)

---

## Step 1 — Find your config file

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

## Step 2 — Open or create the file

If `config.json` doesn't exist, create it (and the `.codex` folder if needed) as an empty object:

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
      "type": "stdio",
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

> **Windows path note:** Backslashes must be doubled in JSON. So
> `C:\Aethvion\Aethvion-ProjectMapper` becomes `C:\\Aethvion\\Aethvion-ProjectMapper`.

> **Note:** Codex CLI MCP support was introduced in 2025. If the config format has changed
> in a newer release, check the [official Codex CLI docs](https://github.com/openai/codex) for
> the latest MCP configuration reference.

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

**`python` not found** — confirm Python 3.10+ is installed. Change `"command": "python"` to `"command": "python3"` if needed.

**MCP server not connecting** — run `codex --version` to confirm your Codex CLI version supports MCP, then verify the JSON in `config.json` is valid.

**`cwd` path errors** — the path must point to the repo root (the folder containing `project_mapper/`), not to `project_mapper/` itself.
