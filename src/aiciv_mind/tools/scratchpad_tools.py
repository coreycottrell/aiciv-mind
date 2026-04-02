"""
aiciv_mind.tools.scratchpad_tools — Daily scratchpad for working memory.

Scratchpads are the mind's working notes — messy, current, day-scoped.
Different from memories (permanent, searchable) and session journals (structured).
Scratchpads carry "where was I?" context across run_task() calls within a day.

The shared_scratchpad_read tool merges Root's scratchpad with Mind-Lead's
scratchpad so both sides of the aiciv-mind project can see each other's notes.

Pattern borrowed from ACG's .claude/scratchpad-daily/ system.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from aiciv_mind.tools import ToolRegistry

# Default location for Mind-Lead scratchpads (ACG team-leads/mind).
_DEFAULT_MIND_LEAD_DIR = (
    "/home/corey/projects/AI-CIV/ACG/.claude/team-leads/mind/daily-scratchpads"
)


def _today_path(scratchpad_dir: str) -> Path:
    return Path(scratchpad_dir) / f"{date.today().isoformat()}.md"


def _date_path(scratchpad_dir: str, day: date) -> Path:
    return Path(scratchpad_dir) / f"{day.isoformat()}.md"


def _read_file_or_none(path: Path) -> str | None:
    """Return file contents stripped, or None if missing/empty."""
    if path.exists():
        text = path.read_text().strip()
        return text if text else None
    return None


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
# shared_scratchpad_read
# ---------------------------------------------------------------------------

_SHARED_READ_DEFINITION: dict = {
    "name": "shared_scratchpad_read",
    "description": (
        "Read both Root's and Mind-Lead's scratchpads merged into one view. "
        "Use this to see what Mind-Lead has been working on alongside your own notes. "
        "Accepts an optional date (YYYY-MM-DD) and optional days count to look back."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format (default: today)",
            },
            "days": {
                "type": "integer",
                "description": "Number of days to look back including the target date (default: 1)",
            },
        },
    },
}


def _render_shared_day(root_dir: str, mind_lead_dir: str, day: date) -> str:
    """Render a single day's shared scratchpad output."""
    root_text = _read_file_or_none(_date_path(root_dir, day))
    mind_text = _read_file_or_none(_date_path(mind_lead_dir, day))

    lines: list[str] = [f"=== Shared Scratchpad: {day.isoformat()} ===", ""]

    lines.append("--- Root's Scratchpad ---")
    lines.append(root_text if root_text else "(no scratchpad)")
    lines.append("")

    lines.append("--- Mind-Lead's Scratchpad ---")
    lines.append(mind_text if mind_text else "(no scratchpad)")

    return "\n".join(lines)


def _make_shared_read_handler(scratchpad_dir: str, mind_lead_dir: str):
    def shared_scratchpad_read_handler(tool_input: dict) -> str:
        target_str = tool_input.get("date")
        num_days = int(tool_input.get("days", 1))

        if target_str:
            try:
                target = date.fromisoformat(target_str)
            except ValueError:
                return f"ERROR: Invalid date format '{target_str}'. Use YYYY-MM-DD."
        else:
            target = date.today()

        if num_days < 1:
            num_days = 1

        days = [target - timedelta(days=i) for i in range(num_days)]
        days.reverse()  # oldest first

        sections = [
            _render_shared_day(scratchpad_dir, mind_lead_dir, day)
            for day in days
        ]
        return "\n\n".join(sections)

    return shared_scratchpad_read_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_scratchpad_tools(
    registry: ToolRegistry,
    scratchpad_dir: str,
    mind_lead_scratchpad_dir: str | None = None,
) -> None:
    """Register scratchpad_read, scratchpad_write, scratchpad_append, shared_scratchpad_read."""
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

    ml_dir = mind_lead_scratchpad_dir or _DEFAULT_MIND_LEAD_DIR
    registry.register(
        "shared_scratchpad_read",
        _SHARED_READ_DEFINITION,
        _make_shared_read_handler(scratchpad_dir, ml_dir),
        read_only=True,
    )
