"""
aiciv_mind.tools.verification_tools — verify_completion tool (P9).

Exposes the CompletionProtocol as a tool so the mind can manually verify
completion claims. Also provides post-response auto-verification.

Tools:
    verify_completion — Manually verify a task completion with evidence
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.verification import (
    CompletionProtocol,
    Evidence,
    VerificationOutcome,
    detect_completion_signal,
    extract_evidence,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

VERIFY_COMPLETION_DEFINITION: dict = {
    "name": "verify_completion",
    "description": (
        "Verify a completion claim before marking a task as done. "
        "Runs the Red Team checklist: challenges assumptions, demands evidence, "
        "checks memory for contradictions, evaluates complexity vs approach. "
        "Returns APPROVED, CHALLENGED (with specific questions), or BLOCKED. "
        "Use this before claiming any significant task is complete."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Original task description.",
            },
            "result": {
                "type": "string",
                "description": "Claimed completion result — what was done.",
            },
            "evidence": {
                "type": "array",
                "description": (
                    "Evidence items. Each item: {description, type, confidence}. "
                    "Types: test_pass, file_written, api_response, manual_check, none."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "type": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                },
            },
            "complexity": {
                "type": "string",
                "description": "Task complexity: trivial, simple, medium, complex, variable.",
                "enum": ["trivial", "simple", "medium", "complex", "variable"],
            },
        },
        "required": ["task", "result"],
    },
}


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


def _make_verify_handler(protocol: CompletionProtocol):
    """Create a verify_completion handler closed over the given protocol."""

    def handler(tool_input: dict) -> str:
        task = tool_input.get("task", "")
        result = tool_input.get("result", "")
        complexity = tool_input.get("complexity", "simple")

        # Parse evidence from input
        evidence_items = []
        for item in tool_input.get("evidence", []):
            evidence_items.append(
                Evidence(
                    description=item.get("description", ""),
                    evidence_type=item.get("type", "none"),
                    confidence=item.get("confidence", 0.5),
                )
            )

        verification = protocol.verify(
            task=task,
            claimed_result=result,
            evidence=evidence_items or None,
            complexity=complexity,
        )

        # Format the result
        lines = [f"## Verification: {verification.outcome.value.upper()}"]
        lines.append(f"Scrutiny: {verification.scrutiny_level}")
        lines.append(f"Assessment: {verification.evidence_assessment}")

        if verification.challenges:
            lines.append(f"\n### Challenges ({len(verification.challenges)}):")
            for i, challenge in enumerate(verification.challenges, 1):
                lines.append(f"{i}. {challenge}")

        if verification.blocking_reason:
            lines.append(f"\n### BLOCKING: {verification.blocking_reason}")

        lines.append(f"\nTime: {verification.elapsed_ms:.1f}ms")

        return "\n".join(lines)

    return handler


# ---------------------------------------------------------------------------
# Post-response auto-verification
# ---------------------------------------------------------------------------


def auto_verify_response(
    protocol: CompletionProtocol,
    response_text: str,
    task: str,
    tool_results: list[str],
    complexity: str = "simple",
) -> dict[str, Any] | None:
    """
    Check if a mind's response claims completion. If so, verify it.

    Returns the verification result dict if a completion was detected,
    or None if no completion signal was found.

    The caller (mind.py) can use this to inject challenges back into context
    or escalate blocking issues.
    """
    if not detect_completion_signal(response_text):
        return None

    # Extract evidence from tool results
    evidence = extract_evidence(tool_results)

    verification = protocol.verify(
        task=task,
        claimed_result=response_text,
        evidence=evidence,
        complexity=complexity,
    )

    result = {
        "outcome": verification.outcome.value,
        "passed": verification.passed,
        "scrutiny": verification.scrutiny_level,
        "assessment": verification.evidence_assessment,
        "challenges": verification.challenges,
        "blocking_reason": verification.blocking_reason,
        "elapsed_ms": verification.elapsed_ms,
    }

    if not verification.passed:
        logger.warning(
            "[P9] Auto-verification %s: %d challenges — %s",
            verification.outcome.value,
            len(verification.challenges),
            verification.evidence_assessment,
        )

    return result


def format_challenge_injection(verification_result: dict[str, Any]) -> str:
    """
    Format a verification result as a context injection for the mind.

    When auto-verification challenges a completion, this text gets injected
    back into the conversation so the mind addresses the challenges.
    """
    outcome = verification_result["outcome"]
    challenges = verification_result.get("challenges", [])

    if outcome == "approved":
        return ""

    lines = [
        f"\n[P9 Verification — {outcome.upper()}]",
        "Your completion claim was challenged. Address these before continuing:\n",
    ]

    for i, challenge in enumerate(challenges, 1):
        lines.append(f"{i}. {challenge}")

    if outcome == "blocked":
        lines.append(f"\nBLOCKING: {verification_result.get('blocking_reason', 'Unknown')}")
        lines.append("This task cannot be marked complete until the blocking issue is resolved.")
    else:
        lines.append("\nAddress each challenge, then verify again.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_verification_tools(
    registry: ToolRegistry,
    protocol: CompletionProtocol,
) -> None:
    """Register the verify_completion tool."""
    registry.register(
        "verify_completion",
        VERIFY_COMPLETION_DEFINITION,
        _make_verify_handler(protocol),
        read_only=True,
    )
