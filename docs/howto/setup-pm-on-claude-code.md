# Setting up Project Mapper with Claude Code

## Prerequisites

- Python 3.10+ installed and available as `python` on your PATH
- The [Aethvion-ProjectMapper](https://github.com/Aethvion/Aethvion-ProjectMapper) repo cloned somewhere on your machine
- Claude Code installed

---

## Step 1 — Find your settings file

The global Claude Code settings file lives at:

| OS | Path |
|---|---|
| Windows | `C:\Users\<YourUsername>\.claude\settings.json` |
| Linux / macOS | `~/.claude/settings.json` |

**How to get there:**

- **Windows** — Open File Explorer and paste `%USERPROFILE%\.claude` into the address bar, then press Enter.
- **macOS** — Open Finder → Go → Go to Folder → type `~/.claude` → press Go.
- **Linux** — run `cd ~/.claude` in a terminal.

---

## Step 2 — Open or create the file

If `settings.json` does not exist yet, create it as an empty JSON file:

```json
{}
```

If it already exists, open it in any text editor (Notepad, VS Code, nano, etc.).

---

## Step 3 — Add the mcpServers block

Add a `"mcpServers"` key alongside any existing settings. The examples below show the most common starting point (default Claude Code install).

**Windows** — replace `C:\\example-path\\Aethvion-ProjectMapper` with your actual clone path:

```json
{
  "extraKnownMarketplaces": {
    "claude-plugins-official": {
      "source": {
        "source": "github",
        "repo": "anthropics/claude-plugins-official"
      }
    }
  },
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
  "extraKnownMarketplaces": {
    "claude-plugins-official": {
      "source": {
        "source": "github",
        "repo": "anthropics/claude-plugins-official"
      }
    }
  },
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

> **Windows path note:** JSON requires backslashes to be doubled. So the path
> `C:\Aethvion\Aethvion-ProjectMapper` becomes `C:\\Aethvion\\Aethvion-ProjectMapper` in the file.

If your `settings.json` was empty (`{}`), the result is simply:

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

---

## Step 4 — Restart Claude Code

Save the file and fully restart Claude Code. The MCP server starts automatically when Claude Code launches.

---

## Step 5 — Smoke test

Open a new session inside any project folder and say:

> "Use Project Mapper to scan this project."

Claude will call `pm_scan` with the current directory and index the codebase. Depending on project size this takes a few seconds to a few minutes. Once done, try:

> "What should I know before touching the auth system?"  
> "What breaks if I change UserService?"

Project Mapper is now available in every Claude Code session, for every project.

---

## Optional — pin to a specific project

If you always work in the same codebase, add `PM_PROJECT_ROOT` so the scan happens without Claude needing to ask for or derive a path:

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

**`python` not found** — make sure Python 3.10+ is installed and the `python` command works in a new terminal window. On some systems the command is `python3` — change `"command": "python"` to `"command": "python3"` if needed.

**MCP server doesn't appear in Claude** — double-check that the JSON in `settings.json` is valid (no missing commas, no unmatched braces). Paste it into [jsonlint.com](https://jsonlint.com) if unsure.

**`cwd` path errors** — make sure the path points to the folder that *contains* `project_mapper/` (i.e. the repo root), not to `project_mapper/` itself.
