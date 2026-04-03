"""
Tests for aiciv_mind.learning — self-improving loop (Principle 7).
"""

from __future__ import annotations

import pytest

from aiciv_mind.learning import SessionLearner, SessionSummary, TaskOutcome


# ---------------------------------------------------------------------------
# TaskOutcome
# ---------------------------------------------------------------------------


class TestTaskOutcome:
    def test_succeeded_with_good_result(self):
        o = TaskOutcome(
            task="deploy blog",
            result="Blog deployed successfully to production.",
            tools_used=["bash", "git"],
            tool_call_count=3,
        )
        assert o.succeeded

    def test_failed_with_errors(self):
        o = TaskOutcome(
            task="deploy blog",
            result="Failed to deploy.",
            tool_errors=["Connection refused"],
            tools_used=["bash"],
            tool_call_count=2,
        )
        assert not o.succeeded

    def test_failed_with_short_result(self):
        o = TaskOutcome(task="check", result="ok", tool_call_count=1)
        assert not o.succeeded  # result < 20 chars

    def test_efficiency_score_zero_with_no_calls(self):
        o = TaskOutcome(task="", result="", tool_call_count=0)
        assert o.efficiency_score == 0.0

    def test_efficiency_score_range(self):
        o = TaskOutcome(
            task="build feature",
            result="Feature built and tested.",
            tools_used=["write", "bash"],
            tool_call_count=4,
        )
        score = o.efficiency_score
        assert 0.0 <= score <= 1.0

    def test_errors_reduce_efficiency(self):
        clean = TaskOutcome(
            task="task",
            result="done",
            tools_used=["bash"],
            tool_call_count=3,
        )
        dirty = TaskOutcome(
            task="task",
            result="done with issues",
            tools_used=["bash"],
            tool_errors=["error1", "error2"],
            tool_call_count=3,
        )
        assert dirty.efficiency_score < clean.efficiency_score

    def test_many_calls_reduce_efficiency(self):
        few = TaskOutcome(
            task="task",
            result="done",
            tools_used=["bash"],
            tool_call_count=3,
        )
        many = TaskOutcome(
            task="task",
            result="done",
            tools_used=["bash"],
            tool_call_count=20,
        )
        assert many.efficiency_score < few.efficiency_score


# ---------------------------------------------------------------------------
# SessionLearner
# ---------------------------------------------------------------------------


class TestSessionLearner:
    def test_empty_session_summary(self):
        learner = SessionLearner(agent_id="test")
        summary = learner.summarize()
        assert summary.task_count == 0

    def test_record_increments_count(self):
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(task="t1", result="r1", tool_call_count=1))
        learner.record(TaskOutcome(task="t2", result="r2", tool_call_count=1))
        assert learner.task_count == 2

    def test_summary_success_rate(self):
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(
            task="good task",
            result="This is a successful result text.",
            tools_used=["bash"],
            tool_call_count=3,
        ))
        learner.record(TaskOutcome(
            task="bad task",
            result="Failed miserably with multiple issues.",
            tool_errors=["error"],
            tools_used=["bash"],
            tool_call_count=3,
        ))
        summary = learner.summarize()
        assert summary.task_count == 2
        assert summary.success_count == 1
        assert summary.success_rate == 0.5

    def test_summary_tool_frequency(self):
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(
            task="t1", result="r1",
            tools_used=["bash", "write"],
            tool_call_count=2,
        ))
        learner.record(TaskOutcome(
            task="t2", result="r2",
            tools_used=["bash", "read"],
            tool_call_count=2,
        ))
        summary = learner.summarize()
        tool_names = [t for t, _ in summary.most_used_tools]
        assert "bash" in tool_names  # bash used in both tasks

    def test_summary_complexity_distribution(self):
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(
            task="t1", result="r1",
            planned_complexity="simple",
            tool_call_count=1,
        ))
        learner.record(TaskOutcome(
            task="t2", result="r2",
            planned_complexity="complex",
            tool_call_count=1,
        ))
        summary = learner.summarize()
        assert summary.complexity_distribution["simple"] == 1
        assert summary.complexity_distribution["complex"] == 1

    def test_summary_planning_accuracy(self):
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(
            task="t1", result="r1",
            plan_was_adequate=True,
            tool_call_count=1,
        ))
        learner.record(TaskOutcome(
            task="t2", result="r2",
            plan_was_adequate=False,
            tool_call_count=1,
        ))
        summary = learner.summarize()
        assert summary.planning_accuracy["adequate"] == 1
        assert summary.planning_accuracy["inadequate"] == 1

    def test_summary_verification_stats(self):
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(
            task="t1", result="r1",
            verification_outcome="approved",
            tool_call_count=1,
        ))
        learner.record(TaskOutcome(
            task="t2", result="r2",
            verification_outcome="challenged",
            tool_call_count=1,
        ))
        summary = learner.summarize()
        assert summary.verification_stats["approved"] == 1
        assert summary.verification_stats["challenged"] == 1

    def test_high_error_rate_generates_insight(self):
        learner = SessionLearner(agent_id="test")
        for i in range(5):
            learner.record(TaskOutcome(
                task=f"task {i}",
                result=f"result {i} is long enough to count",
                tool_errors=["err"] if i < 3 else [],  # 60% error rate
                tools_used=["bash"],
                tool_call_count=2,
            ))
        summary = learner.summarize()
        assert any("error rate" in insight.lower() for insight in summary.insights)

    def test_to_dict_serializable(self):
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(
            task="t1", result="r1", tool_call_count=1,
        ))
        summary = learner.summarize()
        d = summary.to_dict()
        assert isinstance(d, dict)
        assert "task_count" in d
        assert "insights" in d


# ---------------------------------------------------------------------------
# write_session_learning
# ---------------------------------------------------------------------------


class TestWriteSessionLearning:
    def test_skips_single_task_session(self):
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(task="t1", result="r1", tool_call_count=1))

        from aiciv_mind.memory import MemoryStore
        store = MemoryStore(":memory:")
        try:
            mem_id = learner.write_session_learning(store)
            assert mem_id is None  # Not enough tasks
        finally:
            store.close()

    def test_writes_learning_for_multi_task_session(self):
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(
            task="t1", result="Built the feature successfully.",
            tools_used=["bash", "write"],
            tool_call_count=5,
        ))
        learner.record(TaskOutcome(
            task="t2", result="Fixed the bug and all tests pass.",
            tools_used=["bash", "read"],
            tool_call_count=3,
        ))

        from aiciv_mind.memory import MemoryStore
        store = MemoryStore(":memory:")
        try:
            mem_id = learner.write_session_learning(store)
            assert mem_id is not None
            # Verify the memory was stored
            memories = store.search(query="session learning", agent_id="test", limit=1)
            assert len(memories) >= 1
        finally:
            store.close()


# ---------------------------------------------------------------------------
# SessionSummary
# ---------------------------------------------------------------------------


class TestWriteSessionLearningWithCoordination:
    def test_writes_coordination_fitness_to_memory(self):
        """When coordination metrics exist, they appear in the session learning memory."""
        from aiciv_mind.fitness import CoordinationMetrics
        from aiciv_mind.roles import Role
        from aiciv_mind.memory import MemoryStore

        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(
            task="t1", result="Built the feature successfully.",
            tools_used=["bash"], tool_call_count=5,
        ))
        learner.record(TaskOutcome(
            task="t2", result="Fixed the bug and all tests pass.",
            tools_used=["read"], tool_call_count=3,
        ))

        # Record coordination metrics
        learner.record_coordination(CoordinationMetrics(
            role=Role.PRIMARY,
            delegation_target="research-lead",
            delegation_correct=True,
            team_leads_available=5,
            team_leads_utilized=1,
        ))

        store = MemoryStore(":memory:")
        try:
            mem_id = learner.write_session_learning(store)
            assert mem_id is not None
            memories = store.search(query="coordination fitness", agent_id="test", limit=1)
            assert len(memories) >= 1
            content = memories[0]["content"] if isinstance(memories[0], dict) else memories[0].content
            assert "Coordination Fitness" in content
            assert "primary" in content
        finally:
            store.close()


class TestSessionSummary:
    def test_default_values(self):
        s = SessionSummary()
        assert s.task_count == 0
        assert s.insights == []

    def test_to_dict_keys(self):
        s = SessionSummary(task_count=5, success_rate=0.8)
        d = s.to_dict()
        assert d["task_count"] == 5
        assert d["success_rate"] == 0.8
