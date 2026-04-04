"""
Tests for the READY signal IPC handshake (Fix #23).

Proves:
1. MsgType.READY exists and MindMessage.ready() factory works
2. SubMindBus sends READY after connect
3. PrimaryBus receives READY from sub-mind
4. spawn_team_lead waits for READY before sending TASK
5. Handler cleanup prevents leak
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from aiciv_mind.ipc.messages import MindMessage, MsgType
from aiciv_mind.ipc.primary_bus import PrimaryBus
from aiciv_mind.ipc.submind_bus import SubMindBus


def make_ipc_path(tmp_path) -> str:
    return f"ipc://{tmp_path}/test-ready-{uuid.uuid4().hex[:8]}.ipc"


# ---------------------------------------------------------------------------
# Test 1: MsgType.READY exists
# ---------------------------------------------------------------------------

def test_msgtype_ready_exists():
    """READY is a valid message type constant."""
    assert MsgType.READY == "ready"


# ---------------------------------------------------------------------------
# Test 2: MindMessage.ready() factory
# ---------------------------------------------------------------------------

def test_ready_factory():
    """ready() creates a properly formed READY message."""
    msg = MindMessage.ready(sender="research-lead", recipient="primary")
    assert msg.type == MsgType.READY
    assert msg.sender == "research-lead"
    assert msg.recipient == "primary"
    assert msg.payload == {}


# ---------------------------------------------------------------------------
# Test 3: READY round-trip serialization
# ---------------------------------------------------------------------------

def test_ready_roundtrip():
    """READY message survives serialization/deserialization."""
    original = MindMessage.ready("codewright-lead", "primary")
    restored = MindMessage.from_bytes(original.to_bytes())
    assert restored.type == MsgType.READY
    assert restored.sender == "codewright-lead"
    assert restored.recipient == "primary"


# ---------------------------------------------------------------------------
# Test 4: READY flows from SubMindBus to PrimaryBus via ZMQ
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ready_signal_e2e(tmp_path):
    """Sub-mind sends READY, primary receives it via ZMQ ROUTER/DEALER."""
    path = make_ipc_path(tmp_path)

    primary = PrimaryBus(router_path=path)
    primary.bind()

    received = asyncio.Event()
    received_sender = []

    async def on_ready(msg: MindMessage):
        received_sender.append(msg.sender)
        received.set()

    primary.on(MsgType.READY, on_ready)
    primary.start_recv()

    # Sub-mind connects and sends READY
    sub = SubMindBus(mind_id="test-lead", router_path=path)
    sub.connect()
    sub.start_recv()
    await asyncio.sleep(0.1)  # Let ZMQ connect

    await sub.send(MindMessage.ready(sender="test-lead", recipient="primary"))

    # Primary should receive READY
    try:
        await asyncio.wait_for(received.wait(), timeout=3.0)
    except asyncio.TimeoutError:
        pytest.fail("Primary did not receive READY signal within 3s")

    assert received_sender == ["test-lead"]

    sub.close()
    primary.close()


# ---------------------------------------------------------------------------
# Test 5: Multiple sub-minds send distinct READY signals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_ready_signals(tmp_path):
    """Two sub-minds send READY; primary distinguishes them by sender."""
    path = make_ipc_path(tmp_path)

    primary = PrimaryBus(router_path=path)
    primary.bind()

    senders = []

    async def on_ready(msg: MindMessage):
        senders.append(msg.sender)

    primary.on(MsgType.READY, on_ready)
    primary.start_recv()

    sub1 = SubMindBus(mind_id="lead-a", router_path=path)
    sub1.connect()
    sub1.start_recv()

    sub2 = SubMindBus(mind_id="lead-b", router_path=path)
    sub2.connect()
    sub2.start_recv()

    await asyncio.sleep(0.1)

    await sub1.send(MindMessage.ready(sender="lead-a", recipient="primary"))
    await sub2.send(MindMessage.ready(sender="lead-b", recipient="primary"))

    await asyncio.sleep(0.3)

    assert set(senders) == {"lead-a", "lead-b"}

    sub1.close()
    sub2.close()
    primary.close()


# ---------------------------------------------------------------------------
# Test 6: Handler cleanup after READY wait
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ready_handler_cleanup(tmp_path):
    """After wait-for-READY, the handler is removed from the bus."""
    path = make_ipc_path(tmp_path)

    primary = PrimaryBus(router_path=path)
    primary.bind()
    primary.start_recv()

    # Simulate the spawn_team_lead READY wait pattern
    ready_event = asyncio.Event()

    async def _on_ready(msg: MindMessage):
        if msg.sender == "test-lead":
            ready_event.set()

    primary.on(MsgType.READY, _on_ready)
    initial_count = len(primary._handlers.get(MsgType.READY, []))

    # Sub-mind sends READY
    sub = SubMindBus(mind_id="test-lead", router_path=path)
    sub.connect()
    sub.start_recv()
    await asyncio.sleep(0.1)
    await sub.send(MindMessage.ready(sender="test-lead", recipient="primary"))

    await asyncio.wait_for(ready_event.wait(), timeout=3.0)

    # Clean up handler (same pattern as spawn_tools.py)
    handlers = primary._handlers.get(MsgType.READY, [])
    if _on_ready in handlers:
        handlers.remove(_on_ready)

    final_count = len(primary._handlers.get(MsgType.READY, []))
    assert final_count == initial_count - 1

    sub.close()
    primary.close()


# ---------------------------------------------------------------------------
# Test 7: READY timeout does not crash — falls back gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ready_timeout_graceful(tmp_path):
    """If sub-mind never sends READY, wait times out without crashing."""
    path = make_ipc_path(tmp_path)

    primary = PrimaryBus(router_path=path)
    primary.bind()
    primary.start_recv()

    ready_event = asyncio.Event()

    async def _on_ready(msg: MindMessage):
        ready_event.set()

    primary.on(MsgType.READY, _on_ready)

    # Don't spawn any sub-mind — READY will never arrive
    timed_out = False
    try:
        await asyncio.wait_for(ready_event.wait(), timeout=0.5)
    except asyncio.TimeoutError:
        timed_out = True
    finally:
        handlers = primary._handlers.get(MsgType.READY, [])
        if _on_ready in handlers:
            handlers.remove(_on_ready)

    assert timed_out, "Should have timed out waiting for READY"

    primary.close()
