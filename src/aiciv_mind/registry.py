"""MindHandle and MindRegistry — in-memory registry of live sub-minds."""
import time
from dataclasses import dataclass, field
from typing import Iterator


class MindState:
    STARTING = "starting"
    RUNNING  = "running"
    STOPPING = "stopping"
    STOPPED  = "stopped"
    CRASHED  = "crashed"


@dataclass
class MindHandle:
    mind_id: str
    manifest_path: str
    window_name: str
    pane_id: str
    pid: int
    zmq_identity: bytes          # mind_id.encode("utf-8")
    started_at: float = field(default_factory=time.monotonic)
    state: str = MindState.STARTING
    last_heartbeat: float = 0.0  # time.monotonic() of last heartbeat_ack

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def is_alive(self) -> bool:
        return self.state in (MindState.STARTING, MindState.RUNNING)


class MindRegistry:
    """
    In-memory registry of all spawned sub-minds for a session.
    Not thread-safe — designed for single-threaded async use.
    """

    def __init__(self) -> None:
        self._minds: dict[str, MindHandle] = {}

    def register(self, handle: MindHandle) -> None:
        """Register a new mind handle."""
        self._minds[handle.mind_id] = handle

    def get(self, mind_id: str) -> MindHandle | None:
        """Get handle by mind_id. Returns None if not found."""
        return self._minds.get(mind_id)

    def all(self) -> list[MindHandle]:
        """All registered handles."""
        return list(self._minds.values())

    def all_running(self) -> list[MindHandle]:
        """Handles where state is running."""
        return [h for h in self._minds.values() if h.state == MindState.RUNNING]

    def all_alive(self) -> list[MindHandle]:
        """Handles where state is starting or running."""
        return [h for h in self._minds.values() if h.is_alive()]

    def mark_state(self, mind_id: str, state: str) -> None:
        """Update state for a mind. Raises KeyError if not found."""
        self._minds[mind_id].state = state

    def record_heartbeat(self, mind_id: str) -> None:
        """Update last_heartbeat timestamp for a mind."""
        if mind_id in self._minds:
            self._minds[mind_id].last_heartbeat = time.monotonic()

    def unresponsive(self, timeout_seconds: float = 15.0) -> list[MindHandle]:
        """
        Return running handles that haven't sent a heartbeat within timeout.
        Minds that were never heartbeated (last_heartbeat == 0) are exempt
        unless they've been running for > timeout seconds.
        """
        now = time.monotonic()
        result = []
        for h in self._minds.values():
            if h.state != MindState.RUNNING:
                continue
            if h.last_heartbeat == 0:
                # No heartbeat received yet — only flag if uptime exceeds timeout
                if h.uptime_seconds > timeout_seconds:
                    result.append(h)
            elif now - h.last_heartbeat > timeout_seconds:
                result.append(h)
        return result

    def remove(self, mind_id: str) -> MindHandle | None:
        """Remove and return a handle."""
        return self._minds.pop(mind_id, None)

    def __len__(self) -> int:
        return len(self._minds)

    def __iter__(self) -> Iterator[MindHandle]:
        return iter(self._minds.values())
