"""
Tests for aiciv_mind.tools.graph_tools -- memory graph link tools.

Covers: tool definitions, handlers with real MemoryStore(":memory:"),
link creation, graph traversal, conflict/superseded queries, invalid link type,
and registration in ToolRegistry.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_graph_tools.py -v
"""

from __future__ import annotations

import pytest

from aiciv_mind.memory import Memory, MemoryStore
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.graph_tools import register_graph_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store():
    """Create an in-memory MemoryStore for testing."""
    return MemoryStore(":memory:", auto_link=False)


@pytest.fixture()
def registry(store):
    """Create a ToolRegistry with graph tools registered."""
    reg = ToolRegistry()
    register_graph_tools(reg, store)
    return reg


def _store_memory(store: MemoryStore, mem_id: str, title: str) -> str:
    """Helper: store a memory with given id and title."""
    mem = Memory(
        id=mem_id,
        agent_id="test-agent",
        title=title,
        content=f"Content for {title}",
        domain="test",
    )
    return store.store(mem)


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_all_graph_tools_registered(registry):
    """register_graph_tools adds all 4 graph tools."""
    names = registry.names()
    expected = {"memory_link", "memory_graph", "memory_conflicts", "memory_superseded"}
    assert expected.issubset(set(names))


def test_graph_tool_definitions_have_required_keys(registry):
    """Every graph tool definition must have name, description, input_schema."""
    for tool_def in registry.build_anthropic_tools():
        assert "name" in tool_def
        assert "description" in tool_def
        assert "input_schema" in tool_def
        schema = tool_def["input_schema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_read_only_flags(registry):
    """memory_link is not read-only; the rest are."""
    assert registry.is_read_only("memory_link") is False
    assert registry.is_read_only("memory_graph") is True
    assert registry.is_read_only("memory_conflicts") is True
    assert registry.is_read_only("memory_superseded") is True


# ---------------------------------------------------------------------------
# memory_link handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_link_creates_link(store, registry):
    _store_memory(store, "mem-a", "First Memory")
    _store_memory(store, "mem-b", "Second Memory")

    result = await registry.execute("memory_link", {
        "source_id": "mem-a",
        "target_id": "mem-b",
        "link_type": "references",
        "reason": "A cites B",
    })

    assert "Link created" in result
    assert "[references]" in result
    assert "mem-a" in result
    assert "mem-b" in result


@pytest.mark.asyncio
async def test_memory_link_invalid_type(registry):
    result = await registry.execute("memory_link", {
        "source_id": "x",
        "target_id": "y",
        "link_type": "invalidtype",
    })

    assert "ERROR" in result
    assert "invalidtype" in result


@pytest.mark.asyncio
async def test_memory_link_missing_ids(registry):
    result = await registry.execute("memory_link", {
        "source_id": "",
        "target_id": "y",
        "link_type": "references",
    })

    assert "ERROR" in result
    assert "required" in result


# ---------------------------------------------------------------------------
# memory_graph handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_graph_shows_neighborhood(store, registry):
    _store_memory(store, "mem-1", "Root Memory")
    _store_memory(store, "mem-2", "Related Memory")
    _store_memory(store, "mem-3", "Predecessor")

    # Create outgoing link: mem-1 -> mem-2
    await registry.execute("memory_link", {
        "source_id": "mem-1",
        "target_id": "mem-2",
        "link_type": "references",
    })
    # Create incoming link: mem-3 -> mem-1
    await registry.execute("memory_link", {
        "source_id": "mem-3",
        "target_id": "mem-1",
        "link_type": "compounds",
    })

    result = await registry.execute("memory_graph", {"memory_id": "mem-1"})

    assert "Root Memory" in result
    assert "Links FROM this memory" in result
    assert "Related Memory" in result
    assert "Links TO this memory" in result
    assert "Predecessor" in result


@pytest.mark.asyncio
async def test_memory_graph_nonexistent_memory(registry):
    result = await registry.execute("memory_graph", {"memory_id": "does-not-exist"})

    assert "may have been archived" in result


@pytest.mark.asyncio
async def test_memory_graph_empty_id(registry):
    result = await registry.execute("memory_graph", {"memory_id": ""})

    assert "ERROR" in result
    assert "required" in result


# ---------------------------------------------------------------------------
# memory_conflicts handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_conflicts_returns_conflicts(store, registry):
    _store_memory(store, "c-1", "Claim A")
    _store_memory(store, "c-2", "Contradicting B")

    await registry.execute("memory_link", {
        "source_id": "c-1",
        "target_id": "c-2",
        "link_type": "conflicts",
        "reason": "They disagree on X",
    })

    result = await registry.execute("memory_conflicts", {})

    assert "Conflict" in result
    assert "Claim A" in result
    assert "Contradicting B" in result
    assert "They disagree on X" in result


@pytest.mark.asyncio
async def test_memory_conflicts_empty_when_none(registry):
    result = await registry.execute("memory_conflicts", {})

    assert "No unresolved memory conflicts" in result


# ---------------------------------------------------------------------------
# memory_superseded handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_superseded_returns_replaced(store, registry):
    _store_memory(store, "old-1", "Old Knowledge")
    _store_memory(store, "new-1", "Updated Knowledge")

    await registry.execute("memory_link", {
        "source_id": "new-1",
        "target_id": "old-1",
        "link_type": "supersedes",
    })

    result = await registry.execute("memory_superseded", {})

    assert "Old Knowledge" in result
    assert "old-1" in result


@pytest.mark.asyncio
async def test_memory_superseded_empty_when_none(registry):
    result = await registry.execute("memory_superseded", {})

    assert "No superseded memories" in result
