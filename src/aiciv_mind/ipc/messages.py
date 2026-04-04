"""
aiciv_mind.ipc.messages — MindMessage dataclass and MsgType constants.

MindMessage is the single wire format for all IPC communication between
the primary mind (ROUTER) and sub-minds (DEALERs). Serialized as JSON.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class MsgType:
    """String constants for all recognized message types."""

    TASK = "task"
    RESULT = "result"
    COMPLETION = "completion"
    STATUS = "status"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    READY = "ready"
    SHUTDOWN = "shutdown"
    SHUTDOWN_ACK = "shutdown_ack"
    LOG = "log"
    PERMISSION_REQUEST = "permission_request"
    PERMISSION_RESPONSE = "permission_response"


@dataclass
class MindMessage:
    """
    Single wire format for all IPC messages between minds.

    Fields:
        type      — MsgType constant identifying the message kind
        sender    — mind_id of the originating mind
        recipient — mind_id of the intended destination
        id        — unique message UUID (auto-generated)
        timestamp — Unix timestamp (auto-generated)
        payload   — type-specific data dict
    """

    type: str
    sender: str
    recipient: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    payload: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialize to UTF-8 encoded JSON bytes for wire transmission."""
        return json.dumps(
            {
                "type": self.type,
                "sender": self.sender,
                "recipient": self.recipient,
                "id": self.id,
                "timestamp": self.timestamp,
                "payload": self.payload,
            }
        ).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "MindMessage":
        """Deserialize from UTF-8 encoded JSON bytes. Missing optional fields use defaults."""
        d = json.loads(data.decode("utf-8"))
        return cls(
            type=d["type"],
            sender=d["sender"],
            recipient=d["recipient"],
            id=d.get("id", str(uuid.uuid4())),
            timestamp=d.get("timestamp", time.time()),
            payload=d.get("payload", {}),
        )

    # ------------------------------------------------------------------
    # Message factories
    # ------------------------------------------------------------------

    @classmethod
    def task(
        cls,
        sender: str,
        recipient: str,
        task_id: str,
        objective: str,
        context: dict | None = None,
    ) -> "MindMessage":
        """Create a TASK message dispatching work to a sub-mind."""
        return cls(
            type=MsgType.TASK,
            sender=sender,
            recipient=recipient,
            payload={
                "task_id": task_id,
                "objective": objective,
                "context": context or {},
            },
        )

    @classmethod
    def result(
        cls,
        sender: str,
        recipient: str,
        task_id: str,
        result: str,
        success: bool = True,
        error: str | None = None,
    ) -> "MindMessage":
        """Create a RESULT message returning work output to the primary."""
        return cls(
            type=MsgType.RESULT,
            sender=sender,
            recipient=recipient,
            payload={
                "task_id": task_id,
                "result": result,
                "success": success,
                "error": error,
            },
        )

    @classmethod
    def shutdown(
        cls,
        sender: str,
        recipient: str,
        reason: str = "orchestrator_request",
    ) -> "MindMessage":
        """Create a SHUTDOWN message requesting a sub-mind to terminate."""
        return cls(
            type=MsgType.SHUTDOWN,
            sender=sender,
            recipient=recipient,
            payload={"reason": reason},
        )

    @classmethod
    def shutdown_ack(
        cls,
        sender: str,
        recipient: str,
        mind_id: str,
    ) -> "MindMessage":
        """Create a SHUTDOWN_ACK confirming graceful shutdown."""
        return cls(
            type=MsgType.SHUTDOWN_ACK,
            sender=sender,
            recipient=recipient,
            payload={"mind_id": mind_id},
        )

    @classmethod
    def ready(cls, sender: str, recipient: str) -> "MindMessage":
        """Create a READY message indicating sub-mind has connected and is listening."""
        return cls(type=MsgType.READY, sender=sender, recipient=recipient)

    @classmethod
    def heartbeat(cls, sender: str, recipient: str) -> "MindMessage":
        """Create a HEARTBEAT ping."""
        return cls(type=MsgType.HEARTBEAT, sender=sender, recipient=recipient)

    @classmethod
    def heartbeat_ack(cls, sender: str, recipient: str) -> "MindMessage":
        """Create a HEARTBEAT_ACK response."""
        return cls(type=MsgType.HEARTBEAT_ACK, sender=sender, recipient=recipient)

    @classmethod
    def status(
        cls,
        sender: str,
        recipient: str,
        task_id: str,
        progress: str,
        pct: int | None = None,
    ) -> "MindMessage":
        """Create a STATUS update for an in-progress task."""
        return cls(
            type=MsgType.STATUS,
            sender=sender,
            recipient=recipient,
            payload={"task_id": task_id, "progress": progress, "pct": pct},
        )

    @classmethod
    def log(
        cls,
        sender: str,
        recipient: str,
        level: str,
        message: str,
    ) -> "MindMessage":
        """Create a LOG message forwarding a log entry to the primary."""
        return cls(
            type=MsgType.LOG,
            sender=sender,
            recipient=recipient,
            payload={"level": level, "message": message},
        )

    @classmethod
    def completion(
        cls,
        sender: str,
        recipient: str,
        event: "MindCompletionEvent",
    ) -> "MindMessage":
        """Create a COMPLETION message wrapping a MindCompletionEvent."""
        return cls(
            type=MsgType.COMPLETION,
            sender=sender,
            recipient=recipient,
            payload=event.to_dict(),
        )

    @classmethod
    def permission_request(
        cls,
        sender: str,
        recipient: str,
        tool_name: str,
        tool_input: dict,
        reason: str = "",
    ) -> "MindMessage":
        """
        Create a PERMISSION_REQUEST message.

        Sent by a sub-mind to its parent when it encounters a tool in its
        escalate_tools list and needs approval to proceed.
        """
        return cls(
            type=MsgType.PERMISSION_REQUEST,
            sender=sender,
            recipient=recipient,
            payload={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "reason": reason,
            },
        )

    @classmethod
    def permission_response(
        cls,
        sender: str,
        recipient: str,
        request_id: str,
        approved: bool,
        message: str = "",
        modified_input: dict | None = None,
    ) -> "MindMessage":
        """
        Create a PERMISSION_RESPONSE message.

        Sent by the parent mind back to the requesting sub-mind with
        the approval decision. Optionally includes modified tool input.
        """
        return cls(
            type=MsgType.PERMISSION_RESPONSE,
            sender=sender,
            recipient=recipient,
            payload={
                "request_id": request_id,
                "approved": approved,
                "message": message,
                "modified_input": modified_input,
            },
        )


@dataclass
class MindCompletionEvent:
    """
    Structured result format emitted when a sub-mind finishes a task.

    The coordinator receives summaries, not floods (Principle P5).
    This is the information architecture for hierarchical context distribution.

    Fields:
        mind_id      — which mind completed the task
        task_id      — the task that was completed
        status       — "success", "error", or "partial"
        summary      — 5-15 word human-readable summary (the ONLY thing the
                        coordinator needs to inject into its context)
        result       — full result text (stored but not necessarily injected)
        tokens_used  — total tokens consumed by this task
        tool_calls   — number of tool calls made
        duration_ms  — wall-clock execution time in milliseconds
        tools_used   — list of distinct tool names invoked
        error        — error message if status != "success"
    """

    mind_id: str
    task_id: str
    status: str  # "success", "error", "partial"
    summary: str
    result: str = ""
    tokens_used: int = 0
    tool_calls: int = 0
    duration_ms: int = 0
    tools_used: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for embedding in MindMessage payload."""
        return {
            "mind_id": self.mind_id,
            "task_id": self.task_id,
            "status": self.status,
            "summary": self.summary,
            "result": self.result,
            "tokens_used": self.tokens_used,
            "tool_calls": self.tool_calls,
            "duration_ms": self.duration_ms,
            "tools_used": self.tools_used,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MindCompletionEvent":
        """Deserialize from dict (e.g., from MindMessage payload)."""
        return cls(
            mind_id=d["mind_id"],
            task_id=d["task_id"],
            status=d["status"],
            summary=d["summary"],
            result=d.get("result", ""),
            tokens_used=d.get("tokens_used", 0),
            tool_calls=d.get("tool_calls", 0),
            duration_ms=d.get("duration_ms", 0),
            tools_used=d.get("tools_used", []),
            error=d.get("error"),
        )

    def context_line(self) -> str:
        """
        One-line context entry for the coordinator's system prompt.

        Format: [mind_id] STATUS: summary (Nt, Tc tools, Dms)
        Example: [research-lead] SUCCESS: Found 3 relevant papers (1240t, 5 tools, 3200ms)
        """
        return (
            f"[{self.mind_id}] {self.status.upper()}: {self.summary} "
            f"({self.tokens_used}t, {self.tool_calls} tools, {self.duration_ms}ms)"
        )
