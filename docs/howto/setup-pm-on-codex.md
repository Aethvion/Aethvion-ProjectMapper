# Setting up Project Mapper with OpenAI Codex CLI

## Prerequisites

- OpenAI Codex CLI installed (`npm install -g @openai/codex` or via the official installer)
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

## Step 3 — Add the MCP config

Open `~/.codex/config.json` in any text editor (create the file and folder if they don't exist) and add the `project-mapper` entry. If the file already has other settings, add only the `"mcpServers"` key alongside them — don't replace the whole file.

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

> Codex CLI MCP support was introduced in 2025. If the config format has changed in a newer release, check the [official Codex CLI docs](https://github.com/openai/codex) for the latest MCP configuration reference.

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

## Step 6 — Make Codex actually use this by default

Installing the server isn't enough — by default, Codex reaches for its own file search out of habit, even with Project Mapper available. Fix this once per project by adding an `AGENTS.md` file at the project root:

```markdown
## Code navigation

This project has Project Mapper (MCP) indexed. Always prefer `pm_find`,
`pm_context`, and `pm_impact` over built-in file search when locating
symbols, understanding code structure, or assessing change impact — they
return precise, ranked results at a fraction of the token cost.
```

Codex CLI loads `AGENTS.md` into every session automatically — this is a standing instruction, not a one-time prompt, so you only need to add it once per project.

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

**MCP server not connecting** — run `codex --version` to confirm your Codex CLI version supports MCP, then verify the JSON in `config.json` is valid using [jsonlint.com](https://jsonlint.com).

**Updating to a new version** — run `uv tool upgrade aethvion-project-mapper`.
