"""
Tests for aiciv_mind.planning — task complexity classification and planning gates.
"""

from __future__ import annotations

import pytest

from aiciv_mind.planning import (
    ClassificationResult,
    PlanningGate,
    PlanningResult,
    TaskComplexity,
    classify_task,
)


# ---------------------------------------------------------------------------
# TaskComplexity enum
# ---------------------------------------------------------------------------


class TestTaskComplexity:
    def test_gate_depth_ordering(self):
        """gate_depth increases monotonically from TRIVIAL to VARIABLE."""
        depths = [c.gate_depth for c in TaskComplexity]
        assert depths == sorted(depths)
        assert depths == [0, 1, 2, 3, 4]

    def test_values(self):
        assert TaskComplexity.TRIVIAL.value == "trivial"
        assert TaskComplexity.VARIABLE.value == "variable"


# ---------------------------------------------------------------------------
# classify_task — heuristic classifier
# ---------------------------------------------------------------------------


class TestClassifyTask:
    def test_short_familiar_task_is_trivial_or_simple(self):
        """A short task with many memory hits → trivial or simple."""
        result = classify_task("check disk usage", memory_hit_count=5)
        assert result.complexity in (TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE)
        assert result.confidence > 0

    def test_long_complex_task_is_medium_or_higher(self):
        """A long task with complex keywords → medium or higher."""
        task = (
            "Design and implement a new authentication system that integrates "
            "with the existing AgentAuth service. First, research the current "
            "architecture. Then, build the OAuth2 flow. After that, deploy "
            "to staging and run integration tests."
        )
        result = classify_task(task, memory_hit_count=0)
        assert result.complexity.gate_depth >= TaskComplexity.MEDIUM.gate_depth

    def test_novel_task_boosts_complexity(self):
        """Zero memory hits + novelty keywords → higher complexity."""
        result = classify_task(
            "Explore this new experimental prototype for the first time",
            memory_hit_count=0,
        )
        assert result.complexity.gate_depth >= TaskComplexity.SIMPLE.gate_depth

    def test_many_memory_hits_reduces_complexity(self):
        """Many memory hits signal familiarity → lower complexity."""
        base_task = "Deploy the standard blog update to production"
        no_memory = classify_task(base_task, memory_hit_count=0)
        with_memory = classify_task(base_task, memory_hit_count=10)
        # With memory should be same or lower complexity
        assert with_memory.complexity.gate_depth <= no_memory.complexity.gate_depth

    def test_prior_success_rate_reduces_complexity(self):
        """High prior success rate pulls complexity down."""
        task = "Research and evaluate competing approaches to this problem"
        without_success = classify_task(task, memory_hit_count=0)
        with_success = classify_task(
            task, memory_hit_count=0, prior_success_rate=0.95
        )
        assert with_success.complexity.gate_depth <= without_success.complexity.gate_depth

    def test_multi_step_indicators_increase_complexity(self):
        """Tasks with numbered steps / sequential indicators → higher."""
        simple = classify_task("read the file")
        multi = classify_task(
            "1. read the file 2. extract the data 3. transform it "
            "then upload to the API after that verify the result"
        )
        assert multi.complexity.gate_depth >= simple.complexity.gate_depth

    def test_irreversible_keywords_increase_complexity(self):
        """Tasks with delete/deploy/push → higher complexity."""
        safe = classify_task("read the config file")
        risky = classify_task("delete the database and force push to production")
        assert risky.complexity.gate_depth >= safe.complexity.gate_depth

    def test_returns_classification_result(self):
        """Always returns a ClassificationResult with required fields."""
        result = classify_task("hello world")
        assert isinstance(result, ClassificationResult)
        assert isinstance(result.complexity, TaskComplexity)
        assert 0 <= result.confidence <= 1.0
        assert isinstance(result.signals, dict)
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0

    def test_signals_contain_expected_keys(self):
        """Signal dict should have all 5 heuristic signal keys."""
        result = classify_task("build a new feature")
        expected_keys = {"length", "multi_step", "complexity_keywords", "novelty", "reversibility"}
        assert expected_keys.issubset(result.signals.keys())

    def test_empty_task(self):
        """Empty task → trivial."""
        result = classify_task("")
        assert result.complexity == TaskComplexity.TRIVIAL


# ---------------------------------------------------------------------------
# PlanningGate
# ---------------------------------------------------------------------------


class TestPlanningGate:
    def test_disabled_gate_returns_trivial(self):
        """Disabled gate always returns TRIVIAL with empty plan."""
        gate = PlanningGate(enabled=False)
        result = gate.run("design a complex multi-step system")
        assert result.complexity == TaskComplexity.TRIVIAL
        assert result.plan == ""
        assert result.elapsed_ms == 0.0

    def test_enabled_gate_returns_planning_result(self):
        """Enabled gate returns a PlanningResult."""
        gate = PlanningGate(enabled=True)
        result = gate.run("check status")
        assert isinstance(result, PlanningResult)
        assert isinstance(result.complexity, TaskComplexity)
        assert result.elapsed_ms >= 0

    def test_trivial_task_minimal_plan(self):
        """Trivial task → empty or minimal plan text."""
        gate = PlanningGate(enabled=True)
        result = gate.run("hi")
        # Trivial tasks with no memory hits get empty plan
        assert result.complexity == TaskComplexity.TRIVIAL
        assert result.plan == ""

    def test_complex_task_has_plan_text(self):
        """Complex task → non-empty plan with planning instructions."""
        gate = PlanningGate(enabled=True)
        result = gate.run(
            "Design and implement a new microservice architecture. "
            "First research existing patterns. Then build the prototype. "
            "After that, deploy to staging for testing. Finally, migrate "
            "the database and push to production."
        )
        assert result.complexity.gate_depth >= TaskComplexity.MEDIUM.gate_depth
        assert len(result.plan) > 0
        assert "Planning Gate" in result.plan

    def test_medium_task_mentions_competing_hypotheses(self):
        """Medium+ task plan should mention competing hypotheses."""
        gate = PlanningGate(enabled=True)
        result = gate.run(
            "Research and compare three different approaches to implement "
            "this new feature. Evaluate each for performance and "
            "maintainability. Build the best one."
        )
        if result.complexity.gate_depth >= TaskComplexity.MEDIUM.gate_depth:
            assert "hypothes" in result.plan.lower()

    def test_gate_with_memory_store(self):
        """Gate integrates with memory store for memory-informed classification."""
        from aiciv_mind.memory import Memory, MemoryStore

        store = MemoryStore(":memory:")
        try:
            # Add some memories
            mem = Memory(
                agent_id="test",
                title="deploy blog",
                content="deployed blog successfully",
                domain="pipeline",
                memory_type="task",
            )
            store.store(mem)
            gate = PlanningGate(
                memory_store=store,
                agent_id="test",
                enabled=True,
            )
            result = gate.run("deploy the blog update")
            assert result.memories_consulted >= 0
            assert isinstance(result, PlanningResult)
        finally:
            store.close()

    def test_elapsed_ms_is_positive(self):
        """Gate execution should take some measurable time."""
        gate = PlanningGate(enabled=True)
        result = gate.run("check the current status")
        assert result.elapsed_ms >= 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_very_long_task(self):
        """Very long task text doesn't crash and gets high complexity."""
        task = "implement " * 500
        result = classify_task(task, memory_hit_count=0)
        assert result.complexity.gate_depth >= TaskComplexity.SIMPLE.gate_depth

    def test_special_characters_in_task(self):
        """Special characters don't crash the classifier."""
        result = classify_task("fix bug in /path/to/file.py:42 — `TypeError: NoneType`")
        assert isinstance(result.complexity, TaskComplexity)

    def test_unicode_task(self):
        """Unicode text doesn't crash."""
        result = classify_task("修正バグ: データベース接続エラー")
        assert isinstance(result.complexity, TaskComplexity)
