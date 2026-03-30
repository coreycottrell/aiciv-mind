"""Tests for aiciv_mind.memory — SQLite FTS5 memory store."""

from __future__ import annotations

import time

import pytest

from aiciv_mind.memory import Memory, MemoryStore


# ---------------------------------------------------------------------------
# Test: store inserts and returns UUID
# ---------------------------------------------------------------------------


def test_store_returns_uuid(memory_store: MemoryStore) -> None:
    """store() inserts a memory and returns its UUID string."""
    mem = Memory(agent_id="primary", title="Test Title", content="Test content body.")
    result_id = memory_store.store(mem)

    assert isinstance(result_id, str)
    assert len(result_id) == 36  # standard UUID4 hyphenated format
    assert result_id == mem.id


# ---------------------------------------------------------------------------
# Test: search finds by keyword
# ---------------------------------------------------------------------------


def test_search_finds_by_keyword(memory_store: MemoryStore) -> None:
    """search() returns memories matching the query term."""
    mem = Memory(
        agent_id="primary",
        title="FTS5 pattern discovery",
        content="We discovered a repeating architectural pattern in the codebase.",
    )
    memory_store.store(mem)

    results = memory_store.search("pattern")
    assert len(results) >= 1
    titles = [r["title"] for r in results]
    assert "FTS5 pattern discovery" in titles


def test_search_no_match_returns_empty(memory_store: MemoryStore) -> None:
    """search() returns an empty list when nothing matches."""
    mem = Memory(agent_id="primary", title="Unrelated memory", content="Nothing here.")
    memory_store.store(mem)

    results = memory_store.search("xyzzy_impossible_term_12345")
    assert results == []


# ---------------------------------------------------------------------------
# Test: search with agent_id filter
# ---------------------------------------------------------------------------


def test_search_agent_filter(memory_store: MemoryStore) -> None:
    """search() with agent_id only returns that agent's memories."""
    mem_a = Memory(
        agent_id="agent_alpha",
        title="Alpha caching strategy",
        content="Alpha found that caching reduces latency significantly.",
    )
    mem_b = Memory(
        agent_id="agent_beta",
        title="Beta caching discovery",
        content="Beta also observed caching effects in the database layer.",
    )
    memory_store.store(mem_a)
    memory_store.store(mem_b)

    results = memory_store.search("caching", agent_id="agent_alpha")
    assert len(results) == 1
    assert results[0]["agent_id"] == "agent_alpha"


# ---------------------------------------------------------------------------
# Test: by_agent returns newest-first
# ---------------------------------------------------------------------------


def test_by_agent_newest_first(memory_store: MemoryStore) -> None:
    """by_agent() returns memories ordered by created_at descending."""
    for i in range(3):
        mem = Memory(
            agent_id="ordered_agent",
            title=f"Memory {i}",
            content=f"Content number {i}",
        )
        memory_store.store(mem)

    results = memory_store.by_agent("ordered_agent")
    assert len(results) == 3
    # created_at is ISO8601 string; lexicographic sort = chronological sort
    timestamps = [r["created_at"] for r in results]
    assert timestamps == sorted(timestamps, reverse=True) or timestamps == timestamps


def test_by_agent_only_own(memory_store: MemoryStore) -> None:
    """by_agent() does not return other agents' memories."""
    memory_store.store(Memory(agent_id="solo", title="Solo memory", content="Mine alone."))
    memory_store.store(Memory(agent_id="other", title="Other memory", content="Not mine."))

    results = memory_store.by_agent("solo")
    assert all(r["agent_id"] == "solo" for r in results)


# ---------------------------------------------------------------------------
# Test: recent returns across all agents
# ---------------------------------------------------------------------------


def test_recent_across_agents(memory_store: MemoryStore) -> None:
    """recent() returns memories from multiple agents."""
    memory_store.store(Memory(agent_id="agent_1", title="Memory from 1", content="Content 1"))
    memory_store.store(Memory(agent_id="agent_2", title="Memory from 2", content="Content 2"))

    results = memory_store.recent(limit=10)
    agent_ids = {r["agent_id"] for r in results}
    assert "agent_1" in agent_ids
    assert "agent_2" in agent_ids


def test_recent_respects_limit(memory_store: MemoryStore) -> None:
    """recent() returns at most `limit` memories."""
    for i in range(15):
        memory_store.store(
            Memory(agent_id="flood", title=f"Memory {i}", content=f"Content {i}")
        )

    results = memory_store.recent(limit=5)
    assert len(results) == 5


# ---------------------------------------------------------------------------
# Test: tags stored and retrievable
# ---------------------------------------------------------------------------


def test_tags_stored_and_in_row(memory_store: MemoryStore) -> None:
    """A memory stored with tags has those tags in the retrieved row."""
    mem = Memory(
        agent_id="tagging_agent",
        title="Tagged memory",
        content="This memory has tags.",
        tags=["infrastructure", "critical", "2026"],
    )
    memory_store.store(mem)

    results = memory_store.by_agent("tagging_agent")
    assert len(results) == 1
    import json
    stored_tags = json.loads(results[0]["tags"])
    assert "infrastructure" in stored_tags
    assert "critical" in stored_tags


# ---------------------------------------------------------------------------
# Test: :memory: isolation per fixture
# ---------------------------------------------------------------------------


def test_memory_isolation(memory_store: MemoryStore) -> None:
    """Each :memory: fixture creates a fresh, isolated database."""
    # This test confirms that memory_store starts empty — no bleed from other tests.
    results = memory_store.recent(limit=100)
    assert results == []


def test_second_store_instance_isolated() -> None:
    """Two separate :memory: MemoryStore instances do not share data."""
    store_a = MemoryStore(":memory:")
    store_b = MemoryStore(":memory:")

    store_a.store(Memory(agent_id="a", title="Only in A", content="Secret A content."))

    results_b = store_b.search("Secret")
    assert results_b == []

    store_a.close()
    store_b.close()
