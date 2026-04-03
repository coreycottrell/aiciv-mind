"""
aiciv_mind.tools.message_tools — Inter-mind messaging tool.

send_message is available to PRIMARY and TEAM_LEAD roles. It sends a
MindMessage to another mind via the ZMQ bus.  This is how hierarchical
communication works: Primary sends objectives to team leads, team leads
send summaries back to Primary.
"""

from __future__ import annotations

import asyncio

from aiciv_mind.ipc.messages import MindMessage
from aiciv_mind.tools import ToolRegistry


_SEND_DEFINITION: dict = {
    "name": "send_message",
    "description": (
        "Send a message to another mind via the IPC bus. "
        "Use to communicate objectives, status updates, questions, "
        "or results to other minds in the hierarchy."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "The mind_id of the recipient",
            },
            "content": {
                "type": "string",
                "description": "The message content to send",
            },
            "message_type": {
                "type": "string",
                "description": (
                    "Message type: 'status' (update), 'question' (needs response), "
                    "'result' (task result), 'directive' (objective/instruction)"
                ),
                "default": "status",
            },
        },
        "required": ["to", "content"],
    },
}


def _make_send_handler(bus, sender_id: str):
    """Return async send_message handler closed over bus and sender identity."""

    async def handler(tool_input: dict) -> str:
        to = tool_input.get("to", "").strip()
        content = tool_input.get("content", "").strip()
        message_type = tool_input.get("message_type", "status").strip()

        if not to:
            return "ERROR: 'to' (recipient mind_id) is required"
        if not content:
            return "ERROR: 'content' is required"

        valid_types = ("status", "question", "result", "directive")
        if message_type not in valid_types:
            return f"ERROR: message_type must be one of {valid_types}"

        try:
            msg = MindMessage.log(
                sender=sender_id,
                recipient=to,
                level="INFO",
                message=f"[{message_type}] {content}",
            )
            await bus.send(msg)
            return f"Message sent to '{to}': [{message_type}] {content[:100]}{'...' if len(content) > 100 else ''}"
        except Exception as e:
            return f"ERROR: Failed to send message: {type(e).__name__}: {e}"

    return handler


def register_message_tools(
    registry: ToolRegistry,
    bus,
    sender_id: str,
) -> None:
    """Register send_message tool."""
    registry.register(
        "send_message",
        _SEND_DEFINITION,
        _make_send_handler(bus, sender_id),
        read_only=False,
    )
