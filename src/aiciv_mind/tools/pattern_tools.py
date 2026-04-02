"""pattern_tools -- Scan Loop 1 memories for repeated patterns.

Bridges task-level errors (Loop 1) to evolution_log. When the same tool keeps
failing, that is SYSTEM not symptom. Detects patterns, suggests evolution entries.
"""
from __future__ import annotations

import json
from collections import Counter
from aiciv_mind.tools import ToolRegistry

_SCAN_DEFINITION: dict = {
    "name": "loop1_pattern_scan",
    "description": (
        "Scan recent Loop 1 task-learning memories for repeated patterns. "
        "Detects: recurring tool errors, frequently-used tool combinations, "
        "and repeated failure modes. Suggests evolution_log entries when "
        "patterns cross the threshold (3+ similar occurrences)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "threshold": {
                "type": "integer",
                "description": "Minimum occurrences to flag a pattern (default: 3)",
            },
            "lookback": {
                "type": "integer",
                "description": "Number of recent Loop 1 memories to scan (default: 50)",
            },
        },
    },
}


def _has_loop1_tag(mem: dict) -> bool:
    try:
        tags = json.loads(mem.get("tags", "[]"))
        return "loop-1" in tags
    except (json.JSONDecodeError, TypeError):
        return False


def _extract_error_line(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("Errors:") and line.strip() != "Errors: none":
            return line.strip()[:200]
    return None


def _make_scan_handler(memory_store, agent_id: str):
    def loop1_pattern_scan_handler(tool_input: dict) -> str:
        threshold = int(tool_input.get("threshold", 3))
        lookback = int(tool_input.get("lookback", 50))

        errors = memory_store.by_type("error", agent_id=agent_id, limit=lookback)
        learnings = memory_store.by_type("learning", agent_id=agent_id, limit=lookback)

        loop1_errors = [m for m in errors if _has_loop1_tag(m)]
        loop1_learnings = [m for m in learnings if _has_loop1_tag(m)]
        all_loop1 = loop1_errors + loop1_learnings

        if not all_loop1:
            return f"No Loop 1 memories found in recent {lookback} entries."

        suggestions: list[str] = []

        tool_error_counter: Counter = Counter()
        tool_error_lines: dict[str, list[str]] = {}
        for mem in loop1_errors:
            try:
                tags = json.loads(mem.get("tags", "[]"))
            except (json.JSONDecodeError, TypeError):
                tags = []
            tool_names = [t for t in tags if t not in ("loop-1", "task-learning")]
            err_line = _extract_error_line(mem.get("content", ""))
            for tool in tool_names:
                tool_error_counter[tool] += 1
                if err_line:
                    tool_error_lines.setdefault(tool, []).append(err_line)

        error_groups: dict[str, list[str]] = {}
        for mem in all_loop1:
            err_line = _extract_error_line(mem.get("content", ""))
            if err_line:
                key = err_line[:60]
                error_groups.setdefault(key, []).append(err_line)

        for tool, count in tool_error_counter.most_common():
            if count < threshold:
                break
            recent = tool_error_lines.get(tool, [])[:5]
            lines_block = "\n".join(f"  - {l}" for l in recent)
            common = recent[0][:80] if recent else "repeated failures"
            suggestions.append(
                f"## Pattern Detected: `{tool}` errors ({count} occurrences)\n\n"
                f"Recent errors:\n{lines_block}\n\n"
                f"Suggested evolution_log entry:\n"
                f"  change_type: architecture_change\n"
                f"  description: Repeated {tool} failures suggest systemic issue: {common}\n"
                f"  reasoning: {count} task-level errors with the same tool indicates "
                f"this is SYSTEM not symptom\n\n"
                f"To log: "
                f'evolution_log_write(change_type="architecture_change", '
                f'description="...", reasoning="...")'
            )

        for key, lines in error_groups.items():
            if len(lines) >= threshold:
                if any(key[:40] in s for s in suggestions):
                    continue  # already covered by tool-level suggestion
                sample = "\n".join(f"  - {l}" for l in lines[:5])
                suggestions.append(
                    f"## Pattern Detected: repeated error ({len(lines)} occurrences)\n\n"
                    f"Error prefix: `{key}`\n\nSamples:\n{sample}\n\n"
                    f"Suggested evolution_log entry:\n"
                    f"  change_type: architecture_change\n"
                    f"  description: Repeated failure pattern: {key[:80]}\n"
                    f"  reasoning: {len(lines)} occurrences indicates systemic issue\n\n"
                    f"To log: "
                    f'evolution_log_write(change_type="architecture_change", '
                    f'description="...", reasoning="...")'
                )

        if not suggestions:
            return (
                f"No repeated patterns detected in recent {len(all_loop1)} Loop 1 memories "
                f"(threshold: {threshold}). "
                f"Scanned {len(loop1_errors)} errors, {len(loop1_learnings)} learnings."
            )

        header = (
            f"# Loop 1 Pattern Scan Results\n\n"
            f"Scanned {len(all_loop1)} Loop 1 memories "
            f"({len(loop1_errors)} errors, {len(loop1_learnings)} learnings). "
            f"Threshold: {threshold}.\n\n"
        )
        return header + "\n---\n\n".join(suggestions)

    return loop1_pattern_scan_handler

def register_pattern_tools(
    registry: ToolRegistry, memory_store, agent_id: str = "primary",
) -> None:
    """Register loop1_pattern_scan."""
    registry.register(
        "loop1_pattern_scan", _SCAN_DEFINITION,
        _make_scan_handler(memory_store, agent_id), read_only=True,
    )
