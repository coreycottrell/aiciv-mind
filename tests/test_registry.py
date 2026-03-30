"""Tests for aiciv_mind.registry — MindHandle and MindRegistry."""
from __future__ import annotations

import time

import pytest

from aiciv_mind.registry import MindHandle, MindRegistry, MindState


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------


def make_handle(mind_id: str, state: str = MindState.RUNNING) -> MindHandle:
    h = MindHandle(
        mind_id=mind_id,
        manifest_path=f"/tmp/{mind_id}.yaml",
        window_name=mind_id,
        pane_id="%99",
        pid=12345,
        zmq_identity=mind_id.encode(),
    )
    h.state = state
    return h


# ---------------------------------------------------------------------------
# Test: register and get
# ---------------------------------------------------------------------------


def test_register_and_get() -> None:
    """Register a handle, get by mind_id → returns the same handle."""
    registry = MindRegistry()
    handle = make_handle("alpha")
    registry.register(handle)

    result = registry.get("alpha")
    assert result is handle


# ---------------------------------------------------------------------------
# Test: get missing
# ---------------------------------------------------------------------------


def test_get_missing() -> None:
    """get() for an unknown mind_id returns None."""
    registry = MindRegistry()
    assert registry.get("nonexistent") is None


# ---------------------------------------------------------------------------
# Test: all_running
# ---------------------------------------------------------------------------


def test_all_running() -> None:
    """all_running() returns only handles with state RUNNING."""
    registry = MindRegistry()
    h_running = make_handle("running-mind", MindState.RUNNING)
    h_starting = make_handle("starting-mind", MindState.STARTING)
    h_stopped = make_handle("stopped-mind", MindState.STOPPED)

    registry.register(h_running)
    registry.register(h_starting)
    registry.register(h_stopped)

    running = registry.all_running()
    assert len(running) == 1
    assert running[0] is h_running


# ---------------------------------------------------------------------------
# Test: all_alive
# ---------------------------------------------------------------------------


def test_all_alive() -> None:
    """all_alive() returns STARTING and RUNNING handles only."""
    registry = MindRegistry()
    h_starting = make_handle("starting-mind", MindState.STARTING)
    h_running = make_handle("running-mind", MindState.RUNNING)
    h_stopping = make_handle("stopping-mind", MindState.STOPPING)
    h_stopped = make_handle("stopped-mind", MindState.STOPPED)
    h_crashed = make_handle("crashed-mind", MindState.CRASHED)

    for h in (h_starting, h_running, h_stopping, h_stopped, h_crashed):
        registry.register(h)

    alive = registry.all_alive()
    alive_ids = {h.mind_id for h in alive}

    assert alive_ids == {"starting-mind", "running-mind"}
    assert len(alive) == 2


# ---------------------------------------------------------------------------
# Test: mark_state
# ---------------------------------------------------------------------------


def test_mark_state() -> None:
    """mark_state() updates handle.state."""
    registry = MindRegistry()
    handle = make_handle("beta", MindState.RUNNING)
    registry.register(handle)

    registry.mark_state("beta", MindState.STOPPING)
    assert handle.state == MindState.STOPPING


def test_mark_state_unknown_raises() -> None:
    """mark_state() with unknown mind_id raises KeyError."""
    registry = MindRegistry()
    with pytest.raises(KeyError):
        registry.mark_state("ghost", MindState.STOPPED)


# ---------------------------------------------------------------------------
# Test: record_heartbeat
# ---------------------------------------------------------------------------


def test_record_heartbeat() -> None:
    """record_heartbeat() updates last_heartbeat to a recent monotonic time."""
    registry = MindRegistry()
    handle = make_handle("gamma")
    assert handle.last_heartbeat == 0.0
    registry.register(handle)

    before = time.monotonic()
    registry.record_heartbeat("gamma")
    after = time.monotonic()

    assert before <= handle.last_heartbeat <= after


def test_record_heartbeat_unknown_noop() -> None:
    """record_heartbeat() with unknown mind_id is a no-op (no exception)."""
    registry = MindRegistry()
    registry.record_heartbeat("ghost")  # should not raise


# ---------------------------------------------------------------------------
# Test: unresponsive — no heartbeat, uptime exceeds timeout
# ---------------------------------------------------------------------------


def test_unresponsive_no_heartbeat(monkeypatch) -> None:
    """
    A RUNNING handle with no heartbeat (last_heartbeat == 0) and uptime > timeout
    is included in unresponsive().
    """
    registry = MindRegistry()
    handle = make_handle("delta", MindState.RUNNING)
    # Backdate started_at so uptime is large
    handle.started_at = time.monotonic() - 30.0
    handle.last_heartbeat = 0.0
    registry.register(handle)

    result = registry.unresponsive(timeout_seconds=15.0)
    assert handle in result


# ---------------------------------------------------------------------------
# Test: unresponsive — recent heartbeat means not flagged
# ---------------------------------------------------------------------------


def test_unresponsive_fresh_heartbeat() -> None:
    """A RUNNING handle with a recent heartbeat is NOT returned by unresponsive()."""
    registry = MindRegistry()
    handle = make_handle("epsilon", MindState.RUNNING)
    handle.last_heartbeat = time.monotonic()  # heartbeat just now
    registry.register(handle)

    result = registry.unresponsive(timeout_seconds=15.0)
    assert handle not in result


def test_unresponsive_stale_heartbeat() -> None:
    """A RUNNING handle whose last heartbeat was > timeout ago IS flagged."""
    registry = MindRegistry()
    handle = make_handle("zeta", MindState.RUNNING)
    handle.last_heartbeat = time.monotonic() - 20.0  # 20s ago, timeout is 15s
    registry.register(handle)

    result = registry.unresponsive(timeout_seconds=15.0)
    assert handle in result


def test_unresponsive_non_running_exempt() -> None:
    """Non-RUNNING handles are never included in unresponsive(), regardless of heartbeat."""
    registry = MindRegistry()
    for state in (MindState.STARTING, MindState.STOPPING, MindState.STOPPED, MindState.CRASHED):
        h = make_handle(f"mind-{state}", state)
        h.started_at = time.monotonic() - 60.0  # very old
        h.last_heartbeat = 0.0
        registry.register(h)

    result = registry.unresponsive(timeout_seconds=1.0)
    assert result == []


# ---------------------------------------------------------------------------
# Test: remove
# ---------------------------------------------------------------------------


def test_remove() -> None:
    """remove() returns the handle and removes it from the registry."""
    registry = MindRegistry()
    handle = make_handle("eta")
    registry.register(handle)
    assert len(registry) == 1

    removed = registry.remove("eta")
    assert removed is handle
    assert len(registry) == 0
    assert registry.get("eta") is None


def test_remove_missing_returns_none() -> None:
    """remove() with unknown mind_id returns None without error."""
    registry = MindRegistry()
    result = registry.remove("ghost")
    assert result is None


# ---------------------------------------------------------------------------
# Test: __len__ and __iter__
# ---------------------------------------------------------------------------


def test_len_and_iter() -> None:
    """len() and iteration work correctly over registered handles."""
    registry = MindRegistry()
    handles = [make_handle(f"mind-{i}") for i in range(4)]
    for h in handles:
        registry.register(h)

    assert len(registry) == 4

    iterated = list(registry)
    assert len(iterated) == 4
    # All handles present (order may differ by Python dict insertion order)
    iterated_ids = {h.mind_id for h in iterated}
    expected_ids = {h.mind_id for h in handles}
    assert iterated_ids == expected_ids


def test_len_empty() -> None:
    """Empty registry has len 0."""
    registry = MindRegistry()
    assert len(registry) == 0
    assert list(registry) == []
