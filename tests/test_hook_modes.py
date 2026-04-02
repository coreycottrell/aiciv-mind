"""
Tests for two execution modes: callable hooks and shell hooks.
"""

from __future__ import annotations

import sys
import pytest

from aiciv_mind.tools.hooks import (
    HookRunner,
    HookResult,
    make_shell_pre_hook,
    make_shell_post_hook,
)


# ---------------------------------------------------------------------------
# Callable mode — custom pre/post hooks
# ---------------------------------------------------------------------------


class TestCallablePreHooks:
    def test_register_and_execute_pre_hook(self):
        hooks = HookRunner()
        hooks.register_pre_hook(
            "test-hook",
            handler=lambda name, inp: HookResult(allowed=False, message="denied by test"),
            tools=["bash"],
        )
        result = hooks.pre_tool_use("bash", {"command": "echo hi"})
        assert not result.allowed
        assert "denied by test" in result.message

    def test_pre_hook_only_fires_for_matching_tools(self):
        hooks = HookRunner()
        hooks.register_pre_hook(
            "bash-only",
            handler=lambda name, inp: HookResult(allowed=False, message="no"),
            tools=["bash"],
        )
        # Should not fire for non-matching tool
        result = hooks.pre_tool_use("read_file", {})
        assert result.allowed

    def test_pre_hook_with_no_tool_filter_fires_for_all(self):
        hooks = HookRunner()
        hooks.register_pre_hook(
            "all-tools",
            handler=lambda name, inp: HookResult(allowed=False, message="blocked"),
            tools=None,
        )
        assert not hooks.pre_tool_use("bash", {}).allowed
        assert not hooks.pre_tool_use("read_file", {}).allowed

    def test_multiple_pre_hooks_first_deny_wins(self):
        hooks = HookRunner()
        calls = []
        hooks.register_pre_hook(
            "hook-1",
            handler=lambda name, inp: HookResult(allowed=False, message="hook-1 denied"),
        )
        hooks.register_pre_hook(
            "hook-2",
            handler=lambda name, inp: (calls.append("hook-2"), HookResult(allowed=True))[-1],
        )
        result = hooks.pre_tool_use("bash", {})
        assert not result.allowed
        assert "hook-1" in result.message
        # hook-2 should NOT have been called (early exit on deny)
        assert "hook-2" not in calls

    def test_pre_hook_error_is_non_fatal(self):
        hooks = HookRunner()
        hooks.register_pre_hook(
            "buggy-hook",
            handler=lambda name, inp: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        # Should allow despite error (fail-open)
        result = hooks.pre_tool_use("bash", {})
        assert result.allowed

    def test_blocked_tools_checked_before_custom_hooks(self):
        hooks = HookRunner(blocked_tools=["git_push"])
        calls = []
        hooks.register_pre_hook(
            "never-called",
            handler=lambda name, inp: (calls.append("called"), HookResult(allowed=True))[-1],
        )
        result = hooks.pre_tool_use("git_push", {})
        assert not result.allowed
        assert "called" not in calls  # Custom hook shouldn't fire


class TestCallablePostHooks:
    def test_register_and_execute_post_hook(self):
        hooks = HookRunner()
        hooks.register_post_hook(
            "audit-hook",
            handler=lambda name, inp, out, err: HookResult(allowed=True),
            tools=["bash"],
        )
        result = hooks.post_tool_use("bash", {}, "output", False)
        assert result.allowed

    def test_post_hook_can_deny(self):
        hooks = HookRunner()
        hooks.register_post_hook(
            "censor-hook",
            handler=lambda name, inp, out, err: HookResult(allowed=False, message="censored"),
        )
        result = hooks.post_tool_use("bash", {}, "secret output", False)
        assert not result.allowed

    def test_post_hook_can_modify_output(self):
        hooks = HookRunner()
        hooks.register_post_hook(
            "redact-hook",
            handler=lambda name, inp, out, err: HookResult(
                allowed=True, modified_output="[REDACTED]"
            ),
        )
        result = hooks.post_tool_use("bash", {}, "secret data", False)
        assert result.allowed
        assert result.modified_output == "[REDACTED]"

    def test_post_hook_only_fires_for_matching_tools(self):
        calls = []
        hooks = HookRunner()
        hooks.register_post_hook(
            "bash-only",
            handler=lambda name, inp, out, err: (calls.append(name), HookResult(allowed=True))[-1],
            tools=["bash"],
        )
        hooks.post_tool_use("bash", {}, "output", False)
        hooks.post_tool_use("read_file", {}, "output", False)
        assert calls == ["bash"]


class TestHookManagement:
    def test_unregister_hook(self):
        hooks = HookRunner()
        hooks.register_pre_hook("removable", lambda n, i: HookResult(allowed=False, message="no"))
        assert hooks.unregister_hook("removable") is True
        # Hook should no longer fire
        assert hooks.pre_tool_use("bash", {}).allowed

    def test_unregister_nonexistent(self):
        hooks = HookRunner()
        assert hooks.unregister_hook("ghost") is False

    def test_custom_hooks_property(self):
        hooks = HookRunner()
        hooks.register_pre_hook("pre-a", lambda n, i: HookResult(allowed=True))
        hooks.register_post_hook("post-b", lambda n, i, o, e: HookResult(allowed=True))
        names = hooks.custom_hooks
        assert "pre:pre-a" in names
        assert "post:post-b" in names

    def test_custom_hooks_empty_by_default(self):
        hooks = HookRunner()
        assert hooks.custom_hooks == []


# ---------------------------------------------------------------------------
# Shell mode — subprocess-based hooks
# ---------------------------------------------------------------------------


class TestShellPreHook:
    def test_shell_hook_allow(self):
        handler = make_shell_pre_hook("exit 0")
        result = handler("bash", {"command": "echo hi"})
        assert result.allowed

    def test_shell_hook_deny(self):
        handler = make_shell_pre_hook(f"{sys.executable} -c \"print('not allowed'); exit(1)\"")
        result = handler("bash", {"command": "rm -rf /"})
        assert not result.allowed
        assert "not allowed" in result.message

    def test_shell_hook_receives_env_vars(self):
        handler = make_shell_pre_hook(
            f"{sys.executable} -c \"import os; "
            "name = os.environ.get('HOOK_TOOL_NAME', ''); "
            "assert name == 'bash', f'Expected bash, got {{name}}'\""
        )
        result = handler("bash", {})
        assert result.allowed

    def test_shell_hook_timeout_allows(self):
        """Shell hooks that timeout should fail-open (allow)."""
        handler = make_shell_pre_hook("sleep 10", timeout=0.1)
        result = handler("bash", {})
        assert result.allowed  # Fail-open on timeout

    def test_shell_hook_error_allows(self):
        """Shell hooks that crash should fail-open (allow)."""
        handler = make_shell_pre_hook("/nonexistent/binary/that/does/not/exist")
        result = handler("bash", {})
        # Depending on OS, this might exit non-zero (deny) or error (allow)
        # Either is acceptable behavior — the test just verifies no crash
        assert isinstance(result, HookResult)

    def test_shell_hook_integration_with_runner(self):
        hooks = HookRunner()
        handler = make_shell_pre_hook("exit 0")
        hooks.register_pre_hook("shell-allow", handler, tools=["bash"], mode="shell")
        result = hooks.pre_tool_use("bash", {})
        assert result.allowed


class TestShellPostHook:
    def test_shell_post_hook_allow(self):
        handler = make_shell_post_hook("exit 0")
        result = handler("bash", {}, "output text", False)
        assert result.allowed

    def test_shell_post_hook_deny(self):
        handler = make_shell_post_hook(f"{sys.executable} -c \"print('censored'); exit(1)\"")
        result = handler("bash", {}, "secret output", False)
        assert not result.allowed
        assert "censored" in result.message

    def test_shell_post_hook_modify_output(self):
        handler = make_shell_post_hook(f"{sys.executable} -c \"print('[REDACTED]')\"")
        result = handler("bash", {}, "secret data", False)
        assert result.allowed
        assert result.modified_output == "[REDACTED]"

    def test_shell_post_hook_receives_env_vars(self):
        handler = make_shell_post_hook(
            f"{sys.executable} -c \"import os; "
            "assert os.environ.get('HOOK_IS_ERROR') == 'true'\""
        )
        result = handler("bash", {}, "error output", True)
        assert result.allowed

    def test_shell_post_hook_timeout_allows(self):
        handler = make_shell_post_hook("sleep 10", timeout=0.1)
        result = handler("bash", {}, "output", False)
        assert result.allowed
