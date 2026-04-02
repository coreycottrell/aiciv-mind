"""
Tests for token usage tracking and session JSONL logging in Mind.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from aiciv_mind.mind import Mind


@pytest.fixture
def mock_manifest(tmp_path):
    """Create a mock MindManifest."""
    manifest = MagicMock()
    manifest.mind_id = "test-mind"
    manifest.model.preferred = "minimax-m27"
    manifest.model.max_tokens = 4096
    manifest.model.temperature = 0.7
    manifest.hooks.enabled = False
    manifest.compaction.enabled = False
    manifest.memory.auto_search_before_task = False
    manifest.self_modification_enabled = False

    def enabled_tool_names():
        return []
    manifest.enabled_tool_names = enabled_tool_names

    def resolved_system_prompt():
        return "You are a test mind."
    manifest.resolved_system_prompt = resolved_system_prompt

    return manifest


@pytest.fixture
def mock_memory():
    """Create a mock MemoryStore."""
    return MagicMock()


@pytest.fixture
def mind_instance(mock_manifest, mock_memory, tmp_path):
    """Create a Mind instance with patched paths."""
    mind = Mind(manifest=mock_manifest, memory=mock_memory)
    # Override paths to use tmp_path
    mind._mind_root = tmp_path
    mind._token_log_path = tmp_path / "data" / "token_usage.jsonl"
    mind._session_log_dir = tmp_path / "data" / "sessions"
    mind._token_log_path.parent.mkdir(parents=True, exist_ok=True)
    mind._session_log_dir.mkdir(parents=True, exist_ok=True)
    mind._session_id = "test-session-1"
    return mind


class TestModelPricing:
    def test_known_model_cost(self, mind_instance):
        cost = mind_instance._estimate_cost("minimax-m27", 1_000_000, 1_000_000)
        # minimax-m27: $0.50/M input + $1.50/M output = $2.00
        assert cost == 2.0

    def test_ollama_model_free(self, mind_instance):
        cost = mind_instance._estimate_cost("ollama/phi3", 1_000_000, 1_000_000)
        assert cost == 0.0

    def test_unknown_model(self, mind_instance):
        cost = mind_instance._estimate_cost("unknown-model-xyz", 1000, 500)
        assert cost == 0.0

    def test_litellm_prefix_stripped(self, mind_instance):
        cost = mind_instance._estimate_cost("openrouter/kimi-k2", 1_000_000, 1_000_000)
        # kimi-k2: $0.60/M input + $0.60/M output = $1.20
        assert cost == 1.2


class TestTokenUsageLogging:
    def test_log_token_usage_creates_jsonl(self, mind_instance):
        """Test that _log_token_usage writes to the JSONL file."""
        # Create a mock response
        response = MagicMock()
        response.usage.input_tokens = 1234
        response.usage.output_tokens = 567
        response.usage.cache_read_input_tokens = 0
        response.usage.cache_creation_input_tokens = 0
        response.content = []  # No thinking blocks

        mind_instance._messages = [{"role": "user", "content": "Hello test"}]
        mind_instance._log_token_usage(response, latency_ms=2500)

        # Check the JSONL file was created and has the right content
        assert mind_instance._token_log_path.exists()
        with open(mind_instance._token_log_path) as f:
            lines = f.readlines()
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["session_id"] == "test-session-1"
        assert record["model"] == "minimax-m27"
        assert record["input_tokens"] == 1234
        assert record["output_tokens"] == 567
        assert record["latency_ms"] == 2500
        assert record["estimated_cost_usd"] > 0
        assert "Hello test" in record["task_summary"]

    def test_session_accumulators_updated(self, mind_instance):
        """Test that session-level accumulators track across calls."""
        response = MagicMock()
        response.usage.input_tokens = 100
        response.usage.output_tokens = 50
        response.usage.cache_read_input_tokens = 0
        response.usage.cache_creation_input_tokens = 0
        response.content = []

        mind_instance._messages = [{"role": "user", "content": "test"}]

        # Two API calls
        mind_instance._log_token_usage(response, latency_ms=1000)
        mind_instance._log_token_usage(response, latency_ms=2000)

        assert mind_instance._session_api_calls == 2
        assert mind_instance._session_total_output_tokens == 100

    def test_thinking_tokens_detected(self, mind_instance):
        """Test that thinking blocks contribute to thinking token count."""
        response = MagicMock()
        response.usage.input_tokens = 500
        response.usage.output_tokens = 200
        response.usage.cache_read_input_tokens = 0
        response.usage.cache_creation_input_tokens = 0

        # Simulate a thinking block
        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        thinking_block.thinking = "I need to think about this carefully..." * 10  # ~400 chars
        response.content = [thinking_block]

        mind_instance._messages = [{"role": "user", "content": "think hard"}]
        mind_instance._log_token_usage(response, latency_ms=5000)

        with open(mind_instance._token_log_path) as f:
            record = json.loads(f.readline())
        assert record["thinking_tokens"] > 0


class TestSessionTurnLogging:
    def test_log_user_turn(self, mind_instance):
        """Test logging a user turn to session JSONL."""
        mind_instance._log_session_turn(
            turn_number=1,
            turn_type="user",
        )

        session_log = mind_instance._session_log_dir / "test-session-1.jsonl"
        assert session_log.exists()
        with open(session_log) as f:
            record = json.loads(f.readline())
        assert record["type"] == "user"
        assert record["turn"] == 1
        assert record["session_id"] == "test-session-1"

    def test_log_assistant_turn_with_tokens(self, mind_instance):
        """Test logging an assistant turn with token usage."""
        response = MagicMock()
        response.usage.input_tokens = 800
        response.usage.output_tokens = 300
        response.usage.cache_read_input_tokens = 100

        mind_instance._log_session_turn(
            turn_number=2,
            turn_type="assistant",
            response=response,
            duration_ms=3000,
        )

        session_log = mind_instance._session_log_dir / "test-session-1.jsonl"
        with open(session_log) as f:
            record = json.loads(f.readline())
        assert record["type"] == "assistant"
        assert record["tokens"]["input"] == 800
        assert record["tokens"]["output"] == 300
        assert record["tokens"]["cached"] == 100
        assert record["duration_ms"] == 3000

    def test_log_tool_call_turn(self, mind_instance):
        """Test logging a tool call turn."""
        mind_instance._log_session_turn(
            turn_number=3,
            turn_type="tool_call",
            tools_used=["bash", "memory_search", "web_fetch"],
            duration_ms=1500,
        )

        session_log = mind_instance._session_log_dir / "test-session-1.jsonl"
        with open(session_log) as f:
            record = json.loads(f.readline())
        assert record["type"] == "tool_call"
        assert record["tools_used"] == ["bash", "memory_search", "web_fetch"]

    def test_no_session_id_skips(self, mind_instance):
        """Test that logging is silently skipped when no session_id."""
        mind_instance._session_id = None
        mind_instance._log_session_turn(turn_number=1, turn_type="user")
        # Should not create any file
        session_files = list(mind_instance._session_log_dir.glob("*.jsonl"))
        assert len(session_files) == 0


class TestTokenUsageStatsProperty:
    def test_initial_stats(self, mind_instance):
        stats = mind_instance.token_usage_stats
        assert stats["session_id"] == "test-session-1"
        assert stats["api_calls"] == 0
        assert stats["total_input_tokens"] == 0
        assert stats["total_output_tokens"] == 0
        assert stats["estimated_cost_usd"] == 0.0

    def test_stats_after_calls(self, mind_instance):
        response = MagicMock()
        response.usage.input_tokens = 500
        response.usage.output_tokens = 200
        response.usage.cache_read_input_tokens = 0
        response.usage.cache_creation_input_tokens = 0
        response.content = []

        mind_instance._messages = [{"role": "user", "content": "test"}]
        mind_instance._log_token_usage(response, latency_ms=1000)

        stats = mind_instance.token_usage_stats
        assert stats["api_calls"] == 1
        assert stats["total_output_tokens"] == 200
        assert stats["estimated_cost_usd"] > 0
