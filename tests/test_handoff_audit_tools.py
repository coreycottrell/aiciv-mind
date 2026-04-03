"""
Tests for aiciv_mind.tools.handoff_audit_tools.

Covers: 7 audit checks, trust score, tool registration, error handling.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.handoff_audit_tools import (
    _HANDOFF_AUDIT_DEFINITION,
    _check_context_completeness,
    _check_git_state_reconciliation,
    _check_handoff_exists,
    _check_prior_handoff_contradiction,
    _check_session_overlap,
    _check_temporal_staleness,
    _check_tool_existence,
    _compute_trust_score,
    _hours_since,
    _parse_handoff_content,
    handoff_audit,
    register_handoff_audit_tools,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_memory_store():
    """Minimal in-memory SQLite memory store."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            memory_type TEXT,
            content TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE session_journal (
            id TEXT PRIMARY KEY,
            start_time TEXT,
            end_time TEXT
        )
    """)
    store = MagicMock()
    store._conn = conn
    return store


@pytest.fixture
def registry():
    return ToolRegistry()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def dt(hours_ago: int) -> str:
    """ISO timestamp N hours in the past."""
    past = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return past.isoformat()


def insert_handoff(conn, handoff_id, content_json, created_hours_ago=1):
    """Insert a handoff memory row."""
    conn.execute(
        "INSERT INTO memories (id, memory_type, content, created_at) VALUES (?, ?, ?, ?)",
        (handoff_id, "handoff", json.dumps(content_json), dt(created_hours_ago)),
    )


# ---------------------------------------------------------------------------
# Test: _hours_since
# ---------------------------------------------------------------------------

class TestHoursSince:
    def test_parses_iso_with_z(self):
        past = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result = _hours_since(past)
        assert result is not None
        assert 0 <= result < 0.01  # essentially now

    def test_parses_iso_with_offset(self):
        past = datetime.now(timezone.utc).isoformat()
        result = _hours_since(past)
        assert result is not None
        assert 0 <= result < 0.01

    def test_invalid_returns_none(self):
        assert _hours_since("not-a-date") is None
        assert _hours_since("") is None

    def test_two_hours_ago(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        result = _hours_since(past)
        assert result is not None
        assert 1.9 < result < 2.1


# ---------------------------------------------------------------------------
# Test: _parse_handoff_content
# ---------------------------------------------------------------------------

class TestParseHandoffContent:
    def test_parses_valid_json_dict(self):
        raw = json.dumps({"current_work": "fixing bug", "next_steps": ["test"]})
        result = _parse_handoff_content(raw)
        assert result == {"current_work": "fixing bug", "next_steps": ["test"]}

    def test_parses_valid_json_string(self):
        raw = json.dumps("just a string summary")
        result = _parse_handoff_content(raw)
        assert result == {"summary": "just a string summary"}

    def test_falls_back_to_raw_text(self):
        raw = "This is unstructured handoff text."
        result = _parse_handoff_content(raw)
        assert result == {"summary": raw}

    def test_handles_malformed_json(self):
        raw = '{"broken": json here}'
        result = _parse_handoff_content(raw)
        assert result["summary"] == raw


# ---------------------------------------------------------------------------
# Test: _check_handoff_exists
# ---------------------------------------------------------------------------

class TestCheckHandoffExists:
    def test_returns_fail_when_no_handoffs(self, mock_memory_store):
        result = _check_handoff_exists(mock_memory_store, {})
        assert result["status"] == "FAIL"
        assert "handoff" in result["summary"].lower()
        assert any(f["severity"] == "error" for f in result["findings"])

    def test_returns_pass_when_handoff_exists(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-1", {"current_work": "test"}, 1)
        result = _check_handoff_exists(mock_memory_store, {})
        assert result["status"] == "PASS"
        assert result["handoff_id"] == "handoff-1"

    def test_warns_when_handoff_too_old(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-old", {"current_work": "test"}, 30)
        result = _check_handoff_exists(mock_memory_store, {})
        assert result["status"] == "PASS"
        assert any(f["severity"] == "warning" for f in result["findings"])

    def test_finds_specific_handoff_id(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-1", {"current_work": "one"}, 1)
        insert_handoff(mock_memory_store._conn, "handoff-2", {"current_work": "two"}, 2)
        result = _check_handoff_exists(mock_memory_store, {"handoff_id": "handoff-2"})
        assert result["status"] == "PASS"
        assert result["handoff_id"] == "handoff-2"

    def test_returns_fail_for_unknown_handoff_id(self, mock_memory_store):
        result = _check_handoff_exists(mock_memory_store, {"handoff_id": "nonexistent"})
        assert result["status"] == "FAIL"


# ---------------------------------------------------------------------------
# Test: _check_context_completeness
# ---------------------------------------------------------------------------

class TestCheckContextCompleteness:
    def test_returns_fail_when_required_fields_missing(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-1", {"summary": "raw text only"}, 1)
        result = _check_context_completeness(mock_memory_store, None)
        assert result["status"] == "FAIL"
        assert "current_work" in result["missing_required"]
        assert "next_steps" in result["missing_required"]

    def test_returns_pass_when_all_required_fields_present(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-1", {
            "current_work": "working on X",
            "next_steps": ["finish Y"],
            "tools_used": ["memory_search"],
            "open_issues": [],
            "session_id": "session-123",
        }, 1)
        result = _check_context_completeness(mock_memory_store, None)
        assert result["status"] == "PASS"

    def test_returns_warning_when_recommended_fields_missing(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-1", {
            "current_work": "working",
            "next_steps": ["done"],
        }, 1)
        result = _check_context_completeness(mock_memory_store, None)
        assert result["status"] == "WARNING"
        assert len(result["missing_recommended"]) > 0

    def test_returns_skip_when_no_handoff(self, mock_memory_store):
        result = _check_context_completeness(mock_memory_store, None)
        assert result["status"] == "SKIP"


# ---------------------------------------------------------------------------
# Test: _check_temporal_staleness
# ---------------------------------------------------------------------------

class TestCheckTemporalStaleness:
    def test_returns_fail_when_stale_with_unresolved_items(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-stale", {
            "current_work": "X",
            "next_steps": ["Y"],
            "unresolved": ["issue A", "issue B"],
        }, 72)
        result = _check_temporal_staleness(mock_memory_store, None)
        assert result["status"] == "FAIL"
        assert result["hours_old"] > 48
        assert result["unresolved_count"] == 2

    def test_returns_warning_when_just_over_24h(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-25h", {"current_work": "X", "next_steps": ["Y"]}, 26)
        result = _check_temporal_staleness(mock_memory_store, None)
        assert result["status"] == "WARNING"

    def test_returns_pass_when_fresh(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-fresh", {"current_work": "X", "next_steps": ["Y"]}, 2)
        result = _check_temporal_staleness(mock_memory_store, None)
        assert result["status"] == "PASS"

    def test_returns_skip_when_no_handoff(self, mock_memory_store):
        result = _check_temporal_staleness(mock_memory_store, None)
        assert result["status"] == "SKIP"


# ---------------------------------------------------------------------------
# Test: _check_prior_handoff_contradiction
# ---------------------------------------------------------------------------

class TestCheckPriorHandoffContradiction:
    def test_returns_info_when_no_prior_handoff(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-only", {"current_work": "X"}, 1)
        result = _check_prior_handoff_contradiction(mock_memory_store, None)
        assert result["status"] == "INFO"

    def test_returns_pass_when_no_contradiction(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "prior", {
            "current_work": "working on X", "status": "in progress",
            "next_steps": ["finish Y"]
        }, 4)
        insert_handoff(mock_memory_store._conn, "current", {
            "current_work": "working on X", "status": "in progress",
            "next_steps": ["finish Y"]
        }, 1)
        result = _check_prior_handoff_contradiction(mock_memory_store, None)
        assert result["status"] == "PASS"

    def test_returns_fail_when_status_flips_from_done(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "prior", {
            "current_work": "feature done", "status": "done", "next_steps": []
        }, 4)
        insert_handoff(mock_memory_store._conn, "current", {
            "current_work": "regression found", "status": "in progress", "next_steps": ["fix"]
        }, 1)
        result = _check_prior_handoff_contradiction(mock_memory_store, None)
        assert result["status"] == "FAIL"
        assert any("done" in c.lower() for c in result.get("contradictions", []))

    def test_returns_skip_when_no_handoff(self, mock_memory_store):
        result = _check_prior_handoff_contradiction(mock_memory_store, None)
        assert result["status"] == "SKIP"


# ---------------------------------------------------------------------------
# Test: _check_tool_existence
# ---------------------------------------------------------------------------

class TestCheckToolExistence:
    def test_returns_pass_when_referenced_tools_exist(self, mock_memory_store, registry):
        # Use registry.register() which is the correct API
        registry.register("read_file", {"name": "read_file"}, lambda: None)
        registry.register("write_file", {"name": "write_file"}, lambda: None)
        insert_handoff(mock_memory_store._conn, "handoff-1", {
            "current_work": "X",
            "next_steps": ["Y"],
            "tools_used": ["read_file", "write_file"],
        }, 1)
        result = _check_tool_existence(mock_memory_store, registry, None)
        assert result["status"] == "PASS"
        assert result["missing_tools"] == []

    def test_returns_fail_when_tools_missing(self, mock_memory_store, registry):
        registry.register("read_file", {"name": "read_file"}, lambda: None)
        insert_handoff(mock_memory_store._conn, "handoff-1", {
            "current_work": "X",
            "next_steps": ["Y"],
            "tools_used": ["read_file", "nonexistent_tool_xyz"],
        }, 1)
        result = _check_tool_existence(mock_memory_store, registry, None)
        assert result["status"] == "FAIL"
        assert "nonexistent_tool_xyz" in result["missing_tools"]

    def test_returns_info_when_no_tools_referenced(self, mock_memory_store, registry):
        insert_handoff(mock_memory_store._conn, "handoff-1", {
            "current_work": "X", "next_steps": ["Y"],
        }, 1)
        result = _check_tool_existence(mock_memory_store, registry, None)
        assert result["status"] == "INFO"

    def test_returns_skip_when_no_handoff(self, mock_memory_store, registry):
        result = _check_tool_existence(mock_memory_store, registry, None)
        assert result["status"] == "SKIP"


# ---------------------------------------------------------------------------
# Test: _check_git_state_reconciliation
# ---------------------------------------------------------------------------

class TestCheckGitStateReconciliation:
    @patch("aiciv_mind.tools.handoff_audit_tools._git_commits_since")
    @patch("aiciv_mind.tools.handoff_audit_tools._git_changed_files_since")
    def test_returns_pass_when_no_git_changes(
        self, mock_changed, mock_commits, mock_memory_store
    ):
        mock_commits.return_value = ""
        mock_changed.return_value = []
        insert_handoff(mock_memory_store._conn, "handoff-1", {"current_work": "X"}, 1)
        result = _check_git_state_reconciliation(mock_memory_store, ".", None)
        assert result["status"] == "PASS"

    @patch("aiciv_mind.tools.handoff_audit_tools._git_commits_since")
    @patch("aiciv_mind.tools.handoff_audit_tools._git_changed_files_since")
    def test_returns_warning_when_commits_after_handoff(
        self, mock_changed, mock_commits, mock_memory_store
    ):
        mock_commits.return_value = "abc123 fix bug\ndef456 add feature"
        mock_changed.return_value = ["src/main.py", "tests/test_main.py"]
        insert_handoff(mock_memory_store._conn, "handoff-1", {"current_work": "X"}, 1)
        result = _check_git_state_reconciliation(mock_memory_store, ".", None)
        assert result["status"] == "WARNING"
        assert "src/main.py" in result["changed_files"]
        assert any("warning" in f["severity"] for f in result["findings"])

    def test_returns_skip_when_no_handoff(self, mock_memory_store):
        result = _check_git_state_reconciliation(mock_memory_store, ".", None)
        assert result["status"] == "SKIP"


# ---------------------------------------------------------------------------
# Test: _check_session_overlap
# ---------------------------------------------------------------------------

class TestCheckSessionOverlap:
    def test_returns_pass_when_no_overlap(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-1", {"current_work": "X"}, 4)
        result = _check_session_overlap(mock_memory_store, None)
        assert result["status"] == "PASS"

    def test_returns_warning_when_sessions_after_handoff(self, mock_memory_store):
        insert_handoff(mock_memory_store._conn, "handoff-1", {"current_work": "X"}, 4)
        mock_memory_store._conn.execute(
            "INSERT INTO session_journal (id, start_time, end_time) VALUES (?, ?, ?)",
            ("session-1", dt(1), None),
        )
        result = _check_session_overlap(mock_memory_store, None)
        assert result["status"] == "WARNING"
        assert len(result.get("overlapping_sessions", [])) == 1

    def test_returns_skip_when_no_handoff(self, mock_memory_store):
        result = _check_session_overlap(mock_memory_store, None)
        assert result["status"] == "SKIP"


# ---------------------------------------------------------------------------
# Test: _compute_trust_score
# ---------------------------------------------------------------------------

class TestComputeTrustScore:
    def test_all_pass_returns_1_0(self):
        results = [{"status": "PASS"}, {"status": "PASS"}, {"status": "PASS"}]
        trust = _compute_trust_score(results)
        assert trust["score"] == 1.0
        assert trust["grade"] == "A"

    def test_one_fail_drags_score_down(self):
        results = [{"status": "PASS"}, {"status": "FAIL"}, {"status": "PASS"}]
        trust = _compute_trust_score(results)
        assert trust["score"] == pytest.approx(2 / 3, abs=0.01)
        assert trust["grade"] == "C"

    def test_error_sets_score_zero(self):
        results = [{"status": "PASS"}, {"status": "ERROR"}, {"status": "PASS"}]
        trust = _compute_trust_score(results)
        assert trust["score"] == 0.0
        assert trust["grade"] == "F"

    def test_empty_results_returns_1_0(self):
        trust = _compute_trust_score([])
        assert trust["score"] == 1.0
        assert trust["label"] == "NO_CHECKS"

    def test_grades(self):
        assert _compute_trust_score([{"status": "PASS"}])["grade"] == "A"
        assert _compute_trust_score([{"status": "WARNING"}])["grade"] == "C"
        assert _compute_trust_score([{"status": "FAIL"}])["grade"] == "F"


# ---------------------------------------------------------------------------
# Test: handoff_audit — integration
# ---------------------------------------------------------------------------

class TestHandoffAudit:
    def test_runs_all_seven_checks(self, mock_memory_store, registry):
        insert_handoff(mock_memory_store._conn, "handoff-1", {
            "current_work": "X",
            "next_steps": ["Y"],
            "tools_used": [],
        }, 1)
        result = handoff_audit(
            memory_store=mock_memory_store,
            tool_input={"verbose": True},
            registry=registry,
            mind_root=".",
        )
        check_names = {r["check"] for r in result["check_results"]}
        expected = {
            "handoff_exists",
            "git_state_reconciliation",
            "tool_existence",
            "prior_handoff_contradiction",
            "temporal_staleness",
            "context_completeness",
            "session_overlap",
        }
        assert check_names == expected

    def test_non_verbose_excludes_passes(self, mock_memory_store, registry):
        insert_handoff(mock_memory_store._conn, "handoff-1", {
            "current_work": "X",
            "next_steps": ["Y"],
            "tools_used": [],
        }, 1)
        result = handoff_audit(
            memory_store=mock_memory_store,
            tool_input={"verbose": False},
            registry=registry,
            mind_root=".",
        )
        for r in result["check_results"]:
            if r["check"] != "handoff_exists":
                assert r["status"] not in ("PASS", "INFO", "SKIP"), \
                    f"Unexpected {r['status']} for {r['check']}"

    def test_specific_handoff_id(self, mock_memory_store, registry):
        insert_handoff(mock_memory_store._conn, "handoff-1", {
            "current_work": "X", "next_steps": ["Y"]
        }, 1)
        insert_handoff(mock_memory_store._conn, "handoff-2", {
            "current_work": "Z", "next_steps": ["W"]
        }, 2)
        result = handoff_audit(
            memory_store=mock_memory_store,
            tool_input={"handoff_id": "handoff-2"},
            registry=registry,
            mind_root=".",
        )
        exists = next(r for r in result["check_results"] if r["check"] == "handoff_exists")
        assert exists["handoff_id"] == "handoff-2"

    def test_returns_trust_score_and_recommendations(self, mock_memory_store, registry):
        insert_handoff(mock_memory_store._conn, "handoff-1", {
            "summary": "raw text",
            "tools_used": ["fake_tool"],
        }, 1)
        result = handoff_audit(
            memory_store=mock_memory_store,
            tool_input={"verbose": True},
            registry=registry,
            mind_root=".",
        )
        assert "trust_score" in result
        assert "score" in result["trust_score"]
        assert "recommendations" in result

    def test_tool_version_in_output(self, mock_memory_store, registry):
        insert_handoff(mock_memory_store._conn, "handoff-1", {"current_work": "X", "next_steps": ["Y"]}, 1)
        result = handoff_audit(memory_store=mock_memory_store, registry=registry)
        assert result["tool_version"] == "1.0.0"


# ---------------------------------------------------------------------------
# Test: Tool registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_registers_handoff_audit_tool(self, registry, mock_memory_store):
        register_handoff_audit_tools(registry, memory_store=mock_memory_store)
        assert "handoff_audit" in registry.names()
        tool_def = registry._tools["handoff_audit"]
        assert tool_def["name"] == "handoff_audit"
        assert "description" in tool_def

    def test_registered_tool_is_callable(self, registry, mock_memory_store):
        register_handoff_audit_tools(registry, memory_store=mock_memory_store)
        handler = registry._handlers["handoff_audit"]
        result = handler({"verbose": True})
        assert "trust_score" in result
        assert "check_results" in result

    def test_tool_definition_has_required_keys(self, registry, mock_memory_store):
        register_handoff_audit_tools(registry, memory_store=mock_memory_store)
        tool_def = registry._tools["handoff_audit"]
        assert "name" in tool_def
        assert "description" in tool_def
        assert "input_schema" in tool_def
