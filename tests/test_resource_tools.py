"""
Tests for resource_tools — resource_usage, token_stats, session_stats.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.resource_tools import register_resource_tools


@pytest.fixture
def temp_mind_root(tmp_path):
    """Create a temporary mind root with data/ structure."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sessions_dir = data_dir / "sessions"
    sessions_dir.mkdir()
    return str(tmp_path)


@pytest.fixture
def registry_with_resource_tools(temp_mind_root):
    """Create a ToolRegistry with resource tools registered."""
    registry = ToolRegistry()
    register_resource_tools(registry, mind_root=temp_mind_root)
    return registry


class TestResourceToolsRegistration:
    def test_all_three_tools_registered(self, registry_with_resource_tools):
        names = registry_with_resource_tools.names()
        assert "resource_usage" in names
        assert "token_stats" in names
        assert "session_stats" in names

    def test_all_tools_are_read_only(self, registry_with_resource_tools):
        assert registry_with_resource_tools.is_read_only("resource_usage")
        assert registry_with_resource_tools.is_read_only("token_stats")
        assert registry_with_resource_tools.is_read_only("session_stats")


class TestResourceUsage:
    @pytest.mark.asyncio
    async def test_returns_report(self, registry_with_resource_tools):
        result = await registry_with_resource_tools.execute("resource_usage", {})
        assert "Resource Usage Report" in result
        assert "Process count" in result

    @pytest.mark.asyncio
    async def test_verbose_mode(self, registry_with_resource_tools):
        result = await registry_with_resource_tools.execute("resource_usage", {"verbose": True})
        assert "Resource Usage Report" in result


class TestTokenStats:
    @pytest.mark.asyncio
    async def test_empty_log(self, registry_with_resource_tools):
        result = await registry_with_resource_tools.execute("token_stats", {})
        assert "does not exist" in result

    @pytest.mark.asyncio
    async def test_with_data(self, temp_mind_root):
        # Write some test token records
        token_log = Path(temp_mind_root) / "data" / "token_usage.jsonl"
        records = [
            {
                "timestamp": "2026-04-02T10:00:00",
                "session_id": "test-1",
                "model": "minimax-m27",
                "input_tokens": 1000,
                "output_tokens": 500,
                "thinking_tokens": 0,
                "latency_ms": 2000,
                "estimated_cost_usd": 0.0012,
                "task_summary": "test task",
            },
            {
                "timestamp": "2026-04-02T10:05:00",
                "session_id": "test-1",
                "model": "kimi-k2",
                "input_tokens": 2000,
                "output_tokens": 800,
                "thinking_tokens": 100,
                "latency_ms": 3000,
                "estimated_cost_usd": 0.0025,
                "task_summary": "another task",
            },
        ]
        with open(token_log, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        registry = ToolRegistry()
        register_resource_tools(registry, mind_root=temp_mind_root)

        result = await registry.execute("token_stats", {"period": "all"})
        assert "Token Stats" in result
        assert "API calls" in result
        assert "2" in result  # 2 API calls
        assert "minimax-m27" in result
        assert "kimi-k2" in result

    @pytest.mark.asyncio
    async def test_period_filter(self, temp_mind_root):
        # Write a record from "the past"
        token_log = Path(temp_mind_root) / "data" / "token_usage.jsonl"
        old_record = {
            "timestamp": "2020-01-01T00:00:00",
            "session_id": "old",
            "model": "test",
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 0,
            "latency_ms": 1000,
            "estimated_cost_usd": 0.001,
            "task_summary": "old task",
        }
        with open(token_log, "w") as f:
            f.write(json.dumps(old_record) + "\n")

        registry = ToolRegistry()
        register_resource_tools(registry, mind_root=temp_mind_root)

        result = await registry.execute("token_stats", {"period": "today"})
        assert "No token usage records" in result


class TestSessionStats:
    @pytest.mark.asyncio
    async def test_empty_sessions(self, registry_with_resource_tools):
        result = await registry_with_resource_tools.execute("session_stats", {})
        assert "No session log files" in result

    @pytest.mark.asyncio
    async def test_with_session_data(self, temp_mind_root):
        # Write a session log
        session_dir = Path(temp_mind_root) / "data" / "sessions"
        session_file = session_dir / "test-sess.jsonl"
        turns = [
            {"timestamp": "2026-04-02T10:00:00", "session_id": "test-sess", "turn": 1, "type": "user", "model": "m27", "tokens": {}, "tools_used": [], "duration_ms": 0},
            {"timestamp": "2026-04-02T10:00:05", "session_id": "test-sess", "turn": 2, "type": "assistant", "model": "m27", "tokens": {"input": 100, "output": 50}, "tools_used": [], "duration_ms": 2000},
            {"timestamp": "2026-04-02T10:00:07", "session_id": "test-sess", "turn": 3, "type": "tool_call", "model": "m27", "tokens": {}, "tools_used": ["bash", "memory_search"], "duration_ms": 500},
        ]
        with open(session_file, "w") as f:
            for t in turns:
                f.write(json.dumps(t) + "\n")

        registry = ToolRegistry()
        register_resource_tools(registry, mind_root=temp_mind_root)

        # Aggregate stats
        result = await registry.execute("session_stats", {})
        assert "Session Stats" in result
        assert "1" in result  # 1 session

        # Specific session
        result = await registry.execute("session_stats", {"session_id": "test-sess"})
        assert "test-sess" in result
        assert "bash" in result
        assert "memory_search" in result

    @pytest.mark.asyncio
    async def test_nonexistent_session(self, temp_mind_root):
        # Create at least one session file so the dir isn't empty
        session_dir = Path(temp_mind_root) / "data" / "sessions"
        dummy = session_dir / "exists.jsonl"
        dummy.write_text('{"type":"user"}\n')

        registry = ToolRegistry()
        register_resource_tools(registry, mind_root=temp_mind_root)

        result = await registry.execute("session_stats", {"session_id": "nope"})
        assert "not found" in result
