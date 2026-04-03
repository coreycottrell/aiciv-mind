"""SubMindSpawner — spawn sub-mind processes in tmux panes via libtmux."""
import logging
import os
import sys
from pathlib import Path

from aiciv_mind.registry import MindHandle, MindRegistry, MindState
from aiciv_mind.security import scrub_env_for_submind

logger = logging.getLogger(__name__)


class SpawnError(Exception):
    pass


class SubMindSpawner:
    """
    Spawns sub-mind processes in tmux windows via libtmux.
    Each sub-mind runs in its own named window: python3 run_submind.py --manifest ... --id ...
    """

    def __init__(
        self,
        session_name: str,
        mind_root: str | Path,
        registry: MindRegistry | None = None,
        memory_store=None,
        session_id: str | None = None,
    ) -> None:
        """
        Args:
            session_name: tmux session name (created if doesn't exist)
            mind_root: path to aiciv-mind repo root (where run_submind.py lives)
            registry: optional MindRegistry to auto-register spawned handles
            memory_store: optional MemoryStore for persistent agent registration
            session_id: current session ID for touch_agent tracking
        """
        import libtmux
        self._session_name = session_name
        self._mind_root = Path(mind_root).resolve()
        self._registry = registry
        self._memory_store = memory_store
        self._session_id = session_id
        self._server = libtmux.Server()
        self._session = None

    def ensure_session(self) -> "libtmux.Session":
        """Get or create the tmux session. Idempotent."""
        import libtmux
        self._session = self._server.sessions.get(
            session_name=self._session_name, default=None
        )
        if self._session is None:
            self._session = self._server.new_session(session_name=self._session_name)
        return self._session

    def spawn(
        self,
        mind_id: str,
        manifest_path: str | Path,
    ) -> MindHandle:
        """
        Spawn sub-mind in a new tmux window.

        The command run in the window:
            python3 run_submind.py --manifest <manifest_path> --id <mind_id>

        Returns MindHandle with pane_id populated.
        Raises SpawnError if window with mind_id already exists.
        """
        session = self.ensure_session()

        # Check for duplicate — compare against window_name (== mind_id) for each window
        existing_names = [w.window_name for w in session.windows]
        if mind_id in existing_names:
            raise SpawnError(f"Sub-mind '{mind_id}' already running (window exists)")

        manifest_path = Path(manifest_path).resolve()
        python_bin = sys.executable
        run_script = self._mind_root / "run_submind.py"

        # Security: build a scrubbed environment for the sub-mind.
        # Sub-minds need MIND_API_KEY but should not inherit all parent credentials.
        mind_api_key = os.environ.get("MIND_API_KEY")
        safe_env = scrub_env_for_submind(mind_api_key=mind_api_key)

        # Build env export prefix for the tmux shell command.
        # Only export the scrubbed vars, not the full parent environment.
        env_exports = " ".join(
            f'{k}="{v}"' for k, v in safe_env.items()
            if k in ("MIND_API_KEY", "PYTHONPATH", "VIRTUAL_ENV", "PATH", "HOME")
        )
        env_prefix = f"export {env_exports} && " if env_exports else ""

        cmd = (
            f"cd {self._mind_root} && "
            f"{env_prefix}"
            f"{python_bin} {run_script} "
            f"--manifest {manifest_path} "
            f"--id {mind_id}"
        )

        window = session.new_window(window_name=mind_id, window_shell=cmd)
        pane = window.active_pane

        # pane_pid is a string in libtmux 0.55; convert to int for the handle
        pid_str = pane.pane_pid
        try:
            pid = int(pid_str)
        except (TypeError, ValueError):
            pid = -1

        handle = MindHandle(
            mind_id=mind_id,
            manifest_path=str(manifest_path),
            window_name=mind_id,
            pane_id=pane.pane_id,
            pid=pid,
            zmq_identity=mind_id.encode("utf-8"),
        )

        if self._registry is not None:
            self._registry.register(handle)

        # Persistent registry: register agent in DB and bump spawn count
        if self._memory_store is not None:
            try:
                self._memory_store.register_agent(
                    agent_id=mind_id,
                    manifest_path=str(manifest_path),
                    role="sub-mind",
                )
                self._memory_store.touch_agent(mind_id, session_id=self._session_id)
            except Exception as e:
                logger.warning("Persistent agent registration failed for '%s': %s", mind_id, e)

        logger.info(
            "Spawned sub-mind '%s' in tmux window (pane %s)", mind_id, pane.pane_id
        )
        return handle

    def terminate(self, handle: MindHandle, force: bool = False) -> None:
        """Kill sub-mind window. Removes the tmux window."""
        if self._session is None:
            self.ensure_session()
        try:
            window = self._session.windows.get(
                window_name=handle.window_name, default=None
            )
            if window is not None:
                window.kill()
                logger.info("Terminated sub-mind '%s'", handle.mind_id)
        except Exception as e:
            logger.warning(
                "Could not terminate window '%s': %s", handle.window_name, e
            )

    def is_alive(self, handle: MindHandle) -> bool:
        """Check if the sub-mind process is still running."""
        if handle.pid > 0:
            try:
                os.kill(handle.pid, 0)
                return True
            except OSError:
                return False
        # Fall back to tmux window existence check
        if self._session is None:
            return False
        try:
            window = self._session.windows.get(
                window_name=handle.window_name, default=None
            )
            if window is None:
                return False
            pane = window.active_pane
            cmd = pane.pane_current_command
            return cmd not in ("bash", "zsh", "sh", "")
        except Exception:
            return False

    def capture_output(self, handle: MindHandle, lines: int = 50) -> list[str]:
        """Capture recent output from the tmux pane."""
        if self._session is None:
            return []
        try:
            window = self._session.windows.get(
                window_name=handle.window_name, default=None
            )
            if window is None:
                return []
            pane = window.active_pane
            return pane.capture_pane(start=-lines)
        except Exception as e:
            logger.warning("Could not capture output: %s", e)
            return []

    def list_windows(self) -> list[str]:
        """Return window names in the session."""
        if self._session is None:
            return []
        try:
            return [w.window_name for w in self._session.windows]
        except Exception:
            return []
