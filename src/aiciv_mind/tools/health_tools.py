"""
aiciv_mind.tools.health_tools — System health monitoring.

Provides system_health tool that returns a snapshot of Root's
operational state: memory DB size, process status, git status,
context window usage, and recent errors.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)

_HEALTH_DEFINITION: dict = {
    "name": "system_health",
    "description": (
        "Get a system health snapshot: memory DB size, running processes, "
        "git status, disk usage, and recent errors. Use at the start of "
        "every BOOP cycle for self-status reporting."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verbose": {
                "type": "boolean",
                "description": "Include detailed process list (default: false)",
            },
        },
    },
}


def _make_health_handler(
    memory_store=None,
    mind_root: str | None = None,
):
    """Return a system_health handler."""

    def system_health_handler(tool_input: dict) -> str:
        verbose = tool_input.get("verbose", False)
        parts: list[str] = ["## System Health Report"]

        # 1. Memory DB
        if memory_store is not None:
            try:
                db_path = getattr(memory_store, "_db_path", None)
                if db_path and db_path != ":memory:" and Path(db_path).exists():
                    size_mb = Path(db_path).stat().st_size / (1024 * 1024)
                    parts.append(f"**Memory DB**: {size_mb:.1f} MB ({db_path})")

                # Count memories
                try:
                    row = memory_store._conn.execute(
                        "SELECT COUNT(*) FROM memories"
                    ).fetchone()
                    count = row[0] if row else 0
                    parts.append(f"**Total memories**: {count}")
                except Exception:
                    pass

                # Count sessions
                try:
                    row = memory_store._conn.execute(
                        "SELECT COUNT(*) FROM session_journal"
                    ).fetchone()
                    count = row[0] if row else 0
                    parts.append(f"**Total sessions**: {count}")
                except Exception:
                    pass
            except Exception as e:
                parts.append(f"**Memory DB**: ERROR — {e}")

        # 2. Running processes (aiciv-mind related)
        try:
            ps_out = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            mind_procs = [
                line for line in ps_out.splitlines()
                if "aiciv" in line.lower() or "groupchat" in line.lower()
                or "dream_cycle" in line.lower() or "agentmail" in line.lower()
                or "telegram" in line.lower() or "litellm" in line.lower()
            ]
            if mind_procs:
                parts.append(f"**Running processes** ({len(mind_procs)}):")
                for proc in mind_procs[:10]:
                    # Extract just the command part
                    fields = proc.split(None, 10)
                    if len(fields) >= 11:
                        pid = fields[1]
                        cmd = fields[10][:100]
                        parts.append(f"  - PID {pid}: {cmd}")
            else:
                parts.append("**Running processes**: none found")
        except Exception as e:
            parts.append(f"**Processes**: ERROR — {e}")

        # 3. Git status
        if mind_root:
            try:
                git_out = subprocess.run(
                    ["git", "status", "--short"],
                    capture_output=True, text=True, timeout=5,
                    cwd=mind_root,
                ).stdout.strip()
                if git_out:
                    changed = len(git_out.splitlines())
                    parts.append(f"**Git status**: {changed} changed file(s)")
                    if verbose:
                        parts.append(f"```\n{git_out[:500]}\n```")
                else:
                    parts.append("**Git status**: clean")

                # Last commit
                log_out = subprocess.run(
                    ["git", "log", "--oneline", "-1"],
                    capture_output=True, text=True, timeout=5,
                    cwd=mind_root,
                ).stdout.strip()
                if log_out:
                    parts.append(f"**Last commit**: {log_out}")
            except Exception as e:
                parts.append(f"**Git**: ERROR — {e}")

        # 4. Disk usage
        try:
            df_out = subprocess.run(
                ["df", "-h", "/home"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            lines = df_out.splitlines()
            if len(lines) >= 2:
                fields = lines[1].split()
                if len(fields) >= 5:
                    parts.append(
                        f"**Disk**: {fields[2]} used / {fields[1]} total ({fields[4]} used)"
                    )
        except Exception:
            pass

        # 5. Hub connectivity
        try:
            import httpx
            resp = httpx.get("http://87.99.131.49:8900/health", timeout=5)
            parts.append(f"**Hub**: {'UP' if resp.status_code == 200 else f'status {resp.status_code}'}")
        except Exception:
            parts.append("**Hub**: DOWN or unreachable")

        # 6. AgentAuth connectivity
        try:
            import httpx
            resp = httpx.get("http://5.161.90.32:8700/health", timeout=5)
            parts.append(f"**AgentAuth**: {'UP' if resp.status_code == 200 else f'status {resp.status_code}'}")
        except Exception:
            parts.append("**AgentAuth**: DOWN or unreachable")

        return "\n".join(parts)

    return system_health_handler


def register_health_tools(
    registry: ToolRegistry,
    memory_store=None,
    mind_root: str | None = None,
) -> None:
    """Register system_health tool."""
    registry.register(
        "system_health",
        _HEALTH_DEFINITION,
        _make_health_handler(memory_store=memory_store, mind_root=mind_root),
        read_only=True,
    )
    logger.info("Registered system_health tool")
