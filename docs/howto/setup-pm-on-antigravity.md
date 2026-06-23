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
pm-setup --antigravity
```

This does Steps 3 and 6 below for you in one command — registers the MCP server in `~/.gemini/antigravity/mcp_config.json` (merging in alongside anything already there) and writes `AGENTS.md` with the rules that make Antigravity actually prefer Project Mapper over its built-in file search. Safe to run more than once. Run it yourself, or tell Antigravity to ("install and set up Aethvion Project Mapper for this project") — same command either way. Skip ahead to [Step 5 — Smoke test](#step-5--smoke-test).

The rest of this guide walks through what `pm-setup` does, by hand — useful if you'd rather not run a script, or want to understand exactly what changes on your machine.

---

## Step 3 — Add the MCP config

Open `~/.gemini/antigravity/mcp_config.json` in any text editor (create the file and the `antigravity` folder if they don't exist) and add the `project-mapper` entry. If the file already has other settings, add only the `"mcpServers"` key alongside them — don't replace the whole file.

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

## Step 4 — Restart Antigravity

Restart Antigravity. MCP servers are loaded at startup.

---

## Step 5 — Smoke test

Open any project and tell the agent:

> "Use Project Mapper to scan this project."

The agent will call `pm_scan` with the current directory. Once indexed, try:

> "What should I know before touching the auth system?"  
> "What breaks if I change UserService?"

---

## Step 6 — Make Antigravity actually use this by default

> Already ran `pm-setup --antigravity` in the Fast path above? This step is done — it wrote this exact file. Read on only if you're curious what it did, or skip to [Step 5 — Smoke test](#step-5--smoke-test).

Installing the server isn't enough — by default, Antigravity reaches for its own file search out of habit, even with Project Mapper available. Fix this once per project by adding an `AGENTS.md` file at the project root (the same cross-tool standard Codex uses):

```markdown
## Code navigation

This project has Project Mapper (MCP) indexed. Always prefer `pm_find`,
`pm_context`, and `pm_impact` over built-in file search when locating
symbols, understanding code structure, or assessing change impact — they
return precise, ranked results at a fraction of the token cost.
```

For a global override across all your projects instead of per-project, put the same content in `~/.gemini/GEMINI.md` — it's Antigravity-specific and takes priority over `AGENTS.md` when both exist.

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
