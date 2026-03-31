"""
Tests for tools/nightly_training.py — nightly pattern extraction.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_nightly_training.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add tools to path for import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from aiciv_mind.memory import MemoryStore

# Import after path setup
from nightly_training import extract_patterns, get_recent_sessions, run_training


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_nightly_training_runs_without_error(memory_store: MemoryStore) -> None:
    """run_training() against an empty DB should not crash."""
    result = run_training(memory_store, dry_run=True)
    assert result["sessions_analyzed"] == 0
    assert result["total_turns"] == 0
    assert result["dry_run"] is True


def test_nightly_training_writes_memory(memory_store: MemoryStore) -> None:
    """run_training() should write a training memory when sessions exist."""
    # Create a fake completed session
    sid = memory_store.start_session("primary", session_id="test-sess-1")
    memory_store.record_turn(sid, topic="hub posting")
    memory_store.record_turn(sid, topic="memory hygiene")
    memory_store.record_turn(sid, topic="hub posting")
    memory_store.end_session(sid, "Test session completed")

    # Run training (not dry-run, but we don't want to write to disk)
    # Use monkeypatch-free approach: just run and check memory was written
    result = run_training(memory_store, dry_run=False)

    assert result["sessions_analyzed"] == 1
    assert result["total_turns"] == 3

    # Verify a learning memory was written
    memories = memory_store.search("nightly training")
    assert len(memories) >= 1
    assert memories[0]["memory_type"] == "learning"
    assert "training" in memories[0]["domain"]


def test_extract_patterns_empty() -> None:
    """extract_patterns() handles empty session list."""
    patterns = extract_patterns([])
    assert patterns["session_count"] == 0
    assert patterns["total_turns"] == 0
    assert patterns["avg_turns_per_session"] == 0
    assert patterns["top_topics"] == []


def test_extract_patterns_with_data() -> None:
    """extract_patterns() correctly aggregates session data."""
    sessions = [
        {
            "session_id": "s1",
            "agent_id": "primary",
            "turn_count": 10,
            "topics": json.dumps(["hub", "memory", "hub"]),
        },
        {
            "session_id": "s2",
            "agent_id": "primary",
            "turn_count": 6,
            "topics": json.dumps(["skills", "hub"]),
        },
    ]
    patterns = extract_patterns(sessions)
    assert patterns["session_count"] == 2
    assert patterns["total_turns"] == 16
    assert patterns["avg_turns_per_session"] == 8.0
    # hub should be most frequent (3 occurrences)
    assert patterns["top_topics"][0][0] == "hub"
    assert patterns["top_topics"][0][1] == 3


def test_get_recent_sessions_empty(memory_store: MemoryStore) -> None:
    """get_recent_sessions() returns empty list when no sessions exist."""
    sessions = get_recent_sessions(memory_store)
    assert sessions == []


def test_get_recent_sessions_excludes_open(memory_store: MemoryStore) -> None:
    """get_recent_sessions() only returns completed sessions."""
    # Open session (no end_session call)
    memory_store.start_session("primary", session_id="open-sess")
    # Completed session
    sid = memory_store.start_session("primary", session_id="done-sess")
    memory_store.end_session(sid, "Completed")

    sessions = get_recent_sessions(memory_store)
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "done-sess"
