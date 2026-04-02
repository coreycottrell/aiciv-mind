"""
Tests for permission bubbling — sub-minds escalate tool calls to parent minds.
"""

from __future__ import annotations

import asyncio
import pytest

from aiciv_mind.tools.hooks import (
    HookRunner,
    HookResult,
    PermissionRequest,
    PermissionResponse,
)


# ---------------------------------------------------------------------------
# PermissionRequest / PermissionResponse dataclasses
# ---------------------------------------------------------------------------


class TestPermissionRequest:
    def test_default_values(self):
        req = PermissionRequest(
            tool_name="bash",
            tool_input={"command": "rm -rf /"},
            requesting_mind_id="research-lead",
        )
        assert req.tool_name == "bash"
        assert req.requesting_mind_id == "research-lead"
        assert req.reason == ""

    def test_with_reason(self):
        req = PermissionRequest(
            tool_name="git_push",
            tool_input={"branch": "main"},
            requesting_mind_id="infra-lead",
            reason="Pushing to main branch requires approval",
        )
        assert "approval" in req.reason


class TestPermissionResponse:
    def test_approved(self):
        resp = PermissionResponse(approved=True)
        assert resp.approved
        assert resp.message == ""
        assert resp.modified_input is None

    def test_denied_with_message(self):
        resp = PermissionResponse(approved=False, message="Not authorized")
        assert not resp.approved
        assert resp.message == "Not authorized"

    def test_approved_with_modified_input(self):
        resp = PermissionResponse(
            approved=True,
            modified_input={"command": "echo safe"},
        )
        assert resp.approved
        assert resp.modified_input == {"command": "echo safe"}


# ---------------------------------------------------------------------------
# HookRunner — escalate_tools
# ---------------------------------------------------------------------------


class TestEscalateTools:
    def test_escalate_tools_init(self):
        hooks = HookRunner(escalate_tools=["git_push", "netlify_deploy"])
        assert "git_push" in hooks.escalate_tools
        assert "netlify_deploy" in hooks.escalate_tools

    def test_escalate_tools_empty_by_default(self):
        hooks = HookRunner()
        assert hooks.escalate_tools == set()

    def test_add_escalate_tool(self):
        hooks = HookRunner()
        hooks.add_escalate_tool("git_push")
        assert "git_push" in hooks.escalate_tools

    def test_remove_escalate_tool(self):
        hooks = HookRunner(escalate_tools=["git_push"])
        hooks.remove_escalate_tool("git_push")
        assert "git_push" not in hooks.escalate_tools

    def test_remove_nonexistent_escalate_tool(self):
        hooks = HookRunner()
        hooks.remove_escalate_tool("ghost")  # Should not raise


# ---------------------------------------------------------------------------
# Permission handler registration and invocation
# ---------------------------------------------------------------------------


class TestPermissionHandler:
    def test_register_permission_handler(self):
        hooks = HookRunner(escalate_tools=["git_push"])
        hooks.register_permission_handler(
            lambda req: PermissionResponse(approved=True),
            mind_id="research-lead",
        )
        result = hooks.pre_tool_use("git_push", {"branch": "main"})
        assert result.allowed

    def test_escalated_tool_denied_by_handler(self):
        hooks = HookRunner(escalate_tools=["git_push"])
        hooks.register_permission_handler(
            lambda req: PermissionResponse(approved=False, message="no push"),
            mind_id="sub-1",
        )
        result = hooks.pre_tool_use("git_push", {"branch": "main"})
        assert not result.allowed
        assert "no push" in result.message

    def test_escalated_tool_without_handler_denies(self):
        """If no handler registered and tool needs escalation, fail-closed (deny)."""
        hooks = HookRunner(escalate_tools=["git_push"])
        result = hooks.pre_tool_use("git_push", {"branch": "main"})
        assert not result.allowed
        assert "no permission handler" in result.message.lower()

    def test_permission_request_contains_correct_fields(self):
        captured = []
        hooks = HookRunner(escalate_tools=["bash"])
        hooks.register_permission_handler(
            lambda req: (captured.append(req), PermissionResponse(approved=True))[-1],
            mind_id="test-mind",
        )
        hooks.pre_tool_use("bash", {"command": "echo hi"})
        assert len(captured) == 1
        assert captured[0].tool_name == "bash"
        assert captured[0].tool_input == {"command": "echo hi"}
        assert captured[0].requesting_mind_id == "test-mind"

    def test_permission_handler_error_fails_closed(self):
        """If the permission handler raises, fail-closed (deny)."""
        hooks = HookRunner(escalate_tools=["bash"])
        hooks.register_permission_handler(
            lambda req: (_ for _ in ()).throw(RuntimeError("crash")),
            mind_id="broken",
        )
        result = hooks.pre_tool_use("bash", {})
        assert not result.allowed
        assert "error" in result.message.lower()

    def test_permission_modified_input_flows_through(self):
        """Handler can modify the tool input via modified_input."""
        hooks = HookRunner(escalate_tools=["bash"])
        hooks.register_permission_handler(
            lambda req: PermissionResponse(
                approved=True,
                modified_input={"command": "echo safe"},
            ),
            mind_id="test",
        )
        result = hooks.pre_tool_use("bash", {"command": "rm -rf /"})
        assert result.allowed
        assert result.modified_input == {"command": "echo safe"}


# ---------------------------------------------------------------------------
# Interaction with other hook mechanisms
# ---------------------------------------------------------------------------


class TestPermissionInteractions:
    def test_blocked_tools_checked_before_escalation(self):
        """blocked_tools is higher priority than escalate_tools."""
        captured = []
        hooks = HookRunner(
            blocked_tools=["git_push"],
            escalate_tools=["git_push"],
        )
        hooks.register_permission_handler(
            lambda req: (captured.append("called"), PermissionResponse(approved=True))[-1],
            mind_id="test",
        )
        result = hooks.pre_tool_use("git_push", {})
        assert not result.allowed
        # Permission handler should NOT have been called
        assert "called" not in captured

    def test_escalation_before_custom_hooks(self):
        """escalate_tools fires before custom pre-hooks."""
        calls = []
        hooks = HookRunner(escalate_tools=["bash"])
        hooks.register_pre_hook(
            "custom-1",
            handler=lambda n, i: (calls.append("custom"), HookResult(allowed=True))[-1],
        )
        hooks.register_permission_handler(
            lambda req: (calls.append("perm"), PermissionResponse(approved=True))[-1],
            mind_id="test",
        )
        hooks.pre_tool_use("bash", {})
        # Permission should fire first, then custom hook
        assert calls[0] == "perm"

    def test_escalation_denied_skips_custom_hooks(self):
        """If escalation is denied, custom hooks don't run."""
        calls = []
        hooks = HookRunner(escalate_tools=["bash"])
        hooks.register_pre_hook(
            "custom-1",
            handler=lambda n, i: (calls.append("custom"), HookResult(allowed=True))[-1],
        )
        hooks.register_permission_handler(
            lambda req: PermissionResponse(approved=False, message="denied"),
            mind_id="test",
        )
        result = hooks.pre_tool_use("bash", {})
        assert not result.allowed
        assert "custom" not in calls

    def test_non_escalated_tool_skips_permission(self):
        """Tools not in escalate_tools should not trigger the permission handler."""
        captured = []
        hooks = HookRunner(escalate_tools=["git_push"])
        hooks.register_permission_handler(
            lambda req: (captured.append("called"), PermissionResponse(approved=True))[-1],
            mind_id="test",
        )
        result = hooks.pre_tool_use("bash", {})
        assert result.allowed
        assert len(captured) == 0

    def test_stats_include_escalation_denials(self):
        """Denied escalations should be counted in deny_count."""
        hooks = HookRunner(escalate_tools=["git_push"])
        hooks.register_permission_handler(
            lambda req: PermissionResponse(approved=False, message="no"),
            mind_id="test",
        )
        hooks.pre_tool_use("git_push", {})
        assert hooks.stats["denied"] == 1

    def test_escalation_logged_in_call_log(self):
        """Escalation results should appear in the call log."""
        hooks = HookRunner(escalate_tools=["git_push"])
        hooks.register_permission_handler(
            lambda req: PermissionResponse(approved=False, message="blocked"),
            mind_id="test",
        )
        hooks.pre_tool_use("git_push", {})
        log = hooks.call_log
        assert len(log) == 1
        assert log[0].blocked is True
        assert "permission" in log[0].block_reason.lower()


# ---------------------------------------------------------------------------
# IPC message types for permission requests
# ---------------------------------------------------------------------------


class TestPermissionMessages:
    def test_permission_request_message(self):
        from aiciv_mind.ipc.messages import MindMessage, MsgType

        msg = MindMessage.permission_request(
            sender="research-lead",
            recipient="primary",
            tool_name="git_push",
            tool_input={"branch": "main"},
            reason="Pushing requires approval",
        )
        assert msg.type == MsgType.PERMISSION_REQUEST
        assert msg.sender == "research-lead"
        assert msg.recipient == "primary"
        assert msg.payload["tool_name"] == "git_push"
        assert msg.payload["tool_input"] == {"branch": "main"}
        assert msg.payload["reason"] == "Pushing requires approval"

    def test_permission_response_message(self):
        from aiciv_mind.ipc.messages import MindMessage, MsgType

        msg = MindMessage.permission_response(
            sender="primary",
            recipient="research-lead",
            request_id="abc-123",
            approved=True,
            message="Go ahead",
        )
        assert msg.type == MsgType.PERMISSION_RESPONSE
        assert msg.payload["request_id"] == "abc-123"
        assert msg.payload["approved"] is True
        assert msg.payload["message"] == "Go ahead"

    def test_permission_response_with_modified_input(self):
        from aiciv_mind.ipc.messages import MindMessage, MsgType

        msg = MindMessage.permission_response(
            sender="primary",
            recipient="research-lead",
            request_id="abc-123",
            approved=True,
            modified_input={"command": "echo safe"},
        )
        assert msg.payload["modified_input"] == {"command": "echo safe"}

    def test_permission_request_roundtrip(self):
        from aiciv_mind.ipc.messages import MindMessage, MsgType

        msg = MindMessage.permission_request(
            sender="sub-1",
            recipient="primary",
            tool_name="bash",
            tool_input={"command": "rm -rf /"},
        )
        data = msg.to_bytes()
        restored = MindMessage.from_bytes(data)
        assert restored.type == MsgType.PERMISSION_REQUEST
        assert restored.payload["tool_name"] == "bash"

    def test_msg_type_constants_exist(self):
        from aiciv_mind.ipc.messages import MsgType
        assert hasattr(MsgType, "PERMISSION_REQUEST")
        assert hasattr(MsgType, "PERMISSION_RESPONSE")
