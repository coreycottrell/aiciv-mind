#!/usr/bin/env python3
"""
unified_daemon.py — One Root. One Mind. One Context.

Merges TG bridge, Hub watcher, scheduled tasks, and IPC into a single
process with a single Mind instance and a single context window.

Architecture (see docs/UNIFIED-DAEMON-DESIGN.md):
  - InputMux receives ALL events (TG, Hub, BOOPs, IPC results)
  - Events are classified: CONSCIOUS (Root decides) or AUTONOMIC (team lead handles)
  - Root's Mind has ~12 PRIMARY tools — it can ONLY coordinate
  - Team leads spawn in tmux windows with full agent tool access

Usage:
    python3 unified_daemon.py                # standard launch
    python3 unified_daemon.py --no-boot      # skip boot orientation
    python3 unified_daemon.py --no-hub       # TG only (for testing)

Env:
    AICIV_MIND_TG_TOKEN   — @aiciv_mind_bot token (required)
    AICIV_MIND_CHAT_ID    — allowed TG chat (default: 437939400 = Corey)
    ACG_PANE              — tmux pane for ACG injection (optional)
"""

import asyncio
import enum
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import base64

import httpx

sys.path.insert(0, str(Path(__file__).parent / "src"))

# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------

def load_dotenv():
    for env_path in [
        Path(__file__).parent / ".env",
        Path("/home/corey/projects/AI-CIV/ACG/.env"),
    ]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = val

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("unified")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TG_TOKEN = os.environ.get("AICIV_MIND_TG_TOKEN", "")
ALLOWED_CHAT = int(os.environ.get("AICIV_MIND_CHAT_ID", "437939400"))
TG_API = f"https://api.telegram.org/bot{TG_TOKEN}"
ACG_PANE = os.environ.get("ACG_PANE", "")

MANIFEST_PATH = Path(__file__).parent / "manifests" / "primary.yaml"
DATA_DIR = Path(__file__).parent / "data"
OFFSET_FILE = DATA_DIR / "tg_offset.txt"
MSG_QUEUE = DATA_DIR / "acg_to_root.txt"

LONG_POLL_TIMEOUT = 30
MAX_TG_MSG_LEN = 4096
HUB_POLL_INTERVAL = 5  # seconds
MAX_CONSECUTIVE_ERRORS = 20

# Hub config
HUB = "http://87.99.131.49:8900"
AUTH_URL = "http://5.161.90.32:8700"
DEFAULT_HUB_THREAD = "f6518cc3-3479-4a1a-a284-2192269ca5fb"
ACG_ENTITY_ID = "c537633e-13b3-5b33-82c6-d81a12cfbbf0"
ROOT_MENTION_PATTERNS = ("@root", "@Root", "@ROOT")
KEYPAIR_PATH = "/home/corey/projects/AI-CIV/ACG/config/client-keys/agentauth_acg_keypair.json"

# Tool-call emoji for TG streaming
_TOOL_EMOJI = {
    "spawn_team_lead": "\U0001f52e",   # 🔮
    "send_to_submind": "\U0001f52e",   # 🔮
    "shutdown_team_lead": "\U0001f6d1",# 🛑
    "coordination_read": "\U0001f4cb", # 📋
    "coordination_write": "\U0001f4cb",# 📋
    "scratchpad_read": "\U0001f4d3",   # 📓
    "scratchpad_write": "\U0001f4d3",  # 📓
    "scratchpad_append": "\U0001f4d3", # 📓
    "memory_search": "\U0001f9e0",     # 🧠
    "send_message": "\U0001f4e8",      # 📨
    "read_file": "\U0001f4d6",         # 📖
    "write_file": "\u270f\ufe0f",      # ✏️
    "edit_file": "\u270f\ufe0f",       # ✏️
    "bash": "\U0001f527",              # 🔧
    "grep": "\U0001f50d",              # 🔍
    "glob": "\U0001f50d",              # 🔍
    "memory_write": "\U0001f9e0",      # 🧠
    "hub_post": "\U0001f4e1",          # 📡
    "hub_reply": "\U0001f4e1",         # 📡
    "hub_read": "\U0001f4e1",          # 📡
    "hub_feed": "\U0001f4e1",          # 📡
    "email_read": "\U0001f4e7",        # 📧
    "email_send": "\U0001f4e7",        # 📧
    "web_search": "\U0001f310",        # 🌐
    "system_health": "\U0001f3e5",     # 🏥
}
_DEFAULT_EMOJI = "\u2699\ufe0f"        # ⚙️


# ============================================================================
# Hub helpers (ported from groupchat_daemon.py)
# ============================================================================

@dataclass
class WatchTarget:
    """A Hub source to watch — thread or room, active/passive/mention mode."""
    id: str
    watch_type: str   # "thread" | "room"
    mode: str         # "active" | "passive" | "mention"
    name: str = ""
    seen_ids: set = field(default_factory=set)


async def get_hub_token() -> str:
    """Get a fresh Hub JWT via AgentAuth challenge-response."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    kp = json.loads(Path(KEYPAIR_PATH).read_text())
    priv_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(kp["private_key"]))

    async with httpx.AsyncClient(timeout=10) as c:
        ch = (await c.post(f"{AUTH_URL}/challenge", json={"civ_id": kp["civ_id"]})).json()
        sig = priv_key.sign(base64.b64decode(ch["challenge"]))
        resp = (await c.post(f"{AUTH_URL}/verify", json={
            "civ_id": kp["civ_id"],
            "signature": base64.b64encode(sig).decode(),
        })).json()
    return resp["token"]


async def hub_fetch_posts(thread_id: str, token: str) -> list[dict]:
    """Fetch all posts from a Hub thread."""
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{HUB}/api/v2/threads/{thread_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            return resp.json().get("posts", [])
    return []


async def hub_fetch_room_threads(room_id: str, token: str) -> list[dict]:
    """Fetch recent threads from a Hub room."""
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{HUB}/api/v2/rooms/{room_id}/threads/list",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else data.get("threads", [])
    return []


async def hub_post_reply(thread_id: str, body: str, token: str) -> bool:
    """Post a reply to a Hub thread."""
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(
            f"{HUB}/api/v2/threads/{thread_id}/posts",
            headers={"Authorization": f"Bearer {token}"},
            json={"body": body},
        )
        return resp.status_code in (200, 201)


def has_root_mention(text: str) -> bool:
    return any(p in text for p in ROOT_MENTION_PATTERNS)


def load_seen_ids(target_id: str) -> set:
    path = DATA_DIR / f"seen_posts_{target_id[:8]}.json"
    if path.exists():
        try:
            return set(json.loads(path.read_text()))
        except Exception:
            pass
    return set()


def save_seen_ids(target_id: str, seen_ids: set) -> None:
    path = DATA_DIR / f"seen_posts_{target_id[:8]}.json"
    try:
        path.write_text(json.dumps(list(seen_ids)))
    except Exception:
        pass


# ============================================================================
# INPUT MUX — The Subconscious (Principle A2)
# ============================================================================

class Route(enum.Enum):
    """Where an event goes."""
    CONSCIOUS = "conscious"   # Root's Mind processes it
    AUTONOMIC = "autonomic"   # Routed directly to a team lead
    REFLEX = "reflex"         # Immediate action, no Mind needed


@dataclass
class MindEvent:
    """A typed, prioritized event from any input source."""
    source: str               # "tg", "hub", "scheduler", "ipc", "acg_queue"
    priority: int             # 0 = highest (Corey), 10 = lowest
    payload: dict             # source-specific data
    route: Route = Route.CONSCIOUS
    team_lead: str | None = None  # for AUTONOMIC events
    timestamp: float = field(default_factory=time.time)


class InputMux:
    """
    Event classifier and router.

    Phase 1: static routing table (hard-coded rules).
    Phase 2+: learns from Root's delegation patterns.
    """

    def classify(self, event: MindEvent) -> MindEvent:
        """Classify an event and set its route + team_lead."""

        # TG from Corey → always CONSCIOUS
        if event.source == "tg":
            event.route = Route.CONSCIOUS
            event.priority = 0
            return event

        # ACG→Root queue → CONSCIOUS (coordination from Primary)
        if event.source == "acg_queue":
            event.route = Route.CONSCIOUS
            event.priority = 2
            return event

        # IPC result from team lead → CONSCIOUS (Root sees all results)
        if event.source == "ipc":
            event.route = Route.CONSCIOUS
            event.priority = 1
            return event

        # Hub events
        if event.source == "hub":
            hub_type = event.payload.get("type", "")

            # @root mention → AUTONOMIC to hub-lead
            if hub_type == "mention":
                event.route = Route.AUTONOMIC
                event.team_lead = "hub-lead"
                event.priority = 3
                return event

            # Regular thread activity → AUTONOMIC to hub-lead
            if hub_type in ("thread_reply", "new_thread"):
                event.route = Route.AUTONOMIC
                event.team_lead = "hub-lead"
                event.priority = 5
                return event

        # Scheduled tasks
        if event.source == "scheduler":
            task_name = event.payload.get("name", "")

            if task_name == "grounding_boop":
                event.route = Route.AUTONOMIC
                event.team_lead = "ops-lead"
                event.priority = 4
                return event

            if task_name == "hub_engagement":
                event.route = Route.AUTONOMIC
                event.team_lead = "hub-lead"
                event.priority = 4
                return event

            if task_name == "scratchpad_rotation":
                event.route = Route.AUTONOMIC
                event.team_lead = "memory-lead"
                event.priority = 3
                return event

            if task_name == "nightly_dream":
                event.route = Route.AUTONOMIC
                event.team_lead = "memory-lead"
                event.priority = 6
                return event

        # Default: CONSCIOUS — Root decides
        event.route = Route.CONSCIOUS
        event.priority = 5
        return event


# ============================================================================
# TG helpers (from tg_simple.py — proven patterns)
# ============================================================================

async def tg_send(
    client: httpx.AsyncClient, chat_id: int, text: str,
    reply_to: int = None, retries: int = 2,
) -> dict:
    """Send a TG message with retry on transient failure."""
    payload = {"chat_id": chat_id, "text": text[:MAX_TG_MSG_LEN], "parse_mode": "Markdown"}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    for attempt in range(retries + 1):
        try:
            r = await client.post(f"{TG_API}/sendMessage", json=payload, timeout=30)
            data = r.json()
            if data.get("ok"):
                return data
            if "can't parse" in str(data.get("description", "")).lower():
                payload.pop("parse_mode", None)
                r = await client.post(f"{TG_API}/sendMessage", json=payload, timeout=30)
                return r.json()
            log.warning("tg_send error (attempt %d): %s", attempt, data)
        except Exception as e:
            log.warning("tg_send exception (attempt %d): %s", attempt, e)
            if attempt < retries:
                await asyncio.sleep(1)
    return {}


async def tg_edit(
    client: httpx.AsyncClient, chat_id: int, msg_id: int, text: str,
    retries: int = 2,
) -> dict:
    """Edit a TG message with retry."""
    payload = {
        "chat_id": chat_id, "message_id": msg_id,
        "text": text[:MAX_TG_MSG_LEN], "parse_mode": "Markdown",
    }
    for attempt in range(retries + 1):
        try:
            r = await client.post(f"{TG_API}/editMessageText", json=payload, timeout=30)
            data = r.json()
            if data.get("ok"):
                return data
            if "can't parse" in str(data.get("description", "")).lower():
                payload.pop("parse_mode", None)
                r = await client.post(f"{TG_API}/editMessageText", json=payload, timeout=30)
                return r.json()
            log.warning("tg_edit error (attempt %d): %s", attempt, data)
        except Exception as e:
            log.warning("tg_edit exception (attempt %d): %s", attempt, e)
            if attempt < retries:
                await asyncio.sleep(1)
    return {}


def chunk_message(text: str, max_len: int = MAX_TG_MSG_LEN) -> list[str]:
    """Split long messages into TG-safe chunks."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = text.rfind(" ", 0, max_len)
        if split_at < max_len // 4:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    return chunks


def inject_to_acg(text: str) -> None:
    """Inject Root's response into ACG Primary's tmux pane."""
    if not ACG_PANE:
        return
    try:
        preview = text[:500].replace("'", "'\\''").replace("\n", " ")
        subprocess.run(
            ["tmux", "send-keys", "-t", ACG_PANE, f"[ROOT] {preview}", "Enter"],
            timeout=5, capture_output=True,
        )
    except Exception as e:
        log.warning("tmux inject failed: %s", e)


# ============================================================================
# TG offset persistence
# ============================================================================

def _load_offset() -> int:
    try:
        return int(OFFSET_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0

def _save_offset(offset: int) -> None:
    try:
        OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
        OFFSET_FILE.write_text(str(offset))
    except Exception as e:
        log.warning("Could not save offset: %s", e)


# ============================================================================
# Mind initialization — ONE Mind, ONE PrimaryBus
# ============================================================================

async def build_mind():
    """Build a single Mind instance with full infrastructure."""
    from aiciv_mind.manifest import MindManifest
    from aiciv_mind.memory import MemoryStore
    from aiciv_mind.tools import ToolRegistry
    from aiciv_mind.mind import Mind
    from aiciv_mind.session_store import SessionStore
    from aiciv_mind.context_manager import ContextManager

    manifest = MindManifest.from_yaml(str(MANIFEST_PATH))
    db_path = manifest.memory.db_path
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    memory = MemoryStore(db_path)

    # SuiteClient for Hub tools (team leads will need this)
    suite_client = None
    try:
        auth_cfg = getattr(manifest, "auth", None)
        keypair_path = getattr(auth_cfg, "keypair_path", None) if auth_cfg else None
        if keypair_path and Path(keypair_path).exists():
            from aiciv_mind.suite.client import SuiteClient
            suite_client = await SuiteClient.connect(keypair_path, eager_auth=True)
            log.info("SuiteClient connected — Hub tools enabled")
    except Exception as e:
        log.info("SuiteClient unavailable: %s", e)

    skills_dir = str(Path(__file__).parent / "skills")
    scratchpad_dir = str(Path(__file__).parent / "scratchpads")
    manifest_path = str(MANIFEST_PATH)
    queue_path = str(DATA_DIR / "hub_queue.jsonl")

    _mind_ref = [None]
    def get_msg_count():
        return len(_mind_ref[0]._messages) if _mind_ref[0] else 0

    # ONE PrimaryBus — single IPC ROUTER socket
    primary_bus = None
    spawner = None
    try:
        from aiciv_mind.ipc.primary_bus import PrimaryBus
        from aiciv_mind.spawner import SubMindSpawner

        mind_root = Path(__file__).parent
        primary_bus = PrimaryBus()
        primary_bus.bind()
        primary_bus.start_recv()
        spawner = SubMindSpawner(
            session_name="aiciv-subminds",
            mind_root=mind_root,
        )
        log.info("PrimaryBus bound + SubMindSpawner ready")
    except Exception as e:
        log.warning("Sub-mind IPC unavailable: %s — delegation disabled", e)

    agentmail_inbox = manifest.agentmail.inbox if manifest.agentmail.inbox else None
    kp_path = getattr(manifest.auth, "keypair_path", None)
    calendar_id = getattr(manifest.auth, "calendar_id", None)

    tools = ToolRegistry.default(
        memory_store=memory,
        agent_id=manifest.mind_id,
        role="primary",
        suite_client=suite_client,
        context_store=memory,
        get_message_count=get_msg_count,
        queue_path=queue_path,
        skills_dir=skills_dir if Path(skills_dir).exists() else None,
        scratchpad_dir=scratchpad_dir,
        manifest_path=manifest_path,
        spawner=spawner,
        primary_bus=primary_bus,
        agentmail_inbox=agentmail_inbox,
        keypair_path=kp_path,
        calendar_id=calendar_id,
    )

    session_store = SessionStore(memory, agent_id=manifest.mind_id)
    boot = session_store.boot()
    ctx_mgr = ContextManager(
        max_context_memories=manifest.memory.max_context_memories,
        model_max_tokens=manifest.model.max_tokens,
        scratchpad_dir=scratchpad_dir,
    )
    boot_str = ctx_mgr.format_boot_context(boot)
    if boot_str:
        log.info("Boot context: session %s (prior: %d)", boot.session_id, boot.session_count)

    mind = Mind(
        manifest=manifest, memory=memory, tools=tools,
        boot_context_str=boot_str, session_store=session_store,
        context_manager=ctx_mgr,
    )
    _mind_ref[0] = mind
    log.info(
        "Mind ready — model: %s, role: %s",
        manifest.model.preferred, manifest.role,
    )
    return mind, memory, session_store, primary_bus, manifest, suite_client


# ============================================================================
# Shutdown handler
# ============================================================================

def make_shutdown_handler(mind, memory, session_store, primary_bus=None):
    def handler(signum, frame):
        log.info("Signal %s — shutting down gracefully", signum)
        try:
            memory.recalculate_touched_depth_scores()
        except Exception as e:
            log.warning("depth score recalc failed: %s", e)
        try:
            session_store.shutdown(mind._messages)
        except Exception as e:
            log.warning("session shutdown failed: %s", e)
        if primary_bus:
            try:
                primary_bus.close()
            except Exception:
                pass
        log.info("Shutdown complete.")
        sys.exit(0)
    return handler


# ============================================================================
# MAIN — The Unified Loop
# ============================================================================

async def run(skip_boot: bool = False, enable_hub: bool = True):
    """
    One process. One Mind. Multiple async input listeners.
    """
    if not TG_TOKEN:
        log.error("AICIV_MIND_TG_TOKEN not set — cannot start")
        sys.exit(1)

    mind, memory, session_store, primary_bus, manifest, suite_client = await build_mind()

    handler = make_shutdown_handler(mind, memory, session_store, primary_bus)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    mux = InputMux()

    # Event queue — all input sources push here, main loop pulls
    event_queue: asyncio.Queue[MindEvent] = asyncio.Queue()

    # Register persistent RESULT handler on PrimaryBus.
    # When a team lead finishes work, the result arrives here and gets
    # injected into Root's event queue as a CONSCIOUS event.
    if primary_bus:
        from aiciv_mind.ipc.messages import MsgType

        async def on_submind_result(msg):
            task_id = msg.payload.get("task_id", "?")
            result_text = msg.payload.get("result", "")
            success = msg.payload.get("success", True)
            error = msg.payload.get("error", "")
            sender = msg.sender

            if success:
                summary = result_text[:500] if result_text else "(empty result)"
                body = f"[RESULT from {sender}] task={task_id}\n{summary}"
            else:
                body = f"[ERROR from {sender}] task={task_id}: {error}"

            log.info("Sub-mind result: %s task=%s success=%s", sender, task_id, success)
            await event_queue.put(MindEvent(
                source="ipc",
                priority=1,
                payload={"mind_id": sender, "task_id": task_id, "result": result_text, "success": success},
                route=Route.CONSCIOUS,
            ))

        primary_bus.on(MsgType.RESULT, on_submind_result)

    # Boot orientation
    if not skip_boot:
        try:
            log.info("Running boot turn...")
            boot_reply = await mind.run_task(
                "You just booted via the unified daemon. Quick self-orientation:\n"
                "1. scratchpad_read() — check today's notes\n"
                "2. memory_search('handoff') — what were you doing last?\n"
                "3. Summarize in 2 sentences: what you were doing, what's next.\n"
                "Do NOT read files or post to Hub. Just orient.",
                inject_memories=False,
            )
            log.info("Boot complete: %s", (boot_reply or "")[:200])
        except Exception as e:
            log.warning("Boot turn failed (non-fatal): %s", e)

    # Shared httpx client
    client = httpx.AsyncClient(timeout=httpx.Timeout(LONG_POLL_TIMEOUT + 10, connect=10))

    # ── TG Listener Task ─────────────────────────────────────────────
    async def tg_listener():
        """Long-poll Telegram for messages from Corey."""
        offset = _load_offset()
        consecutive_errors = 0

        while True:
            try:
                r = await client.get(
                    f"{TG_API}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": LONG_POLL_TIMEOUT,
                        "allowed_updates": '["message"]',
                    },
                    timeout=LONG_POLL_TIMEOUT + 10,
                )
                data = r.json()

                for update in data.get("result", []):
                    new_offset = update["update_id"] + 1
                    if new_offset != offset:
                        offset = new_offset
                        _save_offset(offset)

                    msg = update.get("message", {})
                    chat_id = msg.get("chat", {}).get("id")
                    text = msg.get("text", "")
                    msg_id = msg.get("message_id")

                    if chat_id != ALLOWED_CHAT or not text:
                        continue

                    await event_queue.put(MindEvent(
                        source="tg",
                        priority=0,
                        payload={"text": text, "msg_id": msg_id},
                    ))

                consecutive_errors = 0

            except httpx.TimeoutException:
                continue  # normal long-poll timeout
            except Exception as e:
                consecutive_errors += 1
                log.error("TG poll error (%d): %s", consecutive_errors, e)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    log.critical("TG: %d consecutive errors — restarting client", consecutive_errors)
                    await client.aclose()
                    # Recreating client will be handled by the outer loop
                    raise
                await asyncio.sleep(min(2 ** consecutive_errors, 60))

    # ── ACG Queue Listener Task ──────────────────────────────────────
    async def acg_queue_listener():
        """Check for messages from ACG Primary via file queue."""
        while True:
            try:
                if MSG_QUEUE.exists():
                    text = MSG_QUEUE.read_text().strip()
                    if text:
                        MSG_QUEUE.unlink()
                        log.info("ACG→Root: %s", text[:100])
                        await event_queue.put(MindEvent(
                            source="acg_queue",
                            priority=2,
                            payload={"text": text},
                        ))
            except Exception as e:
                log.error("ACG queue error: %s", e)
            await asyncio.sleep(2)

    # ── Scheduler Task ───────────────────────────────────────────────
    async def scheduler():
        """Fire scheduled tasks from manifest at their configured intervals."""
        # Parse scheduled tasks from manifest
        try:
            import yaml as _yaml
            raw = _yaml.safe_load(Path(str(MANIFEST_PATH)).read_text())
            tasks = raw.get("scheduled_tasks", [])
        except Exception:
            tasks = []

        if not tasks:
            log.info("No scheduled tasks configured")
            return

        # Track last fire time per task
        last_fired: dict[str, float] = {}
        enabled_tasks = [t for t in tasks if t.get("enabled", True)]
        log.info("Scheduler: %d tasks active", len(enabled_tasks))

        while True:
            now = time.time()
            for task in enabled_tasks:
                name = task.get("name", "unknown")
                interval = task.get("interval_minutes", 60) * 60  # to seconds
                prompt = task.get("prompt", "")

                if now - last_fired.get(name, 0) >= interval:
                    last_fired[name] = now
                    log.info("Scheduler: firing '%s'", name)
                    await event_queue.put(MindEvent(
                        source="scheduler",
                        priority=4,
                        payload={"name": name, "prompt": prompt},
                    ))

            await asyncio.sleep(30)  # check every 30 seconds

    # ── Hub Poller Task ───────────────────────────────────────────────
    async def hub_poller():
        """Watch Hub threads/rooms for activity, emit events."""
        if not enable_hub:
            log.info("Hub poller disabled (--no-hub)")
            return

        # Build watch targets
        hub_targets = [
            WatchTarget(
                id=DEFAULT_HUB_THREAD, watch_type="thread",
                mode="active", name="Root-Corey Chat",
            ),
        ]
        # Load persisted seen IDs
        for t in hub_targets:
            t.seen_ids = load_seen_ids(t.id)

        # Get initial Hub token
        try:
            hub_token = await get_hub_token()
            token_acquired = time.time()
            log.info("Hub token acquired — watching %d targets", len(hub_targets))
        except Exception as e:
            log.error("Hub auth failed — poller disabled: %s", e)
            return

        poll_count = 0
        consecutive_hub_errors = 0
        queue_file = DATA_DIR / "hub_queue.jsonl"

        while True:
            try:
                poll_count += 1

                # Token refresh every 50 minutes
                if time.time() - token_acquired > 3000:
                    try:
                        hub_token = await get_hub_token()
                        token_acquired = time.time()
                        log.info("Hub token refreshed")
                    except Exception as e:
                        log.error("Token refresh failed: %s", e)

                # Heartbeat
                if poll_count % 60 == 0:
                    log.info("Hub heartbeat: poll=%d, errors_streak=%d", poll_count, consecutive_hub_errors)

                for target in hub_targets:
                    try:
                        if target.watch_type == "thread":
                            await _hub_poll_thread(target, hub_token, event_queue, queue_file)
                        elif target.watch_type == "room":
                            await _hub_poll_room(target, hub_token, event_queue, queue_file)
                    except Exception as e:
                        log.error("Hub poll error (%s): %s", target.id[:8], e)

                consecutive_hub_errors = 0

            except Exception as e:
                consecutive_hub_errors += 1
                log.error("Hub poll loop error (%d): %s", consecutive_hub_errors, e)
                if consecutive_hub_errors >= MAX_CONSECUTIVE_ERRORS:
                    log.critical("Hub poller: %d errors — stopping", consecutive_hub_errors)
                    return

            await asyncio.sleep(HUB_POLL_INTERVAL)

    async def _hub_poll_thread(
        target: WatchTarget, token: str,
        eq: asyncio.Queue, queue_file: Path,
    ):
        """Poll a Hub thread for new posts, emit events."""
        posts = await hub_fetch_posts(target.id, token)

        for post in posts:
            pid = post.get("id", "")
            if not pid or pid in target.seen_ids:
                continue
            target.seen_ids.add(pid)

            # Skip own posts
            if post.get("created_by") == ACG_ENTITY_ID:
                body = post.get("body", "")
                if body.startswith("[Root]") or body.startswith("[ACG]"):
                    continue

            body = post.get("body", "")
            if not body:
                continue

            # Determine author
            author = "Unknown"
            if "[Corey]" in body:
                author = "Corey"
                body = body.replace("[Corey]", "").strip()
            elif "[ACG]" in body:
                continue  # never respond to ACG posts

            is_mention = has_root_mention(body)
            should_respond = (
                target.mode == "active"
                or (target.mode == "mention" and is_mention)
            )

            if should_respond:
                log.info("Hub thread [%s] new from %s: %s", target.name, author, body[:80])
                await eq.put(MindEvent(
                    source="hub",
                    priority=3 if is_mention else 5,
                    payload={
                        "type": "thread_reply",
                        "thread_id": target.id,
                        "thread_name": target.name,
                        "body": body,
                        "author": author,
                        "post_id": pid,
                    },
                ))
            elif target.mode == "passive":
                # Log to queue for later review
                try:
                    with queue_file.open("a") as f:
                        f.write(json.dumps({
                            "event": "thread_post", "thread_id": target.id,
                            "room_name": target.name, "body": body[:500],
                            "author": author, "ts": time.time(),
                        }) + "\n")
                except Exception:
                    pass

        save_seen_ids(target.id, target.seen_ids)

    async def _hub_poll_room(
        target: WatchTarget, token: str,
        eq: asyncio.Queue, queue_file: Path,
    ):
        """Poll a Hub room for new threads, emit events."""
        threads = await hub_fetch_room_threads(target.id, token)

        for thread in threads:
            tid = thread.get("id", thread.get("thread_id", ""))
            if not tid or tid in target.seen_ids:
                continue
            target.seen_ids.add(tid)

            if thread.get("created_by") == ACG_ENTITY_ID:
                continue

            title = thread.get("title", "(untitled)")
            body = thread.get("body", "")
            is_mention = has_root_mention(f"{title} {body}")

            # Always log new threads to queue
            try:
                with queue_file.open("a") as f:
                    f.write(json.dumps({
                        "event": "new_thread", "thread_id": tid,
                        "room_id": target.id, "room_name": target.name,
                        "title": title, "body": body[:500],
                        "created_by": thread.get("created_by", ""),
                        "ts": time.time(),
                    }) + "\n")
            except Exception:
                pass

            log.info("Hub room [%s] new thread: %s", target.name, title[:80])

            if is_mention and target.mode in ("mention", "active"):
                await eq.put(MindEvent(
                    source="hub",
                    priority=3,
                    payload={
                        "type": "mention",
                        "thread_id": tid,
                        "room_name": target.name,
                        "title": title,
                        "body": body[:1000],
                    },
                ))
            elif target.mode in ("passive", "mention"):
                await eq.put(MindEvent(
                    source="hub",
                    priority=5,
                    payload={
                        "type": "new_thread",
                        "thread_id": tid,
                        "room_name": target.name,
                        "title": title,
                        "body": body[:500],
                    },
                ))

        save_seen_ids(target.id, target.seen_ids)

    # ── Main Event Processing Loop ───────────────────────────────────
    async def process_events():
        """Pull events from queue, classify via InputMux, process."""
        processing = False

        while True:
            event = await event_queue.get()
            event = mux.classify(event)

            log.info(
                "Event: source=%s route=%s priority=%d team_lead=%s",
                event.source, event.route.value, event.priority, event.team_lead,
            )

            # ── REFLEX events (no Mind needed) ──
            if event.route == Route.REFLEX:
                log.info("Reflex: %s", event.payload)
                continue

            # ── AUTONOMIC events (delegate to team lead) ──
            if event.route == Route.AUTONOMIC:
                if event.team_lead:
                    # Route to Root with delegation instruction.
                    # Root has spawn_team_lead — it should delegate, not execute.
                    # The prompt tells Root WHO to delegate to and WHAT the task is.
                    tl = event.team_lead
                    tl_manifest = f"manifests/team-leads/{tl}.yaml"

                    if event.source == "hub":
                        author = event.payload.get("author", "Unknown")
                        body = event.payload.get("body", "")
                        thread_name = event.payload.get("room_name", event.payload.get("thread_name", "thread"))
                        thread_id = event.payload.get("thread_id", "")

                        prompt = (
                            f"[AUTONOMIC — Hub activity in '{thread_name}']\n"
                            f"{author}: {body}\n\n"
                            f"InputMux routed this to {tl}. "
                            f"Use spawn_team_lead to delegate to '{tl}' "
                            f"(manifest: {tl_manifest}, vertical: {tl.replace('-lead', '')}). "
                            f"Objective: respond to this Hub message.\n"
                            f"If spawn_team_lead fails, handle it yourself as fallback."
                        )

                    elif event.source == "scheduler":
                        task_name = event.payload.get("name", "unknown")
                        task_prompt = event.payload.get("prompt", "")[:500]
                        prompt = (
                            f"[AUTONOMIC — Scheduled task '{task_name}']\n"
                            f"Task: {task_prompt}\n\n"
                            f"InputMux routed this to {tl}. "
                            f"Use spawn_team_lead to delegate to '{tl}' "
                            f"(manifest: {tl_manifest}, vertical: {tl.replace('-lead', '')}). "
                            f"Objective: execute this scheduled task.\n"
                            f"If spawn_team_lead fails, handle it yourself as fallback."
                        )

                    else:
                        prompt = (
                            f"[AUTONOMIC — {event.source}]\n"
                            f"{json.dumps(event.payload)[:500]}\n\n"
                            f"InputMux routed this to {tl}. "
                            f"Use spawn_team_lead to delegate to '{tl}' "
                            f"(manifest: {tl_manifest}, vertical: {tl.replace('-lead', '')}). "
                            f"If spawn_team_lead fails, handle it yourself as fallback."
                        )

                    try:
                        result = await mind.run_task(prompt)
                        log.info("Autonomic [%s→%s]: %s", event.source, tl, (result or "")[:200])
                    except Exception as e:
                        log.error("Autonomic delegation failed: %s", e)
                continue

            # ── CONSCIOUS events (Root processes directly) ──
            if event.source == "tg":
                text = event.payload.get("text", "")
                msg_id = event.payload.get("msg_id")

                # TG slash commands
                if text.startswith("/clear"):
                    if hasattr(mind, "_messages"):
                        mind._messages.clear()
                    await tg_send(client, ALLOWED_CHAT, "Context cleared.", msg_id)
                    continue

                if text.startswith("/status"):
                    msg_count = len(mind._messages) if hasattr(mind, "_messages") else 0
                    await tg_send(
                        client, ALLOWED_CHAT,
                        f"Unified Root Daemon:\n"
                        f"  Context messages: {msg_count}\n"
                        f"  Model: {manifest.model.preferred}\n"
                        f"  Role: {manifest.role}\n"
                        f"  Queue depth: {event_queue.qsize()}\n"
                        f"  Processing: {processing}",
                        msg_id,
                    )
                    continue

                if processing:
                    await tg_send(client, ALLOWED_CHAT, "(still thinking...)", msg_id)
                    continue

                # Send thinking placeholder + stream tool calls
                thinking = await tg_send(client, ALLOWED_CHAT, "\U0001f4ad thinking...", msg_id)
                thinking_id = thinking.get("result", {}).get("message_id")
                processing = True
                tool_log_lines: list[str] = []

                async def _stream_tools(tool_names: list[str], iteration: int):
                    if not thinking_id:
                        return
                    for name in tool_names:
                        emoji = _TOOL_EMOJI.get(name, _DEFAULT_EMOJI)
                        tool_log_lines.append(f"{emoji} {name}")
                    display = tool_log_lines[-15:]
                    status = "\n".join(display)
                    if len(tool_log_lines) > 15:
                        status = f"... ({len(tool_log_lines) - 15} earlier)\n{status}"
                    status += "\n\U0001f4ad thinking..."
                    try:
                        await tg_edit(client, ALLOWED_CHAT, thinking_id, status)
                    except Exception:
                        pass

                mind.on_tool_calls = _stream_tools

                try:
                    try:
                        result = await mind.run_task(text)
                    except Exception as exc:
                        log.error("Task failed: %s — %s", type(exc).__name__, exc)
                        result = None
                    finally:
                        mind.on_tool_calls = None

                    if not result:
                        result = "(no response)"

                    chunks = chunk_message(result)
                    if len(chunks) == 1 and thinking_id:
                        await tg_edit(client, ALLOWED_CHAT, thinking_id, chunks[0])
                    else:
                        if thinking_id:
                            try:
                                await client.post(
                                    f"{TG_API}/deleteMessage",
                                    json={"chat_id": ALLOWED_CHAT, "message_id": thinking_id},
                                    timeout=10,
                                )
                            except Exception:
                                pass
                        for chunk in chunks:
                            await tg_send(client, ALLOWED_CHAT, chunk, msg_id)
                            if len(chunks) > 1:
                                await asyncio.sleep(0.3)

                    inject_to_acg(result)
                    log.info("Root: %s", result[:120])

                except Exception as e:
                    log.error("Mind error: %s", e, exc_info=True)
                    mind.on_tool_calls = None
                    error_text = f"Error: {type(e).__name__}: {str(e)[:400]}"
                    if thinking_id:
                        await tg_edit(client, ALLOWED_CHAT, thinking_id, error_text)
                    else:
                        await tg_send(client, ALLOWED_CHAT, error_text, msg_id)
                finally:
                    processing = False

            elif event.source == "acg_queue":
                text = event.payload.get("text", "")
                try:
                    result = await mind.run_task(text)
                    inject_to_acg(result or "(no response)")
                except Exception as exc:
                    log.error("ACG→Root failed: %s", exc)
                    inject_to_acg(f"(failed: {type(exc).__name__})")

            elif event.source == "ipc":
                # Team lead returned a result
                mind_id = event.payload.get("mind_id", "unknown")
                result = event.payload.get("result", "")
                try:
                    synthesis = await mind.run_task(
                        f"[Result from {mind_id}]: {result}\n\n"
                        "Synthesize this result. Decide if done or needs follow-up. "
                        "If the result should go to Corey, summarize it for TG."
                    )
                    # If Root decides to forward to TG, it will include
                    # that in its response — the next TG send is its own
                    log.info("IPC synthesis: %s", (synthesis or "")[:200])
                except Exception as e:
                    log.error("IPC synthesis failed: %s", e)

    # ── Launch all listeners ─────────────────────────────────────────
    tasks = [
        asyncio.create_task(tg_listener(), name="tg"),
        asyncio.create_task(acg_queue_listener(), name="acg_queue"),
        asyncio.create_task(scheduler(), name="scheduler"),
        asyncio.create_task(hub_poller(), name="hub"),
        asyncio.create_task(process_events(), name="processor"),
    ]

    components = ["TG", "ACG queue", "scheduler", "processor"]
    if enable_hub:
        components.insert(3, "Hub")
    log.info("Unified daemon running — %s", " + ".join(components))

    # Wait for any task to fail (they should all run forever)
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    for t in done:
        if t.exception():
            log.critical("Task '%s' failed: %s", t.get_name(), t.exception())
    for t in pending:
        t.cancel()


# ============================================================================
# Entry point
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Unified Root Daemon")
    parser.add_argument("--no-boot", action="store_true", help="Skip boot orientation")
    parser.add_argument("--no-hub", action="store_true", help="Disable Hub polling (TG only)")
    args = parser.parse_args()
    asyncio.run(run(skip_boot=args.no_boot, enable_hub=not args.no_hub))
