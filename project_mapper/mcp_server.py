"""
project_mapper/mcp_server.py
Minimal MCP (Model Context Protocol) stdio server for ProjectMapper.

Protocol: JSON-RPC 2.0, newline-delimited, over stdin/stdout.
No external dependencies beyond Python stdlib + fastapi/uvicorn (for the HTTP server).

Recommended install
-------------------
    uv tool install "aethvion-project-mapper[languages]"
    # installs pm-mcp as a global command — no Python or repo clone required

Usage (after uv tool install)
------------------------------
    pm-mcp --db workspace

Usage (direct, for development)
--------------------------------
    python -m project_mapper.mcp_server --db my_project
    python -m project_mapper.mcp_server --db-path /data/pm/my_project
    python -m project_mapper.mcp_server --db my_project --project-root /path/to/project

Watch mode (auto-scan)
---------------------
    # Poll every 10 s; rescan when changes detected (requires --project-root)
    pm-mcp --db workspace --project-root /path/to/project --watch
    pm-mcp --db workspace --project-root /path/to/project --watch --watch-interval 30

Environment variable equivalents (CLI overrides env):
    PM_DB_NAME        — same as --db
    PM_DB_PATH        — same as --db-path
    PM_PROJECT_ROOT   — same as --project-root
    PM_DATA_DIR       — root directory for all databases (default: ~/.aethvion_pm/data)
    PM_WATCH          — "1" / "true" / "yes" to enable watch mode
    PM_WATCH_INTERVAL — poll interval in seconds (default: 10)

Claude Code config  (~/.claude/settings.json  or  .claude/settings.json)
------------------------------------------------------------------------
    {
      "mcpServers": {
        "project-mapper": {
          "type": "stdio",
          "command": "pm-mcp",
          "args": ["--db", "workspace"]
        }
      }
    }

Cursor config  (~/.cursor/mcp.json)
------------------------------------
    {
      "mcpServers": {
        "project-mapper": {
          "command": "pm-mcp",
          "args": ["--db", "workspace"]
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# JSON-RPC constants
# ---------------------------------------------------------------------------

PARSE_ERROR      = -32700
INVALID_REQUEST  = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS   = -32602
INTERNAL_ERROR   = -32603

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME      = "project-mapper"
SERVER_VERSION   = "1.7.5"

# Injected into the client agent's context at session start (MCP `instructions`
# field of the initialize response). Keep this short — it costs context tokens
# in every session. Content targets the misunderstandings agents actually hit.
SERVER_INSTRUCTIONS = """\
ProjectMapper builds a knowledge graph of a codebase via static AST analysis \
(Python, JS/TS, Go, Rust, C, C++, C#, Java, Kotlin, Ruby, PHP, Swift). \
Entities are modules, classes, and top-level functions, wired with calls / \
imports / extends / contains relations.

Recommended workflow:
1. pm_stats to check index state; pm_delta to preview changes since last scan.
2. pm_scan to index. Use background=true for projects with 500+ files, then \
poll pm_stats. Incremental (default) only re-processes changed files.
3. pm_context slim=true to locate relevant files cheaply (name + file:line); \
use slim=false when you need docstrings/summaries instead.
4. pm_find for one symbol's definition, callers, and callees. pm_impact for \
blast radius before a change. pm_path to connect two entities.
5. pm_contribute to save your findings (properties, relations, rationale) back \
into the graph for future sessions.

Important notes:
- One database per project root. Scanning a different root into the same \
database retires the previous project's entities.
- Class METHODS are not separate entities. You can search by class-qualified \
name (pm_find "DBImpl::Write" or pm_find "ZodObject.parse") and pm_find \
routes you to the parent class automatically. The class entry lists all \
methods and which method drives each relation ("via").
- pm_orphans is a heuristic for dead-code candidates: entities with no inbound \
relations. Verify with a text search before deleting anything.
- Relations come from static analysis: dynamic dispatch, reflection, and \
string-based references are not captured.\
"""


# ---------------------------------------------------------------------------
# MCPServer
# ---------------------------------------------------------------------------

class MCPServer:
    """
    Minimal MCP stdio server.

    Reads newline-delimited JSON-RPC messages from stdin, writes responses
    to stdout.  All log output goes to stderr (never stdout).
    """

    def __init__(
        self,
        db_root:       Path,
        db_name:       str,
        project_root:  Optional[str] = None,
        watch:         bool = False,
        watch_interval: float = 10.0,
    ) -> None:
        self._db_root       = db_root
        self._db_name       = db_name
        self._project_root  = project_root
        self._watch         = watch
        self._watch_interval = watch_interval
        self._scan_lock     = threading.Lock()
        self._ctx           = None   # built lazily on first tool call

        # stdout must be unbuffered text so responses are flushed immediately
        self._out = sys.stdout

    # ------------------------------------------------------------------
    # DB context (lazy init avoids import overhead at startup)
    # ------------------------------------------------------------------

    def _get_ctx(self):
        if self._ctx is not None:
            return self._ctx

        from .db.pm_store import PMEntityStore, PMNameIndex
        from .db.file_manifest import FileManifest
        from .db import snapshot as _snap
        from .mcp_tools import MCPContext

        self._db_root.mkdir(parents=True, exist_ok=True)
        name_index = PMNameIndex(index_path=self._db_root / "name_index.json")
        if _snap.snapshot_path(self._db_root).exists():
            writer = PMEntityStore.from_snapshot(self._db_root, name_index)
        else:
            writer = PMEntityStore(self._db_root, name_index)
        manifest = FileManifest(self._db_root)

        self._ctx = MCPContext(
            db_root=self._db_root,
            db_name=self._db_name,
            writer=writer,
            index=name_index,
            file_manifest=manifest,
            project_root=self._project_root,
            scan_lock=self._scan_lock,
        )
        return self._ctx

    # ------------------------------------------------------------------
    # Protocol helpers
    # ------------------------------------------------------------------

    def _send(self, payload: dict[str, Any]) -> None:
        """Write one JSON-RPC message to stdout and flush immediately."""
        line = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        self._out.write(line + "\n")
        self._out.flush()

    def _ok(self, req_id: Any, result: Any) -> None:
        self._send({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _err(self, req_id: Any, code: int, message: str, data: Any = None) -> None:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        self._send({"jsonrpc": "2.0", "id": req_id, "error": err})

    def _log(self, *args: Any) -> None:
        """Print to stderr — never stdout."""
        print(*args, file=sys.stderr, flush=True)

    # ------------------------------------------------------------------
    # Method handlers
    # ------------------------------------------------------------------

    def _handle_initialize(self, req_id: Any, params: dict) -> None:
        self._ok(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},   # we expose tools
            },
            "serverInfo": {
                "name":    SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "instructions": SERVER_INSTRUCTIONS,
        })

    def _handle_tools_list(self, req_id: Any, params: dict) -> None:
        from .mcp_tools import TOOL_SCHEMAS
        self._ok(req_id, {"tools": TOOL_SCHEMAS})

    def _handle_tools_call(self, req_id: Any, params: dict) -> None:
        from .mcp_tools import HANDLERS

        name      = params.get("name", "")
        arguments = params.get("arguments", {}) or {}

        handler = HANDLERS.get(name)
        if not handler:
            self._err(req_id, METHOD_NOT_FOUND, f"Unknown tool: {name!r}")
            return

        try:
            ctx    = self._get_ctx()
            result = handler(arguments, ctx)
            self._ok(req_id, {
                "content": [{"type": "text", "text": result}],
                "isError": False,
            })
        except ValueError as exc:
            # Invalid arguments — return as tool error (not protocol error)
            self._ok(req_id, {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            })
        except Exception as exc:
            # Unexpected error — also return as tool error with trace
            tb = traceback.format_exc()
            self._log(f"[MCP] Tool {name!r} failed:\n{tb}")
            self._ok(req_id, {
                "content": [{"type": "text", "text": f"Internal error: {exc}"}],
                "isError": True,
            })

    def _handle_ping(self, req_id: Any, params: dict) -> None:
        self._ok(req_id, {})

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, msg: dict[str, Any]) -> None:
        req_id  = msg.get("id")        # None for notifications
        method  = msg.get("method", "")
        params  = msg.get("params") or {}

        # Notifications have no id — don't send a response
        if req_id is None:
            if method == "notifications/initialized":
                self._log("[MCP] Client initialized.")
            return

        if method == "initialize":
            self._handle_initialize(req_id, params)
        elif method == "tools/list":
            self._handle_tools_list(req_id, params)
        elif method == "tools/call":
            self._handle_tools_call(req_id, params)
        elif method in ("ping", ""):
            self._handle_ping(req_id, params)
        else:
            self._err(req_id, METHOD_NOT_FOUND, f"Method not found: {method!r}")

    # ------------------------------------------------------------------
    # Main read loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Read JSON-RPC messages from stdin line by line until EOF.
        On Windows, re-wrap stdin/stdout/stderr in UTF-8 before any I/O so
        that the startup log and all subsequent output survive narrow codepages
        (cp1252 etc.).  Must come before self._log() to avoid UnicodeEncodeError
        killing the subprocess before the client receives its first byte.
        """
        # UTF-8 stdin/stdout/stderr on Windows — must come first, before any
        # self._log() call.  The startup message may contain em-dashes or other
        # non-ASCII that crash cp1252 consoles, producing a silent client EOF.
        if sys.platform == "win32":
            import io
            sys.stdin  = io.TextIOWrapper(
                sys.stdin.buffer,  encoding="utf-8", errors="replace", newline="\n"
            )
            self._out = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace"
            )

        self._log(
            f"[ProjectMapper MCP] Starting — db={self._db_name!r}  "
            f"db_root={self._db_root}  project={self._project_root or '(unset)'}"
        )

        if self._watch:
            if not self._project_root:
                self._log(
                    "[ProjectMapper MCP] --watch ignored: --project-root not set."
                )
            else:
                from .watcher import AutoScanner
                ctx = self._get_ctx()   # initialise eagerly so watcher shares the same objects
                scanner = AutoScanner(
                    project_root=self._project_root,
                    db_root=self._db_root,
                    db_name=self._db_name,
                    writer=ctx.writer,
                    index=ctx.index,
                    file_manifest=ctx.file_manifest,
                    scan_lock=self._scan_lock,
                    poll_interval=self._watch_interval,
                )
                scanner.start()
                ctx.auto_scanner = scanner

        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            try:
                msg = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                self._log(f"[MCP] JSON parse error: {exc}")
                self._err(None, PARSE_ERROR, f"Parse error: {exc}")
                continue

            if not isinstance(msg, dict):
                self._err(None, INVALID_REQUEST, "Request must be a JSON object")
                continue

            try:
                self._dispatch(msg)
            except Exception as exc:
                req_id = msg.get("id")
                tb = traceback.format_exc()
                self._log(f"[MCP] Dispatch error:\n{tb}")
                if req_id is not None:
                    self._err(req_id, INTERNAL_ERROR, f"Internal error: {exc}")

        self._log("[ProjectMapper MCP] Stdin closed — shutting down.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _resolve_db_root(db_name: str, db_path: Optional[str]) -> tuple[Path, str]:
    """Return (db_root, db_name) from CLI args / env vars."""
    if db_path:
        return Path(db_path), db_name or Path(db_path).name

    if db_name:
        try:
            from .db.db_registry import resolve_db_root
            return resolve_db_root(db_name), db_name
        except Exception:
            pass
        # Fallback: under DATA_DIR
        from .config import DATA_DIR
        return DATA_DIR / db_name, db_name

    # Nothing specified — use "default"
    try:
        from .db.db_registry import resolve_db_root
        return resolve_db_root("default"), "default"
    except Exception:
        from .config import DATA_DIR
        return DATA_DIR / "default", "default"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m project_mapper.mcp_server",
        description="ProjectMapper MCP stdio server",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("PM_DB_NAME", ""),
        metavar="NAME",
        help="Database name (default: 'default')",
    )
    parser.add_argument(
        "--db-path",
        default=os.environ.get("PM_DB_PATH", ""),
        metavar="PATH",
        help="Absolute path to database root directory (overrides --db)",
    )
    parser.add_argument(
        "--project-root",
        default=os.environ.get("PM_PROJECT_ROOT", ""),
        metavar="PATH",
        help="Default project root for pm_scan and pm_delta",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        default=os.environ.get("PM_WATCH", "").lower() in ("1", "true", "yes"),
        help=(
            "Enable auto-scan: poll --project-root for file changes and run "
            "incremental scans automatically (requires --project-root)"
        ),
    )
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=float(os.environ.get("PM_WATCH_INTERVAL", "10")),
        metavar="SECONDS",
        help="Seconds between file-change polls when --watch is active (default: 10)",
    )
    args = parser.parse_args()

    db_root, db_name = _resolve_db_root(
        args.db or "",
        args.db_path or None,
    )
    project_root = args.project_root or None

    server = MCPServer(
        db_root=db_root,
        db_name=db_name,
        project_root=project_root,
        watch=args.watch,
        watch_interval=args.watch_interval,
    )
    server.run()


if __name__ == "__main__":
    main()
