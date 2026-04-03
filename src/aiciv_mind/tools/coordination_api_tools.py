"""
aiciv_mind.tools.coordination_api_tools — Inter-mind coordination tools.

publish_surface and read_surface enable Primary minds to advertise
capabilities and discover peer minds. Available to PRIMARY role only.

Transport: Hub API (HTTP POST/GET to group threads). This is the v0.3
minimum viable inter-mind connection — the same Hub that carries
intra-civ messages carries inter-civ coordination.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiciv_mind.coordination import (
    CoordinationSurface,
    CrossMindMessage,
    CrossMindMsgType,
    VerticalCapability,
)
from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# publish_surface
# ---------------------------------------------------------------------------

_PUBLISH_SURFACE_DEFINITION: dict = {
    "name": "publish_surface",
    "description": (
        "Publish this mind's coordination surface to the Hub for peer discovery. "
        "Other minds can read the surface to discover available team leads, "
        "capabilities, and fitness scores. Call this at session start or when "
        "capabilities change."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "active_priorities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Current priorities this mind is focused on",
            },
            "team_leads": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "vertical": {"type": "string"},
                        "capabilities": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "fitness_composite": {"type": "number"},
                    },
                    "required": ["vertical"],
                },
                "description": "Team lead verticals with capabilities and fitness",
            },
        },
        "required": [],
    },
}


def _make_publish_handler(
    suite_client,
    mind_id: str,
    civ_id: str,
    coordination_thread_id: str = "",
):
    """Return async publish_surface handler."""

    async def handler(tool_input: dict) -> str:
        team_leads_raw = tool_input.get("team_leads", [])
        active_priorities = tool_input.get("active_priorities", [])

        team_leads = []
        for tl in team_leads_raw:
            team_leads.append(VerticalCapability(
                vertical=tl.get("vertical", ""),
                capabilities=tl.get("capabilities", []),
                fitness_composite=tl.get("fitness_composite", 0.0),
            ))

        surface = CoordinationSurface(
            mind_id=mind_id,
            civ_id=civ_id,
            team_leads=team_leads,
            active_priorities=active_priorities,
        )

        if not coordination_thread_id:
            return (
                f"Surface built ({len(team_leads)} verticals) but no coordination "
                f"thread configured — surface not published to Hub.\n"
                f"Surface JSON:\n{surface.to_json()}"
            )

        try:
            msg = CrossMindMessage.surface_publish(civ_id, mind_id, surface)
            body = f"[COORDINATION SURFACE]\n```json\n{surface.to_json()}\n```"

            result = await suite_client.post_to_thread(
                coordination_thread_id, body
            )
            return (
                f"Published coordination surface to Hub thread "
                f"{coordination_thread_id[:8]}...\n"
                f"Verticals: {', '.join(surface.verticals())}\n"
                f"Priorities: {', '.join(active_priorities) or 'none'}"
            )
        except Exception as e:
            return (
                f"ERROR publishing surface: {type(e).__name__}: {e}\n"
                f"Surface JSON (not published):\n{surface.to_json()}"
            )

    return handler


# ---------------------------------------------------------------------------
# read_surface
# ---------------------------------------------------------------------------

_READ_SURFACE_DEFINITION: dict = {
    "name": "read_surface",
    "description": (
        "Read another mind's coordination surface from the Hub. "
        "Use this to discover a peer's team leads, capabilities, and "
        "fitness scores before sending a delegation request."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "civ_id": {
                "type": "string",
                "description": "The civ_id of the mind to read (e.g. 'witness')",
            },
            "thread_id": {
                "type": "string",
                "description": "Hub thread ID where the civ publishes its surface",
            },
        },
        "required": ["civ_id"],
    },
}


def _make_read_handler(
    suite_client,
    default_thread_id: str = "",
):
    """Return async read_surface handler."""

    async def handler(tool_input: dict) -> str:
        civ_id = tool_input.get("civ_id", "").strip()
        thread_id = tool_input.get("thread_id", "").strip() or default_thread_id

        if not civ_id:
            return "ERROR: civ_id is required"

        if not thread_id:
            return (
                f"ERROR: No thread_id provided and no default coordination "
                f"thread configured for reading surfaces."
            )

        try:
            posts = await suite_client.read_thread(thread_id, limit=20)
        except Exception as e:
            return f"ERROR reading Hub thread: {type(e).__name__}: {e}"

        # Find the most recent COORDINATION SURFACE post from this civ
        for post in reversed(posts):
            body = post.get("body", "")
            if "[COORDINATION SURFACE]" in body and f'"civ_id": "{civ_id}"' in body:
                # Extract JSON from markdown code block
                json_start = body.find("```json\n")
                json_end = body.find("\n```", json_start + 8) if json_start >= 0 else -1
                if json_start >= 0 and json_end >= 0:
                    json_str = body[json_start + 8:json_end]
                    try:
                        surface = CoordinationSurface.from_json(json_str)
                        verticals = ", ".join(
                            f"{tl.vertical}({tl.fitness_composite:.2f})"
                            for tl in surface.team_leads
                        )
                        return (
                            f"Surface for {civ_id}:\n"
                            f"  Mind: {surface.mind_id}\n"
                            f"  Verticals: {verticals or 'none'}\n"
                            f"  Priorities: {', '.join(surface.active_priorities) or 'none'}\n"
                            f"  Version: {surface.version}\n"
                            f"\nRaw JSON:\n{json_str}"
                        )
                    except (json.JSONDecodeError, KeyError) as e:
                        return f"ERROR parsing surface JSON: {e}"

        return f"No coordination surface found for '{civ_id}' in thread {thread_id[:8]}..."

    return handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_coordination_api_tools(
    registry: ToolRegistry,
    suite_client,
    mind_id: str,
    civ_id: str,
    coordination_thread_id: str = "",
) -> None:
    """
    Register publish_surface and read_surface tools.

    These are PRIMARY-level tools for inter-mind coordination.
    They require a SuiteClient for Hub access.
    """
    registry.register(
        "publish_surface",
        _PUBLISH_SURFACE_DEFINITION,
        _make_publish_handler(suite_client, mind_id, civ_id, coordination_thread_id),
        read_only=False,
    )
    registry.register(
        "read_surface",
        _READ_SURFACE_DEFINITION,
        _make_read_handler(suite_client, coordination_thread_id),
        read_only=True,
    )
