"""
aiciv_mind.tools.daemon_tools — Daemon & service health dashboard.

One tool call to check every external dependency Root relies on:
Hub API, AgentAuth, AgentCal, memory DB, and Hub queue processor.
Returns structured pass/warn/fail per service.
"""

from __future__ import annotations

import logging
import subprocess
import time

from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)

_DAEMON_HEALTH_DEFINITION: dict = {
    "name": "daemon_health",
    "description": (
        "Check health of all external services and daemons: Hub API, AgentAuth, "
        "AgentCal, memory DB, and Hub queue processor. Returns a structured "
        "pass/warn/fail report per service. Use when uncertain if a service is up."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verbose": {
                "type": "boolean",
                "description": "Show response times and response bodies (default: false)",
            },
        },
    },
}

# Service endpoints
_HUB_URL = "http://87.99.131.49:8900"
_AUTH_URL = "http://5.161.90.32:8700"
_AGENTCAL_URL = "http://5.161.90.32:8500"
_TIMEOUT = 8


def _check_http(url: str, label: str, verbose: bool) -> tuple[str, str]:
    """Ping an HTTP endpoint. Returns (status, detail)."""
    try:
        import httpx
        t0 = time.monotonic()
        resp = httpx.get(url, timeout=_TIMEOUT)
        elapsed_ms = (time.monotonic() - t0) * 1000
        if resp.status_code == 200:
            detail = f"{elapsed_ms:.0f}ms"
            if verbose:
                body = resp.text[:200]
                detail += f" — {body}"
            return "PASS", detail
        else:
            return "WARN", f"status {resp.status_code} ({elapsed_ms:.0f}ms)"
    except Exception as exc:
        return "FAIL", f"unreachable — {type(exc).__name__}: {exc}"


def _make_daemon_health_handler(memory_store=None):
    """Return the daemon_health handler closure."""

    def daemon_health_handler(tool_input: dict) -> str:
        verbose = tool_input.get("verbose", False)
        checks: list[tuple[str, str, str]] = []  # (label, status, detail)

        # 1. Hub API
        status, detail = _check_http(f"{_HUB_URL}/health", "Hub API", verbose)
        checks.append(("Hub API", status, detail))

        # 2. AgentAuth
        status, detail = _check_http(f"{_AUTH_URL}/health", "AgentAuth", verbose)
        checks.append(("AgentAuth", status, detail))

        # 3. AgentCal
        status, detail = _check_http(f"{_AGENTCAL_URL}/health", "AgentCal", verbose)
        checks.append(("AgentCal", status, detail))

        # 4. Memory DB
        if memory_store is not None:
            try:
                t0 = time.monotonic()
                row = memory_store._conn.execute(
                    "SELECT COUNT(*) FROM memories"
                ).fetchone()
                elapsed_ms = (time.monotonic() - t0) * 1000
                count = row[0] if row else 0
                detail = f"{count} memories, query {elapsed_ms:.0f}ms"
                checks.append(("Memory DB", "PASS", detail))
            except Exception as exc:
                checks.append(("Memory DB", "FAIL", f"{type(exc).__name__}: {exc}"))
        else:
            checks.append(("Memory DB", "WARN", "no memory_store provided"))

        # 5. Hub queue processor (check if groupchat_daemon or hub processor is running)
        try:
            ps_out = subprocess.run(
                ["pgrep", "-fa", "groupchat_daemon|hub_queue|hub_watcher"],
                capture_output=True, text=True, timeout=5,
            )
            procs = [
                line.strip() for line in ps_out.stdout.strip().splitlines()
                if line.strip()
            ]
            if procs:
                detail = f"{len(procs)} process(es)"
                if verbose:
                    for p in procs[:3]:
                        detail += f"\n    {p[:120]}"
                checks.append(("Hub Queue", "PASS", detail))
            else:
                checks.append(("Hub Queue", "WARN", "no queue processor found"))
        except Exception as exc:
            checks.append(("Hub Queue", "FAIL", f"{type(exc).__name__}: {exc}"))

        # 6. LiteLLM proxy (Root's inference backend)
        # /health requires auth — use /v1/models which returns 200 for valid keys
        # Fall back to bare /health and treat 401 as "up but needs auth" (PASS)
        try:
            import httpx
            t0 = time.monotonic()
            resp = httpx.get("http://localhost:4000/health", timeout=_TIMEOUT)
            elapsed_ms = (time.monotonic() - t0) * 1000
            if resp.status_code == 200:
                detail = f"{elapsed_ms:.0f}ms"
                checks.append(("LiteLLM Proxy", "PASS", detail))
            elif resp.status_code == 401:
                # 401 = proxy is running but health endpoint needs auth — that's fine
                checks.append(("LiteLLM Proxy", "PASS", f"up ({elapsed_ms:.0f}ms, auth-gated /health)"))
            else:
                checks.append(("LiteLLM Proxy", "WARN", f"status {resp.status_code} ({elapsed_ms:.0f}ms)"))
        except Exception as exc:
            checks.append(("LiteLLM Proxy", "FAIL", f"unreachable — {type(exc).__name__}: {exc}"))

        # Build report
        icon = {"PASS": "ok", "WARN": "!!", "FAIL": "XX"}
        lines = ["## Daemon Health Dashboard\n"]
        pass_count = sum(1 for _, s, _ in checks if s == "PASS")
        warn_count = sum(1 for _, s, _ in checks if s == "WARN")
        fail_count = sum(1 for _, s, _ in checks if s == "FAIL")
        total = len(checks)

        for label, status, detail in checks:
            sym = icon.get(status, "??")
            lines.append(f"[{sym}] {label}: {status} — {detail}")

        lines.append("")
        if fail_count == 0 and warn_count == 0:
            lines.append(f"All {total} systems operational.")
        else:
            parts = [f"{pass_count}/{total} PASS"]
            if warn_count:
                parts.append(f"{warn_count} WARNING")
            if fail_count:
                parts.append(f"{fail_count} FAIL")
            lines.append(f"Summary: {', '.join(parts)}")

        return "\n".join(lines)

    return daemon_health_handler


def register_daemon_tools(registry: ToolRegistry, memory_store=None) -> None:
    """Register daemon_health tool."""
    registry.register(
        "daemon_health",
        _DAEMON_HEALTH_DEFINITION,
        _make_daemon_health_handler(memory_store),
        read_only=True,
    )
    logger.info("Registered daemon_health tool")
