"""
Tests for aiciv_mind.challenger — Challenger System.

Covers all 6 checks including the new filesystem verification (check 5)
and state file integrity (check 6) that catch false completion claims.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python3 -m pytest tests/test_challenger.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiciv_mind.challenger import ChallengerSystem


# ---------------------------------------------------------------------------
# Check 1: Premature completion claims
# ---------------------------------------------------------------------------


def test_premature_completion_low_tool_count():
    """Completion claim with <2 tool calls should be challenged."""
    cs = ChallengerSystem()
    result = cs.challenge_turn(
        response_text="I'm done, task complete!",
        task="fix the bug",
        tool_results=[],
        iteration=1,
        tool_call_count=0,
    )
    assert result.should_inject
    assert result.severity == "critical"
    assert any("premature" in c.lower() for c in result.challenges)


def test_no_challenge_when_enough_work():
    """Normal completion with adequate tool calls should pass."""
    cs = ChallengerSystem()
    # Simulate some write tools having been used
    cs._write_tools_seen = ["write_file", "bash"]
    result = cs.challenge_turn(
        response_text="All work is verified and committed.",
        task="fix the bug",
        tool_results=["bash: committed"],
        iteration=5,
        tool_call_count=10,
    )
    # No premature or empty work challenges
    premature_or_empty = [
        c for c in result.challenges
        if "premature" in c.lower() or "no write" in c.lower()
    ]
    assert not premature_or_empty


# ---------------------------------------------------------------------------
# Check 2: Empty work claims
# ---------------------------------------------------------------------------


def test_empty_work_claim():
    """Claiming work was done with no write tools used."""
    cs = ChallengerSystem()
    result = cs.challenge_turn(
        response_text="I created the new module and implemented the fix.",
        task="build module",
        tool_results=["read_file: contents"],
        iteration=3,
        tool_call_count=5,
    )
    assert result.should_inject
    assert any("no write tools" in c.lower() for c in result.challenges)


# ---------------------------------------------------------------------------
# Check 5: Filesystem verification — THE KEY NEW TEST
# ---------------------------------------------------------------------------


def test_filesystem_claim_missing_file():
    """
    Completion claim referencing a file that doesn't exist.
    This is the exact false-completion pattern that crippled Root.
    """
    cs = ChallengerSystem()
    cs._write_tools_seen = ["write_file"]  # Avoid empty-work trigger
    result = cs.challenge_turn(
        response_text=(
            "Task complete! I created /tmp/aiciv_challenger_test_NONEXISTENT_FILE.py "
            "and it's all done."
        ),
        task="create the file",
        tool_results=["write_file: done"],
        iteration=5,
        tool_call_count=8,
    )
    assert result.should_inject
    assert result.severity == "critical"
    assert any("filesystem verification failed" in c.lower() for c in result.challenges)
    assert any("NONEXISTENT" in c for c in result.challenges)


def test_filesystem_claim_existing_file(tmp_path):
    """Completion claim referencing a file that DOES exist should pass."""
    # Create the file
    test_file = tmp_path / "real_output.py"
    test_file.write_text("# real output\n", encoding="utf-8")

    cs = ChallengerSystem()
    cs._write_tools_seen = ["write_file"]
    result = cs.challenge_turn(
        response_text=f"Task complete! I created {test_file} and verified it works.",
        task="create output",
        tool_results=["write_file: done"],
        iteration=5,
        tool_call_count=8,
    )
    # Should NOT have a filesystem failure
    fs_challenges = [c for c in result.challenges if "filesystem" in c.lower()]
    assert not fs_challenges


def test_filesystem_only_triggers_on_completion():
    """Filesystem check should NOT fire on mid-task responses (no completion signal)."""
    cs = ChallengerSystem()
    result = cs.challenge_turn(
        response_text="I'm working on creating /tmp/nonexistent_file_xyz.py next.",
        task="build thing",
        tool_results=[],
        iteration=2,
        tool_call_count=3,
    )
    fs_challenges = [c for c in result.challenges if "filesystem" in c.lower()]
    assert not fs_challenges


# ---------------------------------------------------------------------------
# Check 6: State file verification
# ---------------------------------------------------------------------------


def test_state_file_missing_evidence(tmp_path):
    """Phase marked complete in evolution-status.json but no evidence dir."""
    # Create evolution-status.json with a completed phase
    status = {
        "phases": {
            "0_self_discovery": {"completed": True},
        }
    }
    (tmp_path / "evolution-status.json").write_text(
        json.dumps(status), encoding="utf-8",
    )
    # NO test-civ/memories/ directory

    cs = ChallengerSystem(mind_root=str(tmp_path))
    cs._write_tools_seen = ["write_file"]
    result = cs.challenge_turn(
        response_text="All phases complete. Shipped.",
        task="evolution test",
        tool_results=[],
        iteration=5,
        tool_call_count=10,
    )
    state_challenges = [c for c in result.challenges if "evolution-status" in c.lower()]
    assert state_challenges


def test_state_file_with_evidence(tmp_path):
    """Phase marked complete WITH evidence should pass."""
    status = {
        "phases": {
            "0_self_discovery": {"completed": True},
        }
    }
    (tmp_path / "evolution-status.json").write_text(
        json.dumps(status), encoding="utf-8",
    )
    # Create evidence directory with files
    evidence_dir = tmp_path / "test-civ" / "memories"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "identity.md").write_text("# Identity", encoding="utf-8")

    cs = ChallengerSystem(mind_root=str(tmp_path))
    cs._write_tools_seen = ["write_file"]
    result = cs.challenge_turn(
        response_text="All phases complete. Shipped.",
        task="evolution test",
        tool_results=[],
        iteration=5,
        tool_call_count=10,
    )
    state_challenges = [c for c in result.challenges if "evolution-status" in c.lower()]
    assert not state_challenges


def test_state_file_no_root_passes():
    """Without mind_root, state check is a no-op."""
    cs = ChallengerSystem(mind_root=None)
    result = cs.challenge_turn(
        response_text="Complete. Done. Shipped.",
        task="test",
        tool_results=[],
        iteration=1,
        tool_call_count=0,
    )
    # Should still get premature completion challenges, but NOT state challenges
    state_challenges = [c for c in result.challenges if "evolution-status" in c.lower()]
    assert not state_challenges


# ---------------------------------------------------------------------------
# Integration: Deliberately false claim caught
# ---------------------------------------------------------------------------


def test_challenger_catches_deliberate_false_claim():
    """
    PROOF: The challenger catches a deliberately false completion claim.

    Scenario: Mind claims to have created 3 files and marks the task complete.
    None of the files exist. Challenger must fire with CRITICAL severity.
    """
    cs = ChallengerSystem()
    cs._write_tools_seen = ["write_file", "write_file", "write_file"]

    result = cs.challenge_turn(
        response_text=(
            "Task complete! I've finished building the challenger mind:\n"
            "- Created /tmp/aiciv_false_claim_test_1.py\n"
            "- Wrote /tmp/aiciv_false_claim_test_2.yaml\n"
            "- Saved /tmp/aiciv_false_claim_test_3.md\n"
            "All done, shipping!"
        ),
        task="build challenger mind",
        tool_results=["write_file: done", "write_file: done", "write_file: done"],
        iteration=8,
        tool_call_count=15,
    )

    assert result.should_inject, "Challenger MUST fire on false file claims"
    assert result.severity == "critical", f"Expected critical, got {result.severity}"
    assert any("filesystem verification failed" in c.lower() for c in result.challenges)

    # All 3 false files should be mentioned
    fs_challenges = [c for c in result.challenges if "filesystem" in c.lower()]
    assert fs_challenges
    combined = " ".join(fs_challenges)
    assert "false_claim_test_1" in combined
    assert "false_claim_test_2" in combined
    assert "false_claim_test_3" in combined
