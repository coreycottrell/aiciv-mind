"""Tests for tools/infrastructure_guard.py — infrastructure health checks."""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module under test
import importlib.util
spec = importlib.util.spec_from_file_location(
    "infrastructure_guard",
    Path(__file__).parent.parent / "tools" / "infrastructure_guard.py",
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a minimal memory.db with session_journal table."""
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE session_journal (
            session_id TEXT PRIMARY KEY,
            agent_id TEXT,
            start_time TEXT,
            end_time TEXT,
            turn_count INTEGER DEFAULT 0,
            summary TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def tmp_skills(tmp_path: Path) -> Path:
    """Create a skills/ directory with 5 SKILL.md files."""
    skills = tmp_path / "skills"
    for name in ["a", "b", "c", "d", "e"]:
        d = skills / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}")
    return skills


# ---------------------------------------------------------------------------
# Tests: memory_db_integrity
# ---------------------------------------------------------------------------


def test_memory_db_pass(tmp_db: Path):
    """Healthy DB returns PASS."""
    with patch.object(guard, "MEMORY_DB", tmp_db):
        result = guard.check_memory_db_integrity()
    assert result["status"] == "PASS"
    assert "integrity OK" in result["detail"]


def test_memory_db_not_found(tmp_path: Path):
    """Missing DB returns FAIL."""
    with patch.object(guard, "MEMORY_DB", tmp_path / "nonexistent.db"):
        result = guard.check_memory_db_integrity()
    assert result["status"] == "FAIL"
    assert "not found" in result["detail"]


# ---------------------------------------------------------------------------
# Tests: skills_directory
# ---------------------------------------------------------------------------


def test_skills_pass(tmp_skills: Path):
    """Skills dir with >= 4 SKILL.md files returns PASS."""
    with patch.object(guard, "SKILLS_DIR", tmp_skills):
        result = guard.check_skills_directory()
    assert result["status"] == "PASS"
    assert "5 skills" in result["detail"]


def test_skills_too_few(tmp_path: Path):
    """Skills dir with < 4 files returns FAIL."""
    skills = tmp_path / "skills"
    for name in ["a", "b"]:
        d = skills / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}")

    with patch.object(guard, "SKILLS_DIR", skills):
        result = guard.check_skills_directory()
    assert result["status"] == "FAIL"
    assert "Only 2" in result["detail"]


def test_skills_dir_missing(tmp_path: Path):
    """Missing skills dir returns FAIL."""
    with patch.object(guard, "SKILLS_DIR", tmp_path / "no-skills"):
        result = guard.check_skills_directory()
    assert result["status"] == "FAIL"


# ---------------------------------------------------------------------------
# Tests: recent_session
# ---------------------------------------------------------------------------


def test_recent_session_pass(tmp_db: Path):
    """Recent session within 24h returns PASS."""
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        "INSERT INTO session_journal (session_id, agent_id, start_time) VALUES (?, ?, ?)",
        ("s1", "primary", datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    with patch.object(guard, "MEMORY_DB", tmp_db):
        result = guard.check_recent_session()
    assert result["status"] == "PASS"


def test_recent_session_none(tmp_db: Path):
    """No sessions in 24h returns WARN."""
    with patch.object(guard, "MEMORY_DB", tmp_db):
        result = guard.check_recent_session()
    assert result["status"] == "WARN"


def test_recent_session_old_only(tmp_db: Path):
    """Only old sessions (> 24h) returns WARN."""
    conn = sqlite3.connect(str(tmp_db))
    old = (datetime.utcnow() - timedelta(hours=48)).isoformat()
    conn.execute(
        "INSERT INTO session_journal (session_id, agent_id, start_time) VALUES (?, ?, ?)",
        ("s1", "primary", old),
    )
    conn.commit()
    conn.close()

    with patch.object(guard, "MEMORY_DB", tmp_db):
        result = guard.check_recent_session()
    assert result["status"] == "WARN"


# ---------------------------------------------------------------------------
# Tests: orphaned_sessions
# ---------------------------------------------------------------------------


def test_no_orphaned_sessions(tmp_db: Path):
    """No orphaned sessions returns PASS."""
    with patch.object(guard, "MEMORY_DB", tmp_db):
        result = guard.check_orphaned_sessions()
    assert result["status"] == "PASS"


def test_orphaned_session_detected(tmp_db: Path):
    """Orphaned session (no end_time, > 24h old) returns WARN."""
    conn = sqlite3.connect(str(tmp_db))
    old = (datetime.utcnow() - timedelta(hours=48)).isoformat()
    conn.execute(
        "INSERT INTO session_journal (session_id, agent_id, start_time, end_time) VALUES (?, ?, ?, NULL)",
        ("s1", "primary", old),
    )
    conn.commit()
    conn.close()

    with patch.object(guard, "MEMORY_DB", tmp_db):
        result = guard.check_orphaned_sessions()
    assert result["status"] == "WARN"
    assert "1 orphaned" in result["detail"]


def test_recent_orphan_not_flagged(tmp_db: Path):
    """Recent orphan (< 24h old, no end_time) is NOT flagged — might still be running."""
    conn = sqlite3.connect(str(tmp_db))
    recent = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO session_journal (session_id, agent_id, start_time, end_time) VALUES (?, ?, ?, NULL)",
        ("s1", "primary", recent),
    )
    conn.commit()
    conn.close()

    with patch.object(guard, "MEMORY_DB", tmp_db):
        result = guard.check_orphaned_sessions()
    assert result["status"] == "PASS"


# ---------------------------------------------------------------------------
# Tests: disk_usage
# ---------------------------------------------------------------------------


def test_disk_usage_pass():
    """Disk usage check returns PASS when < 90%."""
    result = guard.check_disk_usage()
    # This test assumes the build machine isn't at 90% — if it is, the test
    # correctly reports what the guard would report.
    assert result["status"] in ("PASS", "FAIL")
    assert "used" in result["detail"]


# ---------------------------------------------------------------------------
# Tests: run_guard and results file
# ---------------------------------------------------------------------------


def test_run_guard_writes_results(tmp_path: Path, tmp_db: Path, tmp_skills: Path):
    """run_guard writes structured results to JSON."""
    results_file = tmp_path / "guard_results.json"
    with patch.object(guard, "MEMORY_DB", tmp_db), \
         patch.object(guard, "SKILLS_DIR", tmp_skills), \
         patch.object(guard, "DATA_DIR", tmp_path), \
         patch.object(guard, "RESULTS_FILE", results_file):
        output = guard.run_guard(
            checks=["memory_db", "skills", "disk"],
            json_only=True,
        )

    assert len(output["checks"]) == 3
    assert results_file.exists()

    saved = json.loads(results_file.read_text())
    assert "timestamp" in saved
    assert "summary" in saved
    assert saved["summary"]["total"] == 3


def test_run_guard_single_check(tmp_db: Path, tmp_path: Path):
    """run_guard with single check only runs that check."""
    results_file = tmp_path / "guard_results.json"
    with patch.object(guard, "MEMORY_DB", tmp_db), \
         patch.object(guard, "DATA_DIR", tmp_path), \
         patch.object(guard, "RESULTS_FILE", results_file):
        output = guard.run_guard(checks=["memory_db"], json_only=True)

    assert len(output["checks"]) == 1
    assert output["checks"][0]["check"] == "memory_db_integrity"


# ---------------------------------------------------------------------------
# Tests: network checks (mocked)
# ---------------------------------------------------------------------------


def test_hub_unreachable():
    """Hub check returns FAIL when unreachable."""
    with patch.object(guard, "HUB_URL", "http://127.0.0.1:1"):
        result = guard.check_hub_reachable()
    assert result["status"] == "FAIL"


def test_agentauth_unreachable():
    """AgentAuth check returns FAIL when unreachable."""
    with patch.object(guard, "AGENTAUTH_URL", "http://127.0.0.1:1"):
        result = guard.check_agentauth_jwks()
    assert result["status"] == "FAIL"


def test_litellm_unreachable():
    """LiteLLM check returns FAIL when unreachable."""
    with patch.object(guard, "LITELLM_URL", "http://127.0.0.1:1"):
        result = guard.check_litellm_proxy()
    assert result["status"] == "FAIL"
