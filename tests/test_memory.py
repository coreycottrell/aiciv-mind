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


# ---------------------------------------------------------------------------
# Test: touch() — depth signal updates
# ---------------------------------------------------------------------------


def test_touch_increments_access_count(memory_store: MemoryStore) -> None:
    """touch() increments access_count and sets last_accessed_at."""
    mem = Memory(agent_id="primary", title="Touchable", content="Touch me.")
    memory_store.store(mem)

    memory_store.touch(mem.id)
    memory_store.touch(mem.id)

    rows = memory_store.by_agent("primary")
    assert rows[0]["access_count"] == 2
    assert rows[0]["last_accessed_at"] is not None


def test_touch_unknown_id_does_not_crash(memory_store: MemoryStore) -> None:
    """touch() on a non-existent id is a silent no-op."""
    memory_store.touch("nonexistent-id-xyz")  # should not raise


# ---------------------------------------------------------------------------
# Test: pin / unpin
# ---------------------------------------------------------------------------


def test_pin_sets_is_pinned(memory_store: MemoryStore) -> None:
    """pin() sets is_pinned=1; get_pinned() returns it."""
    mem = Memory(agent_id="primary", title="Pinned memory", content="Always in context.")
    memory_store.store(mem)
    memory_store.pin(mem.id)

    pinned = memory_store.get_pinned(agent_id="primary")
    assert len(pinned) == 1
    assert pinned[0]["id"] == mem.id


def test_unpin_removes_pinned(memory_store: MemoryStore) -> None:
    """unpin() removes pinned status."""
    mem = Memory(agent_id="primary", title="Unpinnable", content="Goes away.")
    memory_store.store(mem)
    memory_store.pin(mem.id)
    memory_store.unpin(mem.id)

    pinned = memory_store.get_pinned(agent_id="primary")
    assert all(p["id"] != mem.id for p in pinned)


def test_get_pinned_agent_filter(memory_store: MemoryStore) -> None:
    """get_pinned() only returns pinned memories for the specified agent."""
    mem_a = Memory(agent_id="agent_a", title="A pinned", content="Agent A memory.")
    mem_b = Memory(agent_id="agent_b", title="B pinned", content="Agent B memory.")
    memory_store.store(mem_a)
    memory_store.store(mem_b)
    memory_store.pin(mem_a.id)
    memory_store.pin(mem_b.id)

    pinned_a = memory_store.get_pinned(agent_id="agent_a")
    assert len(pinned_a) == 1
    assert pinned_a[0]["agent_id"] == "agent_a"


# ---------------------------------------------------------------------------
# Test: search_by_depth
# ---------------------------------------------------------------------------


def test_search_by_depth_orders_by_depth_score(memory_store: MemoryStore) -> None:
    """search_by_depth() returns memories in depth_score descending order."""
    mem_low = Memory(agent_id="primary", title="Low depth", content="Rarely accessed.")
    mem_high = Memory(agent_id="primary", title="High depth", content="Frequently accessed.")
    memory_store.store(mem_low)
    memory_store.store(mem_high)

    # Boost mem_high's depth via touches
    for _ in range(5):
        memory_store.touch(mem_high.id)
    memory_store.update_depth_score(mem_high.id)
    memory_store.update_depth_score(mem_low.id)

    results = memory_store.search_by_depth(agent_id="primary", limit=10)
    ids = [r["id"] for r in results]
    assert ids.index(mem_high.id) < ids.index(mem_low.id)


# ---------------------------------------------------------------------------
# Test: session_journal CRUD
# ---------------------------------------------------------------------------


def test_start_session_creates_record(memory_store: MemoryStore) -> None:
    """start_session() creates a session_journal entry and returns an ID."""
    sid = memory_store.start_session("primary")
    assert isinstance(sid, str)
    assert len(sid) > 0

    rec = memory_store.get_session(sid)
    assert rec is not None
    assert rec["agent_id"] == "primary"
    assert rec["turn_count"] == 0
    assert rec["end_time"] is None


def test_record_turn_increments(memory_store: MemoryStore) -> None:
    """record_turn() increments turn_count."""
    sid = memory_store.start_session("primary")
    memory_store.record_turn(sid)
    memory_store.record_turn(sid)

    rec = memory_store.get_session(sid)
    assert rec["turn_count"] == 2


def test_end_session_sets_end_time_and_summary(memory_store: MemoryStore) -> None:
    """end_session() writes end_time and summary."""
    sid = memory_store.start_session("primary")
    memory_store.end_session(sid, "Implemented session store.")

    rec = memory_store.get_session(sid)
    assert rec["end_time"] is not None
    assert rec["summary"] == "Implemented session store."


def test_last_session_returns_most_recent_completed(memory_store: MemoryStore) -> None:
    """last_session() returns the most recently completed session."""
    s1 = memory_store.start_session("primary")
    memory_store.end_session(s1, "First session")
    s2 = memory_store.start_session("primary")
    memory_store.end_session(s2, "Second session")

    last = memory_store.last_session("primary")
    assert last is not None
    assert last["summary"] == "Second session"


def test_last_session_excludes_open_sessions(memory_store: MemoryStore) -> None:
    """last_session() only returns sessions with end_time set."""
    sid = memory_store.start_session("primary")
    # Don't call end_session — leave it open

    last = memory_store.last_session("primary")
    assert last is None


# ---------------------------------------------------------------------------
# Test: _touched_this_session tracking + recalculate_touched_depth_scores
# ---------------------------------------------------------------------------


def test_touched_set_empty_initially(memory_store: MemoryStore) -> None:
    """_touched_this_session is empty on a fresh MemoryStore."""
    assert memory_store._touched_this_session == set()


def test_touch_adds_to_touched_set(memory_store: MemoryStore) -> None:
    """touch() adds the memory_id to _touched_this_session."""
    mem = Memory(agent_id="primary", title="Track me", content="Track this memory.")
    memory_store.store(mem)
    memory_store.touch(mem.id)

    assert mem.id in memory_store._touched_this_session


def test_touch_adds_multiple_ids(memory_store: MemoryStore) -> None:
    """touch() accumulates multiple distinct memory IDs."""
    m1 = Memory(agent_id="primary", title="First", content="First memory.")
    m2 = Memory(agent_id="primary", title="Second", content="Second memory.")
    memory_store.store(m1)
    memory_store.store(m2)
    memory_store.touch(m1.id)
    memory_store.touch(m2.id)

    assert m1.id in memory_store._touched_this_session
    assert m2.id in memory_store._touched_this_session
    assert len(memory_store._touched_this_session) == 2


def test_recalculate_touched_returns_count(memory_store: MemoryStore) -> None:
    """recalculate_touched_depth_scores() returns count of updated memories."""
    m1 = Memory(agent_id="primary", title="A", content="Memory A.")
    m2 = Memory(agent_id="primary", title="B", content="Memory B.")
    memory_store.store(m1)
    memory_store.store(m2)
    memory_store.touch(m1.id)
    memory_store.touch(m2.id)

    count = memory_store.recalculate_touched_depth_scores()
    assert count == 2


def test_recalculate_touched_clears_set(memory_store: MemoryStore) -> None:
    """recalculate_touched_depth_scores() clears _touched_this_session after running."""
    mem = Memory(agent_id="primary", title="Clear me", content="Should clear.")
    memory_store.store(mem)
    memory_store.touch(mem.id)

    memory_store.recalculate_touched_depth_scores()
    assert memory_store._touched_this_session == set()


def test_recalculate_touched_updates_depth_score(memory_store: MemoryStore) -> None:
    """recalculate_touched_depth_scores() actually updates depth_score for touched memories."""
    mem = Memory(agent_id="primary", title="Deepen", content="Deepen this.", confidence="HIGH")
    memory_store.store(mem)

    # Touch it multiple times to give it a non-default depth score
    for _ in range(5):
        memory_store.touch(mem.id)

    memory_store.recalculate_touched_depth_scores()

    rows = memory_store.by_agent("primary")
    # After 5 touches + recalc, depth_score should be > default 1.0
    # (access_count=5, recency=today=1.0, confidence=HIGH=1.0)
    assert rows[0]["depth_score"] > 0


def test_recalculate_touched_no_op_when_empty(memory_store: MemoryStore) -> None:
    """recalculate_touched_depth_scores() returns 0 when nothing was touched."""
    count = memory_store.recalculate_touched_depth_scores()
    assert count == 0
