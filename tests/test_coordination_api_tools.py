"""
Tests for aiciv_mind.tools.coordination_api_tools — publish/read surface tools.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.coordination_api_tools import register_coordination_api_tools


@pytest.fixture
def mock_suite_client():
    client = MagicMock()
    client.post_to_thread = AsyncMock(return_value={"id": "post-1"})
    client.read_thread = AsyncMock(return_value=[])
    return client


@pytest.fixture
def registry(mock_suite_client):
    reg = ToolRegistry()
    register_coordination_api_tools(
        reg, mock_suite_client,
        mind_id="primary", civ_id="acg",
        coordination_thread_id="thread-123",
    )
    return reg


class TestRegistration:
    def test_both_tools_registered(self, registry):
        assert "publish_surface" in registry.names()
        assert "read_surface" in registry.names()

    def test_publish_is_not_read_only(self, registry):
        assert registry.is_read_only("publish_surface") is False

    def test_read_is_read_only(self, registry):
        assert registry.is_read_only("read_surface") is True

    def test_survives_primary_filter(self, mock_suite_client):
        from aiciv_mind.roles import Role
        reg = ToolRegistry()
        register_coordination_api_tools(
            reg, mock_suite_client, "primary", "acg",
        )
        # Add other primary tools so filter works
        for name in ["spawn_team_lead", "coordination_read", "coordination_write",
                      "send_message", "shutdown_team_lead"]:
            reg.register(name, {"name": name}, lambda x: "ok")
        filtered = reg.filter_by_role(Role.PRIMARY)
        assert "publish_surface" in filtered.names()
        assert "read_surface" in filtered.names()


class TestPublishSurface:
    def test_publish_with_thread(self, registry, mock_suite_client):
        result = asyncio.run(registry.execute("publish_surface", {
            "team_leads": [
                {"vertical": "research", "capabilities": ["web-search"], "fitness_composite": 0.85},
                {"vertical": "code", "capabilities": ["python"], "fitness_composite": 0.92},
            ],
            "active_priorities": ["Ship v0.3"],
        }))
        assert "Published" in result
        assert "research" in result
        assert "code" in result
        mock_suite_client.post_to_thread.assert_called_once()
        call_args = mock_suite_client.post_to_thread.call_args
        assert "thread-123" in call_args[0]
        assert "COORDINATION SURFACE" in call_args[0][1]

    def test_publish_without_thread(self, mock_suite_client):
        reg = ToolRegistry()
        register_coordination_api_tools(
            reg, mock_suite_client,
            mind_id="primary", civ_id="acg",
            coordination_thread_id="",  # No thread
        )
        result = asyncio.run(reg.execute("publish_surface", {
            "team_leads": [{"vertical": "research"}],
        }))
        assert "not published" in result
        assert "Surface JSON" in result
        mock_suite_client.post_to_thread.assert_not_called()

    def test_publish_empty_surface(self, registry, mock_suite_client):
        result = asyncio.run(registry.execute("publish_surface", {}))
        assert "Published" in result
        mock_suite_client.post_to_thread.assert_called_once()

    def test_publish_hub_error(self, mock_suite_client):
        mock_suite_client.post_to_thread = AsyncMock(side_effect=RuntimeError("Hub down"))
        reg = ToolRegistry()
        register_coordination_api_tools(
            reg, mock_suite_client,
            mind_id="primary", civ_id="acg",
            coordination_thread_id="thread-123",
        )
        result = asyncio.run(reg.execute("publish_surface", {
            "team_leads": [{"vertical": "research"}],
        }))
        assert "ERROR" in result
        assert "Hub down" in result
        assert "Surface JSON" in result  # Includes the surface even on error


class TestReadSurface:
    def test_read_missing_civ_id(self, registry):
        result = asyncio.run(registry.execute("read_surface", {}))
        assert "ERROR" in result

    def test_read_no_thread(self, mock_suite_client):
        reg = ToolRegistry()
        register_coordination_api_tools(
            reg, mock_suite_client,
            mind_id="primary", civ_id="acg",
            coordination_thread_id="",
        )
        result = asyncio.run(reg.execute("read_surface", {"civ_id": "witness"}))
        assert "ERROR" in result
        assert "thread" in result.lower()

    def test_read_surface_found(self, registry, mock_suite_client):
        surface_json = json.dumps({
            "mind_id": "primary",
            "civ_id": "witness",
            "version": "0.3",
            "team_leads": [
                {"vertical": "infrastructure", "capabilities": ["docker"], "fitness_composite": 0.95},
            ],
            "active_priorities": ["Deploy nodes"],
            "timestamp": 1000000.0,
        }, indent=2)
        mock_suite_client.read_thread = AsyncMock(return_value=[
            {"body": f"[COORDINATION SURFACE]\n```json\n{surface_json}\n```"},
        ])
        result = asyncio.run(registry.execute("read_surface", {"civ_id": "witness"}))
        assert "witness" in result
        assert "infrastructure" in result
        assert "0.95" in result

    def test_read_surface_not_found(self, registry, mock_suite_client):
        mock_suite_client.read_thread = AsyncMock(return_value=[
            {"body": "Just a regular post"},
        ])
        result = asyncio.run(registry.execute("read_surface", {"civ_id": "witness"}))
        assert "No coordination surface found" in result

    def test_read_surface_hub_error(self, registry, mock_suite_client):
        mock_suite_client.read_thread = AsyncMock(side_effect=RuntimeError("timeout"))
        result = asyncio.run(registry.execute("read_surface", {"civ_id": "witness"}))
        assert "ERROR" in result

    def test_read_picks_matching_civ(self, registry, mock_suite_client):
        """When multiple surfaces exist, picks the one matching civ_id."""
        acg_json = json.dumps({
            "mind_id": "p", "civ_id": "acg", "team_leads": [], "active_priorities": [],
        }, indent=2)
        witness_json = json.dumps({
            "mind_id": "p", "civ_id": "witness",
            "team_leads": [{"vertical": "ops", "capabilities": ["deploy"], "fitness_composite": 0.9}],
            "active_priorities": [],
        }, indent=2)
        mock_suite_client.read_thread = AsyncMock(return_value=[
            {"body": f"[COORDINATION SURFACE]\n```json\n{acg_json}\n```"},
            {"body": f"[COORDINATION SURFACE]\n```json\n{witness_json}\n```"},
        ])
        result = asyncio.run(registry.execute("read_surface", {"civ_id": "witness"}))
        assert "witness" in result
        assert "ops" in result
