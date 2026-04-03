"""Tests for persistent JSONL audit logging in HookRunner."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiciv_mind.tools.hooks import HookRunner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_log(tmp_path):
    """Return a path to a temporary audit log file."""
    return tmp_path / "data" / "tool_audit.jsonl"


@pytest.fixture
def hooks_with_audit(audit_log):
    """HookRunner with JSONL audit logging enabled."""
    return HookRunner(log_all=True, audit_log_path=str(audit_log))


# ---------------------------------------------------------------------------
# Tests: audit_log_path creation
# ---------------------------------------------------------------------------


def test_audit_log_creates_parent_dirs(tmp_path):
    """Audit log creates parent directories if they don't exist."""
    deep_path = tmp_path / "a" / "b" / "c" / "audit.jsonl"
    HookRunner(audit_log_path=str(deep_path))
    assert deep_path.parent.exists()


def test_audit_log_none_by_default():
    """Without audit_log_path, no file is written."""
    h = HookRunner()
    assert h._audit_log_path is None


# ---------------------------------------------------------------------------
# Tests: pre_tool_use writes audit records
# ---------------------------------------------------------------------------


def test_pre_tool_use_writes_audit(hooks_with_audit, audit_log):
    """An allowed pre_tool_use writes a record to the JSONL audit log."""
    hooks_with_audit.pre_tool_use("memory_search", {"query": "test"})

    assert audit_log.exists()
    lines = audit_log.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "pre_tool_use"
    assert record["tool"] == "memory_search"
    assert "ts" in record


def test_blocked_tool_does_not_write_audit(tmp_path):
    """A blocked tool does NOT write a pre_tool_use audit record."""
    audit_log = tmp_path / "audit.jsonl"
    h = HookRunner(blocked_tools=["bash"], audit_log_path=str(audit_log))
    result = h.pre_tool_use("bash", {"command": "rm -rf /"})
    assert not result.allowed
    # Blocked tools short-circuit before the audit write
    if audit_log.exists():
        lines = audit_log.read_text().strip().splitlines()
        for line in lines:
            record = json.loads(line)
            assert record["event"] != "pre_tool_use"


# ---------------------------------------------------------------------------
# Tests: post_tool_use writes audit records
# ---------------------------------------------------------------------------


def test_post_tool_use_writes_audit(hooks_with_audit, audit_log):
    """post_tool_use writes a record with duration and result_len."""
    hooks_with_audit.post_tool_use(
        "memory_write",
        {"title": "test"},
        "Memory stored: abc123",
        is_error=False,
        duration_ms=42,
    )

    assert audit_log.exists()
    lines = audit_log.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "post_tool_use"
    assert record["tool"] == "memory_write"
    assert record["duration_ms"] == 42
    assert record["result_len"] == len("Memory stored: abc123")
    assert record["is_error"] is False


def test_post_tool_use_error_recorded(hooks_with_audit, audit_log):
    """Error tool results are marked as is_error in audit."""
    hooks_with_audit.post_tool_use(
        "bash", {"command": "false"}, "ERROR: exit 1", is_error=True, duration_ms=5
    )

    lines = audit_log.read_text().strip().splitlines()
    record = json.loads(lines[0])
    assert record["is_error"] is True


# ---------------------------------------------------------------------------
# Tests: round-trip (pre + post) produces two records
# ---------------------------------------------------------------------------


def test_pre_and_post_produce_two_records(hooks_with_audit, audit_log):
    """A full tool lifecycle (pre + post) produces two audit records."""
    hooks_with_audit.pre_tool_use("grep", {"query": "test"})
    hooks_with_audit.post_tool_use(
        "grep", {"query": "test"}, "found 3 matches", is_error=False, duration_ms=15
    )

    lines = audit_log.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "pre_tool_use"
    assert json.loads(lines[1])["event"] == "post_tool_use"


# ---------------------------------------------------------------------------
# Tests: audit log resilience
# ---------------------------------------------------------------------------


def test_audit_write_failure_does_not_crash(hooks_with_audit, audit_log, monkeypatch):
    """If the audit file can't be written, the tool call still succeeds."""
    # Make the path a directory so open() fails
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    audit_log.mkdir(exist_ok=True)  # audit_log is now a directory, open() will fail

    # Should not raise
    result = hooks_with_audit.pre_tool_use("bash", {"command": "ls"})
    assert result.allowed


def test_no_audit_path_still_works():
    """HookRunner without audit path works normally."""
    h = HookRunner(log_all=True)
    result = h.pre_tool_use("bash", {"command": "ls"})
    assert result.allowed
    h.post_tool_use("bash", {"command": "ls"}, "/home", is_error=False)
    assert h.stats["total_calls"] == 1
