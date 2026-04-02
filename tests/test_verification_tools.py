"""
Tests for aiciv_mind.tools.verification_tools — verify_completion tool + auto-verification.
"""

from __future__ import annotations

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.verification import (
    CompletionProtocol,
    Evidence,
    VerificationOutcome,
)
from aiciv_mind.tools.verification_tools import (
    VERIFY_COMPLETION_DEFINITION,
    _make_verify_handler,
    auto_verify_response,
    format_challenge_injection,
    register_verification_tools,
)


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_name(self):
        assert VERIFY_COMPLETION_DEFINITION["name"] == "verify_completion"

    def test_has_description(self):
        assert len(VERIFY_COMPLETION_DEFINITION["description"]) > 20

    def test_required_fields(self):
        required = VERIFY_COMPLETION_DEFINITION["input_schema"]["required"]
        assert "task" in required
        assert "result" in required

    def test_optional_evidence_field(self):
        props = VERIFY_COMPLETION_DEFINITION["input_schema"]["properties"]
        assert "evidence" in props
        assert props["evidence"]["type"] == "array"

    def test_complexity_enum(self):
        props = VERIFY_COMPLETION_DEFINITION["input_schema"]["properties"]
        assert "complexity" in props
        assert set(props["complexity"]["enum"]) == {
            "trivial", "simple", "medium", "complex", "variable",
        }


# ---------------------------------------------------------------------------
# verify_completion handler
# ---------------------------------------------------------------------------


class TestVerifyHandler:
    def _make_protocol(self, enabled: bool = True) -> CompletionProtocol:
        return CompletionProtocol(agent_id="test", enabled=enabled)

    def test_approved_trivial_task(self):
        handler = _make_verify_handler(self._make_protocol())
        result = handler({
            "task": "Add a print statement",
            "result": "Added print('hello') to line 5 of main.py",
            "complexity": "trivial",
        })
        assert "APPROVED" in result

    def test_challenged_no_evidence(self):
        handler = _make_verify_handler(self._make_protocol())
        result = handler({
            "task": "Implement database migration",
            "result": "Migration implemented and ready to run.",
            "complexity": "medium",
        })
        # Standard scrutiny with no evidence → challenged
        assert "CHALLENGED" in result or "Challenges" in result

    def test_handler_with_evidence(self):
        handler = _make_verify_handler(self._make_protocol())
        result = handler({
            "task": "Fix the login bug",
            "result": "Fixed the login validation — tests pass.",
            "evidence": [
                {
                    "description": "All 12 tests passed",
                    "type": "test_pass",
                    "confidence": 0.9,
                },
            ],
            "complexity": "simple",
        })
        # Strong test evidence + simple → light scrutiny → approved
        assert "APPROVED" in result

    def test_handler_defaults_complexity_to_simple(self):
        handler = _make_verify_handler(self._make_protocol())
        result = handler({
            "task": "Small fix",
            "result": "Done — applied the fix successfully.",
        })
        # No complexity specified → defaults to simple
        assert "Scrutiny:" in result

    def test_handler_formats_challenges(self):
        handler = _make_verify_handler(self._make_protocol())
        result = handler({
            "task": "Rewrite authentication system",
            "result": "Auth system rewritten. Used a patch to fix the edge case.",
            "complexity": "complex",
        })
        # Complex → deep scrutiny → always has challenges
        assert "Challenges" in result

    def test_handler_shows_timing(self):
        handler = _make_verify_handler(self._make_protocol())
        result = handler({
            "task": "Simple task",
            "result": "Task completed without issues.",
            "complexity": "trivial",
        })
        assert "Time:" in result
        assert "ms" in result

    def test_handler_with_disabled_protocol(self):
        handler = _make_verify_handler(self._make_protocol(enabled=False))
        result = handler({
            "task": "Anything",
            "result": "Done",
        })
        assert "APPROVED" in result

    def test_handler_empty_evidence_list(self):
        handler = _make_verify_handler(self._make_protocol())
        result = handler({
            "task": "Check something",
            "result": "Checked and confirmed working.",
            "evidence": [],
            "complexity": "simple",
        })
        # Empty evidence list treated as no evidence
        assert "Scrutiny:" in result

    def test_handler_evidence_defaults_confidence(self):
        """Evidence items without confidence default to 0.5."""
        handler = _make_verify_handler(self._make_protocol())
        result = handler({
            "task": "Write tests",
            "result": "Tests written and passing.",
            "evidence": [
                {"description": "Manual check", "type": "manual_check"},
            ],
            "complexity": "simple",
        })
        # manual_check at 0.5 is not strong → standard scrutiny
        assert "Scrutiny:" in result


# ---------------------------------------------------------------------------
# auto_verify_response
# ---------------------------------------------------------------------------


class TestAutoVerifyResponse:
    def _make_protocol(self) -> CompletionProtocol:
        return CompletionProtocol(agent_id="test", enabled=True)

    def test_returns_none_for_non_completion(self):
        result = auto_verify_response(
            protocol=self._make_protocol(),
            response_text="I'm still working on the implementation.",
            task="Build the API",
            tool_results=[],
        )
        assert result is None

    def test_detects_completion_signal(self):
        result = auto_verify_response(
            protocol=self._make_protocol(),
            response_text="Task complete — all tests pass.",
            task="Fix the login bug",
            tool_results=["12 tests passed, 0 failed"],
        )
        assert result is not None
        assert "outcome" in result
        assert "passed" in result
        assert "challenges" in result

    def test_returns_dict_with_all_fields(self):
        result = auto_verify_response(
            protocol=self._make_protocol(),
            response_text="Done! Implementation finished.",
            task="Build something",
            tool_results=[],
        )
        assert result is not None
        expected_keys = {
            "outcome", "passed", "scrutiny", "assessment",
            "challenges", "blocking_reason", "elapsed_ms",
        }
        assert set(result.keys()) == expected_keys

    def test_approved_with_strong_evidence(self):
        result = auto_verify_response(
            protocol=self._make_protocol(),
            response_text="All done — tests pass.",
            task="Fix the bug",
            tool_results=["All 5 tests passed, 0 failed"],
            complexity="simple",
        )
        assert result is not None
        # test_pass evidence detected → strong → light scrutiny → approved
        assert result["passed"] is True
        assert result["outcome"] == "approved"

    def test_challenged_without_evidence(self):
        result = auto_verify_response(
            protocol=self._make_protocol(),
            response_text="I've finished implementing the feature.",
            task="Add search functionality",
            tool_results=[],
            complexity="medium",
        )
        assert result is not None
        # No tool results → no evidence → challenged
        assert result["passed"] is False
        assert result["outcome"] == "challenged"

    def test_complexity_affects_scrutiny(self):
        result = auto_verify_response(
            protocol=self._make_protocol(),
            response_text="Deployed the migration.",
            task="Database migration",
            tool_results=[],
            complexity="complex",
        )
        assert result is not None
        assert result["scrutiny"] == "deep"

    def test_trivial_complexity(self):
        result = auto_verify_response(
            protocol=self._make_protocol(),
            response_text="Done — added the import.",
            task="Add import statement",
            tool_results=[],
            complexity="trivial",
        )
        assert result is not None
        assert result["scrutiny"] == "light"

    def test_multiple_completion_signals(self):
        """Text with multiple completion signals still works."""
        result = auto_verify_response(
            protocol=self._make_protocol(),
            response_text="Task complete. Finished and shipped.",
            task="Build feature",
            tool_results=[],
        )
        assert result is not None

    def test_evidence_extraction_from_tool_results(self):
        result = auto_verify_response(
            protocol=self._make_protocol(),
            response_text="Done. Committed and pushed.",
            task="Write the module",
            tool_results=[
                "File created: src/module.py",
                "git commit: abc123",
            ],
        )
        assert result is not None
        # "file created" should be detected as file_written evidence


# ---------------------------------------------------------------------------
# format_challenge_injection
# ---------------------------------------------------------------------------


class TestFormatChallengeInjection:
    def test_approved_returns_empty(self):
        result = format_challenge_injection({
            "outcome": "approved",
            "challenges": [],
        })
        assert result == ""

    def test_challenged_formats_challenges(self):
        result = format_challenge_injection({
            "outcome": "challenged",
            "challenges": [
                "No evidence provided.",
                "What tests confirm this works?",
            ],
        })
        assert "[P9 Verification" in result
        assert "CHALLENGED" in result
        assert "1. No evidence provided." in result
        assert "2. What tests confirm this works?" in result
        assert "Address each challenge" in result

    def test_blocked_includes_reason(self):
        result = format_challenge_injection({
            "outcome": "blocked",
            "challenges": ["Critical issue found"],
            "blocking_reason": "Database migration not tested",
        })
        assert "BLOCKED" in result
        assert "Database migration not tested" in result
        assert "cannot be marked complete" in result

    def test_blocked_with_unknown_reason(self):
        result = format_challenge_injection({
            "outcome": "blocked",
            "challenges": [],
        })
        assert "BLOCKED" in result
        assert "Unknown" in result

    def test_empty_challenges_list(self):
        result = format_challenge_injection({
            "outcome": "challenged",
            "challenges": [],
        })
        assert "[P9 Verification" in result
        # No numbered challenges, but still has the header


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_verification_tools(self):
        registry = ToolRegistry()
        protocol = CompletionProtocol(agent_id="test")
        register_verification_tools(registry, protocol)
        assert "verify_completion" in registry.names()

    def test_registered_as_read_only(self):
        registry = ToolRegistry()
        protocol = CompletionProtocol(agent_id="test")
        register_verification_tools(registry, protocol)
        assert registry.is_read_only("verify_completion") is True

    def test_tool_definition_matches(self):
        registry = ToolRegistry()
        protocol = CompletionProtocol(agent_id="test")
        register_verification_tools(registry, protocol)
        tools = registry.build_anthropic_tools(["verify_completion"])
        assert len(tools) == 1
        assert tools[0]["name"] == "verify_completion"

    def test_handler_is_callable(self):
        registry = ToolRegistry()
        protocol = CompletionProtocol(agent_id="test")
        register_verification_tools(registry, protocol)
        handler = registry._handlers["verify_completion"]
        assert callable(handler)

    def test_handler_uses_provided_protocol(self):
        """Verify the handler is closed over the given protocol instance."""
        registry = ToolRegistry()
        protocol = CompletionProtocol(agent_id="test", enabled=False)
        register_verification_tools(registry, protocol)
        handler = registry._handlers["verify_completion"]
        result = handler({"task": "test", "result": "done"})
        # Disabled protocol → always APPROVED
        assert "APPROVED" in result
