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
uv tool install "aethvion-project-mapper[languages]" --python 3.10
```

This downloads Project Mapper and all language parsers (~30 seconds on first run). When it finishes, `pm-mcp` is available as a global command. `--python 3.10` pins the exact Python version Project Mapper is tested on, in an isolated environment, so the install is reproducible and never collides with your system Python.

**Verify it worked:**

```bash
pm-mcp --help
```

---

## Fast path — skip to Step 5

```bash
pm-setup --cursor
```

This does Steps 3 and 6 below for you in one command — registers the MCP server in `~/.cursor/mcp.json` (merging in alongside anything already there) and writes `.cursor/rules/project-mapper.mdc` with the rules that make Cursor actually prefer Project Mapper over its built-in search. Safe to run more than once. Run it yourself, or tell Cursor to ("install and set up Aethvion Project Mapper for this project") — same command either way. Skip ahead to [Step 5 — Smoke test](#step-5--smoke-test).

The rest of this guide walks through what `pm-setup` does, by hand — useful if you'd rather not run a script, or want to understand exactly what changes on your machine.

---

## Step 3 — Add the MCP config

Open `~/.cursor/mcp.json` in any text editor (create it if it doesn't exist) and add the `project-mapper` entry. If the file already has other settings, add only the `"mcpServers"` key alongside them — don't replace the whole file.

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

> Cursor doesn't need a `"type"` field — it infers `stdio` automatically.

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

## Step 6 — Make Cursor actually use this by default

> Already ran `pm-setup --cursor` in the Fast path above? This step is done — it wrote this exact file. Read on only if you're curious what it did, or skip to [Step 5 — Smoke test](#step-5--smoke-test).

Installing the server isn't enough — by default, Cursor reaches for its own codebase search out of habit, even with Project Mapper available. Fix this once per project by adding a rule file at `.cursor/rules/project-mapper.mdc`:

```markdown
---
description: Prefer Project Mapper over built-in search
alwaysApply: true
---

Project Mapper (MCP) is available. If this project hasn't been scanned yet,
call `pm_scan` first. Then always prefer `pm_find`, `pm_context`, and
`pm_impact` over built-in codebase search when locating symbols,
understanding code structure, or assessing change impact — they return
precise, ranked results at a fraction of the token cost. Use built-in
search only for what Project Mapper doesn't cover.
```

On older Cursor versions without `.cursor/rules/`, use a single `.cursorrules` file at the project root with the same body text instead.

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
