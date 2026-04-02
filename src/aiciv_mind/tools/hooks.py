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

import logging
from dataclasses import dataclass, field
from datetime import datetime
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
    ) -> None:
        self._blocked_tools: set[str] = set(blocked_tools or [])
        self._base_blocked_tools: set[str] = set(self._blocked_tools)  # snapshot of base config
        self._log_all = log_all
        self._call_log: list[ToolCallRecord] = []
        self._deny_count: int = 0
        self._total_calls: int = 0

    def pre_tool_use(self, tool_name: str, tool_input: dict) -> HookResult:
        """
        Evaluate whether a tool call should proceed.

        Returns HookResult with allowed=False if the tool is blocked.
        """
        self._total_calls += 1

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

        return HookResult(allowed=True)

    def post_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
        output: str,
        is_error: bool,
    ) -> HookResult:
        """
        Post-execution hook. Logs the call for audit trail.

        Can be extended to modify output or deny based on results.
        """
        if self._log_all:
            self._call_log.append(ToolCallRecord(
                timestamp=datetime.now().isoformat(),
                tool_name=tool_name,
                input_preview=str(tool_input)[:200],
                output_preview=output[:200],
                is_error=is_error,
            ))

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
