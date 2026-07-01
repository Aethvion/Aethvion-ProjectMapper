# Aethvion Project Mapper

> **Give your AI coding agent a living map of your codebase.**  
> Scans once, builds a knowledge graph, answers architecture queries in milliseconds — at **87–91% fewer tokens** than reading raw files.  
> **Runs entirely on your machine.** No data leaves your computer.

---

## Quick Start

**Step 1 — Install `uv`** (one-time, manages Python automatically):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Step 2 — Install Project Mapper:**

```bash
uv tool install "aethvion-project-mapper[languages]" --python 3.10
```

**Step 3 — Connect to your agent and make it actually use Project Mapper:**

```bash
pm-setup --claude-code --global   # Claude Code: one-time, covers every project
pm-setup --claude-code            # or: this project only; also --cursor / --antigravity / --codex / --all
```

`pm-setup` registers the MCP server *and* writes a rules file (`CLAUDE.md`, `.cursor/rules/`, or `AGENTS.md`) telling the agent to prefer Project Mapper over built-in grep/glob/read — the part most setups skip. Without it, the tool is installed but the agent still defaults to its own search out of habit. Safe to re-run; never duplicates or overwrites unrelated config. See [why this step exists](#make-your-agent-actually-use-it).

No terminal access, or you'd rather your agent do it? Paste this into a chat with your agent instead:
> Install and set up Aethvion Project Mapper (https://github.com/Aethvion/Aethvion-ProjectMapper) for this project.

Prefer to do it by hand, or `pm-setup` doesn't support your agent yet? Step-by-step manual guides: [`docs/howto/`](docs/howto/README.md)

New here? The [`docs/explained/`](docs/explained/README.md) folder covers [what Project Mapper is](docs/explained/what-is-project-mapper.md), [what MCP tools are](docs/explained/what-is-mcp.md), [exactly what PM reads and stores on your machine](docs/explained/what-does-pm-access.md), and the [full tools reference](docs/explained/project-mapper-tools.md).

---

## Why it exists

AI coding agents (Claude Code, Cursor, Copilot, etc.) search through your files on every task — reading source files, following imports, grepping for context. That's expensive and slow, and context windows fill up with semi-relevant content before the agent sees what actually matters.

Project Mapper scans your codebase once, builds a structured knowledge graph of every module, class, function, and their relationships, and lets agents query *only what they need* — in milliseconds, reducing token costs by **87–91% on average**.

---

## Benchmark numbers

Measured across [11 real-world codebases](docs/benchmarks/README.md) — Python, Java/Kotlin, C#, PHP, C, Go, Ruby, TypeScript/JS, Rust, C++, Swift — ranging from 57 to 10,437 files.

### Summary (Geometric Mean across all 11 projects)

| Mode | Token Reduction | Speedup vs Normal |
|:---|:---|:---|
| **PM Full** | **~87%** | **~380×** faster |
| **PM Slim** | **~91%** | **~380×** faster |

At 100,000 input tokens, PM typically uses **~13,000** (Full) or **~9,000** (Slim) tokens.

PM Slim returns name + file path + line number only — enough for navigation and refactoring tasks. PM Full returns complete entity context. See the [full benchmark suite](docs/benchmarks/README.md) for per-codebase numbers and the [security benchmark](docs/benchmarks_security/README.md) for a 3-test audit comparison.

### Query latency (measured)

| Query | Latency |
|---|---|
| Context query | 1–100 ms (warm cache) |
| Impact query | < 1–10 ms |

### Session startup — entity map load (measured)

The entity map is stored as a single snapshot file built at the end of each scan.

| Codebase size | Load time |
|---|---|
| ~400 entities | < 50 ms |
| ~12,000 entities | ~145 ms |
| ~33,000 entities | ~300 ms |

### Financial impact at scale (modelled)

> Modelled from the measured ~87% Full / ~92% Slim token reduction (geomean, 11 codebases). Assumes
> 10 tasks/dev/day, 8 turns/task, Claude Sonnet pricing. See the
> [cost calculator](https://aethvion.com/projectmapper.html) for your own numbers.

| Team size | Monthly AI coding cost (est.) | Savings with PM |
|---|---|---|
| Solo developer | $80 | $74 |
| 10-person team | $2,400 | $2,230 |
| 100-person team | $48,000 | $44,600 |
| Enterprise (1,000 devs) | $480,000 | $446,400 |

---

## What it does

1. **Static scan** — walks your project, extracts every module / class / function via AST analysis. No AI needed for this step.
2. **Knowledge graph** — stores entities + relationships (imports, calls, extends, depends_on, …) in a local JSON database.
3. **Agent queries** — 12 MCP tools that agents call instead of reading raw files:

| Tool | What it answers |
|---|---|
| `pm_context` | "What should I know before touching the auth system?" |
| `pm_impact` | "What breaks if I change `UserService`?" |
| `pm_path` | "How does `RateLimiter` connect to the payment flow?" |
| `pm_find` | "Where is `validateToken` defined?" |
| `pm_orphans` | "What code is never called?" |
| `pm_visualize` | "Show me the dependency graph for `UserService`" |
| `pm_security` | "Are there security vulnerabilities in this codebase?" |
| `pm_security_triage` | "Mark this finding as a false positive (or a confirmed bug)" |
| `pm_contribute` | "Record that I added rate limiting to endpoint X" |
| `pm_stats` | "What's already indexed in this database?" |
| `pm_delta` | "What changed since the last scan?" |
| `pm_scan` | "Scan this project directory right now" |

See the [PM Tools Reference](docs/explained/project-mapper-tools.md) for full documentation on each tool.

## Security scanning

`pm_security` is a standalone SAST-style scanner built into Project Mapper. One call checks your entire codebase — no scan dependency, no setup beyond installation.

- **140+ patterns** across OWASP Top 10 (A01–A10) in 8 languages: Python, TypeScript/JS, Java, Go, C#, PHP, Ruby, C/C++
- **Runs in 1–5 seconds** on codebases of any size
- **Route-reachability taint tracking** — ⚡ flags findings confirmed reachable from HTTP handlers
- **CWE mapping** on every finding, stable finding IDs for triage persistence, snapshot delta across scans

It's designed to work alongside `pm_context`: `pm_security` catches pattern-detectable vulnerabilities across 100% of files in seconds; `pm_context` then closes the logic-flaw and IDOR gaps that patterns can't detect. See the [security benchmark](docs/benchmarks_security/README.md) for a 3-test comparison on OWASP Juice Shop.

---

## Other access methods

### HTTP API

```bash
# Install
pip install aethvion-project-mapper

# Start server
pm-server
# pm-server --host 127.0.0.1 --port 8080 --workers 2

# Scan your project
curl -X POST http://localhost:7474/api/project-mapper/scan \
  -H "Content-Type: application/json" \
  -d '{"project_root": "/path/to/your/project", "enrich": false}'

# Query context for a task
curl -X POST http://localhost:7474/api/project-mapper/query/context \
  -H "Content-Type: application/json" \
  -d '{"q": "add rate limiting to auth endpoints", "detail_level": "medium"}'
```

Docs at **http://localhost:7474/docs**

> Developing from a repo clone instead of a pip install? Use `uvicorn server:app --reload --port 7474` from the repo root — `server.py` is a dev shim, not part of the installed package.

### Docker

```bash
docker compose up
# Server running at http://localhost:7474
```

Mount your projects:
```yaml
# docker-compose.yml — set PROJECTS_DIR to your code root
PROJECTS_DIR=/home/you/code docker compose up
```

### MCP stdio (Claude Code / Cursor / Antigravity / Codex)

> Detailed step-by-step setup guides (including Windows and Linux/macOS paths) are in [`docs/howto/`](docs/howto/README.md).

A single global config gives every session access to Project Mapper. The AI passes the project root when it calls `pm_scan`, so you don't need to specify it upfront — just tell Claude (or Cursor, etc.) to scan the current project and it handles the rest.

**Step 1 — install `uv`** (one-time, skippable if you already have it):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Already have Python? Alternatively:
pip install uv
```

`uv` manages its own Python environment — the curl/PowerShell installers above work even if Python is not installed.

**Step 2 — install Project Mapper** (one-time):

```bash
uv tool install "aethvion-project-mapper[languages]" --python 3.10
```

This installs `pm-mcp` as a global command and downloads all language parsers. Takes ~30 seconds on first run, instant on subsequent starts.

`--python 3.10` tells `uv` to fetch and pin the exact Python version Project Mapper is tested on, into an isolated environment — so it never depends on (or collides with) whatever Python is already on your system. This is what makes the install reproducible: every user runs the same interpreter and the same locked dependencies.

<a id="connect-your-agent"></a>
**Step 3 — connect your agent and make it actually use Project Mapper:**

```bash
pm-setup --claude-code --global   # Claude Code: one-time, every project, forever
pm-setup --claude-code            # or: this project only
# --cursor / --antigravity / --codex / --all also supported (project-scoped only for now)
```

This is the recommended path — see [Make your agent actually use it](#make-your-agent-actually-use-it) below for why a rules file matters as much as the MCP registration itself. `pm-setup` never overwrites existing config: it only ever adds the `project-mapper` entry to whatever's already there, and it's safe to run again later (re-running is a no-op if already configured). Run it yourself, or tell your agent to ("install and set up Aethvion Project Mapper for this project") — same command either way.

**Manual setup** — if you'd rather not run a script, or `pm-setup` doesn't cover your agent yet, add the entry below to your agent's MCP config by hand, then restart the agent:

**Claude Code** — run this (registers Project Mapper for all your projects):
```bash
claude mcp add -s user project-mapper -- pm-mcp --db workspace
```
> ⚠️ Do **not** put `mcpServers` in `~/.claude/settings.json` — Claude Code ignores MCP definitions there. It only reads them from `~/.claude.json` (which `claude mcp add` writes) or a project-level `.mcp.json`.

If you don't have the `claude` CLI on your PATH, create a `.mcp.json` in your project root instead:
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

**Cursor** — add to `~/.cursor/mcp.json`:
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

**Antigravity (Google)** — add to `~/.gemini/antigravity/mcp_config.json`:
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

**Codex CLI** — add to `~/.codex/config.json`:
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

**Alternative — no install, run directly with uvx:**
```json
{
  "command": "uvx",
  "args": ["--from", "aethvion-project-mapper[languages]", "pm-mcp", "--db", "workspace"]
}
```

> Restart the agent after editing the config.

**Optional — pin to a single project:**  
If you always work on one codebase, add `PM_PROJECT_ROOT` so the AI never needs to specify it:
```json
{
  "mcpServers": {
    "project-mapper": {
      "...",
      "env": { "PM_PROJECT_ROOT": "/absolute/path/to/your/project" }
    }
  }
}
```

> The `workspace` database is shared — scanning a new project overwrites the previous one. This is fine for single-project sessions; incremental scans on a pre-indexed repo typically finish in under 2 s.

<a id="make-your-agent-actually-use-it"></a>
### Make your agent actually use it

Registering the MCP server isn't enough on its own. By default, agents reach for their built-in grep/glob/read tools out of habit, even with Project Mapper available — nothing tells them to prefer it. The fix isn't a smarter agent; it's a rules file (`CLAUDE.md`, `.cursor/rules/`, or `AGENTS.md`) in your project root that gets loaded into context automatically at the start of every session, the same mechanism that already makes agents follow your coding conventions without you repeating them. `pm-setup` writes this for you:

```markdown
## Code navigation

Project Mapper (MCP) is available. If this project hasn't been scanned yet,
call `pm_scan` first. Then always prefer `pm_find`, `pm_context`, and
`pm_impact` over built-in grep/glob/file-read tools when locating symbols,
understanding code structure, or assessing change impact — they return
precise, ranked results at a fraction of the token cost.
```

Once that file exists, every future session in that project has the instruction loaded automatically — no need to say "use Project Mapper" ever again, for that project. By default this rules file is scoped per-project, same as the MCP registration used to be before `-s user` — so a new project needs its own copy (`pm-setup --claude-code` again, in the new project root) before the agent there knows to prefer it too.

For Claude Code specifically, `pm-setup --claude-code --global` skips that repetition: it writes the directive to `~/.claude/CLAUDE.md`, which Claude Code loads in *every* session regardless of project — matching the MCP registration, which is already user-scoped. Run it once, from anywhere, and every current and future project is covered. (Cursor/Antigravity/Codex don't have a verified global rules mechanism yet, so `--global` refuses for those rather than guessing at an unverified path.)

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PM_DATA_DIR` | `~/.aethvion/project-mapper` | Root directory for all databases |
| `PM_LOG_LEVEL` | `INFO` | Log level: DEBUG / INFO / WARNING / ERROR |
| `PM_DB_NAME` | `default` | MCP server: database name |
| `PM_DB_PATH` | *(unset)* | MCP server: explicit database path |
| `PM_PROJECT_ROOT` | *(unset)* | MCP server: default project root for pm_scan |

---

## Project structure

The package is layered: **analyzers → core → {mcp, http}**, with `config` and
`db` as shared infrastructure. Interface layers (mcp, http) are thin adapters
over the transport-agnostic `core`; `core` never imports from them.

```
project_mapper/
├── config.py             — DATA_DIR / environment config
├── analyzers/            — language extractors (one file per language)
│   ├── base.py               shared types (CodeAnalysis) + language dispatch
│   └── python.py  typescript.py  java.py  kotlin.py  go.py  rust.py
│       c.py  cpp.py  csharp.py  ruby.py  php.py  swift.py
├── core/                 — transport-agnostic engine
│   ├── scanner.py            async background scan engine
│   ├── ingestor.py           CodeAnalysis → AethvionDB entities
│   ├── query_cache.py        query-result cache (snapshot-mtime invalidation)
│   ├── cleanup.py            incremental scan maintenance
│   ├── delta.py              filesystem diff (no DB writes)
│   ├── watcher.py            auto-scan file watcher (--watch mode)
│   ├── query/               graph queries, one module per primitive
│   │   ├── _common.py            entity-map build, resolution, shared constants
│   │   └── context.py  impact.py  path.py  find.py  orphans.py  contribute.py
│   └── security/            standalone SAST scanner (OWASP Top 10, 140+ rules)
│       ├── patterns.py          the pattern catalog (data)
│       └── scanner.py           the scan engine (logic)
├── db/                   — storage
│   ├── entity_schema.py      entity data model + validation
│   ├── pm_store.py           in-memory entity store (PMEntityStore)
│   ├── name_index.py         thread-safe name → ID index
│   ├── file_manifest.py      file ↔ entity provenance tracking
│   ├── snapshot.py           single-file snapshot persistence
│   ├── db_registry.py        named database registry
│   └── utils.py              logging + atomic-write helpers
├── mcp/                  — MCP (stdio) interface
│   ├── server.py             JSON-RPC 2.0 stdio MCP server
│   └── tools/               12 tools, one module per tool (+ base.py)
└── http/                 — HTTP (FastAPI) interface
    ├── app.py                app factory + pm-server CLI entry point
    └── routes.py             FastAPI router (/api/project-mapper/*)

server.py                 — FastAPI dev entry shim (uvicorn server:app)
```

---

## Incremental scanning

Subsequent scans only process files whose SHA-256 hash has changed since the last run.
On a 10,000-file repo that's been scanned before, incremental mode typically processes
< 1 % of files — scan time drops from ~60 s to < 2 s.

```bash
# Full scan (first time or force refresh)
curl -X POST .../scan -d '{"project_root": "...", "incremental": false}'

# Incremental scan (default — only changed files)
curl -X POST .../scan -d '{"project_root": "..."}'
```

---

## License

**Open-source core:** [GNU AGPL v3](LICENSE)  
Free to use, modify, and self-host. Network use requires open-sourcing your modifications.

**Commercial license:** [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md)  
Available for teams that need a proprietary license, SLA, or integration support.

---

## Contributing

Pull requests are welcome. By submitting a PR you agree to the
[Contributor License Agreement](LICENSE) (§2).

```bash
git clone https://github.com/Aethvion/Aethvion-ProjectMapper
cd Aethvion-ProjectMapper
pip install -e ".[dev]"
pytest
```

---

## Support development

If Project Mapper saves you tokens, time, or money — consider sponsoring. It keeps the project maintained and new languages / features coming.

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-30363D?logo=githubsponsors&logoColor=EA4AAA)](https://github.com/sponsors/Aethvion)

See the full [sponsors list](https://github.com/Aethvion/.github/blob/main/SPONSORS.md).

*Built with care by the Aethvion team.*
