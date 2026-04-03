"""
aiciv_mind.tools.spawn_tools — Role-enforced spawn and shutdown tools.

Structural enforcement of the fractal coordination pattern:
  - PRIMARY gets spawn_team_lead() + shutdown_team_lead()
  - TEAM_LEAD gets spawn_agent() + shutdown_agent()
  - AGENT gets neither (cannot spawn)

These wrap the generic SubMindSpawner but enforce role constraints:
  - spawn_team_lead auto-injects team scratchpad + coordination scratchpad
  - spawn_agent auto-injects team scratchpad (write access)
  - Both enforce the correct Role on the spawned sub-mind's tool registry

The LLM never sees the "wrong" spawn tool because role-based filtering
removes it before tool definitions reach the model.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from aiciv_mind.ipc.messages import MindMessage, MsgType
from aiciv_mind.tools import ToolRegistry


# ---------------------------------------------------------------------------
# spawn_team_lead — available ONLY to PRIMARY
# ---------------------------------------------------------------------------

_SPAWN_TL_DEFINITION: dict = {
    "name": "spawn_team_lead",
    "description": (
        "Spawn a team lead sub-mind for a specific vertical. The team lead "
        "gets coordination scratchpad access (read/write) and team scratchpad "
        "access. It can spawn agents but CANNOT execute tools directly."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mind_id": {
                "type": "string",
                "description": "Unique ID for the team lead (e.g. 'research-lead')",
            },
            "manifest_path": {
                "type": "string",
                "description": "Path to the team lead's manifest YAML",
            },
            "vertical": {
                "type": "string",
                "description": "Vertical name (e.g. 'research', 'code', 'comms')",
            },
            "objective": {
                "type": "string",
                "description": "The objective for this team lead session",
            },
        },
        "required": ["mind_id", "manifest_path", "vertical"],
    },
}


def _make_spawn_tl_handler(spawner, scratchpad_dir: str | None = None):
    """Return async spawn_team_lead handler."""

    async def handler(tool_input: dict) -> str:
        mind_id = tool_input.get("mind_id", "").strip()
        manifest_path = tool_input.get("manifest_path", "").strip()
        vertical = tool_input.get("vertical", "").strip()
        objective = tool_input.get("objective", "").strip()

        if not mind_id:
            return "ERROR: mind_id is required"
        if not manifest_path:
            return "ERROR: manifest_path is required"
        if not vertical:
            return "ERROR: vertical is required"

        # Verify the manifest declares role: team_lead
        try:
            from aiciv_mind.manifest import MindManifest
            manifest = MindManifest.from_yaml(manifest_path)
            if manifest.role not in ("team_lead", "team-lead"):
                return (
                    f"ERROR: Manifest for '{mind_id}' declares role '{manifest.role}' "
                    f"but spawn_team_lead requires role 'team_lead'"
                )
        except Exception as e:
            return f"ERROR: Could not validate manifest: {type(e).__name__}: {e}"

        # Ensure team scratchpad dir exists
        if scratchpad_dir:
            teams_dir = Path(scratchpad_dir) / "teams"
            teams_dir.mkdir(parents=True, exist_ok=True)

        try:
            handle = spawner.spawn(mind_id, manifest_path)
            await asyncio.sleep(1)  # Wait for ZMQ connection

            context_parts = [f"Spawned team lead '{mind_id}' for vertical '{vertical}'"]
            context_parts.append(f"Pane: {handle.pane_id}")

            if scratchpad_dir:
                team_scratchpad = str(Path(scratchpad_dir) / "teams" / f"{vertical}-team.md")
                coord_scratchpad = str(Path(scratchpad_dir) / "coordination.md")
                context_parts.append(f"Team scratchpad: {team_scratchpad}")
                context_parts.append(f"Coordination scratchpad: {coord_scratchpad}")

            if objective:
                context_parts.append(f"Objective: {objective}")

            return "\n".join(context_parts)

        except Exception as e:
            return f"ERROR: Failed to spawn team lead: {type(e).__name__}: {e}"

    return handler


# ---------------------------------------------------------------------------
# shutdown_team_lead — available ONLY to PRIMARY
# ---------------------------------------------------------------------------

_SHUTDOWN_TL_DEFINITION: dict = {
    "name": "shutdown_team_lead",
    "description": (
        "Request graceful shutdown of a team lead sub-mind. "
        "The team lead should write final scratchpad entries before exiting."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mind_id": {
                "type": "string",
                "description": "The mind_id of the team lead to shut down",
            },
        },
        "required": ["mind_id"],
    },
}


def _make_shutdown_tl_handler(bus, primary_mind_id: str):
    """Return async shutdown_team_lead handler."""

    async def handler(tool_input: dict) -> str:
        mind_id = tool_input.get("mind_id", "").strip()
        if not mind_id:
            return "ERROR: mind_id is required"

        try:
            msg = MindMessage.shutdown(primary_mind_id, mind_id)
            await bus.send(msg)
            return f"Shutdown request sent to team lead '{mind_id}'"
        except Exception as e:
            return f"ERROR: Failed to send shutdown to '{mind_id}': {type(e).__name__}: {e}"

    return handler


# ---------------------------------------------------------------------------
# spawn_agent — available ONLY to TEAM_LEAD
# ---------------------------------------------------------------------------

_SPAWN_AGENT_DEFINITION: dict = {
    "name": "spawn_agent",
    "description": (
        "Spawn a specialist agent sub-mind. The agent gets full tool access "
        "and team scratchpad write access. It executes tools directly."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mind_id": {
                "type": "string",
                "description": "Unique ID for the agent (e.g. 'coder-1', 'web-searcher')",
            },
            "manifest_path": {
                "type": "string",
                "description": "Path to the agent's manifest YAML",
            },
            "task": {
                "type": "string",
                "description": "The specific task for this agent",
            },
        },
        "required": ["mind_id", "manifest_path"],
    },
}


def _make_spawn_agent_handler(spawner):
    """Return async spawn_agent handler."""

    async def handler(tool_input: dict) -> str:
        mind_id = tool_input.get("mind_id", "").strip()
        manifest_path = tool_input.get("manifest_path", "").strip()
        task = tool_input.get("task", "").strip()

        if not mind_id:
            return "ERROR: mind_id is required"
        if not manifest_path:
            return "ERROR: manifest_path is required"

        # Verify the manifest declares role: agent
        try:
            from aiciv_mind.manifest import MindManifest
            manifest = MindManifest.from_yaml(manifest_path)
            if manifest.role != "agent":
                return (
                    f"ERROR: Manifest for '{mind_id}' declares role '{manifest.role}' "
                    f"but spawn_agent requires role 'agent'"
                )
        except Exception as e:
            return f"ERROR: Could not validate manifest: {type(e).__name__}: {e}"

        try:
            handle = spawner.spawn(mind_id, manifest_path)
            await asyncio.sleep(1)

            parts = [f"Spawned agent '{mind_id}' (pane: {handle.pane_id})"]
            if task:
                parts.append(f"Task: {task}")

            return "\n".join(parts)

        except Exception as e:
            return f"ERROR: Failed to spawn agent: {type(e).__name__}: {e}"

    return handler


# ---------------------------------------------------------------------------
# shutdown_agent — available ONLY to TEAM_LEAD
# ---------------------------------------------------------------------------

_SHUTDOWN_AGENT_DEFINITION: dict = {
    "name": "shutdown_agent",
    "description": (
        "Request graceful shutdown of an agent sub-mind."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mind_id": {
                "type": "string",
                "description": "The mind_id of the agent to shut down",
            },
        },
        "required": ["mind_id"],
    },
}


def _make_shutdown_agent_handler(bus, team_lead_mind_id: str):
    """Return async shutdown_agent handler."""

    async def handler(tool_input: dict) -> str:
        mind_id = tool_input.get("mind_id", "").strip()
        if not mind_id:
            return "ERROR: mind_id is required"

        try:
            msg = MindMessage.shutdown(team_lead_mind_id, mind_id)
            await bus.send(msg)
            return f"Shutdown request sent to agent '{mind_id}'"
        except Exception as e:
            return f"ERROR: Failed to send shutdown to '{mind_id}': {type(e).__name__}: {e}"

    return handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_spawn_tools(
    registry: ToolRegistry,
    spawner,
    bus,
    mind_id: str,
    role: str = "primary",
    scratchpad_dir: str | None = None,
) -> None:
    """
    Register role-appropriate spawn and shutdown tools.

    PRIMARY gets: spawn_team_lead, shutdown_team_lead
    TEAM_LEAD gets: spawn_agent, shutdown_agent
    AGENT gets: nothing (agents don't spawn)

    Note: Role-based filtering also applies via ToolRegistry.filter_by_role(),
    but registering only the correct tools per role provides defense-in-depth.
    """
    if role in ("primary",):
        registry.register(
            "spawn_team_lead",
            _SPAWN_TL_DEFINITION,
            _make_spawn_tl_handler(spawner, scratchpad_dir),
            read_only=False,
            timeout=30.0,
        )
        registry.register(
            "shutdown_team_lead",
            _SHUTDOWN_TL_DEFINITION,
            _make_shutdown_tl_handler(bus, mind_id),
            read_only=False,
        )

    elif role in ("team_lead", "team-lead"):
        registry.register(
            "spawn_agent",
            _SPAWN_AGENT_DEFINITION,
            _make_spawn_agent_handler(spawner),
            read_only=False,
            timeout=30.0,
        )
        registry.register(
            "shutdown_agent",
            _SHUTDOWN_AGENT_DEFINITION,
            _make_shutdown_agent_handler(bus, mind_id),
            read_only=False,
        )
    # AGENT role: register nothing — agents cannot spawn
