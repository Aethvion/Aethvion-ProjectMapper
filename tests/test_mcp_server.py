"""
Tests for the MCP server JSON-RPC 2.0 protocol layer.

Exercises _dispatch() directly (injecting a StringIO output) rather than the
full stdin loop — fast and deterministic while still covering all the protocol
paths the client sees.
"""

import io
import json

from project_mapper.mcp.server import (
    METHOD_NOT_FOUND,
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    MCPServer,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_server(tmp_db, ctx) -> MCPServer:
    srv = MCPServer(db_root=tmp_db, db_name="test")
    srv._out = io.StringIO()
    srv._ctx = ctx  # inject pre-built context; skips lazy init
    return srv


def _last(srv: MCPServer) -> dict:
    """Parse the last JSON-RPC line written to the server's output buffer."""
    lines = [line for line in srv._out.getvalue().strip().splitlines() if line.strip()]
    assert lines, "Server wrote no output"
    return json.loads(lines[-1])


def _dispatch(srv: MCPServer, msg: dict) -> dict:
    srv._dispatch(msg)
    return _last(srv)


# ── Version / constants ───────────────────────────────────────────────────────


def test_server_version_is_2_1_0():
    assert SERVER_VERSION == "2.1.0"


def test_server_name():
    assert SERVER_NAME == "project-mapper"


def test_protocol_version():
    assert PROTOCOL_VERSION == "2024-11-05"


# ── initialize ────────────────────────────────────────────────────────────────


class TestInitialize:
    def test_returns_protocol_version(self, tmp_db, ctx):
        srv = _make_server(tmp_db, ctx)
        resp = _dispatch(srv, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert resp["result"]["protocolVersion"] == PROTOCOL_VERSION

    def test_returns_server_name_and_version(self, tmp_db, ctx):
        srv = _make_server(tmp_db, ctx)
        resp = _dispatch(srv, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        info = resp["result"]["serverInfo"]
        assert info["name"] == SERVER_NAME
        assert info["version"] == SERVER_VERSION

    def test_capabilities_includes_tools(self, tmp_db, ctx):
        srv = _make_server(tmp_db, ctx)
        resp = _dispatch(srv, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert "tools" in resp["result"]["capabilities"]

    def test_instructions_field_present(self, tmp_db, ctx):
        srv = _make_server(tmp_db, ctx)
        resp = _dispatch(srv, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert "instructions" in resp["result"]
        assert len(resp["result"]["instructions"]) > 50


# ── tools/list ────────────────────────────────────────────────────────────────


class TestToolsList:
    def test_returns_twelve_tools(self, tmp_db, ctx):
        srv = _make_server(tmp_db, ctx)
        resp = _dispatch(srv, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = resp["result"]["tools"]
        assert len(tools) == 12

    def test_all_tools_have_name(self, tmp_db, ctx):
        srv = _make_server(tmp_db, ctx)
        resp = _dispatch(srv, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        for tool in resp["result"]["tools"]:
            assert "name" in tool
            assert tool["name"].startswith("pm_")


# ── tools/call ────────────────────────────────────────────────────────────────


class TestToolsCall:
    def test_known_tool_returns_text(self, tmp_db, ctx):
        srv = _make_server(tmp_db, ctx)
        resp = _dispatch(
            srv,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "pm_stats", "arguments": {}},
            },
        )
        content = resp["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert len(content[0]["text"]) > 0
        assert resp["result"]["isError"] is False

    def test_unknown_tool_returns_error(self, tmp_db, ctx):
        srv = _make_server(tmp_db, ctx)
        resp = _dispatch(
            srv,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "pm_nonexistent", "arguments": {}},
            },
        )
        assert "error" in resp
        assert resp["error"]["code"] == METHOD_NOT_FOUND

    def test_invalid_args_returns_tool_error(self, tmp_db, ctx):
        srv = _make_server(tmp_db, ctx)
        # pm_find with no 'name' argument should raise ValueError → isError=True
        resp = _dispatch(
            srv,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "pm_find", "arguments": {}},
            },
        )
        assert resp["result"]["isError"] is True
        assert "error" in resp["result"]["content"][0]["text"].lower()


# ── ping ──────────────────────────────────────────────────────────────────────


def test_ping_returns_empty_result(tmp_db, ctx):
    srv = _make_server(tmp_db, ctx)
    resp = _dispatch(srv, {"jsonrpc": "2.0", "id": 9, "method": "ping", "params": {}})
    assert resp["result"] == {}


# ── unknown method ────────────────────────────────────────────────────────────


def test_unknown_method_returns_method_not_found(tmp_db, ctx):
    srv = _make_server(tmp_db, ctx)
    resp = _dispatch(srv, {"jsonrpc": "2.0", "id": 10, "method": "no_such_method", "params": {}})
    assert "error" in resp
    assert resp["error"]["code"] == METHOD_NOT_FOUND


# ── notifications (no response expected) ─────────────────────────────────────


def test_notification_produces_no_output(tmp_db, ctx):
    srv = _make_server(tmp_db, ctx)
    # Notifications have no "id" field — server must not write a response
    before = srv._out.getvalue()
    srv._dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"})
    after = srv._out.getvalue()
    assert before == after, "Server must not respond to notifications"
