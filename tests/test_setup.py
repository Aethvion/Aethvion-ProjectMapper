"""
Tests for project_mapper.setup: the idempotent rules-file writer, the
JSON-config merge helper, and Claude Code's CLI-vs-fallback registration
path. These are the parts that broke the previous pm-setup (wrong file,
wrong format) -- the thing actually under test is "never duplicate, never
clobber, never touch an unrelated key".
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from project_mapper.setup import cli
from project_mapper.setup.agents import claude_code
from project_mapper.setup.agents.base import Agent
from project_mapper.setup.mcp_config import SERVER_ENTRY, register_in_json_config
from project_mapper.setup.rules import DIRECTIVE_MARKER, append_directive

# ── append_directive ──────────────────────────────────────────────────────────


class TestAppendDirective:
    def test_creates_file_that_does_not_exist(self, tmp_path):
        path = tmp_path / "CLAUDE.md"
        status = append_directive(path)

        assert status == "created"
        assert path.exists()
        assert DIRECTIVE_MARKER in path.read_text(encoding="utf-8")

    def test_creates_missing_parent_directories(self, tmp_path):
        path = tmp_path / ".cursor" / "rules" / "project-mapper.mdc"
        status = append_directive(path)

        assert status == "created"
        assert path.exists()

    def test_appends_to_existing_file_without_marker(self, tmp_path):
        path = tmp_path / "CLAUDE.md"
        path.write_text("# My Project\n\nSome existing conventions.\n", encoding="utf-8")

        status = append_directive(path)

        assert status == "added"
        text = path.read_text(encoding="utf-8")
        assert "Some existing conventions." in text
        assert DIRECTIVE_MARKER in text

    def test_second_run_is_a_noop(self, tmp_path):
        path = tmp_path / "CLAUDE.md"
        append_directive(path)
        original = path.read_text(encoding="utf-8")

        status = append_directive(path)

        assert status == "already-present"
        assert path.read_text(encoding="utf-8") == original

    def test_frontmatter_only_applied_on_creation(self, tmp_path):
        path = tmp_path / "project-mapper.mdc"
        append_directive(path, frontmatter="---\nalwaysApply: true\n---\n\n")

        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\nalwaysApply: true\n---\n\n")


# ── register_in_json_config ───────────────────────────────────────────────────


class TestRegisterInJsonConfig:
    def test_creates_file_that_does_not_exist(self, tmp_path):
        path = tmp_path / "mcp.json"
        status = register_in_json_config(path)

        assert status == "registered"
        config = json.loads(path.read_text(encoding="utf-8"))
        assert config["mcpServers"]["project-mapper"] == SERVER_ENTRY

    def test_preserves_other_servers_and_top_level_keys(self, tmp_path):
        path = tmp_path / "mcp.json"
        path.write_text(
            json.dumps({"mcpServers": {"other-tool": {"command": "other"}}, "unrelated": True}),
            encoding="utf-8",
        )

        status = register_in_json_config(path)

        assert status == "registered"
        config = json.loads(path.read_text(encoding="utf-8"))
        assert config["mcpServers"]["other-tool"] == {"command": "other"}
        assert config["mcpServers"]["project-mapper"] == SERVER_ENTRY
        assert config["unrelated"] is True

    def test_second_run_is_a_noop(self, tmp_path):
        path = tmp_path / "mcp.json"
        register_in_json_config(path)
        original = path.read_text(encoding="utf-8")

        status = register_in_json_config(path)

        assert status == "already-registered"
        assert path.read_text(encoding="utf-8") == original

    def test_invalid_json_fails_loudly_instead_of_overwriting(self, tmp_path):
        path = tmp_path / "mcp.json"
        path.write_text("{not valid json", encoding="utf-8")

        status = register_in_json_config(path)

        assert status.startswith("failed")
        assert path.read_text(encoding="utf-8") == "{not valid json"


# ── Claude Code registration ──────────────────────────────────────────────────


class TestClaudeCodeRegisterMcp:
    def test_falls_back_to_mcp_json_when_cli_missing(self, tmp_path):
        with patch("project_mapper.setup.agents.claude_code.shutil.which", return_value=None):
            status = claude_code.register_mcp(tmp_path)

        assert status == "registered"
        config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
        assert config["mcpServers"]["project-mapper"] == SERVER_ENTRY

    def test_uses_cli_when_present(self, tmp_path):
        fake_result = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch("project_mapper.setup.agents.claude_code.shutil.which", return_value="/usr/bin/claude"),
            patch("project_mapper.setup.agents.claude_code.subprocess.run", return_value=fake_result) as run,
        ):
            status = claude_code.register_mcp(tmp_path)

        assert status == "registered"
        run.assert_called_once()
        assert run.call_args.args[0][:3] == ["/usr/bin/claude", "mcp", "add"]
        # Falling back to a hand-written .mcp.json must not also happen.
        assert not (tmp_path / ".mcp.json").exists()

    def test_cli_already_registered_is_not_a_failure(self, tmp_path):
        fake_result = MagicMock(returncode=1, stdout="", stderr="Error: project-mapper already exists")
        with (
            patch("project_mapper.setup.agents.claude_code.shutil.which", return_value="/usr/bin/claude"),
            patch("project_mapper.setup.agents.claude_code.subprocess.run", return_value=fake_result),
        ):
            status = claude_code.register_mcp(tmp_path)

        assert status == "already-registered"

    def test_unexpected_cli_failure_is_reported(self, tmp_path):
        fake_result = MagicMock(returncode=1, stdout="", stderr="permission denied")
        with (
            patch("project_mapper.setup.agents.claude_code.shutil.which", return_value="/usr/bin/claude"),
            patch("project_mapper.setup.agents.claude_code.subprocess.run", return_value=fake_result),
        ):
            status = claude_code.register_mcp(tmp_path)

        assert status == "failed: permission denied"

    def test_rules_path_is_claude_md_at_project_root(self, tmp_path):
        assert claude_code.rules_path(tmp_path) == tmp_path / "CLAUDE.md"

    def test_global_rules_path_is_claude_md_in_home(self):
        assert claude_code.global_rules_path() == Path.home() / ".claude" / "CLAUDE.md"

    def test_global_only_refuses_instead_of_falling_back_to_project_file(self, tmp_path):
        with patch("project_mapper.setup.agents.claude_code.shutil.which", return_value=None):
            status = claude_code.register_mcp(tmp_path, global_only=True)

        assert status.startswith("failed")
        assert not (tmp_path / ".mcp.json").exists()

    def test_global_only_with_cli_present_still_registers(self, tmp_path):
        fake_result = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch("project_mapper.setup.agents.claude_code.shutil.which", return_value="/usr/bin/claude"),
            patch("project_mapper.setup.agents.claude_code.subprocess.run", return_value=fake_result),
        ):
            status = claude_code.register_mcp(tmp_path, global_only=True)

        assert status == "registered"


# ── pm-setup --global ──────────────────────────────────────────────────────────


class TestConfigureGlobal:
    def _agent(self, tmp_path, *, global_rules_path=None):
        return Agent(
            key="fake",
            label="Fake Agent",
            detect=lambda: True,
            register_mcp=lambda project_root, global_only: "registered",
            rules_path=lambda project_root: project_root / "CLAUDE.md",
            global_rules_path=global_rules_path,
        )

    def test_global_writes_to_global_path_not_project(self, tmp_path):
        home = tmp_path / "home"
        agent = self._agent(tmp_path, global_rules_path=lambda: home / "CLAUDE.md")

        failed = cli._configure(agent, tmp_path / "project", use_global=True)

        assert not failed
        assert (home / "CLAUDE.md").exists()
        assert not (tmp_path / "project" / "CLAUDE.md").exists()

    def test_global_without_verified_path_fails_without_writing(self, tmp_path):
        agent = self._agent(tmp_path, global_rules_path=None)
        project_root = tmp_path / "project"

        failed = cli._configure(agent, project_root, use_global=True)

        assert failed
        assert not project_root.exists()

    def test_non_global_still_writes_to_project_root(self, tmp_path):
        agent = self._agent(tmp_path, global_rules_path=lambda: tmp_path / "home" / "CLAUDE.md")
        project_root = tmp_path / "project"
        project_root.mkdir()

        failed = cli._configure(agent, project_root, use_global=False)

        assert not failed
        assert (project_root / "CLAUDE.md").exists()
