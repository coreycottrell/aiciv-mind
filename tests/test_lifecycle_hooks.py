"""
Tests for lifecycle hooks — on_stop and on_submind_stop.
"""

from __future__ import annotations

import pytest

from aiciv_mind.tools.hooks import HookRunner


class TestOnStopHook:
    def test_on_stop_fires_without_callbacks(self):
        """on_stop should work even with no registered callbacks."""
        hooks = HookRunner()
        hooks.on_stop(mind_id="primary", result="task complete", tool_calls=5)
        # Should not raise

    def test_on_stop_logs_to_call_log(self):
        """on_stop should add an audit log entry."""
        hooks = HookRunner(log_all=True)
        hooks.on_stop(mind_id="primary", result="done", tool_calls=3, session_id="s1")
        assert any(
            r.tool_name == "__lifecycle_stop__"
            for r in hooks.call_log
        )

    def test_on_stop_callback_receives_args(self):
        """Registered callback should receive the correct arguments."""
        received = {}

        def callback(**kwargs):
            received.update(kwargs)

        hooks = HookRunner()
        hooks.register_on_stop(callback)
        hooks.on_stop(
            mind_id="root",
            result="all done",
            tool_calls=7,
            session_id="s2",
            metadata={"key": "val"},
        )

        assert received["mind_id"] == "root"
        assert received["result"] == "all done"
        assert received["tool_calls"] == 7
        assert received["session_id"] == "s2"
        assert received["metadata"]["key"] == "val"

    def test_on_stop_multiple_callbacks(self):
        """Multiple callbacks should all fire."""
        calls = []

        hooks = HookRunner()
        hooks.register_on_stop(lambda **kw: calls.append("cb1"))
        hooks.register_on_stop(lambda **kw: calls.append("cb2"))
        hooks.on_stop(mind_id="test", result="done")

        assert calls == ["cb1", "cb2"]

    def test_on_stop_callback_error_doesnt_crash(self):
        """A failing callback should not prevent other callbacks from firing."""
        calls = []

        def bad_callback(**kw):
            raise RuntimeError("boom")

        hooks = HookRunner()
        hooks.register_on_stop(bad_callback)
        hooks.register_on_stop(lambda **kw: calls.append("ok"))
        hooks.on_stop(mind_id="test", result="done")

        assert "ok" in calls

    def test_on_stop_not_logged_when_log_disabled(self):
        """on_stop should not log when log_all=False."""
        hooks = HookRunner(log_all=False)
        hooks.on_stop(mind_id="test", result="done")
        assert len(hooks.call_log) == 0


class TestOnSubmindStopHook:
    def test_on_submind_stop_fires_without_callbacks(self):
        hooks = HookRunner()
        hooks.on_submind_stop(
            parent_id="primary",
            child_id="researcher",
            result="found 3 papers",
        )

    def test_on_submind_stop_logs_to_call_log(self):
        hooks = HookRunner(log_all=True)
        hooks.on_submind_stop(
            parent_id="primary",
            child_id="coder",
            result="code written",
            exit_code=0,
        )
        assert any(
            r.tool_name == "__lifecycle_submind_stop__"
            for r in hooks.call_log
        )

    def test_on_submind_stop_callback_receives_args(self):
        received = {}

        def callback(**kwargs):
            received.update(kwargs)

        hooks = HookRunner()
        hooks.register_on_submind_stop(callback)
        hooks.on_submind_stop(
            parent_id="root",
            child_id="analyst",
            result="analysis complete",
            exit_code=0,
            metadata={"findings": 5},
        )

        assert received["parent_id"] == "root"
        assert received["child_id"] == "analyst"
        assert received["result"] == "analysis complete"
        assert received["exit_code"] == 0
        assert received["metadata"]["findings"] == 5

    def test_on_submind_stop_error_logged(self):
        """Non-zero exit code should be marked as error in log."""
        hooks = HookRunner(log_all=True)
        hooks.on_submind_stop(
            parent_id="primary",
            child_id="broken",
            result="crashed",
            exit_code=1,
        )
        record = next(
            r for r in hooks.call_log
            if r.tool_name == "__lifecycle_submind_stop__"
        )
        assert record.is_error

    def test_on_submind_stop_callback_error_doesnt_crash(self):
        calls = []

        def bad_callback(**kw):
            raise ValueError("oops")

        hooks = HookRunner()
        hooks.register_on_submind_stop(bad_callback)
        hooks.register_on_submind_stop(lambda **kw: calls.append("ok"))
        hooks.on_submind_stop(
            parent_id="p", child_id="c", result="r",
        )
        assert "ok" in calls


class TestToolRegistryGetHooks:
    def test_get_hooks_returns_none_by_default(self):
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        assert registry.get_hooks() is None

    def test_get_hooks_returns_set_hooks(self):
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        hooks = HookRunner()
        registry.set_hooks(hooks)
        assert registry.get_hooks() is hooks
