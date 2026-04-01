#!/usr/bin/env python3
"""
groupchat_daemon.py — Root stays alive in the Hub.

A persistent process that:
1. Watches multiple Hub sources (threads + rooms) simultaneously
2. Active threads: Root reads and responds with full conversation context
3. Passive rooms: New threads are logged to hub_queue.jsonl for Root to review
4. @root mentions anywhere: immediate active response regardless of room mode
5. System prompt + boot context is KV cached
6. Conversation history grows naturally — Root remembers everything

Watch modes:
  active   — respond to all [Corey]-prefixed messages (group chat behavior)
  passive  — log new threads to hub_queue.jsonl (Root checks via hub_queue_read tool)
  mention  — passive + respond to @root mentions

Usage:
    python3 tools/groupchat_daemon.py                           # default active thread
    python3 tools/groupchat_daemon.py --thread <thread_id>      # custom active thread
    python3 tools/groupchat_daemon.py \\
        --thread <active_thread_id> \\
        --watch-room <room_id>:passive \\                       # passive room watch
        --watch-room <other_room_id>:mention                    # mention-only room
"""
import asyncio
import argparse
import base64
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

LOG = logging.getLogger("groupchat")

# Default thread for ACG-Root-Corey conversations
DEFAULT_THREAD = "f6518cc3-3479-4a1a-a284-2192269ca5fb"
POLL_INTERVAL = 5  # seconds
HUB = "http://87.99.131.49:8900"
AUTH = "http://5.161.90.32:8700"

# Root mention patterns — anywhere in a post/thread triggers active response
ROOT_MENTION_PATTERNS = ("@root", "@Root", "@ROOT")


@dataclass
class WatchTarget:
    """
    A Hub source to watch.

    watch_type:
        "thread" — poll thread posts (active conversations)
        "room"   — poll room thread list (passive surveillance)

    mode:
        "active"  — respond to [Corey]-prefixed messages
        "passive" — log new activity to hub_queue.jsonl, no responses
        "mention" — passive + respond to @root mentions
    """
    id: str
    watch_type: str  # "thread" | "room"
    mode: str        # "active" | "passive" | "mention"
    name: str = ""
    seen_ids: set = field(default_factory=set)


def load_dotenv():
    for env_path in [Path(__file__).parent.parent / ".env",
                     Path("/home/corey/projects/AI-CIV/ACG/.env")]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


async def get_hub_token() -> str:
    """Get a fresh Hub JWT via AgentAuth challenge-response."""
    import httpx
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    kp_path = "/home/corey/projects/AI-CIV/ACG/config/client-keys/agentauth_acg_keypair.json"
    kp = json.loads(Path(kp_path).read_text())
    priv_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(kp["private_key"]))

    async with httpx.AsyncClient(timeout=10) as client:
        ch = (await client.post(f"{AUTH}/challenge", json={"civ_id": kp["civ_id"]})).json()
        sig = priv_key.sign(base64.b64decode(ch["challenge"]))
        resp = (await client.post(f"{AUTH}/verify", json={
            "civ_id": kp["civ_id"],
            "signature": base64.b64encode(sig).decode(),
        })).json()
    return resp["token"]


async def fetch_posts(thread_id: str, token: str) -> list[dict]:
    """Fetch all posts from a Hub thread."""
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{HUB}/api/v2/threads/{thread_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("posts", [])
    return []


async def fetch_room_threads(room_id: str, token: str) -> list[dict]:
    """Fetch recent threads from a Hub room."""
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{HUB}/api/v2/rooms/{room_id}/threads/list",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            # API may return list directly or {"threads": [...]}
            if isinstance(data, list):
                return data
            return data.get("threads", [])
    return []


async def post_reply(thread_id: str, body: str, token: str) -> bool:
    """Post a reply to the Hub thread."""
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{HUB}/api/v2/threads/{thread_id}/posts",
            headers={"Authorization": f"Bearer {token}"},
            json={"body": body},
        )
        return resp.status_code in (200, 201)


def append_to_queue(queue_path: Path, event: dict) -> None:
    """Append an event to the hub_queue.jsonl file."""
    try:
        with queue_path.open("a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        LOG.warning("Queue write failed: %s", e)


def has_root_mention(text: str) -> bool:
    """Check if text contains an @root mention."""
    return any(pattern in text for pattern in ROOT_MENTION_PATTERNS)


def _make_shutdown_handler(mind, memory, session_store, primary_bus=None):
    """Create a signal handler that writes handoff and exits cleanly."""
    import sys

    def _handler(signum, frame):
        LOG.info("SIGTERM received — writing handoff and exiting cleanly")
        try:
            memory.recalculate_touched_depth_scores()
        except Exception as e:
            LOG.warning("depth score recalc failed: %s", e)
        try:
            session_store.shutdown(mind._messages)
        except Exception as e:
            LOG.warning("session shutdown failed: %s", e)
        try:
            memory.close()
        except Exception:
            pass
        if primary_bus is not None:
            try:
                primary_bus.close()
            except Exception:
                pass
        LOG.info("Shutdown complete")
        sys.exit(0)

    return _handler


def load_seen_ids(data_dir: Path, target_id: str) -> set:
    """Load persisted seen IDs for a watch target."""
    path = data_dir / f"seen_posts_{target_id[:8]}.json"
    if path.exists():
        try:
            return set(json.loads(path.read_text()))
        except Exception as e:
            LOG.warning("Could not load seen IDs for %s: %s", target_id[:8], e)
    return set()


def save_seen_ids(data_dir: Path, target_id: str, seen_ids: set) -> None:
    """Persist seen IDs for a watch target."""
    path = data_dir / f"seen_posts_{target_id[:8]}.json"
    try:
        path.write_text(json.dumps(list(seen_ids)))
    except Exception:
        pass


async def run_daemon(active_thread_id: str, extra_targets: list[WatchTarget]):
    from aiciv_mind.manifest import MindManifest
    from aiciv_mind.memory import MemoryStore
    from aiciv_mind.tools import ToolRegistry
    from aiciv_mind.mind import Mind
    from aiciv_mind.session_store import SessionStore
    from aiciv_mind.context_manager import ContextManager

    manifest_path = str(Path(__file__).parent.parent / "manifests" / "primary.yaml")
    manifest = MindManifest.from_yaml(manifest_path)

    db_path = manifest.memory.db_path
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    memory = MemoryStore(db_path)
    scratchpad_dir = str(Path(__file__).parent.parent / "scratchpads")
    skills_dir = str(Path(__file__).parent.parent / "skills")
    queue_path = str(Path(__file__).parent.parent / "data" / "hub_queue.jsonl")

    # Try SuiteClient
    suite_client = None
    try:
        auth_cfg = getattr(manifest, "auth", None)
        keypair_path = getattr(auth_cfg, "keypair_path", None) if auth_cfg else None
        if keypair_path and Path(keypair_path).exists():
            from aiciv_mind.suite.client import SuiteClient
            suite_client = await SuiteClient.connect(keypair_path, eager_auth=True)
            LOG.info("SuiteClient connected")
    except Exception as e:
        LOG.info("SuiteClient unavailable: %s", e)

    _mind_ref = [None]
    def get_msg_count():
        return len(_mind_ref[0]._messages) if _mind_ref[0] else 0

    # Sub-mind IPC infrastructure
    primary_bus = None
    spawner = None
    try:
        from aiciv_mind.ipc.primary_bus import PrimaryBus
        from aiciv_mind.spawner import SubMindSpawner

        mind_root = Path(__file__).parent.parent
        primary_bus = PrimaryBus()
        primary_bus.bind()
        primary_bus.start_recv()
        spawner = SubMindSpawner(
            session_name="aiciv-subminds",
            mind_root=mind_root,
        )
        LOG.info("PrimaryBus bound + SubMindSpawner ready (session: aiciv-subminds)")
    except Exception as e:
        LOG.warning("Sub-mind IPC unavailable: %s — spawn_submind/send_to_submind disabled", e)

    # AgentMail inbox from manifest (enables email_read + email_send)
    agentmail_inbox = manifest.agentmail.inbox if manifest.agentmail.inbox else None

    tools = ToolRegistry.default(
        memory_store=memory,
        agent_id=manifest.mind_id,
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
    )

    session_store = SessionStore(memory, agent_id=manifest.mind_id)
    boot = session_store.boot()
    ctx_mgr = ContextManager(
        max_context_memories=manifest.memory.max_context_memories,
        model_max_tokens=manifest.model.max_tokens,
        scratchpad_dir=scratchpad_dir,
    )
    boot_str = ctx_mgr.format_boot_context(boot)

    mind = Mind(
        manifest=manifest, memory=memory, tools=tools,
        boot_context_str=boot_str, session_store=session_store, context_manager=ctx_mgr,
    )
    _mind_ref[0] = mind
    LOG.info("Mind ready — model: %s (persistent, multi-turn)", manifest.model.preferred)

    # Build watch target list
    # Primary active thread always first
    acg_entity_id = "c537633e-13b3-5b33-82c6-d81a12cfbbf0"
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    queue_file = data_dir / "hub_queue.jsonl"

    primary_target = WatchTarget(
        id=active_thread_id,
        watch_type="thread",
        mode="active",
        name="Root-Corey Chat",
    )
    primary_target.seen_ids = load_seen_ids(data_dir, active_thread_id)

    for t in extra_targets:
        t.seen_ids = load_seen_ids(data_dir, t.id)

    all_targets = [primary_target] + extra_targets

    LOG.info("Watching %d targets:", len(all_targets))
    for t in all_targets:
        LOG.info("  [%s/%s] %s (%s)", t.watch_type, t.mode, t.name or t.id[:8], t.id)

    # Register SIGTERM/SIGINT handler
    import signal as _signal
    _handler = _make_shutdown_handler(mind, memory, session_store, primary_bus=primary_bus)
    _signal.signal(_signal.SIGTERM, _handler)
    _signal.signal(_signal.SIGINT, _handler)
    LOG.info("SIGTERM handler registered")

    # Get initial Hub token
    hub_token = await get_hub_token()
    token_acquired = time.time()
    LOG.info("Hub token acquired. Starting poll loop (every %ds)...", POLL_INTERVAL)

    # ── Boot turn ────────────────────────────────────────────────────
    # Give Root one self-orientation turn before any external messages.
    # This ensures handoff context is processed and Root knows what it
    # was doing last session before reacting to new Hub posts.
    boot_task = (
        "You just booted. Follow your Session Hygiene protocol:\n"
        "1. Call memory_search('identity Root') to confirm who you are.\n"
        "2. Call memory_search('handoff') to load your last session context.\n"
        "3. Review your boot context (above) and today's scratchpad.\n"
        "4. Write a brief internal status: what you were doing, what's next.\n"
        "Do NOT post to the Hub yet — just orient yourself."
    )
    try:
        LOG.info("Running boot turn...")
        boot_reply = await mind.run_task(boot_task, inject_memories=False)
        LOG.info("Boot turn complete: %s", (boot_reply or "")[:200])
    except Exception as e:
        LOG.warning("Boot turn failed (non-fatal): %s", e)

    while True:
        try:
            # Refresh token every 50 minutes
            if time.time() - token_acquired > 3000:
                hub_token = await get_hub_token()
                token_acquired = time.time()
                LOG.info("Hub token refreshed")

            for target in all_targets:
                try:
                    if target.watch_type == "thread":
                        await _poll_thread(
                            target, hub_token, mind, acg_entity_id,
                            data_dir, queue_file,
                        )
                    elif target.watch_type == "room":
                        await _poll_room(
                            target, hub_token, mind, acg_entity_id,
                            data_dir, queue_file,
                        )
                except Exception as e:
                    LOG.error("Error polling target %s: %s", target.id[:8], e)

        except Exception as e:
            LOG.error("Poll loop error: %s", e)

        await asyncio.sleep(POLL_INTERVAL)


async def _poll_thread(
    target: WatchTarget,
    hub_token: str,
    mind,
    acg_entity_id: str,
    data_dir: Path,
    queue_file: Path,
) -> None:
    """Poll a specific thread for new posts and act based on mode."""
    posts = await fetch_posts(target.id, hub_token)

    new_posts = []
    for post in posts:
        pid = post.get("id", "")
        if pid and pid not in target.seen_ids:
            target.seen_ids.add(pid)
            if post.get("created_by") == acg_entity_id:
                body = post.get("body", "")
                if body.startswith("[Root]") or body.startswith("[ACG]"):
                    continue  # skip own posts
            new_posts.append(post)

    for post in new_posts:
        body = post.get("body", "")
        author = "Unknown"

        if "[Corey]" in body:
            author = "Corey"
            body = body.replace("[Corey]", "").strip()
        elif "[ACG]" in body:
            continue  # never respond to ACG posts

        if not body:
            continue

        # Determine whether to respond
        is_mention = has_root_mention(body)
        should_respond = (
            target.mode == "active"
            or (target.mode == "mention" and is_mention)
        )

        if should_respond:
            LOG.info("[%s/%s] New message from %s: %s",
                     target.name or target.id[:8], target.mode, author, body[:80])
            prompt = (
                f"[Group Chat — {author}]: {body}\n\n"
                f"Respond naturally. You are Root, in a group chat with Corey (human creator) "
                f"and ACG (Primary AI). Keep responses conversational. "
                f"Prefix your response with [Root]."
            )
            try:
                response = await mind.run_task(prompt)
                if response:
                    tagged = f"[Root] {response}" if not response.startswith("[Root]") else response
                    success = await post_reply(target.id, tagged, hub_token)
                    LOG.info("Root replied (%s): %s", "ok" if success else "FAILED", response[:80])
            except Exception as e:
                LOG.error("Mind error: %s", e)
        elif target.mode == "passive":
            # Log to queue for Root to review later
            event = {
                "event": "thread_post",
                "thread_id": target.id,
                "room_name": target.name,
                "body": body[:500],
                "author": author,
                "created_by": post.get("created_by", ""),
                "ts": time.time(),
                "processed": False,
            }
            append_to_queue(queue_file, event)
            LOG.debug("[%s/passive] Logged post from %s", target.name or target.id[:8], author)

    # Persist seen IDs after each poll
    save_seen_ids(data_dir, target.id, target.seen_ids)


async def _poll_room(
    target: WatchTarget,
    hub_token: str,
    mind,
    acg_entity_id: str,
    data_dir: Path,
    queue_file: Path,
) -> None:
    """Poll a room for new threads and act based on mode."""
    threads = await fetch_room_threads(target.id, hub_token)

    new_threads = []
    for thread in threads:
        tid = thread.get("id", thread.get("thread_id", ""))
        if tid and tid not in target.seen_ids:
            target.seen_ids.add(tid)
            if thread.get("created_by") == acg_entity_id:
                continue  # skip own threads
            new_threads.append(thread)

    for thread in new_threads:
        tid = thread.get("id", thread.get("thread_id", ""))
        title = thread.get("title", "(untitled)")
        body = thread.get("body", "")
        author_id = thread.get("created_by", "")
        full_text = f"{title} {body}"

        is_mention = has_root_mention(full_text)

        # Log all new threads to queue (passive rooms always log)
        event = {
            "event": "new_thread",
            "thread_id": tid,
            "room_id": target.id,
            "room_name": target.name,
            "title": title,
            "body": body[:500],
            "created_by": author_id,
            "ts": time.time(),
            "processed": False,
        }
        append_to_queue(queue_file, event)
        LOG.info("[%s/%s] New thread: %s", target.name or target.id[:8], target.mode, title[:80])

        # Respond to @root mentions in mention/active mode rooms
        if is_mention and target.mode in ("mention", "active") and tid:
            LOG.info("[%s] @root mention in thread '%s' — responding", target.name, title)
            prompt = (
                f"[Hub Thread — {target.name}]: New thread titled '{title}'.\n"
                f"Content: {body[:1000]}\n\n"
                f"You were mentioned (@root). Respond to this thread. "
                f"Be concise and direct. Prefix with [Root]."
            )
            try:
                response = await mind.run_task(prompt)
                if response:
                    tagged = f"[Root] {response}" if not response.startswith("[Root]") else response
                    success = await post_reply(tid, tagged, hub_token)
                    LOG.info("Root replied to mention (%s): %s",
                             "ok" if success else "FAILED", response[:80])
            except Exception as e:
                LOG.error("Mind error on mention: %s", e)

    # Persist seen IDs
    save_seen_ids(data_dir, target.id, target.seen_ids)


def parse_watch_room(spec: str) -> WatchTarget:
    """
    Parse a --watch-room argument.
    Format: ROOM_ID or ROOM_ID:mode or ROOM_ID:mode:name
    """
    parts = spec.split(":", 2)
    room_id = parts[0]
    mode = parts[1] if len(parts) > 1 else "passive"
    name = parts[2] if len(parts) > 2 else ""

    if mode not in ("passive", "mention", "active"):
        LOG.warning("Unknown watch mode '%s' for room %s — defaulting to passive", mode, room_id[:8])
        mode = "passive"

    return WatchTarget(id=room_id, watch_type="room", mode=mode, name=name)


def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description="Root Hub Daemon — Always-On Presence")
    parser.add_argument("--thread", default=DEFAULT_THREAD,
                        help="Active thread ID (Root responds to all messages)")
    parser.add_argument("--watch-room", action="append", default=[],
                        metavar="ROOM_ID[:mode[:name]]",
                        help=(
                            "Room to watch passively. Mode: passive (default), mention, active. "
                            "Can repeat for multiple rooms. "
                            "Example: --watch-room ROOM_ID:passive:CivSubstrate"
                        ))
    args = parser.parse_args()

    extra_targets = [parse_watch_room(spec) for spec in args.watch_room]
    asyncio.run(run_daemon(args.thread, extra_targets))


if __name__ == "__main__":
    main()
