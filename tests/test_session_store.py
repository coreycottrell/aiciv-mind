"""
Tests for aiciv_mind.session_store — SessionStore + BootContext lifecycle.
"""

from __future__ import annotations

import pytest

from aiciv_mind.memory import Memory, MemoryStore
from aiciv_mind.session_store import BootContext, SessionStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_store():
    store = MemoryStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def session_store(memory_store):
    return SessionStore(memory_store, agent_id="primary")


# ---------------------------------------------------------------------------
# boot() — creates session, returns BootContext
# ---------------------------------------------------------------------------


def test_boot_creates_session_id(session_store, memory_store):
    """boot() starts a session and returns a non-empty session_id."""
    boot = session_store.boot()
    assert isinstance(boot.session_id, str)
    assert len(boot.session_id) > 0


def test_boot_returns_boot_context(session_store):
    """boot() returns a BootContext dataclass."""
    boot = session_store.boot()
    assert isinstance(boot, BootContext)
    assert boot.agent_id == "primary"


def test_boot_session_count_zero_on_first_boot(session_store):
    """First boot: session_count is 0 (no completed prior sessions)."""
    boot = session_store.boot()
    assert boot.session_count == 0


def test_boot_no_identity_memories_on_empty_db(session_store):
    """No identity memories means empty list, not error."""
    boot = session_store.boot()
    assert boot.identity_memories == []


def test_boot_no_handoff_on_first_run(session_store):
    """First boot: no handoff memory."""
    boot = session_store.boot()
    assert boot.handoff_memory is None


def test_boot_loads_identity_memories(session_store, memory_store):
    """boot() returns identity memories if they exist."""
    memory_store.store(Memory(
        agent_id="primary",
        title="Primary conductor identity",
        content="I am the conductor of conductors for A-C-Gee.",
        memory_type="identity",
    ))
    boot = session_store.boot()
    assert len(boot.identity_memories) >= 1
    assert any("conductor" in m["content"] for m in boot.identity_memories)


def test_boot_loads_pinned_memories(session_store, memory_store):
    """boot() returns pinned memories."""
    mem_id = memory_store.store(Memory(
        agent_id="primary",
        title="Always-on context",
        content="HUB is at http://87.99.131.49:8900",
        memory_type="learning",
    ))
    memory_store.pin(mem_id)

    boot = session_store.boot()
    assert len(boot.pinned_memories) == 1
    assert boot.pinned_memories[0]["id"] == mem_id


# ---------------------------------------------------------------------------
# record_turn()
# ---------------------------------------------------------------------------


def test_record_turn_increments_count(session_store, memory_store):
    """record_turn() increments turn_count in session_journal."""
    boot = session_store.boot()
    session_store.record_turn()
    session_store.record_turn()
    session_store.record_turn()

    rec = memory_store.get_session(boot.session_id)
    assert rec is not None
    assert rec["turn_count"] == 3


def test_record_turn_with_topic(session_store, memory_store):
    """record_turn(topic=) appends unique topic to the topics list."""
    import json

    boot = session_store.boot()
    session_store.record_turn(topic="context-architecture")
    session_store.record_turn(topic="memory-schema")
    session_store.record_turn(topic="context-architecture")  # duplicate

    rec = memory_store.get_session(boot.session_id)
    topics = json.loads(rec["topics"])
    assert "context-architecture" in topics
    assert "memory-schema" in topics
    assert topics.count("context-architecture") == 1  # deduplicated


# ---------------------------------------------------------------------------
# shutdown() — writes handoff memory
# ---------------------------------------------------------------------------


def test_shutdown_writes_handoff_memory(session_store, memory_store):
    """shutdown() stores a memory_type=handoff memory."""
    session_store.boot()
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "I am working on the context architecture."},
    ]
    session_store.shutdown(messages)

    handoffs = memory_store.search(
        query="handoff session",
        agent_id="primary",
        memory_type="handoff",
    )
    assert len(handoffs) >= 1


def test_shutdown_captures_last_assistant_text(session_store, memory_store):
    """shutdown() captures the last assistant message in the handoff."""
    session_store.boot()
    messages = [
        {"role": "user", "content": "what are you doing?"},
        {"role": "assistant", "content": "I am building the session store module."},
    ]
    session_store.shutdown(messages)

    handoffs = memory_store.search(
        query="session store module",
        agent_id="primary",
        memory_type="handoff",
    )
    assert len(handoffs) >= 1
    assert "session store" in handoffs[0]["content"]


def test_shutdown_ends_session_journal(session_store, memory_store):
    """shutdown() writes end_time to the session_journal entry."""
    boot = session_store.boot()
    session_store.shutdown([])

    rec = memory_store.last_session("primary")
    assert rec is not None
    assert rec["end_time"] is not None


def test_shutdown_without_boot_does_not_crash(session_store):
    """Calling shutdown() before boot() is a no-op."""
    session_store.shutdown([])  # should not raise


# ---------------------------------------------------------------------------
# Full lifecycle: boot → work → shutdown → new boot loads handoff
# ---------------------------------------------------------------------------


def test_handoff_persists_across_sessions(memory_store):
    """Session 1 shutdown → Session 2 boot loads the handoff memory."""
    # Session 1
    s1 = SessionStore(memory_store, agent_id="primary")
    s1.boot()
    s1.record_turn(topic="context-architecture")
    messages = [
        {"role": "user", "content": "implement session store"},
        {"role": "assistant", "content": "I implemented session_store.py with boot and shutdown."},
    ]
    s1.shutdown(messages)

    # Session 2
    s2 = SessionStore(memory_store, agent_id="primary")
    boot2 = s2.boot()

    assert boot2.session_count == 1  # one completed prior session
    assert boot2.handoff_memory is not None
    assert "session_store" in boot2.handoff_memory["content"]


# ---------------------------------------------------------------------------
# ContextManager: boot context formatting
# ---------------------------------------------------------------------------


def test_context_manager_formats_handoff(memory_store):
    """ContextManager.format_boot_context includes the handoff content."""
    from aiciv_mind.context_manager import ContextManager

    # Setup: run one session and shut down
    s1 = SessionStore(memory_store, agent_id="primary")
    s1.boot()
    s1.shutdown([
        {"role": "assistant", "content": "Built the CONTEXT-ARCHITECTURE.md document."}
    ])

    # New session boot
    s2 = SessionStore(memory_store, agent_id="primary")
    boot = s2.boot()

    ctx = ContextManager(max_context_memories=10, model_max_tokens=4096)
    result = ctx.format_boot_context(boot)

    assert "Previous Session Handoff" in result
    assert "CONTEXT-ARCHITECTURE" in result


def test_context_manager_empty_on_fresh_db(memory_store):
    """format_boot_context returns empty string when there's nothing to inject."""
    from aiciv_mind.context_manager import ContextManager

    s = SessionStore(memory_store, agent_id="primary")
    boot = s.boot()

    ctx = ContextManager()
    result = ctx.format_boot_context(boot)
    # Only session header — no identity, no handoff → returns ""
    assert result == ""


def test_context_manager_formats_search_results():
    """format_search_results returns formatted memory context."""
    from aiciv_mind.context_manager import ContextManager

    ctx = ContextManager()
    results = [
        {"title": "FTS5 fix", "content": "Strip punctuation before FTS5 MATCH."},
        {"title": "LiteLLM key", "content": "Master key is sk-aiciv-dev-masterkey-changeme."},
    ]
    formatted = ctx.format_search_results(results)
    assert "FTS5 fix" in formatted
    assert "LiteLLM key" in formatted
    assert "Relevant memories" in formatted


def test_context_manager_empty_results_returns_empty():
    """format_search_results returns '' when no results."""
    from aiciv_mind.context_manager import ContextManager

    ctx = ContextManager()
    assert ctx.format_search_results([]) == ""


# ---------------------------------------------------------------------------
# shutdown() with cache_stats
# ---------------------------------------------------------------------------


def test_shutdown_without_cache_stats_backwards_compatible(session_store, memory_store):
    """shutdown() without cache_stats still works (backward compatibility)."""
    session_store.boot()
    messages = [
        {"role": "assistant", "content": "I did some work."},
    ]
    session_store.shutdown(messages)

    last = memory_store.last_session("primary")
    assert last is not None
    assert "Cache hit rate" not in last["summary"]


def test_shutdown_with_cache_stats_includes_hit_rate(session_store, memory_store):
    """shutdown() with cache_stats includes hit rate in the session summary."""
    session_store.boot()
    messages = [
        {"role": "assistant", "content": "Used caching effectively."},
    ]
    cache_stats = {
        "cache_hits": 5,
        "cache_writes": 2,
        "cached_tokens": 1200,
        "total_input_tokens": 3000,
        "hit_rate": 0.71,
    }
    session_store.shutdown(messages, cache_stats=cache_stats)

    last = memory_store.last_session("primary")
    assert last is not None
    assert "Cache hit rate: 71%" in last["summary"]
    assert "1200 cached tokens" in last["summary"]


def test_shutdown_with_zero_cache_hits_no_cache_string(session_store, memory_store):
    """shutdown() with cache_stats but zero hits does not include cache string."""
    session_store.boot()
    messages = [
        {"role": "assistant", "content": "No caching."},
    ]
    cache_stats = {
        "cache_hits": 0,
        "cache_writes": 3,
        "cached_tokens": 0,
        "total_input_tokens": 500,
        "hit_rate": 0.0,
    }
    session_store.shutdown(messages, cache_stats=cache_stats)

    last = memory_store.last_session("primary")
    assert last is not None
    assert "Cache hit rate" not in last["summary"]
