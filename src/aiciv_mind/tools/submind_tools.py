"""
aiciv_mind.tools.submind_tools — Sub-mind spawning and communication tools.

These tools give the primary mind the ability to:
  - spawn_submind: Spawn a sub-mind in a new tmux window
  - send_to_submind: Send a task to a running sub-mind and wait for its result

Registered only when both spawner and primary_bus are provided to ToolRegistry.default().
"""

from __future__ import annotations

import asyncio
import uuid

from aiciv_mind.ipc.messages import MindMessage, MsgType
from aiciv_mind.tools import ToolRegistry


# ---------------------------------------------------------------------------
# spawn_submind
# ---------------------------------------------------------------------------

_SPAWN_DEFINITION: dict = {
    "name": "spawn_submind",
    "description": (
        "Spawn a sub-mind in a new tmux window. The sub-mind will start "
        "running and can be communicated with via send_to_submind."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mind_id": {
                "type": "string",
                "description": "Unique identifier for the sub-mind",
            },
            "manifest_path": {
                "type": "string",
                "description": "Path to the sub-mind's manifest YAML file",
            },
        },
        "required": ["mind_id", "manifest_path"],
    },
}


def _make_spawn_handler(spawner):
    """Return an async spawn_submind handler closed over the given SubMindSpawner."""

    async def spawn_handler(tool_input: dict) -> str:
        mind_id: str = tool_input.get("mind_id", "").strip()
        manifest_path: str = tool_input.get("manifest_path", "").strip()

        if not mind_id:
            return "ERROR: No mind_id provided"
        if not manifest_path:
            return "ERROR: No manifest_path provided"

        try:
            handle = spawner.spawn(mind_id, manifest_path)
            # Wait briefly for ZMQ connection establishment
            await asyncio.sleep(1)
            return f"Spawned sub-mind '{mind_id}' (pane: {handle.pane_id})"
        except Exception as e:
            return f"ERROR: Failed to spawn sub-mind: {type(e).__name__}: {e}"

    return spawn_handler


# ---------------------------------------------------------------------------
# send_to_submind
# ---------------------------------------------------------------------------

_SEND_DEFINITION: dict = {
    "name": "send_to_submind",
    "description": (
        "Send a task to a running sub-mind and wait for its result."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mind_id": {
                "type": "string",
                "description": "The mind_id of the target sub-mind",
            },
            "task": {
                "type": "string",
                "description": "The task objective to send to the sub-mind",
            },
            "timeout": {
                "type": "integer",
                "description": "Seconds to wait for result",
                "default": 120,
            },
        },
        "required": ["mind_id", "task"],
    },
}


def _make_send_handler(bus, primary_mind_id: str):
    """Return an async send_to_submind handler closed over the PrimaryBus."""

    async def send_handler(tool_input: dict) -> str:
        mind_id: str = tool_input.get("mind_id", "").strip()
        task: str = tool_input.get("task", "").strip()
        timeout: int = tool_input.get("timeout", 120)

        if not mind_id:
            return "ERROR: No mind_id provided"
        if not task:
            return "ERROR: No task provided"

        task_id = f"task-{uuid.uuid4().hex[:8]}"

        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[str] = loop.create_future()

        async def on_result(msg: MindMessage) -> None:
            if msg.payload.get("task_id") == task_id:
                if not result_future.done():
                    result_future.set_result(msg.payload.get("result", ""))

        bus.on(MsgType.RESULT, on_result)

        try:
            msg = MindMessage.task(primary_mind_id, mind_id, task_id, task)
            await bus.send(msg)
            result = await asyncio.wait_for(result_future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return f"ERROR: Timeout waiting for {mind_id} (task: {task_id})"
        except Exception as e:
            return f"ERROR: send_to_submind failed: {type(e).__name__}: {e}"

    return send_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_submind_tools(
    registry: ToolRegistry,
    spawner,              # SubMindSpawner instance
    bus,                  # PrimaryBus instance
    primary_mind_id: str,  # e.g. "primary"
) -> None:
    """
    Register spawn_submind and send_to_submind tools.

    Both tools require a SubMindSpawner and PrimaryBus to function.
    """
    registry.register(
        "spawn_submind",
        _SPAWN_DEFINITION,
        _make_spawn_handler(spawner),
        read_only=False,
    )
    registry.register(
        "send_to_submind",
        _SEND_DEFINITION,
        _make_send_handler(bus, primary_mind_id),
        read_only=False,
    )
