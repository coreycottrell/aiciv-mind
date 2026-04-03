"""
aiciv_mind.pattern_detector — Runtime pattern detection for self-improvement.

Observes tool calls during a session and detects:
  1. Repeated tool sequences (same tools called in same order 3+ times)
  2. Error patterns (same tool fails 3+ times in a session)
  3. Context pressure events (memory injection growing over time)
  4. Idle patterns (long gaps between tool calls)

Designed to be called from PostToolUse hooks. Collected patterns are
available for the dream cycle to analyze and propose optimizations.

Usage:
    detector = PatternDetector(agent_id="primary")
    detector.observe(tool_name="bash", tool_input={...}, is_error=False, duration_ms=150)
    ...
    patterns = detector.detected_patterns()
    # [{"type": "tool_sequence", "sequence": ["memory_search", "memory_write"], "count": 4}, ...]
"""
from __future__ import annotations

import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolObservation:
    """A single observed tool call."""
    tool_name: str
    is_error: bool
    duration_ms: int
    timestamp: float


@dataclass
class DetectedPattern:
    """A pattern detected from observations."""
    pattern_type: str  # "tool_sequence" | "error_repeat" | "slow_tool" | "dominant_tool"
    description: str
    count: int
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.pattern_type,
            "description": self.description,
            "count": self.count,
            **self.details,
        }


class PatternDetector:
    """
    Observes tool calls and detects patterns within a session.

    Call observe() after each tool execution. Call detected_patterns()
    at session end to get a list of patterns found.
    """

    # Minimum occurrences to qualify as a pattern
    SEQUENCE_THRESHOLD: int = 3
    ERROR_THRESHOLD: int = 3
    # Tool is "slow" if it averages > this many ms
    SLOW_THRESHOLD_MS: int = 5000
    # Tool is "dominant" if it accounts for > this % of all calls
    DOMINANT_THRESHOLD: float = 0.4

    def __init__(self, agent_id: str = "unknown") -> None:
        self._agent_id = agent_id
        self._observations: list[ToolObservation] = []
        self._error_counts: Counter = Counter()
        self._tool_durations: dict[str, list[int]] = {}

    def observe(
        self,
        tool_name: str,
        is_error: bool = False,
        duration_ms: int = 0,
        tool_input: dict | None = None,
    ) -> None:
        """Record a tool call observation."""
        obs = ToolObservation(
            tool_name=tool_name,
            is_error=is_error,
            duration_ms=duration_ms,
            timestamp=time.time(),
        )
        self._observations.append(obs)

        if is_error:
            self._error_counts[tool_name] += 1

        self._tool_durations.setdefault(tool_name, []).append(duration_ms)

    def detected_patterns(self) -> list[DetectedPattern]:
        """Analyze observations and return detected patterns."""
        patterns: list[DetectedPattern] = []

        patterns.extend(self._detect_sequences())
        patterns.extend(self._detect_error_repeats())
        patterns.extend(self._detect_slow_tools())
        patterns.extend(self._detect_dominant_tools())

        return patterns

    def _detect_sequences(self) -> list[DetectedPattern]:
        """Detect repeated tool call sequences (bigrams and trigrams)."""
        if len(self._observations) < 3:
            return []

        tool_names = [obs.tool_name for obs in self._observations]
        patterns: list[DetectedPattern] = []

        # Bigrams
        bigrams: Counter = Counter()
        for i in range(len(tool_names) - 1):
            bigram = (tool_names[i], tool_names[i + 1])
            bigrams[bigram] += 1

        for bigram, count in bigrams.most_common():
            if count >= self.SEQUENCE_THRESHOLD:
                patterns.append(DetectedPattern(
                    pattern_type="tool_sequence",
                    description=f"{bigram[0]} → {bigram[1]} repeated {count} times",
                    count=count,
                    details={"sequence": list(bigram), "length": 2},
                ))

        # Trigrams
        if len(tool_names) >= 4:
            trigrams: Counter = Counter()
            for i in range(len(tool_names) - 2):
                trigram = (tool_names[i], tool_names[i + 1], tool_names[i + 2])
                trigrams[trigram] += 1

            for trigram, count in trigrams.most_common():
                if count >= self.SEQUENCE_THRESHOLD:
                    patterns.append(DetectedPattern(
                        pattern_type="tool_sequence",
                        description=f"{' → '.join(trigram)} repeated {count} times",
                        count=count,
                        details={"sequence": list(trigram), "length": 3},
                    ))

        return patterns

    def _detect_error_repeats(self) -> list[DetectedPattern]:
        """Detect tools that fail repeatedly."""
        patterns: list[DetectedPattern] = []
        for tool_name, count in self._error_counts.items():
            if count >= self.ERROR_THRESHOLD:
                patterns.append(DetectedPattern(
                    pattern_type="error_repeat",
                    description=f"{tool_name} failed {count} times",
                    count=count,
                    details={"tool": tool_name},
                ))
        return patterns

    def _detect_slow_tools(self) -> list[DetectedPattern]:
        """Detect tools with high average latency."""
        patterns: list[DetectedPattern] = []
        for tool_name, durations in self._tool_durations.items():
            if not durations:
                continue
            avg_ms = sum(durations) / len(durations)
            if avg_ms > self.SLOW_THRESHOLD_MS and len(durations) >= 2:
                patterns.append(DetectedPattern(
                    pattern_type="slow_tool",
                    description=f"{tool_name} averages {avg_ms:.0f}ms ({len(durations)} calls)",
                    count=len(durations),
                    details={
                        "tool": tool_name,
                        "avg_ms": int(avg_ms),
                        "max_ms": max(durations),
                        "call_count": len(durations),
                    },
                ))
        return patterns

    def _detect_dominant_tools(self) -> list[DetectedPattern]:
        """Detect tools that dominate the session's tool calls."""
        if len(self._observations) < 5:
            return []

        patterns: list[DetectedPattern] = []
        tool_counts = Counter(obs.tool_name for obs in self._observations)
        total = len(self._observations)

        for tool_name, count in tool_counts.most_common():
            ratio = count / total
            if ratio >= self.DOMINANT_THRESHOLD:
                patterns.append(DetectedPattern(
                    pattern_type="dominant_tool",
                    description=f"{tool_name} used {count}/{total} times ({ratio:.0%})",
                    count=count,
                    details={
                        "tool": tool_name,
                        "ratio": round(ratio, 3),
                        "total_calls": total,
                    },
                ))

        return patterns

    def summary(self) -> str:
        """Return a human-readable summary of detected patterns."""
        patterns = self.detected_patterns()
        if not patterns:
            return f"No patterns detected ({len(self._observations)} observations)"

        lines = [f"Detected {len(patterns)} pattern(s) from {len(self._observations)} observations:"]
        for p in patterns:
            lines.append(f"  [{p.pattern_type}] {p.description}")
        return "\n".join(lines)

    def to_jsonl(self, path: str | Path) -> int:
        """Write detected patterns to JSONL file. Returns count written."""
        patterns = self.detected_patterns()
        if not patterns:
            return 0

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for p in patterns:
                record = {
                    "agent_id": self._agent_id,
                    "timestamp": time.time(),
                    **p.to_dict(),
                }
                f.write(json.dumps(record, default=str) + "\n")
        return len(patterns)

    @property
    def observation_count(self) -> int:
        return len(self._observations)

    @property
    def error_count(self) -> int:
        return sum(self._error_counts.values())
