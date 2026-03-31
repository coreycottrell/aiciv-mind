#!/usr/bin/env python3
"""
hub_daemon.py — Persistent Hub room watcher for aiciv-mind.

Polls configured Hub rooms every POLL_INTERVAL seconds.
When new threads or posts appear, appends them as JSON events
to data/hub_queue.jsonl for Root to process on next boot or turn.

Usage:
    python3 hub_daemon.py [--rooms room_id1,room_id2] [--interval 30]

State file: data/hub_daemon_state.json
Queue file: data/hub_queue.jsonl (append-only event log)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aiciv_mind.suite.client import SuiteClient

logger = logging.getLogger("hub_daemon")

# Default rooms to watch
DEFAULT_ROOMS = [
    "bdb6bc7d-288a-4ae7-babb-f2e4ae206bb6",  # AgentMind WG #general — Root's home room
    "2a20869b-8068-4a2f-834b-9702c7197bdf",  # CivSubstrate #general — civilization substrate
]

DATA_DIR = Path(__file__).parent / "data"
STATE_FILE = DATA_DIR / "hub_daemon_state.json"
QUEUE_FILE = DATA_DIR / "hub_queue.jsonl"


def load_dotenv() -> None:
    """Load .env from project root if present."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def load_state() -> dict:
    """Load daemon state from file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    """Save daemon state to file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def append_event(event: dict) -> None:
    """Append an event to the queue file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")


class HubDaemon:
    """Polls Hub rooms and writes new activity to the queue."""

    def __init__(
        self,
        rooms: list[str],
        interval: float = 30.0,
        keypair_path: str | None = None,
    ) -> None:
        self.rooms = rooms
        self.interval = interval
        self.keypair_path = keypair_path
        self._running = True
        self._client: SuiteClient | None = None
        self.state = load_state()

    async def connect(self) -> None:
        """Connect to Hub via SuiteClient."""
        if not self.keypair_path:
            raise RuntimeError("keypair_path is required for Hub auth")
        self._client = await SuiteClient.connect(self.keypair_path, eager_auth=True)
        logger.info("Connected to Hub via SuiteClient")

    async def poll_room(self, room_id: str) -> None:
        """Poll a single room for new threads."""
        if self._client is None:
            return

        try:
            threads = await self._client.hub.list_threads(room_id)
        except Exception as e:
            logger.warning("Failed to poll room %s: %s", room_id, e)
            return

        if not threads:
            return

        last_seen = self.state.get(f"last_thread_{room_id}")
        new_count = 0

        for thread in threads:
            thread_id = thread.get("id", thread.get("thread_id"))
            if not thread_id:
                continue

            # If we've seen this thread before, skip
            if last_seen and thread_id == last_seen:
                break

            event = {
                "event": "new_thread",
                "room_id": room_id,
                "thread_id": thread_id,
                "title": thread.get("title", ""),
                "created_by": thread.get("author", thread.get("author_id", "unknown")),
                "created_at": thread.get("created_at", datetime.now(timezone.utc).isoformat()),
                "processed": False,
            }
            append_event(event)
            new_count += 1
            logger.info("New thread: %s in room %s", thread.get("title", "?"), room_id)

        # Update state with the first (newest) thread ID
        if threads:
            newest_id = threads[0].get("id", threads[0].get("thread_id"))
            if newest_id:
                self.state[f"last_thread_{room_id}"] = newest_id
                save_state(self.state)

        if new_count > 0:
            logger.info("Found %d new thread(s) in room %s", new_count, room_id)

    async def run(self) -> None:
        """Main polling loop."""
        logger.info(
            "Hub daemon starting — polling %d room(s) every %.0fs",
            len(self.rooms),
            self.interval,
        )

        while self._running:
            for room_id in self.rooms:
                await self.poll_room(room_id)

            # Sleep in small increments to allow clean shutdown
            elapsed = 0.0
            while elapsed < self.interval and self._running:
                await asyncio.sleep(min(1.0, self.interval - elapsed))
                elapsed += 1.0

        logger.info("Hub daemon shutting down")

    def stop(self) -> None:
        """Signal the daemon to stop."""
        self._running = False

    async def close(self) -> None:
        """Clean up resources."""
        if self._client:
            await self._client.close()


async def main_async(args: argparse.Namespace) -> None:
    rooms = args.rooms.split(",") if args.rooms else DEFAULT_ROOMS
    keypair_path = args.keypair or os.environ.get("AICIV_KEYPAIR_PATH")

    if not keypair_path:
        # Try default path from primary manifest
        default_kp = Path(__file__).parent / "config" / "keypair.json"
        if not default_kp.exists():
            # Try ACG keypair path
            acg_kp = Path.home() / "projects/AI-CIV/ACG/config/client-keys/agentauth_acg_keypair.json"
            if acg_kp.exists():
                keypair_path = str(acg_kp)
        else:
            keypair_path = str(default_kp)

    daemon = HubDaemon(rooms=rooms, interval=args.interval, keypair_path=keypair_path)

    # Handle signals for graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, daemon.stop)

    try:
        await daemon.connect()
        await daemon.run()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error("Daemon error: %s", e)
    finally:
        await daemon.close()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Hub room watcher daemon")
    parser.add_argument(
        "--rooms",
        help="Comma-separated room IDs to watch (default: CivSubstrate #general)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        help="Poll interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--keypair",
        help="Path to AgentAuth keypair JSON file",
    )
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
