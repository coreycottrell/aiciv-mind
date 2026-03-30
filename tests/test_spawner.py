"""Tests for aiciv_mind.spawner — SubMindSpawner (libtmux mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aiciv_mind.registry import MindHandle, MindRegistry, MindState
from aiciv_mind.spawner import SpawnError, SubMindSpawner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_libtmux(mocker):
    """
    Mock the libtmux.Server so no real tmux session is touched.

    Returns (mock_server, mock_session, mock_window, mock_pane).
    """
    mock_server = mocker.MagicMock()
    mock_session = mocker.MagicMock()
    mock_window = mocker.MagicMock()
    mock_pane = mocker.MagicMock()

    # Session lookup: session already exists
    mock_server.sessions.get.return_value = mock_session

    # No existing windows in this session by default
    mock_session.windows.__iter__ = mocker.MagicMock(return_value=iter([]))
    # windows.get by name returns None (window doesn't exist yet)
    mock_session.windows.get.return_value = None

    # Creating a new window returns mock_window
    mock_session.new_window.return_value = mock_window

    # active_pane on the new window
    mock_window.active_pane = mock_pane
    mock_pane.pane_id = "%10"
    mock_pane.pane_pid = "12345"

    mocker.patch("libtmux.Server", return_value=mock_server)

    return mock_server, mock_session, mock_window, mock_pane


@pytest.fixture
def spawner(mock_libtmux, tmp_path):
    """A SubMindSpawner with libtmux mocked and a real tmp_path as mind_root."""
    return SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )


@pytest.fixture
def spawner_with_registry(mock_libtmux, tmp_path):
    """A SubMindSpawner with a MindRegistry attached."""
    registry = MindRegistry()
    sp = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
        registry=registry,
    )
    return sp, registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_window_mock(name: str) -> MagicMock:
    """Create a mock Window object with a given window_name."""
    w = MagicMock()
    w.window_name = name
    return w


# ---------------------------------------------------------------------------
# Test 1: spawn() calls session.new_window with correct args
# ---------------------------------------------------------------------------


def test_spawn_creates_window(mock_libtmux, tmp_path) -> None:
    """spawn() calls session.new_window with the correct window_name and command."""
    mock_server, mock_session, mock_window, mock_pane = mock_libtmux

    spawner = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )

    manifest = tmp_path / "test.yaml"
    manifest.touch()

    spawner.spawn("research-lead", manifest)

    # new_window must have been called once
    mock_session.new_window.assert_called_once()
    call_kwargs = mock_session.new_window.call_args

    # window_name should be the mind_id
    assert call_kwargs.kwargs.get("window_name") == "research-lead" or (
        len(call_kwargs.args) > 0 and call_kwargs.args[0] == "research-lead"
    )

    # window_command should contain the mind_id and manifest path
    window_cmd = call_kwargs.kwargs.get("window_command", "")
    assert "research-lead" in window_cmd
    assert str(manifest.resolve()) in window_cmd
    assert "run_submind.py" in window_cmd


# ---------------------------------------------------------------------------
# Test 2: spawn() returns a MindHandle with correct fields
# ---------------------------------------------------------------------------


def test_spawn_returns_handle(mock_libtmux, tmp_path) -> None:
    """spawn() returns a MindHandle with correct mind_id, pane_id, and pid."""
    mock_server, mock_session, mock_window, mock_pane = mock_libtmux

    spawner = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )

    manifest = tmp_path / "worker.yaml"
    manifest.touch()

    handle = spawner.spawn("worker-1", manifest)

    assert isinstance(handle, MindHandle)
    assert handle.mind_id == "worker-1"
    assert handle.pane_id == "%10"
    assert handle.pid == 12345
    assert handle.zmq_identity == b"worker-1"
    assert handle.window_name == "worker-1"
    assert handle.state == MindState.STARTING


# ---------------------------------------------------------------------------
# Test 3: spawn() registers handle in registry when provided
# ---------------------------------------------------------------------------


def test_spawn_registers_in_registry(spawner_with_registry, tmp_path) -> None:
    """If a registry is provided, spawn() registers the returned handle."""
    sp, registry = spawner_with_registry

    manifest = tmp_path / "sub.yaml"
    manifest.touch()

    handle = sp.spawn("sub-mind-1", manifest)

    assert registry.get("sub-mind-1") is handle
    assert len(registry) == 1


def test_spawn_no_registry_does_not_crash(mock_libtmux, tmp_path) -> None:
    """spawn() with no registry provided works fine (no registration)."""
    spawner = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )
    manifest = tmp_path / "solo.yaml"
    manifest.touch()

    handle = spawner.spawn("solo-mind", manifest)
    assert handle.mind_id == "solo-mind"


# ---------------------------------------------------------------------------
# Test 4: spawn() raises SpawnError on duplicate mind_id
# ---------------------------------------------------------------------------


def test_spawn_duplicate_raises(mock_libtmux, tmp_path, mocker) -> None:
    """Calling spawn() with a mind_id that already has a window raises SpawnError."""
    mock_server, mock_session, mock_window, mock_pane = mock_libtmux

    # Simulate an existing window with the same name
    existing_window = _make_window_mock("worker-2")
    mock_session.windows.__iter__ = mocker.MagicMock(
        return_value=iter([existing_window])
    )

    spawner = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )

    manifest = tmp_path / "worker2.yaml"
    manifest.touch()

    with pytest.raises(SpawnError, match="worker-2"):
        spawner.spawn("worker-2", manifest)

    # new_window must NOT have been called
    mock_session.new_window.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: terminate() calls window.kill()
# ---------------------------------------------------------------------------


def test_terminate_kills_window(mock_libtmux, tmp_path) -> None:
    """terminate() finds the window by name and calls window.kill()."""
    mock_server, mock_session, mock_window, mock_pane = mock_libtmux

    # windows.get returns mock_window (so terminate can find it)
    mock_session.windows.get.return_value = mock_window

    spawner = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )

    # Build a handle as if we'd already spawned it
    handle = MindHandle(
        mind_id="target-mind",
        manifest_path="/tmp/target.yaml",
        window_name="target-mind",
        pane_id="%10",
        pid=12345,
        zmq_identity=b"target-mind",
    )

    # Call terminate — need a session in place first
    spawner.ensure_session()
    spawner.terminate(handle)

    mock_window.kill.assert_called_once()


# ---------------------------------------------------------------------------
# Test 6: is_alive() uses os.kill(pid, 0) signal check
# ---------------------------------------------------------------------------


def test_is_alive_pid_check_alive(mock_libtmux, tmp_path, mocker) -> None:
    """is_alive() returns True when os.kill(pid, 0) does not raise."""
    mocker.patch("os.kill")  # does not raise = process alive

    spawner = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )

    handle = MindHandle(
        mind_id="live-mind",
        manifest_path="/tmp/live.yaml",
        window_name="live-mind",
        pane_id="%10",
        pid=99999,
        zmq_identity=b"live-mind",
    )

    assert spawner.is_alive(handle) is True


def test_is_alive_pid_check_dead(mock_libtmux, tmp_path, mocker) -> None:
    """is_alive() returns False when os.kill(pid, 0) raises OSError (process gone)."""
    mocker.patch("os.kill", side_effect=OSError("no such process"))

    spawner = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )

    handle = MindHandle(
        mind_id="dead-mind",
        manifest_path="/tmp/dead.yaml",
        window_name="dead-mind",
        pane_id="%10",
        pid=99998,
        zmq_identity=b"dead-mind",
    )

    assert spawner.is_alive(handle) is False


def test_is_alive_no_pid_uses_window_check(mock_libtmux, tmp_path) -> None:
    """is_alive() falls back to window/pane check when pid <= 0."""
    mock_server, mock_session, mock_window, mock_pane = mock_libtmux

    # Simulate window found, running command
    mock_session.windows.get.return_value = mock_window
    mock_pane.pane_current_command = "python3"
    mock_window.active_pane = mock_pane

    spawner = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )
    spawner.ensure_session()  # sets self._session

    handle = MindHandle(
        mind_id="no-pid-mind",
        manifest_path="/tmp/nopid.yaml",
        window_name="no-pid-mind",
        pane_id="%10",
        pid=-1,  # invalid pid → falls back to window check
        zmq_identity=b"no-pid-mind",
    )

    assert spawner.is_alive(handle) is True


def test_is_alive_no_pid_shell_means_dead(mock_libtmux, tmp_path) -> None:
    """is_alive() returns False when fallback command is 'bash' (process finished)."""
    mock_server, mock_session, mock_window, mock_pane = mock_libtmux

    mock_session.windows.get.return_value = mock_window
    mock_pane.pane_current_command = "bash"
    mock_window.active_pane = mock_pane

    spawner = SubMindSpawner(
        session_name="test-session",
        mind_root=tmp_path,
    )
    spawner.ensure_session()

    handle = MindHandle(
        mind_id="shell-mind",
        manifest_path="/tmp/shell.yaml",
        window_name="shell-mind",
        pane_id="%10",
        pid=-1,
        zmq_identity=b"shell-mind",
    )

    assert spawner.is_alive(handle) is False
