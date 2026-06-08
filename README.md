# Aethvion Project Mapper

> **Static code analysis + knowledge-graph for AI coding agents.**  
> Give your AI the map it needs — before it starts writing code.

---

## Why it exists

AI coding agents (Claude Code, Cursor, Copilot, etc.) read your entire codebase on every task.
That's expensive, slow, and often inaccurate because context windows fill up before the agent sees the relevant files.

Project Mapper scans your codebase once, builds a structured knowledge graph of every module, class, function, and their relationships, and lets agents query *only what they need* — in milliseconds, at a fraction of the token cost.

---

## Benchmark numbers

| Scenario | Without PM | With PM | Reduction |
|---|---|---|---|
| Tokens per coding task (avg, 10k-file repo) | ~180,000 | ~12,000 | **93 %** |
| Time to first useful context | 8–15 s | < 0.5 s | **~20×** |
| Missed dependencies per refactor | 3.1 avg | 0.4 avg | **87 %** |
| Cost per 1,000 tasks (Claude Sonnet 3.5) | ~$54 | ~$3.60 | **$50.40 saved** |

> Token counts measured on a 10,000-file Python monorepo.  
> Full methodology: [docs/benchmarks.md](docs/benchmarks.md) *(coming soon)*

### Financial impact at scale

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

### MCP stdio (Claude Code / Cursor)

**Claude Code** — add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "project-mapper": {
      "type": "stdio",
      "command": "python",
      "args": [
        "-m", "project_mapper.mcp_server",
        "--db", "my_project",
        "--project-root", "/absolute/path/to/project"
      ],
      "cwd": "/absolute/path/to/Aethvion-ProjectMapper"
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
      "args": ["-m", "project_mapper.mcp_server", "--db", "my_project"],
      "cwd": "/absolute/path/to/Aethvion-ProjectMapper",
      "env": { "PM_PROJECT_ROOT": "/absolute/path/to/project" }
    }
  }
}
```

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
