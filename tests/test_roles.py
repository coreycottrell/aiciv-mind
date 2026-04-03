"""
Tests for aiciv_mind.roles — Role enum, tool whitelists, structural constraints.

The core guarantee: Primary cannot call bash. Team leads cannot write files.
Agents get everything. These tests prove the structural constraints hold.
"""

from __future__ import annotations

import pytest

from aiciv_mind.roles import (
    Role,
    PRIMARY_TOOLS,
    TEAM_LEAD_TOOLS,
    AGENT_TOOLS,
    ROLE_TOOL_WHITELIST,
    tools_for_role,
)


# ---------------------------------------------------------------------------
# Role enum
# ---------------------------------------------------------------------------


class TestRoleEnum:
    def test_primary_value(self):
        assert Role.PRIMARY.value == "primary"

    def test_team_lead_value(self):
        assert Role.TEAM_LEAD.value == "team_lead"

    def test_agent_value(self):
        assert Role.AGENT.value == "agent"

    def test_from_str_primary(self):
        assert Role.from_str("primary") == Role.PRIMARY

    def test_from_str_team_lead_underscore(self):
        assert Role.from_str("team_lead") == Role.TEAM_LEAD

    def test_from_str_team_lead_hyphen(self):
        assert Role.from_str("team-lead") == Role.TEAM_LEAD

    def test_from_str_agent(self):
        assert Role.from_str("agent") == Role.AGENT

    def test_from_str_case_insensitive(self):
        assert Role.from_str("PRIMARY") == Role.PRIMARY
        assert Role.from_str("Team_Lead") == Role.TEAM_LEAD

    def test_from_str_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown role"):
            Role.from_str("superuser")

    def test_from_str_empty_raises(self):
        with pytest.raises(ValueError):
            Role.from_str("")


# ---------------------------------------------------------------------------
# Tool whitelists — structural constraints
# ---------------------------------------------------------------------------


class TestToolWhitelists:
    def test_primary_has_exactly_5_tools(self):
        assert len(PRIMARY_TOOLS) == 5

    def test_primary_tools_content(self):
        assert "spawn_team_lead" in PRIMARY_TOOLS
        assert "coordination_read" in PRIMARY_TOOLS
        assert "coordination_write" in PRIMARY_TOOLS
        assert "send_message" in PRIMARY_TOOLS
        assert "shutdown_team_lead" in PRIMARY_TOOLS

    def test_primary_cannot_bash(self):
        """Primary must NOT have bash access."""
        assert "bash" not in PRIMARY_TOOLS

    def test_primary_cannot_read_files(self):
        assert "read_file" not in PRIMARY_TOOLS

    def test_primary_cannot_write_files(self):
        assert "write_file" not in PRIMARY_TOOLS

    def test_primary_cannot_search_memory(self):
        assert "memory_search" not in PRIMARY_TOOLS

    def test_primary_cannot_spawn_agents(self):
        assert "spawn_agent" not in PRIMARY_TOOLS

    def test_team_lead_has_7_tools(self):
        assert len(TEAM_LEAD_TOOLS) == 7

    def test_team_lead_tools_content(self):
        assert "spawn_agent" in TEAM_LEAD_TOOLS
        assert "team_scratchpad_read" in TEAM_LEAD_TOOLS
        assert "team_scratchpad_write" in TEAM_LEAD_TOOLS
        assert "coordination_read" in TEAM_LEAD_TOOLS
        assert "send_message" in TEAM_LEAD_TOOLS
        assert "memory_search" in TEAM_LEAD_TOOLS
        assert "shutdown_agent" in TEAM_LEAD_TOOLS

    def test_team_lead_cannot_bash(self):
        """Team leads must NOT have bash access."""
        assert "bash" not in TEAM_LEAD_TOOLS

    def test_team_lead_cannot_write_files(self):
        assert "write_file" not in TEAM_LEAD_TOOLS

    def test_team_lead_cannot_spawn_team_leads(self):
        assert "spawn_team_lead" not in TEAM_LEAD_TOOLS

    def test_agent_tools_is_none(self):
        """Agent gets all tools — represented by None (no filter)."""
        assert AGENT_TOOLS is None


# ---------------------------------------------------------------------------
# tools_for_role mapping
# ---------------------------------------------------------------------------


class TestToolsForRole:
    def test_primary_returns_frozenset(self):
        result = tools_for_role(Role.PRIMARY)
        assert isinstance(result, frozenset)
        assert result == PRIMARY_TOOLS

    def test_team_lead_returns_frozenset(self):
        result = tools_for_role(Role.TEAM_LEAD)
        assert isinstance(result, frozenset)
        assert result == TEAM_LEAD_TOOLS

    def test_agent_returns_none(self):
        result = tools_for_role(Role.AGENT)
        assert result is None

    def test_role_whitelist_covers_all_roles(self):
        """Every Role enum member has a whitelist entry."""
        for role in Role:
            assert role in ROLE_TOOL_WHITELIST


# ---------------------------------------------------------------------------
# ToolRegistry.filter_by_role
# ---------------------------------------------------------------------------


class TestToolRegistryFilterByRole:
    def test_primary_filter_excludes_bash(self):
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        registry.register("bash", {"name": "bash"}, lambda x: "ok")
        registry.register("coordination_read", {"name": "coordination_read"}, lambda x: "ok")
        registry.register("spawn_team_lead", {"name": "spawn_team_lead"}, lambda x: "ok")

        filtered = registry.filter_by_role(Role.PRIMARY)
        assert "bash" not in filtered.names()
        assert "coordination_read" in filtered.names()
        assert "spawn_team_lead" in filtered.names()

    def test_agent_filter_keeps_everything(self):
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        registry.register("bash", {"name": "bash"}, lambda x: "ok")
        registry.register("write_file", {"name": "write_file"}, lambda x: "ok")

        filtered = registry.filter_by_role(Role.AGENT)
        assert "bash" in filtered.names()
        assert "write_file" in filtered.names()

    def test_team_lead_filter_keeps_memory_search(self):
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        registry.register("memory_search", {"name": "memory_search"}, lambda x: "ok")
        registry.register("bash", {"name": "bash"}, lambda x: "ok")

        filtered = registry.filter_by_role(Role.TEAM_LEAD)
        assert "memory_search" in filtered.names()
        assert "bash" not in filtered.names()

    def test_filter_preserves_hooks(self):
        from aiciv_mind.tools import ToolRegistry
        from aiciv_mind.tools.hooks import HookRunner
        registry = ToolRegistry()
        hooks = HookRunner()
        registry.set_hooks(hooks)
        registry.register("coordination_read", {"name": "coordination_read"}, lambda x: "ok")

        filtered = registry.filter_by_role(Role.PRIMARY)
        assert filtered.get_hooks() is hooks

    def test_filter_preserves_timeouts(self):
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        registry.register("spawn_team_lead", {"name": "spawn_team_lead"}, lambda x: "ok", timeout=60.0)

        filtered = registry.filter_by_role(Role.PRIMARY)
        assert filtered._timeouts.get("spawn_team_lead") == 60.0

    def test_primary_cannot_call_unknown_tools(self):
        """Tools not in the whitelist are silently excluded."""
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        registry.register("web_search", {"name": "web_search"}, lambda x: "ok")
        registry.register("hub_post", {"name": "hub_post"}, lambda x: "ok")
        registry.register("git_commit", {"name": "git_commit"}, lambda x: "ok")

        filtered = registry.filter_by_role(Role.PRIMARY)
        assert len(filtered.names()) == 0  # None of these are in PRIMARY_TOOLS
