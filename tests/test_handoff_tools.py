"""
Tests for aiciv_mind.tools.handoff_tools — handoff_context for session continuity.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from aiciv_mind.memory import MemoryStore, Memory
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.handoff_tools import (
    _HANDOFF_CONTEXT_DEFINITION,
    _git_recent_commits,
    _git_changed_files,
    _make_handoff_context_handler,
    register_handoff_tools,
)


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_name(self):
        assert _HANDOFF_CONTEXT_DEFINITION["name"] == "handoff_context"

    def test_has_description(self):
        assert len(_HANDOFF_CONTEXT_DEFINITION["description"]) > 20

    def test_since_commits_field(self):
        props = _HANDOFF_CONTEXT_DEFINITION["input_schema"]["properties"]
        assert "since_commits" in props
        assert props["since_commits"]["type"] == "integer"

    def test_no_required_fields(self):
        """All fields are optional — handoff_context works with no args."""
        schema = _HANDOFF_CONTEXT_DEFINITION["input_schema"]
        assert "required" not in schema or len(schema.get("required", [])) == 0


# ---------------------------------------------------------------------------
# Git helper functions
# ---------------------------------------------------------------------------


class TestGitHelpers:
    def test_git_recent_commits_success(self, tmp_path):
        with patch("aiciv_mind.tools.handoff_tools.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc1234 fix: something\ndef5678 feat: other\n",
            )
            result = _git_recent_commits(str(tmp_path), n=5)
        assert "abc1234" in result
        assert "def5678" in result
        mock_run.assert_called_once()
        # Verify --oneline and -5 flags
        args = mock_run.call_args[0][0]
        assert "--oneline" in args
        assert "-5" in args

    def test_git_recent_commits_failure(self, tmp_path):
        with patch("aiciv_mind.tools.handoff_tools.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = _git_recent_commits(str(tmp_path))
        assert "failed" in result

    def test_git_recent_commits_exception(self, tmp_path):
        with patch("aiciv_mind.tools.handoff_tools.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("timeout")
            result = _git_recent_commits(str(tmp_path))
        assert "error" in result.lower()

    def test_git_changed_files_clean(self, tmp_path):
        with patch("aiciv_mind.tools.handoff_tools.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = _git_changed_files(str(tmp_path))
        assert "clean" in result.lower()

    def test_git_changed_files_with_changes(self, tmp_path):
        with patch("aiciv_mind.tools.handoff_tools.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=" M src/mind.py\n?? tests/new_test.py\n"
            )
            result = _git_changed_files(str(tmp_path))
        assert "mind.py" in result
        assert "new_test.py" in result


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class TestHandoffHandler:
    @pytest.fixture
    def store(self):
        s = MemoryStore(":memory:")
        yield s
        s.close()

    def test_handler_returns_handoff_header(self, store):
        handler = _make_handoff_context_handler(memory_store=store)
        result = handler({})
        assert "Handoff Context" in result

    def test_handler_includes_memory_stats(self, store):
        handler = _make_handoff_context_handler(memory_store=store)
        result = handler({})
        assert "Memory Stats" in result
        assert "Memories: 0" in result

    def test_handler_includes_memory_stats_with_data(self, store):
        store.store(Memory(
            agent_id="primary", title="Test learning",
            content="Learned something", memory_type="learning",
        ))
        handler = _make_handoff_context_handler(memory_store=store)
        result = handler({})
        assert "Memories: 1" in result

    def test_handler_includes_git_when_mind_root_set(self, tmp_path):
        with patch("aiciv_mind.tools.handoff_tools.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc fix\n")
            handler = _make_handoff_context_handler(mind_root=str(tmp_path))
            result = handler({})
        assert "Recent Commits" in result

    def test_handler_includes_tools_when_registry_set(self, store):
        registry = ToolRegistry()
        registry.register("test_tool", {
            "name": "test_tool",
            "description": "A test",
            "input_schema": {"type": "object", "properties": {}},
        }, lambda x: "ok")
        handler = _make_handoff_context_handler(
            memory_store=store, registry=registry,
        )
        result = handler({})
        assert "Available Tools" in result
        assert "test_tool" in result

    def test_handler_since_commits_param(self, tmp_path):
        with patch("aiciv_mind.tools.handoff_tools.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc\n")
            handler = _make_handoff_context_handler(mind_root=str(tmp_path))
            handler({"since_commits": 3})
        # Check that git log was called with -3
        args = mock_run.call_args_list[0][0][0]
        assert "-3" in args

    def test_handler_minimal_no_deps(self):
        """Handler works with no memory_store, no mind_root, no registry."""
        handler = _make_handoff_context_handler()
        result = handler({})
        assert "Handoff Context" in result

    def test_handler_includes_scratchpad_when_exists(self, tmp_path):
        from datetime import date
        scratchpad_dir = tmp_path / "scratchpads"
        scratchpad_dir.mkdir()
        today_pad = scratchpad_dir / f"{date.today().isoformat()}.md"
        today_pad.write_text("## Today\nDid some work on tests.")

        with patch("aiciv_mind.tools.handoff_tools.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            handler = _make_handoff_context_handler(mind_root=str(tmp_path))
            result = handler({})
        assert "Today's Scratchpad" in result
        assert "Did some work on tests" in result

    def test_handler_scratchpad_missing(self, tmp_path):
        with patch("aiciv_mind.tools.handoff_tools.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            handler = _make_handoff_context_handler(mind_root=str(tmp_path))
            result = handler({})
        assert "none for" in result


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_handoff_tools(self):
        registry = ToolRegistry()
        register_handoff_tools(registry)
        assert "handoff_context" in registry.names()

    def test_registered_as_read_only(self):
        registry = ToolRegistry()
        register_handoff_tools(registry)
        assert registry.is_read_only("handoff_context") is True

    def test_handler_is_callable(self):
        registry = ToolRegistry()
        register_handoff_tools(registry)
        handler = registry._handlers["handoff_context"]
        assert callable(handler)
