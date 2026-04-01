#!/usr/bin/env python3
"""
groupchat_daemon.py — Root stays alive in the Group Chat.

A persistent process that:
1. Polls a Hub thread for new posts every 5 seconds
2. Feeds them to a PERSISTENT Mind instance (messages accumulate)
3. Root responds with full conversation context
4. System prompt + boot context is KV cached
5. Conversation history grows naturally — Root remembers everything

This is the difference between "Root responds to prompts" and "Root is in the room."

Usage:
    MIND_API_KEY=... python3 tools/groupchat_daemon.py --thread <thread_id>
    MIND_API_KEY=... python3 tools/groupchat_daemon.py  # uses default thread
"""
import asyncio
import argparse
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

LOG = logging.getLogger("groupchat")

# Default thread for ACG-Root-Corey conversations
DEFAULT_THREAD = "f6518cc3-3479-4a1a-a284-2192269ca5fb"
POLL_INTERVAL = 5  # seconds


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

    AUTH = "http://5.161.90.32:8700"
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
    HUB = "http://87.99.131.49:8900"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{HUB}/api/v2/threads/{thread_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("posts", [])
    return []


async def post_reply(thread_id: str, body: str, token: str) -> bool:
    """Post a reply to the Hub thread."""
    import httpx
    HUB = "http://87.99.131.49:8900"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{HUB}/api/v2/threads/{thread_id}/posts",
            headers={"Authorization": f"Bearer {token}"},
            json={"body": body},
        )
        return resp.status_code in (200, 201)


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


async def run_daemon(thread_id: str):
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

    # Sub-mind IPC infrastructure — PrimaryBus (ZMQ ROUTER) + SubMindSpawner (libtmux)
    # Bound before ToolRegistry so spawn_submind + send_to_submind are wired in.
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

    # Track which posts we've already seen
    seen_post_ids: set[str] = set()
    acg_entity_id = "c537633e-13b3-5b33-82c6-d81a12cfbbf0"

    # Persist seen_post_ids across restarts to avoid replaying history
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    seen_posts_path = data_dir / f"seen_posts_{thread_id[:8]}.json"

    if seen_posts_path.exists():
        try:
            saved = json.loads(seen_posts_path.read_text())
            seen_post_ids = set(saved)
            LOG.info("Loaded %d seen post IDs from disk", len(seen_post_ids))
        except Exception as e:
            LOG.warning("Could not load seen_post_ids: %s", e)

    # Register SIGTERM/SIGINT handler for clean shutdown
    import signal as _signal
    _handler = _make_shutdown_handler(mind, memory, session_store, primary_bus=primary_bus)
    _signal.signal(_signal.SIGTERM, _handler)
    _signal.signal(_signal.SIGINT, _handler)
    LOG.info("SIGTERM handler registered")

    # Get initial Hub token
    hub_token = await get_hub_token()
    token_acquired = time.time()

    LOG.info("Watching thread %s (poll every %ds)...", thread_id, POLL_INTERVAL)

    while True:
        try:
            # Refresh token every 50 minutes
            if time.time() - token_acquired > 3000:
                hub_token = await get_hub_token()
                token_acquired = time.time()
                LOG.info("Hub token refreshed")

            posts = await fetch_posts(thread_id, hub_token)

            # Find new posts we haven't seen
            new_posts = []
            for post in posts:
                pid = post.get("id", "")
                if pid and pid not in seen_post_ids:
                    seen_post_ids.add(pid)
                    # Skip our own posts
                    if post.get("created_by") == acg_entity_id:
                        body = post.get("body", "")
                        if body.startswith("[Root]"):
                            continue  # Skip Root's own posts
                        if body.startswith("[ACG]"):
                            continue  # Skip ACG's posts
                    new_posts.append(post)

            for post in new_posts:
                body = post.get("body", "")
                author = "Unknown"
                if "[Corey]" in body:
                    author = "Corey"
                    body = body.replace("[Corey]", "").strip()
                elif "[ACG]" in body:
                    # Don't respond to ACG
                    continue

                if not body:
                    continue

                LOG.info("New message from %s: %s", author, body[:80])

                # Feed to persistent Mind — messages accumulate!
                prompt = f"[Group Chat — {author}]: {body}\n\nRespond naturally. You are Root, in a group chat with Corey (human creator) and ACG (Primary AI). Keep responses conversational. Prefix your response with [Root]."

                try:
                    response = await mind.run_task(prompt)
                    if response:
                        # Post response to Hub
                        tagged = f"[Root] {response}" if not response.startswith("[Root]") else response
                        success = await post_reply(thread_id, tagged, hub_token)
                        LOG.info("Root replied (%s): %s", "ok" if success else "FAILED", response[:80])
                except Exception as e:
                    LOG.error("Mind error: %s", e)

            # Persist seen_post_ids after each poll cycle
            try:
                seen_posts_path.write_text(json.dumps(list(seen_post_ids)))
            except Exception:
                pass

        except Exception as e:
            LOG.error("Poll error: %s", e)

        await asyncio.sleep(POLL_INTERVAL)


def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description="Root Group Chat Daemon")
    parser.add_argument("--thread", default=DEFAULT_THREAD, help="Hub thread ID to watch")
    args = parser.parse_args()

    asyncio.run(run_daemon(args.thread))


if __name__ == "__main__":
    main()
