"""
aiciv_mind.fork_context — Isolated context execution for complex skills.

CC pattern: "Fork context mode" — skills get an isolated context window
so they don't pollute the main conversation.

When a skill runs in fork mode:
1. Current conversation state is saved (snapshotted)
2. A clean context is created with the skill as the system prompt
3. The skill task runs in the clean context
4. Results are collected
5. Original context is restored with a summary appended

This is lighter than spawning a full sub-mind (no tmux pane, no ZeroMQ).
It reuses the same Mind instance but with context isolation.

Usage:
    fork = ForkContext(
        mind=mind,
        skill_content="# Hub Engagement\nSteps: ...",
        task="Analyze the hub threads and suggest improvements",
    )
    result = await fork.execute()
    # result.output = "Analysis complete. Found 3 improvements..."
    # result.messages_consumed = 5
    # Original context restored with summary appended.
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ForkResult:
    """Result of a forked skill execution."""
    output: str
    messages_consumed: int
    elapsed_ms: float
    skill_id: str = ""
    success: bool = True
    error: str = ""


class ForkContext:
    """
    Isolated context for running a skill without polluting the main conversation.

    Snapshots the current message history, runs the skill with a clean context,
    then restores the original history with a summary of what happened.
    """

    def __init__(
        self,
        messages: list[dict],
        system_prompt: str,
        skill_content: str,
        skill_id: str = "",
        max_messages: int = 50,
    ) -> None:
        """
        Args:
            messages: The current conversation messages (will be snapshotted).
            system_prompt: The current system prompt (will be snapshotted).
            skill_content: The skill's full content to use as the fork's system prompt.
            skill_id: Optional skill ID for tracking.
            max_messages: Max messages to allow in the forked context.
        """
        self._original_messages = messages
        self._original_system_prompt = system_prompt
        self._skill_content = skill_content
        self._skill_id = skill_id
        self._max_messages = max_messages

        # Snapshot state
        self._snapshot_messages: list[dict] = []
        self._snapshot_system_prompt: str = ""
        self._is_forked = False

    def snapshot(self) -> None:
        """Save the current conversation state."""
        self._snapshot_messages = copy.deepcopy(self._original_messages)
        self._snapshot_system_prompt = self._original_system_prompt
        self._is_forked = True
        logger.info(
            "[fork_context] Snapshot saved: %d messages, skill=%s",
            len(self._snapshot_messages), self._skill_id,
        )

    def enter_fork(self) -> tuple[list[dict], str]:
        """
        Enter fork mode: clear messages and set skill as system prompt.

        Returns (empty_messages, skill_system_prompt) for the caller to use.
        """
        if not self._is_forked:
            self.snapshot()

        # Return a clean context with the skill content as system prompt
        fork_system = (
            f"[Fork Context — Skill: {self._skill_id}]\n"
            f"You are executing a skill in isolated context mode. "
            f"Focus only on this skill's task. Your main conversation is paused.\n\n"
            f"{self._skill_content}"
        )

        logger.info(
            "[fork_context] Entered fork: skill=%s, clean context",
            self._skill_id,
        )
        return [], fork_system

    def exit_fork(self, fork_result: str, fork_messages: list[dict]) -> tuple[list[dict], str]:
        """
        Exit fork mode: restore original context with a summary appended.

        Args:
            fork_result: The final output from the forked skill execution.
            fork_messages: Messages consumed during the fork (for stats).

        Returns (restored_messages, original_system_prompt).
        """
        if not self._is_forked:
            logger.warning("[fork_context] exit_fork called without entering fork")
            return self._original_messages, self._original_system_prompt

        # Restore original messages
        restored = copy.deepcopy(self._snapshot_messages)

        # Append a summary of what happened in the fork
        summary = (
            f"[Skill '{self._skill_id}' completed in fork context]\n"
            f"Messages consumed: {len(fork_messages)}\n"
            f"Result: {fork_result[:500]}"
        )
        restored.append({
            "role": "assistant",
            "content": summary,
        })

        self._is_forked = False

        logger.info(
            "[fork_context] Restored context: %d messages + summary",
            len(self._snapshot_messages),
        )
        return restored, self._snapshot_system_prompt

    @property
    def is_forked(self) -> bool:
        return self._is_forked

    @property
    def skill_id(self) -> str:
        return self._skill_id


async def run_skill_forked(
    mind,
    skill_content: str,
    task: str,
    skill_id: str = "",
) -> ForkResult:
    """
    Run a skill in fork context mode using an existing Mind instance.

    This is the high-level API for fork execution:
    1. Snapshot the mind's current state
    2. Replace context with the skill content
    3. Run the task
    4. Restore original context
    5. Return the fork result

    Note: This modifies the mind's _messages and _system_prompt in-place,
    so it MUST complete (or be properly error-handled) before the mind
    continues its normal operation.
    """
    start = time.monotonic()

    fork = ForkContext(
        messages=mind._messages,
        system_prompt=getattr(mind, "_system_prompt", ""),
        skill_content=skill_content,
        skill_id=skill_id,
    )

    try:
        # Enter fork — get clean context
        fork.snapshot()
        clean_messages, fork_system = fork.enter_fork()

        # Swap mind's state to the fork
        original_messages = mind._messages
        original_system = getattr(mind, "_system_prompt", "")

        mind._messages = clean_messages
        if hasattr(mind, "_system_prompt"):
            mind._system_prompt = fork_system

        # Run the task in forked context
        try:
            result = await mind.run_task(task)
            fork_messages = mind._messages
            success = True
            error = ""
        except Exception as e:
            result = f"Fork execution failed: {type(e).__name__}: {e}"
            fork_messages = mind._messages
            success = False
            error = str(e)

        # Exit fork — restore original context
        restored_messages, restored_system = fork.exit_fork(result, fork_messages)
        mind._messages = restored_messages
        if hasattr(mind, "_system_prompt"):
            mind._system_prompt = restored_system

    except Exception as e:
        # Emergency restore if something goes wrong during fork setup
        logger.error("[fork_context] Fork failed, emergency restore: %s", e)
        if "original_messages" in locals():
            mind._messages = original_messages
        if "original_system" in locals() and hasattr(mind, "_system_prompt"):
            mind._system_prompt = original_system
        return ForkResult(
            output=f"Fork failed: {e}",
            messages_consumed=0,
            elapsed_ms=(time.monotonic() - start) * 1000,
            skill_id=skill_id,
            success=False,
            error=str(e),
        )

    elapsed = (time.monotonic() - start) * 1000
    return ForkResult(
        output=result,
        messages_consumed=len(fork_messages),
        elapsed_ms=elapsed,
        skill_id=skill_id,
        success=success,
        error=error,
    )
