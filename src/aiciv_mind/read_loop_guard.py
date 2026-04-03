"""
aiciv_mind.read_loop_guard — Detect and break repetitive read-without-write loops.

Gap 4 fix: When an agent reads the same file 3+ times without writing anything,
inject a warning. At 5+ reads, force a different action.

This is a structural guard — no LLM calls, pure pattern detection.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class GuardAction(Enum):
    """What the guard recommends."""
    ALLOW = "allow"        # Normal operation
    WARN = "warn"          # Inject a warning but allow the read
    BLOCK = "block"        # Block the read, force different action
    FORCE_STOP = "force_stop"  # Too many iterations without progress


@dataclass
class GuardResult:
    """Result of checking a tool call against the read loop guard."""
    action: GuardAction
    message: str = ""
    reads_without_write: int = 0
    most_read_file: str = ""


class ReadLoopGuard:
    """
    Tracks file reads and writes per agent session.
    Detects when an agent is stuck in a read loop (reading the same files
    repeatedly without producing any output).

    Thresholds:
        - 3 reads of same file without any write → WARN
        - 5 reads of same file without any write → BLOCK
        - 10 total reads without any write → FORCE_STOP
    """

    WARN_THRESHOLD = 3     # reads of same file before warning
    BLOCK_THRESHOLD = 5    # reads of same file before blocking
    FORCE_STOP_THRESHOLD = 10  # total reads without any write

    # Tool names that count as "read" operations
    READ_TOOLS = frozenset({
        "read_file", "list_directory", "search_files", "search_code",
        "read_resource", "glob", "grep",
    })

    # Tool names that count as "write" operations (reset read counters)
    WRITE_TOOLS = frozenset({
        "write_file", "edit_file", "bash", "spawn_agent", "spawn_team_lead",
        "store_memory", "send_message",
    })

    def __init__(self) -> None:
        # file_path -> read count since last write
        self._file_reads: dict[str, int] = defaultdict(int)
        # Total reads since last write
        self._total_reads_since_write: int = 0
        # Total writes this session
        self._total_writes: int = 0

    def check(self, tool_name: str, tool_input: dict) -> GuardResult:
        """
        Check a tool call against the read loop guard.

        Call this BEFORE executing each tool. If the result action is BLOCK
        or FORCE_STOP, return the message as the tool result instead of
        executing the tool.

        Args:
            tool_name: Name of the tool being called
            tool_input: The tool's input parameters

        Returns:
            GuardResult with recommended action
        """
        # Normalize tool name to lowercase for matching
        name_lower = tool_name.lower()

        # Check if this is a write tool → reset counters
        if name_lower in self.WRITE_TOOLS or any(w in name_lower for w in ("write", "edit", "store", "spawn")):
            self._on_write()
            return GuardResult(action=GuardAction.ALLOW)

        # Check if this is a read tool
        if name_lower not in self.READ_TOOLS and not any(r in name_lower for r in ("read", "search", "list", "glob", "grep")):
            # Not a read tool — allow without tracking
            return GuardResult(action=GuardAction.ALLOW)

        # Extract file path from tool input (various field names)
        file_path = (
            tool_input.get("path", "") or
            tool_input.get("file_path", "") or
            tool_input.get("file", "") or
            tool_input.get("pattern", "") or
            tool_input.get("query", "") or
            str(tool_input)[:100]
        )

        # Track the read
        self._file_reads[file_path] += 1
        self._total_reads_since_write += 1
        file_count = self._file_reads[file_path]

        # Find the most-read file for reporting
        most_read = max(self._file_reads, key=self._file_reads.get) if self._file_reads else ""
        most_read_count = self._file_reads.get(most_read, 0)

        # Check FORCE_STOP first (total reads threshold)
        if self._total_reads_since_write >= self.FORCE_STOP_THRESHOLD:
            msg = (
                f"[READ LOOP GUARD — FORCE STOP] You have read {self._total_reads_since_write} "
                f"times without writing ANY output. Most-read: '{most_read}' ({most_read_count}x). "
                f"You MUST write output NOW or explain why you cannot. "
                f"Do NOT read another file — produce results with what you have."
            )
            logger.warning("[ReadLoopGuard] FORCE_STOP: %d reads, 0 writes", self._total_reads_since_write)
            return GuardResult(
                action=GuardAction.FORCE_STOP,
                message=msg,
                reads_without_write=self._total_reads_since_write,
                most_read_file=most_read,
            )

        # Check per-file BLOCK threshold
        if file_count >= self.BLOCK_THRESHOLD:
            msg = (
                f"[READ LOOP GUARD — BLOCKED] You have read '{file_path}' {file_count} times "
                f"without writing anything. This read is BLOCKED. "
                f"Use the information you already have to produce output. "
                f"If you need different information, read a DIFFERENT file."
            )
            logger.warning("[ReadLoopGuard] BLOCK: '%s' read %dx", file_path, file_count)
            return GuardResult(
                action=GuardAction.BLOCK,
                message=msg,
                reads_without_write=self._total_reads_since_write,
                most_read_file=file_path,
            )

        # Check per-file WARN threshold
        if file_count >= self.WARN_THRESHOLD:
            msg = (
                f"[READ LOOP GUARD — WARNING] You have read '{file_path}' {file_count} times "
                f"without writing any output ({self._total_reads_since_write} total reads, 0 writes). "
                f"Consider writing output with what you have before reading more."
            )
            logger.info("[ReadLoopGuard] WARN: '%s' read %dx", file_path, file_count)
            return GuardResult(
                action=GuardAction.WARN,
                message=msg,
                reads_without_write=self._total_reads_since_write,
                most_read_file=file_path,
            )

        return GuardResult(action=GuardAction.ALLOW)

    def _on_write(self) -> None:
        """Reset read counters when a write occurs."""
        self._file_reads.clear()
        self._total_reads_since_write = 0
        self._total_writes += 1

    def stats(self) -> dict:
        """Return guard statistics."""
        return {
            "total_writes": self._total_writes,
            "reads_since_last_write": self._total_reads_since_write,
            "unique_files_read": len(self._file_reads),
            "file_read_counts": dict(self._file_reads),
        }

    def reset(self) -> None:
        """Full reset (e.g. between tasks)."""
        self._file_reads.clear()
        self._total_reads_since_write = 0
        self._total_writes = 0
