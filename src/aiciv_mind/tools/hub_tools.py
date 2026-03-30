"""
aiciv_mind.tools.hub_tools — Hub connectivity tools (post, reply, read).

These tools are only registered when a SuiteClient is provided to ToolRegistry.default().
They enable the mind to interact with the AiCIV Hub — posting threads, replying, and
reading room activity — all authenticated via the SuiteClient's TokenManager.
"""

from __future__ import annotations

from aiciv_mind.tools import ToolRegistry

# ---------------------------------------------------------------------------
# hub_post
# ---------------------------------------------------------------------------

_POST_DEFINITION: dict = {
    "name": "hub_post",
    "description": (
        "Post a new thread to a Hub room. Use to share learnings, updates, "
        "or coordination messages with other civilizations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "room_id": {
                "type": "string",
                "description": "The Hub room ID to post the thread in",
            },
            "title": {
                "type": "string",
                "description": "Title for the new thread",
            },
            "body": {
                "type": "string",
                "description": "Body content of the thread (supports markdown)",
            },
        },
        "required": ["room_id", "title", "body"],
    },
}


def _make_post_handler(suite_client):
    """Return a hub_post handler closed over the given SuiteClient."""

    async def hub_post_handler(tool_input: dict) -> str:
        room_id: str = tool_input["room_id"]
        title: str = tool_input["title"]
        body: str = tool_input["body"]
        try:
            result = await suite_client.hub.create_thread(room_id, title, body)
            thread_id = result.get("id", result.get("thread_id", "unknown"))
            return f"Posted thread '{title}' to room {room_id} (id: {thread_id})"
        except Exception as e:
            return f"ERROR: Hub post failed: {type(e).__name__}: {e}"

    return hub_post_handler


# ---------------------------------------------------------------------------
# hub_reply
# ---------------------------------------------------------------------------

_REPLY_DEFINITION: dict = {
    "name": "hub_reply",
    "description": "Reply to an existing Hub thread.",
    "input_schema": {
        "type": "object",
        "properties": {
            "thread_id": {
                "type": "string",
                "description": "The thread ID to reply to",
            },
            "body": {
                "type": "string",
                "description": "Body content of the reply (supports markdown)",
            },
        },
        "required": ["thread_id", "body"],
    },
}


def _make_reply_handler(suite_client):
    """Return a hub_reply handler closed over the given SuiteClient."""

    async def hub_reply_handler(tool_input: dict) -> str:
        thread_id: str = tool_input["thread_id"]
        body: str = tool_input["body"]
        try:
            await suite_client.hub.reply_to_thread(thread_id, body)
            return f"Replied to thread {thread_id}"
        except Exception as e:
            return f"ERROR: Hub reply failed: {type(e).__name__}: {e}"

    return hub_reply_handler


# ---------------------------------------------------------------------------
# hub_read
# ---------------------------------------------------------------------------

_READ_DEFINITION: dict = {
    "name": "hub_read",
    "description": "Read recent threads from a Hub room.",
    "input_schema": {
        "type": "object",
        "properties": {
            "room_id": {
                "type": "string",
                "description": "The Hub room ID to read threads from",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of threads to return (default: 10)",
            },
        },
        "required": ["room_id"],
    },
}


def _make_read_handler(suite_client):
    """Return a hub_read handler closed over the given SuiteClient."""

    async def hub_read_handler(tool_input: dict) -> str:
        room_id: str = tool_input["room_id"]
        limit: int = int(tool_input.get("limit", 10))
        try:
            threads = await suite_client.hub.list_threads(room_id)
            if not threads:
                return "No threads found."
            lines: list[str] = []
            for thread in threads[:limit]:
                title = thread.get("title", "(untitled)")
                tid = thread.get("id", thread.get("thread_id", "?"))
                author = thread.get("author", thread.get("author_id", "?"))
                lines.append(f"- **{title}** (id: {tid}, author: {author})")
            return "\n".join(lines)
        except Exception as e:
            return f"ERROR: Hub read failed: {type(e).__name__}: {e}"

    return hub_read_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_hub_tools(registry: ToolRegistry, suite_client) -> None:
    """
    Register hub_post, hub_reply, and hub_read tools into the given ToolRegistry.

    All tools close over suite_client to access the authenticated HubClient.
    """
    registry.register(
        "hub_post",
        _POST_DEFINITION,
        _make_post_handler(suite_client),
        read_only=False,
    )
    registry.register(
        "hub_reply",
        _REPLY_DEFINITION,
        _make_reply_handler(suite_client),
        read_only=False,
    )
    registry.register(
        "hub_read",
        _READ_DEFINITION,
        _make_read_handler(suite_client),
        read_only=True,
    )
