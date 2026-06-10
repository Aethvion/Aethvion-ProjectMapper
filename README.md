# Aethvion Project Mapper

> **Static code analysis + knowledge-graph for AI coding agents.**  
> Give your AI the map it needs — before it starts writing code.

---

## Why it exists

AI coding agents (Claude Code, Cursor, Copilot, etc.) read your entire codebase on every task.
That's expensive, slow, and often inaccurate because context windows fill up before the agent sees the relevant files.

Project Mapper scans your codebase once, builds a structured knowledge graph of every module, class, function, and their relationships, and lets agents query *only what they need* — in milliseconds, at a fraction of the token cost.

New here? The [`docs/explained/`](docs/explained/) folder covers [what Project Mapper is](docs/explained/what-is-project-mapper.md), [what MCP tools are](docs/explained/what-is-mcp.md), and [exactly what PM reads and stores on your machine](docs/explained/what-does-pm-access.md).

---

## Benchmark numbers

Measured across [10 real-world codebases](docs/benchmarks/README.md) — Python, Java/Kotlin, C#, PHP, C, Ruby, TypeScript/JS, Rust, C++, Swift — ranging from 57 to 11,083 files.

### Token reduction (geometric mean across 10 benchmarks)

| | Normal (Grep + Read) | PM Full | PM Slim |
|---|---|---|---|
| Tokens per query | baseline | **~6× less** | **~13× less** |
| At 100,000 input tokens | 100,000 | **~17,000** | **~7,700** |

PM Slim returns name + file path + line number only — enough for navigation and refactoring tasks. PM Full returns complete entity context. See the [benchmark suite](docs/benchmarks/README.md) for per-codebase numbers.

### Query latency (measured)

| Query | Latency |
|---|---|
| Context query | 10–100 ms (warm cache) |
| Impact query | 10–60 ms |

### Session startup — entity map load (measured)

The entity map is stored as a single snapshot file built at the end of each scan.

| Codebase size | Load time |
|---|---|
| ~400 entities | < 50 ms |
| ~12,000 entities | ~145 ms |
| ~33,000 entities | ~300 ms |

### Financial impact at scale (modelled)

> Modelled from the measured ~6× Full / ~13× Slim token reduction (geomean, 10 codebases). Assumes
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
3. **Agent queries** — 7 MCP tools that agents call instead of reading raw files:

| Tool | What it answers |
|---|---|
| `pm_context` | "What should I know before touching the auth system?" |
| `pm_impact` | "What breaks if I change `UserService`?" |
| `pm_path` | "How does `RateLimiter` connect to the payment flow?" |
| `pm_contribute` | "Record that I added rate limiting to endpoint X" |
| `pm_stats` | "What's already indexed in this database?" |
| `pm_delta` | "What changed since the last scan?" |
| `pm_scan` | "Scan this project directory right now" |

---

## Quick start

### HTTP API

```bash
# Install
pip install aethvion-project-mapper

# Start server
uvicorn server:app --port 7474

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

> Detailed step-by-step setup guides (including Windows and Linux/macOS paths) are in [`docs/howto/`](docs/howto/).

A single global config gives every session access to Project Mapper. The AI passes the project root when it calls `pm_scan`, so you don't need to specify it upfront — just tell Claude (or Cursor, etc.) to scan the current project and it handles the rest.

**Claude Code** — add to `~/.claude/settings.json`:
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
      "cwd": "C:\\absolute\\path\\to\\Aethvion-ProjectMapper"
    }
  }
}
```

**Cursor** — add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "project-mapper": {
      "command": "python",
      "args": ["-m", "project_mapper.mcp_server", "--db", "workspace"],
      "cwd": "/absolute/path/to/Aethvion-ProjectMapper"
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
      "command": "python",
      "args": [
        "-m", "project_mapper.mcp_server",
        "--db", "workspace"
      ],
      "cwd": "C:/absolute/path/to/Aethvion-ProjectMapper"
    }
  }
}
```

> All three agents use the same `mcpServers` format — only the config file location differs. Restart the agent after editing the config.

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

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PM_DATA_DIR` | `~/.aethvion_pm/data` | Root directory for all databases |
| `PM_LOG_LEVEL` | `INFO` | Log level: DEBUG / INFO / WARNING / ERROR |
| `PM_DB_NAME` | `default` | MCP server: database name |
| `PM_DB_PATH` | *(unset)* | MCP server: explicit database path |
| `PM_PROJECT_ROOT` | *(unset)* | MCP server: default project root for pm_scan |

---

## Project structure

```
project_mapper/
├── config.py          — DATA_DIR config
├── routes.py          — FastAPI router (/api/project-mapper/*)
├── scanner.py         — Async background scan engine
├── ingestor.py        — CodeAnalysis → AethvionDB entities
├── code_analyzer.py   — Python AST extractor
├── query.py           — Impact / context / shortest-path algorithms
├── cleanup.py         — Incremental scan maintenance
├── delta.py           — Filesystem diff (no DB writes)
├── mcp_tools.py       — 7 MCP tool schemas + handlers
├── mcp_server.py      — JSON-RPC 2.0 stdio MCP server
└── db/
    ├── entity_schema.py   — Entity data model + validation
    ├── entity_writer.py   — Create / update / delete entities
    ├── name_index.py      — Thread-safe name → ID index
    ├── file_manifest.py   — File ↔ entity provenance tracking
    ├── snapshot.py        — Fast-load snapshot cache
    └── db_registry.py     — Named database registry
server.py              — FastAPI app entry point
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

*Built with care by the Aethvion team.*
