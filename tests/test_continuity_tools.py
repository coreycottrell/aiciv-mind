"""
Tests for aiciv_mind.tools.continuity_tools — Evolution log and trajectory.

Covers: tool definitions, evolution_log_write, evolution_log_read,
evolution_trajectory, evolution_update_outcome handlers, error cases,
and registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_continuity_tools.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from aiciv_mind.memory import MemoryStore
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.continuity_tools import (
    _WRITE_DEFINITION,
    _READ_DEFINITION,
    _TRAJECTORY_DEFINITION,
    _UPDATE_OUTCOME_DEFINITION,
    _make_write_handler,
    _make_read_handler,
    _make_trajectory_handler,
    _make_update_outcome_handler,
    register_continuity_tools,
)


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_write_definition_has_required_keys():
    """evolution_log_write definition must have name, description, input_schema."""
    assert _WRITE_DEFINITION["name"] == "evolution_log_write"
    assert "description" in _WRITE_DEFINITION
    assert len(_WRITE_DEFINITION["description"]) > 10
    schema = _WRITE_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "change_type" in schema["properties"]
    assert "description" in schema["properties"]
    assert "reasoning" in schema["properties"]
    assert set(schema["required"]) == {"change_type", "description", "reasoning"}


def test_read_definition_has_required_keys():
    """evolution_log_read definition must have name, description, input_schema."""
    assert _READ_DEFINITION["name"] == "evolution_log_read"
    assert "description" in _READ_DEFINITION
    schema = _READ_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "change_type" in schema["properties"]
    assert "limit" in schema["properties"]


def test_trajectory_definition_has_required_keys():
    """evolution_trajectory definition must have name, description, input_schema."""
    assert _TRAJECTORY_DEFINITION["name"] == "evolution_trajectory"
    assert "description" in _TRAJECTORY_DEFINITION
    schema = _TRAJECTORY_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "limit" in schema["properties"]


def test_update_outcome_definition_has_required_keys():
    """evolution_update_outcome definition must have name, description, input_schema with required."""
    assert _UPDATE_OUTCOME_DEFINITION["name"] == "evolution_update_outcome"
    assert "description" in _UPDATE_OUTCOME_DEFINITION
    schema = _UPDATE_OUTCOME_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "evolution_id" in schema["properties"]
    assert "outcome" in schema["properties"]
    assert set(schema["required"]) == {"evolution_id", "outcome"}


# ---------------------------------------------------------------------------
# evolution_log_write handler tests
# ---------------------------------------------------------------------------


def test_write_handler_logs_evolution(memory_store):
    """evolution_log_write should record an entry and return confirmation."""
    handler = _make_write_handler(memory_store, agent_id="primary")
    result = handler({
        "change_type": "skill_added",
        "description": "Added web search capability",
        "reasoning": "Need to research external topics autonomously",
    })
    assert "Evolution logged" in result
    assert "skill_added" in result
    assert "Added web search capability" in result


def test_write_handler_missing_required_fields(memory_store):
    """evolution_log_write should error when required fields are missing."""
    handler = _make_write_handler(memory_store, agent_id="primary")
    result = handler({
        "change_type": "skill_added",
        # missing description and reasoning
    })
    assert "ERROR" in result
    assert "required" in result


def test_write_handler_with_optional_fields(memory_store):
    """evolution_log_write should accept optional before/after/outcome/tags."""
    handler = _make_write_handler(memory_store, agent_id="primary")
    result = handler({
        "change_type": "behavioral_shift",
        "description": "Switched from eager to lazy evaluation",
        "reasoning": "Reduce context window burn",
        "before_state": "Eager: evaluate all branches",
        "after_state": "Lazy: evaluate on demand",
        "outcome": "positive",
        "tags": "optimization, context-management",
    })
    assert "Evolution logged" in result
    assert "behavioral_shift" in result


# ---------------------------------------------------------------------------
# evolution_log_read handler tests
# ---------------------------------------------------------------------------


def test_read_handler_empty_log(memory_store):
    """evolution_log_read should return 'no entries' when log is empty."""
    handler = _make_read_handler(memory_store, agent_id="primary")
    result = handler({})
    assert "No evolution entries found" in result


def test_read_handler_returns_entries(memory_store):
    """evolution_log_read should format and return logged entries."""
    # Write some entries first
    memory_store.log_evolution(
        agent_id="primary",
        change_type="tool_created",
        description="Created web_fetch tool",
        reasoning="Need HTTP fetching for research",
    )
    memory_store.log_evolution(
        agent_id="primary",
        change_type="insight_crystallized",
        description="Memory is architecture, not add-on",
        reasoning="Repeated observation across sessions",
    )

    handler = _make_read_handler(memory_store, agent_id="primary")
    result = handler({})
    assert "Evolution Log" in result
    assert "2 entries" in result
    assert "tool_created" in result
    assert "insight_crystallized" in result


def test_read_handler_respects_limit(memory_store):
    """evolution_log_read should respect the limit parameter."""
    for i in range(5):
        memory_store.log_evolution(
            agent_id="primary",
            change_type="skill_added",
            description=f"Skill {i}",
            reasoning=f"Reason {i}",
        )

    handler = _make_read_handler(memory_store, agent_id="primary")
    result = handler({"limit": 2})
    assert "2 entries" in result


def test_read_handler_filters_by_change_type(memory_store):
    """evolution_log_read should filter by change_type when provided."""
    memory_store.log_evolution(
        agent_id="primary", change_type="skill_added",
        description="Skill A", reasoning="Reason A",
    )
    memory_store.log_evolution(
        agent_id="primary", change_type="behavioral_shift",
        description="Shift B", reasoning="Reason B",
    )

    handler = _make_read_handler(memory_store, agent_id="primary")
    result = handler({"change_type": "skill_added"})
    assert "1 entries" in result
    assert "Skill A" in result
    assert "Shift B" not in result


# ---------------------------------------------------------------------------
# evolution_trajectory handler tests
# ---------------------------------------------------------------------------


def test_trajectory_handler_empty(memory_store):
    """evolution_trajectory should return fallback when no entries exist."""
    handler = _make_trajectory_handler(memory_store, agent_id="primary")
    result = handler({})
    assert "No evolution entries yet" in result


def test_trajectory_handler_generates_summary(memory_store):
    """evolution_trajectory should synthesize a growth direction summary."""
    memory_store.log_evolution(
        agent_id="primary", change_type="skill_added",
        description="Added memory tools", reasoning="Core capability",
        outcome="positive",
    )
    memory_store.log_evolution(
        agent_id="primary", change_type="architecture_change",
        description="Switched to FTS5", reasoning="Better search",
        outcome="positive",
    )

    handler = _make_trajectory_handler(memory_store, agent_id="primary")
    result = handler({})
    assert "Evolution Trajectory" in result
    assert "Growth direction" in result
    assert "2 changes tracked" in result
    assert "2 positive" in result


# ---------------------------------------------------------------------------
# evolution_update_outcome handler tests
# ---------------------------------------------------------------------------


def test_update_outcome_handler_success(memory_store):
    """evolution_update_outcome should update an existing entry's outcome."""
    eid = memory_store.log_evolution(
        agent_id="primary", change_type="tool_created",
        description="Test tool", reasoning="Testing",
        outcome="pending",
    )

    handler = _make_update_outcome_handler(memory_store)
    result = handler({"evolution_id": eid, "outcome": "positive"})
    assert "updated to: positive" in result

    # Verify in DB
    entries = memory_store.get_evolution_log(agent_id="primary")
    assert entries[0]["outcome"] == "positive"


def test_update_outcome_handler_missing_id(memory_store):
    """evolution_update_outcome should error when evolution_id is missing."""
    handler = _make_update_outcome_handler(memory_store)
    result = handler({"outcome": "positive"})
    assert "ERROR" in result
    assert "evolution_id is required" in result


def test_update_outcome_handler_invalid_outcome(memory_store):
    """evolution_update_outcome should reject invalid outcome values."""
    handler = _make_update_outcome_handler(memory_store)
    result = handler({"evolution_id": "some-id", "outcome": "excellent"})
    assert "ERROR" in result
    assert "must be positive, negative, neutral, or pending" in result


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_continuity_tools_adds_all_four(memory_store):
    """register_continuity_tools should register all 4 evolution tools."""
    registry = ToolRegistry()
    register_continuity_tools(registry, memory_store, agent_id="primary")
    names = registry.names()
    assert "evolution_log_write" in names
    assert "evolution_log_read" in names
    assert "evolution_trajectory" in names
    assert "evolution_update_outcome" in names


def test_continuity_tools_read_only_flags(memory_store):
    """Read/trajectory should be read-only; write/update should not."""
    registry = ToolRegistry()
    register_continuity_tools(registry, memory_store, agent_id="primary")
    assert registry.is_read_only("evolution_log_read") is True
    assert registry.is_read_only("evolution_trajectory") is True
    assert registry.is_read_only("evolution_log_write") is False
    assert registry.is_read_only("evolution_update_outcome") is False


def test_continuity_tool_definitions_in_registry(memory_store):
    """All continuity tools in registry should have valid Anthropic definitions."""
    registry = ToolRegistry()
    register_continuity_tools(registry, memory_store, agent_id="primary")
    tools = registry.build_anthropic_tools()
    for tool_def in tools:
        assert "name" in tool_def
        assert "description" in tool_def
        assert "input_schema" in tool_def
        assert tool_def["input_schema"]["type"] == "object"
        assert "properties" in tool_def["input_schema"]
