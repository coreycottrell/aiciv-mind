"""
Tests for aiciv_mind.verification — completion protocol and Red Team verification.
"""

from __future__ import annotations

import pytest

from aiciv_mind.verification import (
    CompletionProtocol,
    Evidence,
    VerificationOutcome,
    VerificationResult,
    detect_completion_signal,
    extract_evidence,
)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class TestEvidence:
    def test_strong_evidence_with_test_pass(self):
        e = Evidence(
            description="All tests passed",
            evidence_type="test_pass",
            confidence=0.9,
        )
        assert e.is_strong()

    def test_weak_evidence_with_low_confidence(self):
        e = Evidence(
            description="Looks right",
            evidence_type="manual_check",
            confidence=0.3,
        )
        assert not e.is_strong()

    def test_no_evidence_type_is_weak(self):
        e = Evidence(
            description="Did the thing",
            evidence_type="none",
            confidence=0.5,
        )
        assert not e.is_strong()

    def test_api_response_strong_at_high_confidence(self):
        e = Evidence(
            description="200 OK",
            evidence_type="api_response",
            confidence=0.8,
        )
        assert e.is_strong()


# ---------------------------------------------------------------------------
# extract_evidence
# ---------------------------------------------------------------------------


class TestExtractEvidence:
    def test_detects_test_pass(self):
        results = ["Running tests... 22 passed, 0 failed"]
        evidence = extract_evidence(results)
        assert any(e.evidence_type == "test_pass" for e in evidence)

    def test_detects_file_written(self):
        results = ["File created at /tmp/output.txt"]
        evidence = extract_evidence(results)
        assert any(e.evidence_type == "file_written" for e in evidence)

    def test_detects_api_response(self):
        results = ["HTTP 200 response: {'status': 'ok'}"]
        evidence = extract_evidence(results)
        assert any(e.evidence_type == "api_response" for e in evidence)

    def test_no_evidence_from_empty_results(self):
        assert extract_evidence([]) == []

    def test_no_evidence_from_unrelated_text(self):
        results = ["Just thinking about what to do next"]
        evidence = extract_evidence(results)
        # May or may not find anything — but shouldn't crash
        assert isinstance(evidence, list)


# ---------------------------------------------------------------------------
# detect_completion_signal
# ---------------------------------------------------------------------------


class TestDetectCompletionSignal:
    def test_detects_done(self):
        assert detect_completion_signal("The task is done.")

    def test_detects_complete(self):
        assert detect_completion_signal("Task complete!")

    def test_detects_shipped(self):
        assert detect_completion_signal("Feature shipped to production.")

    def test_detects_committed(self):
        assert detect_completion_signal("Changes committed and pushed.")

    def test_no_signal_in_progress_text(self):
        assert not detect_completion_signal("Still working on this, making progress.")

    def test_no_signal_in_question(self):
        assert not detect_completion_signal("What should I do next?")


# ---------------------------------------------------------------------------
# CompletionProtocol
# ---------------------------------------------------------------------------


class TestCompletionProtocol:
    def test_disabled_always_approves(self):
        proto = CompletionProtocol(enabled=False)
        result = proto.verify("task", "result")
        assert result.outcome == VerificationOutcome.APPROVED
        assert result.scrutiny_level == "none"

    def test_trivial_with_good_result_approves(self):
        proto = CompletionProtocol(enabled=True)
        result = proto.verify(
            task="check disk usage",
            claimed_result="Disk usage is at 42%. Plenty of space remaining.",
            complexity="trivial",
        )
        assert result.outcome == VerificationOutcome.APPROVED
        assert result.scrutiny_level == "light"

    def test_empty_result_gets_challenged(self):
        proto = CompletionProtocol(enabled=True)
        result = proto.verify(
            task="build the feature",
            claimed_result="",
            complexity="simple",
        )
        assert result.outcome == VerificationOutcome.CHALLENGED
        assert any("empty" in c.lower() for c in result.challenges)

    def test_error_in_result_gets_challenged(self):
        proto = CompletionProtocol(enabled=True)
        result = proto.verify(
            task="deploy the service",
            claimed_result="Attempted deployment but got an error: connection refused.",
            complexity="simple",
        )
        assert result.outcome == VerificationOutcome.CHALLENGED
        assert any("error" in c.lower() for c in result.challenges)

    def test_no_evidence_standard_challenged(self):
        proto = CompletionProtocol(enabled=True)
        result = proto.verify(
            task="implement the feature",
            claimed_result="The feature has been fully implemented and is working correctly.",
            evidence=[],
            complexity="medium",
        )
        assert result.outcome == VerificationOutcome.CHALLENGED
        assert any("evidence" in c.lower() for c in result.challenges)

    def test_strong_evidence_can_approve(self):
        proto = CompletionProtocol(enabled=True)
        evidence = [
            Evidence(
                description="All 22 tests pass",
                evidence_type="test_pass",
                confidence=0.9,
            ),
        ]
        result = proto.verify(
            task="fix the bug",
            claimed_result="Fixed the null pointer in handler.py. All tests pass.",
            evidence=evidence,
            complexity="simple",
        )
        # Strong evidence on simple task → should approve
        assert result.outcome == VerificationOutcome.APPROVED

    def test_complex_task_gets_deep_scrutiny(self):
        proto = CompletionProtocol(enabled=True)
        result = proto.verify(
            task="architect the new microservice",
            claimed_result="Designed the architecture with 5 services. This is a fix for the old system.",
            complexity="complex",
        )
        assert result.scrutiny_level == "deep"
        # Deep scrutiny always challenges
        assert result.outcome == VerificationOutcome.CHALLENGED

    def test_variable_task_gets_deep_scrutiny(self):
        proto = CompletionProtocol(enabled=True)
        result = proto.verify(
            task="explore novel approach",
            claimed_result="Found a promising approach after exploration.",
            complexity="variable",
        )
        assert result.scrutiny_level == "deep"

    def test_session_stats_empty(self):
        proto = CompletionProtocol(enabled=True)
        stats = proto.get_session_stats()
        assert stats["total"] == 0

    def test_session_stats_accumulate(self):
        proto = CompletionProtocol(enabled=True)
        proto.verify("t1", "Good result with enough text to pass.", complexity="trivial")
        proto.verify("t2", "", complexity="simple")
        stats = proto.get_session_stats()
        assert stats["total"] == 2

    def test_elapsed_ms_positive(self):
        proto = CompletionProtocol(enabled=True)
        result = proto.verify("task", "result text is long enough", complexity="simple")
        assert result.elapsed_ms >= 0


# ---------------------------------------------------------------------------
# build_verification_prompt
# ---------------------------------------------------------------------------


class TestVerificationPrompt:
    def test_disabled_returns_empty(self):
        proto = CompletionProtocol(enabled=False)
        assert proto.build_verification_prompt("task") == ""

    def test_light_prompt_for_trivial(self):
        proto = CompletionProtocol(enabled=True)
        prompt = proto.build_verification_prompt("task", complexity="trivial")
        assert "Light" in prompt
        assert "verify" in prompt.lower()

    def test_standard_prompt_for_simple(self):
        proto = CompletionProtocol(enabled=True)
        prompt = proto.build_verification_prompt("task", complexity="simple")
        assert "Red Team" in prompt

    def test_deep_prompt_for_complex(self):
        proto = CompletionProtocol(enabled=True)
        prompt = proto.build_verification_prompt("task", complexity="complex")
        assert "Red Team" in prompt
        # Deep should have more questions than standard
        assert "reversible" in prompt.lower()

    def test_prompt_contains_questions(self):
        proto = CompletionProtocol(enabled=True)
        prompt = proto.build_verification_prompt("task", complexity="complex")
        assert "REALLY know" in prompt
        assert "prove it" in prompt.lower()


# ---------------------------------------------------------------------------
# Integration with memory store
# ---------------------------------------------------------------------------


class TestWithMemory:
    def test_memory_contradiction_check(self):
        from aiciv_mind.memory import Memory, MemoryStore

        store = MemoryStore(":memory:")
        try:
            # Add a memory about a failed deployment
            mem = Memory(
                agent_id="test",
                title="deploy blog failed",
                content="Blog deployment failed because the build script has a bug",
                domain="pipeline",
                memory_type="task",
            )
            store.store(mem)

            proto = CompletionProtocol(
                memory_store=store,
                agent_id="test",
                enabled=True,
            )
            result = proto.verify(
                task="deploy the blog",
                claimed_result="Blog deployed successfully.",
                complexity="medium",
            )
            # Should find the contradiction and challenge
            assert result.outcome == VerificationOutcome.CHALLENGED
            assert any("prior issues" in c.lower() or "memory" in c.lower() for c in result.challenges)
        finally:
            store.close()
