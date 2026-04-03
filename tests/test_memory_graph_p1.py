"""
Tests for P1 Memory Graph Links — auto-linking on write + graph-augmented search.
"""

from __future__ import annotations

import pytest

from aiciv_mind.memory import Memory, MemoryStore


@pytest.fixture
def store():
    """Fresh in-memory MemoryStore with auto_link enabled."""
    s = MemoryStore(":memory:", auto_link=True)
    return s


@pytest.fixture
def store_no_auto():
    """Fresh in-memory MemoryStore with auto_link disabled."""
    s = MemoryStore(":memory:", auto_link=False)
    return s


def _mem(agent_id="test", title="", content="", domain="general", tags=None):
    return Memory(
        agent_id=agent_id,
        title=title,
        content=content,
        domain=domain,
        tags=tags or [],
    )


# ---------------------------------------------------------------------------
# Auto-linking on write
# ---------------------------------------------------------------------------


class TestAutoLinking:
    def test_auto_link_creates_links_for_similar_memories(self, store):
        # Store a base memory
        m1 = _mem(title="Python async patterns", content="asyncio event loop concurrency patterns")
        store.store(m1)

        m2 = _mem(title="JavaScript async patterns", content="Promise and async await patterns")
        store.store(m2)

        # Third memory about async patterns — should auto-link to m1 and/or m2
        m3 = _mem(title="Async concurrency patterns", content="asyncio patterns for concurrent execution")
        store.store(m3)

        links_from_m3 = store.get_links_from(m3.id)
        assert len(links_from_m3) > 0
        linked_targets = {l["target_id"] for l in links_from_m3}
        # Should have linked to at least one of the prior memories
        assert linked_targets & {m1.id, m2.id}

    def test_auto_link_uses_compounds_for_shared_domain(self, store):
        m1 = _mem(
            title="Database optimization",
            content="Index tuning for PostgreSQL",
            domain="infrastructure",
        )
        store.store(m1)

        m2 = _mem(
            title="Database migration patterns",
            content="PostgreSQL migration best practices",
            domain="infrastructure",
        )
        store.store(m2)

        links = store.get_links_from(m2.id)
        compounds = [l for l in links if l["link_type"] == "compounds"]
        assert len(compounds) > 0

    def test_auto_link_uses_compounds_for_shared_tags(self, store):
        m1 = _mem(
            title="React component design",
            content="Building reusable React components",
            tags=["frontend", "react"],
        )
        store.store(m1)

        m2 = _mem(
            title="React testing strategies",
            content="Testing React components with vitest",
            tags=["frontend", "testing"],
        )
        store.store(m2)

        links = store.get_links_from(m2.id)
        compounds = [l for l in links if l["link_type"] == "compounds"]
        # Shared tag "frontend" → compounds
        assert len(compounds) > 0

    def test_auto_link_uses_references_for_similarity_only(self, store):
        m1 = _mem(
            title="API rate limiting",
            content="Implementing token bucket rate limiting for REST APIs",
            domain="general",
        )
        store.store(m1)

        m2 = _mem(
            title="REST API rate limits",
            content="How to handle rate limiting in REST API calls",
            domain="general",
        )
        store.store(m2)

        links = store.get_links_from(m2.id)
        references = [l for l in links if l["link_type"] == "references"]
        # No shared domain (both general) or tags → references
        assert len(references) > 0

    def test_auto_link_disabled(self, store_no_auto):
        m1 = _mem(title="First memory", content="Some unique first content about databases")
        store_no_auto.store(m1)

        m2 = _mem(title="Second memory", content="Some unique second content about databases")
        store_no_auto.store(m2)

        links = store_no_auto.get_links_from(m2.id)
        assert len(links) == 0

    def test_auto_link_does_not_self_link(self, store):
        m1 = _mem(title="Self referential test", content="This is a test of self referential linking")
        store.store(m1)

        links = store.get_links_from(m1.id)
        self_links = [l for l in links if l["target_id"] == m1.id]
        assert len(self_links) == 0

    def test_auto_link_max_links_respected(self, store):
        # Store many similar memories
        for i in range(10):
            store.store(_mem(
                title=f"Memory about patterns #{i}",
                content=f"Pattern recognition and machine learning techniques #{i}",
            ))

        # Store another — should create at most max_links (default 3)
        final = _mem(title="Pattern recognition overview", content="Overview of pattern recognition techniques")
        store.store(final)

        links = store.get_links_from(final.id)
        assert len(links) <= 3

    def test_auto_link_no_links_when_only_one_memory(self, store):
        """First memory stored has nothing to link to."""
        m1 = _mem(title="First ever memory", content="Absolutely unique first entry")
        store.store(m1)

        links = store.get_links_from(m1.id)
        assert len(links) == 0


# ---------------------------------------------------------------------------
# Graph-augmented search
# ---------------------------------------------------------------------------


class TestSearchWithGraph:
    def test_search_with_graph_returns_linked_memories(self, store):
        m1 = _mem(title="Auth middleware design", content="JWT token validation middleware")
        store.store(m1)

        m2 = _mem(title="Auth token refresh", content="How to refresh JWT tokens")
        store.store(m2)

        # Manually link
        store.link_memories(m1.id, m2.id, "references", "m1 references m2")

        results = store.search_with_graph("JWT token auth")
        assert len(results) > 0

        # At least one result should have graph data
        has_links = any(r.get("_links_from") or r.get("_links_to") for r in results)
        assert has_links

    def test_search_with_graph_includes_linked_field(self, store):
        m1 = _mem(title="Database schema v1", content="Users table with email column")
        store.store(m1)

        m2 = _mem(title="Database schema v2", content="Users table with email and phone columns")
        store.store(m2)

        m3 = _mem(title="Migration notes", content="Added phone column to users table")
        store.store(m3)

        store.link_memories(m2.id, m1.id, "supersedes", "v2 replaces v1")
        store.link_memories(m3.id, m2.id, "references", "migration for v2")

        results = store.search_with_graph("database schema users")
        for r in results:
            assert "_linked" in r
            assert "_links_from" in r
            assert "_links_to" in r

    def test_search_with_graph_deduplicates(self, store):
        m1 = _mem(title="Error handling patterns", content="Try except best practices in Python")
        store.store(m1)

        m2 = _mem(title="Python error types", content="Built-in exception types in Python")
        store.store(m2)

        store.link_memories(m1.id, m2.id, "references")

        results = store.search_with_graph("Python error handling")
        # Both might appear in direct results — linked should not duplicate
        for r in results:
            direct_ids = {r2["id"] for r2 in results}
            linked_ids = {l["id"] for l in r.get("_linked", [])}
            # No overlap between direct and linked
            assert not (direct_ids & linked_ids)

    def test_search_with_graph_empty_query(self, store):
        results = store.search_with_graph("")
        assert results == []

    def test_search_with_graph_no_results(self, store):
        results = store.search_with_graph("xyznonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# Manual linking (existing infrastructure validation)
# ---------------------------------------------------------------------------


class TestManualLinking:
    """Use store_no_auto to test manual links without auto-link interference."""

    def test_link_memories_creates_link(self, store_no_auto):
        m1 = _mem(title="Memory A", content="Content A")
        m2 = _mem(title="Memory B", content="Content B")
        store_no_auto.store(m1)
        store_no_auto.store(m2)

        lid = store_no_auto.link_memories(m1.id, m2.id, "references", "A cites B")
        assert lid  # Returns a UUID

        links = store_no_auto.get_links_from(m1.id)
        assert len(links) == 1
        assert links[0]["target_id"] == m2.id
        assert links[0]["link_type"] == "references"
        assert links[0]["reason"] == "A cites B"

    def test_get_links_to(self, store_no_auto):
        m1 = _mem(title="Source", content="Source content")
        m2 = _mem(title="Target", content="Target content")
        store_no_auto.store(m1)
        store_no_auto.store(m2)

        store_no_auto.link_memories(m1.id, m2.id, "supersedes")

        incoming = store_no_auto.get_links_to(m2.id)
        assert len(incoming) == 1
        assert incoming[0]["source_id"] == m1.id

    def test_get_memory_graph(self, store_no_auto):
        m1 = _mem(title="Center", content="Center node")
        m2 = _mem(title="Child", content="Child node")
        m3 = _mem(title="Parent", content="Parent node")
        store_no_auto.store(m1)
        store_no_auto.store(m2)
        store_no_auto.store(m3)

        store_no_auto.link_memories(m1.id, m2.id, "references")
        store_no_auto.link_memories(m3.id, m1.id, "compounds")

        graph = store_no_auto.get_memory_graph(m1.id)
        assert graph["memory"]["title"] == "Center"
        assert len(graph["links_from"]) == 1
        assert len(graph["links_to"]) == 1

    def test_invalid_link_type_raises(self, store_no_auto):
        m1 = _mem(title="A", content="A")
        m2 = _mem(title="B", content="B")
        store_no_auto.store(m1)
        store_no_auto.store(m2)

        with pytest.raises(ValueError, match="link_type must be one of"):
            store_no_auto.link_memories(m1.id, m2.id, "invalid_type")

    def test_duplicate_link_ignored(self, store_no_auto):
        m1 = _mem(title="A", content="A")
        m2 = _mem(title="B", content="B")
        store_no_auto.store(m1)
        store_no_auto.store(m2)

        store_no_auto.link_memories(m1.id, m2.id, "references")
        store_no_auto.link_memories(m1.id, m2.id, "references")  # duplicate

        links = store_no_auto.get_links_from(m1.id)
        assert len(links) == 1  # UNIQUE constraint prevents duplicate

    def test_get_conflicts(self, store_no_auto):
        m1 = _mem(title="Claim A", content="X is true")
        m2 = _mem(title="Claim B", content="X is false")
        store_no_auto.store(m1)
        store_no_auto.store(m2)

        store_no_auto.link_memories(m1.id, m2.id, "conflicts", "Contradictory claims about X")

        conflicts = store_no_auto.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["source_id"] == m1.id
        assert conflicts[0]["target_id"] == m2.id

    def test_get_superseded(self, store_no_auto):
        m1 = _mem(title="Old version", content="Version 1")
        m2 = _mem(title="New version", content="Version 2")
        store_no_auto.store(m1)
        store_no_auto.store(m2)

        store_no_auto.link_memories(m2.id, m1.id, "supersedes", "v2 replaces v1")

        superseded = store_no_auto.get_superseded()
        assert len(superseded) == 1
        assert superseded[0]["id"] == m1.id
        assert superseded[0]["superseded_by"] == m2.id

    def test_link_increments_citation_count(self, store_no_auto):
        """P1: linking a memory increments citation_count on the target."""
        m1 = _mem(title="Source", content="References target")
        m2 = _mem(title="Target", content="Referenced by source")
        store_no_auto.store(m1)
        store_no_auto.store(m2)

        # Before linking
        row = store_no_auto._conn.execute(
            "SELECT citation_count FROM memories WHERE id = ?", (m2.id,)
        ).fetchone()
        assert row["citation_count"] == 0

        store_no_auto.link_memories(m1.id, m2.id, "references")

        row = store_no_auto._conn.execute(
            "SELECT citation_count FROM memories WHERE id = ?", (m2.id,)
        ).fetchone()
        assert row["citation_count"] == 1

    def test_multiple_links_increment_citation_count(self, store_no_auto):
        """Each unique link increments citation_count once."""
        m1 = _mem(title="A", content="A")
        m2 = _mem(title="B", content="B")
        m3 = _mem(title="Target", content="Target")
        store_no_auto.store(m1)
        store_no_auto.store(m2)
        store_no_auto.store(m3)

        store_no_auto.link_memories(m1.id, m3.id, "references")
        store_no_auto.link_memories(m2.id, m3.id, "compounds")

        row = store_no_auto._conn.execute(
            "SELECT citation_count FROM memories WHERE id = ?", (m3.id,)
        ).fetchone()
        assert row["citation_count"] == 2

    def test_duplicate_link_does_not_increment_citation_count(self, store_no_auto):
        """Duplicate links (INSERT OR IGNORE) do not double-count citations."""
        m1 = _mem(title="A", content="A")
        m2 = _mem(title="B", content="B")
        store_no_auto.store(m1)
        store_no_auto.store(m2)

        store_no_auto.link_memories(m1.id, m2.id, "references")
        store_no_auto.link_memories(m1.id, m2.id, "references")  # duplicate

        row = store_no_auto._conn.execute(
            "SELECT citation_count FROM memories WHERE id = ?", (m2.id,)
        ).fetchone()
        assert row["citation_count"] == 1

    def test_citation_count_boosts_depth_score(self, store_no_auto):
        """Memories with higher citation_count get higher depth_score."""
        m1 = _mem(title="Highly cited", content="Important pattern")
        m2 = _mem(title="Uncited", content="Isolated fact")
        m3 = _mem(title="Citer A", content="Cites m1")
        m4 = _mem(title="Citer B", content="Also cites m1")
        for m in (m1, m2, m3, m4):
            store_no_auto.store(m)

        store_no_auto.link_memories(m3.id, m1.id, "references")
        store_no_auto.link_memories(m4.id, m1.id, "compounds")

        store_no_auto.update_depth_score(m1.id)
        store_no_auto.update_depth_score(m2.id)

        cited_score = store_no_auto._conn.execute(
            "SELECT depth_score FROM memories WHERE id = ?", (m1.id,)
        ).fetchone()["depth_score"]
        uncited_score = store_no_auto._conn.execute(
            "SELECT depth_score FROM memories WHERE id = ?", (m2.id,)
        ).fetchone()["depth_score"]

        assert cited_score > uncited_score
