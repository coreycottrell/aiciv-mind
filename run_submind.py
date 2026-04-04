#!/usr/bin/env python3
"""
aiciv-mind -- Sub-Mind Entry Point

Spawned by primary into a tmux pane. Two modes:

1. IPC mode (team leads): Connects to primary via ZeroMQ DEALER socket.
   Waits for task messages, executes them, reports results.
   Team leads also get a SubMindSpawner so they can spawn agents.

2. Task-file mode (agents): Reads task from --task-file, runs it directly,
   writes result to data/submind_results/, and exits. No IPC needed.

Usage (internal -- don't call directly):
    # Team lead (IPC mode):
    python3 run_submind.py --manifest manifests/team-leads/research-lead.yaml --id research-lead

    # Agent (task-file mode):
    python3 run_submind.py --manifest manifests/agents/coder.yaml --id coder-1 --task-file data/agent_tasks/agent-abc123.json
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

_MIND_ROOT = Path(__file__).parent
_RESULTS_DIR = _MIND_ROOT / "data" / "submind_results"


def setup_logging(mind_id: str, level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=f"%(asctime)s [{mind_id}] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


def _persist_result(
    task_id: str, mind_id: str, result: str, logger: logging.Logger,
    success: bool = True, error: str = "",
) -> None:
    """Write result to disk. Used by both IPC mode and task-file mode."""
    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (_RESULTS_DIR / f"{task_id}.json").write_text(json.dumps({
            "task_id": task_id,
            "mind_id": mind_id,
            "result": result,
            "success": success,
            "error": error,
            "timestamp": time.time(),
        }))
    except Exception as exc:
        logger.warning("Failed to persist result for %s: %s", task_id, exc)


def _load_common(manifest_path: str, mind_id: str, model_override: str | None):
    """Load manifest, memory, and suite client. Shared by both modes."""
    from aiciv_mind.manifest import MindManifest
    from aiciv_mind.memory import MemoryStore

    logger = logging.getLogger(mind_id)

    # Load manifest
    manifest = MindManifest.from_yaml(manifest_path)
    if mind_id and mind_id != manifest.mind_id:
        logger.info("Overriding mind_id: %s -> %s", manifest.mind_id, mind_id)
        manifest = manifest.model_copy(update={"mind_id": mind_id})

    if model_override:
        logger.info("Model override: %s -> %s", manifest.model.preferred, model_override)
        new_model = manifest.model.model_copy(update={"preferred": model_override})
        manifest = manifest.model_copy(update={"model": new_model})

    # Initialize memory (shared db)
    db_path = manifest.memory.db_path
    if db_path != ":memory:":
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    memory = MemoryStore(db_path)

    return manifest, memory, logger


async def _init_suite_client(manifest, logger):
    """Initialize SuiteClient if auth config is present."""
    suite_client = None
    try:
        auth_cfg = getattr(manifest, "auth", None)
        keypair_path = getattr(auth_cfg, "keypair_path", None) if auth_cfg else None
        if keypair_path and Path(keypair_path).exists():
            from aiciv_mind.suite.client import SuiteClient
            suite_client = await SuiteClient.connect(keypair_path, eager_auth=True)
            logger.info("SuiteClient connected — Hub tools enabled")
    except Exception as e:
        logger.info("SuiteClient unavailable: %s", e)
    return suite_client


def _build_tool_registry(manifest, memory, suite_client):
    """Build the base tool registry with all standard tools."""
    from aiciv_mind.tools import ToolRegistry

    scratchpad_dir = str(_MIND_ROOT / "scratchpads")
    queue_path = str(_MIND_ROOT / "data" / "hub_queue.jsonl")
    return ToolRegistry.default(
        memory_store=memory,
        role="agent",  # Register ALL tools; manifest tool list controls LLM visibility
        agent_id=manifest.mind_id,
        suite_client=suite_client,
        queue_path=queue_path,
        scratchpad_dir=scratchpad_dir,
    )


# ---------------------------------------------------------------------------
# Mode 1: Task-file mode (agents) — direct execution, no IPC
# ---------------------------------------------------------------------------

async def run_agent_task(manifest_path: str, mind_id: str, task_file: str,
                         model_override: str | None = None) -> None:
    """
    Agent task-file mode: read task from file, run it, write result, exit.
    No ZeroMQ bus needed. The team lead polls the result file.
    """
    from aiciv_mind.mind import Mind

    manifest, memory, logger = _load_common(manifest_path, mind_id, model_override)
    logger.info("Agent starting in task-file mode: %s", mind_id)

    # Read task from file
    task_path = Path(task_file)
    if not task_path.exists():
        logger.error("Task file not found: %s", task_file)
        return

    task_data = json.loads(task_path.read_text())
    task_id = task_data.get("task_id", f"unknown-{int(time.time())}")
    task = task_data.get("task", "")
    from_lead = task_data.get("from", "unknown")

    if not task:
        logger.error("Empty task in task file: %s", task_file)
        _persist_result(task_id, mind_id, "ERROR: Empty task", logger,
                        success=False, error="Empty task in task file")
        return

    logger.info("Task %s from %s: %s", task_id, from_lead, task[:100])

    # Initialize tools and mind (no bus needed)
    suite_client = await _init_suite_client(manifest, logger)
    tools = _build_tool_registry(manifest, memory, suite_client)
    mind = Mind(manifest=manifest, memory=memory, tools=tools, bus=None)

    # Execute the task
    try:
        result = await mind.run_task(task, task_id=task_id)
        logger.info("Task %s completed (%d chars)", task_id, len(result))
        _persist_result(task_id, mind_id, result, logger, success=True)
    except Exception as e:
        err_msg = str(e) or repr(e)
        logger.exception("Task %s failed: %s", task_id, err_msg)
        _persist_result(task_id, mind_id, f"ERROR: {err_msg}", logger,
                        success=False, error=err_msg)
    finally:
        memory.close()
        logger.info("Agent %s exiting", mind_id)


# ---------------------------------------------------------------------------
# Mode 2: IPC mode (team leads) — ZeroMQ bus, long-running
# ---------------------------------------------------------------------------

async def run_submind(manifest_path: str, mind_id: str,
                      model_override: str | None = None) -> None:
    """
    IPC mode for team leads: connect to primary's bus, wait for tasks.
    Team leads also get a SubMindSpawner so they can spawn agents.
    """
    from aiciv_mind.mind import Mind
    from aiciv_mind.ipc.submind_bus import SubMindBus
    from aiciv_mind.ipc.messages import MindMessage, MsgType
    from aiciv_mind.roles import Role

    manifest, memory, logger = _load_common(manifest_path, mind_id, model_override)
    logger.info("Sub-mind starting (IPC mode): %s", mind_id)

    suite_client = await _init_suite_client(manifest, logger)
    tools = _build_tool_registry(manifest, memory, suite_client)

    # --- Wire spawn_agent for team leads ---
    role = Role.from_str(manifest.role)
    if role == Role.TEAM_LEAD:
        logger.info("Team lead detected — wiring SubMindSpawner + spawn_agent")
        from aiciv_mind.spawner import SubMindSpawner
        from aiciv_mind.registry import MindRegistry
        from aiciv_mind.tools.spawn_tools import register_spawn_tools

        agent_registry = MindRegistry()
        spawner = SubMindSpawner(
            session_name="aiciv-subminds",
            mind_root=_MIND_ROOT,
            registry=agent_registry,
            memory_store=memory,
        )
        # Register spawn_agent + shutdown_agent on the tool registry.
        # bus=None because agents use file-based task passing, not IPC.
        register_spawn_tools(
            registry=tools,
            spawner=spawner,
            bus=None,
            mind_id=manifest.mind_id,
            role="team_lead",
        )
        logger.info("spawn_agent + shutdown_agent registered")

    # Connect IPC bus (for Primary ↔ team lead communication)
    bus = SubMindBus(mind_id=manifest.mind_id)
    bus.connect()

    # Create mind
    mind = Mind(manifest=manifest, memory=memory, tools=tools, bus=bus)
    shutdown_event = asyncio.Event()

    # IPC handlers
    async def on_task(msg: MindMessage) -> None:
        task_id = msg.payload.get("task_id", "unknown")
        objective = msg.payload.get("objective", "")

        logger.info("Received task %s: %s", task_id, objective[:100])

        # Send status: received
        await bus.send(MindMessage.status(
            sender=manifest.mind_id,
            recipient="primary",
            task_id=task_id,
            progress="Task received, starting...",
            pct=0,
        ))

        try:
            result = await mind.run_task(objective, task_id=task_id)
            # Persist result to file BEFORE ZMQ send so primary can
            # recover it if this process crashes before the send completes.
            _persist_result(task_id, manifest.mind_id, result, logger)
            await bus.send(MindMessage.result(
                sender=manifest.mind_id,
                recipient="primary",
                task_id=task_id,
                result=result,
                success=True,
            ))
        except Exception as e:
            # Use repr(e) as fallback — some exceptions (TimeoutError, etc.)
            # have str(e) == "" which makes diagnosis impossible.
            err_msg = str(e) or repr(e)
            logger.exception("Task %s failed: %s", task_id, err_msg)
            _persist_result(task_id, manifest.mind_id, f"ERROR: {err_msg}", logger,
                            success=False, error=err_msg)
            await bus.send(MindMessage.result(
                sender=manifest.mind_id,
                recipient="primary",
                task_id=task_id,
                result="",
                success=False,
                error=err_msg,
            ))

    async def on_heartbeat(msg: MindMessage) -> None:
        await bus.send(MindMessage.heartbeat_ack(
            sender=manifest.mind_id,
            recipient="primary",
        ))

    async def on_shutdown(msg: MindMessage) -> None:
        logger.info("Shutdown requested by primary")
        await bus.send(MindMessage.shutdown_ack(
            sender=manifest.mind_id,
            recipient="primary",
            mind_id=manifest.mind_id,
        ))
        shutdown_event.set()

    bus.on(MsgType.TASK, on_task)
    bus.on(MsgType.HEARTBEAT, on_heartbeat)
    bus.on(MsgType.SHUTDOWN, on_shutdown)

    recv_task = bus.start_recv()

    # Send READY signal to primary — confirms ZMQ connection is live
    # and this sub-mind is listening for TASK messages.
    await bus.send(MindMessage.ready(
        sender=manifest.mind_id,
        recipient="primary",
    ))

    logger.info("Sub-mind ready: %s (READY signal sent, waiting for tasks)", manifest.mind_id)
    print(f"[{manifest.mind_id}] ready", flush=True)

    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        bus.close()
        memory.close()
        logger.info("Sub-mind %s stopped", manifest.mind_id)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="aiciv-mind sub-mind process")
    parser.add_argument("--manifest", required=True, help="Path to mind manifest YAML")
    parser.add_argument("--id", required=True, dest="mind_id", help="Mind ID override")
    parser.add_argument("--model", default=None, help="Override manifest model.preferred")
    parser.add_argument("--task-file", default=None, dest="task_file",
                        help="Path to task JSON file (agent direct-execution mode)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(args.mind_id, args.log_level)

    if args.task_file:
        # Agent mode: run task directly, write result, exit
        asyncio.run(run_agent_task(
            args.manifest, args.mind_id, args.task_file,
            model_override=args.model,
        ))
    else:
        # IPC mode: connect to primary's bus, wait for tasks
        asyncio.run(run_submind(
            args.manifest, args.mind_id,
            model_override=args.model,
        ))


if __name__ == "__main__":
    main()
