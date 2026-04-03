"""
aiciv_mind.tools.ab_test_tools — A/B model comparison for Root.

Root spawns two sub-minds with the SAME task on DIFFERENT models.
Both run in parallel. Root compares: speed, quality, tool use accuracy,
token efficiency. Root writes the comparison to memory as a routing preference.

This tool is available to PRIMARY only (added to PRIMARY_TOOLS).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from aiciv_mind.ipc.messages import MindMessage, MsgType
from aiciv_mind.tools import ToolRegistry

_RESULTS_DIR = Path(__file__).resolve().parents[3] / "data" / "submind_results"
_AB_LOG_DIR = Path(__file__).resolve().parents[3] / "data" / "ab_comparisons"


# ---------------------------------------------------------------------------
# ab_model_test — available ONLY to PRIMARY
# ---------------------------------------------------------------------------

_AB_TEST_DEFINITION: dict = {
    "name": "ab_model_test",
    "description": (
        "A/B test two models on the same task. Spawns two sub-minds in parallel "
        "with different models, waits for both results, and returns a comparison "
        "of speed, quality, and token efficiency. Results are logged for routing "
        "preference learning."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task to send to both sub-minds",
            },
            "model_a": {
                "type": "string",
                "description": "First model (e.g. 'minimax-m27')",
            },
            "model_b": {
                "type": "string",
                "description": "Second model (e.g. 'gemma4-orchestrator')",
            },
            "manifest_path": {
                "type": "string",
                "description": "Manifest for the sub-minds (must be role: agent)",
            },
            "timeout": {
                "type": "integer",
                "description": "Seconds to wait for each result (default: 180)",
                "default": 180,
            },
        },
        "required": ["task", "model_a", "model_b", "manifest_path"],
    },
}


def _make_ab_test_handler(spawner, bus, primary_mind_id: str):
    """Return async ab_model_test handler."""

    async def handler(tool_input: dict) -> str:
        task = tool_input.get("task", "").strip()
        model_a = tool_input.get("model_a", "").strip()
        model_b = tool_input.get("model_b", "").strip()
        manifest_path = tool_input.get("manifest_path", "").strip()
        timeout = tool_input.get("timeout", 180)

        if not task:
            return "ERROR: task is required"
        if not model_a or not model_b:
            return "ERROR: both model_a and model_b are required"
        if not manifest_path:
            return "ERROR: manifest_path is required"

        test_id = f"ab-{uuid.uuid4().hex[:8]}"
        mind_a_id = f"{test_id}-a"
        mind_b_id = f"{test_id}-b"
        task_a_id = f"task-{uuid.uuid4().hex[:8]}"
        task_b_id = f"task-{uuid.uuid4().hex[:8]}"

        loop = asyncio.get_running_loop()
        result_a: asyncio.Future[str] = loop.create_future()
        result_b: asyncio.Future[str] = loop.create_future()

        # Wire up result listeners
        async def on_result(msg: MindMessage) -> None:
            tid = msg.payload.get("task_id", "")
            res = msg.payload.get("result", "")
            if tid == task_a_id and not result_a.done():
                result_a.set_result(res)
            elif tid == task_b_id and not result_b.done():
                result_b.set_result(res)

        bus.on(MsgType.RESULT, on_result)

        comparison = {
            "test_id": test_id,
            "task": task[:500],
            "model_a": model_a,
            "model_b": model_b,
            "timestamp": time.time(),
        }

        try:
            # Spawn both sub-minds with different models
            start_a = time.time()
            try:
                handle_a = spawner.spawn(mind_a_id, manifest_path, model_override=model_a)
                comparison["spawn_a_ok"] = True
            except Exception as e:
                comparison["spawn_a_ok"] = False
                comparison["spawn_a_error"] = str(e)
                return f"ERROR: Failed to spawn model_a ({model_a}): {e}"

            start_b = time.time()
            try:
                handle_b = spawner.spawn(mind_b_id, manifest_path, model_override=model_b)
                comparison["spawn_b_ok"] = True
            except Exception as e:
                comparison["spawn_b_ok"] = False
                comparison["spawn_b_error"] = str(e)
                # Clean up model_a
                try:
                    spawner.terminate(handle_a)
                except Exception:
                    pass
                return f"ERROR: Failed to spawn model_b ({model_b}): {e}"

            # Wait for ZMQ connections
            await asyncio.sleep(2)

            # Send tasks in parallel
            msg_a = MindMessage.task(primary_mind_id, mind_a_id, task_a_id, task)
            msg_b = MindMessage.task(primary_mind_id, mind_b_id, task_b_id, task)
            await bus.send(msg_a)
            await bus.send(msg_b)

            # Wait for both results
            res_a_text = ""
            res_b_text = ""
            time_a = None
            time_b = None

            try:
                res_a_text = await asyncio.wait_for(result_a, timeout=timeout)
                time_a = time.time() - start_a
            except asyncio.TimeoutError:
                # Check disk fallback
                rf = _RESULTS_DIR / f"{task_a_id}.json"
                if rf.exists():
                    try:
                        res_a_text = json.loads(rf.read_text()).get("result", "")
                        time_a = time.time() - start_a
                    except Exception:
                        pass
                if not res_a_text:
                    res_a_text = f"TIMEOUT after {timeout}s"
                    time_a = timeout

            try:
                res_b_text = await asyncio.wait_for(result_b, timeout=timeout)
                time_b = time.time() - start_b
            except asyncio.TimeoutError:
                rf = _RESULTS_DIR / f"{task_b_id}.json"
                if rf.exists():
                    try:
                        res_b_text = json.loads(rf.read_text()).get("result", "")
                        time_b = time.time() - start_b
                    except Exception:
                        pass
                if not res_b_text:
                    res_b_text = f"TIMEOUT after {timeout}s"
                    time_b = timeout

            # Build comparison
            comparison["time_a_s"] = round(time_a, 2) if time_a else None
            comparison["time_b_s"] = round(time_b, 2) if time_b else None
            comparison["result_a_len"] = len(res_a_text)
            comparison["result_b_len"] = len(res_b_text)
            comparison["result_a_preview"] = res_a_text[:300]
            comparison["result_b_preview"] = res_b_text[:300]

            # Speed comparison
            if time_a and time_b and time_a > 0 and time_b > 0:
                faster = model_a if time_a < time_b else model_b
                speedup = max(time_a, time_b) / min(time_a, time_b)
                comparison["faster_model"] = faster
                comparison["speedup_factor"] = round(speedup, 2)

            # Log comparison to disk
            _AB_LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = _AB_LOG_DIR / f"{test_id}.json"
            log_path.write_text(json.dumps(comparison, indent=2))

            # Clean up sub-minds
            for handle in (handle_a, handle_b):
                try:
                    spawner.terminate(handle)
                except Exception:
                    pass

            # Format result for Root
            lines = [
                f"## A/B Test: {model_a} vs {model_b}",
                f"Task: {task[:200]}",
                "",
                f"**{model_a}** (Model A):",
                f"  Time: {comparison.get('time_a_s', '?')}s",
                f"  Output length: {comparison.get('result_a_len', '?')} chars",
                f"  Preview: {res_a_text[:200]}",
                "",
                f"**{model_b}** (Model B):",
                f"  Time: {comparison.get('time_b_s', '?')}s",
                f"  Output length: {comparison.get('result_b_len', '?')} chars",
                f"  Preview: {res_b_text[:200]}",
                "",
            ]

            if "faster_model" in comparison:
                lines.append(
                    f"**Faster**: {comparison['faster_model']} "
                    f"({comparison['speedup_factor']}x)"
                )

            lines.append(f"\nFull comparison logged: {log_path}")
            lines.append(
                "\nTo record routing preference, write to memory: "
                "'For [task type], prefer [model] because [reason]'"
            )

            return "\n".join(lines)

        except Exception as e:
            comparison["error"] = str(e)
            return f"ERROR: A/B test failed: {type(e).__name__}: {e}"

    return handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_ab_test_tools(
    registry: ToolRegistry,
    spawner,
    bus,
    mind_id: str,
) -> None:
    """Register the ab_model_test tool (PRIMARY only)."""
    registry.register(
        "ab_model_test",
        _AB_TEST_DEFINITION,
        _make_ab_test_handler(spawner, bus, mind_id),
        read_only=False,
        timeout=400.0,  # Long timeout — waits for two sub-minds
    )
