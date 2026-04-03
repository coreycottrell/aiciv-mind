"""
Tests for aiciv_mind.tools.coordination_tools — Three-level scratchpad system.

Level 2: Team scratchpads (per vertical)
Level 3: Coordination scratchpad (cross-vertical)
"""

from __future__ import annotations

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.coordination_tools import register_coordination_tools


@pytest.fixture
def registry(tmp_path):
    reg = ToolRegistry()
    register_coordination_tools(reg, str(tmp_path), writer_id="test-mind")
    return reg


@pytest.fixture
def scratchpad_dir(tmp_path):
    return tmp_path


# ---------------------------------------------------------------------------
# team_scratchpad_read
# ---------------------------------------------------------------------------


class TestTeamScratchpadRead:
    def test_read_nonexistent(self, registry):
        import asyncio
        result = asyncio.run(registry.execute("team_scratchpad_read", {"vertical": "research"}))
        assert "No team scratchpad" in result

    def test_read_existing(self, registry, scratchpad_dir):
        import asyncio
        teams_dir = scratchpad_dir / "teams"
        teams_dir.mkdir(exist_ok=True)
        (teams_dir / "research-team.md").write_text("## Research Notes\n- Found 3 papers")

        result = asyncio.run(registry.execute("team_scratchpad_read", {"vertical": "research"}))
        assert "Found 3 papers" in result

    def test_read_empty_vertical(self, registry):
        import asyncio
        result = asyncio.run(registry.execute("team_scratchpad_read", {"vertical": ""}))
        assert "ERROR" in result


# ---------------------------------------------------------------------------
# team_scratchpad_write
# ---------------------------------------------------------------------------


class TestTeamScratchpadWrite:
    def test_write_creates_file(self, registry, scratchpad_dir):
        import asyncio
        result = asyncio.run(registry.execute(
            "team_scratchpad_write",
            {"vertical": "coder", "entry": "Implemented auth module"},
        ))
        assert "Appended" in result
        path = scratchpad_dir / "teams" / "coder-team.md"
        assert path.exists()
        content = path.read_text()
        assert "Implemented auth module" in content
        assert "test-mind" in content  # writer attribution

    def test_write_appends(self, registry, scratchpad_dir):
        import asyncio
        asyncio.run(registry.execute(
            "team_scratchpad_write",
            {"vertical": "coder", "entry": "First entry"},
        ))
        asyncio.run(registry.execute(
            "team_scratchpad_write",
            {"vertical": "coder", "entry": "Second entry"},
        ))
        content = (scratchpad_dir / "teams" / "coder-team.md").read_text()
        assert "First entry" in content
        assert "Second entry" in content

    def test_write_empty_entry(self, registry):
        import asyncio
        result = asyncio.run(registry.execute(
            "team_scratchpad_write",
            {"vertical": "coder", "entry": ""},
        ))
        assert "ERROR" in result

    def test_write_empty_vertical(self, registry):
        import asyncio
        result = asyncio.run(registry.execute(
            "team_scratchpad_write",
            {"vertical": "", "entry": "something"},
        ))
        assert "ERROR" in result


# ---------------------------------------------------------------------------
# coordination_read
# ---------------------------------------------------------------------------


class TestCoordinationRead:
    def test_read_nonexistent(self, tmp_path):
        import asyncio
        import shutil
        # Use a fresh dir without the coordination.md we created above
        fresh = tmp_path / "fresh"
        fresh.mkdir()
        reg = ToolRegistry()
        register_coordination_tools(reg, str(fresh), writer_id="test")
        result = asyncio.run(reg.execute("coordination_read", {}))
        assert "No coordination scratchpad" in result

    def test_read_existing(self, registry, scratchpad_dir):
        import asyncio
        (scratchpad_dir / "coordination.md").write_text("## Priorities\n- Ship auth v2")
        result = asyncio.run(registry.execute("coordination_read", {}))
        assert "Ship auth v2" in result


# ---------------------------------------------------------------------------
# coordination_write
# ---------------------------------------------------------------------------


class TestCoordinationWrite:
    def test_write_creates_file(self, registry, scratchpad_dir):
        import asyncio
        result = asyncio.run(registry.execute(
            "coordination_write",
            {"entry": "Research blocked on Hub API access"},
        ))
        assert "Appended" in result
        content = (scratchpad_dir / "coordination.md").read_text()
        assert "Research blocked" in content
        assert "test-mind" in content

    def test_write_appends(self, registry, scratchpad_dir):
        import asyncio
        asyncio.run(registry.execute(
            "coordination_write",
            {"entry": "Priority 1: Ship auth"},
        ))
        asyncio.run(registry.execute(
            "coordination_write",
            {"entry": "Priority 2: Blog post"},
        ))
        content = (scratchpad_dir / "coordination.md").read_text()
        assert "Priority 1" in content
        assert "Priority 2" in content

    def test_write_empty_entry(self, registry):
        import asyncio
        result = asyncio.run(registry.execute(
            "coordination_write",
            {"entry": ""},
        ))
        assert "ERROR" in result


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_all_tools_registered(self, registry):
        names = registry.names()
        assert "team_scratchpad_read" in names
        assert "team_scratchpad_write" in names
        assert "coordination_read" in names
        assert "coordination_write" in names

    def test_read_tools_are_read_only(self, registry):
        assert registry.is_read_only("team_scratchpad_read") is True
        assert registry.is_read_only("coordination_read") is True

    def test_write_tools_are_not_read_only(self, registry):
        assert registry.is_read_only("team_scratchpad_write") is False
        assert registry.is_read_only("coordination_write") is False
