#!/usr/bin/env python3
"""
aiciv-mind Telegram Bridge

Routes Telegram messages from Corey directly to the aiciv-mind tool-use loop.
Maintains conversation history across messages (same process = same context window).

Usage:
    python3 tg_bridge.py

Commands:
    /start  — confirm the mind is online
    /clear  — reset conversation history (fresh context)
    /model  — show current model
    (anything else) — run through mind and reply
"""
import asyncio
import logging
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Bootstrap — load .env and add src to path before any project imports
# ---------------------------------------------------------------------------

def _bootstrap() -> None:
    root = Path(__file__).parent
    sys.path.insert(0, str(root / "src"))
    env_path = root / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

_bootstrap()

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from aiciv_mind.manifest import MindManifest
from aiciv_mind.memory import MemoryStore
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.mind import Mind


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BOT_TOKEN = "8388754468:AAEROakhpBPR1KNHjravHx3CIMH-FIyIWEc"
COREY_CHAT_ID = 437939400
MANIFEST_PATH = Path(__file__).parent / "manifests" / "primary.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("tg_bridge")


# ---------------------------------------------------------------------------
# Mind (module-level singleton — keeps conversation history alive)
# ---------------------------------------------------------------------------

_mind: Mind | None = None
_memory: MemoryStore | None = None


def _build_mind() -> tuple[Mind, MemoryStore]:
    manifest = MindManifest.from_yaml(MANIFEST_PATH)
    db_path = manifest.memory.db_path
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    memory = MemoryStore(db_path)
    tools = ToolRegistry.default(memory_store=memory)
    mind = Mind(manifest=manifest, memory=memory, tools=tools)
    return mind, memory


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------


def _only_corey(fn):
    """Decorator: silently drop messages from anyone who isn't Corey."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != COREY_CHAT_ID:
            return
        return await fn(update, context)
    return wrapper


@_only_corey
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    model = _mind.manifest.model.preferred if _mind else "unknown"
    await update.message.reply_text(
        f"aiciv-mind online.\nModel: {model}\nSend me anything."
    )


@_only_corey
async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _mind:
        _mind.clear_history()
    await update.message.reply_text("Context cleared. Fresh conversation.")


@_only_corey
async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    model = _mind.manifest.model.preferred if _mind else "unknown"
    await update.message.reply_text(f"Model: {model}")


@_only_corey
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text
    logger.info("Message: %s", user_text[:120])

    # Send acknowledgment immediately so Corey knows it's working
    ack = await update.message.reply_text("...")

    try:
        result = await _mind.run_task(user_text)

        if not result:
            await ack.edit_text("(no response)")
            return

        # Telegram max message length is 4096 chars
        if len(result) <= 4096:
            await ack.edit_text(result)
        else:
            await ack.delete()
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i : i + 4000])

    except Exception as e:
        logger.exception("Mind task failed")
        await ack.edit_text(f"Error: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    global _mind, _memory

    logger.info("Building aiciv-mind...")
    _mind, _memory = _build_mind()
    logger.info("Mind ready — model: %s", _mind.manifest.model.preferred)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Polling Telegram (chat_id=%d)...", COREY_CHAT_ID)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
