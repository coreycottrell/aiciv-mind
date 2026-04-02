"""
aiciv_mind.tools.resource_tools — Resource tracking and usage analytics.

Provides three tools for Root to monitor resource consumption:
  - resource_usage: RAM, CPU, process count, disk for aiciv-mind processes
  - token_stats: reads token_usage.jsonl, returns summary (total tokens, cost, avg latency)
  - session_stats: session count, avg duration, tool call frequency

Uses psutil for system metrics when available, falls back to /proc on Linux.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions (Anthropic API format)
# ---------------------------------------------------------------------------

_RESOURCE_USAGE_DEFINITION: dict = {
    "name": "resource_usage",
    "description": (
        "Get real-time resource usage for aiciv-mind processes: RAM (RSS + VMS), "
        "CPU percentage, process count, disk usage for the data/ directory. "
        "Use this to monitor system health and detect resource leaks."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verbose": {
                "type": "boolean",
                "description": "Include per-process breakdown (default: false)",
            },
        },
    },
}

_TOKEN_STATS_DEFINITION: dict = {
    "name": "token_stats",
    "description": (
        "Read token_usage.jsonl and return a summary: total tokens today/all-time, "
        "total cost, average latency, per-model breakdown. Use this to understand "
        "how much compute is being consumed and optimize model routing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "enum": ["today", "last_hour", "last_24h", "all"],
                "description": "Time period to summarize (default: today)",
            },
            "by_model": {
                "type": "boolean",
                "description": "Break down stats per model (default: true)",
            },
        },
    },
}

_SESSION_STATS_DEFINITION: dict = {
    "name": "session_stats",
    "description": (
        "Read session JSONL logs and return: session count, average turns per session, "
        "tool call frequency, most-used tools. Use this to understand usage patterns "
        "and identify optimization opportunities."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Specific session to inspect. If omitted, returns aggregate stats.",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _make_resource_usage_handler(mind_root: str):
    """Return a resource_usage handler."""

    def resource_usage_handler(tool_input: dict) -> str:
        verbose = tool_input.get("verbose", False)
        parts: list[str] = ["## Resource Usage Report"]

        try:
            import psutil
            _has_psutil = True
        except ImportError:
            _has_psutil = False

        # Find aiciv-mind related processes
        mind_procs = []
        total_rss_mb = 0.0
        total_vms_mb = 0.0
        total_cpu = 0.0

        if _has_psutil:
            for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "cpu_percent"]):
                try:
                    cmdline = " ".join(proc.info.get("cmdline") or [])
                    if any(kw in cmdline.lower() for kw in [
                        "aiciv", "groupchat", "dream_cycle", "litellm",
                        "run_submind", "agentmail",
                    ]):
                        mem = proc.info.get("memory_info")
                        rss_mb = mem.rss / (1024 * 1024) if mem else 0
                        vms_mb = mem.vms / (1024 * 1024) if mem else 0
                        cpu = proc.info.get("cpu_percent", 0) or 0
                        total_rss_mb += rss_mb
                        total_vms_mb += vms_mb
                        total_cpu += cpu
                        mind_procs.append({
                            "pid": proc.info["pid"],
                            "name": proc.info.get("name", "unknown"),
                            "rss_mb": round(rss_mb, 1),
                            "vms_mb": round(vms_mb, 1),
                            "cpu_pct": round(cpu, 1),
                            "cmd": cmdline[:120],
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            parts.append(f"**Process count**: {len(mind_procs)}")
            parts.append(f"**Total RSS**: {total_rss_mb:.1f} MB")
            parts.append(f"**Total VMS**: {total_vms_mb:.1f} MB")
            parts.append(f"**Total CPU**: {total_cpu:.1f}%")

            # System-wide stats
            vm = psutil.virtual_memory()
            parts.append(f"**System RAM**: {vm.used / (1024**3):.1f} / {vm.total / (1024**3):.1f} GB ({vm.percent}%)")
            parts.append(f"**System CPU**: {psutil.cpu_percent(interval=0.1):.1f}% ({psutil.cpu_count()} cores)")
        else:
            # Fallback: use ps
            try:
                ps_out = subprocess.run(
                    ["ps", "aux"], capture_output=True, text=True, timeout=5,
                ).stdout
                for line in ps_out.splitlines():
                    if any(kw in line.lower() for kw in [
                        "aiciv", "groupchat", "dream_cycle", "litellm",
                        "run_submind", "agentmail",
                    ]):
                        fields = line.split(None, 10)
                        if len(fields) >= 11:
                            mind_procs.append({
                                "pid": fields[1],
                                "cpu_pct": fields[2],
                                "mem_pct": fields[3],
                                "rss_kb": fields[5],
                                "cmd": fields[10][:120],
                            })
                parts.append(f"**Process count**: {len(mind_procs)} (psutil not installed, limited stats)")
            except Exception as e:
                parts.append(f"**Processes**: ERROR — {e}")

        # Disk usage for data/
        data_dir = Path(mind_root) / "data"
        if data_dir.exists():
            total_size = sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file())
            parts.append(f"**Data dir size**: {total_size / (1024 * 1024):.2f} MB")

            # Token log size
            token_log = data_dir / "token_usage.jsonl"
            if token_log.exists():
                parts.append(f"**token_usage.jsonl**: {token_log.stat().st_size / 1024:.1f} KB")

            # Session logs
            session_dir = data_dir / "sessions"
            if session_dir.exists():
                session_files = list(session_dir.glob("*.jsonl"))
                parts.append(f"**Session logs**: {len(session_files)} file(s)")

        if verbose and mind_procs:
            parts.append("\n### Per-Process Breakdown")
            for p in mind_procs:
                pid = p.get("pid", "?")
                cmd = p.get("cmd", "?")
                rss = p.get("rss_mb", p.get("rss_kb", "?"))
                cpu = p.get("cpu_pct", "?")
                parts.append(f"  - PID {pid}: RSS={rss} CPU={cpu}% — {cmd}")

        return "\n".join(parts)

    return resource_usage_handler


def _make_token_stats_handler(token_log_path: str):
    """Return a token_stats handler that reads from the JSONL log."""

    def token_stats_handler(tool_input: dict) -> str:
        period = tool_input.get("period", "today")
        by_model = tool_input.get("by_model", True)

        log_path = Path(token_log_path)
        if not log_path.exists():
            return "No token usage data found. token_usage.jsonl does not exist yet."

        # Determine time filter
        now = datetime.now()
        if period == "today":
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "last_hour":
            cutoff = now - timedelta(hours=1)
        elif period == "last_24h":
            cutoff = now - timedelta(hours=24)
        else:  # "all"
            cutoff = datetime.min

        # Parse JSONL
        records: list[dict] = []
        try:
            with open(log_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        ts_str = record.get("timestamp", "")
                        # Parse timestamp — handle both with and without timezone
                        try:
                            ts = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
                        except ValueError:
                            ts = datetime.min
                        if ts >= cutoff:
                            records.append(record)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            return f"ERROR reading token_usage.jsonl: {e}"

        if not records:
            return f"No token usage records found for period '{period}'."

        # Aggregate
        total_input = sum(r.get("input_tokens", 0) for r in records)
        total_output = sum(r.get("output_tokens", 0) for r in records)
        total_thinking = sum(r.get("thinking_tokens", 0) for r in records)
        total_cost = sum(r.get("estimated_cost_usd", 0) for r in records)
        latencies = [r.get("latency_ms", 0) for r in records if r.get("latency_ms", 0) > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        parts: list[str] = [
            f"## Token Stats ({period})",
            f"**API calls**: {len(records)}",
            f"**Total input tokens**: {total_input:,}",
            f"**Total output tokens**: {total_output:,}",
            f"**Total thinking tokens**: {total_thinking:,}",
            f"**Total tokens**: {total_input + total_output + total_thinking:,}",
            f"**Estimated cost**: ${total_cost:.4f}",
            f"**Avg latency**: {avg_latency:.0f}ms",
        ]

        if latencies:
            p50 = sorted(latencies)[len(latencies) // 2]
            p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else p50
            parts.append(f"**P50 latency**: {p50}ms | **P95**: {p95}ms")

        if by_model:
            # Per-model breakdown
            model_stats: dict[str, dict] = {}
            for r in records:
                model = r.get("model", "unknown")
                if model not in model_stats:
                    model_stats[model] = {
                        "calls": 0, "input": 0, "output": 0,
                        "thinking": 0, "cost": 0.0, "latencies": [],
                    }
                ms = model_stats[model]
                ms["calls"] += 1
                ms["input"] += r.get("input_tokens", 0)
                ms["output"] += r.get("output_tokens", 0)
                ms["thinking"] += r.get("thinking_tokens", 0)
                ms["cost"] += r.get("estimated_cost_usd", 0)
                lat = r.get("latency_ms", 0)
                if lat > 0:
                    ms["latencies"].append(lat)

            parts.append("\n### Per-Model Breakdown")
            for model, ms in sorted(model_stats.items(), key=lambda x: -x[1]["calls"]):
                avg_lat = sum(ms["latencies"]) / len(ms["latencies"]) if ms["latencies"] else 0
                parts.append(
                    f"  - **{model}**: {ms['calls']} calls, "
                    f"in={ms['input']:,} out={ms['output']:,} "
                    f"think={ms['thinking']:,} "
                    f"cost=${ms['cost']:.4f} "
                    f"avg_lat={avg_lat:.0f}ms"
                )

        return "\n".join(parts)

    return token_stats_handler


def _make_session_stats_handler(session_log_dir: str, token_log_path: str):
    """Return a session_stats handler that reads from session JSONL logs."""

    def session_stats_handler(tool_input: dict) -> str:
        session_id = tool_input.get("session_id")
        log_dir = Path(session_log_dir)

        if not log_dir.exists():
            return "No session logs found. data/sessions/ does not exist yet."

        session_files = sorted(log_dir.glob("*.jsonl"))
        if not session_files:
            return "No session log files found in data/sessions/."

        if session_id:
            # Inspect a specific session
            target = log_dir / f"{session_id}.jsonl"
            if not target.exists():
                return f"Session log for '{session_id}' not found."

            records = []
            try:
                with open(target) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            records.append(json.loads(line))
            except Exception as e:
                return f"ERROR reading session log: {e}"

            if not records:
                return f"Session log for '{session_id}' is empty."

            turns = [r for r in records if r.get("type") in ("user", "assistant")]
            tool_calls = [r for r in records if r.get("type") == "tool_call"]
            all_tools: list[str] = []
            for tc in tool_calls:
                all_tools.extend(tc.get("tools_used", []))

            total_tokens = sum(
                r.get("tokens", {}).get("input", 0) + r.get("tokens", {}).get("output", 0)
                for r in records
            )
            total_duration = sum(r.get("duration_ms", 0) for r in records)

            # Tool frequency
            tool_freq: dict[str, int] = {}
            for t in all_tools:
                tool_freq[t] = tool_freq.get(t, 0) + 1

            parts = [
                f"## Session: {session_id}",
                f"**Total records**: {len(records)}",
                f"**Turns**: {len(turns)}",
                f"**Tool call batches**: {len(tool_calls)}",
                f"**Individual tool calls**: {len(all_tools)}",
                f"**Total tokens**: {total_tokens:,}",
                f"**Total duration**: {total_duration:,}ms ({total_duration / 1000:.1f}s)",
            ]

            if tool_freq:
                parts.append("\n### Tool Frequency")
                for tool, count in sorted(tool_freq.items(), key=lambda x: -x[1]):
                    parts.append(f"  - {tool}: {count}")

            return "\n".join(parts)

        # Aggregate stats across all sessions
        total_sessions = len(session_files)
        total_turns = 0
        total_tool_calls = 0
        all_tools_agg: dict[str, int] = {}
        session_turn_counts: list[int] = []

        for sf in session_files:
            try:
                session_turns = 0
                with open(sf) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            r = json.loads(line)
                            if r.get("type") in ("user", "assistant"):
                                total_turns += 1
                                session_turns += 1
                            elif r.get("type") == "tool_call":
                                tools = r.get("tools_used", [])
                                total_tool_calls += len(tools)
                                for t in tools:
                                    all_tools_agg[t] = all_tools_agg.get(t, 0) + 1
                        except json.JSONDecodeError:
                            continue
                session_turn_counts.append(session_turns)
            except Exception:
                continue

        avg_turns = sum(session_turn_counts) / len(session_turn_counts) if session_turn_counts else 0

        parts = [
            f"## Session Stats (Aggregate)",
            f"**Total sessions logged**: {total_sessions}",
            f"**Total turns**: {total_turns:,}",
            f"**Avg turns/session**: {avg_turns:.1f}",
            f"**Total tool calls**: {total_tool_calls:,}",
        ]

        if all_tools_agg:
            parts.append("\n### Top Tools (all sessions)")
            for tool, count in sorted(all_tools_agg.items(), key=lambda x: -x[1])[:15]:
                parts.append(f"  - {tool}: {count}")

        # Cross-reference with token_usage.jsonl for cost
        token_log = Path(token_log_path)
        if token_log.exists():
            try:
                total_cost = 0.0
                total_api_calls = 0
                with open(token_log) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                r = json.loads(line)
                                total_cost += r.get("estimated_cost_usd", 0)
                                total_api_calls += 1
                            except json.JSONDecodeError:
                                continue
                parts.append(f"\n**Total API calls (all time)**: {total_api_calls:,}")
                parts.append(f"**Total estimated cost (all time)**: ${total_cost:.4f}")
            except Exception:
                pass

        return "\n".join(parts)

    return session_stats_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_resource_tools(
    registry: ToolRegistry,
    mind_root: str,
    token_log_path: str | None = None,
    session_log_dir: str | None = None,
) -> None:
    """
    Register resource_usage, token_stats, and session_stats tools.

    Args:
        registry: The tool registry to register into
        mind_root: Path to the aiciv-mind repo root
        token_log_path: Override path to token_usage.jsonl (default: data/token_usage.jsonl)
        session_log_dir: Override path to session logs dir (default: data/sessions/)
    """
    mind_root_path = Path(mind_root)
    _token_log = token_log_path or str(mind_root_path / "data" / "token_usage.jsonl")
    _session_dir = session_log_dir or str(mind_root_path / "data" / "sessions")

    registry.register(
        "resource_usage",
        _RESOURCE_USAGE_DEFINITION,
        _make_resource_usage_handler(mind_root),
        read_only=True,
    )

    registry.register(
        "token_stats",
        _TOKEN_STATS_DEFINITION,
        _make_token_stats_handler(_token_log),
        read_only=True,
    )

    registry.register(
        "session_stats",
        _SESSION_STATS_DEFINITION,
        _make_session_stats_handler(_session_dir, _token_log),
        read_only=True,
    )

    logger.info("Registered resource tools: resource_usage, token_stats, session_stats")
