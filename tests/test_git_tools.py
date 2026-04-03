"""
Tests for aiciv_mind.tools.git_tools -- git operations scoped to aiciv-mind repo.

Covers: tool definitions, handler logic (mocked subprocess), error paths,
blocked patterns, and registration in ToolRegistry.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_git_tools.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.git_tools import (
    BLOCKED_PATTERNS,
    _check_blocked,
    register_git_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_process(stdout: bytes = b"", returncode: int = 0):
    """Create a mock asyncio subprocess."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_all_git_tools_registered():
    """register_git_tools adds all 6 git tools to a ToolRegistry."""
    registry = ToolRegistry()
    register_git_tools(registry)
    names = registry.names()
    expected = {"git_status", "git_diff", "git_add", "git_commit", "git_push", "git_log"}
    assert expected.issubset(set(names))


def test_git_tool_definitions_have_required_keys():
    """Every git tool definition must have name, description, input_schema."""
    registry = ToolRegistry()
    register_git_tools(registry)
    for tool_def in registry.build_anthropic_tools():
        assert "name" in tool_def, f"Missing 'name' in {tool_def}"
        assert "description" in tool_def, f"Missing 'description' in {tool_def}"
        assert "input_schema" in tool_def, f"Missing 'input_schema' in {tool_def}"
        schema = tool_def["input_schema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_read_only_flags():
    """git_status, git_diff, git_log are read-only; git_add, git_commit, git_push are not."""
    registry = ToolRegistry()
    register_git_tools(registry)
    assert registry.is_read_only("git_status") is True
    assert registry.is_read_only("git_diff") is True
    assert registry.is_read_only("git_log") is True
    assert registry.is_read_only("git_add") is False
    assert registry.is_read_only("git_commit") is False
    assert registry.is_read_only("git_push") is False


# ---------------------------------------------------------------------------
# _check_blocked tests
# ---------------------------------------------------------------------------


def test_check_blocked_rejects_force_push():
    result = _check_blocked("push --force origin main")
    assert result is not None
    assert "BLOCKED" in result
    assert "--force" in result


def test_check_blocked_rejects_reset_hard():
    result = _check_blocked("reset --hard HEAD~1")
    assert result is not None
    assert "reset --hard" in result


def test_check_blocked_allows_normal_commands():
    assert _check_blocked("status") is None
    assert _check_blocked("log --oneline -10") is None
    assert _check_blocked("diff --cached") is None


# ---------------------------------------------------------------------------
# git_status handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("aiciv_mind.tools.git_tools.asyncio.create_subprocess_shell")
async def test_git_status_runs_correct_command(mock_create):
    mock_create.return_value = _mock_process(b"On branch main\nnothing to commit\n")

    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_status", {})

    assert "On branch main" in result
    # Verify the command includes 'git -C ... status'
    call_args = mock_create.call_args
    cmd = call_args[0][0]
    assert "status" in cmd


# ---------------------------------------------------------------------------
# git_diff handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("aiciv_mind.tools.git_tools.asyncio.create_subprocess_shell")
async def test_git_diff_staged_flag(mock_create):
    mock_create.return_value = _mock_process(b"+new line\n")

    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_diff", {"staged": True})

    cmd = mock_create.call_args[0][0]
    assert "--cached" in cmd
    assert "+new line" in result


@pytest.mark.asyncio
@patch("aiciv_mind.tools.git_tools.asyncio.create_subprocess_shell")
async def test_git_diff_with_file_path(mock_create):
    mock_create.return_value = _mock_process(b"diff content\n")

    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_diff", {"file_path": "src/main.py"})

    cmd = mock_create.call_args[0][0]
    assert "-- src/main.py" in cmd


@pytest.mark.asyncio
async def test_git_diff_blocks_absolute_path_outside_repo():
    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_diff", {"file_path": "/etc/passwd"})

    assert "BLOCKED" in result


# ---------------------------------------------------------------------------
# git_log handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("aiciv_mind.tools.git_tools.asyncio.create_subprocess_shell")
async def test_git_log_default_count(mock_create):
    mock_create.return_value = _mock_process(b"abc1234 Initial commit\n")

    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_log", {})

    cmd = mock_create.call_args[0][0]
    assert "-10" in cmd


@pytest.mark.asyncio
@patch("aiciv_mind.tools.git_tools.asyncio.create_subprocess_shell")
async def test_git_log_caps_at_50(mock_create):
    mock_create.return_value = _mock_process(b"commits\n")

    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_log", {"count": 999})

    cmd = mock_create.call_args[0][0]
    assert "-50" in cmd
    assert "-999" not in cmd


# ---------------------------------------------------------------------------
# git_add handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("aiciv_mind.tools.git_tools.asyncio.create_subprocess_shell")
async def test_git_add_stages_files(mock_create):
    mock_create.return_value = _mock_process(b"", returncode=0)

    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_add", {"files": ["src/main.py", "README.md"]})

    assert "Staged" in result
    assert "src/main.py" in result
    assert "README.md" in result


@pytest.mark.asyncio
async def test_git_add_error_no_files():
    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_add", {"files": []})

    assert "ERROR" in result
    assert "No files" in result


@pytest.mark.asyncio
async def test_git_add_blocks_absolute_outside_repo():
    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_add", {"files": ["/etc/shadow"]})

    assert "BLOCKED" in result


# ---------------------------------------------------------------------------
# git_commit handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("aiciv_mind.tools.git_tools.asyncio.create_subprocess_shell")
async def test_git_commit_prefixes_root(mock_create):
    mock_create.return_value = _mock_process(b"[main abc1234] [Root] fix bug\n")

    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_commit", {"message": "fix bug"})

    cmd = mock_create.call_args[0][0]
    assert "[Root]" in cmd


@pytest.mark.asyncio
async def test_git_commit_error_empty_message():
    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_commit", {"message": ""})

    assert "ERROR" in result
    assert "No commit message" in result


# ---------------------------------------------------------------------------
# git_push handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("aiciv_mind.tools.git_tools.asyncio.create_subprocess_shell")
async def test_git_push_runs_push_origin_head(mock_create):
    mock_create.return_value = _mock_process(b"Everything up-to-date\n")

    registry = ToolRegistry()
    register_git_tools(registry)
    result = await registry.execute("git_push", {})

    cmd = mock_create.call_args[0][0]
    assert "push origin HEAD" in cmd
    assert "Everything up-to-date" in result
