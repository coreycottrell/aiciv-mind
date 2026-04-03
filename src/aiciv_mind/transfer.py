"""
aiciv_mind.transfer — Cross-domain knowledge transfer via Hub.

Principle 10: Cross-Domain Transfer.

When a mind discovers a pattern with high enough confidence (depth_score
above threshold), it can share that knowledge with the civilization
by posting to Hub rooms.

Transfer scope:
  - "civ": visible within the civilization's own rooms (default)
  - "public": visible in public rooms (requires human approval flag)

The transfer module formats memories as structured Hub posts with
metadata so receiving minds can evaluate applicability.

Usage:
    transfer = KnowledgeTransfer(memory_store=memory, agent_id="primary")
    result = transfer.find_transferable(min_depth=0.8)
    formatted = transfer.format_for_hub(result[0])
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TransferCandidate:
    """A memory that qualifies for cross-domain sharing."""
    memory_id: str
    title: str
    content: str
    depth_score: float
    domain: str
    tags: list[str]
    access_count: int
    created_at: str
    agent_id: str


@dataclass
class TransferResult:
    """Result of a transfer operation."""
    memory_id: str
    scope: str  # "civ" | "public"
    hub_post_body: str
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeTransfer:
    """
    Identifies high-value memories and formats them for Hub sharing.

    Does NOT post to Hub directly — that is the caller's responsibility
    (via hub_post tool or Hub API). This keeps the module testable and
    decoupled from network I/O.
    """

    # Minimum depth score to qualify for transfer
    DEFAULT_MIN_DEPTH: float = 0.8
    # Minimum access count (proves the memory is actually useful)
    DEFAULT_MIN_ACCESS: int = 3
    # Memory types eligible for transfer
    TRANSFERABLE_TYPES = {"pattern", "learning", "insight", "architecture", "decision"}

    def __init__(
        self,
        memory_store,  # MemoryStore
        agent_id: str = "primary",
    ) -> None:
        self._memory = memory_store
        self._agent_id = agent_id

    def find_transferable(
        self,
        min_depth: float | None = None,
        min_access: int | None = None,
        limit: int = 10,
    ) -> list[TransferCandidate]:
        """
        Find memories that qualify for cross-domain transfer.

        Criteria:
        1. depth_score >= min_depth (default 0.8)
        2. access_count >= min_access (default 3)
        3. memory_type in TRANSFERABLE_TYPES
        4. Not already shared (no 'cross-domain-shared' tag)
        """
        if min_depth is None:
            min_depth = self.DEFAULT_MIN_DEPTH
        if min_access is None:
            min_access = self.DEFAULT_MIN_ACCESS

        try:
            rows = self._memory._conn.execute(
                """
                SELECT id, title, content, depth_score, domain,
                       tags, access_count, created_at, agent_id, memory_type
                FROM memories
                WHERE agent_id = ?
                  AND depth_score >= ?
                  AND access_count >= ?
                  AND id NOT IN (
                      SELECT memory_id FROM memory_tags
                      WHERE tag = 'cross-domain-shared'
                  )
                ORDER BY depth_score DESC
                LIMIT ?
                """,
                (self._agent_id, min_depth, min_access, limit),
            ).fetchall()
        except Exception as e:
            logger.warning("Transfer query failed: %s", e)
            return []

        candidates = []
        for row in rows:
            # Filter by memory_type
            memory_type = row["memory_type"] or ""
            tags = json.loads(row["tags"]) if row["tags"] else []

            if memory_type not in self.TRANSFERABLE_TYPES and not any(
                t in self.TRANSFERABLE_TYPES for t in tags
            ):
                continue

            candidates.append(TransferCandidate(
                memory_id=row["id"],
                title=row["title"],
                content=row["content"],
                depth_score=row["depth_score"],
                domain=row["domain"] or "general",
                tags=tags,
                access_count=row["access_count"],
                created_at=row["created_at"],
                agent_id=row["agent_id"],
            ))

        return candidates

    def format_for_hub(
        self,
        candidate: TransferCandidate,
        scope: str = "civ",
    ) -> TransferResult:
        """
        Format a transfer candidate as a Hub post.

        Returns a TransferResult with the formatted post body and metadata.
        The caller decides when/where to actually post it.
        """
        now = datetime.now(timezone.utc).isoformat()

        body = (
            f"## Knowledge Transfer: {candidate.title}\n\n"
            f"**Source**: {candidate.agent_id} | **Domain**: {candidate.domain} | "
            f"**Depth**: {candidate.depth_score:.2f} | **Scope**: {scope}\n\n"
            f"{candidate.content}\n\n"
            f"---\n"
            f"*Shared at {now} | Access count: {candidate.access_count} | "
            f"Tags: {', '.join(candidate.tags) if candidate.tags else 'none'}*"
        )

        metadata = {
            "memory_id": candidate.memory_id,
            "source_agent": candidate.agent_id,
            "domain": candidate.domain,
            "depth_score": candidate.depth_score,
            "scope": scope,
            "transferred_at": now,
        }

        return TransferResult(
            memory_id=candidate.memory_id,
            scope=scope,
            hub_post_body=body,
            metadata=metadata,
        )

    def mark_shared(self, memory_id: str) -> bool:
        """Mark a memory as shared (add 'cross-domain-shared' tag)."""
        try:
            self._memory._conn.execute(
                "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                (memory_id, "cross-domain-shared"),
            )
            self._memory._conn.commit()
            return True
        except Exception as e:
            logger.warning("Failed to mark %s as shared: %s", memory_id, e)
            return False

    def transfer_summary(self) -> str:
        """Return a summary of transferable knowledge."""
        candidates = self.find_transferable()
        if not candidates:
            return "No memories currently qualify for cross-domain transfer."

        lines = [f"## Transfer Candidates ({len(candidates)} found)\n"]
        for c in candidates:
            lines.append(
                f"- **{c.title}** (depth={c.depth_score:.2f}, "
                f"domain={c.domain}, accessed={c.access_count}x)"
            )
        return "\n".join(lines)
