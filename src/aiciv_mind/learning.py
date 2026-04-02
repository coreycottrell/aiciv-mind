"""
aiciv_mind.learning — Self-improving loop (Principle 7: The Hyperagent Principle).

Three nested learning loops:
    Loop 1 — Task-Level:   After every task, record what worked/didn't.
    Loop 2 — Session-Level: At session end, extract cross-task patterns.
    Loop 3 — Civilization:  Dream Mode (see dream_cycle.py).

This module provides:
    - TaskOutcome: structured record of a completed task
    - SessionLearner: accumulates task outcomes, produces session-level insights
    - Meta-metrics: tracks whether the learning process itself is improving
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task-level outcome (Loop 1)
# ---------------------------------------------------------------------------


@dataclass
class TaskOutcome:
    """Structured record of a completed task — the raw material for learning."""

    task: str
    result: str
    tools_used: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    tool_call_count: int = 0
    elapsed_s: float = 0.0

    # Planning gate feedback
    planned_complexity: str = "unknown"  # From P3 classifier
    plan_was_adequate: bool | None = None  # Did the plan match reality?

    # Verification feedback
    verification_outcome: str = "none"  # From P9: approved/challenged/blocked
    verification_challenges: list[str] = field(default_factory=list)

    # Memory feedback
    memories_consulted: int = 0
    memory_was_useful: bool | None = None  # Did injected memories actually help?

    @property
    def succeeded(self) -> bool:
        """Task succeeded if no tool errors and result is non-trivial."""
        return len(self.tool_errors) == 0 and len(self.result.strip()) >= 20

    @property
    def efficiency_score(self) -> float:
        """
        Rough efficiency: result quality vs. resource expenditure.
        Higher = more efficient.  Range 0.0 - 1.0.
        """
        if self.tool_call_count == 0:
            return 0.0
        # Penalize errors, reward short tool chains
        error_penalty = min(1.0, len(self.tool_errors) * 0.3)
        # Ideal: 2-5 tool calls.  More than 10 = diminishing returns.
        call_efficiency = min(1.0, 5.0 / max(self.tool_call_count, 1))
        return max(0.0, (call_efficiency - error_penalty))


# ---------------------------------------------------------------------------
# Session-level learner (Loop 2)
# ---------------------------------------------------------------------------


class SessionLearner:
    """
    Accumulates task outcomes during a session and produces session-level insights.

    Wired into Mind — receives task outcomes after each task completes.
    At session end, `summarize()` produces cross-task learnings.
    """

    def __init__(self, agent_id: str = "", data_dir: Path | None = None):
        self._agent_id = agent_id
        self._outcomes: list[TaskOutcome] = []
        self._session_start = time.monotonic()
        self._data_dir = data_dir

    def record(self, outcome: TaskOutcome) -> None:
        """Record a completed task outcome."""
        self._outcomes.append(outcome)

    @property
    def task_count(self) -> int:
        return len(self._outcomes)

    def summarize(self) -> SessionSummary:
        """
        Produce session-level learning summary (Loop 2).

        Analyzes all task outcomes for cross-cutting patterns:
        - Success rate, efficiency trends
        - Most-used tools, most-erroring tools
        - Planning accuracy, verification patterns
        - Memory usefulness
        """
        if not self._outcomes:
            return SessionSummary(task_count=0)

        total = len(self._outcomes)
        succeeded = sum(1 for o in self._outcomes if o.succeeded)
        total_tool_calls = sum(o.tool_call_count for o in self._outcomes)
        total_errors = sum(len(o.tool_errors) for o in self._outcomes)
        elapsed = time.monotonic() - self._session_start

        # Tool frequency
        tool_freq: dict[str, int] = {}
        tool_error_freq: dict[str, int] = {}
        for o in self._outcomes:
            for t in o.tools_used:
                tool_freq[t] = tool_freq.get(t, 0) + 1
            for e in o.tool_errors:
                # Extract tool name from error if possible
                for t in o.tools_used:
                    if t.lower() in e.lower():
                        tool_error_freq[t] = tool_error_freq.get(t, 0) + 1

        # Planning accuracy
        plan_adequate_count = sum(
            1 for o in self._outcomes
            if o.plan_was_adequate is True
        )
        plan_inadequate_count = sum(
            1 for o in self._outcomes
            if o.plan_was_adequate is False
        )
        plan_unknown = total - plan_adequate_count - plan_inadequate_count

        # Verification patterns
        ver_approved = sum(1 for o in self._outcomes if o.verification_outcome == "approved")
        ver_challenged = sum(1 for o in self._outcomes if o.verification_outcome == "challenged")
        ver_blocked = sum(1 for o in self._outcomes if o.verification_outcome == "blocked")

        # Complexity distribution
        complexity_dist: dict[str, int] = {}
        for o in self._outcomes:
            c = o.planned_complexity
            complexity_dist[c] = complexity_dist.get(c, 0) + 1

        # Average efficiency
        efficiencies = [o.efficiency_score for o in self._outcomes if o.tool_call_count > 0]
        avg_efficiency = sum(efficiencies) / len(efficiencies) if efficiencies else 0.0

        # Memory usefulness
        memory_useful = sum(1 for o in self._outcomes if o.memory_was_useful is True)
        memory_not_useful = sum(1 for o in self._outcomes if o.memory_was_useful is False)

        # Build insights
        insights: list[str] = []

        if total_errors > total * 0.3:
            insights.append(
                f"High error rate: {total_errors} tool errors across {total} tasks. "
                "Review tool configurations or add pre-flight checks."
            )

        if plan_inadequate_count > plan_adequate_count and plan_inadequate_count >= 2:
            insights.append(
                f"Planning accuracy low: {plan_inadequate_count} inadequate plans vs "
                f"{plan_adequate_count} adequate. Consider adjusting complexity thresholds."
            )

        if ver_challenged > ver_approved and ver_challenged >= 2:
            insights.append(
                f"Verification challenges high: {ver_challenged} challenged vs "
                f"{ver_approved} approved. Quality checks are catching issues — "
                "this might indicate the mind is rushing."
            )

        # Identify most-erroring tool
        if tool_error_freq:
            worst_tool = max(tool_error_freq, key=tool_error_freq.get)  # type: ignore[arg-type]
            if tool_error_freq[worst_tool] >= 3:
                insights.append(
                    f"Tool '{worst_tool}' errored {tool_error_freq[worst_tool]} times. "
                    "Consider adding to blocked_tools or reviewing its implementation."
                )

        if avg_efficiency < 0.3 and total >= 3:
            insights.append(
                f"Low average efficiency ({avg_efficiency:.2f}). "
                "Tasks are using many tool calls with frequent errors."
            )

        if memory_not_useful > memory_useful and memory_not_useful >= 2:
            insights.append(
                "Memory injection was frequently not useful. "
                "Consider refining search queries or adjusting max_context_memories."
            )

        return SessionSummary(
            task_count=total,
            success_count=succeeded,
            success_rate=round(succeeded / total, 3),
            total_tool_calls=total_tool_calls,
            total_errors=total_errors,
            elapsed_s=round(elapsed, 1),
            avg_efficiency=round(avg_efficiency, 3),
            most_used_tools=sorted(tool_freq.items(), key=lambda x: -x[1])[:5],
            most_erroring_tools=sorted(tool_error_freq.items(), key=lambda x: -x[1])[:3],
            complexity_distribution=complexity_dist,
            planning_accuracy={
                "adequate": plan_adequate_count,
                "inadequate": plan_inadequate_count,
                "unknown": plan_unknown,
            },
            verification_stats={
                "approved": ver_approved,
                "challenged": ver_challenged,
                "blocked": ver_blocked,
            },
            memory_usefulness={
                "useful": memory_useful,
                "not_useful": memory_not_useful,
            },
            insights=insights,
        )

    def write_session_learning(self, memory_store: Any) -> str | None:
        """
        Write a session-level learning memory (Loop 2 → Memory).

        Returns the memory ID if written, None if skipped.
        """
        summary = self.summarize()
        if summary.task_count < 2:
            return None  # Not enough data to learn from

        from aiciv_mind.memory import Memory

        content_parts = [
            f"Session: {summary.task_count} tasks, "
            f"{summary.success_count} succeeded ({summary.success_rate:.0%})",
            f"Efficiency: {summary.avg_efficiency:.2f} avg",
            f"Tool calls: {summary.total_tool_calls}, errors: {summary.total_errors}",
            f"Duration: {summary.elapsed_s:.0f}s",
        ]

        if summary.insights:
            content_parts.append("\nInsights:")
            for insight in summary.insights:
                content_parts.append(f"  - {insight}")

        if summary.most_used_tools:
            tools_str = ", ".join(f"{t}({c}x)" for t, c in summary.most_used_tools[:3])
            content_parts.append(f"\nTop tools: {tools_str}")

        content = "\n".join(content_parts)

        mem = Memory(
            agent_id=self._agent_id,
            title=f"Session learning: {summary.task_count} tasks, "
                  f"{summary.success_rate:.0%} success",
            content=content,
            memory_type="learning",
            tags=["loop-2", "session-learning"],
        )
        memory_store.store(mem)

        logger.info(
            "[%s] Session learning written: %d tasks, %.0f%% success, "
            "%d insights",
            self._agent_id,
            summary.task_count,
            summary.success_rate * 100,
            len(summary.insights),
        )

        return mem.id


# ---------------------------------------------------------------------------
# Session summary
# ---------------------------------------------------------------------------


@dataclass
class SessionSummary:
    """Cross-task analysis from a session — the output of Loop 2."""

    task_count: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    total_tool_calls: int = 0
    total_errors: int = 0
    elapsed_s: float = 0.0
    avg_efficiency: float = 0.0
    most_used_tools: list[tuple[str, int]] = field(default_factory=list)
    most_erroring_tools: list[tuple[str, int]] = field(default_factory=list)
    complexity_distribution: dict[str, int] = field(default_factory=dict)
    planning_accuracy: dict[str, int] = field(default_factory=dict)
    verification_stats: dict[str, int] = field(default_factory=dict)
    memory_usefulness: dict[str, int] = field(default_factory=dict)
    insights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONL logging."""
        return {
            "task_count": self.task_count,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "total_tool_calls": self.total_tool_calls,
            "total_errors": self.total_errors,
            "elapsed_s": self.elapsed_s,
            "avg_efficiency": self.avg_efficiency,
            "most_used_tools": self.most_used_tools,
            "complexity_distribution": self.complexity_distribution,
            "planning_accuracy": self.planning_accuracy,
            "verification_stats": self.verification_stats,
            "memory_usefulness": self.memory_usefulness,
            "insights": self.insights,
        }
