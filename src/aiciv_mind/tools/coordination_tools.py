"""
aiciv_mind.tools.coordination_tools — Three-level scratchpad system.

Level 1: Agent scratchpads — personal daily notes (existing scratchpad_tools.py)
Level 2: Team scratchpads — one per vertical, shared between team lead + its agents
Level 3: Coordination scratchpad — cross-vertical, shared between all team leads + Primary

This module implements Levels 2 and 3.  Level 1 is in scratchpad_tools.py.

Directory structure:
    scratchpads/teams/{vertical}-team.md     — Level 2
    scratchpads/coordination.md              — Level 3
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from aiciv_mind.tools import ToolRegistry


# ---------------------------------------------------------------------------
# team_scratchpad_read
# ---------------------------------------------------------------------------

_TEAM_READ_DEFINITION: dict = {
    "name": "team_scratchpad_read",
    "description": (
        "Read the team scratchpad for a vertical. "
        "Shared between the team lead and all its agents. "
        "Use this to see what your team has been working on."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "vertical": {
                "type": "string",
                "description": "Team vertical name (e.g. 'research', 'coder', 'memory', 'comms', 'ops')",
            },
        },
        "required": ["vertical"],
    },
}


def _team_scratchpad_path(base_dir: str, vertical: str) -> Path:
    return Path(base_dir) / "teams" / f"{vertical}-team.md"


def _make_team_read_handler(base_dir: str):
    def handler(tool_input: dict) -> str:
        vertical = tool_input.get("vertical", "").strip()
        if not vertical:
            return "ERROR: No vertical provided"
        path = _team_scratchpad_path(base_dir, vertical)
        if not path.exists():
            return f"No team scratchpad for '{vertical}' yet. Start one with team_scratchpad_write."
        return path.read_text()

    return handler


# ---------------------------------------------------------------------------
# team_scratchpad_write
# ---------------------------------------------------------------------------

_TEAM_WRITE_DEFINITION: dict = {
    "name": "team_scratchpad_write",
    "description": (
        "Append an entry to the team scratchpad for a vertical. "
        "Both the team lead and its agents can write here. "
        "Entries are timestamped and attributed to the writer."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "vertical": {
                "type": "string",
                "description": "Team vertical name",
            },
            "entry": {
                "type": "string",
                "description": "The entry to append (will be timestamped)",
            },
        },
        "required": ["vertical", "entry"],
    },
}


def _make_team_write_handler(base_dir: str, writer_id: str):
    def handler(tool_input: dict) -> str:
        vertical = tool_input.get("vertical", "").strip()
        entry = tool_input.get("entry", "").strip()
        if not vertical:
            return "ERROR: No vertical provided"
        if not entry:
            return "ERROR: No entry provided"

        path = _team_scratchpad_path(base_dir, vertical)
        os.makedirs(path.parent, exist_ok=True)

        timestamp = datetime.now().strftime("%H:%M")
        line = f"\n[{timestamp} | {writer_id}] {entry}\n"
        with open(path, "a") as f:
            f.write(line)

        return f"Appended to {vertical} team scratchpad ({len(entry)} chars)"

    return handler


# ---------------------------------------------------------------------------
# coordination_read
# ---------------------------------------------------------------------------

_COORD_READ_DEFINITION: dict = {
    "name": "coordination_read",
    "description": (
        "Read the coordination scratchpad — cross-vertical status visible "
        "to Primary and all team leads. Contains active decisions, priorities, "
        "and blockers across the entire mind."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


def _coordination_path(base_dir: str) -> Path:
    return Path(base_dir) / "coordination.md"


def _make_coord_read_handler(base_dir: str):
    def handler(tool_input: dict) -> str:
        path = _coordination_path(base_dir)
        if not path.exists():
            return "No coordination scratchpad yet. Start one with coordination_write."
        return path.read_text()

    return handler


# ---------------------------------------------------------------------------
# coordination_write
# ---------------------------------------------------------------------------

_COORD_WRITE_DEFINITION: dict = {
    "name": "coordination_write",
    "description": (
        "Append an entry to the coordination scratchpad — cross-vertical "
        "status shared between Primary and all team leads. Use for priorities, "
        "blockers, decisions that affect multiple verticals."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entry": {
                "type": "string",
                "description": "The entry to append (will be timestamped)",
            },
        },
        "required": ["entry"],
    },
}


def _make_coord_write_handler(base_dir: str, writer_id: str):
    def handler(tool_input: dict) -> str:
        entry = tool_input.get("entry", "").strip()
        if not entry:
            return "ERROR: No entry provided"

        path = _coordination_path(base_dir)
        os.makedirs(path.parent, exist_ok=True)

        timestamp = datetime.now().strftime("%H:%M")
        line = f"\n[{timestamp} | {writer_id}] {entry}\n"
        with open(path, "a") as f:
            f.write(line)

        return f"Appended to coordination scratchpad ({len(entry)} chars)"

    return handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_coordination_tools(
    registry: ToolRegistry,
    scratchpad_base_dir: str,
    writer_id: str = "unknown",
) -> None:
    """
    Register team_scratchpad_read, team_scratchpad_write,
    coordination_read, and coordination_write tools.

    Args:
        registry: ToolRegistry to register into
        scratchpad_base_dir: Base directory for scratchpads (contains teams/ and coordination.md)
        writer_id: Mind ID of the writer (for attribution in entries)
    """
    registry.register(
        "team_scratchpad_read",
        _TEAM_READ_DEFINITION,
        _make_team_read_handler(scratchpad_base_dir),
        read_only=True,
    )
    registry.register(
        "team_scratchpad_write",
        _TEAM_WRITE_DEFINITION,
        _make_team_write_handler(scratchpad_base_dir, writer_id),
        read_only=False,
    )
    registry.register(
        "coordination_read",
        _COORD_READ_DEFINITION,
        _make_coord_read_handler(scratchpad_base_dir),
        read_only=True,
    )
    registry.register(
        "coordination_write",
        _COORD_WRITE_DEFINITION,
        _make_coord_write_handler(scratchpad_base_dir, writer_id),
        read_only=False,
    )
