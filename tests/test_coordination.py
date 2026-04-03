"""
Tests for aiciv_mind.coordination — Inter-mind coordination protocol.

Covers:
  - CoordinationSurface: creation, serialization, capability matching
  - CrossMindMessage: creation, serialization, factory methods
  - Round-trip: bytes → object → bytes preserves data
"""

from __future__ import annotations

import json
import time

import pytest

from aiciv_mind.coordination import (
    CoordinationSurface,
    CrossMindMessage,
    CrossMindMsgType,
    VerticalCapability,
)


# ---------------------------------------------------------------------------
# VerticalCapability
# ---------------------------------------------------------------------------


class TestVerticalCapability:
    def test_to_dict(self):
        vc = VerticalCapability(
            vertical="research",
            capabilities=["web-search", "paper-analysis"],
            fitness_composite=0.85,
        )
        d = vc.to_dict()
        assert d["vertical"] == "research"
        assert d["capabilities"] == ["web-search", "paper-analysis"]
        assert d["fitness_composite"] == 0.85

    def test_from_dict(self):
        vc = VerticalCapability.from_dict({
            "vertical": "code",
            "capabilities": ["python", "typescript"],
            "fitness_composite": 0.92,
        })
        assert vc.vertical == "code"
        assert vc.fitness_composite == 0.92

    def test_round_trip(self):
        original = VerticalCapability(
            vertical="comms",
            capabilities=["email", "hub-post", "blog"],
            fitness_composite=0.78,
        )
        restored = VerticalCapability.from_dict(original.to_dict())
        assert restored.vertical == original.vertical
        assert restored.capabilities == original.capabilities
        assert restored.fitness_composite == original.fitness_composite

    def test_defaults(self):
        vc = VerticalCapability(vertical="test")
        assert vc.capabilities == []
        assert vc.fitness_composite == 0.0


# ---------------------------------------------------------------------------
# CoordinationSurface
# ---------------------------------------------------------------------------


class TestCoordinationSurface:
    def test_create_minimal(self):
        surface = CoordinationSurface(mind_id="primary", civ_id="acg")
        assert surface.mind_id == "primary"
        assert surface.civ_id == "acg"
        assert surface.version == "0.3"
        assert surface.team_leads == []
        assert surface.active_priorities == []

    def test_to_dict(self):
        surface = CoordinationSurface(
            mind_id="primary",
            civ_id="acg",
            team_leads=[
                VerticalCapability("research", ["web-search"], 0.85),
                VerticalCapability("code", ["python"], 0.92),
            ],
            active_priorities=["Ship v0.3"],
        )
        d = surface.to_dict()
        assert d["mind_id"] == "primary"
        assert len(d["team_leads"]) == 2
        assert d["team_leads"][0]["vertical"] == "research"
        assert d["active_priorities"] == ["Ship v0.3"]

    def test_to_json_and_back(self):
        original = CoordinationSurface(
            mind_id="primary",
            civ_id="acg",
            team_leads=[
                VerticalCapability("research", ["web-search", "paper-analysis"], 0.85),
            ],
            active_priorities=["Build coordination layer"],
            timestamp=1000000.0,
        )
        json_str = original.to_json()
        restored = CoordinationSurface.from_json(json_str)
        assert restored.mind_id == original.mind_id
        assert restored.civ_id == original.civ_id
        assert len(restored.team_leads) == 1
        assert restored.team_leads[0].vertical == "research"
        assert restored.active_priorities == ["Build coordination layer"]
        assert restored.timestamp == 1000000.0

    def test_verticals(self):
        surface = CoordinationSurface(
            mind_id="p", civ_id="acg",
            team_leads=[
                VerticalCapability("research", [], 0.8),
                VerticalCapability("code", [], 0.9),
                VerticalCapability("comms", [], 0.7),
            ],
        )
        assert surface.verticals() == ["research", "code", "comms"]

    def test_best_match_found(self):
        surface = CoordinationSurface(
            mind_id="p", civ_id="acg",
            team_leads=[
                VerticalCapability("research", ["web-search", "paper-analysis"], 0.85),
                VerticalCapability("code", ["python", "web-search"], 0.92),
            ],
        )
        match = surface.best_match("web-search")
        assert match is not None
        assert match.vertical == "code"  # Higher fitness among matches

    def test_best_match_case_insensitive(self):
        surface = CoordinationSurface(
            mind_id="p", civ_id="acg",
            team_leads=[
                VerticalCapability("research", ["Paper-Analysis"], 0.85),
            ],
        )
        match = surface.best_match("paper-analysis")
        assert match is not None
        assert match.vertical == "research"

    def test_best_match_not_found(self):
        surface = CoordinationSurface(
            mind_id="p", civ_id="acg",
            team_leads=[
                VerticalCapability("research", ["web-search"], 0.85),
            ],
        )
        match = surface.best_match("docker-deploy")
        assert match is None

    def test_best_match_empty_surface(self):
        surface = CoordinationSurface(mind_id="p", civ_id="acg")
        assert surface.best_match("anything") is None

    def test_from_dict_missing_optionals(self):
        surface = CoordinationSurface.from_dict({
            "mind_id": "p",
            "civ_id": "acg",
        })
        assert surface.team_leads == []
        assert surface.active_priorities == []


# ---------------------------------------------------------------------------
# CrossMindMessage
# ---------------------------------------------------------------------------


class TestCrossMindMessage:
    def test_create_minimal(self):
        msg = CrossMindMessage(
            from_civ="acg",
            from_mind="primary",
            to_civ="witness",
            to_mind="primary",
            message_type=CrossMindMsgType.HEARTBEAT,
        )
        assert msg.from_civ == "acg"
        assert msg.to_civ == "witness"
        assert msg.message_type == "heartbeat"
        assert msg.request_id  # Auto-generated
        assert msg.timestamp > 0

    def test_to_bytes_and_back(self):
        original = CrossMindMessage(
            from_civ="acg",
            from_mind="primary",
            to_civ="witness",
            to_mind="primary",
            message_type=CrossMindMsgType.DELEGATION_REQUEST,
            payload={"task": "Deploy service", "target_vertical": "infrastructure"},
            request_id="test-123",
            timestamp=1000000.0,
        )
        wire = original.to_bytes()
        restored = CrossMindMessage.from_bytes(wire)
        assert restored.from_civ == "acg"
        assert restored.to_civ == "witness"
        assert restored.message_type == "delegation_request"
        assert restored.payload["task"] == "Deploy service"
        assert restored.request_id == "test-123"
        assert restored.timestamp == 1000000.0

    def test_to_dict(self):
        msg = CrossMindMessage(
            from_civ="acg",
            from_mind="p",
            to_civ="w",
            to_mind="p",
            message_type="test",
        )
        d = msg.to_dict()
        assert set(d.keys()) == {
            "from_civ", "from_mind", "to_civ", "to_mind",
            "message_type", "payload", "request_id", "timestamp",
        }


# ---------------------------------------------------------------------------
# Factory methods
# ---------------------------------------------------------------------------


class TestFactoryMethods:
    def test_delegation_request(self):
        msg = CrossMindMessage.delegation_request(
            from_civ="acg",
            from_mind="primary",
            to_civ="witness",
            to_mind="primary",
            task="Deploy service to Hetzner",
            target_vertical="infrastructure",
            priority="urgent",
            context="Docker + nginx + SSL needed",
        )
        assert msg.message_type == CrossMindMsgType.DELEGATION_REQUEST
        assert msg.payload["task"] == "Deploy service to Hetzner"
        assert msg.payload["target_vertical"] == "infrastructure"
        assert msg.payload["priority"] == "urgent"
        assert msg.payload["context"] == "Docker + nginx + SSL needed"

    def test_delegation_result(self):
        msg = CrossMindMessage.delegation_result(
            from_civ="witness",
            from_mind="primary",
            to_civ="acg",
            to_mind="primary",
            request_id="req-456",
            outcome="completed",
            summary="Deployed successfully",
            evidence=["docker ps output", "health check OK"],
        )
        assert msg.message_type == CrossMindMsgType.DELEGATION_RESULT
        assert msg.request_id == "req-456"
        assert msg.payload["outcome"] == "completed"
        assert msg.payload["summary"] == "Deployed successfully"
        assert len(msg.payload["evidence"]) == 2

    def test_delegation_result_no_evidence(self):
        msg = CrossMindMessage.delegation_result(
            from_civ="w", from_mind="p",
            to_civ="acg", to_mind="p",
            request_id="r1",
            outcome="failed",
            summary="Timeout",
        )
        assert msg.payload["evidence"] == []

    def test_capability_query(self):
        msg = CrossMindMessage.capability_query(
            from_civ="acg",
            from_mind="primary",
            to_civ="witness",
            capability="docker-deploy",
        )
        assert msg.message_type == CrossMindMsgType.CAPABILITY_QUERY
        assert msg.to_mind == "*"  # Broadcast
        assert msg.payload["capability"] == "docker-deploy"

    def test_surface_publish(self):
        surface = CoordinationSurface(
            mind_id="primary",
            civ_id="acg",
            team_leads=[
                VerticalCapability("research", ["web-search"], 0.85),
            ],
            timestamp=1000000.0,
        )
        msg = CrossMindMessage.surface_publish(
            from_civ="acg",
            from_mind="primary",
            surface=surface,
        )
        assert msg.message_type == CrossMindMsgType.SURFACE_PUBLISH
        assert msg.to_civ == "*"  # Broadcast
        assert msg.to_mind == "*"  # Broadcast
        assert msg.payload["mind_id"] == "primary"
        assert msg.payload["civ_id"] == "acg"
        assert len(msg.payload["team_leads"]) == 1

    def test_surface_publish_round_trip(self):
        """Surface embedded in a CrossMindMessage can be extracted back."""
        surface = CoordinationSurface(
            mind_id="primary",
            civ_id="acg",
            team_leads=[
                VerticalCapability("research", ["web-search", "papers"], 0.85),
                VerticalCapability("code", ["python", "rust"], 0.92),
            ],
            active_priorities=["Ship v0.3", "Hub integration"],
            timestamp=1000000.0,
        )
        msg = CrossMindMessage.surface_publish("acg", "primary", surface)
        wire = msg.to_bytes()
        restored_msg = CrossMindMessage.from_bytes(wire)
        restored_surface = CoordinationSurface.from_dict(restored_msg.payload)
        assert restored_surface.mind_id == "primary"
        assert len(restored_surface.team_leads) == 2
        assert restored_surface.team_leads[1].vertical == "code"
        assert restored_surface.active_priorities == ["Ship v0.3", "Hub integration"]


# ---------------------------------------------------------------------------
# Protocol patterns
# ---------------------------------------------------------------------------


class TestProtocolPatterns:
    def test_delegation_request_response_correlation(self):
        """Request and response share request_id for correlation."""
        request = CrossMindMessage.delegation_request(
            from_civ="acg", from_mind="primary",
            to_civ="witness", to_mind="primary",
            task="Analyze paper", target_vertical="research",
        )
        response = CrossMindMessage.delegation_result(
            from_civ="witness", from_mind="primary",
            to_civ="acg", to_mind="primary",
            request_id=request.request_id,  # Same ID
            outcome="completed",
            summary="Paper analyzed",
        )
        assert request.request_id == response.request_id

    def test_surface_capability_match_flow(self):
        """Full flow: publish surface → query → match → delegate."""
        # Step 1: Witness publishes its surface
        witness_surface = CoordinationSurface(
            mind_id="primary", civ_id="witness",
            team_leads=[
                VerticalCapability("infrastructure", ["docker", "deploy", "ssl"], 0.95),
                VerticalCapability("research", ["web-search"], 0.60),
            ],
        )

        # Step 2: ACG needs docker help, checks Witness's surface
        match = witness_surface.best_match("docker")
        assert match is not None
        assert match.vertical == "infrastructure"
        assert match.fitness_composite == 0.95

        # Step 3: ACG sends delegation request to Witness's infra vertical
        request = CrossMindMessage.delegation_request(
            from_civ="acg", from_mind="primary",
            to_civ="witness", to_mind="primary",
            task="Deploy service with Docker",
            target_vertical=match.vertical,
        )
        assert request.payload["target_vertical"] == "infrastructure"

    def test_broadcast_addressing(self):
        """Broadcast messages use '*' for to_civ and to_mind."""
        msg = CrossMindMessage.surface_publish(
            from_civ="acg", from_mind="primary",
            surface=CoordinationSurface(mind_id="p", civ_id="acg"),
        )
        assert msg.to_civ == "*"
        assert msg.to_mind == "*"

    def test_json_serialization_is_valid(self):
        """All message types produce valid JSON."""
        messages = [
            CrossMindMessage.delegation_request(
                "acg", "p", "w", "p", "task", "research"
            ),
            CrossMindMessage.delegation_result(
                "w", "p", "acg", "p", "r1", "done", "ok"
            ),
            CrossMindMessage.capability_query("acg", "p", "w", "docker"),
            CrossMindMessage.surface_publish(
                "acg", "p",
                CoordinationSurface(mind_id="p", civ_id="acg"),
            ),
        ]
        for msg in messages:
            wire = msg.to_bytes()
            parsed = json.loads(wire)
            assert "message_type" in parsed
            assert "from_civ" in parsed
