"""
Tests for the 12 MCP tool handlers.

Each test calls a handler function directly with a minimal MCPContext and
checks that the output string is reasonable — not that it contains specific
formatting, but that it doesn't crash and carries the expected semantics
(empty-graph message, entity names, error text, etc.).
"""
import pytest

from project_mapper.mcp.tools import HANDLERS, TOOL_SCHEMAS

# ── Schema / registry smoke tests ────────────────────────────────────────────

class TestToolRegistry:
    def test_twelve_tools_exported(self):
        assert len(TOOL_SCHEMAS) == 12

    def test_twelve_handlers_registered(self):
        assert len(HANDLERS) == 12

    def test_all_expected_names_present(self):
        expected = {
            "pm_context", "pm_impact", "pm_path", "pm_contribute",
            "pm_stats", "pm_delta", "pm_find", "pm_orphans",
            "pm_visualize", "pm_scan", "pm_security", "pm_security_triage",
        }
        assert set(HANDLERS.keys()) == expected

    def test_schemas_have_required_fields(self):
        for schema in TOOL_SCHEMAS:
            assert "name" in schema, f"Missing 'name' in schema: {schema}"
            assert "description" in schema, f"Missing 'description' for {schema.get('name')}"
            assert "inputSchema" in schema, f"Missing 'inputSchema' for {schema.get('name')}"

    def test_schema_names_match_handlers(self):
        schema_names = {s["name"] for s in TOOL_SCHEMAS}
        handler_names = set(HANDLERS.keys())
        assert schema_names == handler_names


# ── pm_stats ──────────────────────────────────────────────────────────────────

class TestPmStats:
    def test_empty_db_does_not_crash(self, empty_ctx):
        from project_mapper.mcp.tools.stats import handle_pm_stats
        result = handle_pm_stats({}, empty_ctx)
        assert isinstance(result, str)
        assert "Database" in result
        assert "test" in result          # db_name

    def test_populated_db_reports_entities(self, ctx):
        from project_mapper.mcp.tools.stats import handle_pm_stats
        result = handle_pm_stats({}, ctx)
        assert "Entities:" in result
        assert "3 active" in result

    def test_auto_scan_off_reported(self, ctx):
        from project_mapper.mcp.tools.stats import handle_pm_stats
        result = handle_pm_stats({}, ctx)
        assert "Auto-scan: off" in result


# ── pm_find ───────────────────────────────────────────────────────────────────

class TestPmFind:
    def test_empty_graph_returns_guidance(self, empty_ctx):
        from project_mapper.mcp.tools.find import handle_pm_find
        result = handle_pm_find({"name": "get_user"}, empty_ctx)
        assert "empty" in result.lower() or "pm_scan" in result.lower()

    def test_find_known_entity(self, ctx):
        from project_mapper.mcp.tools.find import handle_pm_find
        result = handle_pm_find({"name": "get_user"}, ctx)
        assert "get_user" in result
        assert "function" in result.lower()
        assert "auth/user.py" in result

    def test_find_missing_entity(self, ctx):
        from project_mapper.mcp.tools.find import handle_pm_find
        result = handle_pm_find({"name": "NonExistentXYZ"}, ctx)
        assert "not found" in result.lower()

    def test_find_requires_name(self, ctx):
        from project_mapper.mcp.tools.find import handle_pm_find
        with pytest.raises(ValueError, match="'name' is required"):
            handle_pm_find({}, ctx)

    def test_find_partial_match(self, ctx):
        from project_mapper.mcp.tools.find import handle_pm_find
        result = handle_pm_find({"name": "user"}, ctx)
        assert "user" in result.lower()

    def test_find_shows_callers(self, ctx):
        from project_mapper.mcp.tools.find import handle_pm_find
        # get_user is called by UserService
        result = handle_pm_find({"name": "get_user"}, ctx)
        assert "Callers" in result
        assert "UserService" in result


# ── pm_context ────────────────────────────────────────────────────────────────

class TestPmContext:
    def test_empty_graph_does_not_crash(self, empty_ctx):
        from project_mapper.mcp.tools.context import handle_pm_context
        result = handle_pm_context({"query": "authentication"}, empty_ctx)
        assert isinstance(result, str)

    def test_returns_relevant_entities(self, ctx):
        from project_mapper.mcp.tools.context import handle_pm_context
        result = handle_pm_context({"query": "user authentication service"}, ctx)
        assert isinstance(result, str)
        # At least one of our seeded entities should appear
        assert any(name in result for name in ("get_user", "UserService", "auth_module"))

    def test_slim_mode_returns_string(self, ctx):
        from project_mapper.mcp.tools.context import handle_pm_context
        result = handle_pm_context({"query": "auth", "slim": True}, ctx)
        assert isinstance(result, str)

    def test_query_is_required(self, ctx):
        from project_mapper.mcp.tools.context import handle_pm_context
        with pytest.raises(ValueError):
            handle_pm_context({}, ctx)


# ── pm_impact ─────────────────────────────────────────────────────────────────

class TestPmImpact:
    def test_empty_graph_returns_message(self, empty_ctx):
        from project_mapper.mcp.tools.impact import handle_pm_impact
        result = handle_pm_impact({"entity": "get_user"}, empty_ctx)
        assert isinstance(result, str)

    def test_impact_on_known_entity(self, ctx):
        from project_mapper.mcp.tools.impact import handle_pm_impact
        # get_user is called by UserService, so UserService should appear in impact
        result = handle_pm_impact({"entity": "get_user"}, ctx)
        assert isinstance(result, str)
        assert "get_user" in result

    def test_entity_is_required(self, ctx):
        from project_mapper.mcp.tools.impact import handle_pm_impact
        with pytest.raises(ValueError):
            handle_pm_impact({}, ctx)


# ── pm_orphans ────────────────────────────────────────────────────────────────

class TestPmOrphans:
    def test_empty_graph_returns_string(self, empty_ctx):
        from project_mapper.mcp.tools.orphans import handle_pm_orphans
        result = handle_pm_orphans({}, empty_ctx)
        assert isinstance(result, str)

    def test_finds_orphan_module(self, ctx):
        from project_mapper.mcp.tools.orphans import handle_pm_orphans
        # auth_module has no inbound relations → it's an orphan candidate
        result = handle_pm_orphans({}, ctx)
        assert isinstance(result, str)
        # auth_module is a module, which may be excluded by default — just check no crash


# ── pm_delta ──────────────────────────────────────────────────────────────────

class TestPmDelta:
    def test_missing_project_root_returns_guidance(self, empty_ctx):
        from project_mapper.mcp.tools.delta import handle_pm_delta
        result = handle_pm_delta({}, empty_ctx)
        assert "project_root" in result.lower()

    def test_nonexistent_root_raises(self, empty_ctx):
        from project_mapper.mcp.tools.delta import handle_pm_delta
        with pytest.raises(ValueError):
            handle_pm_delta({"project_root": "/nonexistent/path/xyz"}, empty_ctx)

    def test_valid_root_returns_string(self, ctx, tmp_path):
        from project_mapper.mcp.tools.delta import handle_pm_delta
        result = handle_pm_delta({"project_root": str(tmp_path)}, ctx)
        assert isinstance(result, str)


# ── pm_visualize ──────────────────────────────────────────────────────────────

class TestPmVisualize:
    def test_empty_graph_returns_message(self, empty_ctx):
        from project_mapper.mcp.tools.visualize import handle_pm_visualize
        result = handle_pm_visualize({"entity": "SomeClass"}, empty_ctx)
        assert isinstance(result, str)

    def test_known_entity_returns_diagram(self, ctx):
        from project_mapper.mcp.tools.visualize import handle_pm_visualize
        result = handle_pm_visualize({"entity": "UserService", "format": "mermaid"}, ctx)
        assert isinstance(result, str)

    def test_entity_required(self, ctx):
        from project_mapper.mcp.tools.visualize import handle_pm_visualize
        with pytest.raises(ValueError):
            handle_pm_visualize({}, ctx)


# ── pm_path ───────────────────────────────────────────────────────────────────

class TestPmPath:
    def test_empty_graph_returns_message(self, empty_ctx):
        from project_mapper.mcp.tools.path import handle_pm_path
        result = handle_pm_path({"from_entity": "A", "to_entity": "B"}, empty_ctx)
        assert isinstance(result, str)

    def test_path_between_connected_entities(self, ctx):
        from project_mapper.mcp.tools.path import handle_pm_path
        result = handle_pm_path({"from_entity": "UserService", "to_entity": "get_user"}, ctx)
        assert isinstance(result, str)

    def test_requires_both_endpoints(self, ctx):
        from project_mapper.mcp.tools.path import handle_pm_path
        with pytest.raises(ValueError):
            handle_pm_path({"from_entity": "UserService"}, ctx)
