"""
aiciv_mind.challenger — Challenger System (Gap 1).

Runs EVERY turn during task execution, not just at completion. While the
CompletionProtocol (P9) fires after a completion signal, the Challenger fires
after every tool-execution batch and catches problems before the mind claims
it's done.

Detection is STRUCTURAL — pattern matching on text and tool results, no
additional LLM calls.

Checks:
    1. Premature completion claims — completion signals with low tool/iteration counts
    2. Empty work claims — claims of doing work with no write tools used
    3. Spawn-without-verify — spawning agents without verifying their results
    4. Stall detection — many iterations with only read tools (no writes)

Integration point: called from mind.py's _run_task_body after tool execution,
before the P9 auto-verify block. If should_inject is True, the caller injects
injection_text as a user message to redirect the mind.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ChallengeResult:
    """Output of a per-turn challenger check."""

    should_inject: bool
    injection_text: str
    severity: str  # "info", "warning", "critical"
    challenges: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Signals that the mind is claiming it's done (shared with verification.py)
_COMPLETION_SIGNALS = [
    "done", "complete", "finished", "shipped", "deployed",
    "task complete", "all done", "that's it", "implemented",
    "committed", "pushed", "merged", "all complete",
]

# Tools that produce output (i.e. actually DO something beyond reading)
_WRITE_TOOLS = frozenset({
    "write_file",
    "edit_file",
    "bash",
    "spawn_agent",
    "spawn_team_lead",
    "store_memory",
    "memory_write",
    "scratchpad_write",
})

# Tools that specifically spawn sub-agents
_SPAWN_TOOLS = frozenset({
    "spawn_agent",
    "spawn_team_lead",
})

# Tools that read/verify agent results
_VERIFY_TOOLS = frozenset({
    "read_file",
    "bash",
    "grep",
    "glob",
    "memory_search",
    "verify_completion",
})


# ---------------------------------------------------------------------------
# ChallengerSystem
# ---------------------------------------------------------------------------


class ChallengerSystem:
    """
    Per-turn adversarial checker.

    Instantiated once per mind (alongside CompletionProtocol). Called after
    every tool-execution batch in _run_task_body.

    Args:
        completion_protocol: The CompletionProtocol instance (for consistency,
            though the Challenger does its own structural checks).
        memory_store: Optional MemoryStore for memory-aware challenges.
        enabled: Kill switch — when False, challenge_turn always returns
            a no-op ChallengeResult.
    """

    def __init__(
        self,
        completion_protocol: Any = None,
        memory_store: Any = None,
        enabled: bool = True,
    ):
        self._protocol = completion_protocol
        self._memory = memory_store
        self._enabled = enabled

        # Accumulated state across turns (reset per task via reset())
        self._write_tools_seen: list[str] = []
        self._spawn_tools_seen: list[str] = []
        self._verify_after_spawn: bool = False
        self._total_challenges_injected: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset per-task state. Call at the start of each new task."""
        self._write_tools_seen.clear()
        self._spawn_tools_seen.clear()
        self._verify_after_spawn = False
        self._total_challenges_injected = 0

    def challenge_turn(
        self,
        response_text: str,
        task: str,
        tool_results: list[str],
        iteration: int,
        tool_call_count: int,
    ) -> ChallengeResult:
        """
        Run all challenger checks for the current turn.

        Args:
            response_text: The mind's latest text output (may be empty if
                the model only produced tool calls).
            task: The original task description.
            tool_results: List of tool-result strings from this turn's
                tool execution. Each entry is the tool name or a combined
                "name: result_content" string — the checker looks for
                tool names in these strings.
            iteration: Current loop iteration (1-based).
            tool_call_count: Cumulative tool calls across all iterations.

        Returns:
            ChallengeResult. If should_inject is True, the caller must
            inject injection_text as a user message.
        """
        if not self._enabled:
            return ChallengeResult(
                should_inject=False,
                injection_text="",
                severity="info",
            )

        # Update internal state from this turn's tool results
        self._update_tool_state(tool_results)

        # Run all checks
        challenges: list[str] = []
        max_severity = "info"

        # 1. Premature completion claims
        sev, msgs = self._check_premature_completion(
            response_text, iteration, tool_call_count,
        )
        if msgs:
            challenges.extend(msgs)
            max_severity = _max_severity(max_severity, sev)

        # 2. Empty work claims
        sev, msgs = self._check_empty_work_claims(response_text)
        if msgs:
            challenges.extend(msgs)
            max_severity = _max_severity(max_severity, sev)

        # 3. Spawn-without-verify
        sev, msgs = self._check_spawn_without_verify(tool_results)
        if msgs:
            challenges.extend(msgs)
            max_severity = _max_severity(max_severity, sev)

        # 4. Stall detection
        sev, msgs = self._check_stall(iteration)
        if msgs:
            challenges.extend(msgs)
            max_severity = _max_severity(max_severity, sev)

        if not challenges:
            return ChallengeResult(
                should_inject=False,
                injection_text="",
                severity="info",
            )

        # Build injection text
        injection_text = self._format_injection(challenges, max_severity)
        self._total_challenges_injected += 1

        logger.info(
            "[Challenger] Turn %d: %d challenge(s) at %s severity",
            iteration, len(challenges), max_severity,
        )

        return ChallengeResult(
            should_inject=True,
            injection_text=injection_text,
            severity=max_severity,
            challenges=challenges,
        )

    def get_session_stats(self) -> dict[str, Any]:
        """Return challenger stats for the current task."""
        return {
            "total_injections": self._total_challenges_injected,
            "write_tools_seen": len(self._write_tools_seen),
            "spawn_tools_seen": len(self._spawn_tools_seen),
        }

    # ------------------------------------------------------------------
    # Internal state tracking
    # ------------------------------------------------------------------

    def _update_tool_state(self, tool_results: list[str]) -> None:
        """Update internal state from the current turn's tool results."""
        for result in tool_results:
            result_lower = result.lower()
            # Extract tool name — tool results may be formatted as
            # "tool_name: ..." or "[Tool result: tool_name]\n..."
            tool_name = self._extract_tool_name(result)

            if tool_name in _WRITE_TOOLS:
                self._write_tools_seen.append(tool_name)

            if tool_name in _SPAWN_TOOLS:
                self._spawn_tools_seen.append(tool_name)
                self._verify_after_spawn = False  # Need verify after this spawn

            if tool_name in _VERIFY_TOOLS and self._spawn_tools_seen:
                # A verify-like tool was used after a spawn — mark verified
                self._verify_after_spawn = True

    @staticmethod
    def _extract_tool_name(result_str: str) -> str:
        """
        Extract tool name from a tool result string.

        Handles formats:
            "[Tool result: bash]\n..."
            "bash: ..."
            Just the tool name alone
        """
        # Pattern 1: [Tool result: NAME]
        m = re.match(r"\[Tool result:\s*(\w+)\]", result_str)
        if m:
            return m.group(1)

        # Pattern 2: NAME: ...  (tool name before first colon)
        # Only match if it looks like a known tool name (avoid false positives)
        first_word = result_str.split(":", 1)[0].strip().split("\n")[0].strip()
        all_tools = _WRITE_TOOLS | _VERIFY_TOOLS | _SPAWN_TOOLS
        if first_word in all_tools:
            return first_word

        # Pattern 3: the string IS just the tool name (passed from iter_tool_names)
        stripped = result_str.strip()
        if stripped in all_tools:
            return stripped

        return ""

    # ------------------------------------------------------------------
    # Challenge checks
    # ------------------------------------------------------------------

    def _check_premature_completion(
        self,
        response_text: str,
        iteration: int,
        tool_call_count: int,
    ) -> tuple[str, list[str]]:
        """
        Check 1: Premature completion claims.

        If the response contains completion signals but:
        - tool_call_count < 2  (barely did anything)
        - iteration < 3  (very early in the loop)

        Flag as premature.
        """
        if not response_text:
            return "info", []

        text_lower = response_text.lower()
        has_completion_signal = any(
            signal in text_lower for signal in _COMPLETION_SIGNALS
        )

        if not has_completion_signal:
            return "info", []

        challenges = []

        if tool_call_count < 2:
            challenges.append(
                f"Premature completion: you claim to be done but have only made "
                f"{tool_call_count} tool call(s). Verify your work actually "
                f"produced output before claiming completion."
            )

        if iteration < 3:
            challenges.append(
                f"Early completion signal at iteration {iteration}. Complex tasks "
                f"rarely complete in fewer than 3 iterations. Are you sure "
                f"everything is actually done?"
            )

        severity = "critical" if tool_call_count < 1 else "warning"
        return severity, challenges

    def _check_empty_work_claims(
        self,
        response_text: str,
    ) -> tuple[str, list[str]]:
        """
        Check 2: Empty work claims.

        If response claims work was done but no write tools were used
        across the entire task so far.
        """
        if not response_text:
            return "info", []

        text_lower = response_text.lower()

        # Phrases that claim work was done
        work_claim_patterns = [
            "created", "wrote", "written", "built", "implemented",
            "fixed", "updated", "deployed", "configured", "set up",
            "installed", "modified", "changed", "added", "removed",
        ]

        has_work_claim = any(p in text_lower for p in work_claim_patterns)

        if has_work_claim and not self._write_tools_seen:
            return "warning", [
                "You claim to have done work (created/wrote/built/fixed/etc.) but "
                "no write tools (write_file, edit_file, bash, etc.) have been used "
                "this task. Did you actually produce output, or are you describing "
                "what SHOULD be done?"
            ]

        return "info", []

    def _check_spawn_without_verify(
        self,
        tool_results: list[str],
    ) -> tuple[str, list[str]]:
        """
        Check 3: Spawn-without-verify.

        If an agent was spawned but no verification of results followed.
        Only fires if spawns happened and no verify tool has been used since.
        """
        if not self._spawn_tools_seen:
            return "info", []

        if self._verify_after_spawn:
            return "info", []

        # Only challenge if we've had at least one turn after the spawn
        # (give the mind a chance to verify on the next turn)
        spawn_count = len(self._spawn_tools_seen)
        return "info", [
            f"You spawned {spawn_count} agent(s) but haven't verified their "
            f"results yet. Read their output or check their work before "
            f"claiming completion."
        ]

    def _check_stall(
        self,
        iteration: int,
    ) -> tuple[str, list[str]]:
        """
        Check 4: Stall detection.

        If iteration > 5 and no write tools have been used (only reads),
        the mind may be spinning without producing output.
        """
        if iteration <= 5:
            return "info", []

        if self._write_tools_seen:
            return "info", []

        return "warning", [
            f"Stall detected: {iteration} iterations with no write operations. "
            f"You appear to be reading/searching without producing output. "
            f"Write output or explain why you're still gathering information."
        ]

    # ------------------------------------------------------------------
    # Injection formatting
    # ------------------------------------------------------------------

    def _format_injection(
        self,
        challenges: list[str],
        severity: str,
    ) -> str:
        """Format challenges as a user message injection."""
        severity_label = severity.upper()

        lines = [
            f"\n[Challenger System — {severity_label}]",
            "The following issues were detected:\n",
        ]

        for i, challenge in enumerate(challenges, 1):
            lines.append(f"{i}. {challenge}")

        if severity == "critical":
            lines.append(
                "\nCRITICAL: Do NOT claim completion until these issues are resolved."
            )
        else:
            lines.append(
                "\nAddress these concerns before proceeding."
            )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


def _max_severity(a: str, b: str) -> str:
    """Return the higher of two severity levels."""
    return a if _SEVERITY_ORDER.get(a, 0) >= _SEVERITY_ORDER.get(b, 0) else b
