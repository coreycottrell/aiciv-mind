"""
aiciv_mind.consolidation_lock — Prevents concurrent Dream Mode / consolidation operations.

CC uses mtime-based consolidation locks with rollback on kill.
We implement the same pattern: a lock file with PID and timestamp,
stale-lock detection (dead PID = safe to steal), and automatic cleanup.

Usage:
    lock = ConsolidationLock("/path/to/dream.lock")

    # Context manager (recommended)
    async with lock:
        await run_dream_cycle()

    # Manual acquire/release
    if lock.acquire():
        try:
            await run_dream_cycle()
        finally:
            lock.release()

    # Check if another cycle is running
    if lock.is_held():
        print("Another dream cycle is active — skipping")
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from pathlib import Path
from types import TracebackType

logger = logging.getLogger(__name__)

# If a lock is older than this and the PID is dead, consider it stale.
STALE_LOCK_SECONDS: float = 3600.0  # 1 hour


class ConsolidationLock:
    """
    File-based lock for Dream Mode and other consolidation operations.

    The lock file contains JSON: {"pid": N, "started_at": epoch, "operation": "dream"}.
    On acquire, we check if an existing lock is held by a live process.
    If the PID is dead (crashed), we steal the lock and log a warning.
    """

    def __init__(
        self,
        lock_path: str | Path,
        operation: str = "dream",
        stale_seconds: float = STALE_LOCK_SECONDS,
    ) -> None:
        self._lock_path = Path(lock_path)
        self._operation = operation
        self._stale_seconds = stale_seconds
        self._held = False

    @property
    def lock_path(self) -> Path:
        return self._lock_path

    @property
    def is_held_by_us(self) -> bool:
        return self._held

    def is_held(self) -> bool:
        """Check if the lock is currently held by any live process."""
        if not self._lock_path.exists():
            return False

        info = self._read_lock()
        if info is None:
            return False

        pid = info.get("pid")
        if pid is None:
            return False

        return _pid_alive(pid)

    def holder_info(self) -> dict | None:
        """Return info about the current lock holder, or None if not held."""
        if not self._lock_path.exists():
            return None
        info = self._read_lock()
        if info is None:
            return None
        if not _pid_alive(info.get("pid", -1)):
            return None
        return info

    def acquire(self) -> bool:
        """
        Try to acquire the lock. Returns True if acquired, False if held by another.

        If the lock file exists but the holding PID is dead, we steal the lock
        (the previous process crashed without cleanup).
        """
        if self._held:
            return True  # Re-entrant — already holding

        if self._lock_path.exists():
            info = self._read_lock()
            if info is not None:
                pid = info.get("pid")
                started_at = info.get("started_at", 0)

                if pid is not None and _pid_alive(pid):
                    # Lock is held by a live process
                    age = time.time() - started_at
                    logger.warning(
                        "[consolidation_lock] Lock held by PID %d (age: %.0fs, op: %s) — cannot acquire",
                        pid, age, info.get("operation", "unknown"),
                    )
                    return False

                # PID is dead — stale lock, safe to steal
                age = time.time() - started_at
                logger.warning(
                    "[consolidation_lock] Stealing stale lock from dead PID %d (age: %.0fs)",
                    pid or -1, age,
                )

        self._write_lock()
        self._held = True
        logger.info(
            "[consolidation_lock] Acquired lock: pid=%d, op=%s, path=%s",
            os.getpid(), self._operation, self._lock_path,
        )
        return True

    def release(self) -> None:
        """Release the lock by removing the lock file."""
        if not self._held:
            return

        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("[consolidation_lock] Failed to remove lock file: %s", e)

        self._held = False
        logger.info("[consolidation_lock] Released lock: %s", self._lock_path)

    def _write_lock(self) -> None:
        """Write lock file with our PID and timestamp."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        info = {
            "pid": os.getpid(),
            "started_at": time.time(),
            "operation": self._operation,
        }
        self._lock_path.write_text(json.dumps(info), encoding="utf-8")

    def _read_lock(self) -> dict | None:
        """Read and parse the lock file. Returns None if unreadable."""
        try:
            return json.loads(self._lock_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    # Context manager support
    async def __aenter__(self) -> ConsolidationLock:
        if not self.acquire():
            raise ConsolidationLockHeld(
                f"Lock held by another process — see {self._lock_path}"
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()

    # Synchronous context manager too (for non-async callers)
    def __enter__(self) -> ConsolidationLock:
        if not self.acquire():
            raise ConsolidationLockHeld(
                f"Lock held by another process — see {self._lock_path}"
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()


class ConsolidationLockHeld(RuntimeError):
    """Raised when attempting to acquire a lock that's held by another process."""
    pass


def _pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still alive."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # Signal 0 = existence check, no actual signal sent
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but we can't signal it
