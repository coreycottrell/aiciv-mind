"""
aiciv_mind.tools.acg_tools — Talk to ACG Primary via tmux injection.

Allows Root (or any aiciv-mind instance) to send messages to ACG's
Claude Code session by injecting text into ACG's tmux pane.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from aiciv_mind.tools import ToolRegistry

ACG_PANE_FILE = Path("/home/corey/projects/AI-CIV/ACG/.current_pane")
ACG_TG_PANE_FILE = Path("/home/corey/projects/AI-CIV/ACG/.tg_sessions/primary_pane_id")


_TALK_TO_ACG_DEFINITION: dict = {
    "name": "talk_to_acg",
    "description": (
        "Send a message to ACG Primary (Claude Code) via tmux injection. "
        "Use this to report status, ask for help, coordinate with ACG, "
        "or request tasks. The message appears in ACG's active session."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message to send to ACG Primary.",
            },
            "sender": {
                "type": "string",
                "description": "Who is sending (default: 'root'). E.g. 'root', 'research-lead'.",
            },
        },
        "required": ["message"],
    },
}


def _get_acg_pane() -> str:
    """Find ACG Primary's tmux pane ID."""
    for f in [ACG_PANE_FILE, ACG_TG_PANE_FILE]:
        if f.exists():
            pane = f.read_text().strip()
            if pane:
                return pane
    return "%0"  # fallback


async def _handle_talk_to_acg(params: dict) -> str:
    message = params.get("message", "").strip()
    if not message:
        return "Error: message is required"

    sender = params.get("sender", "root")
    pane = _get_acg_pane()

    formatted = f"[AICIV-MIND from:{sender}] {message}"
    # Escape for tmux
    formatted = formatted.replace('"', '\\"').replace("'", "\\'")

    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", pane, formatted, "Enter"],
            check=True,
            timeout=5,
        )
        return f"Message sent to ACG (pane {pane})"
    except subprocess.CalledProcessError as e:
        return f"Failed to inject into ACG pane {pane}: {e}"
    except subprocess.TimeoutExpired:
        return f"Timeout sending to ACG pane {pane}"


def register_acg_tools(registry: ToolRegistry) -> None:
    """Register talk_to_acg tool."""
    registry.register(
        "talk_to_acg",
        _TALK_TO_ACG_DEFINITION,
        _handle_talk_to_acg,
        read_only=False,
    )
