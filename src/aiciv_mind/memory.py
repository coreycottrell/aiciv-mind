"""
aiciv_mind.memory — SQLite + FTS5 memory store.

Memory is not bolted on — it IS the architecture. Every mind has a MemoryStore.
The store persists learnings, decisions, errors, and observations across sessions
and surfaces them via full-text search (BM25 ranking via FTS5).

Design notes:
- db_path=":memory:" is supported for in-process tests.
- WAL mode keeps concurrent readers/writers from blocking each other.
- FTS5 triggers keep the virtual table in sync automatically.
- Tags live in a separate table for efficient per-tag lookup.
- v0.1.1: depth scoring (access_count, recency, pinning, human_endorsed),
  session_journal for lifecycle tracking.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Memory:
    """A single unit of stored intelligence."""

    agent_id: str
    title: str
    content: str
    domain: str = "general"
    memory_type: str = "learning"  # learning | decision | error | handoff | observation
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    source_path: str | None = None
    confidence: str = "MEDIUM"  # HIGH | MEDIUM | LOW
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    domain      TEXT NOT NULL DEFAULT 'general',
    session_id  TEXT,
    memory_type TEXT NOT NULL DEFAULT 'learning',
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    source_path TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    confidence  TEXT NOT NULL DEFAULT 'MEDIUM',
    tags        TEXT NOT NULL DEFAULT '[]'
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    title,
    content,
    agent_id   UNINDEXED,
    domain     UNINDEXED,
    memory_type UNINDEXED,
    content='memories',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, title, content, agent_id, domain, memory_type)
    VALUES (new.rowid, new.title, new.content, new.agent_id, new.domain, new.memory_type);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, content, agent_id, domain, memory_type)
    VALUES ('delete', old.rowid, old.title, old.content, old.agent_id, old.domain, old.memory_type);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, content, agent_id, domain, memory_type)
    VALUES ('delete', old.rowid, old.title, old.content, old.agent_id, old.domain, old.memory_type);
    INSERT INTO memories_fts(rowid, title, content, agent_id, domain, memory_type)
    VALUES (new.rowid, new.title, new.content, new.agent_id, new.domain, new.memory_type);
END;

CREATE INDEX IF NOT EXISTS idx_memories_agent   ON memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_memories_domain  ON memories(domain);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);

CREATE TABLE IF NOT EXISTS memory_tags (
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    tag       TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_tags_tag ON memory_tags(tag);

CREATE TABLE IF NOT EXISTS session_journal (
    session_id     TEXT PRIMARY KEY,
    agent_id       TEXT NOT NULL,
    start_time     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    end_time       TEXT,
    turn_count     INTEGER NOT NULL DEFAULT 0,
    topics         TEXT NOT NULL DEFAULT '[]',
    summary        TEXT,
    identity_ver   INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_session_agent ON session_journal(agent_id, start_time DESC);

CREATE TABLE IF NOT EXISTS skills (
    skill_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    domain          TEXT NOT NULL DEFAULT 'general',
    file_path       TEXT NOT NULL,
    usage_count     INTEGER NOT NULL DEFAULT 0,
    last_used_at    TEXT,
    effectiveness   REAL NOT NULL DEFAULT 0.5,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS agent_registry (
    agent_id        TEXT PRIMARY KEY,
    manifest_path   TEXT NOT NULL,
    display_name    TEXT,
    role            TEXT,
    domain          TEXT DEFAULT 'general',
    spawn_count     INTEGER NOT NULL DEFAULT 0,
    last_active_at  TEXT,
    last_session_id TEXT,
    registered_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""

# Columns added in v0.1.1 — applied via _migrate_schema() for existing DBs.
_V011_COLUMNS: list[tuple[str, str]] = [
    ("access_count",     "INTEGER NOT NULL DEFAULT 0"),
    ("last_accessed_at", "TEXT"),
    ("depth_score",      "REAL NOT NULL DEFAULT 1.0"),
    ("is_pinned",        "INTEGER NOT NULL DEFAULT 0"),
    ("human_endorsed",   "INTEGER NOT NULL DEFAULT 0"),
]


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class MemoryStore:
    """
    Persistent memory store backed by SQLite with FTS5 full-text search.

    Usage:
        store = MemoryStore("/path/to/memory.db")
        mem = Memory(agent_id="primary", title="...", content="...")
        store.store(mem)
        results = store.search("pattern discovery")
        store.close()

    Pass db_path=":memory:" for in-process tests — each instance is isolated.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        self._touched_this_session: set[str] = set()  # track for depth score update

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create all tables, virtual tables, triggers, and indexes."""
        # executescript auto-commits, so we commit the pragma changes first.
        self._conn.commit()
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Add v0.1.1 columns to an existing memories table if missing."""
        existing = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(memories)")
        }
        for col_name, col_def in _V011_COLUMNS:
            if col_name not in existing:
                self._conn.execute(
                    f"ALTER TABLE memories ADD COLUMN {col_name} {col_def}"
                )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(self, memory: Memory) -> str:
        """
        Persist a Memory.

        Inserts the memory row, then inserts each tag into memory_tags.
        Returns the memory's UUID string.
        """
        tags_json = json.dumps(memory.tags)
        self._conn.execute(
            """
            INSERT INTO memories
                (id, agent_id, domain, session_id, memory_type, title, content,
                 source_path, confidence, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.agent_id,
                memory.domain,
                memory.session_id,
                memory.memory_type,
                memory.title,
                memory.content,
                memory.source_path,
                memory.confidence,
                tags_json,
            ),
        )
        for tag in memory.tags:
            self._conn.execute(
                "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                (memory.id, tag),
            )
        self._conn.commit()
        return memory.id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        agent_id: str | None = None,
        domain: str | None = None,
        memory_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Full-text search over memories using FTS5 BM25 ranking.

        Filters by agent_id, domain, and/or memory_type when provided.
        Results are ordered by relevance (rank, lower BM25 = better match).
        """
        # FTS5 MATCH cannot handle punctuation — strip to words only.
        clean_query = " ".join(re.findall(r"\w+", query))
        if not clean_query:
            return []

        filters: list[str] = []
        params: list[Any] = [clean_query]

        if agent_id is not None:
            filters.append("m.agent_id = ?")
            params.append(agent_id)
        if domain is not None:
            filters.append("m.domain = ?")
            params.append(domain)
        if memory_type is not None:
            filters.append("m.memory_type = ?")
            params.append(memory_type)

        where_clause = ""
        if filters:
            where_clause = "AND " + " AND ".join(filters)

        params.append(limit)

        sql = f"""
            SELECT m.*
            FROM memories m
            JOIN memories_fts fts ON m.rowid = fts.rowid
            WHERE memories_fts MATCH ?
            {where_clause}
            ORDER BY rank
            LIMIT ?
        """
        cursor = self._conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def by_type(
        self,
        memory_type: str,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return memories of a specific type, newest first."""
        if agent_id is not None:
            cursor = self._conn.execute(
                """
                SELECT * FROM memories
                 WHERE memory_type = ? AND agent_id = ?
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (memory_type, agent_id, limit),
            )
        else:
            cursor = self._conn.execute(
                """
                SELECT * FROM memories
                 WHERE memory_type = ?
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (memory_type, limit),
            )
        return [dict(row) for row in cursor.fetchall()]

    def by_agent(self, agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return memories for a specific agent, newest first."""
        cursor = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE agent_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (agent_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recently created memories across all agents."""
        cursor = self._conn.execute(
            """
            SELECT * FROM memories
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Depth & pinning (v0.1.1)
    # ------------------------------------------------------------------

    def touch(self, memory_id: str) -> None:
        """Increment access_count and set last_accessed_at to now."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._conn.execute(
            """
            UPDATE memories
               SET access_count     = access_count + 1,
                   last_accessed_at = ?
             WHERE id = ?
            """,
            (now, memory_id),
        )
        self._conn.commit()
        self._touched_this_session.add(memory_id)

    def pin(self, memory_id: str) -> None:
        """Mark a memory as always-in-context (pinned)."""
        self._conn.execute(
            "UPDATE memories SET is_pinned = 1 WHERE id = ?", (memory_id,)
        )
        self._conn.commit()

    def unpin(self, memory_id: str) -> None:
        """Remove pinned status from a memory."""
        self._conn.execute(
            "UPDATE memories SET is_pinned = 0 WHERE id = ?", (memory_id,)
        )
        self._conn.commit()

    def get_pinned(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        """Return all pinned memories, optionally filtered by agent."""
        if agent_id is not None:
            cursor = self._conn.execute(
                "SELECT * FROM memories WHERE is_pinned = 1 AND agent_id = ?",
                (agent_id,),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM memories WHERE is_pinned = 1"
            )
        return [dict(row) for row in cursor.fetchall()]

    def search_by_depth(
        self, agent_id: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return top memories sorted by depth_score descending."""
        if agent_id is not None:
            cursor = self._conn.execute(
                """
                SELECT * FROM memories
                 WHERE agent_id = ?
                 ORDER BY depth_score DESC
                 LIMIT ?
                """,
                (agent_id, limit),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM memories ORDER BY depth_score DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in cursor.fetchall()]

    def update_depth_score(self, memory_id: str) -> None:
        """
        Recompute and store depth_score for a single memory.

        Formula:
          depth_score = (min(access_count, 20) / 20 * 0.3) +
                        (recency_score * 0.25) +   # 1.0=today, 0.5=this month, 0.1=older
                        (is_pinned * 0.2) +
                        (human_endorsed * 0.15) +
                        (confidence_score * 0.1)   # HIGH=1.0, MEDIUM=0.6, LOW=0.3
        """
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%dT")
        last = row["last_accessed_at"] or ""
        recency = 1.0 if last.startswith(today) else max(0.0, 1.0 - len(last) * 0)

        # Simple recency: 1.0 today, 0.5 this week, 0.1 older
        if last.startswith(today[:10]):
            recency = 1.0
        elif last[:7] == today[:7]:
            recency = 0.5
        elif last:
            recency = 0.1
        else:
            recency = 0.0

        conf_map = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}
        conf = conf_map.get(str(row["confidence"]).upper(), 0.6)

        score = (
            min(row["access_count"], 20) / 20 * 0.3
            + recency * 0.25
            + int(row["is_pinned"]) * 0.2
            + int(row["human_endorsed"]) * 0.15
            + conf * 0.1
        )

        self._conn.execute(
            "UPDATE memories SET depth_score = ? WHERE id = ?",
            (round(score, 4), memory_id),
        )
        self._conn.commit()

    def recalculate_touched_depth_scores(self) -> int:
        """
        Recalculate depth_score for all memories touched this session.
        Returns count of memories updated.
        Called at session shutdown.
        """
        count = 0
        for memory_id in self._touched_this_session:
            try:
                self.update_depth_score(memory_id)
                count += 1
            except Exception:
                pass  # individual update failures don't stop the batch
        self._touched_this_session.clear()
        return count

    # ------------------------------------------------------------------
    # Session journal (v0.1.1)
    # ------------------------------------------------------------------

    def start_session(self, agent_id: str, session_id: str | None = None) -> str:
        """
        Create a session_journal entry.  Returns the session_id (UUID).
        """
        sid = session_id or str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._conn.execute(
            """
            INSERT OR IGNORE INTO session_journal
                (session_id, agent_id, start_time)
            VALUES (?, ?, ?)
            """,
            (sid, agent_id, now),
        )
        self._conn.commit()
        return sid

    def record_turn(self, session_id: str, topic: str | None = None) -> None:
        """Increment turn_count for a session; optionally append a topic."""
        if topic:
            row = self._conn.execute(
                "SELECT topics FROM session_journal WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            existing: list[str] = json.loads(row["topics"]) if row else []
            if topic not in existing:
                existing.append(topic)
            topics_json = json.dumps(existing)
            self._conn.execute(
                """
                UPDATE session_journal
                   SET turn_count = turn_count + 1, topics = ?
                 WHERE session_id = ?
                """,
                (topics_json, session_id),
            )
        else:
            self._conn.execute(
                "UPDATE session_journal SET turn_count = turn_count + 1 WHERE session_id = ?",
                (session_id,),
            )
        self._conn.commit()

    def end_session(self, session_id: str, summary: str) -> None:
        """Write end_time and summary to the session_journal entry."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._conn.execute(
            """
            UPDATE session_journal
               SET end_time = ?, summary = ?
             WHERE session_id = ?
            """,
            (now, summary, session_id),
        )
        self._conn.commit()

    def last_session(self, agent_id: str) -> dict[str, Any] | None:
        """Return the most recent completed session for this agent."""
        row = self._conn.execute(
            """
            SELECT * FROM session_journal
             WHERE agent_id = ? AND end_time IS NOT NULL
             ORDER BY end_time DESC, rowid DESC
             LIMIT 1
            """,
            (agent_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return a session record by ID."""
        row = self._conn.execute(
            "SELECT * FROM session_journal WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Skills registry
    # ------------------------------------------------------------------

    def register_skill(
        self,
        skill_id: str,
        name: str,
        domain: str,
        file_path: str,
        effectiveness: float = 0.5,
    ) -> None:
        """Register or update a skill in the skills table."""
        self._conn.execute(
            """
            INSERT INTO skills (skill_id, name, domain, file_path, effectiveness)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(skill_id) DO UPDATE SET
                name = excluded.name,
                domain = excluded.domain,
                file_path = excluded.file_path
            """,
            (skill_id, name, domain, file_path, effectiveness),
        )
        self._conn.commit()

    def get_skill(self, skill_id: str) -> dict | None:
        """Get skill metadata by skill_id."""
        row = self._conn.execute(
            "SELECT * FROM skills WHERE skill_id = ?", (skill_id,)
        ).fetchone()
        return dict(row) if row else None

    def search_skills(self, query: str) -> list[dict]:
        """Search skills by keyword in skill_id, name, or domain."""
        pattern = f"%{query}%"
        cursor = self._conn.execute(
            """
            SELECT * FROM skills
            WHERE skill_id LIKE ? OR name LIKE ? OR domain LIKE ?
            ORDER BY usage_count DESC
            """,
            (pattern, pattern, pattern),
        )
        return [dict(row) for row in cursor.fetchall()]

    def touch_skill(self, skill_id: str) -> None:
        """Increment usage_count and update last_used_at for a skill."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._conn.execute(
            """
            UPDATE skills
               SET usage_count  = usage_count + 1,
                   last_used_at = ?
             WHERE skill_id = ?
            """,
            (now, skill_id),
        )
        self._conn.commit()

    def list_skills(self) -> list[dict]:
        """List all registered skills."""
        cursor = self._conn.execute(
            "SELECT * FROM skills ORDER BY usage_count DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Agent registry (persistent)
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        manifest_path: str,
        display_name: str = "",
        role: str = "",
        domain: str = "general",
    ) -> None:
        """Register or update an agent in the persistent registry."""
        self._conn.execute(
            """
            INSERT INTO agent_registry (agent_id, manifest_path, display_name, role, domain)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                manifest_path = excluded.manifest_path,
                display_name  = excluded.display_name,
                role          = excluded.role,
                domain        = excluded.domain
            """,
            (agent_id, manifest_path, display_name, role, domain),
        )
        self._conn.commit()

    def get_agent(self, agent_id: str) -> dict | None:
        """Get agent metadata by agent_id."""
        row = self._conn.execute(
            "SELECT * FROM agent_registry WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_agents(self) -> list[dict]:
        """List all registered agents."""
        cursor = self._conn.execute(
            "SELECT * FROM agent_registry ORDER BY registered_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def touch_agent(self, agent_id: str, session_id: str | None = None) -> None:
        """Increment spawn_count and update last_active_at."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if session_id:
            self._conn.execute(
                """
                UPDATE agent_registry
                   SET spawn_count     = spawn_count + 1,
                       last_active_at  = ?,
                       last_session_id = ?
                 WHERE agent_id = ?
                """,
                (now, session_id, agent_id),
            )
        else:
            self._conn.execute(
                """
                UPDATE agent_registry
                   SET spawn_count    = spawn_count + 1,
                       last_active_at = ?
                 WHERE agent_id = ?
                """,
                (now, agent_id),
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the SQLite connection and optimize the FTS5 index."""
        try:
            self._conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('optimize')")
            self._conn.commit()
        except Exception:
            pass  # FTS5 optimize is best-effort; never crash on close
        self._conn.close()
