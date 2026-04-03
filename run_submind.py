#!/usr/bin/env python3
"""
aiciv-mind -- Sub-Mind Entry Point

Spawned by primary into a tmux pane. Connects to primary via ZeroMQ DEALER socket.
Waits for task messages, executes them, reports results.

Usage (internal -- don't call directly):
    python3 run_submind.py --manifest manifests/research-lead.yaml --id research-lead
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


def setup_logging(mind_id: str, level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=f"%(asctime)s [{mind_id}] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


_RESULTS_DIR = Path(__file__).parent / "data" / "submind_results"


def _persist_result(task_id: str, mind_id: str, result: str, logger: logging.Logger) -> None:
    """Write result to disk so primary can recover it on ZMQ timeout."""
    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (_RESULTS_DIR / f"{task_id}.json").write_text(json.dumps({
            "task_id": task_id, "mind_id": mind_id,
            "result": result, "timestamp": time.time(),
        }))
    except Exception as exc:
        logger.warning("Failed to persist result for %s: %s", task_id, exc)


async def run_submind(manifest_path: str, mind_id: str) -> None:
    from aiciv_mind.manifest import MindManifest
    from aiciv_mind.memory import MemoryStore
    from aiciv_mind.tools import ToolRegistry
    from aiciv_mind.mind import Mind
    from aiciv_mind.ipc.submind_bus import SubMindBus
    from aiciv_mind.ipc.messages import MindMessage, MsgType

    logger = logging.getLogger(mind_id)
    logger.info("Sub-mind starting: %s", mind_id)

    # Load manifest
    manifest = MindManifest.from_yaml(manifest_path)
    # Override mind_id if provided via CLI
    if mind_id and mind_id != manifest.mind_id:
        logger.info("Overriding mind_id: %s -> %s", manifest.mind_id, mind_id)
        manifest = manifest.model_copy(update={"mind_id": mind_id})

    # Initialize memory (shared db)
    db_path = manifest.memory.db_path
    if db_path != ":memory:":
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    memory = MemoryStore(db_path)

    # Build tool registry with role from manifest.
    # Team leads get spawn_agent; agents get full tools; primary gets spawn_team_lead.
    # The role also drives filter_by_role() in Mind.__init__ (defense-in-depth).
    role_str = manifest.role.replace("-", "_") if manifest.role else "agent"
    tools = ToolRegistry.default(memory_store=memory, role=role_str, agent_id=manifest.mind_id)

    # Connect IPC bus
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
            logger.exception("Task %s failed", task_id)
            _persist_result(task_id, manifest.mind_id, f"ERROR: {e}", logger)
            await bus.send(MindMessage.result(
                sender=manifest.mind_id,
                recipient="primary",
                task_id=task_id,
                result="",
                success=False,
                error=str(e),
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

    logger.info("Sub-mind ready: %s (waiting for tasks)", manifest.mind_id)
    print(f"[{manifest.mind_id}] ready", flush=True)

    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        bus.close()
        memory.close()
        logger.info("Sub-mind %s stopped", manifest.mind_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="aiciv-mind sub-mind process")
    parser.add_argument("--manifest", required=True, help="Path to mind manifest YAML")
    parser.add_argument("--id", required=True, dest="mind_id", help="Mind ID override")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(args.mind_id, args.log_level)
    asyncio.run(run_submind(args.manifest, args.mind_id))


if __name__ == "__main__":
    main()
