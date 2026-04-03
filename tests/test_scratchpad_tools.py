"""
Tests for aiciv_mind.tools.scratchpad_tools -- daily scratchpad working memory.

Covers: tool definitions, read/write/append handlers with tmp_path,
shared_scratchpad_read merging, error cases, and registration in ToolRegistry.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_scratchpad_tools.py -v
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.scratchpad_tools import register_scratchpad_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def scratch_dir(tmp_path):
    """Create a temporary scratchpad directory."""
    d = tmp_path / "scratchpads"
    d.mkdir()
    return str(d)


@pytest.fixture()
def mind_lead_dir(tmp_path):
    """Create a temporary mind-lead scratchpad directory."""
    d = tmp_path / "mind-lead-scratchpads"
    d.mkdir()
    return str(d)


@pytest.fixture()
def registry(scratch_dir, mind_lead_dir):
    """Create a ToolRegistry with scratchpad tools registered."""
    reg = ToolRegistry()
    register_scratchpad_tools(reg, scratch_dir, mind_lead_dir)
    return reg


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_all_scratchpad_tools_registered(registry):
    """register_scratchpad_tools adds all 4 scratchpad tools."""
    names = registry.names()
    expected = {"scratchpad_read", "scratchpad_write", "scratchpad_append", "shared_scratchpad_read"}
    assert expected.issubset(set(names))


def test_scratchpad_tool_definitions_have_required_keys(registry):
    """Every scratchpad tool definition must have name, description, input_schema."""
    for tool_def in registry.build_anthropic_tools():
        assert "name" in tool_def
        assert "description" in tool_def
        assert "input_schema" in tool_def
        schema = tool_def["input_schema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_read_only_flags(registry):
    """scratchpad_read and shared_scratchpad_read are read-only; write/append are not."""
    assert registry.is_read_only("scratchpad_read") is True
    assert registry.is_read_only("scratchpad_write") is False
    assert registry.is_read_only("scratchpad_append") is False
    assert registry.is_read_only("shared_scratchpad_read") is True


# ---------------------------------------------------------------------------
# scratchpad_read handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scratchpad_read_nonexistent(registry):
    """Reading when no scratchpad exists returns a helpful message."""
    result = await registry.execute("scratchpad_read", {})

    assert "No scratchpad" in result
    assert "scratchpad_write" in result


@pytest.mark.asyncio
async def test_scratchpad_read_existing(scratch_dir, registry):
    """Reading an existing scratchpad returns its content."""
    today = date.today().isoformat()
    path = Path(scratch_dir) / f"{today}.md"
    path.write_text("## Working notes\n- Task A done\n")

    result = await registry.execute("scratchpad_read", {})

    assert "Working notes" in result
    assert "Task A done" in result


# ---------------------------------------------------------------------------
# scratchpad_write handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scratchpad_write_creates_file(scratch_dir, registry):
    """Writing creates the scratchpad file with the given content."""
    content = "## Today\n- Started testing\n- Fixed a bug"
    result = await registry.execute("scratchpad_write", {"content": content})

    assert "Scratchpad updated" in result
    assert str(len(content)) in result

    today = date.today().isoformat()
    path = Path(scratch_dir) / f"{today}.md"
    assert path.exists()
    assert path.read_text() == content


@pytest.mark.asyncio
async def test_scratchpad_write_replaces_existing(scratch_dir, registry):
    """Writing replaces the entire content (not appends)."""
    await registry.execute("scratchpad_write", {"content": "old content"})
    await registry.execute("scratchpad_write", {"content": "new content"})

    today = date.today().isoformat()
    path = Path(scratch_dir) / f"{today}.md"
    assert path.read_text() == "new content"


# ---------------------------------------------------------------------------
# scratchpad_append handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scratchpad_append_creates_file_if_needed(scratch_dir, registry):
    """Appending to a nonexistent scratchpad creates the file."""
    result = await registry.execute("scratchpad_append", {"line": "- first note"})

    assert "Appended" in result
    today = date.today().isoformat()
    path = Path(scratch_dir) / f"{today}.md"
    assert path.exists()
    assert "- first note\n" in path.read_text()


@pytest.mark.asyncio
async def test_scratchpad_append_adds_to_existing(scratch_dir, registry):
    """Appending adds a line to the end of the existing scratchpad."""
    await registry.execute("scratchpad_write", {"content": "## Notes\n"})
    await registry.execute("scratchpad_append", {"line": "- added later"})

    today = date.today().isoformat()
    path = Path(scratch_dir) / f"{today}.md"
    content = path.read_text()
    assert content.endswith("- added later\n")
    assert "## Notes\n" in content


# ---------------------------------------------------------------------------
# shared_scratchpad_read handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_scratchpad_read_merges_both(scratch_dir, mind_lead_dir, registry):
    """shared_scratchpad_read shows both Root's and Mind-Lead's scratchpads."""
    today = date.today().isoformat()
    (Path(scratch_dir) / f"{today}.md").write_text("Root notes here")
    (Path(mind_lead_dir) / f"{today}.md").write_text("Mind-Lead notes here")

    result = await registry.execute("shared_scratchpad_read", {})

    assert "Root's Scratchpad" in result
    assert "Root notes here" in result
    assert "Mind-Lead's Scratchpad" in result
    assert "Mind-Lead notes here" in result


@pytest.mark.asyncio
async def test_shared_scratchpad_read_shows_no_scratchpad_when_empty(registry):
    """shared_scratchpad_read shows '(no scratchpad)' when neither file exists."""
    result = await registry.execute("shared_scratchpad_read", {})

    assert "(no scratchpad)" in result


@pytest.mark.asyncio
async def test_shared_scratchpad_read_invalid_date(registry):
    """shared_scratchpad_read returns error for invalid date format."""
    result = await registry.execute("shared_scratchpad_read", {"date": "not-a-date"})

    assert "ERROR" in result
    assert "Invalid date format" in result
