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
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
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
"""


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

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create all tables, virtual tables, triggers, and indexes."""
        # executescript auto-commits, so we commit the pragma changes first.
        self._conn.commit()
        self._conn.executescript(_SCHEMA_SQL)
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
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()
