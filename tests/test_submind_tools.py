"""
Tests for aiciv_mind.tools.submind_tools — spawn_submind and send_to_submind.

All spawner and bus interactions are mocked. No real tmux or ZMQ required.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_submind_tools.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.ipc.messages import MindMessage, MsgType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_spawner():
    """A mocked SubMindSpawner."""
    spawner = MagicMock()
    handle = MagicMock()
    handle.pane_id = "%42"
    handle.mind_id = "research-lead"
    spawner.spawn.return_value = handle
    return spawner


@pytest.fixture
def mock_bus():
    """A mocked PrimaryBus with async send."""
    bus = MagicMock()
    bus.send = AsyncMock()
    bus._handlers = {}

    # Track registered handlers so tests can fire them
    _registered_handlers: dict[str, list] = {}

    def on_side_effect(msg_type, handler):
        _registered_handlers.setdefault(msg_type, []).append(handler)

    bus.on = MagicMock(side_effect=on_side_effect)
    bus._registered_handlers = _registered_handlers
    return bus


@pytest.fixture
def registry_with_submind_tools(mock_spawner, mock_bus):
    """A ToolRegistry with submind tools registered."""
    from aiciv_mind.tools.submind_tools import register_submind_tools
    registry = ToolRegistry()
    register_submind_tools(registry, spawner=mock_spawner, bus=mock_bus, primary_mind_id="primary")
    return registry


# ---------------------------------------------------------------------------
# Test: spawn_submind calls spawner.spawn() and returns success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_submind_success(registry_with_submind_tools, mock_spawner):
    """spawn_submind calls spawner.spawn() and returns a success string with pane_id."""
    result = await registry_with_submind_tools.execute(
        "spawn_submind",
        {"mind_id": "research-lead", "manifest_path": "/tmp/research.yaml"},
    )

    mock_spawner.spawn.assert_called_once_with("research-lead", "/tmp/research.yaml")
    assert "Spawned sub-mind 'research-lead'" in result
    assert "%42" in result


@pytest.mark.asyncio
async def test_spawn_submind_error(registry_with_submind_tools, mock_spawner):
    """spawn_submind returns an error string when spawner raises."""
    mock_spawner.spawn.side_effect = RuntimeError("tmux not available")

    result = await registry_with_submind_tools.execute(
        "spawn_submind",
        {"mind_id": "bad-mind", "manifest_path": "/tmp/bad.yaml"},
    )

    assert "ERROR:" in result
    assert "RuntimeError" in result
    assert "tmux not available" in result


@pytest.mark.asyncio
async def test_spawn_submind_missing_mind_id(registry_with_submind_tools):
    """spawn_submind returns error when mind_id is missing."""
    result = await registry_with_submind_tools.execute(
        "spawn_submind",
        {"mind_id": "", "manifest_path": "/tmp/test.yaml"},
    )
    assert "ERROR: No mind_id provided" in result


@pytest.mark.asyncio
async def test_spawn_submind_missing_manifest_path(registry_with_submind_tools):
    """spawn_submind returns error when manifest_path is missing."""
    result = await registry_with_submind_tools.execute(
        "spawn_submind",
        {"mind_id": "test-mind", "manifest_path": ""},
    )
    assert "ERROR: No manifest_path provided" in result


# ---------------------------------------------------------------------------
# Test: send_to_submind sends correct MindMessage and returns result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_to_submind_success(mock_bus):
    """send_to_submind sends a TASK message and returns the result from the bus."""
    from aiciv_mind.tools.submind_tools import register_submind_tools

    registry = ToolRegistry()
    register_submind_tools(registry, spawner=MagicMock(), bus=mock_bus, primary_mind_id="primary")

    # When bus.send() is called, simulate the sub-mind responding immediately
    async def fake_send(msg):
        # Extract the task_id from the sent message
        task_id = msg.payload["task_id"]
        # Fire all registered RESULT handlers with a matching response
        result_msg = MindMessage.result(
            sender="research-lead",
            recipient="primary",
            task_id=task_id,
            result="Research complete: 42 papers found",
        )
        for handler in mock_bus._registered_handlers.get(MsgType.RESULT, []):
            await handler(result_msg)

    mock_bus.send = AsyncMock(side_effect=fake_send)

    result = await registry.execute(
        "send_to_submind",
        {"mind_id": "research-lead", "task": "Find papers on consciousness", "timeout": 5},
    )

    assert result == "Research complete: 42 papers found"


@pytest.mark.asyncio
async def test_send_to_submind_sends_correct_message(mock_bus):
    """send_to_submind constructs the correct MindMessage.task."""
    from aiciv_mind.tools.submind_tools import register_submind_tools

    registry = ToolRegistry()
    register_submind_tools(registry, spawner=MagicMock(), bus=mock_bus, primary_mind_id="primary")

    sent_messages = []

    async def capture_send(msg):
        sent_messages.append(msg)
        # Fire result handler so it doesn't timeout
        task_id = msg.payload["task_id"]
        result_msg = MindMessage.result("target", "primary", task_id, "ok")
        for handler in mock_bus._registered_handlers.get(MsgType.RESULT, []):
            await handler(result_msg)

    mock_bus.send = AsyncMock(side_effect=capture_send)

    await registry.execute(
        "send_to_submind",
        {"mind_id": "target", "task": "Do work"},
    )

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert msg.type == MsgType.TASK
    assert msg.sender == "primary"
    assert msg.recipient == "target"
    assert msg.payload["objective"] == "Do work"
    assert msg.payload["task_id"].startswith("task-")


# ---------------------------------------------------------------------------
# Test: send_to_submind timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_to_submind_timeout(mock_bus):
    """send_to_submind returns an error string on timeout."""
    from aiciv_mind.tools.submind_tools import register_submind_tools

    registry = ToolRegistry()
    register_submind_tools(registry, spawner=MagicMock(), bus=mock_bus, primary_mind_id="primary")

    # bus.send succeeds but no result ever comes back
    mock_bus.send = AsyncMock()

    result = await registry.execute(
        "send_to_submind",
        {"mind_id": "slow-mind", "task": "Take forever", "timeout": 1},
    )

    assert "ERROR: Timeout waiting for slow-mind" in result
    assert "task-" in result


@pytest.mark.asyncio
async def test_send_to_submind_ignores_wrong_task_id(mock_bus):
    """send_to_submind ignores RESULT messages with non-matching task_id."""
    from aiciv_mind.tools.submind_tools import register_submind_tools

    registry = ToolRegistry()
    register_submind_tools(registry, spawner=MagicMock(), bus=mock_bus, primary_mind_id="primary")

    async def fake_send(msg):
        # Send a result with a WRONG task_id — should be ignored
        wrong_result = MindMessage.result(
            sender="research-lead",
            recipient="primary",
            task_id="task-wrong-id",
            result="Wrong task result",
        )
        for handler in mock_bus._registered_handlers.get(MsgType.RESULT, []):
            await handler(wrong_result)
        # Don't send the correct result — should timeout

    mock_bus.send = AsyncMock(side_effect=fake_send)

    result = await registry.execute(
        "send_to_submind",
        {"mind_id": "research-lead", "task": "Find papers", "timeout": 1},
    )

    assert "ERROR: Timeout" in result


@pytest.mark.asyncio
async def test_send_to_submind_missing_mind_id(mock_bus):
    """send_to_submind returns error when mind_id is empty."""
    from aiciv_mind.tools.submind_tools import register_submind_tools

    registry = ToolRegistry()
    register_submind_tools(registry, spawner=MagicMock(), bus=mock_bus, primary_mind_id="primary")

    result = await registry.execute(
        "send_to_submind",
        {"mind_id": "", "task": "Do something"},
    )
    assert "ERROR: No mind_id provided" in result


@pytest.mark.asyncio
async def test_send_to_submind_missing_task(mock_bus):
    """send_to_submind returns error when task is empty."""
    from aiciv_mind.tools.submind_tools import register_submind_tools

    registry = ToolRegistry()
    register_submind_tools(registry, spawner=MagicMock(), bus=mock_bus, primary_mind_id="primary")

    result = await registry.execute(
        "send_to_submind",
        {"mind_id": "research-lead", "task": ""},
    )
    assert "ERROR: No task provided" in result


# ---------------------------------------------------------------------------
# Test: tools registered when both spawner and bus are provided
# ---------------------------------------------------------------------------


def test_tools_registered_when_both_provided():
    """spawn_submind and send_to_submind are registered when spawner AND bus are provided."""
    spawner = MagicMock()
    bus = MagicMock()
    bus.on = MagicMock()

    registry = ToolRegistry.default(spawner=spawner, primary_bus=bus)

    names = registry.names()
    assert "spawn_submind" in names
    assert "send_to_submind" in names


# ---------------------------------------------------------------------------
# Test: tools NOT registered when spawner or bus is None
# ---------------------------------------------------------------------------


def test_tools_not_registered_when_spawner_is_none():
    """submind tools are not registered when spawner is None."""
    bus = MagicMock()
    bus.on = MagicMock()

    registry = ToolRegistry.default(spawner=None, primary_bus=bus)

    names = registry.names()
    assert "spawn_submind" not in names
    assert "send_to_submind" not in names


def test_tools_not_registered_when_bus_is_none():
    """submind tools are not registered when primary_bus is None."""
    spawner = MagicMock()

    registry = ToolRegistry.default(spawner=spawner, primary_bus=None)

    names = registry.names()
    assert "spawn_submind" not in names
    assert "send_to_submind" not in names


def test_tools_not_registered_when_both_none():
    """submind tools are not registered when both spawner and primary_bus are None."""
    registry = ToolRegistry.default(spawner=None, primary_bus=None)

    names = registry.names()
    assert "spawn_submind" not in names
    assert "send_to_submind" not in names


# ---------------------------------------------------------------------------
# Test: tool definitions have correct Anthropic format
# ---------------------------------------------------------------------------


def test_submind_tool_definitions_format():
    """spawn_submind and send_to_submind have proper Anthropic tool definitions."""
    from aiciv_mind.tools.submind_tools import register_submind_tools

    registry = ToolRegistry()
    register_submind_tools(
        registry,
        spawner=MagicMock(),
        bus=MagicMock(),
        primary_mind_id="primary",
    )

    tools = registry.build_anthropic_tools()
    for tool_def in tools:
        assert "name" in tool_def
        assert "description" in tool_def
        assert "input_schema" in tool_def
        schema = tool_def["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
