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
import json
import time
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
            "model": {
                "type": "string",
                "description": "Override the manifest's model (e.g. 'gemma4-orchestrator' for A/B testing)",
            },
        },
        "required": ["mind_id", "manifest_path", "vertical"],
    },
}


def _make_spawn_tl_handler(spawner, bus, primary_mind_id: str, scratchpad_dir: str | None = None):
    """Return async spawn_team_lead handler."""

    async def handler(tool_input: dict) -> str:
        mind_id = tool_input.get("mind_id", "").strip()
        manifest_path = tool_input.get("manifest_path", "").strip()
        vertical = tool_input.get("vertical", "").strip()
        objective = tool_input.get("objective", "").strip()
        model_override = tool_input.get("model", "").strip() or None

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
            handle = spawner.spawn(mind_id, manifest_path, model_override=model_override)
            await asyncio.sleep(1)  # Wait for ZMQ connection

            context_parts = [f"Spawned team lead '{mind_id}' for vertical '{vertical}'"]
            context_parts.append(f"Pane: {handle.pane_id}")
            if model_override:
                context_parts.append(f"Model override: {model_override}")

            team_scratchpad = ""
            coord_scratchpad = ""
            if scratchpad_dir:
                team_scratchpad = str(Path(scratchpad_dir) / "teams" / f"{vertical}-team.md")
                coord_scratchpad = str(Path(scratchpad_dir) / "coordination.md")
                context_parts.append(f"Team scratchpad: {team_scratchpad}")
                context_parts.append(f"Coordination scratchpad: {coord_scratchpad}")

            if objective:
                context_parts.append(f"Objective: {objective}")

            # Send the objective as a TASK to the team lead.
            # The sub-mind's on_task handler in run_submind.py will receive this
            # and execute it via mind.run_task().  Results come back as RESULT
            # messages on the PrimaryBus.
            if bus is not None and objective:
                task_parts = [
                    f"You are team lead for vertical '{vertical}'.",
                ]
                if team_scratchpad:
                    task_parts.append(f"Team scratchpad: {team_scratchpad}")
                if coord_scratchpad:
                    task_parts.append(f"Coordination scratchpad: {coord_scratchpad}")
                task_parts.append(f"\nObjective: {objective}")

                task_id = f"tl-{uuid.uuid4().hex[:8]}"
                try:
                    task_msg = MindMessage.task(
                        sender=primary_mind_id,
                        recipient=mind_id,
                        task_id=task_id,
                        objective="\n".join(task_parts),
                    )
                    await asyncio.sleep(1)  # Extra wait for sub-mind to finish init
                    await bus.send(task_msg)
                    context_parts.append(f"Task sent: {task_id}")
                except Exception as exc:
                    context_parts.append(f"Warning: failed to send task: {exc}")

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
        "Spawn a specialist agent sub-mind to execute a task. The agent gets "
        "full tool access (65+ tools). It runs the task, returns results, and "
        "exits. This call BLOCKS until the agent completes or times out."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mind_id": {
                "type": "string",
                "description": "Unique ID for the agent (e.g. 'coder-1', 'researcher-1')",
            },
            "manifest_path": {
                "type": "string",
                "description": "Path to the agent's manifest YAML (e.g. 'manifests/agents/coder.yaml')",
            },
            "task": {
                "type": "string",
                "description": "The specific task for this agent to execute",
            },
        },
        "required": ["mind_id", "manifest_path", "task"],
    },
}

# Directories for task files and results (relative to mind_root)
_AGENT_TASKS_DIR = "data/agent_tasks"
_AGENT_RESULTS_DIR = "data/submind_results"
_AGENT_TIMEOUT_SECONDS = 180  # 3 minutes max per agent task


def _make_spawn_agent_handler(spawner, bus=None, team_lead_mind_id: str = ""):
    """
    Return async spawn_agent handler.

    Architecture: file-based task passing (no IPC needed between team lead and agent).
    1. Write task to data/agent_tasks/{task_id}.json
    2. Spawn agent with --task-file flag pointing to the task file
    3. Agent reads task, runs mind.run_task(), writes result to data/submind_results/{task_id}.json
    4. Team lead polls for result file, returns result when found
    """

    async def handler(tool_input: dict) -> str:
        mind_id = tool_input.get("mind_id", "").strip()
        manifest_path = tool_input.get("manifest_path", "").strip()
        task = tool_input.get("task", "").strip()

        if not mind_id:
            return "ERROR: mind_id is required"
        if not manifest_path:
            return "ERROR: manifest_path is required"
        if not task:
            return "ERROR: task is required — agents need a specific task to execute"

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

        # Generate task_id and write task file
        task_id = f"agent-{uuid.uuid4().hex[:8]}"
        mind_root = spawner._mind_root
        task_dir = mind_root / _AGENT_TASKS_DIR
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / f"{task_id}.json"
        task_file.write_text(json.dumps({
            "task_id": task_id,
            "task": task,
            "from": team_lead_mind_id,
            "mind_id": mind_id,
            "timestamp": time.time(),
        }))

        try:
            # Spawn agent with --task-file flag (runs task directly, no IPC needed)
            handle = spawner.spawn(
                mind_id,
                manifest_path,
                extra_args=["--task-file", str(task_file)],
            )

            parts = [
                f"Spawned agent '{mind_id}' (pane: {handle.pane_id})",
                f"Task ID: {task_id}",
                f"Task: {task[:200]}",
                "Waiting for agent to complete...",
            ]

            # Poll for result file
            result_file = mind_root / _AGENT_RESULTS_DIR / f"{task_id}.json"
            start = time.time()
            while time.time() - start < _AGENT_TIMEOUT_SECONDS:
                if result_file.exists():
                    try:
                        result_data = json.loads(result_file.read_text())
                        result_text = result_data.get("result", "No result text")
                        success = result_data.get("success", True)
                        elapsed = round(time.time() - start, 1)
                        if success:
                            return (
                                f"Agent '{mind_id}' completed task ({elapsed}s):\n\n"
                                f"{result_text}"
                            )
                        else:
                            error = result_data.get("error", "Unknown error")
                            return (
                                f"Agent '{mind_id}' FAILED ({elapsed}s):\n"
                                f"Error: {error}\n"
                                f"Partial result: {result_text}"
                            )
                    except json.JSONDecodeError:
                        pass  # File still being written, retry
                await asyncio.sleep(2)

            # Timeout — try to capture last output from pane
            elapsed = round(time.time() - start, 1)
            try:
                last_output = spawner.capture_output(handle, lines=20)
                output_text = "\n".join(last_output[-10:]) if last_output else "(no output captured)"
            except Exception:
                output_text = "(could not capture pane output)"

            return (
                f"Agent '{mind_id}' TIMED OUT after {elapsed}s.\n"
                f"Last pane output:\n{output_text}"
            )

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


def _make_shutdown_agent_handler(spawner, team_lead_mind_id: str):
    """Return async shutdown_agent handler. Uses spawner.terminate() since agents
    use file-based task passing (no IPC bus)."""

    async def handler(tool_input: dict) -> str:
        mind_id = tool_input.get("mind_id", "").strip()
        if not mind_id:
            return "ERROR: mind_id is required"

        try:
            # Look up handle in spawner's registry
            if spawner._registry is not None:
                handle = spawner._registry.get(mind_id)
                if handle is not None:
                    spawner.terminate(handle)
                    return f"Agent '{mind_id}' terminated"
            # Fallback: kill tmux window by name
            session = spawner.ensure_session()
            window = session.windows.get(window_name=mind_id, default=None)
            if window is not None:
                window.kill()
                return f"Agent '{mind_id}' terminated (via tmux window kill)"
            return f"Agent '{mind_id}' not found — may have already exited"
        except Exception as e:
            return f"ERROR: Failed to terminate '{mind_id}': {type(e).__name__}: {e}"

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
            _make_spawn_tl_handler(spawner, bus, mind_id, scratchpad_dir),
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
            _make_spawn_agent_handler(spawner, bus, mind_id),
            read_only=False,
            timeout=_AGENT_TIMEOUT_SECONDS + 10,  # Tool timeout > poll timeout
        )
        registry.register(
            "shutdown_agent",
            _SHUTDOWN_AGENT_DEFINITION,
            _make_shutdown_agent_handler(spawner, mind_id),
            read_only=False,
        )
    # AGENT role: register nothing — agents cannot spawn
