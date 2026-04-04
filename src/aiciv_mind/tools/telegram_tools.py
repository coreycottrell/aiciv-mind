"""
aiciv_mind.tools.telegram_tools — Telegram outbound messaging.

Gives Root the ability to SEND messages to Corey via Telegram,
not just receive them. Uses the same bot token as the unified daemon.

Environment:
    AICIV_MIND_TG_TOKEN  — Telegram bot token
    AICIV_MIND_CHAT_ID   — Allowed chat ID (default: 437939400 = Corey)
"""

from __future__ import annotations

import logging
import os

import httpx

from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)

_TELEGRAM_SEND_DEFINITION: dict = {
    "name": "telegram_send",
    "description": (
        "Send a message to Corey via Telegram. Use for status updates, "
        "questions that need human input, or reporting significant results. "
        "Messages support Markdown formatting."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message text to send (Markdown supported)",
            },
        },
        "required": ["message"],
    },
}

# Telegram message length limit
_MAX_TG_MSG_LEN = 4096


def _make_telegram_send_handler(bot_token: str, chat_id: int):
    """Return async telegram_send handler."""

    async def handler(tool_input: dict) -> str:
        message = tool_input.get("message", "").strip()
        if not message:
            return "ERROR: message is required"

        if len(message) > _MAX_TG_MSG_LEN:
            message = message[:_MAX_TG_MSG_LEN - 20] + "\n\n[truncated]"

        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    msg_id = data.get("result", {}).get("message_id", "?")
                    return f"Message sent to Telegram (msg_id: {msg_id})"
                else:
                    return f"ERROR: Telegram API returned {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return f"ERROR: Failed to send Telegram message: {type(e).__name__}: {e}"

    return handler


def register_telegram_tools(registry: ToolRegistry) -> None:
    """Register telegram_send tool if bot token is available."""
    bot_token = os.environ.get("AICIV_MIND_TG_TOKEN", "")
    chat_id = int(os.environ.get("AICIV_MIND_CHAT_ID", "437939400"))

    if not bot_token:
        logger.info("AICIV_MIND_TG_TOKEN not set — telegram_send tool not registered")
        return

    registry.register(
        "telegram_send",
        _TELEGRAM_SEND_DEFINITION,
        _make_telegram_send_handler(bot_token, chat_id),
        read_only=False,
        timeout=20.0,
    )
    logger.info("telegram_send tool registered (chat_id: %d)", chat_id)
