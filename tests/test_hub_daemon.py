"""Tests for hub_daemon.py — persistent Hub room watcher."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The hub_daemon module lives at project root, not in src/
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from hub_daemon import (
    HubDaemon,
    append_event,
    load_state,
    save_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def state_file(data_dir):
    return data_dir / "hub_daemon_state.json"


@pytest.fixture
def queue_file(data_dir):
    return data_dir / "hub_queue.jsonl"


@pytest.fixture(autouse=True)
def patch_paths(data_dir, state_file, queue_file):
    """Redirect daemon state and queue files to tmp_path."""
    with patch("hub_daemon.DATA_DIR", data_dir), \
         patch("hub_daemon.STATE_FILE", state_file), \
         patch("hub_daemon.QUEUE_FILE", queue_file):
        yield


# ---------------------------------------------------------------------------
# Tests: state management
# ---------------------------------------------------------------------------


class TestStateManagement:
    def test_load_state_empty(self):
        assert load_state() == {}

    def test_save_and_load_state(self, data_dir):
        state = {"last_thread_room1": "abc123", "count": 5}
        save_state(state)
        loaded = load_state()
        assert loaded == state

    def test_load_state_corrupt_file(self, state_file, data_dir):
        data_dir.mkdir(parents=True, exist_ok=True)
        state_file.write_text("not json")
        assert load_state() == {}


# ---------------------------------------------------------------------------
# Tests: event queue
# ---------------------------------------------------------------------------


class TestEventQueue:
    def test_append_event_creates_file(self, queue_file):
        event = {"event": "test", "data": "hello"}
        append_event(event)
        assert queue_file.exists()
        line = queue_file.read_text().strip()
        assert json.loads(line) == event

    def test_append_multiple_events(self, queue_file):
        for i in range(3):
            append_event({"event": "test", "index": i})
        lines = queue_file.read_text().strip().splitlines()
        assert len(lines) == 3
        for i, line in enumerate(lines):
            assert json.loads(line)["index"] == i


# ---------------------------------------------------------------------------
# Tests: HubDaemon
# ---------------------------------------------------------------------------


class TestHubDaemon:
    def test_init(self):
        daemon = HubDaemon(rooms=["room1"], interval=60.0, keypair_path="/tmp/kp.json")
        assert daemon.rooms == ["room1"]
        assert daemon.interval == 60.0
        assert daemon._running is True

    def test_stop(self):
        daemon = HubDaemon(rooms=["room1"], interval=30.0, keypair_path="/tmp/kp.json")
        daemon.stop()
        assert daemon._running is False

    @pytest.mark.asyncio
    async def test_poll_room_no_client(self):
        daemon = HubDaemon(rooms=["room1"], interval=30.0, keypair_path="/tmp/kp.json")
        daemon._client = None
        # Should not raise
        await daemon.poll_room("room1")

    @pytest.mark.asyncio
    async def test_poll_room_with_threads(self, queue_file):
        daemon = HubDaemon(rooms=["room1"], interval=30.0, keypair_path="/tmp/kp.json")
        mock_client = MagicMock()
        mock_client.hub.list_threads = AsyncMock(return_value=[
            {"id": "thread-1", "title": "Hello World", "author": "test-civ"},
            {"id": "thread-2", "title": "Second Thread", "author": "other-civ"},
        ])
        daemon._client = mock_client

        await daemon.poll_room("room1")

        # Events should be queued
        assert queue_file.exists()
        lines = queue_file.read_text().strip().splitlines()
        assert len(lines) == 2

        event = json.loads(lines[0])
        assert event["event"] == "new_thread"
        assert event["thread_id"] == "thread-1"
        assert event["room_id"] == "room1"

    @pytest.mark.asyncio
    async def test_poll_room_dedup_seen_threads(self, queue_file):
        daemon = HubDaemon(rooms=["room1"], interval=30.0, keypair_path="/tmp/kp.json")
        daemon.state["last_thread_room1"] = "thread-2"

        mock_client = MagicMock()
        mock_client.hub.list_threads = AsyncMock(return_value=[
            {"id": "thread-3", "title": "New Thread", "author": "test"},
            {"id": "thread-2", "title": "Already Seen", "author": "test"},
        ])
        daemon._client = mock_client

        await daemon.poll_room("room1")

        # Only thread-3 should be queued (thread-2 was already seen)
        assert queue_file.exists()
        lines = queue_file.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["thread_id"] == "thread-3"

    @pytest.mark.asyncio
    async def test_poll_room_updates_state(self):
        daemon = HubDaemon(rooms=["room1"], interval=30.0, keypair_path="/tmp/kp.json")
        mock_client = MagicMock()
        mock_client.hub.list_threads = AsyncMock(return_value=[
            {"id": "thread-new", "title": "Fresh"},
        ])
        daemon._client = mock_client

        await daemon.poll_room("room1")
        assert daemon.state["last_thread_room1"] == "thread-new"

    @pytest.mark.asyncio
    async def test_poll_room_handles_error(self):
        daemon = HubDaemon(rooms=["room1"], interval=30.0, keypair_path="/tmp/kp.json")
        mock_client = MagicMock()
        mock_client.hub.list_threads = AsyncMock(side_effect=ConnectionError("timeout"))
        daemon._client = mock_client

        # Should not raise
        await daemon.poll_room("room1")

    @pytest.mark.asyncio
    async def test_poll_room_empty_threads(self, queue_file):
        daemon = HubDaemon(rooms=["room1"], interval=30.0, keypair_path="/tmp/kp.json")
        mock_client = MagicMock()
        mock_client.hub.list_threads = AsyncMock(return_value=[])
        daemon._client = mock_client

        await daemon.poll_room("room1")
        assert not queue_file.exists()

    @pytest.mark.asyncio
    async def test_close_with_client(self):
        daemon = HubDaemon(rooms=["room1"], interval=30.0, keypair_path="/tmp/kp.json")
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        daemon._client = mock_client

        await daemon.close()
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        daemon = HubDaemon(rooms=["room1"], interval=30.0, keypair_path="/tmp/kp.json")
        daemon._client = None
        # Should not raise
        await daemon.close()
