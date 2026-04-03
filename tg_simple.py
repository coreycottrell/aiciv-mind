#!/usr/bin/env python3
"""
aiciv-mind Telegram bridge — hardened always-on daemon.

Raw HTTP polling (no python-telegram-bot library — avoids getUpdates conflict bugs).
Full Mind instance with boot context, session lifecycle, all tools.

Hardening:
  - Reconnect with exponential backoff on connection drops
  - Consecutive error tracking with safety valve (auto-restart after 20 failures)
  - Heartbeat logging every 60 poll cycles (~30 min at 30s long-poll)
  - Message consistency repair (prevents "must alternate" API errors)
  - Graceful SIGTERM shutdown (writes handoff, closes memory)
  - Offset persistence across restarts
  - httpx client recreation on connection death

Usage:
    python3 tg_simple.py                  # standard launch
    python3 tg_simple.py --no-boot        # skip boot orientation turn

Env:
    AICIV_MIND_TG_TOKEN   — @aiciv_mind_bot token (required)
    AICIV_MIND_CHAT_ID    — allowed chat (default: 437939400 = Corey)
    ACG_PANE              — tmux pane for ACG injection (optional)
"""
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent / "src"))

# ---------------------------------------------------------------------------
# Env loading (no external dependency on python-dotenv)
# ---------------------------------------------------------------------------

def load_dotenv():
    """Load .env files without requiring python-dotenv."""
    for env_path in [
        Path(__file__).parent / ".env",
        Path("/home/corey/projects/AI-CIV/ACG/.env"),
    ]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("tg-mind")

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

# Reliability constants
MAX_CONSECUTIVE_ERRORS = 20
LONG_POLL_TIMEOUT = 30       # seconds (TG long-poll)
HEARTBEAT_INTERVAL = 60      # poll cycles between heartbeats
BACKOFF_BASE = 2.0           # exponential backoff base (seconds)
BACKOFF_MAX = 60.0           # max backoff (seconds)
MAX_TG_MSG_LEN = 4096        # Telegram message limit


# ---------------------------------------------------------------------------
# Offset persistence
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Telegram API helpers (with retry)
# ---------------------------------------------------------------------------

async def tg_send(
    client: httpx.AsyncClient, chat_id: int, text: str,
    reply_to: int = None, retries: int = 2,
) -> dict:
    """Send a TG message with retry on transient failure."""
    # Escape markdown chars that cause parse errors — fall back to no parse_mode
    payload = {"chat_id": chat_id, "text": text[:MAX_TG_MSG_LEN], "parse_mode": "Markdown"}
    if reply_to:
        payload["reply_to_message_id"] = reply_to

    for attempt in range(retries + 1):
        try:
            r = await client.post(f"{TG_API}/sendMessage", json=payload, timeout=30)
            data = r.json()
            if data.get("ok"):
                return data
            # Markdown parse error — retry without parse_mode
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


def chunk_message(text: str, max_len: int = 4000) -> list[str]:
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


# ---------------------------------------------------------------------------
# ACG tmux injection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Mind initialization (matches groupchat_daemon pattern)
# ---------------------------------------------------------------------------

async def build_mind():
    """Build a full Mind instance with boot context, session store, all tools."""
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

    # SuiteClient for Hub tools
    suite_client = None
    try:
        auth_cfg = getattr(manifest, "auth", None)
        keypair_path = getattr(auth_cfg, "keypair_path", None) if auth_cfg else None
        if keypair_path and Path(keypair_path).exists():
            from aiciv_mind.suite.client import SuiteClient
            suite_client = await SuiteClient.connect(keypair_path, eager_auth=True)
            log.info("SuiteClient connected — hub tools enabled")
    except Exception as e:
        log.info("SuiteClient unavailable: %s", e)

    skills_dir = str(Path(__file__).parent / "skills")
    scratchpad_dir = str(Path(__file__).parent / "scratchpads")
    manifest_path = str(MANIFEST_PATH)
    queue_path = str(DATA_DIR / "hub_queue.jsonl")

    _mind_ref = [None]
    def get_msg_count():
        return len(_mind_ref[0]._messages) if _mind_ref[0] else 0

    # AgentMail + AgentCal config
    agentmail_inbox = manifest.agentmail.inbox if manifest.agentmail.inbox else None
    kp_path = getattr(manifest.auth, "keypair_path", None)
    calendar_id = getattr(manifest.auth, "calendar_id", None)

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
        log.info("Boot context loaded: session %s (prior: %d)", boot.session_id, boot.session_count)

    mind = Mind(
        manifest=manifest, memory=memory, tools=tools,
        boot_context_str=boot_str, session_store=session_store,
        context_manager=ctx_mgr,
    )
    _mind_ref[0] = mind
    log.info("Mind ready — model: %s (full tool registry)", manifest.model.preferred)
    return mind, memory, session_store


# ---------------------------------------------------------------------------
# Shutdown handler
# ---------------------------------------------------------------------------

def make_shutdown_handler(mind, memory, session_store):
    """Create SIGTERM/SIGINT handler for graceful shutdown."""
    def handler(signum, frame):
        log.info("Signal %s received — shutting down gracefully", signum)
        try:
            memory.recalculate_touched_depth_scores()
        except Exception as e:
            log.warning("depth score recalc failed: %s", e)
        try:
            session_store.shutdown(mind._messages)
        except Exception as e:
            log.warning("session shutdown failed: %s", e)
        try:
            memory.close()
        except Exception:
            pass
        log.info("Shutdown complete")
        sys.exit(0)
    return handler


# ---------------------------------------------------------------------------
# Main poll loop
# ---------------------------------------------------------------------------

async def run(skip_boot: bool = False):
    """Main daemon loop with hardened error handling."""
    if not TG_TOKEN:
        log.error("AICIV_MIND_TG_TOKEN not set — cannot start")
        sys.exit(1)

    mind, memory, session_store = await build_mind()

    # Register signal handlers
    handler = make_shutdown_handler(mind, memory, session_store)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
    log.info("Signal handlers registered")

    # Boot orientation turn
    if not skip_boot:
        try:
            log.info("Running boot turn...")
            boot_reply = await mind.run_task(
                "You just booted via Telegram bridge (@aiciv_mind_bot). Quick self-orientation:\n"
                "1. memory_search('handoff') — what were you doing last?\n"
                "2. scratchpad_read — check today's notes.\n"
                "3. Summarize in 2 sentences: what you were doing, what's next.\n"
                "Do NOT read code or post to Hub. Just orient.",
                inject_memories=False,
            )
            log.info("Boot complete: %s", (boot_reply or "")[:200])
        except Exception as e:
            log.warning("Boot turn failed (non-fatal): %s", e)

    offset = _load_offset()
    log.info("Starting offset: %d", offset)

    poll_count = 0
    consecutive_errors = 0
    processing = False  # guard against overlapping mind calls
    client = httpx.AsyncClient(timeout=httpx.Timeout(LONG_POLL_TIMEOUT + 10, connect=10))

    log.info("Polling @aiciv_mind_bot (chat_id=%s)...", ALLOWED_CHAT)

    while True:
        try:
            poll_count += 1

            # ── Heartbeat
            if poll_count % HEARTBEAT_INTERVAL == 0:
                msg_count = len(mind._messages) if hasattr(mind, "_messages") else -1
                log.info(
                    "HEARTBEAT: poll=%d, ctx_msgs=%d, errors_streak=%d, processing=%s",
                    poll_count, msg_count, consecutive_errors, processing,
                )

            # ── Message consistency repair
            if hasattr(mind, "_messages") and len(mind._messages) >= 2:
                last_role = mind._messages[-1].get("role")
                prev_role = mind._messages[-2].get("role")
                if last_role == prev_role == "user":
                    log.warning("Message consistency repair: consecutive user messages — popping stale")
                    mind._messages.pop()

            # ── Long-poll TG for updates
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
            except httpx.TimeoutException:
                continue  # Normal long-poll timeout — loop back
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as e:
                # Connection dropped — recreate client with backoff
                backoff = min(BACKOFF_BASE * (2 ** consecutive_errors), BACKOFF_MAX)
                log.warning("Connection lost (%s) — reconnecting in %.1fs", type(e).__name__, backoff)
                await asyncio.sleep(backoff)
                try:
                    await client.aclose()
                except Exception:
                    pass
                client = httpx.AsyncClient(timeout=httpx.Timeout(LONG_POLL_TIMEOUT + 10, connect=10))
                consecutive_errors += 1
                continue

            if not data.get("ok"):
                log.warning("TG API error: %s", data)
                await asyncio.sleep(5)
                consecutive_errors += 1
                continue

            # ── Check ACG→Root file queue
            if MSG_QUEUE.exists() and not processing:
                try:
                    acg_msg = MSG_QUEUE.read_text().strip()
                    if acg_msg:
                        MSG_QUEUE.unlink()
                        log.info("ACG→Root: %s", acg_msg[:100])
                        processing = True
                        try:
                            result = await mind.run_task(acg_msg)
                            inject_to_acg(result or "(no response)")
                        finally:
                            processing = False
                except Exception as e:
                    log.error("Queue error: %s", e)
                    processing = False

            # ── Process TG updates
            for update in data.get("result", []):
                new_offset = update["update_id"] + 1
                if new_offset != offset:
                    offset = new_offset
                    _save_offset(offset)

                msg = update.get("message")
                if not msg or msg.get("chat", {}).get("id") != ALLOWED_CHAT:
                    continue
                text = msg.get("text", "")
                if not text:
                    continue

                msg_id = msg["message_id"]
                log.info("Corey: %s", text[:120])

                # ── Commands
                if text.startswith("/start"):
                    model = mind.manifest.model.preferred
                    msg_count = len(mind._messages) if hasattr(mind, "_messages") else 0
                    await tg_send(client, ALLOWED_CHAT, f"Root online.\nModel: {model}\nContext: {msg_count} msgs", msg_id)
                    continue

                if text.startswith("/clear"):
                    if hasattr(mind, "_messages"):
                        mind._messages.clear()
                    await tg_send(client, ALLOWED_CHAT, "Context cleared.", msg_id)
                    continue

                if text.startswith("/status"):
                    msg_count = len(mind._messages) if hasattr(mind, "_messages") else 0
                    mem_count = "?"
                    try:
                        row = memory._conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()
                        mem_count = row["c"]
                    except Exception:
                        pass
                    await tg_send(
                        client, ALLOWED_CHAT,
                        f"Root TG Bridge:\n"
                        f"  Polls: {poll_count}\n"
                        f"  Context messages: {msg_count}\n"
                        f"  Memories: {mem_count}\n"
                        f"  Model: {mind.manifest.model.preferred}\n"
                        f"  Error streak: {consecutive_errors}\n"
                        f"  Processing: {processing}",
                        msg_id,
                    )
                    continue

                if processing:
                    await tg_send(client, ALLOWED_CHAT, "(still thinking...)", msg_id)
                    continue

                # ── Send "thinking..." placeholder, then run through Mind
                thinking = await tg_send(client, ALLOWED_CHAT, "...", msg_id)
                thinking_id = thinking.get("result", {}).get("message_id")
                processing = True

                try:
                    result = await mind.run_task(text)

                    if not result:
                        result = "(no response)"

                    chunks = chunk_message(result)
                    if len(chunks) == 1 and thinking_id:
                        await tg_edit(client, ALLOWED_CHAT, thinking_id, chunks[0])
                    else:
                        # Delete the "..." placeholder and send chunks
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
                    error_text = f"Error: {type(e).__name__}: {str(e)[:400]}"
                    if thinking_id:
                        await tg_edit(client, ALLOWED_CHAT, thinking_id, error_text)
                    else:
                        await tg_send(client, ALLOWED_CHAT, error_text, msg_id)
                finally:
                    processing = False

            # Successful cycle — reset error counter
            consecutive_errors = 0

        except Exception as e:
            consecutive_errors += 1
            log.error(
                "Poll loop error (streak=%d/%d): %s",
                consecutive_errors, MAX_CONSECUTIVE_ERRORS, e,
                exc_info=True,
            )
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.critical(
                    "FATAL: %d consecutive errors — exiting for restart. Last: %s",
                    MAX_CONSECUTIVE_ERRORS, e,
                )
                # Clean shutdown before exit
                try:
                    memory.recalculate_touched_depth_scores()
                    session_store.shutdown(mind._messages)
                    memory.close()
                except Exception:
                    pass
                sys.exit(1)

            backoff = min(BACKOFF_BASE * consecutive_errors, BACKOFF_MAX)
            await asyncio.sleep(backoff)

        except BaseException as e:
            if isinstance(e, (SystemExit, KeyboardInterrupt)):
                log.info("Received %s — shutting down", type(e).__name__)
                raise
            log.error("BaseException in poll loop: %s: %s — continuing", type(e).__name__, e)
            consecutive_errors += 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Root Telegram Bridge (hardened)")
    parser.add_argument("--no-boot", action="store_true", help="Skip boot orientation turn")
    args = parser.parse_args()
    asyncio.run(run(skip_boot=args.no_boot))
