"""
aiciv_mind.tools.hooks — Pre/post tool execution hooks.

Governance layer for tool execution. Pre-hooks can deny tool calls.
Post-hooks log calls for auditing. Pattern from clawd-code HookRunner.

Usage:
    hooks = HookRunner(blocked_tools=["git_push", "netlify_deploy"])

    pre = hooks.pre_tool_use("git_push", {"branch": "main"})
    if not pre.allowed:
        return pre.message  # tool denied

    result = execute_tool(...)

    post = hooks.post_tool_use("git_push", input, result, is_error=False)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


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
