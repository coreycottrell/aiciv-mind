"""
Tests for aiciv_mind.tools package.

Covers: bash, files (read/write/edit), search (grep/glob), ToolRegistry.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_tools.py -v
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.bash import bash_handler, TIMEOUT_SECONDS
from aiciv_mind.tools.files import read_file_handler, write_file_handler, edit_file_handler
from aiciv_mind.tools.search import grep_handler, glob_handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(coro):
    """Run a coroutine synchronously (works inside pytest-asyncio auto mode too)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Bash tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bash_simple_command():
    result = await bash_handler({"command": "echo hello"})
    assert "hello" in result


@pytest.mark.asyncio
async def test_bash_blocked_pattern():
    result = await bash_handler({"command": "rm -rf /"})
    assert result.startswith("BLOCKED:")


@pytest.mark.asyncio
async def test_bash_exit_code():
    result = await bash_handler({"command": "exit 1"})
    assert result.startswith("EXIT CODE 1:")


@pytest.mark.asyncio
async def test_bash_timeout(monkeypatch):
    """Simulate a timeout by patching asyncio.wait_for to raise TimeoutError."""

    async def _fake_wait_for(coro, timeout):
        # Close the coroutine so it doesn't leak; then simulate timeout.
        coro.close()
        raise asyncio.TimeoutError()

    with patch("aiciv_mind.tools.bash.asyncio.wait_for", side_effect=_fake_wait_for):
        result = await bash_handler({"command": "sleep 100"})
    assert result.startswith("TIMEOUT:")


# ---------------------------------------------------------------------------
# read_file tests
# ---------------------------------------------------------------------------


def test_read_file_exists(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("line one\nline two\nline three\n", encoding="utf-8")
    result = read_file_handler({"file_path": str(f)})
    assert "1\tline one" in result
    assert "2\tline two" in result
    assert "3\tline three" in result


def test_read_file_not_found(tmp_path):
    result = read_file_handler({"file_path": str(tmp_path / "nonexistent.txt")})
    assert result.startswith("ERROR: File not found")


def test_read_file_with_offset_and_limit(tmp_path):
    f = tmp_path / "multi.txt"
    f.write_text("\n".join(f"line {i}" for i in range(1, 11)) + "\n", encoding="utf-8")
    result = read_file_handler({"file_path": str(f), "offset": 3, "limit": 2})
    assert "3\tline 3" in result
    assert "4\tline 4" in result
    # Lines outside the window must not appear.
    assert "line 1" not in result
    assert "line 5" not in result


# ---------------------------------------------------------------------------
# write_file tests
# ---------------------------------------------------------------------------


def test_write_file(tmp_path):
    dest = tmp_path / "out.txt"
    result = write_file_handler({"file_path": str(dest), "content": "hello world\n"})
    assert "Written" in result
    assert dest.read_text(encoding="utf-8") == "hello world\n"


def test_write_file_creates_directories(tmp_path):
    dest = tmp_path / "deep" / "nested" / "file.txt"
    result = write_file_handler({"file_path": str(dest), "content": "data"})
    assert "Written" in result
    assert dest.exists()


# ---------------------------------------------------------------------------
# edit_file tests
# ---------------------------------------------------------------------------


def test_edit_file_success(tmp_path):
    f = tmp_path / "edit_me.txt"
    f.write_text("hello world\nfoo bar\n", encoding="utf-8")
    result = edit_file_handler({
        "file_path": str(f),
        "old_string": "hello world",
        "new_string": "goodbye world",
    })
    assert result == f"Replaced 1 occurrence in {f}"
    assert "goodbye world" in f.read_text(encoding="utf-8")
    assert "hello world" not in f.read_text(encoding="utf-8")


def test_edit_file_not_found_string(tmp_path):
    f = tmp_path / "no_match.txt"
    f.write_text("something else entirely\n", encoding="utf-8")
    result = edit_file_handler({
        "file_path": str(f),
        "old_string": "hello world",
        "new_string": "goodbye",
    })
    assert result == "ERROR: old_string not found in file"


def test_edit_file_ambiguous(tmp_path):
    f = tmp_path / "ambiguous.txt"
    f.write_text("hello world\nhello world\n", encoding="utf-8")
    result = edit_file_handler({
        "file_path": str(f),
        "old_string": "hello world",
        "new_string": "replaced",
    })
    assert result == "ERROR: old_string found 2 times — must be unique"


def test_edit_file_file_not_found(tmp_path):
    result = edit_file_handler({
        "file_path": str(tmp_path / "ghost.txt"),
        "old_string": "x",
        "new_string": "y",
    })
    assert result.startswith("ERROR: File not found")


# ---------------------------------------------------------------------------
# glob tests
# ---------------------------------------------------------------------------


def test_glob_finds_files(tmp_path):
    (tmp_path / "a.py").write_text("# a", encoding="utf-8")
    (tmp_path / "b.py").write_text("# b", encoding="utf-8")
    (tmp_path / "c.py").write_text("# c", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("not python", encoding="utf-8")

    result = glob_handler({"pattern": "*.py", "path": str(tmp_path)})
    lines = result.splitlines()
    py_files = [l for l in lines if l.endswith(".py")]
    assert len(py_files) == 3


def test_glob_no_matches(tmp_path):
    result = glob_handler({"pattern": "*.xyz", "path": str(tmp_path)})
    assert result == "No matches found"


def test_glob_recursive(tmp_path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "deep.py").write_text("# deep", encoding="utf-8")
    (tmp_path / "top.py").write_text("# top", encoding="utf-8")

    result = glob_handler({"pattern": "**/*.py", "path": str(tmp_path)})
    assert "deep.py" in result
    assert "top.py" in result


# ---------------------------------------------------------------------------
# grep tests
# ---------------------------------------------------------------------------


def test_grep_finds_pattern(tmp_path):
    f = tmp_path / "search_me.txt"
    f.write_text("apple\nbanana\ncherry\n", encoding="utf-8")
    result = grep_handler({"pattern": "banana", "path": str(tmp_path)})
    assert "banana" in result
    assert "apple" not in result


def test_grep_no_matches(tmp_path):
    f = tmp_path / "no_match.txt"
    f.write_text("hello world\n", encoding="utf-8")
    result = grep_handler({"pattern": "xyz_not_here", "path": str(tmp_path)})
    assert result == "No matches found"


def test_grep_with_context(tmp_path):
    f = tmp_path / "ctx.txt"
    lines = ["alpha", "beta", "gamma", "delta", "epsilon"]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = grep_handler({"pattern": "gamma", "path": str(tmp_path), "context": 1})
    # With context=1, should include beta, gamma, delta.
    assert "beta" in result
    assert "gamma" in result
    assert "delta" in result


def test_grep_invalid_regex(tmp_path):
    f = tmp_path / "dummy.txt"
    f.write_text("data\n", encoding="utf-8")
    result = grep_handler({"pattern": "[invalid(regex", "path": str(tmp_path)})
    assert result.startswith("ERROR: Invalid regex pattern")


def test_grep_on_single_file(tmp_path):
    f = tmp_path / "single.txt"
    f.write_text("foo\nbar\nbaz\n", encoding="utf-8")
    result = grep_handler({"pattern": "bar", "path": str(f)})
    assert "bar" in result
    assert "foo" not in result


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------


def test_tool_registry_default():
    registry = ToolRegistry.default()
    names = registry.names()
    assert "bash" in names
    assert "read_file" in names
    assert "write_file" in names
    assert "edit_file" in names
    assert "grep" in names
    assert "glob" in names
    # Memory tools not included without a store.
    assert "memory_search" not in names
    assert "memory_write" not in names


def test_tool_registry_default_with_memory():
    from aiciv_mind.memory import MemoryStore
    store = MemoryStore(":memory:")
    registry = ToolRegistry.default(memory_store=store)
    names = registry.names()
    assert "memory_search" in names
    assert "memory_write" in names
    store.close()


def test_tool_registry_build_anthropic_all():
    registry = ToolRegistry.default()
    tools = registry.build_anthropic_tools()
    assert isinstance(tools, list)
    assert len(tools) >= 6  # bash + 3 file + 2 search
    tool_names = [t["name"] for t in tools]
    assert "bash" in tool_names


def test_tool_registry_build_anthropic_filtered():
    registry = ToolRegistry.default()
    tools = registry.build_anthropic_tools(["bash"])
    assert len(tools) == 1
    assert tools[0]["name"] == "bash"


def test_tool_registry_build_anthropic_skips_unknown():
    registry = ToolRegistry.default()
    tools = registry.build_anthropic_tools(["bash", "nonexistent_tool"])
    assert len(tools) == 1
    assert tools[0]["name"] == "bash"


@pytest.mark.asyncio
async def test_tool_registry_execute_bash():
    registry = ToolRegistry.default()
    result = await registry.execute("bash", {"command": "echo hi"})
    assert "hi" in result


@pytest.mark.asyncio
async def test_tool_registry_execute_unknown():
    registry = ToolRegistry.default()
    result = await registry.execute("nonexistent", {})
    assert result.startswith("ERROR: Unknown tool")


def test_tool_registry_is_read_only():
    registry = ToolRegistry.default()
    assert registry.is_read_only("bash") is False
    assert registry.is_read_only("read_file") is True
    assert registry.is_read_only("write_file") is False
    assert registry.is_read_only("grep") is True
    assert registry.is_read_only("glob") is True


def test_tool_registry_definitions_have_required_keys():
    """All tool definitions must have name, description, and input_schema."""
    registry = ToolRegistry.default()
    for tool_def in registry.build_anthropic_tools():
        assert "name" in tool_def, f"Missing 'name' in {tool_def}"
        assert "description" in tool_def, f"Missing 'description' in {tool_def}"
        assert "input_schema" in tool_def, f"Missing 'input_schema' in {tool_def}"
        schema = tool_def["input_schema"]
        assert schema.get("type") == "object"
        assert "properties" in schema
