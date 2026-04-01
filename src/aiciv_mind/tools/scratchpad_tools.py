"""
aiciv_mind.tools.scratchpad_tools — Daily scratchpad for working memory.

Scratchpads are the mind's working notes — messy, current, day-scoped.
Different from memories (permanent, searchable) and session journals (structured).
Scratchpads carry "where was I?" context across run_task() calls within a day.

Pattern borrowed from ACG's .claude/scratchpad-daily/ system.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from aiciv_mind.tools import ToolRegistry


def _today_path(scratchpad_dir: str) -> Path:
    return Path(scratchpad_dir) / f"{date.today().isoformat()}.md"


# ---------------------------------------------------------------------------
# scratchpad_read
# ---------------------------------------------------------------------------

_READ_DEFINITION: dict = {
    "name": "scratchpad_read",
    "description": (
        "Read today's scratchpad — your working notes for the day. "
        "Use at session start to remember what you were doing. "
        "Returns empty string if no scratchpad exists yet today."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


def _make_read_handler(scratchpad_dir: str):
    def scratchpad_read_handler(tool_input: dict) -> str:
        path = _today_path(scratchpad_dir)
        if not path.exists():
            return f"No scratchpad for {date.today().isoformat()} yet. Start one with scratchpad_write."
        return path.read_text()

    return scratchpad_read_handler


# ---------------------------------------------------------------------------
# scratchpad_write
# ---------------------------------------------------------------------------

_WRITE_DEFINITION: dict = {
    "name": "scratchpad_write",
    "description": (
        "Write to today's scratchpad. Use for working notes, current state, "
        "in-progress thinking, task lists, anything you need to remember "
        "across turns today. Replaces the entire scratchpad content."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The full scratchpad content (replaces existing)",
            },
        },
        "required": ["content"],
    },
}


def _make_write_handler(scratchpad_dir: str):
    def scratchpad_write_handler(tool_input: dict) -> str:
        content = tool_input.get("content", "")
        path = _today_path(scratchpad_dir)
        os.makedirs(path.parent, exist_ok=True)
        path.write_text(content)
        return f"Scratchpad updated ({len(content)} chars) at {path}"

    return scratchpad_write_handler


# ---------------------------------------------------------------------------
# scratchpad_append
# ---------------------------------------------------------------------------

_APPEND_DEFINITION: dict = {
    "name": "scratchpad_append",
    "description": (
        "Append a line to today's scratchpad without reading/rewriting the whole thing. "
        "Use for quick notes, status updates, task completions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "line": {
                "type": "string",
                "description": "The line to append",
            },
        },
        "required": ["line"],
    },
}


def _make_append_handler(scratchpad_dir: str):
    def scratchpad_append_handler(tool_input: dict) -> str:
        line = tool_input.get("line", "")
        path = _today_path(scratchpad_dir)
        os.makedirs(path.parent, exist_ok=True)
        with open(path, "a") as f:
            f.write(line + "\n")
        return f"Appended to scratchpad: {line[:80]}"

    return scratchpad_append_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_scratchpad_tools(registry: ToolRegistry, scratchpad_dir: str) -> None:
    """Register scratchpad_read, scratchpad_write, scratchpad_append."""
    registry.register(
        "scratchpad_read",
        _READ_DEFINITION,
        _make_read_handler(scratchpad_dir),
        read_only=True,
    )
    registry.register(
        "scratchpad_write",
        _WRITE_DEFINITION,
        _make_write_handler(scratchpad_dir),
        read_only=False,
    )
    registry.register(
        "scratchpad_append",
        _APPEND_DEFINITION,
        _make_append_handler(scratchpad_dir),
        read_only=False,
    )
