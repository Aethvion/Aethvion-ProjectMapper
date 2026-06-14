# Setting up Project Mapper with Claude Code

## Prerequisites

- Claude Code installed
- Internet connection (for the one-time download)

No Python installation needed — `uv` handles everything.

---

## Step 1 — Install `uv`

`uv` is a fast Python toolchain manager. Install it once and it manages Python and packages for you.

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

You should see the Project Mapper MCP server help text.

---

## Step 3 — Run pm-setup

```bash
pm-setup claude-code
```

`pm-setup` finds `~/.claude/settings.json`, reads it safely, adds the Project Mapper entry under `mcpServers`, and writes back — without touching any of your existing settings. If the file doesn't exist yet it creates it.

---

## Step 4 — Restart Claude Code

Fully restart Claude Code. The MCP server starts automatically on launch.

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
      "command": "pm-mcp",
      "args": ["--db", "workspace"],
      "env": { "PM_PROJECT_ROOT": "/absolute/path/to/your/project" }
    }
  }
}
```

---

## Troubleshooting

**`pm-mcp` not found** — the `uv tool install` step adds `pm-mcp` to `~/.local/bin` (Linux/macOS) or `%USERPROFILE%\.local\bin` (Windows). Open a **new** terminal window after installing — the PATH update only takes effect in new sessions. If it still doesn't work, run `uv tool list` to confirm the install succeeded.

**MCP server doesn't appear in Claude** — double-check that the JSON in `settings.json` is valid (no missing commas, no unmatched braces). Paste it into [jsonlint.com](https://jsonlint.com) if unsure.

**Updating to a new version** — run `uv tool upgrade aethvion-project-mapper` to get the latest release.

---

## Manual setup (alternative to pm-setup)

If you prefer to edit the config yourself, open `~/.claude/settings.json` in any text editor (create it if it doesn't exist) and add the `mcpServers` block:

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

If the file already has other settings, add only the `"mcpServers"` key alongside them — do not replace the whole file.
