"""
aiciv_mind.coordination — Inter-mind coordination protocol.

When two aiciv-mind Primaries connect, they need:
  1. Discovery   — "What can you do?" (CoordinationSurface)
  2. Negotiation — "Who handles what?" (capability matching)
  3. Execution   — "Please do this for me." (CrossMindMessage)
  4. Verification — "Is it done?" (delegation_result)

The protocol builds on the existing fractal coordination pattern.
The same coordinate→delegate→verify→learn loop that works within
a single mind works between minds.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Coordination Surface — what a mind advertises to peers
# ---------------------------------------------------------------------------


@dataclass
class VerticalCapability:
    """A single team lead vertical's advertised capabilities."""

    vertical: str
    capabilities: list[str] = field(default_factory=list)
    fitness_composite: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertical": self.vertical,
            "capabilities": self.capabilities,
            "fitness_composite": round(self.fitness_composite, 3),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VerticalCapability":
        return cls(
            vertical=d["vertical"],
            capabilities=d.get("capabilities", []),
            fitness_composite=d.get("fitness_composite", 0.0),
        )


@dataclass
class CoordinationSurface:
    """
    Read-only coordination surface a mind publishes to peers.

    Contains:
      - mind_id and civ_id for identity
      - team_leads: list of verticals with capabilities and fitness scores
      - active_priorities: what the mind is currently focused on
      - timestamp: when this surface was generated
    """

    mind_id: str
    civ_id: str
    version: str = "0.3"
    team_leads: list[VerticalCapability] = field(default_factory=list)
    active_priorities: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mind_id": self.mind_id,
            "civ_id": self.civ_id,
            "version": self.version,
            "team_leads": [tl.to_dict() for tl in self.team_leads],
            "active_priorities": self.active_priorities,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "CoordinationSurface":
        return cls(
            mind_id=d["mind_id"],
            civ_id=d["civ_id"],
            version=d.get("version", "0.3"),
            team_leads=[
                VerticalCapability.from_dict(tl)
                for tl in d.get("team_leads", [])
            ],
            active_priorities=d.get("active_priorities", []),
            timestamp=d.get("timestamp", time.time()),
        )

    @classmethod
    def from_json(cls, data: str) -> "CoordinationSurface":
        return cls.from_dict(json.loads(data))

    def verticals(self) -> list[str]:
        """Return list of available vertical names."""
        return [tl.vertical for tl in self.team_leads]

    def best_match(self, capability: str) -> VerticalCapability | None:
        """
        Find the team lead vertical best matching a requested capability.

        Returns the vertical with the highest fitness score among those
        that advertise the requested capability. Returns None if no match.
        """
        matches = [
            tl for tl in self.team_leads
            if capability.lower() in [c.lower() for c in tl.capabilities]
        ]
        if not matches:
            return None
        return max(matches, key=lambda tl: tl.fitness_composite)


# ---------------------------------------------------------------------------
# Cross-Mind Message — inter-civ communication wire format
# ---------------------------------------------------------------------------


class CrossMindMsgType:
    """Message types for inter-mind communication."""

    DELEGATION_REQUEST = "delegation_request"
    DELEGATION_RESULT = "delegation_result"
    CAPABILITY_QUERY = "capability_query"
    CAPABILITY_RESPONSE = "capability_response"
    SURFACE_PUBLISH = "surface_publish"
    HEARTBEAT = "heartbeat"


@dataclass
class CrossMindMessage:
    """
    Message between two aiciv-mind instances.

    Uses the same pattern as MindMessage but adds civ-level addressing
    for cross-civilization communication.
    """

    from_civ: str
    from_mind: str
    to_civ: str
    to_mind: str  # or "*" for broadcast to any Primary
    message_type: str
    payload: dict = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_bytes(self) -> bytes:
        """Serialize to UTF-8 JSON bytes for wire transmission."""
        return json.dumps(self.to_dict()).encode("utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_civ": self.from_civ,
            "from_mind": self.from_mind,
            "to_civ": self.to_civ,
            "to_mind": self.to_mind,
            "message_type": self.message_type,
            "payload": self.payload,
            "request_id": self.request_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_bytes(cls, data: bytes) -> "CrossMindMessage":
        """Deserialize from UTF-8 JSON bytes."""
        d = json.loads(data.decode("utf-8"))
        return cls.from_dict(d)

    @classmethod
    def from_dict(cls, d: dict) -> "CrossMindMessage":
        return cls(
            from_civ=d["from_civ"],
            from_mind=d["from_mind"],
            to_civ=d["to_civ"],
            to_mind=d["to_mind"],
            message_type=d["message_type"],
            payload=d.get("payload", {}),
            request_id=d.get("request_id", str(uuid.uuid4())),
            timestamp=d.get("timestamp", time.time()),
        )

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def delegation_request(
        cls,
        from_civ: str,
        from_mind: str,
        to_civ: str,
        to_mind: str,
        task: str,
        target_vertical: str,
        priority: str = "standard",
        context: str = "",
    ) -> "CrossMindMessage":
        """Create a delegation request to another mind's team lead."""
        return cls(
            from_civ=from_civ,
            from_mind=from_mind,
            to_civ=to_civ,
            to_mind=to_mind,
            message_type=CrossMindMsgType.DELEGATION_REQUEST,
            payload={
                "task": task,
                "target_vertical": target_vertical,
                "priority": priority,
                "context": context,
            },
        )

    @classmethod
    def delegation_result(
        cls,
        from_civ: str,
        from_mind: str,
        to_civ: str,
        to_mind: str,
        request_id: str,
        outcome: str,
        summary: str,
        evidence: list[str] | None = None,
    ) -> "CrossMindMessage":
        """Create a delegation result responding to a request."""
        return cls(
            from_civ=from_civ,
            from_mind=from_mind,
            to_civ=to_civ,
            to_mind=to_mind,
            message_type=CrossMindMsgType.DELEGATION_RESULT,
            request_id=request_id,
            payload={
                "outcome": outcome,
                "summary": summary,
                "evidence": evidence or [],
            },
        )

    @classmethod
    def capability_query(
        cls,
        from_civ: str,
        from_mind: str,
        to_civ: str,
        capability: str,
    ) -> "CrossMindMessage":
        """Ask another civ if it can handle a capability."""
        return cls(
            from_civ=from_civ,
            from_mind=from_mind,
            to_civ=to_civ,
            to_mind="*",
            message_type=CrossMindMsgType.CAPABILITY_QUERY,
            payload={"capability": capability},
        )

    @classmethod
    def surface_publish(
        cls,
        from_civ: str,
        from_mind: str,
        surface: "CoordinationSurface",
    ) -> "CrossMindMessage":
        """Publish a coordination surface for peer discovery."""
        return cls(
            from_civ=from_civ,
            from_mind=from_mind,
            to_civ="*",
            to_mind="*",
            message_type=CrossMindMsgType.SURFACE_PUBLISH,
            payload=surface.to_dict(),
        )
