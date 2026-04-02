"""
aiciv_mind.tools.calendar_tools — AgentCal calendar management tools.

These tools let Root schedule events, read events, and manage its own
AgentCal calendar. Authentication is via AgentAuth challenge-response
using Root's Ed25519 keypair.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from aiciv_mind.tools import ToolRegistry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENTAUTH_URL = "http://5.161.90.32:8700"
AGENTCAL_URL = "http://5.161.90.32:8300"


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

async def _get_agentcal_token(keypair_path: str) -> str:
    """Get a fresh JWT via AgentAuth challenge-response using the given keypair."""
    import httpx
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    kp = json.loads(Path(keypair_path).read_text())
    priv_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(kp["private_key"]))

    async with httpx.AsyncClient(timeout=10) as client:
        ch = (await client.post(
            f"{AGENTAUTH_URL}/challenge",
            json={"civ_id": kp["civ_id"]},
        )).json()
        sig = priv_key.sign(base64.b64decode(ch["challenge"]))
        resp = (await client.post(
            f"{AGENTAUTH_URL}/verify",
            json={
                "civ_id": kp["civ_id"],
                "signature": base64.b64encode(sig).decode(),
            },
        )).json()

    return resp["token"]


# ---------------------------------------------------------------------------
# calendar_list_events
# ---------------------------------------------------------------------------

_LIST_EVENTS_DEFINITION: dict = {
    "name": "calendar_list_events",
    "description": (
        "List upcoming events from your AgentCal calendar. "
        "Returns event titles, times, and IDs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of events to return (default: 20)",
                "default": 20,
            },
        },
    },
}


def _make_list_events_handler(keypair_path: str, calendar_id: str):
    """Return a calendar_list_events handler closed over keypair_path and calendar_id."""

    async def calendar_list_events_handler(tool_input: dict) -> str:
        import httpx

        limit = int(tool_input.get("limit", 20))
        try:
            token = await _get_agentcal_token(keypair_path)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{AGENTCAL_URL}/api/v1/calendars/{calendar_id}/events",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code != 200:
                    return f"ERROR: AgentCal returned status {resp.status_code}: {resp.text}"

                events = resp.json()
                if isinstance(events, dict):
                    events = events.get("events", events.get("items", []))

                if not events:
                    return "No events found on your calendar."

                lines: list[str] = [f"Calendar events ({min(len(events), limit)} shown):"]
                for event in events[:limit]:
                    eid = event.get("id", event.get("event_id", "?"))
                    title = event.get("title", "(untitled)")
                    start = event.get("start_time", "?")
                    end = event.get("end_time", "?")
                    desc = event.get("description", "")
                    desc_preview = f" — {desc[:80]}" if desc else ""
                    lines.append(
                        f"- **{title}** ({start} to {end}){desc_preview} [id: {eid}]"
                    )
                return "\n".join(lines)
        except Exception as e:
            return f"ERROR: calendar_list_events failed: {type(e).__name__}: {e}"

    return calendar_list_events_handler


# ---------------------------------------------------------------------------
# calendar_create_event
# ---------------------------------------------------------------------------

_CREATE_EVENT_DEFINITION: dict = {
    "name": "calendar_create_event",
    "description": (
        "Create a new event on your AgentCal calendar. "
        "Times must be ISO 8601 format (e.g. 2026-04-01T14:00:00Z)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Event title",
            },
            "description": {
                "type": "string",
                "description": "Event description (optional)",
                "default": "",
            },
            "start_time": {
                "type": "string",
                "description": "Start time in ISO 8601 format (e.g. 2026-04-01T14:00:00Z)",
            },
            "end_time": {
                "type": "string",
                "description": "End time in ISO 8601 format (e.g. 2026-04-01T15:00:00Z)",
            },
            "metadata": {
                "type": "string",
                "description": "Optional JSON metadata string (e.g. '{\"priority\": \"high\"}')",
                "default": "",
            },
        },
        "required": ["title", "start_time", "end_time"],
    },
}


def _make_create_event_handler(keypair_path: str, calendar_id: str):
    """Return a calendar_create_event handler closed over keypair_path and calendar_id."""

    async def calendar_create_event_handler(tool_input: dict) -> str:
        import httpx

        title = tool_input.get("title", "").strip()
        description = tool_input.get("description", "").strip()
        start_time = tool_input.get("start_time", "").strip()
        end_time = tool_input.get("end_time", "").strip()
        metadata_raw = tool_input.get("metadata", "").strip()

        if not title or not start_time or not end_time:
            return "ERROR: title, start_time, and end_time are required"

        payload: dict = {
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
        }
        if description:
            payload["description"] = description
        if metadata_raw:
            try:
                payload["metadata"] = json.loads(metadata_raw)
            except json.JSONDecodeError:
                return f"ERROR: metadata must be valid JSON (got: {metadata_raw[:100]})"

        try:
            token = await _get_agentcal_token(keypair_path)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{AGENTCAL_URL}/api/v1/calendars/{calendar_id}/events",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
                if resp.status_code not in (200, 201):
                    return f"ERROR: AgentCal returned status {resp.status_code}: {resp.text}"

                result = resp.json()
                eid = result.get("id", result.get("event_id", "unknown"))
                return f"Event created: '{title}' ({start_time} to {end_time}) [id: {eid}]"
        except Exception as e:
            return f"ERROR: calendar_create_event failed: {type(e).__name__}: {e}"

    return calendar_create_event_handler


# ---------------------------------------------------------------------------
# calendar_delete_event
# ---------------------------------------------------------------------------

_DELETE_EVENT_DEFINITION: dict = {
    "name": "calendar_delete_event",
    "description": "Delete an event from your AgentCal calendar by event ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The event ID to delete",
            },
        },
        "required": ["event_id"],
    },
}


def _make_delete_event_handler(keypair_path: str, calendar_id: str):
    """Return a calendar_delete_event handler closed over keypair_path and calendar_id."""

    async def calendar_delete_event_handler(tool_input: dict) -> str:
        import httpx

        event_id = tool_input.get("event_id", "").strip()
        if not event_id:
            return "ERROR: event_id is required"

        try:
            token = await _get_agentcal_token(keypair_path)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.delete(
                    f"{AGENTCAL_URL}/api/v1/calendars/{calendar_id}/events/{event_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code not in (200, 204):
                    return f"ERROR: AgentCal returned status {resp.status_code}: {resp.text}"

                return f"Event {event_id} deleted successfully."
        except Exception as e:
            return f"ERROR: calendar_delete_event failed: {type(e).__name__}: {e}"

    return calendar_delete_event_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_calendar_tools(
    registry: ToolRegistry,
    keypair_path: str,
    calendar_id: str,
) -> None:
    """Register calendar_list_events, calendar_create_event, calendar_delete_event."""
    registry.register(
        "calendar_list_events",
        _LIST_EVENTS_DEFINITION,
        _make_list_events_handler(keypair_path, calendar_id),
        read_only=True,
    )
    registry.register(
        "calendar_create_event",
        _CREATE_EVENT_DEFINITION,
        _make_create_event_handler(keypair_path, calendar_id),
        read_only=False,
    )
    registry.register(
        "calendar_delete_event",
        _DELETE_EVENT_DEFINITION,
        _make_delete_event_handler(keypair_path, calendar_id),
        read_only=False,
    )
