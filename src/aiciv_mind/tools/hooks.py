"""
aiciv_mind.tools.hooks — Pre/post tool execution hooks + lifecycle hooks.

Governance layer for tool execution. Pre-hooks can deny tool calls.
Post-hooks log calls for auditing. Pattern from clawd-code HookRunner.

Lifecycle hooks:
    - on_stop: fires when a mind's response completes (cleanup, notifications)
    - on_submind_stop: fires when a spawned sub-mind completes (collect results)

Usage:
    hooks = HookRunner(blocked_tools=["git_push", "netlify_deploy"])

    pre = hooks.pre_tool_use("git_push", {"branch": "main"})
    if not pre.allowed:
        return pre.message  # tool denied

    result = execute_tool(...)

    post = hooks.post_tool_use("git_push", input, result, is_error=False)

    # Lifecycle:
    hooks.on_stop(mind_id="primary", result="task complete", tool_calls=5)
    hooks.on_submind_stop(parent_id="primary", child_id="researcher", result="found 3 papers")
"""

from __future__ import annotations

import json as _json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type for lifecycle callbacks
LifecycleCallback = Callable[..., None]


@dataclass
class HookResult:
    """Result of a hook evaluation."""

    allowed: bool = True
    message: str = ""
    modified_output: str | None = None
    modified_input: dict | None = None


@dataclass
class PermissionRequest:
    """
    Request from a sub-mind to its parent for permission to execute a tool.

    When a sub-mind encounters a tool in its escalate_tools list, it creates
    a PermissionRequest and sends it to the parent mind via the registered handler.
    """

    tool_name: str
    tool_input: dict
    requesting_mind_id: str
    reason: str = ""


@dataclass
class PermissionResponse:
    """
    Parent mind's response to a PermissionRequest.

    approved=True → sub-mind proceeds with tool call.
    approved=False → sub-mind skips tool call, returns message.
    modified_input → if set, sub-mind uses this instead of original input.
    """

    approved: bool
    message: str = ""
    modified_input: dict | None = None


@dataclass
class ToolCallRecord:
    """Audit log entry for a tool call."""

    timestamp: str
    tool_name: str
    input_preview: str
    output_preview: str
    is_error: bool
    blocked: bool = False
    block_reason: str = ""


class HookRunner:
    """
    Pre/post tool execution hooks for governance and auditing.

    Pre-hooks can deny tool calls (returns HookResult with allowed=False).
    Post-hooks log the call and can modify output.
    """

    def __init__(
        self,
        blocked_tools: list[str] | None = None,
        log_all: bool = True,
        escalate_tools: list[str] | None = None,
        audit_log_path: str | Path | None = None,
    ) -> None:
        self._blocked_tools: set[str] = set(blocked_tools or [])
        self._base_blocked_tools: set[str] = set(self._blocked_tools)  # snapshot of base config
        self._escalate_tools: set[str] = set(escalate_tools or [])
        self._permission_handler: Callable[[PermissionRequest], PermissionResponse] | None = None
        self._permission_mind_id: str = ""
        self._log_all = log_all
        self._call_log: list[ToolCallRecord] = []
        self._deny_count: int = 0
        self._total_calls: int = 0
        # Persistent JSONL audit log — training data for dream cycle
        self._audit_log_path: Path | None = None
        if audit_log_path:
            self._audit_log_path = Path(audit_log_path)
            self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Persistent JSONL audit log
    # ------------------------------------------------------------------

    def _audit_write(self, record: dict) -> None:
        """Append a JSON record to the persistent audit log (best-effort)."""
        if self._audit_log_path is None:
            return
        try:
            with open(self._audit_log_path, "a", encoding="utf-8") as f:
                f.write(_json.dumps(record, default=str) + "\n")
        except Exception:
            pass  # audit is telemetry — never crashes the loop

    # ------------------------------------------------------------------
    # Permission escalation — sub-minds request parent approval
    # ------------------------------------------------------------------

    def register_permission_handler(
        self,
        handler: Callable[[PermissionRequest], PermissionResponse],
        mind_id: str = "",
    ) -> None:
        """
        Register a handler for permission escalation.

        When a tool in escalate_tools is called, the handler receives a
        PermissionRequest and returns a PermissionResponse.

        Args:
            handler: Callable that decides whether to approve the tool call.
            mind_id: The mind_id of this mind (used in PermissionRequest.requesting_mind_id).
        """
        self._permission_handler = handler
        self._permission_mind_id = mind_id
        logger.info("[hooks] Registered permission handler (mind_id=%s)", mind_id)

    def add_escalate_tool(self, tool_name: str) -> None:
        """Add a tool to the escalation list."""
        self._escalate_tools.add(tool_name)

    def remove_escalate_tool(self, tool_name: str) -> None:
        """Remove a tool from the escalation list."""
        self._escalate_tools.discard(tool_name)

    @property
    def escalate_tools(self) -> set[str]:
        """Return the set of tools requiring permission escalation."""
        return set(self._escalate_tools)

    # ------------------------------------------------------------------
    # Custom hook registration — shell and callable modes
    # ------------------------------------------------------------------

    def register_pre_hook(
        self,
        name: str,
        handler: Callable[[str, dict], HookResult],
        tools: list[str] | None = None,
        mode: str = "callable",
    ) -> None:
        """
        Register a custom pre-tool-use hook.

        Args:
            name: Unique hook name for identification.
            handler: Callable(tool_name, tool_input) -> HookResult.
            tools: If set, only triggers for these tool names. None = all tools.
            mode: "callable" (Python function) or "shell" (subprocess).
                  For "shell" mode, use make_shell_hook() to create the handler.
        """
        if not hasattr(self, "_custom_pre_hooks"):
            self._custom_pre_hooks: list[dict] = []
        self._custom_pre_hooks.append({
            "name": name,
            "handler": handler,
            "tools": set(tools) if tools else None,
            "mode": mode,
        })
        logger.info("[hooks] Registered pre-hook '%s' (mode=%s, tools=%s)", name, mode, tools)

    def register_post_hook(
        self,
        name: str,
        handler: Callable[[str, dict, str, bool], HookResult],
        tools: list[str] | None = None,
        mode: str = "callable",
    ) -> None:
        """
        Register a custom post-tool-use hook.

        Args:
            name: Unique hook name for identification.
            handler: Callable(tool_name, tool_input, output, is_error) -> HookResult.
            tools: If set, only triggers for these tool names. None = all tools.
            mode: "callable" or "shell".
        """
        if not hasattr(self, "_custom_post_hooks"):
            self._custom_post_hooks: list[dict] = []
        self._custom_post_hooks.append({
            "name": name,
            "handler": handler,
            "tools": set(tools) if tools else None,
            "mode": mode,
        })
        logger.info("[hooks] Registered post-hook '%s' (mode=%s, tools=%s)", name, mode, tools)

    def unregister_hook(self, name: str) -> bool:
        """Remove a custom hook by name. Returns True if found and removed."""
        removed = False
        for attr in ("_custom_pre_hooks", "_custom_post_hooks"):
            hooks = getattr(self, attr, [])
            before = len(hooks)
            filtered = [h for h in hooks if h["name"] != name]
            if len(filtered) < before:
                setattr(self, attr, filtered)
                removed = True
        if removed:
            logger.info("[hooks] Unregistered hook '%s'", name)
        return removed

    @property
    def custom_hooks(self) -> list[str]:
        """Return names of all registered custom hooks."""
        names = []
        for h in getattr(self, "_custom_pre_hooks", []):
            names.append(f"pre:{h['name']}")
        for h in getattr(self, "_custom_post_hooks", []):
            names.append(f"post:{h['name']}")
        return names

    def _handle_permission_escalation(self, tool_name: str, tool_input: dict) -> HookResult:
        """
        Handle a tool that requires permission escalation.

        Creates a PermissionRequest and sends it to the registered handler.
        If no handler is registered, fails closed (denies).
        If the handler raises, fails closed (denies).
        """
        if self._permission_handler is None:
            self._deny_count += 1
            reason = (
                f"Tool '{tool_name}' requires permission escalation but "
                "no permission handler is registered. Denied (fail-closed)."
            )
            logger.warning("[hooks] DENIED (no permission handler): %s", tool_name)
            if self._log_all:
                self._call_log.append(ToolCallRecord(
                    timestamp=datetime.now().isoformat(),
                    tool_name=tool_name,
                    input_preview=str(tool_input)[:200],
                    output_preview="",
                    is_error=False,
                    blocked=True,
                    block_reason=f"Permission escalation: {reason}",
                ))
            return HookResult(allowed=False, message=reason)

        request = PermissionRequest(
            tool_name=tool_name,
            tool_input=tool_input,
            requesting_mind_id=self._permission_mind_id,
        )

        try:
            response = self._permission_handler(request)
        except Exception as e:
            self._deny_count += 1
            reason = f"Permission handler error: {e}. Denied (fail-closed)."
            logger.error("[hooks] Permission handler error for %s: %s", tool_name, e)
            if self._log_all:
                self._call_log.append(ToolCallRecord(
                    timestamp=datetime.now().isoformat(),
                    tool_name=tool_name,
                    input_preview=str(tool_input)[:200],
                    output_preview="",
                    is_error=False,
                    blocked=True,
                    block_reason=f"Permission escalation: {reason}",
                ))
            return HookResult(allowed=False, message=reason)

        if not response.approved:
            self._deny_count += 1
            logger.warning(
                "[hooks] Permission DENIED for %s: %s", tool_name, response.message,
            )
            if self._log_all:
                self._call_log.append(ToolCallRecord(
                    timestamp=datetime.now().isoformat(),
                    tool_name=tool_name,
                    input_preview=str(tool_input)[:200],
                    output_preview="",
                    is_error=False,
                    blocked=True,
                    block_reason=f"Permission denied: {response.message}",
                ))
            return HookResult(allowed=False, message=response.message)

        # Approved
        logger.info("[hooks] Permission APPROVED for %s", tool_name)
        return HookResult(
            allowed=True,
            modified_input=response.modified_input,
        )

    def pre_tool_use(self, tool_name: str, tool_input: dict) -> HookResult:
        """
        Evaluate whether a tool call should proceed.

        Check order: blocked_tools → escalate_tools → custom pre-hooks.
        Any check returning denied will short-circuit the rest.
        """
        self._total_calls += 1

        # 1. Built-in: blocked tools check (hard deny, no escalation)
        if tool_name in self._blocked_tools:
            self._deny_count += 1
            reason = (
                f"Tool '{tool_name}' is blocked by hook policy. "
                "This tool requires human approval before execution."
            )
            logger.warning("[hooks] DENIED: %s — %s", tool_name, reason)

            if self._log_all:
                self._call_log.append(ToolCallRecord(
                    timestamp=datetime.now().isoformat(),
                    tool_name=tool_name,
                    input_preview=str(tool_input)[:200],
                    output_preview="",
                    is_error=False,
                    blocked=True,
                    block_reason=reason,
                ))

            return HookResult(allowed=False, message=reason)

        # 2. Permission escalation: tools that need parent approval
        if tool_name in self._escalate_tools:
            return self._handle_permission_escalation(tool_name, tool_input)

        # 3. Custom pre-hooks
        for hook in getattr(self, "_custom_pre_hooks", []):
            if hook["tools"] is not None and tool_name not in hook["tools"]:
                continue  # Skip — this hook doesn't apply to this tool
            try:
                result = hook["handler"](tool_name, tool_input)
                if not result.allowed:
                    self._deny_count += 1
                    logger.warning(
                        "[hooks] DENIED by hook '%s': %s — %s",
                        hook["name"], tool_name, result.message,
                    )
                    if self._log_all:
                        self._call_log.append(ToolCallRecord(
                            timestamp=datetime.now().isoformat(),
                            tool_name=tool_name,
                            input_preview=str(tool_input)[:200],
                            output_preview="",
                            is_error=False,
                            blocked=True,
                            block_reason=f"Hook '{hook['name']}': {result.message}",
                        ))
                    return result
            except Exception as e:
                logger.error("[hooks] Pre-hook '%s' error: %s", hook["name"], e)
                # Hook errors are non-fatal — allow the tool call to proceed

        # Audit: log allowed pre-tool call
        self._audit_write({
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "pre_tool_use",
            "tool": tool_name,
            "input": str(tool_input)[:500],
        })

        return HookResult(allowed=True)

    def post_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
        output: str,
        is_error: bool,
        duration_ms: int = 0,
    ) -> HookResult:
        """
        Post-execution hook. Logs the call and runs custom post-hooks.

        Custom post-hooks can deny (suppress output) or modify output.
        """
        if self._log_all:
            self._call_log.append(ToolCallRecord(
                timestamp=datetime.now().isoformat(),
                tool_name=tool_name,
                input_preview=str(tool_input)[:200],
                output_preview=output[:200],
                is_error=is_error,
            ))

        # Persistent audit
        self._audit_write({
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "post_tool_use",
            "tool": tool_name,
            "duration_ms": duration_ms,
            "result_len": len(output),
            "is_error": is_error,
        })

        # Custom post-hooks
        for hook in getattr(self, "_custom_post_hooks", []):
            if hook["tools"] is not None and tool_name not in hook["tools"]:
                continue
            try:
                result = hook["handler"](tool_name, tool_input, output, is_error)
                if not result.allowed:
                    logger.warning(
                        "[hooks] Post-hook '%s' denied: %s",
                        hook["name"], result.message,
                    )
                    return result
                if result.modified_output is not None:
                    return result
            except Exception as e:
                logger.error("[hooks] Post-hook '%s' error: %s", hook["name"], e)

        return HookResult(allowed=True)

    def block_tool(self, tool_name: str) -> None:
        """Dynamically block a tool at runtime."""
        self._blocked_tools.add(tool_name)
        logger.info("[hooks] Blocked tool: %s", tool_name)

    def unblock_tool(self, tool_name: str) -> None:
        """Dynamically unblock a tool at runtime."""
        self._blocked_tools.discard(tool_name)
        logger.info("[hooks] Unblocked tool: %s", tool_name)

    # ------------------------------------------------------------------
    # Skill-defined hooks — skills register their own governance rules
    # ------------------------------------------------------------------

    def install_skill_hooks(self, skill_id: str, hooks_config: dict) -> None:
        """
        Install hooks declared by a skill.

        hooks_config format:
            {
                "blocked_tools": ["git_push", "netlify_deploy"],
                "pre_tool_use": [
                    {"tool": "bash", "action": "warn", "reason": "..."},
                ],
            }

        Tracked per skill_id so they can be cleanly uninstalled later.
        """
        if not hasattr(self, "_skill_hooks"):
            self._skill_hooks: dict[str, dict] = {}

        # Store the config for later uninstall
        self._skill_hooks[skill_id] = hooks_config

        # Apply blocked_tools
        for tool_name in hooks_config.get("blocked_tools", []):
            self._blocked_tools.add(tool_name)
            logger.info("[hooks] Skill '%s' blocked tool: %s", skill_id, tool_name)

        # Apply pre_tool_use warn rules (stored for pre_tool_use to check)
        if not hasattr(self, "_skill_warn_rules"):
            self._skill_warn_rules: dict[str, list[dict]] = {}
        for rule in hooks_config.get("pre_tool_use", []):
            if rule.get("action") == "warn":
                tool = rule.get("tool", "")
                if tool:
                    self._skill_warn_rules.setdefault(tool, []).append({
                        "skill_id": skill_id,
                        "reason": rule.get("reason", f"Warning from skill '{skill_id}'"),
                    })

        logger.info(
            "[hooks] Installed hooks for skill '%s': %d blocked, %d warn rules",
            skill_id,
            len(hooks_config.get("blocked_tools", [])),
            len(hooks_config.get("pre_tool_use", [])),
        )

    def uninstall_skill_hooks(self, skill_id: str) -> None:
        """
        Remove all hooks installed by a skill.

        Only unblocks tools that were blocked by THIS skill (not by other
        skills or the base blocked_tools list).
        """
        if not hasattr(self, "_skill_hooks"):
            return

        config = self._skill_hooks.pop(skill_id, None)
        if config is None:
            return

        # Unblock tools that this skill blocked (but only if no OTHER skill
        # also blocks them AND it's not in the base blocked set)
        other_blocked: set[str] = set(self._base_blocked_tools)
        for other_id, other_config in self._skill_hooks.items():
            other_blocked.update(other_config.get("blocked_tools", []))

        for tool_name in config.get("blocked_tools", []):
            if tool_name not in other_blocked:
                self._blocked_tools.discard(tool_name)
                logger.info("[hooks] Skill '%s' unblocked tool: %s", skill_id, tool_name)

        # Remove warn rules
        if hasattr(self, "_skill_warn_rules"):
            for tool_name, rules in list(self._skill_warn_rules.items()):
                self._skill_warn_rules[tool_name] = [
                    r for r in rules if r.get("skill_id") != skill_id
                ]
                if not self._skill_warn_rules[tool_name]:
                    del self._skill_warn_rules[tool_name]

        logger.info("[hooks] Uninstalled hooks for skill '%s'", skill_id)

    @property
    def active_skill_hooks(self) -> dict[str, dict]:
        """Return a copy of all active skill hook configurations."""
        return dict(getattr(self, "_skill_hooks", {}))

    @property
    def blocked_tools(self) -> set[str]:
        """Return the set of currently blocked tools."""
        return set(self._blocked_tools)

    @property
    def call_log(self) -> list[ToolCallRecord]:
        """Return a copy of the call audit log."""
        return list(self._call_log)

    @property
    def stats(self) -> dict:
        """Return hook statistics."""
        return {
            "total_calls": self._total_calls,
            "denied": self._deny_count,
            "logged": len(self._call_log),
            "blocked_tools": sorted(self._blocked_tools),
        }

    # ------------------------------------------------------------------
    # Lifecycle hooks — fire at mind lifecycle events
    # ------------------------------------------------------------------

    def register_on_stop(self, callback: LifecycleCallback) -> None:
        """Register a callback to fire when a mind's response completes."""
        if not hasattr(self, "_on_stop_callbacks"):
            self._on_stop_callbacks: list[LifecycleCallback] = []
        self._on_stop_callbacks.append(callback)

    def register_on_submind_stop(self, callback: LifecycleCallback) -> None:
        """Register a callback to fire when a sub-mind completes."""
        if not hasattr(self, "_on_submind_stop_callbacks"):
            self._on_submind_stop_callbacks: list[LifecycleCallback] = []
        self._on_submind_stop_callbacks.append(callback)

    def on_stop(
        self,
        mind_id: str,
        result: str,
        tool_calls: int = 0,
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Fire stop hook — called when a mind's task execution completes.

        Used for:
        - Cleanup (releasing resources, closing connections)
        - Notifications (alerting other systems of completion)
        - Session learning (triggering Loop 2 wrapup)
        - Handoff preparation (writing session state for next boot)
        """
        logger.info(
            "[hooks] on_stop: mind=%s, tool_calls=%d, result_len=%d",
            mind_id, tool_calls, len(result),
        )

        if self._log_all:
            self._call_log.append(ToolCallRecord(
                timestamp=datetime.now().isoformat(),
                tool_name="__lifecycle_stop__",
                input_preview=f"mind_id={mind_id}, session={session_id}",
                output_preview=result[:200],
                is_error=False,
            ))

        for cb in getattr(self, "_on_stop_callbacks", []):
            try:
                cb(
                    mind_id=mind_id,
                    result=result,
                    tool_calls=tool_calls,
                    session_id=session_id,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.error("[hooks] on_stop callback error: %s", e)

    def on_submind_stop(
        self,
        parent_id: str,
        child_id: str,
        result: str,
        exit_code: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Fire sub-mind stop hook — called when a spawned sub-mind completes.

        Used for:
        - Result collection (gathering output from parallel sub-minds)
        - Resource cleanup (freeing context windows, tmux panes)
        - Error detection (sub-mind crashed or failed)
        - Orchestration (deciding next steps based on sub-mind results)
        """
        logger.info(
            "[hooks] on_submind_stop: parent=%s, child=%s, exit=%d, result_len=%d",
            parent_id, child_id, exit_code, len(result),
        )

        if self._log_all:
            self._call_log.append(ToolCallRecord(
                timestamp=datetime.now().isoformat(),
                tool_name="__lifecycle_submind_stop__",
                input_preview=f"parent={parent_id}, child={child_id}, exit={exit_code}",
                output_preview=result[:200],
                is_error=exit_code != 0,
            ))

        for cb in getattr(self, "_on_submind_stop_callbacks", []):
            try:
                cb(
                    parent_id=parent_id,
                    child_id=child_id,
                    result=result,
                    exit_code=exit_code,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.error("[hooks] on_submind_stop callback error: %s", e)


# ---------------------------------------------------------------------------
# Hook factories — create handlers for different execution modes
# ---------------------------------------------------------------------------


def make_shell_pre_hook(command: str, timeout: float = 5.0) -> Callable[[str, dict], HookResult]:
    """
    Create a pre-tool-use hook that runs a shell command.

    The command receives environment variables:
        HOOK_TOOL_NAME  — the tool being called
        HOOK_TOOL_INPUT — JSON-encoded tool input

    Exit code 0 = ALLOW. Non-zero = DENY.
    Stdout is captured as the reason/message.

    Args:
        command: Shell command to execute (e.g. "python3 /path/to/check.py")
        timeout: Maximum execution time in seconds (default 5s)
    """
    import json
    import os
    import subprocess

    def handler(tool_name: str, tool_input: dict) -> HookResult:
        env = os.environ.copy()
        env["HOOK_TOOL_NAME"] = tool_name
        env["HOOK_TOOL_INPUT"] = json.dumps(tool_input)

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            if proc.returncode == 0:
                return HookResult(allowed=True)
            else:
                message = proc.stdout.strip() or proc.stderr.strip() or f"Shell hook denied (exit {proc.returncode})"
                return HookResult(allowed=False, message=message)
        except subprocess.TimeoutExpired:
            logger.warning("[hooks] Shell pre-hook timed out after %.1fs: %s", timeout, command)
            return HookResult(allowed=True)  # Timeout = allow (fail-open)
        except Exception as e:
            logger.error("[hooks] Shell pre-hook error: %s", e)
            return HookResult(allowed=True)  # Errors = allow (fail-open)

    return handler


def make_shell_post_hook(command: str, timeout: float = 5.0) -> Callable[[str, dict, str, bool], HookResult]:
    """
    Create a post-tool-use hook that runs a shell command.

    The command receives environment variables:
        HOOK_TOOL_NAME   — the tool that was called
        HOOK_TOOL_INPUT  — JSON-encoded tool input
        HOOK_TOOL_OUTPUT — first 1000 chars of tool output
        HOOK_IS_ERROR    — "true" or "false"

    Exit code 0 = ALLOW. Non-zero = DENY (suppress output).
    """
    import json
    import os
    import subprocess

    def handler(tool_name: str, tool_input: dict, output: str, is_error: bool) -> HookResult:
        env = os.environ.copy()
        env["HOOK_TOOL_NAME"] = tool_name
        env["HOOK_TOOL_INPUT"] = json.dumps(tool_input)
        env["HOOK_TOOL_OUTPUT"] = output[:1000]
        env["HOOK_IS_ERROR"] = "true" if is_error else "false"

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            if proc.returncode == 0:
                modified = proc.stdout.strip() if proc.stdout.strip() else None
                return HookResult(allowed=True, modified_output=modified)
            else:
                message = proc.stdout.strip() or f"Post-hook denied (exit {proc.returncode})"
                return HookResult(allowed=False, message=message)
        except subprocess.TimeoutExpired:
            return HookResult(allowed=True)
        except Exception as e:
            logger.error("[hooks] Shell post-hook error: %s", e)
            return HookResult(allowed=True)

    return handler
