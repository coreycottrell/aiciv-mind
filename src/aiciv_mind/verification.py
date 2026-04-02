"""
aiciv_mind.verification — Completion protocol and Red Team verification.

Principle 9: VERIFICATION BEFORE COMPLETION (Red Team Everything).

Every completion claim requires evidence.  Every significant decision gets
challenged by a dedicated adversary.  The mind proves it's done — it doesn't
just say it's done.

The Red Team operates as a lightweight inline check (no separate LLM call for
trivial/simple tasks) or a structured adversarial prompt injected before the
final response (medium+ tasks).

Verification Outcomes:
    APPROVED   — evidence supports the claim
    CHALLENGED — specific questions must be addressed before completing
    BLOCKED    — fundamental problem found, escalate

The verification outcome is logged to memory so the Red Team LEARNS which
completion types are usually wrong and adjusts scrutiny accordingly.
"""

from __future__ import annotations

import enum
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Verification outcomes
# ---------------------------------------------------------------------------


class VerificationOutcome(enum.Enum):
    """Red Team verdict on a completion claim."""

    APPROVED = "approved"
    CHALLENGED = "challenged"
    BLOCKED = "blocked"


@dataclass
class Evidence:
    """Evidence supporting a completion claim."""

    description: str
    evidence_type: str  # "test_pass", "file_written", "api_response", "manual_check", "none"
    details: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5  # 0.0 = no confidence, 1.0 = certain

    def is_strong(self) -> bool:
        """Evidence with automated verification is strong."""
        return self.evidence_type in ("test_pass", "api_response") and self.confidence >= 0.7


@dataclass
class VerificationResult:
    """Output of the Red Team verification."""

    outcome: VerificationOutcome
    evidence_assessment: str  # Summary of evidence quality
    challenges: list[str] = field(default_factory=list)  # Questions that must be addressed
    blocking_reason: str = ""  # If BLOCKED, why
    scrutiny_level: str = "standard"  # "light", "standard", "deep"
    elapsed_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.outcome == VerificationOutcome.APPROVED


# ---------------------------------------------------------------------------
# Red Team questions — the adversarial challenge set
# ---------------------------------------------------------------------------

_RED_TEAM_QUESTIONS = [
    ("Do we REALLY know this?", "Challenge assumptions — what evidence supports this claim?"),
    ("Can we prove it?", "Demand concrete evidence: tests, outputs, logs."),
    ("Does memory confirm this?", "Search memory for contradicting prior experience."),
    ("Is there a simpler way?", "Challenge complexity — simplest correct solution wins."),
    ("Are we missing something obvious?", "Check blind spots — what hasn't been considered?"),
    ("Is this SYSTEM > symptom?", "Is this fix addressing root cause or patching a symptom?"),
    ("What could go wrong?", "Pre-mortem: if this fails in production, most likely cause?"),
    ("Is this reversible?", "If wrong, can we undo? What's the blast radius?"),
]


# ---------------------------------------------------------------------------
# Evidence extraction — detect evidence from tool results
# ---------------------------------------------------------------------------

# Patterns that indicate automated evidence
_EVIDENCE_PATTERNS = {
    "test_pass": [
        "passed", "tests pass", "all tests", "✅", "ok", "success",
        "0 failed", "no failures",
    ],
    "file_written": [
        "file created", "file written", "wrote to", "saved to",
        "committed", "pushed",
    ],
    "api_response": [
        "200", "201", "status: ok", "response:", "api call succeeded",
    ],
}


def extract_evidence(tool_results: list[str]) -> list[Evidence]:
    """
    Extract evidence items from tool result strings.

    Scans tool outputs for patterns indicating successful verification
    (test passes, file writes, API responses).
    """
    evidence_items: list[Evidence] = []
    combined = " ".join(tool_results).lower()

    for evidence_type, patterns in _EVIDENCE_PATTERNS.items():
        for pattern in patterns:
            if pattern in combined:
                evidence_items.append(
                    Evidence(
                        description=f"Detected '{pattern}' in tool output",
                        evidence_type=evidence_type,
                        confidence=0.7 if evidence_type == "test_pass" else 0.5,
                    )
                )
                break  # One match per evidence type is enough

    return evidence_items


# ---------------------------------------------------------------------------
# CompletionProtocol — the core verification engine
# ---------------------------------------------------------------------------


class CompletionProtocol:
    """
    Enforces evidence-based completion claims.

    Integrated into the mind loop: when the mind's response contains
    completion signals, the protocol fires and either approves, challenges,
    or blocks the completion.
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
        # Track verification history for learning
        self._session_verifications: list[dict[str, Any]] = []

    def verify(
        self,
        task: str,
        claimed_result: str,
        evidence: list[Evidence] | None = None,
        complexity: str = "simple",
    ) -> VerificationResult:
        """
        Verify a completion claim.

        Args:
            task: Original task description.
            claimed_result: The mind's claimed completion/result text.
            evidence: Evidence items collected during execution.
            complexity: Task complexity from planning gate ("trivial"→"variable").

        Returns:
            VerificationResult with outcome and assessment.
        """
        if not self._enabled:
            return VerificationResult(
                outcome=VerificationOutcome.APPROVED,
                evidence_assessment="Verification disabled",
                scrutiny_level="none",
            )

        start = time.monotonic()
        evidence = evidence or []

        # Determine scrutiny level based on complexity
        scrutiny = self._determine_scrutiny(complexity, evidence)

        # Run verification checks
        challenges: list[str] = []
        blocking_reason = ""

        if scrutiny == "light":
            # Trivial tasks: just check for obvious problems
            result = self._light_verification(task, claimed_result, evidence)
        elif scrutiny == "deep":
            # Complex/variable: full adversarial check
            result = self._deep_verification(task, claimed_result, evidence)
        else:
            # Standard: balanced check
            result = self._standard_verification(task, claimed_result, evidence)

        elapsed_ms = (time.monotonic() - start) * 1000

        # Update result with timing
        result.scrutiny_level = scrutiny
        result.elapsed_ms = elapsed_ms

        # Log for learning
        self._log_verification(task, result, complexity)

        logger.info(
            "[%s] Verification: %s (%s scrutiny, %.0fms) — %s",
            self._agent_id,
            result.outcome.value,
            scrutiny,
            elapsed_ms,
            result.evidence_assessment,
        )

        return result

    def _determine_scrutiny(self, complexity: str, evidence: list[Evidence]) -> str:
        """Determine scrutiny level based on complexity and evidence quality."""
        if complexity in ("trivial",):
            return "light"
        if complexity in ("complex", "variable"):
            return "deep"
        # For simple/medium: check if evidence is strong
        if evidence and any(e.is_strong() for e in evidence):
            return "light"  # Strong evidence → relax scrutiny
        return "standard"

    def _light_verification(
        self, task: str, result: str, evidence: list[Evidence]
    ) -> VerificationResult:
        """Light verification — check for obvious red flags only."""
        challenges = []

        # Check: empty result
        if not result or len(result.strip()) < 10:
            challenges.append("Result is empty or suspiciously short — is the task actually done?")

        # Check: error indicators in result
        error_signals = ["error", "failed", "exception", "traceback", "could not"]
        result_lower = result.lower()
        for signal in error_signals:
            if signal in result_lower:
                challenges.append(
                    f"Result contains '{signal}' — verify this isn't masking a failure."
                )
                break

        if challenges:
            return VerificationResult(
                outcome=VerificationOutcome.CHALLENGED,
                evidence_assessment=f"Light check found {len(challenges)} concern(s)",
                challenges=challenges,
            )

        return VerificationResult(
            outcome=VerificationOutcome.APPROVED,
            evidence_assessment="Light verification passed — no red flags",
        )

    def _standard_verification(
        self, task: str, result: str, evidence: list[Evidence]
    ) -> VerificationResult:
        """Standard verification — check evidence quality and consistency."""
        challenges = []

        # Run light checks first
        light = self._light_verification(task, result, evidence)
        challenges.extend(light.challenges)

        # Check: evidence exists
        if not evidence:
            challenges.append(
                "No concrete evidence provided. How do we know this is actually done? "
                "Tests passed? File written? API response received?"
            )

        # Check: evidence quality
        strong_evidence = [e for e in evidence if e.is_strong()]
        weak_evidence = [e for e in evidence if not e.is_strong()]
        if evidence and not strong_evidence:
            challenges.append(
                f"Only weak evidence ({len(weak_evidence)} items). "
                "Consider running tests or verifying output directly."
            )

        # Check: memory contradictions
        if self._memory and self._agent_id:
            contradictions = self._check_memory_contradictions(task, result)
            challenges.extend(contradictions)

        if any("BLOCK" in c.upper() for c in challenges):
            return VerificationResult(
                outcome=VerificationOutcome.BLOCKED,
                evidence_assessment="Blocking issue found",
                challenges=challenges,
                blocking_reason=next(c for c in challenges if "BLOCK" in c.upper()),
            )

        if challenges:
            return VerificationResult(
                outcome=VerificationOutcome.CHALLENGED,
                evidence_assessment=f"Standard check raised {len(challenges)} challenge(s)",
                challenges=challenges,
            )

        return VerificationResult(
            outcome=VerificationOutcome.APPROVED,
            evidence_assessment=f"Standard verification passed — {len(evidence)} evidence item(s) reviewed",
        )

    def _deep_verification(
        self, task: str, result: str, evidence: list[Evidence]
    ) -> VerificationResult:
        """Deep verification — full adversarial challenge for complex tasks."""
        challenges = []

        # Run standard checks first
        standard = self._standard_verification(task, result, evidence)
        challenges.extend(standard.challenges)

        # Apply full Red Team question set
        result_lower = result.lower()

        # "Is there a simpler way?" — flag if result is very long
        if len(result) > 5000:
            challenges.append(
                "Result is very long (>5000 chars). Is there a simpler approach? "
                "Complex solutions have more failure modes."
            )

        # "Is this SYSTEM > symptom?" — flag if fix-language without root cause
        fix_words = {"fix", "patch", "workaround", "hack", "bandaid"}
        if any(w in result_lower for w in fix_words):
            systemic_words = {"root cause", "systemic", "underlying", "architecture", "design"}
            if not any(w in result_lower for w in systemic_words):
                challenges.append(
                    "This looks like a symptom-level fix. "
                    "Has the systemic root cause been identified? (P2: SYSTEM > SYMPTOM)"
                )

        # "What could go wrong?" — always ask for complex tasks
        challenges.append(
            "Pre-mortem: What is the most likely failure mode if this goes to production? "
            "What edge cases haven't been tested?"
        )

        # "Is this reversible?" — flag irreversible actions
        irreversible_signals = {"delete", "drop", "force", "deploy", "publish", "migrate"}
        if any(w in result_lower for w in irreversible_signals):
            challenges.append(
                "This involves potentially irreversible actions. "
                "Is there a rollback plan? What's the blast radius?"
            )

        # De-duplicate
        seen = set()
        unique_challenges = []
        for c in challenges:
            key = c[:50]
            if key not in seen:
                seen.add(key)
                unique_challenges.append(c)

        if any(standard.outcome == VerificationOutcome.BLOCKED for _ in [1]):
            return VerificationResult(
                outcome=VerificationOutcome.BLOCKED,
                evidence_assessment="Deep review found blocking issue",
                challenges=unique_challenges,
                blocking_reason=standard.blocking_reason,
            )

        # Deep always challenges (that's the point — it forces reflection)
        return VerificationResult(
            outcome=VerificationOutcome.CHALLENGED,
            evidence_assessment=f"Deep adversarial review — {len(unique_challenges)} challenges raised",
            challenges=unique_challenges,
        )

    def _check_memory_contradictions(self, task: str, result: str) -> list[str]:
        """Search memory for information that contradicts the claimed result."""
        contradictions = []
        try:
            memories = self._memory.search(
                query=task,
                agent_id=self._agent_id,
                limit=3,
            )
            for m in memories:
                content = m.get("content", "").lower()
                # Simple heuristic: check if memory mentions failure/issue with same topic
                if any(w in content for w in ("failed", "broken", "doesn't work", "bug", "issue")):
                    title = m.get("title", "untitled")
                    contradictions.append(
                        f"Memory '{title}' mentions prior issues with a similar task. "
                        "Verify this completion addresses those concerns."
                    )
        except Exception as e:
            logger.debug("Memory contradiction check failed: %s", e)
        return contradictions

    def _log_verification(
        self, task: str, result: VerificationResult, complexity: str
    ) -> None:
        """Log verification for learning."""
        entry = {
            "task_preview": task[:100],
            "outcome": result.outcome.value,
            "scrutiny": result.scrutiny_level,
            "complexity": complexity,
            "num_challenges": len(result.challenges),
            "elapsed_ms": result.elapsed_ms,
        }
        self._session_verifications.append(entry)

    def get_session_stats(self) -> dict[str, Any]:
        """Return verification stats for the current session."""
        if not self._session_verifications:
            return {"total": 0}

        total = len(self._session_verifications)
        approved = sum(1 for v in self._session_verifications if v["outcome"] == "approved")
        challenged = sum(1 for v in self._session_verifications if v["outcome"] == "challenged")
        blocked = sum(1 for v in self._session_verifications if v["outcome"] == "blocked")

        return {
            "total": total,
            "approved": approved,
            "challenged": challenged,
            "blocked": blocked,
            "approval_rate": round(approved / total, 3) if total else 0,
        }

    # ------------------------------------------------------------------
    # Prompt injection — build Red Team context for the mind's prompt
    # ------------------------------------------------------------------

    def build_verification_prompt(
        self,
        task: str,
        complexity: str = "simple",
    ) -> str:
        """
        Build a Red Team verification section to inject into the system prompt.

        This makes the mind self-verify by embedding the adversarial questions
        directly into its instructions.
        """
        if not self._enabled:
            return ""

        scrutiny = self._determine_scrutiny(complexity, [])

        if scrutiny == "light":
            return (
                "\n## Verification Protocol (Light)\n"
                "Before claiming this task is complete, verify:\n"
                "- The result is not empty and addresses the actual task\n"
                "- No error indicators in the output\n"
            )

        parts = ["\n## Verification Protocol (Red Team)"]
        parts.append(
            "Before claiming this task is complete, you MUST answer these questions:"
        )

        if scrutiny == "standard":
            questions = _RED_TEAM_QUESTIONS[:4]  # First 4 questions
        else:
            questions = _RED_TEAM_QUESTIONS  # All 8 questions

        for q, purpose in questions:
            parts.append(f"- **{q}** — {purpose}")

        parts.append(
            "\nIf you cannot confidently answer ALL questions, state what remains "
            "unverified rather than claiming completion."
        )

        return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Completion signal detection
# ---------------------------------------------------------------------------

_COMPLETION_SIGNALS = [
    "done", "complete", "finished", "shipped", "deployed",
    "task complete", "all done", "that's it", "implemented",
    "committed", "pushed", "merged",
]


def detect_completion_signal(text: str) -> bool:
    """
    Check if the text contains signals that the mind is claiming completion.

    Used to decide whether to run verification on a response.
    """
    text_lower = text.lower()
    return any(signal in text_lower for signal in _COMPLETION_SIGNALS)
