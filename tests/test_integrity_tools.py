"""
Tests for aiciv_mind.tools.integrity_tools — Memory integrity self-check.
Also tests aiciv_mind.tools.pattern_tools — Loop 1 pattern scanning.

Covers: tool definitions, memory_selfcheck on empty/populated store,
loop1_pattern_scan handler basics, and registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_integrity_tools.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from aiciv_mind.memory import Memory, MemoryStore
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.integrity_tools import (
    _SELFCHECK_DEFINITION,
    _make_selfcheck_handler,
    register_integrity_tools,
)
from aiciv_mind.tools.pattern_tools import (
    _SCAN_DEFINITION,
    _make_scan_handler,
    register_pattern_tools,
)


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_selfcheck_definition_has_required_keys():
    """memory_selfcheck definition must have name, description, input_schema."""
    assert _SELFCHECK_DEFINITION["name"] == "memory_selfcheck"
    assert "description" in _SELFCHECK_DEFINITION
    assert len(_SELFCHECK_DEFINITION["description"]) > 10
    schema = _SELFCHECK_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "verbose" in schema["properties"]


def test_scan_definition_has_required_keys():
    """loop1_pattern_scan definition must have name, description, input_schema."""
    assert _SCAN_DEFINITION["name"] == "loop1_pattern_scan"
    assert "description" in _SCAN_DEFINITION
    schema = _SCAN_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "threshold" in schema["properties"]
    assert "lookback" in schema["properties"]


# ---------------------------------------------------------------------------
# memory_selfcheck handler tests (real MemoryStore with :memory:)
# ---------------------------------------------------------------------------


def test_selfcheck_empty_store_returns_clean(memory_store):
    """An empty MemoryStore should produce all-PASS results."""
    handler = _make_selfcheck_handler(memory_store)
    result = handler({})
    assert "Memory Integrity Report" in result
    assert "PASS Round-trip" in result
    assert "PASS FTS5 sync" in result
    assert "FAIL" not in result


def test_selfcheck_verbose_mode(memory_store):
    """Verbose output should include 'Verbose details' section."""
    handler = _make_selfcheck_handler(memory_store)
    result = handler({"verbose": True})
    assert "Verbose details" in result
    assert "Memories:" in result
    assert "Tags:" in result


def test_selfcheck_with_populated_store(memory_store):
    """Selfcheck should pass with real memories in the store."""
    for i in range(3):
        mem = Memory(
            agent_id="test-agent",
            title=f"Test memory {i}",
            content=f"Content for memory {i}",
            domain="testing",
            memory_type="observation",
            tags=["test", f"tag-{i}"],
        )
        memory_store.store(mem)

    handler = _make_selfcheck_handler(memory_store)
    result = handler({})
    assert "Memory Integrity Report" in result
    assert "PASS Round-trip" in result
    assert "PASS FTS5 sync" in result
    assert "PASS Tag integrity" in result


def test_selfcheck_cleans_up_probe(memory_store):
    """The test probe memory should be deleted after self-check."""
    handler = _make_selfcheck_handler(memory_store)
    handler({})

    # Verify no selfcheck probe memories remain
    count = memory_store._conn.execute(
        "SELECT COUNT(*) FROM memories WHERE agent_id = '__selfcheck__'"
    ).fetchone()[0]
    assert count == 0


def test_selfcheck_report_has_overall_summary(memory_store):
    """Report should end with an Overall: line summarizing pass/fail."""
    handler = _make_selfcheck_handler(memory_store)
    result = handler({})
    assert "Overall:" in result
    assert "PASS" in result


# ---------------------------------------------------------------------------
# loop1_pattern_scan handler tests
# ---------------------------------------------------------------------------


def test_scan_no_loop1_memories(memory_store):
    """Should report 'no Loop 1 memories' when store is empty."""
    handler = _make_scan_handler(memory_store, agent_id="primary")
    result = handler({})
    assert "No Loop 1 memories found" in result


def test_scan_with_loop1_errors_below_threshold(memory_store):
    """Errors below threshold should not produce pattern suggestions."""
    # Add 2 error memories with loop-1 tag (below default threshold of 3)
    for i in range(2):
        mem = Memory(
            agent_id="primary",
            title=f"bash error {i}",
            content=f"Errors: bash command failed\nDetails: exit code 1",
            domain="general",
            memory_type="error",
            tags=["loop-1", "task-learning", "bash"],
        )
        memory_store.store(mem)

    handler = _make_scan_handler(memory_store, agent_id="primary")
    result = handler({})
    assert "No repeated patterns detected" in result


def test_scan_with_loop1_errors_at_threshold(memory_store):
    """Errors at threshold should produce pattern suggestions."""
    # Add 3 error memories with loop-1 tag (meets default threshold of 3)
    for i in range(3):
        mem = Memory(
            agent_id="primary",
            title=f"bash error {i}",
            content=f"Errors: bash command failed with exit code 1\nDetails: something broke",
            domain="general",
            memory_type="error",
            tags=["loop-1", "task-learning", "bash"],
        )
        memory_store.store(mem)

    handler = _make_scan_handler(memory_store, agent_id="primary")
    result = handler({})
    assert "Pattern Detected" in result
    assert "bash" in result
    assert "3 occurrences" in result


def test_scan_respects_custom_threshold(memory_store):
    """Custom threshold should be applied."""
    for i in range(2):
        mem = Memory(
            agent_id="primary",
            title=f"error {i}",
            content="Errors: repeated issue detected",
            domain="general",
            memory_type="error",
            tags=["loop-1", "task-learning", "web_fetch"],
        )
        memory_store.store(mem)

    handler = _make_scan_handler(memory_store, agent_id="primary")
    # With threshold=2, the 2 errors should trigger a pattern
    result = handler({"threshold": 2})
    assert "Pattern Detected" in result
    assert "web_fetch" in result


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_integrity_tools(memory_store):
    """register_integrity_tools should add memory_selfcheck to registry."""
    registry = ToolRegistry()
    register_integrity_tools(registry, memory_store)
    names = registry.names()
    assert "memory_selfcheck" in names


def test_register_pattern_tools(memory_store):
    """register_pattern_tools should add loop1_pattern_scan to registry."""
    registry = ToolRegistry()
    register_pattern_tools(registry, memory_store, agent_id="primary")
    names = registry.names()
    assert "loop1_pattern_scan" in names


def test_integrity_tool_is_read_only(memory_store):
    """memory_selfcheck should be marked read-only."""
    registry = ToolRegistry()
    register_integrity_tools(registry, memory_store)
    assert registry.is_read_only("memory_selfcheck") is True


def test_pattern_tool_is_read_only(memory_store):
    """loop1_pattern_scan should be marked read-only."""
    registry = ToolRegistry()
    register_pattern_tools(registry, memory_store, agent_id="primary")
    assert registry.is_read_only("loop1_pattern_scan") is True
