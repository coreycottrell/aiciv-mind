"""
Tests for aiciv_mind.fitness — Role-specific coordination fitness scoring.

Proves that the gravitational pull works: correct coordination gets high
scores, incorrect gets low scores, and the system distinguishes between
roles properly.
"""

from __future__ import annotations

import pytest

from aiciv_mind.fitness import (
    AgentFitness,
    CoordinationMetrics,
    PrimaryFitness,
    TeamLeadFitness,
    score_agent,
    score_for_role,
    score_primary,
    score_team_lead,
)
from aiciv_mind.roles import Role


# ---------------------------------------------------------------------------
# CoordinationMetrics construction
# ---------------------------------------------------------------------------


class TestCoordinationMetrics:
    def test_default_primary_metrics(self):
        m = CoordinationMetrics(role=Role.PRIMARY)
        assert m.role == Role.PRIMARY
        assert m.delegation_target == ""
        assert m.delegation_correct is None
        assert m.cross_vertical_synthesis is False

    def test_default_team_lead_metrics(self):
        m = CoordinationMetrics(role=Role.TEAM_LEAD)
        assert m.role == Role.TEAM_LEAD
        assert m.agent_spawned == ""
        assert m.result_synthesized is False
        assert m.scratchpad_updated is False

    def test_default_agent_metrics(self):
        m = CoordinationMetrics(role=Role.AGENT)
        assert m.role == Role.AGENT
        assert m.tools_attempted == 0
        assert m.tools_succeeded == 0
        assert m.memory_writes == 0

    def test_primary_with_values(self):
        m = CoordinationMetrics(
            role=Role.PRIMARY,
            delegation_target="research-lead",
            delegation_correct=True,
            team_leads_available=5,
            team_leads_utilized=3,
            cross_vertical_synthesis=True,
        )
        assert m.delegation_target == "research-lead"
        assert m.delegation_correct is True
        assert m.team_leads_available == 5


# ---------------------------------------------------------------------------
# Primary fitness scoring
# ---------------------------------------------------------------------------


class TestScorePrimary:
    def test_empty_metrics(self):
        result = score_primary([])
        assert isinstance(result, PrimaryFitness)
        assert result.composite == 0.0
        assert result.tasks_scored == 0

    def test_no_primary_metrics(self):
        """Non-primary metrics should be ignored."""
        m = CoordinationMetrics(role=Role.AGENT, tools_attempted=5)
        result = score_primary([m])
        assert result.tasks_scored == 0

    def test_perfect_delegation(self):
        """All delegations correct → high delegation accuracy."""
        metrics = [
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target="research-lead",
                delegation_correct=True,
                team_leads_available=5,
            ),
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target="coder-lead",
                delegation_correct=True,
                team_leads_available=5,
            ),
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target="comms-lead",
                delegation_correct=True,
                team_leads_available=5,
            ),
        ]
        result = score_primary(metrics)
        assert result.delegation_accuracy == 1.0
        assert result.tasks_scored == 3
        assert result.tasks_judged == 3

    def test_poor_delegation(self):
        """All delegations wrong → zero delegation accuracy."""
        metrics = [
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target="research-lead",
                delegation_correct=False,
                team_leads_available=5,
            ),
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target="research-lead",
                delegation_correct=False,
                team_leads_available=5,
            ),
        ]
        result = score_primary(metrics)
        assert result.delegation_accuracy == 0.0

    def test_mixed_delegation(self):
        """2/3 correct → ~0.667 accuracy."""
        metrics = [
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", delegation_correct=True, team_leads_available=3),
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="b", delegation_correct=True, team_leads_available=3),
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="c", delegation_correct=False, team_leads_available=3),
        ]
        result = score_primary(metrics)
        assert result.delegation_accuracy == pytest.approx(0.667, abs=0.01)

    def test_unjudged_delegation(self):
        """Unjudged (None) delegations don't count toward accuracy."""
        metrics = [
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", delegation_correct=True, team_leads_available=3),
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="b", delegation_correct=None, team_leads_available=3),
        ]
        result = score_primary(metrics)
        assert result.delegation_accuracy == 1.0
        assert result.tasks_judged == 1
        assert result.tasks_scored == 2

    def test_utilization_balance(self):
        """Using all available leads → high utilization balance."""
        metrics = [
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", team_leads_available=3),
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="b", team_leads_available=3),
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="c", team_leads_available=3),
        ]
        result = score_primary(metrics)
        assert result.utilization_balance > 0.7

    def test_utilization_unbalanced(self):
        """All tasks to one lead out of many → low utilization balance."""
        metrics = [
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", team_leads_available=5),
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", team_leads_available=5),
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", team_leads_available=5),
        ]
        result = score_primary(metrics)
        # 1/5 utilization = 0.2 ratio, but perfect balance within that one lead
        # so composite is ~0.52 (low but not zero because balance is 1.0)
        assert result.utilization_balance < 0.6

    def test_synthesis_rate(self):
        """Cross-vertical synthesis → high synthesis rate."""
        metrics = [
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", cross_vertical_synthesis=True, team_leads_available=3),
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="b", cross_vertical_synthesis=True, team_leads_available=3),
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="c", cross_vertical_synthesis=False, team_leads_available=3),
        ]
        result = score_primary(metrics)
        assert result.synthesis_rate == pytest.approx(0.667, abs=0.01)

    def test_to_dict(self):
        result = score_primary([])
        d = result.to_dict()
        assert d["role"] == "primary"
        assert "delegation_accuracy" in d
        assert "composite" in d

    def test_composite_includes_all_factors(self):
        """Perfect on all dimensions → composite = 1.0."""
        metrics = [
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target="a",
                delegation_correct=True,
                team_leads_available=2,
                cross_vertical_synthesis=True,
            ),
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target="b",
                delegation_correct=True,
                team_leads_available=2,
                cross_vertical_synthesis=True,
            ),
        ]
        result = score_primary(metrics)
        assert result.delegation_accuracy == 1.0
        assert result.synthesis_rate == 1.0
        assert result.composite > 0.8


# ---------------------------------------------------------------------------
# Team Lead fitness scoring
# ---------------------------------------------------------------------------


class TestScoreTeamLead:
    def test_empty_metrics(self):
        result = score_team_lead([])
        assert isinstance(result, TeamLeadFitness)
        assert result.composite == 0.0

    def test_no_team_lead_metrics(self):
        m = CoordinationMetrics(role=Role.AGENT)
        result = score_team_lead([m])
        assert result.tasks_scored == 0

    def test_perfect_agent_selection(self):
        metrics = [
            CoordinationMetrics(role=Role.TEAM_LEAD, agent_spawned="coder", agent_selection_correct=True),
            CoordinationMetrics(role=Role.TEAM_LEAD, agent_spawned="tester", agent_selection_correct=True),
        ]
        result = score_team_lead(metrics)
        assert result.agent_selection_accuracy == 1.0

    def test_synthesis_rate(self):
        metrics = [
            CoordinationMetrics(role=Role.TEAM_LEAD, result_synthesized=True),
            CoordinationMetrics(role=Role.TEAM_LEAD, result_synthesized=False),
        ]
        result = score_team_lead(metrics)
        assert result.synthesis_rate == 0.5

    def test_scratchpad_continuity(self):
        metrics = [
            CoordinationMetrics(role=Role.TEAM_LEAD, scratchpad_updated=True),
            CoordinationMetrics(role=Role.TEAM_LEAD, scratchpad_updated=True),
            CoordinationMetrics(role=Role.TEAM_LEAD, scratchpad_updated=False),
        ]
        result = score_team_lead(metrics)
        assert result.scratchpad_continuity == pytest.approx(0.667, abs=0.01)

    def test_delegation_speed_fast(self):
        """Fast delegation (< 1s) → high speed score."""
        metrics = [
            CoordinationMetrics(role=Role.TEAM_LEAD, delegation_latency_ms=500),
            CoordinationMetrics(role=Role.TEAM_LEAD, delegation_latency_ms=800),
        ]
        result = score_team_lead(metrics)
        assert result.delegation_speed > 0.9

    def test_delegation_speed_slow(self):
        """Slow delegation (> 30s) → low speed score."""
        metrics = [
            CoordinationMetrics(role=Role.TEAM_LEAD, delegation_latency_ms=35000),
        ]
        result = score_team_lead(metrics)
        assert result.delegation_speed == 0.0

    def test_to_dict(self):
        result = score_team_lead([])
        d = result.to_dict()
        assert d["role"] == "team_lead"
        assert "agent_selection_accuracy" in d

    def test_avg_latency(self):
        metrics = [
            CoordinationMetrics(role=Role.TEAM_LEAD, delegation_latency_ms=1000),
            CoordinationMetrics(role=Role.TEAM_LEAD, delegation_latency_ms=3000),
        ]
        result = score_team_lead(metrics)
        assert result.avg_latency_ms == 2000.0


# ---------------------------------------------------------------------------
# Agent fitness scoring
# ---------------------------------------------------------------------------


class TestScoreAgent:
    def test_empty_metrics(self):
        result = score_agent([])
        assert isinstance(result, AgentFitness)
        assert result.composite == 0.0

    def test_no_agent_metrics(self):
        m = CoordinationMetrics(role=Role.PRIMARY)
        result = score_agent([m])
        assert result.tasks_scored == 0

    def test_perfect_tool_effectiveness(self):
        metrics = [
            CoordinationMetrics(role=Role.AGENT, tools_attempted=10, tools_succeeded=10, task_completed=True, verification_provided=True),
        ]
        result = score_agent(metrics)
        assert result.tool_effectiveness == 1.0

    def test_poor_tool_effectiveness(self):
        metrics = [
            CoordinationMetrics(role=Role.AGENT, tools_attempted=10, tools_succeeded=2),
        ]
        result = score_agent(metrics)
        assert result.tool_effectiveness == 0.2

    def test_zero_tool_attempts(self):
        metrics = [
            CoordinationMetrics(role=Role.AGENT, tools_attempted=0, tools_succeeded=0),
        ]
        result = score_agent(metrics)
        assert result.tool_effectiveness == 0.0

    def test_memory_contribution(self):
        """1 write per 3 tasks = ideal."""
        metrics = [
            CoordinationMetrics(role=Role.AGENT, memory_writes=1),
            CoordinationMetrics(role=Role.AGENT, memory_writes=0),
            CoordinationMetrics(role=Role.AGENT, memory_writes=0),
        ]
        result = score_agent(metrics)
        assert result.memory_contribution == 1.0
        assert result.total_memory_writes == 1

    def test_verification_compliance(self):
        metrics = [
            CoordinationMetrics(role=Role.AGENT, verification_provided=True),
            CoordinationMetrics(role=Role.AGENT, verification_provided=False),
        ]
        result = score_agent(metrics)
        assert result.verification_compliance == 0.5

    def test_completion_rate(self):
        metrics = [
            CoordinationMetrics(role=Role.AGENT, task_completed=True),
            CoordinationMetrics(role=Role.AGENT, task_completed=True),
            CoordinationMetrics(role=Role.AGENT, task_completed=False),
        ]
        result = score_agent(metrics)
        assert result.completion_rate == pytest.approx(0.667, abs=0.01)

    def test_to_dict(self):
        result = score_agent([])
        d = result.to_dict()
        assert d["role"] == "agent"
        assert "tool_effectiveness" in d
        assert "total_tool_calls" in d

    def test_composite_all_perfect(self):
        metrics = [
            CoordinationMetrics(
                role=Role.AGENT,
                tools_attempted=5,
                tools_succeeded=5,
                memory_writes=1,
                verification_provided=True,
                task_completed=True,
            ),
        ]
        result = score_agent(metrics)
        assert result.composite == 1.0


# ---------------------------------------------------------------------------
# score_for_role dispatch
# ---------------------------------------------------------------------------


class TestScoreForRole:
    def test_dispatches_primary(self):
        result = score_for_role(Role.PRIMARY, [])
        assert isinstance(result, PrimaryFitness)

    def test_dispatches_team_lead(self):
        result = score_for_role(Role.TEAM_LEAD, [])
        assert isinstance(result, TeamLeadFitness)

    def test_dispatches_agent(self):
        result = score_for_role(Role.AGENT, [])
        assert isinstance(result, AgentFitness)

    def test_scores_correct_role_metrics_only(self):
        """Mixed metrics — only the target role's metrics are scored."""
        metrics = [
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", delegation_correct=True, team_leads_available=3),
            CoordinationMetrics(role=Role.AGENT, tools_attempted=10, tools_succeeded=10),
        ]
        primary_result = score_for_role(Role.PRIMARY, metrics)
        assert isinstance(primary_result, PrimaryFitness)
        assert primary_result.tasks_scored == 1

        agent_result = score_for_role(Role.AGENT, metrics)
        assert isinstance(agent_result, AgentFitness)
        assert agent_result.tasks_scored == 1


# ---------------------------------------------------------------------------
# Integration with SessionLearner
# ---------------------------------------------------------------------------


class TestSessionLearnerIntegration:
    def test_record_coordination(self):
        from aiciv_mind.learning import SessionLearner
        learner = SessionLearner(agent_id="test")
        m = CoordinationMetrics(role=Role.PRIMARY, delegation_target="research")
        learner.record_coordination(m)
        assert learner.coordination_count == 1

    def test_summarize_includes_fitness(self):
        from aiciv_mind.learning import SessionLearner, TaskOutcome
        learner = SessionLearner(agent_id="test")

        # Need at least one TaskOutcome for summarize to run
        learner.record(TaskOutcome(task="do stuff", result="done successfully and verified", tool_call_count=3))

        # Add coordination metrics
        learner.record_coordination(
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target="research-lead",
                delegation_correct=True,
                team_leads_available=3,
                cross_vertical_synthesis=True,
            )
        )

        summary = learner.summarize()
        assert "primary" in summary.coordination_fitness
        assert summary.coordination_fitness["primary"]["delegation_accuracy"] == 1.0

    def test_summarize_without_coordination(self):
        """Summarize works fine without any coordination metrics."""
        from aiciv_mind.learning import SessionLearner, TaskOutcome
        learner = SessionLearner(agent_id="test")
        learner.record(TaskOutcome(task="do stuff", result="done successfully and verified", tool_call_count=3))
        summary = learner.summarize()
        assert summary.coordination_fitness == {}

    def test_session_summary_to_dict_includes_fitness(self):
        from aiciv_mind.learning import SessionSummary
        s = SessionSummary(
            task_count=1,
            coordination_fitness={"primary": {"delegation_accuracy": 1.0}},
        )
        d = s.to_dict()
        assert "coordination_fitness" in d
        assert d["coordination_fitness"]["primary"]["delegation_accuracy"] == 1.0
