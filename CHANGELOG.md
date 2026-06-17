# Changelog

All notable changes to Aethvion Project Mapper are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [2.1.0] — 2026-06-17

### Changed
- **Data directory moved to `~/.aethvion/project-mapper`** (was `~/.aethvion_pm/data`).
  Aethvion products now share one vendor directory with a sub-directory per
  product, matching the standard `~/.config` / `~/.aws` convention and avoiding a
  sprawl of `~/.aethvion_*` folders as more products ship. `PM_DATA_DIR` still
  overrides the default. No automatic migration of the old location — re-run a
  scan to repopulate (scans are fast).

---

## [2.0.0] — 2026-06-17

### Changed — breaking / structural
- **Package restructured into subpackages.** The flat module layout is replaced
  by a layered hierarchy: `analyzers/` → `core/` → `{mcp/, http/}`.
  - Language extractors moved to `project_mapper/analyzers/` (one file per language).
  - Engine modules moved to `project_mapper/core/` (`scanner`, `ingestor`,
    `query_cache`, `cleanup`, `delta`, `watcher`).
  - Query primitives split into `project_mapper/core/query/` (one module per
    query: `context`, `impact`, `path`, `find`, `orphans`, `contribute`).
  - Security scanner split into `project_mapper/core/security/` (`patterns`,
    `scanner`, `scan`).
  - MCP tools split into `project_mapper/mcp/tools/` (one module per tool).
  - HTTP layer moved to `project_mapper/http/` (`app`, `routes`).
- **`pm-setup` command removed.** Replaced by per-agent manual setup guides in
  `docs/howto/`. The one-liner `claude mcp add` command is the recommended
  install path for Claude Code users.
- **`EntityWriter` deleted.** Superseded by `PMEntityStore` since v1.5.

### Added
- **`pm_visualize` MCP tool** — generates Mermaid or DOT subgraph diagrams
  centred on a named entity (depth, direction, and relation-kind filters).
- **HTTP endpoints for `pm_find`, `pm_orphans`, `pm_visualize`** — the HTTP
  API now covers the full MCP tool surface.
- **HTTP endpoints for `pm_security` and `pm_security_triage`** — security
  scanning and triage accessible over HTTP in addition to MCP.
- **`pm_scan` background mode** — pass `background=true` to return immediately
  and poll `pm_stats` for progress; avoids MCP client timeouts on large repos.
- **Test suite** — 87 tests across four files covering the DB layer, MCP tool
  handlers, JSON-RPC protocol, and security scanner.

### Improved
- **Security scanner patterns** — 140+ rules after adding PEM private-key
  detection, TLS-bypass patterns, and broadened secret detection.
- **Agent output compression** — rule references deduplicated in `pm_security`
  output; significantly reduces token cost for large codebases.
- **Benchmarks re-measured** — all 11 benchmark projects updated with
  tiktoken-counted token figures measured from the actual MCP handler output.
  Security benchmark re-run on OWASP Juice Shop (3-test comparison).

### Fixed
- Two split-boundary regressions introduced during the package restructure
  (committed in `b67898b`).
- Duplicate `php_header_injection` entry removed from the security pattern
  catalog.

---

## [1.9.0] — 2025-06

### Added
- `pm_visualize` MCP tool with Mermaid/DOT output and documented usage
  examples.

### Improved
- `pm_security` output compressed via rule reference deduplication.
- `SERVER_INSTRUCTIONS` updated to document `pm_visualize` and
  `pm_security` workflow.

---

## [1.8.0] — 2025-05

### Added
- `pm_security_triage` — triage lifecycle (false positive, verified
  vulnerability, resolved, unreviewed) with stable 8-char finding IDs and
  snapshot delta across scans.
- Tools reference (`docs/explained/project-mapper-tools.md`), explained/ and
  howto/ guide directories covering Claude Code, Cursor, Antigravity, Codex.
- Security benchmark — 3-test audit on OWASP Juice Shop comparing manual,
  `pm_security`, and `pm_security + pm_context` approaches.
- 11-codebase benchmark suite (Python, Java/Kotlin, C#, PHP, C, Go, Ruby,
  TypeScript, Rust, C++, Swift).

### Improved
- `pm_security` patterns expanded to 140+ rules (OWASP Top 10, 8 languages)
  with innerHTML/outerHTML lookahead fix and 4 new patterns.
- Route-reachability taint tracking added to `pm_security`.

---

## [1.7.0] — 2025-04

### Added
- `pm_security` MCP tool — standalone SAST scanner (OWASP Top 10, 8 languages,
  no prior scan required).
- CWE mapping on every security finding.

---

## [1.6.0] — 2025-03

### Added
- `pm_delta` MCP tool — show file-system changes since the last scan without
  writing to the database.
- `pm_orphans` MCP tool — dead-code candidates (entities with no inbound
  relations).
- Auto-scan watch mode (`--watch` / `PM_WATCH`) — polls the project root and
  runs incremental scans when changes are detected.

---

## [1.5.0] — 2025-02

### Added
- `PMEntityStore` — in-memory entity store with single-snapshot persistence,
  replacing per-entity JSON file writes. Eliminates O(N) disk I/O during scans.
- `pm_contribute` MCP tool — write agent-discovered knowledge (properties,
  relations, rationale) back into the graph.
- Incremental scanning with SHA-256 file-hash change detection.
- Docker support (`docker-compose.yml`).

---

## [1.0.0] — 2025-01

Initial public release.

- Static AST analysis for Python, TypeScript/JavaScript, Java, Kotlin, Go,
  Rust, C, C++, C#, Ruby, PHP, Swift (12 languages at launch).
- Knowledge graph with module / class / function entities and calls / imports /
  extends / depends_on relations.
- 9 MCP tools: `pm_scan`, `pm_stats`, `pm_context`, `pm_impact`, `pm_path`,
  `pm_find`, `pm_visualize` (stub), `pm_contribute` (stub).
- FastAPI HTTP API with background scan, incremental mode, and `/docs`.
- Smithery.yaml for one-click discovery on Smithery.ai.
