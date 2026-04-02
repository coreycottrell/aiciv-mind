"""
Tests for aiciv_mind.ipc — MindMessage, PrimaryBus, SubMindBus.

Unit tests cover MindMessage serialization and all factory methods.
The integration test (test_router_dealer_message_exchange) uses real ZMQ
IPC sockets via a tmp_path fixture to ensure isolation between test runs.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from aiciv_mind.ipc import MindCompletionEvent, MindMessage, MsgType, PrimaryBus, SubMindBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ipc_path(tmp_path) -> str:
    """Return a unique IPC socket path rooted in pytest's tmp_path."""
    return f"ipc://{tmp_path}/test-router-{uuid.uuid4().hex[:8]}.ipc"


# ---------------------------------------------------------------------------
# Test 1: MindMessage round-trip serialization
# ---------------------------------------------------------------------------


def test_mindmessage_roundtrip() -> None:
    """to_bytes() followed by from_bytes() preserves all fields exactly."""
    original = MindMessage(
        type=MsgType.TASK,
        sender="primary",
        recipient="research-lead",
        id="fixed-id-123",
        timestamp=1234567890.123,
        payload={"task_id": "t1", "objective": "do research", "context": {"key": "val"}},
    )

    wire = original.to_bytes()
    assert isinstance(wire, bytes)

    restored = MindMessage.from_bytes(wire)

    assert restored.type == original.type
    assert restored.sender == original.sender
    assert restored.recipient == original.recipient
    assert restored.id == original.id
    assert restored.timestamp == pytest.approx(original.timestamp)
    assert restored.payload == original.payload


# ---------------------------------------------------------------------------
# Test 2: MindMessage.task() factory
# ---------------------------------------------------------------------------


def test_mindmessage_task_factory() -> None:
    """MindMessage.task() produces correct type, sender, recipient, and payload keys."""
    msg = MindMessage.task(
        sender="primary",
        recipient="research-lead",
        task_id="task-abc",
        objective="Analyze competitive landscape",
        context={"depth": "deep"},
    )

    assert msg.type == MsgType.TASK
    assert msg.sender == "primary"
    assert msg.recipient == "research-lead"
    assert msg.payload["task_id"] == "task-abc"
    assert msg.payload["objective"] == "Analyze competitive landscape"
    assert msg.payload["context"] == {"depth": "deep"}
    # Auto-generated fields are present
    assert msg.id
    assert msg.timestamp > 0


def test_mindmessage_task_factory_default_context() -> None:
    """MindMessage.task() with no context defaults to empty dict."""
    msg = MindMessage.task("primary", "infra-lead", "t2", "deploy service")
    assert msg.payload["context"] == {}


# ---------------------------------------------------------------------------
# Test 3: MindMessage.result() factory
# ---------------------------------------------------------------------------


def test_mindmessage_result_factory() -> None:
    """MindMessage.result() has correct type and all payload keys."""
    msg = MindMessage.result(
        sender="research-lead",
        recipient="primary",
        task_id="task-abc",
        result="Summary of findings.",
        success=True,
        error=None,
    )

    assert msg.type == MsgType.RESULT
    assert msg.sender == "research-lead"
    assert msg.recipient == "primary"
    assert msg.payload["task_id"] == "task-abc"
    assert msg.payload["result"] == "Summary of findings."
    assert msg.payload["success"] is True
    assert msg.payload["error"] is None


def test_mindmessage_result_factory_failure() -> None:
    """MindMessage.result() with success=False carries the error string."""
    msg = MindMessage.result(
        sender="infra-lead",
        recipient="primary",
        task_id="t9",
        result="",
        success=False,
        error="Connection refused",
    )

    assert msg.payload["success"] is False
    assert msg.payload["error"] == "Connection refused"


# ---------------------------------------------------------------------------
# Test 4: MindMessage.shutdown() factory
# ---------------------------------------------------------------------------


def test_mindmessage_shutdown_factory() -> None:
    """MindMessage.shutdown() has reason in payload; defaults to orchestrator_request."""
    msg_default = MindMessage.shutdown(sender="primary", recipient="research-lead")
    assert msg_default.type == MsgType.SHUTDOWN
    assert msg_default.payload["reason"] == "orchestrator_request"

    msg_custom = MindMessage.shutdown(
        sender="primary", recipient="research-lead", reason="task_complete"
    )
    assert msg_custom.payload["reason"] == "task_complete"


# ---------------------------------------------------------------------------
# Test 5: Full ROUTER/DEALER integration — bidirectional message exchange
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_dealer_message_exchange(tmp_path) -> None:
    """
    Integration test: primary (ROUTER) sends task to sub-mind (DEALER);
    sub-mind sends result back; both sides receive correctly.
    """
    ipc_path = make_ipc_path(tmp_path)

    primary = PrimaryBus(router_path=ipc_path)
    submind = SubMindBus(mind_id="test-mind", router_path=ipc_path)

    # Coordination events
    task_received_event = asyncio.Event()
    result_received_event = asyncio.Event()
    received_task: list[MindMessage] = []
    received_result: list[MindMessage] = []

    async def on_task(msg: MindMessage) -> None:
        received_task.append(msg)
        task_received_event.set()

    async def on_result(msg: MindMessage) -> None:
        received_result.append(msg)
        result_received_event.set()

    submind.on(MsgType.TASK, on_task)
    primary.on(MsgType.RESULT, on_result)

    primary.bind()
    submind.connect()

    primary.start_recv()
    submind.start_recv()

    # Give ZMQ a moment to complete the handshake
    await asyncio.sleep(0.05)

    # Primary dispatches task to sub-mind
    outbound_task = MindMessage.task(
        sender="primary",
        recipient="test-mind",
        task_id="integration-task-1",
        objective="Run a test",
        context={"priority": "high"},
    )
    await primary.send(outbound_task)

    # Wait for sub-mind to receive the task (1-second timeout)
    await asyncio.wait_for(task_received_event.wait(), timeout=1.0)

    assert len(received_task) == 1
    task_msg = received_task[0]
    assert task_msg.type == MsgType.TASK
    assert task_msg.sender == "primary"
    assert task_msg.recipient == "test-mind"
    assert task_msg.payload["task_id"] == "integration-task-1"
    assert task_msg.payload["objective"] == "Run a test"
    assert task_msg.payload["context"]["priority"] == "high"

    # Sub-mind sends result back
    outbound_result = MindMessage.result(
        sender="test-mind",
        recipient="primary",
        task_id="integration-task-1",
        result="Test passed successfully.",
        success=True,
    )
    await submind.send(outbound_result)

    # Wait for primary to receive the result
    await asyncio.wait_for(result_received_event.wait(), timeout=1.0)

    assert len(received_result) == 1
    result_msg = received_result[0]
    assert result_msg.type == MsgType.RESULT
    assert result_msg.sender == "test-mind"
    assert result_msg.recipient == "primary"
    assert result_msg.payload["task_id"] == "integration-task-1"
    assert result_msg.payload["result"] == "Test passed successfully."
    assert result_msg.payload["success"] is True

    # Cleanup
    primary.close()
    submind.close()
    # Allow cancelled tasks to finalize
    await asyncio.sleep(0.01)


# ---------------------------------------------------------------------------
# Test 6: Unknown message type does not crash; no handler called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_primary_bus_unknown_message_type(tmp_path) -> None:
    """A message with an unregistered type is silently dropped — no exception, no handler."""
    ipc_path = make_ipc_path(tmp_path)

    primary = PrimaryBus(router_path=ipc_path)
    submind = SubMindBus(mind_id="ghost-mind", router_path=ipc_path)

    called = []

    async def should_not_be_called(msg: MindMessage) -> None:
        called.append(msg)

    # Register handler for TASK only — not for "unknown_type"
    primary.on(MsgType.TASK, should_not_be_called)

    primary.bind()
    submind.connect()
    primary.start_recv()
    submind.start_recv()

    await asyncio.sleep(0.05)

    # Send a message with an unknown type directly (bypass factory)
    unknown_msg = MindMessage(
        type="unknown_type",
        sender="ghost-mind",
        recipient="primary",
        payload={"data": "mystery"},
    )
    await submind.send(unknown_msg)

    # Give it time to be processed
    await asyncio.sleep(0.1)

    # No handler should have been called
    assert called == []

    primary.close()
    submind.close()
    await asyncio.sleep(0.01)


# ---------------------------------------------------------------------------
# Test 7: from_bytes with missing optional fields uses defaults
# ---------------------------------------------------------------------------


def test_mindmessage_missing_fields() -> None:
    """from_bytes with missing id/timestamp/payload uses generated defaults."""
    import json

    minimal_json = json.dumps(
        {
            "type": MsgType.HEARTBEAT,
            "sender": "research-lead",
            "recipient": "primary",
            # id, timestamp, payload intentionally omitted
        }
    ).encode("utf-8")

    msg = MindMessage.from_bytes(minimal_json)

    assert msg.type == MsgType.HEARTBEAT
    assert msg.sender == "research-lead"
    assert msg.recipient == "primary"
    # id should be auto-generated (valid UUID format)
    assert len(msg.id) == 36  # standard UUID string length
    # timestamp should be recent
    assert msg.timestamp == pytest.approx(time.time(), abs=5.0)
    # payload defaults to empty dict
    assert msg.payload == {}


# ---------------------------------------------------------------------------
# Additional factory coverage
# ---------------------------------------------------------------------------


def test_mindmessage_heartbeat_factories() -> None:
    """heartbeat and heartbeat_ack factories produce correct types."""
    hb = MindMessage.heartbeat("primary", "infra-lead")
    assert hb.type == MsgType.HEARTBEAT
    assert hb.sender == "primary"
    assert hb.recipient == "infra-lead"
    assert hb.payload == {}

    ack = MindMessage.heartbeat_ack("infra-lead", "primary")
    assert ack.type == MsgType.HEARTBEAT_ACK


def test_mindmessage_status_factory() -> None:
    """MindMessage.status() carries task_id, progress, and optional pct."""
    msg = MindMessage.status(
        sender="research-lead",
        recipient="primary",
        task_id="t5",
        progress="Searching web",
        pct=40,
    )
    assert msg.type == MsgType.STATUS
    assert msg.payload["task_id"] == "t5"
    assert msg.payload["progress"] == "Searching web"
    assert msg.payload["pct"] == 40

    msg_no_pct = MindMessage.status("research-lead", "primary", "t6", "Processing")
    assert msg_no_pct.payload["pct"] is None


def test_mindmessage_log_factory() -> None:
    """MindMessage.log() carries level and message in payload."""
    msg = MindMessage.log(
        sender="infra-lead",
        recipient="primary",
        level="WARNING",
        message="Disk usage above 80%",
    )
    assert msg.type == MsgType.LOG
    assert msg.payload["level"] == "WARNING"
    assert msg.payload["message"] == "Disk usage above 80%"


def test_mindmessage_shutdown_ack_factory() -> None:
    """MindMessage.shutdown_ack() includes mind_id in payload."""
    msg = MindMessage.shutdown_ack(
        sender="research-lead",
        recipient="primary",
        mind_id="research-lead",
    )
    assert msg.type == MsgType.SHUTDOWN_ACK
    assert msg.payload["mind_id"] == "research-lead"


# ---------------------------------------------------------------------------
# MindCompletionEvent tests
# ---------------------------------------------------------------------------


def test_completion_event_to_dict() -> None:
    """MindCompletionEvent.to_dict() serializes all fields."""
    event = MindCompletionEvent(
        mind_id="research-lead",
        task_id="task-42",
        status="success",
        summary="Found 3 relevant papers",
        result="Detailed analysis of papers...",
        tokens_used=1240,
        tool_calls=5,
        duration_ms=3200,
        tools_used=["web_search", "memory_write"],
        error=None,
    )
    d = event.to_dict()
    assert d["mind_id"] == "research-lead"
    assert d["task_id"] == "task-42"
    assert d["status"] == "success"
    assert d["summary"] == "Found 3 relevant papers"
    assert d["tokens_used"] == 1240
    assert d["tool_calls"] == 5
    assert d["duration_ms"] == 3200
    assert d["tools_used"] == ["web_search", "memory_write"]
    assert d["error"] is None


def test_completion_event_from_dict() -> None:
    """MindCompletionEvent.from_dict() round-trips through to_dict()."""
    original = MindCompletionEvent(
        mind_id="infra-lead",
        task_id="deploy-99",
        status="error",
        summary="Deploy failed on step 3",
        result="",
        tokens_used=500,
        tool_calls=2,
        duration_ms=8000,
        tools_used=["bash"],
        error="Connection refused",
    )
    restored = MindCompletionEvent.from_dict(original.to_dict())
    assert restored.mind_id == original.mind_id
    assert restored.task_id == original.task_id
    assert restored.status == original.status
    assert restored.summary == original.summary
    assert restored.error == original.error
    assert restored.tools_used == original.tools_used


def test_completion_event_from_dict_defaults() -> None:
    """from_dict() fills defaults for optional fields."""
    minimal = {
        "mind_id": "test-mind",
        "task_id": "t1",
        "status": "success",
        "summary": "Done",
    }
    event = MindCompletionEvent.from_dict(minimal)
    assert event.result == ""
    assert event.tokens_used == 0
    assert event.tool_calls == 0
    assert event.duration_ms == 0
    assert event.tools_used == []
    assert event.error is None


def test_completion_event_context_line() -> None:
    """context_line() produces a compact one-liner for coordinator injection."""
    event = MindCompletionEvent(
        mind_id="memory-lead",
        task_id="t5",
        status="success",
        summary="Consolidated 12 stale memories",
        tokens_used=800,
        tool_calls=3,
        duration_ms=1500,
    )
    line = event.context_line()
    assert "[memory-lead]" in line
    assert "SUCCESS" in line
    assert "Consolidated 12 stale memories" in line
    assert "800t" in line
    assert "3 tools" in line
    assert "1500ms" in line


def test_mindmessage_completion_factory() -> None:
    """MindMessage.completion() wraps a MindCompletionEvent in a COMPLETION message."""
    event = MindCompletionEvent(
        mind_id="research-lead",
        task_id="task-77",
        status="partial",
        summary="Found 2 of 5 requested items",
        tokens_used=600,
        tool_calls=4,
        duration_ms=2000,
    )
    msg = MindMessage.completion(
        sender="research-lead",
        recipient="primary",
        event=event,
    )
    assert msg.type == MsgType.COMPLETION
    assert msg.sender == "research-lead"
    assert msg.recipient == "primary"
    assert msg.payload["mind_id"] == "research-lead"
    assert msg.payload["task_id"] == "task-77"
    assert msg.payload["status"] == "partial"

    # Verify round-trip through MindMessage serialization
    wire = msg.to_bytes()
    restored_msg = MindMessage.from_bytes(wire)
    restored_event = MindCompletionEvent.from_dict(restored_msg.payload)
    assert restored_event.mind_id == "research-lead"
    assert restored_event.summary == "Found 2 of 5 requested items"
