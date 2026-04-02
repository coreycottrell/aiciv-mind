"""
Tests for aiciv_mind.fork_context — Isolated skill execution.
"""

from __future__ import annotations

import copy
import pytest

from aiciv_mind.fork_context import ForkContext, ForkResult


# ---------------------------------------------------------------------------
# ForkResult
# ---------------------------------------------------------------------------


class TestForkResult:
    def test_default_values(self):
        r = ForkResult(output="done", messages_consumed=3, elapsed_ms=100.0)
        assert r.success is True
        assert r.error == ""
        assert r.skill_id == ""

    def test_error_result(self):
        r = ForkResult(
            output="failed",
            messages_consumed=0,
            elapsed_ms=10.0,
            success=False,
            error="crashed",
        )
        assert not r.success
        assert r.error == "crashed"


# ---------------------------------------------------------------------------
# ForkContext — snapshot and restore
# ---------------------------------------------------------------------------


class TestForkContext:
    def test_snapshot_saves_messages(self):
        messages = [{"role": "user", "content": "hello"}]
        fork = ForkContext(
            messages=messages,
            system_prompt="original system",
            skill_content="# Skill content",
            skill_id="test-skill",
        )
        fork.snapshot()
        assert fork.is_forked is True
        assert len(fork._snapshot_messages) == 1
        assert fork._snapshot_messages[0]["content"] == "hello"

    def test_snapshot_is_deep_copy(self):
        messages = [{"role": "user", "content": "hello"}]
        fork = ForkContext(
            messages=messages,
            system_prompt="sys",
            skill_content="skill",
        )
        fork.snapshot()
        # Modify original — snapshot should be unaffected
        messages.append({"role": "assistant", "content": "hi"})
        assert len(fork._snapshot_messages) == 1

    def test_enter_fork_returns_clean_context(self):
        messages = [{"role": "user", "content": "hello"}]
        fork = ForkContext(
            messages=messages,
            system_prompt="original",
            skill_content="# My Skill\nDo things.",
            skill_id="my-skill",
        )
        clean_msgs, fork_system = fork.enter_fork()
        assert clean_msgs == []
        assert "My Skill" in fork_system
        assert "Fork Context" in fork_system

    def test_enter_fork_auto_snapshots(self):
        messages = [{"role": "user", "content": "hello"}]
        fork = ForkContext(
            messages=messages,
            system_prompt="original",
            skill_content="skill",
        )
        assert fork.is_forked is False
        fork.enter_fork()
        assert fork.is_forked is True

    def test_exit_fork_restores_messages(self):
        original = [{"role": "user", "content": "hello"}]
        fork = ForkContext(
            messages=original,
            system_prompt="original system",
            skill_content="skill",
            skill_id="test",
        )
        fork.snapshot()
        fork.enter_fork()

        # Simulate fork execution
        fork_messages = [
            {"role": "user", "content": "skill task"},
            {"role": "assistant", "content": "skill done"},
        ]

        restored_msgs, restored_sys = fork.exit_fork("skill result", fork_messages)

        # Original message should be restored
        assert restored_msgs[0]["content"] == "hello"
        # Summary should be appended
        assert len(restored_msgs) == 2
        assert "test" in restored_msgs[1]["content"]  # skill_id in summary
        assert "skill result" in restored_msgs[1]["content"]
        # System prompt restored
        assert restored_sys == "original system"
        # Fork is no longer active
        assert fork.is_forked is False

    def test_exit_fork_without_enter_returns_originals(self):
        messages = [{"role": "user", "content": "hello"}]
        fork = ForkContext(
            messages=messages,
            system_prompt="sys",
            skill_content="skill",
        )
        # Exit without entering
        restored_msgs, restored_sys = fork.exit_fork("result", [])
        assert restored_msgs is messages  # Same reference
        assert restored_sys == "sys"

    def test_skill_id_property(self):
        fork = ForkContext(
            messages=[],
            system_prompt="",
            skill_content="",
            skill_id="my-skill",
        )
        assert fork.skill_id == "my-skill"

    def test_exit_fork_truncates_long_result(self):
        messages = [{"role": "user", "content": "hello"}]
        fork = ForkContext(
            messages=messages,
            system_prompt="sys",
            skill_content="skill",
            skill_id="test",
        )
        fork.snapshot()
        fork.enter_fork()

        long_result = "x" * 1000
        restored_msgs, _ = fork.exit_fork(long_result, [])
        # Summary should truncate to 500 chars
        summary = restored_msgs[-1]["content"]
        assert len(summary) < len(long_result) + 200  # Summary text + truncated result


# ---------------------------------------------------------------------------
# ForkContext — multiple fork cycles
# ---------------------------------------------------------------------------


class TestMultipleForks:
    def test_sequential_forks(self):
        messages = [{"role": "user", "content": "original"}]
        fork = ForkContext(
            messages=messages,
            system_prompt="sys",
            skill_content="skill-1",
            skill_id="skill-1",
        )

        # First fork
        fork.snapshot()
        fork.enter_fork()
        restored, _ = fork.exit_fork("result-1", [])
        assert len(restored) == 2  # original + summary

        # Second fork (new instance)
        fork2 = ForkContext(
            messages=restored,
            system_prompt="sys",
            skill_content="skill-2",
            skill_id="skill-2",
        )
        fork2.snapshot()
        fork2.enter_fork()
        restored2, _ = fork2.exit_fork("result-2", [])
        assert len(restored2) == 3  # original + summary1 + summary2

    def test_fork_preserves_message_immutability(self):
        """Original messages should not be modified by fork operations."""
        original = [{"role": "user", "content": "keep me safe"}]
        original_copy = copy.deepcopy(original)

        fork = ForkContext(
            messages=original,
            system_prompt="sys",
            skill_content="skill",
            skill_id="test",
        )
        fork.snapshot()
        fork.enter_fork()
        fork.exit_fork("done", [{"role": "user", "content": "fork msg"}])

        # Original list should not be mutated
        assert original == original_copy
