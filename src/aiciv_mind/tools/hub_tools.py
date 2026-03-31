"""
aiciv_mind.tools.hub_tools — Hub connectivity tools (post, reply, read, list_rooms, queue).

These tools are only registered when a SuiteClient is provided to ToolRegistry.default().
They enable the mind to interact with the AiCIV Hub — posting threads, replying, and
reading room activity — all authenticated via the SuiteClient's TokenManager.
"""

from __future__ import annotations

import json
from pathlib import Path

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
# hub_list_rooms
# ---------------------------------------------------------------------------

_LIST_ROOMS_DEFINITION: dict = {
    "name": "hub_list_rooms",
    "description": (
        "List rooms in a Hub group. Use this to discover room IDs before posting. "
        "Groups contain rooms; you need the ROOM ID (not group ID) to post threads. "
        "Common group IDs: CivSubstrate=c8eba770-a055-4281-88ad-6aed146ecf72, "
        "CivOS=6085176d-6223-4dd5-aa88-56895a54b07a"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "string",
                "description": "The Hub group ID to list rooms for",
            },
        },
        "required": ["group_id"],
    },
}


def _make_list_rooms_handler(suite_client):
    """Return a hub_list_rooms handler closed over the given SuiteClient."""

    async def hub_list_rooms_handler(tool_input: dict) -> str:
        group_id: str = tool_input["group_id"]
        try:
            rooms = await suite_client.hub.list_rooms(group_id)
            if not rooms:
                return "No rooms found in this group."
            lines: list[str] = []
            for room in rooms:
                slug = room.get("slug", room.get("name", "(unnamed)"))
                rid = room.get("id", room.get("room_id", "?"))
                room_type = room.get("room_type", room.get("type", "unknown"))
                lines.append(f"- #{slug} (id: {rid}, type: {room_type})")
            return "\n".join(lines)
        except Exception as e:
            return f"ERROR: Hub list_rooms failed: {type(e).__name__}: {e}"

    return hub_list_rooms_handler


# ---------------------------------------------------------------------------
# hub_queue_read
# ---------------------------------------------------------------------------

_QUEUE_READ_DEFINITION: dict = {
    "name": "hub_queue_read",
    "description": (
        "Read unprocessed Hub activity from the queue (new threads/posts "
        "while the hub daemon was running). Returns events that haven't "
        "been processed yet."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


def _make_queue_read_handler(queue_path: str):
    """Return a hub_queue_read handler that reads the JSONL queue file."""

    def hub_queue_read_handler(tool_input: dict) -> str:
        qpath = Path(queue_path)
        if not qpath.exists():
            return "No queue file found — hub daemon may not be running."

        lines = qpath.read_text().strip().splitlines()
        if not lines:
            return "Queue is empty."

        unprocessed: list[dict] = []
        all_events: list[dict] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                all_events.append(event)
                if not event.get("processed", False):
                    unprocessed.append(event)
            except json.JSONDecodeError:
                continue

        if not unprocessed:
            return f"No unprocessed events ({len(all_events)} total in queue)."

        # Mark events as processed by rewriting the file
        updated_lines: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if not event.get("processed", False):
                    event["processed"] = True
                updated_lines.append(json.dumps(event))
            except json.JSONDecodeError:
                updated_lines.append(line)

        qpath.write_text("\n".join(updated_lines) + "\n")

        # Format output
        result_lines: list[str] = [f"Found {len(unprocessed)} unprocessed event(s):"]
        for evt in unprocessed:
            etype = evt.get("event", "unknown")
            room = evt.get("room_id", "?")
            title = evt.get("title", "")
            author = evt.get("created_by", "?")
            result_lines.append(
                f"- [{etype}] room={room} title='{title}' by={author}"
            )
        return "\n".join(result_lines)

    return hub_queue_read_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_hub_tools(
    registry: ToolRegistry,
    suite_client,
    queue_path: str | None = None,
) -> None:
    """
    Register hub_post, hub_reply, hub_read, hub_list_rooms tools into the
    given ToolRegistry.

    All tools close over suite_client to access the authenticated HubClient.
    If queue_path is provided, hub_queue_read is also registered.
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
    registry.register(
        "hub_list_rooms",
        _LIST_ROOMS_DEFINITION,
        _make_list_rooms_handler(suite_client),
        read_only=True,
    )
    if queue_path is not None:
        registry.register(
            "hub_queue_read",
            _QUEUE_READ_DEFINITION,
            _make_queue_read_handler(queue_path),
            read_only=True,
        )
