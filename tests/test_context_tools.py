"""
Tests for aiciv_mind.tools.context_tools — pin_memory, unpin_memory, introspect_context.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_context_tools.py -v
"""

from __future__ import annotations

import pytest

from aiciv_mind.memory import Memory, MemoryStore
from aiciv_mind.session_store import SessionStore
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.context_tools import register_context_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_store():
    store = MemoryStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def sample_memory(memory_store):
    """Store a sample memory and return its ID."""
    mem = Memory(
        agent_id="primary",
        title="Critical deployment fact",
        content="The HUB runs on port 8900.",
        memory_type="learning",
        domain="infrastructure",
        tags=["hub", "deploy"],
    )
    return memory_store.store(mem)


@pytest.fixture
def registry_with_context(memory_store, sample_memory):
    """Build a ToolRegistry with context tools registered."""
    session_store = SessionStore(memory_store, agent_id="primary")
    session_store.boot()

    msg_count = [3]  # mutable counter for testing

    def get_msg_count():
        return msg_count[0]

    registry = ToolRegistry()
    register_context_tools(
        registry,
        memory_store=memory_store,
        agent_id="primary",
        session_store=session_store,
        get_message_count=get_msg_count,
    )
    return registry, memory_store, sample_memory, msg_count


# ---------------------------------------------------------------------------
# pin_memory tests
# ---------------------------------------------------------------------------


class TestPinMemory:
    def test_pin_calls_store(self, registry_with_context):
        registry, store, mem_id, _ = registry_with_context
        handler = registry._handlers["pin_memory"]

        result = handler({"memory_id": mem_id})
        assert f"Memory {mem_id} pinned" in result
        assert "will load at every session boot" in result

        # Verify it was actually pinned in the store
        pinned = store.get_pinned(agent_id="primary")
        assert len(pinned) == 1
        assert pinned[0]["id"] == mem_id

    def test_pin_empty_id_returns_error(self, registry_with_context):
        registry, _, _, _ = registry_with_context
        handler = registry._handlers["pin_memory"]

        result = handler({"memory_id": ""})
        assert result.startswith("ERROR")

    def test_pin_missing_id_returns_error(self, registry_with_context):
        registry, _, _, _ = registry_with_context
        handler = registry._handlers["pin_memory"]

        result = handler({})
        assert result.startswith("ERROR")

    def test_pin_nonexistent_id_succeeds_silently(self, memory_store):
        """pin() on a non-existent ID is a no-op UPDATE (0 rows affected), not an error."""
        registry = ToolRegistry()
        register_context_tools(registry, memory_store=memory_store, agent_id="primary")
        handler = registry._handlers["pin_memory"]

        # SQLite UPDATE on non-existent row is a no-op, not an exception
        result = handler({"memory_id": "nonexistent-uuid"})
        assert "pinned" in result


# ---------------------------------------------------------------------------
# unpin_memory tests
# ---------------------------------------------------------------------------


class TestUnpinMemory:
    def test_unpin_calls_store(self, registry_with_context):
        registry, store, mem_id, _ = registry_with_context

        # First pin it
        store.pin(mem_id)
        assert len(store.get_pinned(agent_id="primary")) == 1

        # Then unpin via tool
        handler = registry._handlers["unpin_memory"]
        result = handler({"memory_id": mem_id})
        assert f"Memory {mem_id} unpinned" in result

        # Verify it was unpinned
        assert len(store.get_pinned(agent_id="primary")) == 0

    def test_unpin_empty_id_returns_error(self, registry_with_context):
        registry, _, _, _ = registry_with_context
        handler = registry._handlers["unpin_memory"]

        result = handler({"memory_id": ""})
        assert result.startswith("ERROR")

    def test_unpin_missing_id_returns_error(self, registry_with_context):
        registry, _, _, _ = registry_with_context
        handler = registry._handlers["unpin_memory"]

        result = handler({})
        assert result.startswith("ERROR")


# ---------------------------------------------------------------------------
# introspect_context tests
# ---------------------------------------------------------------------------


class TestIntrospectContext:
    def test_returns_formatted_output(self, registry_with_context):
        registry, store, mem_id, msg_count = registry_with_context
        handler = registry._handlers["introspect_context"]

        result = handler({})
        assert "Context Introspection" in result
        assert "Session ID:" in result
        assert "Message count:** 3" in result
        assert "Pinned memories:** 0" in result

    def test_shows_session_id(self, registry_with_context):
        registry, _, _, _ = registry_with_context
        handler = registry._handlers["introspect_context"]

        result = handler({})
        # Session ID should be present (from boot)
        assert "Session ID:" in result
        assert "(unknown)" not in result

    def test_shows_pinned_count(self, registry_with_context):
        registry, store, mem_id, _ = registry_with_context
        store.pin(mem_id)

        handler = registry._handlers["introspect_context"]
        result = handler({})
        assert "Pinned memories:** 1" in result

    def test_shows_top_memories(self, registry_with_context):
        registry, store, mem_id, _ = registry_with_context

        # Touch the memory to give it a non-zero depth score
        store.touch(mem_id)
        store.update_depth_score(mem_id)

        handler = registry._handlers["introspect_context"]
        result = handler({})
        assert "Top memories by depth score:" in result
        assert "Critical deployment fact" in result

    def test_message_count_reflects_callable(self, registry_with_context):
        registry, _, _, msg_count = registry_with_context
        handler = registry._handlers["introspect_context"]

        msg_count[0] = 42
        result = handler({})
        assert "Message count:** 42" in result

    def test_no_session_store(self, memory_store):
        """introspect_context works even without a session_store."""
        registry = ToolRegistry()
        register_context_tools(
            registry,
            memory_store=memory_store,
            agent_id="primary",
            session_store=None,
            get_message_count=None,
        )
        handler = registry._handlers["introspect_context"]
        result = handler({})
        assert "(unknown)" in result
        assert "Message count:** 0" in result


# ---------------------------------------------------------------------------
# ToolRegistry integration tests
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    def test_context_tools_registered_when_context_store_provided(self):
        store = MemoryStore(":memory:")
        try:
            registry = ToolRegistry.default(
                memory_store=store,
                agent_id="primary",
                context_store=store,
            )
            names = registry.names()
            assert "pin_memory" in names
            assert "unpin_memory" in names
            assert "introspect_context" in names
        finally:
            store.close()

    def test_context_tools_not_registered_when_context_store_is_none(self):
        store = MemoryStore(":memory:")
        try:
            registry = ToolRegistry.default(
                memory_store=store,
                agent_id="primary",
                context_store=None,
            )
            names = registry.names()
            assert "pin_memory" not in names
            assert "unpin_memory" not in names
            assert "introspect_context" not in names
        finally:
            store.close()

    def test_context_tools_definitions_have_required_keys(self):
        store = MemoryStore(":memory:")
        try:
            registry = ToolRegistry.default(
                memory_store=store,
                agent_id="primary",
                context_store=store,
            )
            context_tool_names = {"pin_memory", "unpin_memory", "introspect_context"}
            for tool_def in registry.build_anthropic_tools():
                if tool_def["name"] in context_tool_names:
                    assert "name" in tool_def
                    assert "description" in tool_def
                    assert "input_schema" in tool_def
                    schema = tool_def["input_schema"]
                    assert schema.get("type") == "object"
                    assert "properties" in schema
        finally:
            store.close()

    def test_read_only_flags(self):
        store = MemoryStore(":memory:")
        try:
            registry = ToolRegistry.default(
                memory_store=store,
                agent_id="primary",
                context_store=store,
            )
            assert registry.is_read_only("pin_memory") is False
            assert registry.is_read_only("unpin_memory") is False
            assert registry.is_read_only("introspect_context") is True
        finally:
            store.close()
