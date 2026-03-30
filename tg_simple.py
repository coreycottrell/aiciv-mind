#!/usr/bin/env python3
"""
aiciv-mind Telegram bridge — minimal raw HTTP version.
No python-telegram-bot library (avoids getUpdates conflict bugs).

Usage: AICIV_MIND_TG_TOKEN=... MIND_API_KEY=... python3 tg_simple.py
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "AI-CIV/ACG/.env")
load_dotenv(Path(__file__).parent / ".env")

from aiciv_mind.manifest import MindManifest
from aiciv_mind.memory import MemoryStore
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.mind import Mind

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("tg-mind")

TG_TOKEN = os.environ.get("AICIV_MIND_TG_TOKEN", "")
ALLOWED_CHAT = int(os.environ.get("AICIV_MIND_CHAT_ID", "437939400"))
TG_API = f"https://api.telegram.org/bot{TG_TOKEN}"

MANIFEST_PATH = Path(__file__).parent / "manifests" / "primary.yaml"


async def tg_send(client: httpx.AsyncClient, chat_id: int, text: str, reply_to: int = None) -> dict:
    """Send a message via Telegram API."""
    payload = {"chat_id": chat_id, "text": text[:4096], "parse_mode": "Markdown"}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    r = await client.post(f"{TG_API}/sendMessage", json=payload, timeout=30)
    return r.json()


async def tg_edit(client: httpx.AsyncClient, chat_id: int, msg_id: int, text: str) -> dict:
    """Edit a message."""
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text[:4096], "parse_mode": "Markdown"}
    r = await client.post(f"{TG_API}/editMessageText", json=payload, timeout=30)
    return r.json()


async def main():
    if not TG_TOKEN:
        log.error("Set AICIV_MIND_TG_TOKEN")
        return

    # Build the mind
    manifest = MindManifest.from_yaml(str(MANIFEST_PATH))
    memory = MemoryStore(manifest.memory.db_path)
    tools = ToolRegistry.default(memory_store=memory)
    mind = Mind(manifest=manifest, memory=memory, tools=tools)
    log.info("Mind ready — model: %s", manifest.model.preferred)

    offset = 0
    async with httpx.AsyncClient() as client:
        log.info("Polling Telegram for @aiciv_mind_bot (chat_id=%s)...", ALLOWED_CHAT)

        while True:
            try:
                r = await client.get(
                    f"{TG_API}/getUpdates",
                    params={"offset": offset, "timeout": 30, "allowed_updates": '["message"]'},
                    timeout=35,
                )
                data = r.json()
                if not data.get("ok"):
                    log.warning("TG error: %s", data)
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message")
                    if not msg or msg.get("chat", {}).get("id") != ALLOWED_CHAT:
                        continue
                    text = msg.get("text", "")
                    if not text:
                        continue

                    msg_id = msg["message_id"]
                    log.info("Corey: %s", text[:100])

                    # Handle /start
                    if text.startswith("/start"):
                        await tg_send(client, ALLOWED_CHAT, f"aiciv-mind online. Model: `{manifest.model.preferred}`", msg_id)
                        continue

                    if text.startswith("/clear"):
                        mind._messages.clear()
                        await tg_send(client, ALLOWED_CHAT, "Context cleared.", msg_id)
                        continue

                    # Send "thinking..." placeholder
                    thinking = await tg_send(client, ALLOWED_CHAT, "...", msg_id)
                    thinking_id = thinking.get("result", {}).get("message_id")

                    # Run through the mind
                    try:
                        result = await mind.run_task(text)
                        if thinking_id:
                            await tg_edit(client, ALLOWED_CHAT, thinking_id, result or "(no response)")
                        else:
                            await tg_send(client, ALLOWED_CHAT, result or "(no response)", msg_id)
                    except Exception as e:
                        log.error("Mind error: %s", e)
                        error_text = f"Error: {str(e)[:500]}"
                        if thinking_id:
                            await tg_edit(client, ALLOWED_CHAT, thinking_id, error_text)
                        else:
                            await tg_send(client, ALLOWED_CHAT, error_text, msg_id)

            except httpx.TimeoutException:
                continue  # Normal long-poll timeout
            except Exception as e:
                log.error("Poll error: %s", e)
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
