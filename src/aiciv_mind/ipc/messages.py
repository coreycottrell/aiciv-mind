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
    STATUS = "status"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    SHUTDOWN = "shutdown"
    SHUTDOWN_ACK = "shutdown_ack"
    LOG = "log"


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
