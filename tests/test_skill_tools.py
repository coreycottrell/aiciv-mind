"""
Tests for aiciv_mind.tools.skill_tools — Skill loading, listing, and creation.

Also covers MemoryStore skill methods (register_skill, get_skill, search_skills,
touch_skill, list_skills).

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_skill_tools.py -v
"""

from __future__ import annotations

import pytest

from aiciv_mind.memory import MemoryStore
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.skill_tools import register_skill_tools


# ---------------------------------------------------------------------------
# MemoryStore skill methods
# ---------------------------------------------------------------------------


def test_register_and_get_skill(memory_store: MemoryStore) -> None:
    """register_skill() inserts a skill; get_skill() retrieves it."""
    memory_store.register_skill(
        skill_id="test-skill",
        name="Test Skill",
        domain="testing",
        file_path="/tmp/skills/test-skill/SKILL.md",
        effectiveness=0.8,
    )
    skill = memory_store.get_skill("test-skill")
    assert skill is not None
    assert skill["skill_id"] == "test-skill"
    assert skill["name"] == "Test Skill"
    assert skill["domain"] == "testing"
    assert skill["file_path"] == "/tmp/skills/test-skill/SKILL.md"
    assert skill["effectiveness"] == 0.8
    assert skill["usage_count"] == 0


def test_search_skills(memory_store: MemoryStore) -> None:
    """search_skills() finds skills by keyword in skill_id, name, or domain."""
    memory_store.register_skill("hub-engage", "Hub Engagement", "comms", "/a")
    memory_store.register_skill("memory-clean", "Memory Cleanup", "memory", "/b")

    results = memory_store.search_skills("hub")
    assert len(results) == 1
    assert results[0]["skill_id"] == "hub-engage"

    results = memory_store.search_skills("memory")
    # matches both name ("Memory Cleanup") and domain ("memory")
    assert len(results) >= 1
    ids = [r["skill_id"] for r in results]
    assert "memory-clean" in ids


def test_touch_skill_increments_count(memory_store: MemoryStore) -> None:
    """touch_skill() increments usage_count and sets last_used_at."""
    memory_store.register_skill("touchable", "Touchable", "test", "/x")

    memory_store.touch_skill("touchable")
    memory_store.touch_skill("touchable")
    memory_store.touch_skill("touchable")

    skill = memory_store.get_skill("touchable")
    assert skill is not None
    assert skill["usage_count"] == 3
    assert skill["last_used_at"] is not None


def test_list_skills_method(memory_store: MemoryStore) -> None:
    """list_skills() returns all registered skills."""
    memory_store.register_skill("s1", "Skill One", "a", "/1")
    memory_store.register_skill("s2", "Skill Two", "b", "/2")

    skills = memory_store.list_skills()
    assert len(skills) == 2
    ids = {s["skill_id"] for s in skills}
    assert ids == {"s1", "s2"}


def test_get_skill_not_found(memory_store: MemoryStore) -> None:
    """get_skill() returns None for unknown skill_id."""
    assert memory_store.get_skill("nonexistent") is None


# ---------------------------------------------------------------------------
# Skill tool handlers
# ---------------------------------------------------------------------------


def test_load_skill_tool(tmp_path, memory_store: MemoryStore) -> None:
    """load_skill handler reads a SKILL.md file and increments usage count."""
    # Create a skill file
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("# Test Skill\nThis is a test skill.")

    # Register in memory store
    memory_store.register_skill("test-skill", "Test Skill", "test", str(skill_file))

    # Register tools
    registry = ToolRegistry()
    register_skill_tools(registry, memory_store, str(tmp_path))

    # Execute
    import asyncio
    result = asyncio.run(
        registry.execute("load_skill", {"skill_id": "test-skill"})
    )

    assert "# Test Skill" in result
    assert "This is a test skill." in result

    # Verify usage count incremented
    skill = memory_store.get_skill("test-skill")
    assert skill["usage_count"] == 1


def test_load_skill_not_found(tmp_path, memory_store: MemoryStore) -> None:
    """load_skill returns error for unknown skill_id."""
    registry = ToolRegistry()
    register_skill_tools(registry, memory_store, str(tmp_path))

    import asyncio
    result = asyncio.run(
        registry.execute("load_skill", {"skill_id": "nope"})
    )
    assert "ERROR" in result
    assert "not found" in result


def test_list_skills_tool(tmp_path, memory_store: MemoryStore) -> None:
    """list_skills handler returns formatted skill list."""
    memory_store.register_skill("sk-a", "Skill A", "alpha", "/a")
    memory_store.register_skill("sk-b", "Skill B", "beta", "/b")

    registry = ToolRegistry()
    register_skill_tools(registry, memory_store, str(tmp_path))

    import asyncio
    result = asyncio.run(
        registry.execute("list_skills", {})
    )
    assert "sk-a" in result
    assert "sk-b" in result
    assert "alpha" in result
    assert "beta" in result


def test_list_skills_tool_empty(tmp_path, memory_store: MemoryStore) -> None:
    """list_skills handler returns message when no skills registered."""
    registry = ToolRegistry()
    register_skill_tools(registry, memory_store, str(tmp_path))

    import asyncio
    result = asyncio.run(
        registry.execute("list_skills", {})
    )
    assert "No skills registered" in result


def test_create_skill_tool(tmp_path, memory_store: MemoryStore) -> None:
    """create_skill handler creates file and registers skill."""
    registry = ToolRegistry()
    register_skill_tools(registry, memory_store, str(tmp_path))

    content = "---\nskill_id: new-skill\ndomain: test\n---\n# New Skill\nCreated at runtime."

    import asyncio
    result = asyncio.run(
        registry.execute("create_skill", {
            "skill_id": "new-skill",
            "domain": "test",
            "content": content,
        })
    )
    assert "Created skill 'new-skill'" in result

    # Verify file exists
    skill_file = tmp_path / "new-skill" / "SKILL.md"
    assert skill_file.exists()
    assert "# New Skill" in skill_file.read_text()

    # Verify registered in memory store
    skill = memory_store.get_skill("new-skill")
    assert skill is not None
    assert skill["domain"] == "test"
