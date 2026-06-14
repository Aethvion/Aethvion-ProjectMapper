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
uv tool install "aethvion-project-mapper[languages]" --python 3.10
```

This downloads Project Mapper and all language parsers (~30 seconds on first run). When it finishes, `pm-mcp` is available as a global command. `--python 3.10` pins the exact Python version Project Mapper is tested on, in an isolated environment, so the install is reproducible and never collides with your system Python.

**Verify it worked:**

```bash
pm-mcp --help
```

You should see the Project Mapper MCP server help text.

---

## Step 3 — Add the MCP config

Register Project Mapper for **all** your projects with the Claude Code CLI:

```bash
claude mcp add -s user project-mapper -- pm-mcp --db workspace
```

This writes to `~/.claude.json` — the file Claude Code actually reads for MCP servers.

> ⚠️ **Do not** add `mcpServers` to `~/.claude/settings.json`. Claude Code **ignores** MCP definitions there — the server will silently never load. It only reads them from `~/.claude.json` (what `claude mcp add` writes) or a project-level `.mcp.json`.

**No `claude` CLI on your PATH?** Create a `.mcp.json` file in the root of the project you want to use Project Mapper in, with exactly this content:

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

This enables it for that one project. (The CLI command above enables it everywhere.)

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

**MCP server doesn't appear in Claude** — first confirm it's registered: run `claude mcp list` (or `/mcp` inside Claude Code). If it's missing, the config went to the wrong place — make sure it's in `~/.claude.json` or a project `.mcp.json`, **not** `~/.claude/settings.json`. If it's listed but failing, check the per-server log under `%LOCALAPPDATA%\claude-cli-nodejs\Cache\<project>\mcp-logs-project-mapper\` for the exact error.

**Updating to a new version** — run `uv tool upgrade aethvion-project-mapper` to get the latest release.
