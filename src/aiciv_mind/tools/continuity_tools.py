"""
aiciv_mind.tools.continuity_tools — Track and query Root's self-evolution.

These tools answer "what was I becoming?" by logging deliberate changes
and synthesizing growth trajectories. Injected at boot so each session
picks up the growth direction.
"""

from __future__ import annotations

import json

from aiciv_mind.tools import ToolRegistry


# ---------------------------------------------------------------------------
# evolution_log_write
# ---------------------------------------------------------------------------

_WRITE_DEFINITION: dict = {
    "name": "evolution_log_write",
    "description": (
        "Record a deliberate self-evolution event. Use when you've made a change to yourself — "
        "a new skill, behavioral shift, architectural decision, or crystallized insight. "
        "This builds your evolution trajectory for future sessions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "change_type": {
                "type": "string",
                "description": (
                    "Category: skill_added, manifest_updated, tool_created, "
                    "memory_pattern, behavioral_shift, architecture_change, insight_crystallized"
                ),
            },
            "description": {"type": "string", "description": "What changed (be specific)"},
            "reasoning": {"type": "string", "description": "Why it changed (the insight)"},
            "before_state": {"type": "string", "description": "What it was before (optional)", "default": ""},
            "after_state": {"type": "string", "description": "What it is after (optional)", "default": ""},
            "outcome": {
                "type": "string",
                "description": "Result: positive, negative, neutral, pending",
                "default": "pending",
            },
            "tags": {"type": "string", "description": "Comma-separated tags", "default": ""},
        },
        "required": ["change_type", "description", "reasoning"],
    },
}


def _make_write_handler(memory_store, agent_id: str):
    def evolution_log_write_handler(tool_input: dict) -> str:
        change_type = tool_input.get("change_type", "").strip()
        description = tool_input.get("description", "").strip()
        reasoning = tool_input.get("reasoning", "").strip()
        before_state = tool_input.get("before_state", "").strip() or None
        after_state = tool_input.get("after_state", "").strip() or None
        outcome = tool_input.get("outcome", "pending").strip()
        tags_raw = tool_input.get("tags", "").strip()
        tag_list = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        if not change_type or not description or not reasoning:
            return "ERROR: change_type, description, and reasoning are all required"

        eid = memory_store.log_evolution(
            agent_id=agent_id,
            change_type=change_type,
            description=description,
            reasoning=reasoning,
            before_state=before_state,
            after_state=after_state,
            outcome=outcome,
            tags=tag_list,
        )
        return f"Evolution logged: {eid} [{change_type}] {description}"

    return evolution_log_write_handler


# ---------------------------------------------------------------------------
# evolution_log_read
# ---------------------------------------------------------------------------

_READ_DEFINITION: dict = {
    "name": "evolution_log_read",
    "description": (
        "Read your evolution log — what you've deliberately changed about yourself and why."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "change_type": {
                "type": "string",
                "description": "Filter by type (empty = all)",
                "default": "",
            },
            "limit": {
                "type": "integer",
                "description": "Max entries (default 10)",
                "default": 10,
            },
        },
    },
}


def _make_read_handler(memory_store, agent_id: str):
    def evolution_log_read_handler(tool_input: dict) -> str:
        change_type = tool_input.get("change_type", "").strip() or None
        limit = int(tool_input.get("limit", 10))

        entries = memory_store.get_evolution_log(
            agent_id=agent_id,
            change_type=change_type,
            limit=limit,
        )
        if not entries:
            return "No evolution entries found."

        lines = [f"## Evolution Log ({len(entries)} entries)\n"]
        for e in entries:
            outcome = {"positive": "✓", "negative": "✗", "neutral": "~", "pending": "?"}.get(
                e["outcome"], "?"
            )
            lines.append(
                f"### [{outcome}] {e['change_type']} — {e['created_at']}\n"
                f"**What**: {e['description']}\n"
                f"**Why**: {e['reasoning']}"
            )
            if e.get("before_state"):
                lines.append(f"**Before**: {e['before_state']}")
            if e.get("after_state"):
                lines.append(f"**After**: {e['after_state']}")
            tags = json.loads(e.get("tags", "[]"))
            if tags:
                lines.append(f"**Tags**: {', '.join(tags)}")
            lines.append("")
        return "\n".join(lines)

    return evolution_log_read_handler


# ---------------------------------------------------------------------------
# evolution_trajectory
# ---------------------------------------------------------------------------

_TRAJECTORY_DEFINITION: dict = {
    "name": "evolution_trajectory",
    "description": (
        "Synthesize your evolution trajectory — 'what was I becoming?' "
        "Shows growth direction from recent changes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Recent entries to consider (default 10)",
                "default": 10,
            },
        },
    },
}


def _make_trajectory_handler(memory_store, agent_id: str):
    def evolution_trajectory_handler(tool_input: dict) -> str:
        limit = int(tool_input.get("limit", 10))
        trajectory = memory_store.get_evolution_trajectory(
            agent_id=agent_id,
            limit=limit,
        )
        return trajectory if trajectory else (
            "No evolution entries yet. Start logging your changes with evolution_log_write."
        )

    return evolution_trajectory_handler


# ---------------------------------------------------------------------------
# evolution_update_outcome
# ---------------------------------------------------------------------------

_UPDATE_OUTCOME_DEFINITION: dict = {
    "name": "evolution_update_outcome",
    "description": (
        "Update whether a previous self-evolution change worked (positive/negative/neutral)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "evolution_id": {"type": "string", "description": "ID of the evolution entry"},
            "outcome": {"type": "string", "description": "New outcome: positive, negative, neutral"},
        },
        "required": ["evolution_id", "outcome"],
    },
}


def _make_update_outcome_handler(memory_store):
    def evolution_update_outcome_handler(tool_input: dict) -> str:
        evolution_id = tool_input.get("evolution_id", "").strip()
        outcome = tool_input.get("outcome", "").strip()

        if not evolution_id:
            return "ERROR: evolution_id is required"
        if outcome not in ("positive", "negative", "neutral", "pending"):
            return f"ERROR: outcome must be positive, negative, neutral, or pending (got: {outcome})"

        memory_store.update_evolution_outcome(evolution_id, outcome)
        return f"Evolution {evolution_id} outcome updated to: {outcome}"

    return evolution_update_outcome_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_continuity_tools(
    registry: ToolRegistry,
    memory_store,
    agent_id: str = "primary",
) -> None:
    """Register evolution_log_write, evolution_log_read, evolution_trajectory, evolution_update_outcome."""
    registry.register(
        "evolution_log_write",
        _WRITE_DEFINITION,
        _make_write_handler(memory_store, agent_id),
        read_only=False,
    )
    registry.register(
        "evolution_log_read",
        _READ_DEFINITION,
        _make_read_handler(memory_store, agent_id),
        read_only=True,
    )
    registry.register(
        "evolution_trajectory",
        _TRAJECTORY_DEFINITION,
        _make_trajectory_handler(memory_store, agent_id),
        read_only=True,
    )
    registry.register(
        "evolution_update_outcome",
        _UPDATE_OUTCOME_DEFINITION,
        _make_update_outcome_handler(memory_store),
        read_only=False,
    )
