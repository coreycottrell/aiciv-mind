"""Tests for aiciv_mind.transfer — cross-domain knowledge transfer."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from aiciv_mind.memory import MemoryStore, Memory
from aiciv_mind.transfer import KnowledgeTransfer, TransferCandidate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def transfer(memory):
    return KnowledgeTransfer(memory_store=memory, agent_id="test-mind")


def _make_memory(
    memory_store: MemoryStore,
    title: str = "Test Pattern",
    content: str = "A useful pattern",
    depth_score: float = 0.9,
    access_count: int = 5,
    memory_type: str = "pattern",
    domain: str = "engineering",
    tags: list[str] | None = None,
    agent_id: str = "test-mind",
) -> str:
    """Helper to create a memory with specific attributes."""
    mem = Memory(
        agent_id=agent_id,
        title=title,
        content=content,
        memory_type=memory_type,
        domain=domain,
        tags=tags or ["pattern"],
    )
    mem_id = memory_store.store(mem)

    # Update depth_score and access_count directly
    memory_store._conn.execute(
        "UPDATE memories SET depth_score = ?, access_count = ? WHERE id = ?",
        (depth_score, access_count, mem_id),
    )
    memory_store._conn.commit()
    return mem_id


# ---------------------------------------------------------------------------
# Tests: find_transferable
# ---------------------------------------------------------------------------


class TestFindTransferable:
    def test_empty_db(self, transfer):
        assert transfer.find_transferable() == []

    def test_finds_high_depth_pattern(self, transfer, memory):
        _make_memory(memory, title="Good Pattern", depth_score=0.9, access_count=5)
        candidates = transfer.find_transferable()
        assert len(candidates) == 1
        assert candidates[0].title == "Good Pattern"

    def test_skips_low_depth(self, transfer, memory):
        _make_memory(memory, depth_score=0.3, access_count=5)
        assert transfer.find_transferable() == []

    def test_skips_low_access(self, transfer, memory):
        _make_memory(memory, depth_score=0.9, access_count=1)
        assert transfer.find_transferable() == []

    def test_skips_wrong_type(self, transfer, memory):
        _make_memory(memory, memory_type="session", tags=["general"], depth_score=0.9, access_count=5)
        assert transfer.find_transferable() == []

    def test_skips_already_shared(self, transfer, memory):
        mem_id = _make_memory(memory, depth_score=0.9, access_count=5)
        transfer.mark_shared(mem_id)
        assert transfer.find_transferable() == []

    def test_custom_thresholds(self, transfer, memory):
        _make_memory(memory, depth_score=0.5, access_count=2)
        # Default thresholds: should not find
        assert transfer.find_transferable() == []
        # Lowered thresholds: should find
        candidates = transfer.find_transferable(min_depth=0.4, min_access=1)
        assert len(candidates) == 1

    def test_limit_results(self, transfer, memory):
        for i in range(5):
            _make_memory(memory, title=f"Pattern {i}", depth_score=0.9, access_count=5)
        candidates = transfer.find_transferable(limit=3)
        assert len(candidates) == 3

    def test_ordered_by_depth(self, transfer, memory):
        _make_memory(memory, title="Low", depth_score=0.8, access_count=5)
        _make_memory(memory, title="High", depth_score=0.95, access_count=5)
        candidates = transfer.find_transferable()
        assert candidates[0].title == "High"
        assert candidates[1].title == "Low"

    def test_different_agent_id(self, transfer, memory):
        _make_memory(memory, agent_id="other-mind", depth_score=0.9, access_count=5)
        assert transfer.find_transferable() == []

    def test_tag_based_type_match(self, transfer, memory):
        """Memories with transferable tags (not just memory_type) should qualify."""
        _make_memory(
            memory,
            memory_type="general",
            tags=["learning", "hub-engagement"],
            depth_score=0.9,
            access_count=5,
        )
        candidates = transfer.find_transferable()
        assert len(candidates) == 1


# ---------------------------------------------------------------------------
# Tests: format_for_hub
# ---------------------------------------------------------------------------


class TestFormatForHub:
    def test_basic_format(self, transfer):
        candidate = TransferCandidate(
            memory_id="mem-123",
            title="Error Recovery Pattern",
            content="When bash fails 3 times, try a different approach.",
            depth_score=0.92,
            domain="engineering",
            tags=["pattern", "error-handling"],
            access_count=7,
            created_at="2026-04-02T12:00:00Z",
            agent_id="test-mind",
        )
        result = transfer.format_for_hub(candidate)

        assert "Error Recovery Pattern" in result.hub_post_body
        assert "test-mind" in result.hub_post_body
        assert "engineering" in result.hub_post_body
        assert "0.92" in result.hub_post_body
        assert result.scope == "civ"
        assert result.memory_id == "mem-123"

    def test_public_scope(self, transfer):
        candidate = TransferCandidate(
            memory_id="mem-456",
            title="Universal Pattern",
            content="Always search memory before acting.",
            depth_score=0.95,
            domain="meta",
            tags=["insight"],
            access_count=20,
            created_at="2026-04-02T12:00:00Z",
            agent_id="test-mind",
        )
        result = transfer.format_for_hub(candidate, scope="public")
        assert result.scope == "public"
        assert "public" in result.hub_post_body

    def test_metadata_fields(self, transfer):
        candidate = TransferCandidate(
            memory_id="mem-789",
            title="Test",
            content="Content",
            depth_score=0.85,
            domain="testing",
            tags=[],
            access_count=3,
            created_at="2026-04-02T12:00:00Z",
            agent_id="test-mind",
        )
        result = transfer.format_for_hub(candidate)
        assert result.metadata["memory_id"] == "mem-789"
        assert result.metadata["source_agent"] == "test-mind"
        assert result.metadata["domain"] == "testing"
        assert result.metadata["depth_score"] == 0.85
        assert "transferred_at" in result.metadata


# ---------------------------------------------------------------------------
# Tests: mark_shared
# ---------------------------------------------------------------------------


class TestMarkShared:
    def test_mark_shared(self, transfer, memory):
        mem_id = _make_memory(memory, depth_score=0.9, access_count=5)
        assert transfer.mark_shared(mem_id) is True

        # Verify tag was added
        tags = memory._conn.execute(
            "SELECT tag FROM memory_tags WHERE memory_id = ?", (mem_id,)
        ).fetchall()
        tag_list = [r["tag"] for r in tags]
        assert "cross-domain-shared" in tag_list

    def test_mark_shared_idempotent(self, transfer, memory):
        mem_id = _make_memory(memory, depth_score=0.9, access_count=5)
        assert transfer.mark_shared(mem_id) is True
        assert transfer.mark_shared(mem_id) is True  # Should not raise


# ---------------------------------------------------------------------------
# Tests: transfer_summary
# ---------------------------------------------------------------------------


class TestTransferSummary:
    def test_empty_summary(self, transfer):
        summary = transfer.transfer_summary()
        assert "No memories" in summary

    def test_summary_with_candidates(self, transfer, memory):
        _make_memory(memory, title="Pattern A", depth_score=0.9, access_count=5)
        _make_memory(memory, title="Pattern B", depth_score=0.85, access_count=4)
        summary = transfer.transfer_summary()
        assert "Transfer Candidates" in summary
        assert "Pattern A" in summary
        assert "Pattern B" in summary
        assert "2 found" in summary
