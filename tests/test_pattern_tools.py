"""
Tests for aiciv_mind.tools.pattern_tools — loop1_pattern_scan tool.

Covers: tool definition, handler with mock memory data, threshold logic, registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_pattern_tools.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.pattern_tools import (
    _SCAN_DEFINITION,
    _make_scan_handler,
    _has_loop1_tag,
    _extract_error_line,
    register_pattern_tools,
)


# ---------------------------------------------------------------------------
# Definition tests
# ---------------------------------------------------------------------------


def test_scan_definition_name():
    assert _SCAN_DEFINITION["name"] == "loop1_pattern_scan"


def test_scan_definition_has_description():
    assert isinstance(_SCAN_DEFINITION["description"], str)
    assert len(_SCAN_DEFINITION["description"]) > 10
    assert "pattern" in _SCAN_DEFINITION["description"].lower()


def test_scan_definition_has_threshold_and_lookback():
    props = _SCAN_DEFINITION["input_schema"]["properties"]
    assert "threshold" in props
    assert "lookback" in props


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


def test_has_loop1_tag_true():
    mem = {"tags": json.dumps(["loop-1", "task-learning"])}
    assert _has_loop1_tag(mem) is True


def test_has_loop1_tag_false():
    mem = {"tags": json.dumps(["loop-2", "something"])}
    assert _has_loop1_tag(mem) is False


def test_has_loop1_tag_bad_json():
    mem = {"tags": "not-valid-json"}
    assert _has_loop1_tag(mem) is False


def test_extract_error_line_found():
    content = "Tool: bash\nErrors: Connection refused on port 8080\nResult: failed"
    line = _extract_error_line(content)
    assert line is not None
    assert "Connection refused" in line


def test_extract_error_line_none_errors():
    content = "Tool: bash\nErrors: none\nResult: ok"
    assert _extract_error_line(content) is None


def test_extract_error_line_no_errors_field():
    content = "Tool: bash\nResult: ok"
    assert _extract_error_line(content) is None


# ---------------------------------------------------------------------------
# Handler tests (with mock MemoryStore)
# ---------------------------------------------------------------------------


def _make_mock_store(errors=None, learnings=None):
    """Create a mock MemoryStore with controlled by_type returns."""
    store = MagicMock()

    def by_type_side_effect(memory_type, agent_id=None, limit=20):
        if memory_type == "error":
            return errors or []
        if memory_type == "learning":
            return learnings or []
        return []

    store.by_type = MagicMock(side_effect=by_type_side_effect)
    return store


def test_handler_no_loop1_memories():
    """Handler reports 'no Loop 1 memories' when store is empty."""
    store = _make_mock_store()
    handler = _make_scan_handler(store, "test-agent")
    result = handler({})
    assert "No Loop 1 memories" in result


def test_handler_detects_repeated_tool_errors():
    """Handler detects a pattern when the same tool fails 3+ times."""
    errors = []
    for i in range(4):
        errors.append({
            "tags": json.dumps(["loop-1", "task-learning", "bash"]),
            "content": f"Tool: bash\nErrors: Connection refused attempt {i}\nResult: failed",
        })

    store = _make_mock_store(errors=errors)
    handler = _make_scan_handler(store, "test-agent")
    result = handler({"threshold": 3})

    assert "Pattern Detected" in result
    assert "bash" in result
    assert "4 occurrences" in result or "4)" in result


def test_handler_below_threshold_no_patterns():
    """Handler reports no patterns when occurrences are below threshold."""
    errors = [
        {
            "tags": json.dumps(["loop-1", "task-learning", "bash"]),
            "content": "Tool: bash\nErrors: Connection refused\nResult: failed",
        },
    ]
    store = _make_mock_store(errors=errors)
    handler = _make_scan_handler(store, "test-agent")
    result = handler({"threshold": 3})

    assert "No repeated patterns" in result


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_pattern_tools():
    store = _make_mock_store()
    registry = ToolRegistry()
    register_pattern_tools(registry, store, agent_id="test")
    assert "loop1_pattern_scan" in registry.names()
    assert registry.is_read_only("loop1_pattern_scan")
