"""
aiciv_mind.session_store — Session lifecycle for aiciv-mind.

Manages boot (identity load, last-session handoff inject) and shutdown
(session summary write, handoff memory store).  SessionStore is the
bridge between raw MemoryStore CRUD and Mind's context-loading needs.

The acceptance contract:
  1. Session runs.  Mind does work.
  2. Process killed.
  3. New session starts.  Mind is asked "what were you doing yesterday?"
  4. Mind answers correctly — because BootContext injected the handoff.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from aiciv_mind.memory import Memory, MemoryStore


# ---------------------------------------------------------------------------
# BootContext — what a Mind knows before its first turn
# ---------------------------------------------------------------------------


@dataclass
class BootContext:
    """Everything the mind needs injected into its system prompt at startup."""

    session_id: str
    session_count: int
    agent_id: str

    # Always in context — who this mind IS
    identity_memories: list[dict[str, Any]] = field(default_factory=list)

    # What happened last time
    handoff_memory: dict[str, Any] | None = None

    # Unresolved threads from prior sessions
    active_threads: list[dict[str, Any]] = field(default_factory=list)

    # is_pinned=True memories — always loaded
    pinned_memories: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class SessionStore:
    """
    Owns the session lifecycle: boot, record turns, write handoff, shutdown.

    Usage:
        store = SessionStore(memory, agent_id="primary")
        boot = store.boot()       # call once at startup
        # ... pass boot to ContextManager for system prompt injection ...
        store.record_turn()       # call after each turn
        store.shutdown(messages)  # call at process exit
    """

    def __init__(self, memory: MemoryStore, agent_id: str) -> None:
        self._memory = memory
        self._agent_id = agent_id
        self._session_id: str | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def boot(self) -> BootContext:
        """
        Load boot context from memory and start a new session journal entry.

        Searches for:
        - identity memories (memory_type="identity")
        - last session's handoff (memory_type="handoff")
        - unresolved threads (memory_type="handoff", no end marker)
        - pinned memories
        """
        # Start session record
        self._session_id = self._memory.start_session(self._agent_id)

        # Clean up orphaned sessions (turn_count=0, end_time=NULL, not this session)
        try:
            self._memory._conn.execute(
                """
                UPDATE session_journal
                   SET end_time = datetime('now'),
                       summary  = 'Orphaned session — closed at next boot'
                 WHERE agent_id = ?
                   AND end_time IS NULL
                   AND session_id != ?
                """,
                (self._agent_id, self._session_id),
            )
            self._memory._conn.commit()
        except Exception:
            pass  # never crash on cleanup

        # Count how many sessions this agent has had
        last = self._memory.last_session(self._agent_id)

        # Identity anchors — who am I? (search by type, not keywords)
        identity = self._memory.by_type(
            agent_id=self._agent_id,
            memory_type="identity",
            limit=5,
        )

        # Last session's handoff (most recent, by type)
        handoff: dict[str, Any] | None = None
        if last:
            handoffs = self._memory.by_type(
                agent_id=self._agent_id,
                memory_type="handoff",
                limit=1,
            )
            handoff = handoffs[0] if handoffs else None

        # Pinned memories
        pinned = self._memory.get_pinned(agent_id=self._agent_id)

        return BootContext(
            session_id=self._session_id,
            session_count=self._count_sessions(),
            agent_id=self._agent_id,
            identity_memories=identity,
            handoff_memory=handoff,
            active_threads=[],
            pinned_memories=pinned,
        )

    def _count_sessions(self) -> int:
        """Count completed sessions for this agent."""
        try:
            row = self._memory._conn.execute(
                "SELECT COUNT(*) FROM session_journal WHERE agent_id = ? AND end_time IS NOT NULL",
                (self._agent_id,),
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # During session
    # ------------------------------------------------------------------

    def record_turn(self, topic: str | None = None) -> None:
        """Increment turn count; optionally tag the domain being worked on."""
        if self._session_id:
            self._memory.record_turn(self._session_id, topic=topic)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self, messages: list[dict[str, Any]], cache_stats: dict | None = None) -> None:
        """
        Write the session summary and store a handoff memory.

        Called at process exit (finally block in main.py).
        Extracts the last meaningful assistant response as the session summary.
        """
        if not self._session_id:
            return

        # Pull turn count from journal
        session_rec = self._memory.get_session(self._session_id)
        turn_count = session_rec.get("turn_count", 0) if session_rec else 0
        topics = []
        if session_rec:
            import json
            try:
                topics = json.loads(session_rec.get("topics", "[]"))
            except Exception:
                topics = []

        # Extract last assistant text
        last_text = self._extract_last_assistant_text(messages)

        # Build summary
        topics_str = ", ".join(topics) if topics else "general"

        cache_str = ""
        if cache_stats and cache_stats.get("cache_hits", 0) > 0:
            hit_rate = cache_stats.get("hit_rate", 0.0)
            cached_tokens = cache_stats.get("cached_tokens", 0)
            cache_str = f" Cache hit rate: {hit_rate:.0%} ({cached_tokens} cached tokens)."

        summary = (
            f"Session {self._session_id} completed. "
            f"{turn_count} turn(s). "
            f"Topics: {topics_str}.{cache_str} "
            f"Last response: {last_text[:400]}"
        )

        # Write to session_journal
        self._memory.end_session(self._session_id, summary)

        # Write handoff memory — this is what the NEXT session will load at boot
        handoff = Memory(
            agent_id=self._agent_id,
            title=f"Session handoff — {self._session_id}",
            content=(
                f"## What I was doing in session {self._session_id}\n\n"
                f"**Turns:** {turn_count}\n"
                f"**Topics:** {topics_str}\n\n"
                f"**Last thing I said:**\n{last_text[:600]}"
            ),
            memory_type="handoff",
            session_id=self._session_id,
            domain="session",
            confidence="HIGH",
            tags=["handoff", "session", self._session_id],
        )
        self._memory.store(handoff)

    @staticmethod
    def _extract_last_assistant_text(messages: list[dict[str, Any]]) -> str:
        """Extract the last non-empty text from assistant messages."""
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                for block in reversed(content):
                    if hasattr(block, "text") and block.text.strip():
                        return block.text.strip()
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text:
                            return text
        return "(no text recorded)"
