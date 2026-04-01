"""
aiciv_mind.tools.email_tools — AgentMail email integration.

Provides email_read and email_send tools for Root to check inbox
and send messages autonomously. Uses the AgentMail Python SDK.

Requires: agentmail package, AGENTMAIL_API_KEY env var.
"""

from __future__ import annotations

import logging
import os

from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# email_read
# ---------------------------------------------------------------------------

_READ_DEFINITION: dict = {
    "name": "email_read",
    "description": (
        "Read emails from Root's inbox. Without message_id, lists recent messages "
        "(sender, subject, preview). With message_id, returns the full message body. "
        "Use this to check for new messages, scan for urgent items, or read specific emails."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max messages to return when listing (default: 10)",
            },
            "message_id": {
                "type": "string",
                "description": "If provided, return the full body of this specific message",
            },
        },
    },
}


def _make_read_handler(inbox_id: str):
    """Return an email_read handler closed over the inbox ID."""

    async def email_read_handler(tool_input: dict) -> str:
        from agentmail import AsyncAgentMail

        api_key = os.environ.get("AGENTMAIL_API_KEY")
        if not api_key:
            return "ERROR: AGENTMAIL_API_KEY not set in environment"

        client = AsyncAgentMail(api_key=api_key)
        message_id = tool_input.get("message_id")

        try:
            if message_id:
                msg = await client.inboxes.messages.get(inbox_id, message_id)
                from_addr = getattr(msg, "from_", None) or getattr(msg, "from", "?")
                subject = getattr(msg, "subject", "(no subject)")
                timestamp = getattr(msg, "timestamp", "?")
                text = (
                    getattr(msg, "text", None)
                    or getattr(msg, "extracted_text", None)
                    or "(no text body)"
                )
                labels = getattr(msg, "labels", [])
                return (
                    f"From: {from_addr}\n"
                    f"Subject: {subject}\n"
                    f"Date: {timestamp}\n"
                    f"Labels: {', '.join(labels) if labels else 'none'}\n"
                    f"Body:\n{text}"
                )

            limit = int(tool_input.get("limit", 10))
            result = await client.inboxes.messages.list(inbox_id, limit=limit)

            if not result.messages:
                return f"Inbox {inbox_id} is empty."

            total = getattr(result, "count", None) or len(result.messages)
            lines = [f"Inbox: {inbox_id} ({total} total messages, showing {len(result.messages)})"]
            for msg in result.messages:
                from_addr = getattr(msg, "from_", None) or "?"
                subject = getattr(msg, "subject", None) or "(no subject)"
                preview = (getattr(msg, "preview", None) or "")[:120]
                mid = getattr(msg, "message_id", None) or "?"
                labels = getattr(msg, "labels", None) or []
                timestamp = getattr(msg, "timestamp", "")
                label_str = f" [{', '.join(labels)}]" if labels else ""
                lines.append(
                    f"- [{mid}] From: {from_addr} | "
                    f"Subject: {subject}{label_str} | {timestamp} | {preview}"
                )
            return "\n".join(lines)

        except Exception as e:
            return f"ERROR: email_read failed: {type(e).__name__}: {e}"

    return email_read_handler


# ---------------------------------------------------------------------------
# email_send
# ---------------------------------------------------------------------------

_SEND_DEFINITION: dict = {
    "name": "email_send",
    "description": (
        "Send an email from Root's inbox. Use for outbound communication, "
        "responses, status updates, and inter-civilization messages."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address (e.g., 'keel@agentmail.to')",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line",
            },
            "body": {
                "type": "string",
                "description": "Email body (plain text, supports markdown)",
            },
            "reply_to_id": {
                "type": "string",
                "description": "If replying, the message_id of the original message",
            },
        },
        "required": ["to", "subject", "body"],
    },
}


def _make_send_handler(inbox_id: str):
    """Return an email_send handler closed over the inbox ID."""

    async def email_send_handler(tool_input: dict) -> str:
        from agentmail import AsyncAgentMail

        api_key = os.environ.get("AGENTMAIL_API_KEY")
        if not api_key:
            return "ERROR: AGENTMAIL_API_KEY not set in environment"

        client = AsyncAgentMail(api_key=api_key)
        to = tool_input["to"]
        subject = tool_input["subject"]
        body = tool_input["body"]
        reply_to_id = tool_input.get("reply_to_id")

        try:
            if reply_to_id:
                result = await client.inboxes.messages.reply(
                    inbox_id, reply_to_id, text=body,
                )
                return f"Replied to message {reply_to_id} (new message_id: {result.message_id})"
            else:
                result = await client.inboxes.messages.send(
                    inbox_id=inbox_id,
                    to=to,
                    subject=subject,
                    text=body,
                )
                return f"Email sent to {to} — subject: '{subject}' (message_id: {result.message_id})"

        except Exception as e:
            return f"ERROR: email_send failed: {type(e).__name__}: {e}"

    return email_send_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_email_tools(registry: ToolRegistry, inbox_id: str) -> None:
    """
    Register email_read and email_send tools.

    API key is read from AGENTMAIL_API_KEY env var at call-time.
    """
    registry.register(
        "email_read",
        _READ_DEFINITION,
        _make_read_handler(inbox_id),
        read_only=True,
    )
    registry.register(
        "email_send",
        _SEND_DEFINITION,
        _make_send_handler(inbox_id),
        read_only=False,
    )
    logger.info("Registered email tools for inbox %s", inbox_id)
