"""
Tests for aiciv_mind.consolidation_lock — Dream Mode consolidation lock.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from aiciv_mind.consolidation_lock import (
    ConsolidationLock,
    ConsolidationLockHeld,
    _pid_alive,
)


# ---------------------------------------------------------------------------
# _pid_alive
# ---------------------------------------------------------------------------


class TestPidAlive:
    def test_current_process_is_alive(self):
        assert _pid_alive(os.getpid()) is True

    def test_invalid_pid_not_alive(self):
        assert _pid_alive(-1) is False
        assert _pid_alive(0) is False

    def test_nonexistent_pid_not_alive(self):
        # PID 999999999 is extremely unlikely to exist
        assert _pid_alive(999999999) is False


# ---------------------------------------------------------------------------
# ConsolidationLock — basic acquire/release
# ---------------------------------------------------------------------------


class TestAcquireRelease:
    def test_acquire_creates_lock_file(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        assert lock.acquire() is True
        assert (tmp_path / "test.lock").exists()
        lock.release()

    def test_release_removes_lock_file(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        lock.acquire()
        lock.release()
        assert not (tmp_path / "test.lock").exists()

    def test_lock_file_contains_pid_and_timestamp(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock", operation="dream")
        lock.acquire()
        info = json.loads((tmp_path / "test.lock").read_text())
        assert info["pid"] == os.getpid()
        assert info["operation"] == "dream"
        assert isinstance(info["started_at"], float)
        lock.release()

    def test_reentrant_acquire(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        assert lock.acquire() is True
        assert lock.acquire() is True  # Re-entrant — still True
        lock.release()

    def test_release_without_acquire_is_noop(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        lock.release()  # Should not raise

    def test_is_held_by_us_flag(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        assert lock.is_held_by_us is False
        lock.acquire()
        assert lock.is_held_by_us is True
        lock.release()
        assert lock.is_held_by_us is False


# ---------------------------------------------------------------------------
# ConsolidationLock — contention
# ---------------------------------------------------------------------------


class TestContention:
    def test_cannot_acquire_when_held_by_live_process(self, tmp_path):
        """Lock held by our own PID (alive) blocks a second lock instance."""
        lock_path = tmp_path / "test.lock"
        lock1 = ConsolidationLock(lock_path)
        lock2 = ConsolidationLock(lock_path)

        assert lock1.acquire() is True
        assert lock2.acquire() is False  # Blocked by lock1
        lock1.release()

    def test_can_acquire_after_release(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        lock1 = ConsolidationLock(lock_path)
        lock2 = ConsolidationLock(lock_path)

        lock1.acquire()
        lock1.release()
        assert lock2.acquire() is True
        lock2.release()

    def test_steals_stale_lock_from_dead_pid(self, tmp_path):
        """If the lock file has a dead PID, we steal the lock."""
        lock_path = tmp_path / "test.lock"
        # Write a lock file with a fake dead PID
        info = {"pid": 999999999, "started_at": time.time() - 100, "operation": "dream"}
        lock_path.write_text(json.dumps(info))

        lock = ConsolidationLock(lock_path)
        assert lock.acquire() is True  # Should steal the stale lock
        lock.release()

    def test_is_held_with_dead_pid_returns_false(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        info = {"pid": 999999999, "started_at": time.time() - 100, "operation": "dream"}
        lock_path.write_text(json.dumps(info))

        lock = ConsolidationLock(lock_path)
        assert lock.is_held() is False

    def test_is_held_with_live_pid_returns_true(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        lock = ConsolidationLock(lock_path)
        lock.acquire()
        # A separate instance checking the same path
        checker = ConsolidationLock(lock_path)
        assert checker.is_held() is True
        lock.release()


# ---------------------------------------------------------------------------
# ConsolidationLock — holder_info
# ---------------------------------------------------------------------------


class TestHolderInfo:
    def test_no_lock_returns_none(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        assert lock.holder_info() is None

    def test_dead_pid_returns_none(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        info = {"pid": 999999999, "started_at": time.time(), "operation": "dream"}
        lock_path.write_text(json.dumps(info))
        lock = ConsolidationLock(lock_path)
        assert lock.holder_info() is None

    def test_live_pid_returns_info(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        lock = ConsolidationLock(lock_path, operation="test-op")
        lock.acquire()
        info = ConsolidationLock(lock_path).holder_info()
        assert info is not None
        assert info["pid"] == os.getpid()
        assert info["operation"] == "test-op"
        lock.release()


# ---------------------------------------------------------------------------
# ConsolidationLock — corrupt lock file
# ---------------------------------------------------------------------------


class TestCorruptLockFile:
    def test_corrupt_json_allows_acquire(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        lock_path.write_text("NOT VALID JSON!!!")
        lock = ConsolidationLock(lock_path)
        assert lock.acquire() is True
        lock.release()

    def test_empty_lock_file_allows_acquire(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        lock_path.write_text("")
        lock = ConsolidationLock(lock_path)
        assert lock.acquire() is True
        lock.release()

    def test_missing_pid_in_lock_allows_acquire(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        lock_path.write_text(json.dumps({"started_at": time.time()}))
        lock = ConsolidationLock(lock_path)
        assert lock.acquire() is True
        lock.release()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_sync_context_manager(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        with lock:
            assert lock.is_held_by_us is True
            assert (tmp_path / "test.lock").exists()
        assert lock.is_held_by_us is False

    @pytest.mark.asyncio
    async def test_async_context_manager(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        async with lock:
            assert lock.is_held_by_us is True
        assert lock.is_held_by_us is False

    def test_sync_context_manager_raises_if_held(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        lock1 = ConsolidationLock(lock_path)
        lock1.acquire()
        lock2 = ConsolidationLock(lock_path)
        with pytest.raises(ConsolidationLockHeld):
            with lock2:
                pass  # Should never reach here
        lock1.release()

    @pytest.mark.asyncio
    async def test_async_context_manager_raises_if_held(self, tmp_path):
        lock_path = tmp_path / "test.lock"
        lock1 = ConsolidationLock(lock_path)
        lock1.acquire()
        lock2 = ConsolidationLock(lock_path)
        with pytest.raises(ConsolidationLockHeld):
            async with lock2:
                pass
        lock1.release()

    def test_context_manager_releases_on_exception(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        with pytest.raises(ValueError):
            with lock:
                raise ValueError("boom")
        assert lock.is_held_by_us is False
        assert not (tmp_path / "test.lock").exists()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_creates_parent_directories(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "deep" / "nested" / "test.lock")
        lock.acquire()
        assert (tmp_path / "deep" / "nested" / "test.lock").exists()
        lock.release()

    def test_lock_path_property(self, tmp_path):
        lock = ConsolidationLock(tmp_path / "test.lock")
        assert lock.lock_path == tmp_path / "test.lock"
