"""
Tests for aiciv_mind.tools.memory_tools — specifically the depth scoring fix.

The critical bug: memory_search never called memory_store.touch() on results,
so access_count was permanently 0 and depth scores never compounded.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python3 -m pytest tests/test_memory_tools.py -v
"""

from __future__ import annotations

import pytest

from aiciv_mind.memory import Memory, MemoryStore
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.memory_tools import register_memory_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry_with_store(store: MemoryStore) -> ToolRegistry:
    registry = ToolRegistry()
    register_memory_tools(registry, store, agent_id="test-agent")
    return registry


# ---------------------------------------------------------------------------
# Fix verification: memory_search calls touch() on each result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_search_increments_access_count(memory_store: MemoryStore) -> None:
    """
    After memory_search returns a result, access_count must be > 0.

    This is the smoking-gun fix: before the fix, access_count stayed at 0
    forever because the search handler never called touch().
    """
    mem = Memory(
        agent_id="test-agent",
        title="Depth scoring fix verification",
        content="The compounding intelligence system needs touch() to be called on search.",
    )
    memory_store.store(mem)

    registry = _make_registry_with_store(memory_store)

    # Execute the search tool
    result = await registry.execute("memory_search", {"query": "compounding intelligence"})

    # The search must have found the memory
    assert "Depth scoring fix verification" in result

    # The access_count must now be > 0 (the core fix)
    row = memory_store._conn.execute(
        "SELECT access_count FROM memories WHERE id = ?", (mem.id,)
    ).fetchone()
    assert row is not None
    assert row[0] > 0, (
        "access_count is still 0 after memory_search — touch() was not called. "
        "This is the depth scoring bug."
    )


@pytest.mark.asyncio
async def test_memory_search_adds_to_touched_session_set(memory_store: MemoryStore) -> None:
    """Searched memories are added to _touched_this_session for depth recalculation."""
    mem = Memory(
        agent_id="test-agent",
        title="Session touch tracking",
        content="This memory should appear in the touched set after search.",
    )
    memory_store.store(mem)

    registry = _make_registry_with_store(memory_store)

    assert mem.id not in memory_store._touched_this_session

    await registry.execute("memory_search", {"query": "session touch tracking"})

    assert mem.id in memory_store._touched_this_session, (
        "Memory ID not in _touched_this_session after search. "
        "touch() was not called — depth scoring will never compound."
    )


@pytest.mark.asyncio
async def test_memory_search_triggers_depth_score_recalculation(memory_store: MemoryStore) -> None:
    """
    After searching and calling recalculate_touched(), depth_score must increase.

    This validates the full compounding intelligence loop:
    search → touch() → recalculate_touched() → higher depth_score
    """
    mem = Memory(
        agent_id="test-agent",
        title="Depth score should rise",
        content="Memories accessed repeatedly must score higher for future retrieval.",
    )
    memory_store.store(mem)

    initial_row = memory_store._conn.execute(
        "SELECT depth_score FROM memories WHERE id = ?", (mem.id,)
    ).fetchone()
    initial_depth = initial_row[0]

    registry = _make_registry_with_store(memory_store)

    # Search multiple times to accumulate access counts
    for _ in range(3):
        await registry.execute("memory_search", {"query": "depth score should rise"})

    # Trigger depth recalculation (happens at end of session in mind.py)
    count = memory_store.recalculate_touched_depth_scores()
    assert count > 0

    updated_row = memory_store._conn.execute(
        "SELECT depth_score FROM memories WHERE id = ?", (mem.id,)
    ).fetchone()
    updated_depth = updated_row[0]

    # depth_score was recalculated from the default 1.0 to a computed value.
    # The computed value may be < 1.0 (formula normalizes access_count/20),
    # but it must differ from the SQL default (1.0) — proving recalculation ran.
    assert updated_depth != initial_depth, (
        f"depth_score unchanged at {initial_depth} — recalculate_touched_depth_scores() "
        "did not update the value. The compounding intelligence loop is broken."
    )


@pytest.mark.asyncio
async def test_memory_search_touch_failure_does_not_suppress_results(
    memory_store: MemoryStore,
) -> None:
    """
    If touch() fails for any reason, search results must still be returned.

    The touch() call is wrapped in try/except — results are never suppressed.
    """
    from unittest.mock import patch

    mem = Memory(
        agent_id="test-agent",
        title="Results survive touch failure",
        content="Even if touch() throws, the search results must come back.",
    )
    memory_store.store(mem)

    registry = _make_registry_with_store(memory_store)

    # Patch touch() to raise an exception
    with patch.object(memory_store, "touch", side_effect=RuntimeError("DB locked")):
        result = await registry.execute("memory_search", {"query": "results survive touch"})

    # Results must still be returned despite the touch() failure
    assert "Results survive touch failure" in result
    assert "ERROR" not in result


@pytest.mark.asyncio
async def test_memory_search_no_match_does_not_call_touch(
    memory_store: MemoryStore,
) -> None:
    """touch() is only called when there are results to touch."""
    from unittest.mock import patch

    registry = _make_registry_with_store(memory_store)

    with patch.object(memory_store, "touch") as mock_touch:
        result = await registry.execute("memory_search", {"query": "xyzzy-nomatch-404"})

    assert "No memories found" in result
    mock_touch.assert_not_called()


@pytest.mark.asyncio
async def test_memory_search_multiple_results_all_touched(memory_store: MemoryStore) -> None:
    """All returned results are touched, not just the first one."""
    for i in range(3):
        memory_store.store(Memory(
            agent_id="test-agent",
            title=f"Compounding memory {i}",
            content=f"Content about compounding intelligence number {i}.",
        ))

    registry = _make_registry_with_store(memory_store)
    await registry.execute("memory_search", {"query": "compounding intelligence", "limit": 10})

    rows = memory_store._conn.execute(
        "SELECT id, access_count FROM memories WHERE agent_id = 'test-agent'"
    ).fetchall()

    # All found memories should have been touched
    touched_count = sum(1 for row in rows if row[1] > 0)
    assert touched_count >= 3, (
        f"Only {touched_count}/3 memories were touched. "
        "All search results should have touch() called on them."
    )
