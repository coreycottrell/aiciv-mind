"""
Tests for aiciv_mind.tools.spawn_tools — Role-enforced spawn and shutdown.

Proves the structural constraint: spawn_team_lead validates manifest role,
spawn_agent validates manifest role, registration is role-gated.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.spawn_tools import register_spawn_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass
class FakeHandle:
    mind_id: str
    pane_id: str = "%99"
    pid: int = 12345


@pytest.fixture
def mock_spawner():
    spawner = MagicMock()
    spawner.spawn.return_value = FakeHandle(mind_id="test-mind")
    return spawner


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.send = AsyncMock()
    return bus


@pytest.fixture
def team_lead_manifest(tmp_path):
    """Create a minimal team_lead manifest YAML."""
    m = tmp_path / "tl-manifest.yaml"
    m.write_text(
        "mind_id: research-lead\n"
        "display_name: Research Lead\n"
        "role: team_lead\n"
        "auth:\n"
        "  civ_id: acg\n"
        "  keypair_path: /tmp/fake-key.json\n"
        "memory:\n"
        "  db_path: /tmp/fake.db\n"
    )
    return str(m)


@pytest.fixture
def agent_manifest(tmp_path):
    """Create a minimal agent manifest YAML."""
    m = tmp_path / "agent-manifest.yaml"
    m.write_text(
        "mind_id: coder-1\n"
        "display_name: Coder Agent\n"
        "role: agent\n"
        "auth:\n"
        "  civ_id: acg\n"
        "  keypair_path: /tmp/fake-key.json\n"
        "memory:\n"
        "  db_path: /tmp/fake.db\n"
    )
    return str(m)


@pytest.fixture
def wrong_role_manifest(tmp_path):
    """Create a manifest with wrong role for testing validation."""
    m = tmp_path / "wrong-manifest.yaml"
    m.write_text(
        "mind_id: wrong-role\n"
        "display_name: Wrong Role\n"
        "role: agent\n"  # agent, not team_lead
        "auth:\n"
        "  civ_id: acg\n"
        "  keypair_path: /tmp/fake-key.json\n"
        "memory:\n"
        "  db_path: /tmp/fake.db\n"
    )
    return str(m)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_primary_gets_spawn_team_lead(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "primary", role="primary")
        assert "spawn_team_lead" in reg.names()
        assert "shutdown_team_lead" in reg.names()

    def test_primary_does_not_get_spawn_agent(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "primary", role="primary")
        assert "spawn_agent" not in reg.names()
        assert "shutdown_agent" not in reg.names()

    def test_team_lead_gets_spawn_agent(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "research-lead", role="team_lead")
        assert "spawn_agent" in reg.names()
        assert "shutdown_agent" in reg.names()

    def test_team_lead_does_not_get_spawn_team_lead(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "research-lead", role="team_lead")
        assert "spawn_team_lead" not in reg.names()
        assert "shutdown_team_lead" not in reg.names()

    def test_agent_gets_no_spawn_tools(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "coder-1", role="agent")
        names = reg.names()
        assert "spawn_team_lead" not in names
        assert "spawn_agent" not in names
        assert "shutdown_team_lead" not in names
        assert "shutdown_agent" not in names


# ---------------------------------------------------------------------------
# spawn_team_lead
# ---------------------------------------------------------------------------


class TestSpawnTeamLead:
    def test_spawn_success(self, mock_spawner, mock_bus, team_lead_manifest):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "primary", role="primary")
        result = asyncio.run(reg.execute("spawn_team_lead", {
            "mind_id": "research-lead",
            "manifest_path": team_lead_manifest,
            "vertical": "research",
            "objective": "Find papers on memory systems",
        }))
        assert "Spawned team lead" in result
        assert "research-lead" in result
        assert "research" in result
        mock_spawner.spawn.assert_called_once()

    def test_spawn_wrong_role_rejected(self, mock_spawner, mock_bus, wrong_role_manifest):
        """spawn_team_lead rejects manifests that aren't role: team_lead."""
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "primary", role="primary")
        result = asyncio.run(reg.execute("spawn_team_lead", {
            "mind_id": "wrong",
            "manifest_path": wrong_role_manifest,
            "vertical": "research",
        }))
        assert "ERROR" in result
        assert "team_lead" in result
        mock_spawner.spawn.assert_not_called()

    def test_spawn_missing_mind_id(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "primary", role="primary")
        result = asyncio.run(reg.execute("spawn_team_lead", {
            "manifest_path": "/tmp/fake.yaml",
            "vertical": "research",
        }))
        assert "ERROR" in result
        assert "mind_id" in result

    def test_spawn_missing_vertical(self, mock_spawner, mock_bus, team_lead_manifest):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "primary", role="primary")
        result = asyncio.run(reg.execute("spawn_team_lead", {
            "mind_id": "research-lead",
            "manifest_path": team_lead_manifest,
        }))
        assert "ERROR" in result
        assert "vertical" in result

    def test_spawn_creates_scratchpad_dir(self, mock_spawner, mock_bus, team_lead_manifest, tmp_path):
        scratchpad_dir = str(tmp_path / "scratchpads")
        reg = ToolRegistry()
        register_spawn_tools(
            reg, mock_spawner, mock_bus, "primary",
            role="primary", scratchpad_dir=scratchpad_dir,
        )
        result = asyncio.run(reg.execute("spawn_team_lead", {
            "mind_id": "research-lead",
            "manifest_path": team_lead_manifest,
            "vertical": "research",
        }))
        assert "Spawned team lead" in result
        assert (tmp_path / "scratchpads" / "teams").is_dir()


# ---------------------------------------------------------------------------
# shutdown_team_lead
# ---------------------------------------------------------------------------


class TestShutdownTeamLead:
    def test_shutdown_sends_message(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "primary", role="primary")
        result = asyncio.run(reg.execute("shutdown_team_lead", {
            "mind_id": "research-lead",
        }))
        assert "Shutdown request sent" in result
        assert "research-lead" in result
        mock_bus.send.assert_called_once()

    def test_shutdown_missing_mind_id(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "primary", role="primary")
        result = asyncio.run(reg.execute("shutdown_team_lead", {
            "mind_id": "",
        }))
        assert "ERROR" in result


# ---------------------------------------------------------------------------
# spawn_agent
# ---------------------------------------------------------------------------


class TestSpawnAgent:
    def test_spawn_success(self, mock_spawner, mock_bus, agent_manifest):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "research-lead", role="team_lead")
        result = asyncio.run(reg.execute("spawn_agent", {
            "mind_id": "coder-1",
            "manifest_path": agent_manifest,
            "task": "Implement the auth module",
        }))
        assert "Spawned agent" in result
        assert "coder-1" in result
        mock_spawner.spawn.assert_called_once()

    def test_spawn_wrong_role_rejected(self, mock_spawner, mock_bus, team_lead_manifest):
        """spawn_agent rejects manifests that aren't role: agent."""
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "research-lead", role="team_lead")
        result = asyncio.run(reg.execute("spawn_agent", {
            "mind_id": "wrong",
            "manifest_path": team_lead_manifest,  # team_lead manifest, not agent
        }))
        assert "ERROR" in result
        assert "agent" in result
        mock_spawner.spawn.assert_not_called()

    def test_spawn_missing_mind_id(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "research-lead", role="team_lead")
        result = asyncio.run(reg.execute("spawn_agent", {
            "manifest_path": "/tmp/fake.yaml",
        }))
        assert "ERROR" in result

    def test_spawn_missing_manifest(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "research-lead", role="team_lead")
        result = asyncio.run(reg.execute("spawn_agent", {
            "mind_id": "coder-1",
        }))
        assert "ERROR" in result


# ---------------------------------------------------------------------------
# shutdown_agent
# ---------------------------------------------------------------------------


class TestShutdownAgent:
    def test_shutdown_sends_message(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "research-lead", role="team_lead")
        result = asyncio.run(reg.execute("shutdown_agent", {
            "mind_id": "coder-1",
        }))
        assert "Shutdown request sent" in result
        assert "coder-1" in result
        mock_bus.send.assert_called_once()

    def test_shutdown_missing_mind_id(self, mock_spawner, mock_bus):
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "research-lead", role="team_lead")
        result = asyncio.run(reg.execute("shutdown_agent", {
            "mind_id": "",
        }))
        assert "ERROR" in result


# ---------------------------------------------------------------------------
# Defense-in-depth: role filtering + registration both enforce constraints
# ---------------------------------------------------------------------------


class TestDefenseInDepth:
    def test_primary_filtered_has_spawn_team_lead(self, mock_spawner, mock_bus):
        """When primary registers spawn tools AND filters by role, spawn_team_lead survives."""
        from aiciv_mind.roles import Role
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "primary", role="primary")
        reg.register("coordination_read", {"name": "coordination_read"}, lambda x: "ok")
        reg.register("coordination_write", {"name": "coordination_write"}, lambda x: "ok")
        reg.register("send_message", {"name": "send_message"}, lambda x: "ok")

        filtered = reg.filter_by_role(Role.PRIMARY)
        assert "spawn_team_lead" in filtered.names()
        assert "shutdown_team_lead" in filtered.names()
        assert "spawn_agent" not in filtered.names()

    def test_team_lead_filtered_has_spawn_agent(self, mock_spawner, mock_bus):
        """When team_lead registers spawn tools AND filters by role, spawn_agent survives."""
        from aiciv_mind.roles import Role
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "tl", role="team_lead")
        reg.register("team_scratchpad_read", {"name": "team_scratchpad_read"}, lambda x: "ok")
        reg.register("team_scratchpad_write", {"name": "team_scratchpad_write"}, lambda x: "ok")
        reg.register("coordination_read", {"name": "coordination_read"}, lambda x: "ok")
        reg.register("send_message", {"name": "send_message"}, lambda x: "ok")
        reg.register("memory_search", {"name": "memory_search"}, lambda x: "ok")

        filtered = reg.filter_by_role(Role.TEAM_LEAD)
        assert "spawn_agent" in filtered.names()
        assert "shutdown_agent" in filtered.names()
        assert "spawn_team_lead" not in filtered.names()

    def test_agent_filtered_has_no_spawn_tools(self, mock_spawner, mock_bus):
        """Agent role gets all tools but spawn tools were never registered for agents."""
        from aiciv_mind.roles import Role
        reg = ToolRegistry()
        register_spawn_tools(reg, mock_spawner, mock_bus, "coder-1", role="agent")
        reg.register("bash", {"name": "bash"}, lambda x: "ok")

        filtered = reg.filter_by_role(Role.AGENT)
        assert "bash" in filtered.names()
        assert "spawn_team_lead" not in filtered.names()
        assert "spawn_agent" not in filtered.names()
