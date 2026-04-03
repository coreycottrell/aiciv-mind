"""
aiciv_mind.fitness — Role-specific coordination fitness scoring.

Measures HOW WELL each level of the fractal hierarchy is coordinating, not
just whether tasks completed.  This is the gravitational pull that rewards
correct fractal behavior.

Scoring by role:
    PRIMARY:    delegation accuracy, team lead utilization, cross-vertical synthesis
    TEAM_LEAD:  agent selection quality, result synthesis, scratchpad continuity
    AGENT:      tool effectiveness, memory writes, verification compliance

Scores are 0.0–1.0.  They feed into SessionLearner alongside TaskOutcome for
the Loop 2 session summary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aiciv_mind.roles import Role

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Coordination metrics — recorded per-task, role-specific
# ---------------------------------------------------------------------------


@dataclass
class CoordinationMetrics:
    """
    Role-aware coordination metrics for a single task.

    Captures HOW the task was coordinated, not just whether it succeeded.
    Different fields are relevant for different roles.
    """

    role: Role

    # --- PRIMARY metrics ---
    delegation_target: str = ""           # Which team lead was chosen
    delegation_correct: bool | None = None  # Was it the RIGHT team lead?
    team_leads_available: int = 0         # How many team leads exist
    team_leads_utilized: int = 0          # How many were used this session
    cross_vertical_synthesis: bool = False  # Did Primary synthesize across verticals?
    context_tokens_used: int = 0          # Context efficiency tracking

    # --- TEAM LEAD metrics ---
    agent_spawned: str = ""               # Which agent was selected
    agent_selection_correct: bool | None = None  # Right agent for the task?
    result_synthesized: bool = False       # Did TL produce a synthesis (not passthrough)?
    scratchpad_updated: bool = False       # Did TL update team scratchpad?
    delegation_latency_ms: float = 0.0    # Time from receipt to agent spawn

    # --- AGENT metrics ---
    tools_attempted: int = 0
    tools_succeeded: int = 0
    memory_writes: int = 0                # How many memories written
    verification_provided: bool = False    # Did agent provide evidence with completion?
    task_completed: bool = False


# ---------------------------------------------------------------------------
# Fitness calculators — one per role
# ---------------------------------------------------------------------------


def score_primary(metrics: list[CoordinationMetrics]) -> PrimaryFitness:
    """
    Score a Primary mind's coordination fitness for a session.

    Measures:
    - Delegation accuracy: % of tasks routed to the correct team lead
    - Utilization balance: are all team leads being used, or is one overloaded?
    - Synthesis quality: did Primary synthesize cross-vertical results?
    """
    if not metrics:
        return PrimaryFitness()

    primary_metrics = [m for m in metrics if m.role == Role.PRIMARY]
    if not primary_metrics:
        return PrimaryFitness()

    total = len(primary_metrics)

    # Delegation accuracy
    judged = [m for m in primary_metrics if m.delegation_correct is not None]
    correct = sum(1 for m in judged if m.delegation_correct)
    delegation_accuracy = correct / len(judged) if judged else 0.0

    # Utilization balance (Gini-like: 1.0 = perfectly balanced, 0.0 = all on one lead)
    lead_counts: dict[str, int] = {}
    for m in primary_metrics:
        if m.delegation_target:
            lead_counts[m.delegation_target] = lead_counts.get(m.delegation_target, 0) + 1

    max_leads = max(m.team_leads_available for m in primary_metrics) if primary_metrics else 0
    if max_leads > 0 and lead_counts:
        used = len(lead_counts)
        utilization_ratio = used / max_leads
        # Balance: how evenly distributed across used leads
        counts = list(lead_counts.values())
        max_count = max(counts)
        min_count = min(counts)
        balance = 1.0 - (max_count - min_count) / max(max_count, 1)
        utilization_balance = utilization_ratio * 0.6 + balance * 0.4
    else:
        utilization_balance = 0.0

    # Synthesis quality
    synthesis_count = sum(1 for m in primary_metrics if m.cross_vertical_synthesis)
    synthesis_rate = synthesis_count / total if total else 0.0

    # Weighted composite
    composite = (
        delegation_accuracy * 0.50
        + utilization_balance * 0.25
        + synthesis_rate * 0.25
    )

    return PrimaryFitness(
        delegation_accuracy=round(delegation_accuracy, 3),
        utilization_balance=round(utilization_balance, 3),
        synthesis_rate=round(synthesis_rate, 3),
        composite=round(composite, 3),
        tasks_scored=total,
        tasks_judged=len(judged),
    )


def score_team_lead(metrics: list[CoordinationMetrics]) -> TeamLeadFitness:
    """
    Score a Team Lead mind's coordination fitness for a session.

    Measures:
    - Agent selection quality: % of correct agent choices
    - Synthesis quality: did TL synthesize (not passthrough)?
    - Scratchpad continuity: did TL maintain the team scratchpad?
    - Delegation speed: average time to spawn agent
    """
    if not metrics:
        return TeamLeadFitness()

    tl_metrics = [m for m in metrics if m.role == Role.TEAM_LEAD]
    if not tl_metrics:
        return TeamLeadFitness()

    total = len(tl_metrics)

    # Agent selection accuracy
    judged = [m for m in tl_metrics if m.agent_selection_correct is not None]
    correct = sum(1 for m in judged if m.agent_selection_correct)
    selection_accuracy = correct / len(judged) if judged else 0.0

    # Synthesis rate
    synthesized = sum(1 for m in tl_metrics if m.result_synthesized)
    synthesis_rate = synthesized / total

    # Scratchpad continuity
    scratchpad_updates = sum(1 for m in tl_metrics if m.scratchpad_updated)
    scratchpad_rate = scratchpad_updates / total

    # Delegation speed (normalize: < 1s = 1.0, > 30s = 0.0)
    latencies = [m.delegation_latency_ms for m in tl_metrics if m.delegation_latency_ms > 0]
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        speed_score = max(0.0, 1.0 - avg_latency / 30000.0)
    else:
        speed_score = 0.0

    composite = (
        selection_accuracy * 0.35
        + synthesis_rate * 0.30
        + scratchpad_rate * 0.20
        + speed_score * 0.15
    )

    return TeamLeadFitness(
        agent_selection_accuracy=round(selection_accuracy, 3),
        synthesis_rate=round(synthesis_rate, 3),
        scratchpad_continuity=round(scratchpad_rate, 3),
        delegation_speed=round(speed_score, 3),
        composite=round(composite, 3),
        tasks_scored=total,
        tasks_judged=len(judged),
        avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
    )


def score_agent(metrics: list[CoordinationMetrics]) -> AgentFitness:
    """
    Score an Agent mind's operational fitness for a session.

    Measures:
    - Tool effectiveness: successful tool calls / total tool calls
    - Memory contribution: how many memories written
    - Verification compliance: did agent provide evidence with completion claims?
    - Task completion rate
    """
    if not metrics:
        return AgentFitness()

    agent_metrics = [m for m in metrics if m.role == Role.AGENT]
    if not agent_metrics:
        return AgentFitness()

    total = len(agent_metrics)

    # Tool effectiveness
    total_attempted = sum(m.tools_attempted for m in agent_metrics)
    total_succeeded = sum(m.tools_succeeded for m in agent_metrics)
    tool_effectiveness = total_succeeded / total_attempted if total_attempted else 0.0

    # Memory contribution (at least 1 write per 3 tasks is good)
    total_writes = sum(m.memory_writes for m in agent_metrics)
    ideal_writes = max(1, total / 3)
    memory_score = min(1.0, total_writes / ideal_writes)

    # Verification compliance
    verified = sum(1 for m in agent_metrics if m.verification_provided)
    verification_rate = verified / total

    # Task completion
    completed = sum(1 for m in agent_metrics if m.task_completed)
    completion_rate = completed / total

    composite = (
        tool_effectiveness * 0.30
        + memory_score * 0.20
        + verification_rate * 0.20
        + completion_rate * 0.30
    )

    return AgentFitness(
        tool_effectiveness=round(tool_effectiveness, 3),
        memory_contribution=round(memory_score, 3),
        verification_compliance=round(verification_rate, 3),
        completion_rate=round(completion_rate, 3),
        composite=round(composite, 3),
        tasks_scored=total,
        total_tool_calls=total_attempted,
        total_memory_writes=total_writes,
    )


def score_for_role(
    role: Role,
    metrics: list[CoordinationMetrics],
) -> PrimaryFitness | TeamLeadFitness | AgentFitness:
    """
    Dispatch to the correct fitness calculator based on role.

    This is the main entry point for fitness scoring.
    """
    if role == Role.PRIMARY:
        return score_primary(metrics)
    elif role == Role.TEAM_LEAD:
        return score_team_lead(metrics)
    elif role == Role.AGENT:
        return score_agent(metrics)
    else:
        raise ValueError(f"Unknown role: {role}")


# ---------------------------------------------------------------------------
# Fitness result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PrimaryFitness:
    """Fitness scores for a Primary mind."""

    delegation_accuracy: float = 0.0
    utilization_balance: float = 0.0
    synthesis_rate: float = 0.0
    composite: float = 0.0
    tasks_scored: int = 0
    tasks_judged: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": "primary",
            "delegation_accuracy": self.delegation_accuracy,
            "utilization_balance": self.utilization_balance,
            "synthesis_rate": self.synthesis_rate,
            "composite": self.composite,
            "tasks_scored": self.tasks_scored,
            "tasks_judged": self.tasks_judged,
        }


@dataclass
class TeamLeadFitness:
    """Fitness scores for a Team Lead mind."""

    agent_selection_accuracy: float = 0.0
    synthesis_rate: float = 0.0
    scratchpad_continuity: float = 0.0
    delegation_speed: float = 0.0
    composite: float = 0.0
    tasks_scored: int = 0
    tasks_judged: int = 0
    avg_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": "team_lead",
            "agent_selection_accuracy": self.agent_selection_accuracy,
            "synthesis_rate": self.synthesis_rate,
            "scratchpad_continuity": self.scratchpad_continuity,
            "delegation_speed": self.delegation_speed,
            "composite": self.composite,
            "tasks_scored": self.tasks_scored,
            "tasks_judged": self.tasks_judged,
            "avg_latency_ms": self.avg_latency_ms,
        }


@dataclass
class AgentFitness:
    """Fitness scores for an Agent mind."""

    tool_effectiveness: float = 0.0
    memory_contribution: float = 0.0
    verification_compliance: float = 0.0
    completion_rate: float = 0.0
    composite: float = 0.0
    tasks_scored: int = 0
    total_tool_calls: int = 0
    total_memory_writes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": "agent",
            "tool_effectiveness": self.tool_effectiveness,
            "memory_contribution": self.memory_contribution,
            "verification_compliance": self.verification_compliance,
            "completion_rate": self.completion_rate,
            "composite": self.composite,
            "tasks_scored": self.tasks_scored,
            "total_tool_calls": self.total_tool_calls,
            "total_memory_writes": self.total_memory_writes,
        }
