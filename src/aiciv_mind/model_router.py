"""
aiciv_mind.model_router — Dynamic model selection per task.

Root is locked to one model. This router lets it pick models per-task:
  - Cheap/fast tasks → small model (minimax-m27)
  - Reasoning tasks → strong model (kimi-k2)
  - Code tasks → code model (qwen2.5-coder)

The router starts with heuristic rules and evolves via performance tracking.
Over time, Root learns which models work best for which task types.

Principle 11: Distributed Intelligence at All Layers.
The routing layer itself becomes intelligent.

Usage:
    router = ModelRouter(manifest)
    model = router.select(task="analyze this code for bugs")
    # → "qwen2.5-coder" (code task detected)

    router.record_outcome(task, model, success=True, tokens_used=1200)
    # → updates performance stats for future routing decisions
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ModelProfile:
    """Profile for a model available via LiteLLM."""
    model_id: str
    strengths: list[str]  # task types this model excels at
    cost_tier: str  # "cheap", "medium", "expensive"
    speed_tier: str  # "fast", "medium", "slow"
    max_tokens: int = 8192


@dataclass
class RoutingOutcome:
    """Record of a model's performance on a task."""
    task_type: str
    model_id: str
    success: bool
    tokens_used: int
    response_quality: float = 0.0  # 0-1, default unknown


# Default model profiles for the LiteLLM proxy stack
DEFAULT_PROFILES: list[ModelProfile] = [
    ModelProfile(
        model_id="minimax-m27",
        strengths=["general", "conversation", "memory-ops", "file-ops"],
        cost_tier="cheap",
        speed_tier="fast",
    ),
    ModelProfile(
        model_id="kimi-k2",
        strengths=["reasoning", "analysis", "planning", "research", "math"],
        cost_tier="medium",
        speed_tier="medium",
    ),
    ModelProfile(
        model_id="qwen2.5-coder",
        strengths=["code", "debugging", "code-review", "refactoring"],
        cost_tier="cheap",
        speed_tier="medium",
        max_tokens=4096,
    ),
]

# Task type detection patterns
TASK_PATTERNS: dict[str, list[str]] = {
    "code": [r"\bcode\b", r"\bfunction\b", r"\bbug\b", r"\bfix\b", r"\brefactor\b",
             r"\bimport\b", r"\.py\b", r"\bclass\b", r"\bdef\b", r"\btest\b"],
    "reasoning": [r"\banalyze\b", r"\bcompare\b", r"\bwhy\b", r"\bexplain\b",
                  r"\bplan\b", r"\bdesign\b", r"\barchitect\b", r"\bstrategy\b"],
    "research": [r"\bresearch\b", r"\bsearch\b", r"\bfind\b", r"\binvestigate\b",
                 r"\breview\b", r"\baudit\b"],
    "memory-ops": [r"\bremember\b", r"\bmemory\b", r"\bscratchpad\b", r"\bhandoff\b",
                   r"\bsearch.*memor\b"],
    "conversation": [r"\bhello\b", r"\bhi\b", r"\btell me\b", r"\bwhat do you\b",
                     r"\bhow are\b"],
    "file-ops": [r"\bread\b.*file", r"\bwrite\b.*file", r"\bcreate\b.*file",
                 r"\bedit\b", r"\bgrep\b", r"\bglob\b"],
    "hub": [r"\bhub\b", r"\bpost\b", r"\bthread\b", r"\broom\b", r"\bagora\b"],
    "math": [r"\bcalculate\b", r"\bmath\b", r"\d+\s*[\+\-\*\/]\s*\d+", r"\bsum\b"],
}


class ModelRouter:
    """
    Dynamic model selection based on task classification + performance history.

    Phase 1 (current): Heuristic pattern matching
    Phase 2 (future): Performance-weighted selection from tracked outcomes
    """

    def __init__(
        self,
        profiles: list[ModelProfile] | None = None,
        default_model: str = "minimax-m27",
        stats_path: str | None = None,
    ) -> None:
        self._profiles = {p.model_id: p for p in (profiles or DEFAULT_PROFILES)}
        self._default = default_model
        self._stats_path = stats_path
        self._outcomes: list[RoutingOutcome] = []

        # Load historical stats if available
        if stats_path and Path(stats_path).exists():
            try:
                data = json.loads(Path(stats_path).read_text())
                self._outcomes = [RoutingOutcome(**o) for o in data]
            except Exception:
                pass

    def classify_task(self, task: str) -> str:
        """Classify a task string into a task type using pattern matching."""
        task_lower = task.lower()
        scores: dict[str, int] = {}

        for task_type, patterns in TASK_PATTERNS.items():
            score = sum(1 for p in patterns if re.search(p, task_lower))
            if score > 0:
                scores[task_type] = score

        if not scores:
            return "general"

        return max(scores, key=scores.get)

    def select(self, task: str, override: str | None = None) -> str:
        """
        Select the best model for a given task.

        Args:
            task: The task description
            override: If set, use this model regardless of classification

        Returns:
            model_id string for LiteLLM
        """
        if override:
            return override

        task_type = self.classify_task(task)

        # Find profiles that list this task type as a strength
        candidates = [
            p for p in self._profiles.values()
            if task_type in p.strengths
        ]

        if not candidates:
            return self._default

        # Phase 1: prefer cheap+fast when multiple candidates match
        # Phase 2 (future): weight by historical success rate
        candidates.sort(key=lambda p: (
            0 if p.cost_tier == "cheap" else 1 if p.cost_tier == "medium" else 2,
            0 if p.speed_tier == "fast" else 1 if p.speed_tier == "medium" else 2,
        ))

        return candidates[0].model_id

    def record_outcome(
        self,
        task: str,
        model_id: str,
        success: bool,
        tokens_used: int = 0,
        quality: float = 0.0,
    ) -> None:
        """Record the outcome of a model's performance on a task."""
        task_type = self.classify_task(task)
        outcome = RoutingOutcome(
            task_type=task_type,
            model_id=model_id,
            success=success,
            tokens_used=tokens_used,
            response_quality=quality,
        )
        self._outcomes.append(outcome)

        # Persist
        if self._stats_path:
            try:
                data = [
                    {
                        "task_type": o.task_type,
                        "model_id": o.model_id,
                        "success": o.success,
                        "tokens_used": o.tokens_used,
                        "response_quality": o.response_quality,
                    }
                    for o in self._outcomes[-500:]  # keep last 500
                ]
                Path(self._stats_path).write_text(json.dumps(data, indent=2))
            except Exception:
                pass

    def get_stats(self) -> dict:
        """Return aggregated stats per model per task type."""
        stats: dict[str, dict] = {}
        for o in self._outcomes:
            key = f"{o.model_id}:{o.task_type}"
            if key not in stats:
                stats[key] = {"model": o.model_id, "task_type": o.task_type,
                              "total": 0, "success": 0, "tokens": 0}
            stats[key]["total"] += 1
            if o.success:
                stats[key]["success"] += 1
            stats[key]["tokens"] += o.tokens_used
        return stats
