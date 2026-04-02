"""
aiciv_mind.planning — Task complexity classification and planning gates.

Principle 3: GO SLOW TO GO FAST.

Every task passes through a planning gate whose depth scales with the task's
complexity.  The gate fires BEFORE tool execution begins — between "I received
a task" and "I start executing."

Complexity Levels:
    TRIVIAL   — memory check only (< 1s)
    SIMPLE    — memory check + brief plan (2-5s)
    MEDIUM    — memory check + plan + competing hypotheses (10-30s)
    COMPLEX   — spawn a planning sub-mind (30s-5m)
    VARIABLE  — spawn multiple competing planners (1-10m)
"""

from __future__ import annotations

import enum
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Complexity classification
# ---------------------------------------------------------------------------


class TaskComplexity(enum.Enum):
    """Task complexity levels — determines planning gate depth."""

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    VARIABLE = "variable"

    @property
    def gate_depth(self) -> int:
        """Numeric depth 0-4 for ordering and comparison."""
        return list(TaskComplexity).index(self)


@dataclass
class ClassificationResult:
    """Output of the complexity classifier."""

    complexity: TaskComplexity
    confidence: float  # 0.0 - 1.0
    signals: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


# Signal weights for the heuristic classifier
_WEIGHTS = {
    "length": 0.20,          # Task text length
    "multi_step": 0.25,      # Multi-step indicators
    "complexity_keywords": 0.25,  # Complex action keywords
    "novelty": 0.15,         # Novel/unknown indicators
    "reversibility": 0.15,   # Irreversible action signals
}

# Keyword groups
_COMPLEX_KEYWORDS = {
    "architect", "design", "implement", "build", "refactor", "migrate",
    "rewrite", "overhaul", "restructure", "integrate", "deploy",
    "research", "investigate", "analyze", "evaluate", "compare",
    "proposal", "strategy", "roadmap", "plan",
}

_MULTI_STEP_PATTERNS = [
    r"\b(?:then|after that|next|finally|first|second|third|step \d)\b",
    r"\b\d+\.\s",              # Numbered lists
    r"\band\s+then\b",
    r"\bfollowed by\b",
]

_NOVELTY_KEYWORDS = {
    "never", "first time", "new", "unknown", "unfamiliar", "novel",
    "experimental", "prototype", "explore", "spike",
}

_IRREVERSIBLE_KEYWORDS = {
    "delete", "remove", "drop", "destroy", "reset", "force",
    "migrate", "deploy", "publish", "send", "push",
}


def classify_task(
    task: str,
    memory_hit_count: int = 0,
    prior_success_rate: float | None = None,
) -> ClassificationResult:
    """
    Classify task complexity using weighted heuristic signals.

    Args:
        task: The task description text.
        memory_hit_count: Number of relevant memories found for this task.
            Many hits → familiar territory → lower complexity.
        prior_success_rate: If known, historical success rate on similar tasks.
            High rate → lower complexity.

    Returns:
        ClassificationResult with complexity level, confidence, and signal breakdown.
    """
    task_lower = task.lower()
    words = task_lower.split()
    word_count = len(words)
    signals: dict[str, Any] = {}

    # --- Signal 1: Length ---
    if word_count <= 10:
        length_score = 0.0
    elif word_count <= 30:
        length_score = 0.25
    elif word_count <= 80:
        length_score = 0.50
    elif word_count <= 200:
        length_score = 0.75
    else:
        length_score = 1.0
    signals["length"] = {"word_count": word_count, "score": length_score}

    # --- Signal 2: Multi-step indicators ---
    step_matches = 0
    for pattern in _MULTI_STEP_PATTERNS:
        step_matches += len(re.findall(pattern, task_lower))
    multi_step_score = min(1.0, step_matches / 3.0)
    signals["multi_step"] = {"matches": step_matches, "score": multi_step_score}

    # --- Signal 3: Complexity keywords ---
    found_complex = {w for w in _COMPLEX_KEYWORDS if w in task_lower}
    complexity_kw_score = min(1.0, len(found_complex) / 3.0)
    signals["complexity_keywords"] = {
        "found": sorted(found_complex),
        "score": complexity_kw_score,
    }

    # --- Signal 4: Novelty ---
    found_novelty = {w for w in _NOVELTY_KEYWORDS if w in task_lower}
    # Low memory hits also signal novelty
    if memory_hit_count == 0:
        novelty_boost = 0.4
    elif memory_hit_count <= 2:
        novelty_boost = 0.2
    else:
        novelty_boost = 0.0
    novelty_score = min(1.0, len(found_novelty) * 0.3 + novelty_boost)
    signals["novelty"] = {
        "found": sorted(found_novelty),
        "memory_hits": memory_hit_count,
        "score": novelty_score,
    }

    # --- Signal 5: Reversibility ---
    found_irreversible = {w for w in _IRREVERSIBLE_KEYWORDS if w in task_lower}
    reversibility_score = min(1.0, len(found_irreversible) / 2.0)
    signals["reversibility"] = {
        "found": sorted(found_irreversible),
        "score": reversibility_score,
    }

    # --- Weighted sum ---
    weighted = (
        _WEIGHTS["length"] * length_score
        + _WEIGHTS["multi_step"] * multi_step_score
        + _WEIGHTS["complexity_keywords"] * complexity_kw_score
        + _WEIGHTS["novelty"] * novelty_score
        + _WEIGHTS["reversibility"] * reversibility_score
    )

    # --- Override: prior success rate pulls complexity down ---
    if prior_success_rate is not None and prior_success_rate > 0.8:
        weighted *= 0.7  # Familiar pattern — pull toward simpler
        signals["prior_success_override"] = prior_success_rate

    # --- Map weighted score to complexity level ---
    if weighted < 0.15:
        complexity = TaskComplexity.TRIVIAL
    elif weighted < 0.35:
        complexity = TaskComplexity.SIMPLE
    elif weighted < 0.55:
        complexity = TaskComplexity.MEDIUM
    elif weighted < 0.75:
        complexity = TaskComplexity.COMPLEX
    else:
        complexity = TaskComplexity.VARIABLE

    # Confidence is how far from the boundary we are
    boundaries = [0.0, 0.15, 0.35, 0.55, 0.75, 1.0]
    idx = complexity.gate_depth
    low, high = boundaries[idx], boundaries[idx + 1]
    mid = (low + high) / 2
    distance_from_mid = abs(weighted - mid)
    half_range = (high - low) / 2
    confidence = min(1.0, 0.5 + distance_from_mid / half_range * 0.5) if half_range > 0 else 0.5

    reason = (
        f"score={weighted:.2f} → {complexity.value} "
        f"(length={length_score:.2f}, multi_step={multi_step_score:.2f}, "
        f"keywords={complexity_kw_score:.2f}, novelty={novelty_score:.2f}, "
        f"reversibility={reversibility_score:.2f})"
    )

    return ClassificationResult(
        complexity=complexity,
        confidence=round(confidence, 3),
        signals=signals,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Planning gate output
# ---------------------------------------------------------------------------


@dataclass
class PlanningResult:
    """Output of the planning gate — injected into the mind's system prompt."""

    complexity: TaskComplexity
    classification: ClassificationResult
    plan: str  # Planning text to inject into system prompt
    memories_consulted: int
    elapsed_ms: float
    competing_hypotheses: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PlanningGate — orchestrates the gate based on complexity
# ---------------------------------------------------------------------------


class PlanningGate:
    """
    Enforces planning depth proportional to task complexity.

    Wired into Mind._run_task_body() — fires BEFORE tool execution begins.
    """

    def __init__(
        self,
        memory_store: Any = None,
        agent_id: str = "",
        enabled: bool = True,
    ):
        self._memory = memory_store
        self._agent_id = agent_id
        self._enabled = enabled

    def run(self, task: str) -> PlanningResult:
        """
        Execute the planning gate for a task.

        1. Classify complexity.
        2. Search memory for prior similar tasks.
        3. Build planning context proportional to complexity.
        4. Return PlanningResult with plan text for prompt injection.
        """
        if not self._enabled:
            classification = ClassificationResult(
                complexity=TaskComplexity.TRIVIAL,
                confidence=1.0,
                reason="planning gate disabled",
            )
            return PlanningResult(
                complexity=TaskComplexity.TRIVIAL,
                classification=classification,
                plan="",
                memories_consulted=0,
                elapsed_ms=0.0,
            )

        start = time.monotonic()

        # Step 1: Quick memory search to inform classification
        memory_hits = []
        if self._memory and self._agent_id:
            memory_hits = self._memory.search(
                query=task,
                agent_id=self._agent_id,
                limit=5,
            )

        # Step 2: Classify
        classification = classify_task(
            task=task,
            memory_hit_count=len(memory_hits),
        )

        # Step 3: Build plan context based on complexity
        plan = self._build_plan(classification, memory_hits, task)

        elapsed_ms = (time.monotonic() - start) * 1000

        logger.info(
            "[%s] Planning gate: %s (%.0fms) — %s",
            self._agent_id,
            classification.complexity.value,
            elapsed_ms,
            classification.reason,
        )

        return PlanningResult(
            complexity=classification.complexity,
            classification=classification,
            plan=plan,
            memories_consulted=len(memory_hits),
            elapsed_ms=elapsed_ms,
        )

    def _build_plan(
        self,
        classification: ClassificationResult,
        memory_hits: list[dict[str, Any]],
        task: str,
    ) -> str:
        """Build planning context text proportional to complexity."""
        complexity = classification.complexity

        if complexity == TaskComplexity.TRIVIAL:
            # Memory check only — no plan text needed
            if memory_hits:
                return (
                    f"## Planning Gate: {complexity.value}\n"
                    f"*{len(memory_hits)} relevant memories found — "
                    f"familiar territory. Proceed directly.*\n"
                )
            return ""

        parts = [
            f"## Planning Gate: {complexity.value}",
            f"*Classification: {classification.reason}*\n",
        ]

        # Memory context (all levels above trivial)
        if memory_hits:
            parts.append(f"**Prior experience**: {len(memory_hits)} relevant memories found.")
            for m in memory_hits[:3]:  # Show top 3 at most
                title = m.get("title", "untitled")
                access_count = m.get("access_count", 0)
                parts.append(f"  - {title} *(accessed {access_count}x)*")
        else:
            parts.append("**Prior experience**: None found — novel territory.")

        # Brief plan (SIMPLE+)
        if complexity.gate_depth >= TaskComplexity.SIMPLE.gate_depth:
            parts.append(
                "\n**Planning instruction**: Before executing, outline your approach "
                "in 2-4 steps. State what you'll do and why."
            )

        # Competing hypotheses (MEDIUM+)
        if complexity.gate_depth >= TaskComplexity.MEDIUM.gate_depth:
            parts.append(
                "**Competing hypotheses**: Consider at least 2 different approaches. "
                "State which you'll try first and why. If the first approach fails "
                "or stalls, switch to the alternative."
            )

        # Sub-mind recommendation (COMPLEX+)
        if complexity.gate_depth >= TaskComplexity.COMPLEX.gate_depth:
            parts.append(
                "\n**Complexity warning**: This task is complex enough to warrant "
                "spawning a planning sub-mind with fresh context. Consider breaking "
                "it into sub-tasks before proceeding."
            )

        # Variable/Novel (VARIABLE)
        if complexity == TaskComplexity.VARIABLE:
            parts.append(
                "**Novel task**: Multiple approaches should be explored in parallel. "
                "Consider spawning competing planners if sub-mind spawning is available."
            )

        return "\n".join(parts) + "\n"
