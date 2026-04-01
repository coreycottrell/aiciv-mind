"""
aiciv_mind.tools.context_tools — Context agency tools for aiciv-mind.

These tools give the mind agency over its own context window:
  - pin_memory: mark a memory as always-in-context at session boot
  - unpin_memory: remove a memory from always-in-context
  - introspect_context: inspect current context window state
  - get_context_snapshot: rich JSON snapshot for the context-engineer sub-mind

Registered only when context_store is provided to ToolRegistry.default().
All handlers are sync (SQLite + counter — no I/O beyond that).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

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


def _make_introspect_handler(memory_store, agent_id: str, get_session_store=None, get_message_count=None):
    """Return an introspect_context handler closed over state references."""

    def introspect_handler(tool_input: dict) -> str:
        try:
            parts: list[str] = ["## Context Introspection"]

            # Session info
            session_store = get_session_store() if get_session_store else None
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
# get_context_snapshot
# ---------------------------------------------------------------------------

_SNAPSHOT_DEFINITION: dict = {
    "name": "get_context_snapshot",
    "description": (
        "Return a rich JSON snapshot of Root's memory state for the context-engineer "
        "sub-mind. Includes total counts, pinned memories, top/bottom depth scores, "
        "and stale memories. Use before calling send_to_submind('context-engineer', ...)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


def _make_snapshot_handler(memory_store, agent_id: str, get_message_count=None):
    """Return a get_context_snapshot handler for the context engineer sub-mind."""

    def snapshot_handler(tool_input: dict) -> str:
        try:
            now = datetime.now(timezone.utc)
            stale_cutoff = "2000-01-01T00:00:00Z"  # fallback — any old date

            # Total memory count
            row = memory_store._conn.execute(
                "SELECT COUNT(*) FROM memories WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            total = row[0] if row else 0

            # Session count
            row = memory_store._conn.execute(
                "SELECT COUNT(*) FROM session_journal WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            session_count = row[0] if row else 0

            # Message count
            message_count = get_message_count() if get_message_count else 0

            # Pinned memories
            pinned_rows = memory_store.get_pinned(agent_id=agent_id)
            pinned = [
                {
                    "id": m["id"],
                    "title": m["title"],
                    "depth_score": m.get("depth_score", 0.0),
                    "access_count": m.get("access_count", 0),
                    "last_accessed_at": m.get("last_accessed_at"),
                }
                for m in pinned_rows
            ]

            # Top 10 by depth score (search_by_depth returns list[dict])
            top_rows = memory_store.search_by_depth(agent_id=agent_id, limit=10)
            top_by_depth = [
                {
                    "id": m["id"],
                    "title": m["title"],
                    "depth_score": m.get("depth_score") or 0.0,
                    "access_count": m.get("access_count") or 0,
                    "is_pinned": bool(m.get("is_pinned", 0)),
                    "memory_type": m.get("memory_type") or "learning",
                }
                for m in top_rows
            ]

            # Bottom 10 by depth score (eviction candidates) — convert to dict
            bottom_rows = [
                dict(r) for r in memory_store._conn.execute(
                    """
                    SELECT id, title, depth_score, access_count, is_pinned, memory_type,
                           last_accessed_at
                    FROM memories
                    WHERE agent_id = ?
                    ORDER BY depth_score ASC
                    LIMIT 10
                    """,
                    (agent_id,),
                ).fetchall()
            ]
            bottom_by_depth = [
                {
                    "id": m["id"],
                    "title": m["title"],
                    "depth_score": m["depth_score"] or 0.0,
                    "access_count": m["access_count"] or 0,
                    "is_pinned": bool(m["is_pinned"]),
                    "memory_type": m["memory_type"] or "learning",
                    "last_accessed_at": m["last_accessed_at"],
                }
                for m in bottom_rows
            ]

            # Stale memories: not accessed in 14+ days (or never accessed), low depth
            stale_rows = [
                dict(r) for r in memory_store._conn.execute(
                    """
                    SELECT id, title, depth_score, access_count, is_pinned, memory_type,
                           last_accessed_at, created_at
                    FROM memories
                    WHERE agent_id = ?
                      AND is_pinned = 0
                      AND (last_accessed_at IS NULL
                           OR last_accessed_at < date('now', '-14 days'))
                      AND depth_score < 0.3
                    ORDER BY depth_score ASC
                    LIMIT 20
                    """,
                    (agent_id,),
                ).fetchall()
            ]
            stale_memories = [
                {
                    "id": m["id"],
                    "title": m["title"],
                    "depth_score": m["depth_score"] or 0.0,
                    "access_count": m["access_count"] or 0,
                    "last_accessed_at": m["last_accessed_at"],
                    "memory_type": m["memory_type"] or "learning",
                }
                for m in stale_rows
            ]

            snapshot = {
                "total_memories": total,
                "session_count": session_count,
                "message_count": message_count,
                "pinned_count": len(pinned),
                "pinned": pinned,
                "top_by_depth": top_by_depth,
                "bottom_by_depth": bottom_by_depth,
                "stale_memories": stale_memories,
                "snapshot_time": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

            return json.dumps(snapshot, indent=2)

        except Exception as e:
            return f"ERROR: get_context_snapshot failed: {type(e).__name__}: {e}"

    return snapshot_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_context_tools(
    registry: ToolRegistry,
    memory_store,
    agent_id: str,
    get_session_store=None,
    get_message_count=None,
) -> None:
    """
    Register pin_memory, unpin_memory, introspect_context, and get_context_snapshot tools.

    All tools close over memory_store. introspect_context and get_context_snapshot also use
    get_session_store (a callable returning session_store) and get_message_count for richer context reporting.
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
        _make_introspect_handler(memory_store, agent_id, get_session_store=get_session_store, get_message_count=get_message_count),
        read_only=True,
    )
    registry.register(
        "get_context_snapshot",
        _SNAPSHOT_DEFINITION,
        _make_snapshot_handler(memory_store, agent_id, get_message_count),
        read_only=True,
    )
