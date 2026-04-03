"""Tests for aiciv_mind.memory_selector — AI-powered memory relevance selection."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiciv_mind.memory_selector import MemorySelector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def selector():
    """Default MemorySelector with test config."""
    return MemorySelector(
        api_url="http://localhost:4000",
        api_key="test-key",
        model="test-model",
        timeout_s=5.0,
    )


@pytest.fixture
def candidates():
    """10 candidate memories for selection tests."""
    return [
        {"id": f"mem-{i}", "title": f"Memory {i}", "content": f"Content for memory {i} about topic {i}"}
        for i in range(10)
    ]


# ---------------------------------------------------------------------------
# Tests: _parse_indices
# ---------------------------------------------------------------------------


class TestParseIndices:
    def test_simple_array(self):
        assert MemorySelector._parse_indices("[0, 2, 4]", 10, 5) == [0, 2, 4]

    def test_with_markdown_code_block(self):
        text = "```json\n[1, 3, 5]\n```"
        assert MemorySelector._parse_indices(text, 10, 5) == [1, 3, 5]

    def test_with_surrounding_text(self):
        text = "Here are the most relevant: [2, 0, 7] based on my analysis"
        assert MemorySelector._parse_indices(text, 10, 5) == [2, 0, 7]

    def test_trailing_comma(self):
        assert MemorySelector._parse_indices("[1, 2, 3,]", 10, 5) == [1, 2, 3]

    def test_deduplicates(self):
        assert MemorySelector._parse_indices("[1, 1, 2, 2]", 10, 5) == [1, 2]

    def test_filters_out_of_range(self):
        assert MemorySelector._parse_indices("[0, 15, 2, -1]", 10, 5) == [0, 2]

    def test_limits_to_top_k(self):
        result = MemorySelector._parse_indices("[0, 1, 2, 3, 4, 5, 6]", 10, 3)
        assert len(result) == 3
        assert result == [0, 1, 2]

    def test_empty_array(self):
        assert MemorySelector._parse_indices("[]", 10, 5) == []

    def test_no_array_in_text(self):
        assert MemorySelector._parse_indices("no array here", 10, 5) == []

    def test_invalid_json(self):
        assert MemorySelector._parse_indices("[not, valid, json]", 10, 5) == []

    def test_non_integer_values(self):
        # Mixed: some valid, some not
        assert MemorySelector._parse_indices('[0, "two", 3, null]', 10, 5) == [0, 3]


# ---------------------------------------------------------------------------
# Tests: select() — short-circuit cases
# ---------------------------------------------------------------------------


class TestSelectShortCircuit:
    @pytest.mark.asyncio
    async def test_returns_all_when_under_top_k(self, selector, candidates):
        """When candidates <= top_k, returns all without model call."""
        small = candidates[:3]
        result = await selector.select("test task", small, top_k=5)
        assert result == small
        assert selector.calls == 0  # No model call made

    @pytest.mark.asyncio
    async def test_returns_all_when_equal_to_top_k(self, selector, candidates):
        """When candidates == top_k, returns all without model call."""
        exact = candidates[:5]
        result = await selector.select("test task", exact, top_k=5)
        assert result == exact
        assert selector.calls == 0


# ---------------------------------------------------------------------------
# Tests: select() — model call success
# ---------------------------------------------------------------------------


class TestSelectSuccess:
    @pytest.mark.asyncio
    async def test_selects_based_on_model_response(self, selector, candidates):
        """When model returns valid indices, those candidates are selected."""
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "[2, 5, 0, 8, 1]"
        mock_response.content = [mock_block]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("anthropic.AsyncAnthropic") as MockAnthropic:
            MockAnthropic.return_value = mock_client
            result = await selector.select("find patterns", candidates, top_k=5)

        assert len(result) == 5
        assert result[0]["id"] == "mem-2"
        assert result[1]["id"] == "mem-5"
        assert selector.calls == 1
        assert selector.failures == 0


# ---------------------------------------------------------------------------
# Tests: select() — fallback on failure
# ---------------------------------------------------------------------------


class TestSelectFallback:
    @pytest.mark.asyncio
    async def test_falls_back_on_model_error(self, selector, candidates):
        """When model call fails, returns FTS5 order (first top_k candidates)."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=ConnectionError("model down"))

        with patch("anthropic.AsyncAnthropic") as MockAnthropic:
            MockAnthropic.return_value = mock_client
            result = await selector.select("find patterns", candidates, top_k=3)

        assert len(result) == 3
        assert result[0]["id"] == "mem-0"  # FTS5 order preserved
        assert selector.calls == 1
        assert selector.failures == 1

    @pytest.mark.asyncio
    async def test_falls_back_on_unparseable_response(self, selector, candidates):
        """When model returns unparseable text, falls back to FTS5 order."""
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "I cannot determine the most relevant memories."
        mock_response.content = [mock_block]

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("anthropic.AsyncAnthropic") as MockAnthropic:
            MockAnthropic.return_value = mock_client
            result = await selector.select("find patterns", candidates, top_k=3)

        assert len(result) == 3
        assert result[0]["id"] == "mem-0"
        assert selector.failures == 1


# ---------------------------------------------------------------------------
# Tests: stats
# ---------------------------------------------------------------------------


class TestSelectorStats:
    def test_initial_stats(self, selector):
        stats = selector.stats
        assert stats["calls"] == 0
        assert stats["failures"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["avg_latency_ms"] == 0
