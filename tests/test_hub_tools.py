"""
Tests for aiciv_mind.tools.hub_tools — Hub connectivity tools.

Covers: registration with/without suite_client, hub_post, hub_reply, hub_read,
hub_list_rooms, hub_queue_read handlers (success and error paths).

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_hub_tools.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.hub_tools import register_hub_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_suite_client():
    """Create a mock SuiteClient with an async mock HubClient."""
    suite = MagicMock()
    suite.hub = MagicMock()
    suite.hub.create_thread = AsyncMock()
    suite.hub.reply_to_thread = AsyncMock()
    suite.hub.list_threads = AsyncMock()
    suite.hub.list_rooms = AsyncMock()
    return suite


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_hub_tools_registered_when_suite_client_provided():
    """Hub tools appear in registry when suite_client is passed."""
    suite = _make_mock_suite_client()
    registry = ToolRegistry.default(suite_client=suite)
    names = registry.names()
    assert "hub_post" in names
    assert "hub_reply" in names
    assert "hub_read" in names


def test_hub_tools_not_registered_when_suite_client_is_none():
    """Hub tools must NOT appear when suite_client is None."""
    registry = ToolRegistry.default(suite_client=None)
    names = registry.names()
    assert "hub_post" not in names
    assert "hub_reply" not in names
    assert "hub_read" not in names


# ---------------------------------------------------------------------------
# hub_post tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hub_post_success():
    suite = _make_mock_suite_client()
    suite.hub.create_thread.return_value = {"id": "thread-123", "title": "Test"}

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_post", {
        "room_id": "room-abc",
        "title": "Hello World",
        "body": "This is a test post",
    })

    assert "Posted thread 'Hello World' to room room-abc" in result
    assert "thread-123" in result
    suite.hub.create_thread.assert_awaited_once_with("room-abc", "Hello World", "This is a test post")


@pytest.mark.asyncio
async def test_hub_post_error():
    suite = _make_mock_suite_client()
    suite.hub.create_thread.side_effect = ConnectionError("Hub unreachable")

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_post", {
        "room_id": "room-abc",
        "title": "Fail",
        "body": "Should fail",
    })

    assert result.startswith("ERROR: Hub post failed: ConnectionError:")
    assert "Hub unreachable" in result


# ---------------------------------------------------------------------------
# hub_reply tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hub_reply_success():
    suite = _make_mock_suite_client()
    suite.hub.reply_to_thread.return_value = {"id": "reply-456"}

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_reply", {
        "thread_id": "thread-123",
        "body": "Great discussion!",
    })

    assert result == "Replied to thread thread-123"
    suite.hub.reply_to_thread.assert_awaited_once_with("thread-123", "Great discussion!")


@pytest.mark.asyncio
async def test_hub_reply_error():
    suite = _make_mock_suite_client()
    suite.hub.reply_to_thread.side_effect = RuntimeError("Auth expired")

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_reply", {
        "thread_id": "thread-123",
        "body": "This will fail",
    })

    assert result.startswith("ERROR: Hub reply failed: RuntimeError:")
    assert "Auth expired" in result


# ---------------------------------------------------------------------------
# hub_read tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hub_read_returns_formatted_threads():
    suite = _make_mock_suite_client()
    suite.hub.list_threads.return_value = [
        {"id": "t-1", "title": "First Thread", "author": "acg"},
        {"id": "t-2", "title": "Second Thread", "author": "weaver"},
        {"id": "t-3", "title": "Third Thread", "author": "synth"},
    ]

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_read", {"room_id": "room-xyz"})

    assert "**First Thread**" in result
    assert "t-1" in result
    assert "acg" in result
    assert "**Second Thread**" in result
    assert "weaver" in result
    assert "**Third Thread**" in result
    suite.hub.list_threads.assert_awaited_once_with("room-xyz")


@pytest.mark.asyncio
async def test_hub_read_respects_limit():
    suite = _make_mock_suite_client()
    suite.hub.list_threads.return_value = [
        {"id": f"t-{i}", "title": f"Thread {i}", "author": "acg"}
        for i in range(20)
    ]

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_read", {"room_id": "room-xyz", "limit": 3})

    lines = [l for l in result.splitlines() if l.startswith("- ")]
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_hub_read_empty():
    suite = _make_mock_suite_client()
    suite.hub.list_threads.return_value = []

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_read", {"room_id": "room-xyz"})

    assert result == "No threads found."


@pytest.mark.asyncio
async def test_hub_read_error():
    suite = _make_mock_suite_client()
    suite.hub.list_threads.side_effect = TimeoutError("Network timeout")

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_read", {"room_id": "room-xyz"})

    assert result.startswith("ERROR: Hub read failed: TimeoutError:")
    assert "Network timeout" in result


# ---------------------------------------------------------------------------
# Tool definition validation
# ---------------------------------------------------------------------------


def test_hub_tool_definitions_have_required_keys():
    """All hub tool definitions must have name, description, and input_schema."""
    suite = _make_mock_suite_client()
    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    for tool_def in registry.build_anthropic_tools():
        assert "name" in tool_def, f"Missing 'name' in {tool_def}"
        assert "description" in tool_def, f"Missing 'description' in {tool_def}"
        assert "input_schema" in tool_def, f"Missing 'input_schema' in {tool_def}"
        schema = tool_def["input_schema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_hub_read_is_read_only():
    """hub_read should be marked read_only; hub_post and hub_reply should not."""
    suite = _make_mock_suite_client()
    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    assert registry.is_read_only("hub_read") is True
    assert registry.is_read_only("hub_post") is False
    assert registry.is_read_only("hub_reply") is False


# ---------------------------------------------------------------------------
# hub_list_rooms tests
# ---------------------------------------------------------------------------


def test_hub_list_rooms_registered():
    """hub_list_rooms appears in registry when suite_client is provided."""
    suite = _make_mock_suite_client()
    registry = ToolRegistry()
    register_hub_tools(registry, suite)
    assert "hub_list_rooms" in registry.names()


@pytest.mark.asyncio
async def test_hub_list_rooms_success():
    suite = _make_mock_suite_client()
    suite.hub.list_rooms.return_value = [
        {"id": "room-1", "slug": "general", "room_type": "discussion"},
        {"id": "room-2", "slug": "research", "room_type": "discussion"},
    ]

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_list_rooms", {"group_id": "grp-abc"})

    assert "#general" in result
    assert "room-1" in result
    assert "#research" in result
    assert "room-2" in result
    suite.hub.list_rooms.assert_awaited_once_with("grp-abc")


@pytest.mark.asyncio
async def test_hub_list_rooms_empty():
    suite = _make_mock_suite_client()
    suite.hub.list_rooms.return_value = []

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_list_rooms", {"group_id": "grp-abc"})
    assert "No rooms found" in result


@pytest.mark.asyncio
async def test_hub_list_rooms_error():
    suite = _make_mock_suite_client()
    suite.hub.list_rooms.side_effect = ConnectionError("Network down")

    registry = ToolRegistry()
    register_hub_tools(registry, suite)

    result = await registry.execute("hub_list_rooms", {"group_id": "grp-abc"})
    assert "ERROR" in result
    assert "Network down" in result


def test_hub_list_rooms_is_read_only():
    suite = _make_mock_suite_client()
    registry = ToolRegistry()
    register_hub_tools(registry, suite)
    assert registry.is_read_only("hub_list_rooms") is True


# ---------------------------------------------------------------------------
# hub_queue_read tests
# ---------------------------------------------------------------------------


def test_hub_queue_read_registered_with_queue_path(tmp_path):
    """hub_queue_read appears in registry when queue_path is provided."""
    suite = _make_mock_suite_client()
    registry = ToolRegistry()
    register_hub_tools(registry, suite, queue_path=str(tmp_path / "q.jsonl"))
    assert "hub_queue_read" in registry.names()


def test_hub_queue_read_not_registered_without_queue_path():
    """hub_queue_read is NOT registered when queue_path is None."""
    suite = _make_mock_suite_client()
    registry = ToolRegistry()
    register_hub_tools(registry, suite, queue_path=None)
    assert "hub_queue_read" not in registry.names()


@pytest.mark.asyncio
async def test_hub_queue_read_no_file(tmp_path):
    """hub_queue_read returns message when queue file doesn't exist."""
    suite = _make_mock_suite_client()
    registry = ToolRegistry()
    qpath = str(tmp_path / "nonexistent.jsonl")
    register_hub_tools(registry, suite, queue_path=qpath)

    result = await registry.execute("hub_queue_read", {})
    assert "No queue file" in result


@pytest.mark.asyncio
async def test_hub_queue_read_returns_unprocessed(tmp_path):
    """hub_queue_read returns unprocessed events and marks them processed."""
    suite = _make_mock_suite_client()
    qpath = tmp_path / "queue.jsonl"

    events = [
        {"event": "new_thread", "room_id": "r1", "thread_id": "t1",
         "title": "Hello", "created_by": "synth", "processed": False},
        {"event": "new_thread", "room_id": "r1", "thread_id": "t2",
         "title": "Already Read", "created_by": "acg", "processed": True},
    ]
    qpath.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    registry = ToolRegistry()
    register_hub_tools(registry, suite, queue_path=str(qpath))

    result = await registry.execute("hub_queue_read", {})
    assert "1 unprocessed" in result
    assert "Hello" in result
    assert "Already Read" not in result

    # Verify events are now marked processed
    lines = qpath.read_text().strip().splitlines()
    for line in lines:
        evt = json.loads(line)
        assert evt["processed"] is True
