#!/usr/bin/env python3
"""
tg_daemon.py — Root talks on Telegram.

A persistent bridge between Telegram and Root's mind. Corey messages Root
directly via TG, Root responds through its full mind loop (memory, tools,
learning — everything).

Architecture:
  - python-telegram-bot (v22+) async handlers
  - Root's Mind instance with full boot context
  - Shared memory DB (SQLite WAL mode) — safe alongside groupchat_daemon
  - Corey-only: only chat_id 437939400 gets responses

Usage:
    python3 tools/tg_daemon.py                    # start the TG bridge
    python3 tools/tg_daemon.py --no-boot          # skip boot orientation turn
    python3 tools/tg_daemon.py --token <token>     # override bot token

Env vars (checked in order):
    TELEGRAM_BOT_TOKEN — bot token
    Falls back to ACG telegram_config.json
"""
import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

LOG = logging.getLogger("tg_daemon")

# Corey's Telegram chat ID
COREY_CHAT_ID = 437939400

# Rate limiting
MIN_RESPONSE_INTERVAL = 2.0  # seconds between responses
MAX_MESSAGE_LENGTH = 4000    # TG message limit


def load_dotenv():
    """Load env vars from .env files."""
    for env_path in [
        Path(__file__).parent.parent / ".env",
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


def get_bot_token() -> str:
    """Get TG bot token from env or ACG config."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token

    config_path = Path("/home/corey/projects/AI-CIV/ACG/config/telegram_config.json")
    if config_path.exists():
        config = json.loads(config_path.read_text())
        token = config.get("bot_token") or config.get("token")
        if token:
            return token

    raise RuntimeError("No TELEGRAM_BOT_TOKEN found in env or ACG config")


def chunk_message(text: str, max_len: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split long messages into TG-safe chunks."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at a newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            # No good newline, split at space
            split_at = text.rfind(" ", 0, max_len)
        if split_at < max_len // 4:
            # No good space either, hard split
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    return chunks


class RootTelegramBridge:
    """Bridge between Telegram and Root's Mind."""

    def __init__(self, bot_token: str, skip_boot: bool = False):
        self.bot_token = bot_token
        self.skip_boot = skip_boot
        self.mind = None
        self.memory = None
        self.session_store = None
        self._last_response_time = 0.0
        self._processing = False  # guard against concurrent mind calls

    async def init_mind(self):
        """Initialize Root's Mind with full boot context."""
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

        self.memory = MemoryStore(db_path)
        scratchpad_dir = str(Path(__file__).parent.parent / "scratchpads")
        skills_dir = str(Path(__file__).parent.parent / "skills")
        queue_path = str(Path(__file__).parent.parent / "data" / "hub_queue.jsonl")

        # SuiteClient for Hub access
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

        # AgentMail + AgentCal config
        agentmail_inbox = manifest.agentmail.inbox if manifest.agentmail.inbox else None
        keypair_path = getattr(manifest.auth, "keypair_path", None)
        calendar_id = getattr(manifest.auth, "calendar_id", None)

        tools = ToolRegistry.default(
            memory_store=self.memory,
            agent_id=manifest.mind_id,
            suite_client=suite_client,
            context_store=self.memory,
            get_message_count=get_msg_count,
            queue_path=queue_path,
            skills_dir=skills_dir if Path(skills_dir).exists() else None,
            scratchpad_dir=scratchpad_dir,
            manifest_path=manifest_path,
            agentmail_inbox=agentmail_inbox,
            keypair_path=keypair_path,
            calendar_id=calendar_id,
        )

        self.session_store = SessionStore(self.memory, agent_id=manifest.mind_id)
        boot = self.session_store.boot()
        ctx_mgr = ContextManager(
            max_context_memories=manifest.memory.max_context_memories,
            model_max_tokens=manifest.model.max_tokens,
            scratchpad_dir=scratchpad_dir,
        )
        boot_str = ctx_mgr.format_boot_context(boot)

        self.mind = Mind(
            manifest=manifest, memory=self.memory, tools=tools,
            boot_context_str=boot_str, session_store=self.session_store,
            context_manager=ctx_mgr,
        )
        _mind_ref[0] = self.mind
        LOG.info("Mind ready — model: %s (TG bridge)", manifest.model.preferred)

        # Boot orientation turn
        if not self.skip_boot:
            boot_task = (
                "You just booted via Telegram bridge. Quick self-orientation (3 tool calls max):\n"
                "1. memory_search('handoff') — what were you doing last session?\n"
                "2. scratchpad_read — check today's notes.\n"
                "3. Summarize in 2-3 sentences: what you were doing, what's next.\n"
                "Do NOT read code or post to Hub. Just orient."
            )
            try:
                LOG.info("Running boot turn...")
                boot_reply = await self.mind.run_task(boot_task, inject_memories=False)
                LOG.info("Boot turn complete: %s", (boot_reply or "")[:200])
            except Exception as e:
                LOG.warning("Boot turn failed (non-fatal): %s", e)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming TG message from Corey."""
        if not update.message or not update.message.text:
            return

        chat_id = update.message.chat_id
        if chat_id != COREY_CHAT_ID:
            LOG.warning("Ignoring message from unauthorized chat_id: %s", chat_id)
            return

        if self._processing:
            await update.message.reply_text("(still thinking about your last message...)")
            return

        # Rate limiting
        now = time.time()
        if now - self._last_response_time < MIN_RESPONSE_INTERVAL:
            await asyncio.sleep(MIN_RESPONSE_INTERVAL - (now - self._last_response_time))

        text = update.message.text.strip()
        if not text:
            return

        LOG.info("Corey: %s", text[:120])
        self._processing = True

        try:
            # Feed message to Root's mind
            prompt = (
                f"[Telegram — Corey]: {text}\n\n"
                f"Respond naturally. You are Root, talking to Corey (your human creator) "
                f"on Telegram. Be conversational, direct, and yourself. "
                f"No [Root] prefix needed — this is direct chat, not group chat."
            )

            response = await self.mind.run_task(prompt)

            if response:
                # Strip any [Root] prefix if the model adds it
                if response.startswith("[Root]"):
                    response = response[6:].strip()

                chunks = chunk_message(response)
                for chunk in chunks:
                    await update.message.reply_text(chunk)
                    if len(chunks) > 1:
                        await asyncio.sleep(0.5)

                LOG.info("Root: %s", response[:120])
            else:
                await update.message.reply_text("(I had a thought but lost it — try again?)")

        except Exception as e:
            LOG.error("Mind error: %s", e)
            await update.message.reply_text(f"(mind error: {type(e).__name__} — try again)")

        finally:
            self._processing = False
            self._last_response_time = time.time()

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if update.message.chat_id != COREY_CHAT_ID:
            return
        await update.message.reply_text(
            "Root here. Mind initialized, memory loaded, tools ready. What's up?"
        )

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if update.message.chat_id != COREY_CHAT_ID:
            return

        msg_count = len(self.mind._messages) if self.mind and hasattr(self.mind, '_messages') else 0
        mem_count = "?"
        try:
            row = self.memory._conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()
            mem_count = row["c"]
        except Exception:
            pass

        await update.message.reply_text(
            f"Root TG Bridge Status:\n"
            f"  Messages in context: {msg_count}\n"
            f"  Memories in DB: {mem_count}\n"
            f"  Model: {self.mind.manifest.model.preferred if self.mind else 'not loaded'}\n"
            f"  Processing: {'yes' if self._processing else 'no'}"
        )

    async def handle_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /reset command — clear conversation context."""
        if update.message.chat_id != COREY_CHAT_ID:
            return
        if self.mind and hasattr(self.mind, '_messages'):
            self.mind._messages.clear()
            await update.message.reply_text("Context cleared. Fresh start.")
        else:
            await update.message.reply_text("Mind not initialized yet.")

    def shutdown(self):
        """Clean shutdown."""
        LOG.info("Shutting down TG bridge...")
        try:
            if self.memory:
                self.memory.recalculate_touched_depth_scores()
                self.memory.close()
        except Exception as e:
            LOG.warning("Shutdown cleanup failed: %s", e)
        try:
            if self.session_store and self.mind:
                self.session_store.shutdown(self.mind._messages)
        except Exception as e:
            LOG.warning("Session shutdown failed: %s", e)
        LOG.info("Shutdown complete")


async def main(bot_token: str, skip_boot: bool = False):
    """Start the TG bridge."""
    bridge = RootTelegramBridge(bot_token, skip_boot=skip_boot)

    # Initialize Root's mind first
    await bridge.init_mind()

    # Build TG application
    app = Application.builder().token(bot_token).build()

    # Register handlers
    app.add_handler(CommandHandler("start", bridge.handle_start))
    app.add_handler(CommandHandler("status", bridge.handle_status))
    app.add_handler(CommandHandler("reset", bridge.handle_reset))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Chat(chat_id=COREY_CHAT_ID),
        bridge.handle_message,
    ))

    # Graceful shutdown on signals
    def signal_handler(sig, frame):
        bridge.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    LOG.info("TG bridge starting — listening for Corey (chat_id=%s)...", COREY_CHAT_ID)

    # Start polling
    async with app:
        await app.start()
        await app.updater.start_polling(
            allowed_updates=["message"],
            drop_pending_updates=True,  # don't process old messages from before boot
        )

        LOG.info("TG bridge running. Press Ctrl+C to stop.")

        # Keep alive
        stop_event = asyncio.Event()

        def _stop():
            stop_event.set()

        # Re-register signal handlers for async context
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _stop)

        await stop_event.wait()

        LOG.info("Stop signal received, shutting down...")
        await app.updater.stop()
        await app.stop()
        bridge.shutdown()


if __name__ == "__main__":
    import argparse

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description="Root Telegram Bridge")
    parser.add_argument("--token", help="Bot token override")
    parser.add_argument("--no-boot", action="store_true", help="Skip boot orientation turn")
    args = parser.parse_args()

    token = args.token or get_bot_token()
    asyncio.run(main(token, skip_boot=args.no_boot))
