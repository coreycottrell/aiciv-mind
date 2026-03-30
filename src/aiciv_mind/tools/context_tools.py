"""
aiciv_mind.tools.context_tools — Context agency tools for aiciv-mind.

These tools give the mind agency over its own context window:
  - pin_memory: mark a memory as always-in-context at session boot
  - unpin_memory: remove a memory from always-in-context
  - introspect_context: inspect current context window state

Registered only when context_store is provided to ToolRegistry.default().
All handlers are sync (SQLite + counter — no I/O beyond that).
"""

from __future__ import annotations

from aiciv_mind.tools import ToolRegistry


# ---------------------------------------------------------------------------
# pin_memory
# ---------------------------------------------------------------------------

_PIN_DEFINITION: dict = {
    "name": "pin_memory",
    "description": (
        "Pin a memory to always be included in context at session boot. "
        "Use for critical facts you always need."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "memory_id": {
                "type": "string",
                "description": "The UUID of the memory to pin",
            },
        },
        "required": ["memory_id"],
    },
}


def _make_pin_handler(memory_store):
    """Return a pin_memory handler closed over the given MemoryStore."""

    def pin_handler(tool_input: dict) -> str:
        memory_id: str = tool_input.get("memory_id", "").strip()
        if not memory_id:
            return "ERROR: No memory_id provided"

        try:
            memory_store.pin(memory_id)
            return f"Memory {memory_id} pinned — will load at every session boot"
        except Exception as e:
            return f"ERROR: Failed to pin memory: {type(e).__name__}: {e}"

    return pin_handler


# ---------------------------------------------------------------------------
# unpin_memory
# ---------------------------------------------------------------------------

_UNPIN_DEFINITION: dict = {
    "name": "unpin_memory",
    "description": (
        "Remove a pinned memory from always-in-context. "
        "Use when a memory is no longer critical."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "memory_id": {
                "type": "string",
                "description": "The UUID of the memory to unpin",
            },
        },
        "required": ["memory_id"],
    },
}


def _make_unpin_handler(memory_store):
    """Return an unpin_memory handler closed over the given MemoryStore."""

    def unpin_handler(tool_input: dict) -> str:
        memory_id: str = tool_input.get("memory_id", "").strip()
        if not memory_id:
            return "ERROR: No memory_id provided"

        try:
            memory_store.unpin(memory_id)
            return f"Memory {memory_id} unpinned"
        except Exception as e:
            return f"ERROR: Failed to unpin memory: {type(e).__name__}: {e}"

    return unpin_handler


# ---------------------------------------------------------------------------
# introspect_context
# ---------------------------------------------------------------------------

_INTROSPECT_DEFINITION: dict = {
    "name": "introspect_context",
    "description": (
        "Inspect current context window state — session info, message count, "
        "pinned memories, and top memories by depth score."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


def _make_introspect_handler(memory_store, agent_id: str, session_store=None, get_message_count=None):
    """Return an introspect_context handler closed over state references."""

    def introspect_handler(tool_input: dict) -> str:
        try:
            parts: list[str] = ["## Context Introspection"]

            # Session info
            session_id = session_store.session_id if session_store else None
            parts.append(f"**Session ID:** {session_id or '(unknown)'}")

            # Message count
            msg_count = get_message_count() if get_message_count else 0
            parts.append(f"**Message count:** {msg_count}")

            # Pinned memories
            try:
                pinned = memory_store.get_pinned(agent_id=agent_id)
            except Exception:
                pinned = []
            parts.append(f"**Pinned memories:** {len(pinned)}")

            # Top 5 by depth_score
            try:
                top = memory_store.search_by_depth(agent_id=agent_id, limit=5)
            except Exception:
                top = []

            if top:
                parts.append("\n**Top memories by depth score:**")
                for i, mem in enumerate(top, 1):
                    title = mem.get("title", "(untitled)")
                    score = mem.get("depth_score", 0.0)
                    mem_id = mem.get("id", "?")
                    parts.append(f"  {i}. [{score:.4f}] {title} (id: {mem_id})")
            else:
                parts.append("\n**Top memories by depth score:** (none)")

            return "\n".join(parts)
        except Exception as e:
            return f"ERROR: Introspection failed: {type(e).__name__}: {e}"

    return introspect_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_context_tools(
    registry: ToolRegistry,
    memory_store,
    agent_id: str,
    session_store=None,
    get_message_count=None,
) -> None:
    """
    Register pin_memory, unpin_memory, and introspect_context tools.

    All tools close over memory_store. introspect_context also uses
    session_store and get_message_count for richer context reporting.
    """
    registry.register(
        "pin_memory",
        _PIN_DEFINITION,
        _make_pin_handler(memory_store),
        read_only=False,
    )
    registry.register(
        "unpin_memory",
        _UNPIN_DEFINITION,
        _make_unpin_handler(memory_store),
        read_only=False,
    )
    registry.register(
        "introspect_context",
        _INTROSPECT_DEFINITION,
        _make_introspect_handler(memory_store, agent_id, session_store, get_message_count),
        read_only=True,
    )
