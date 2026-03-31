"""
aiciv_mind.tools.skill_tools — Skill loading, listing, and creation tools.

Skills are reusable protocols/workflows stored as SKILL.md files and registered
in the memory store's skills table. These tools enable a mind to discover,
load, and create new skills at runtime.
"""

from __future__ import annotations

import re
from pathlib import Path

from aiciv_mind.tools import ToolRegistry


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_LOAD_SKILL_DEFINITION: dict = {
    "name": "load_skill",
    "description": (
        "Load a skill by ID. Reads the SKILL.md file and returns its content. "
        "Also increments the skill's usage count."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": "The skill ID to load (e.g. 'hub-engagement')",
            },
        },
        "required": ["skill_id"],
    },
}

_LIST_SKILLS_DEFINITION: dict = {
    "name": "list_skills",
    "description": "List all registered skills with their IDs, domains, and usage counts.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

_CREATE_SKILL_DEFINITION: dict = {
    "name": "create_skill",
    "description": (
        "Create a new skill. Writes a SKILL.md file and registers it. "
        "Content should be markdown with frontmatter (skill_id, domain, version, trigger)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": "Unique skill identifier (e.g. 'error-recovery')",
            },
            "domain": {
                "type": "string",
                "description": "Skill domain (e.g. 'communications', 'memory', 'meta')",
            },
            "content": {
                "type": "string",
                "description": "Full SKILL.md content including frontmatter",
            },
        },
        "required": ["skill_id", "domain", "content"],
    },
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _make_load_skill_handler(memory_store, skills_dir: str):
    """Return a load_skill handler."""

    def load_skill_handler(tool_input: dict) -> str:
        skill_id: str = tool_input["skill_id"]
        skill = memory_store.get_skill(skill_id)
        if skill is None:
            return f"ERROR: Skill '{skill_id}' not found. Use list_skills to see available skills."

        file_path = Path(skill["file_path"])
        if not file_path.exists():
            # Try relative to skills_dir
            alt_path = Path(skills_dir) / skill_id / "SKILL.md"
            if alt_path.exists():
                file_path = alt_path
            else:
                return f"ERROR: Skill file not found: {file_path}"

        content = file_path.read_text(encoding="utf-8")
        memory_store.touch_skill(skill_id)
        return content

    return load_skill_handler


def _make_list_skills_handler(memory_store):
    """Return a list_skills handler."""

    def list_skills_handler(tool_input: dict) -> str:
        skills = memory_store.list_skills()
        if not skills:
            return "No skills registered."

        lines: list[str] = []
        for s in skills:
            lines.append(
                f"- {s['skill_id']} (domain: {s['domain']}, "
                f"uses: {s['usage_count']}, "
                f"effectiveness: {s['effectiveness']})"
            )
        return "\n".join(lines)

    return list_skills_handler


def _make_create_skill_handler(memory_store, skills_dir: str):
    """Return a create_skill handler."""

    def create_skill_handler(tool_input: dict) -> str:
        skill_id: str = tool_input["skill_id"]
        domain: str = tool_input["domain"]
        content: str = tool_input["content"]

        # Create directory and write file
        skill_dir = Path(skills_dir) / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(content, encoding="utf-8")

        # Register in memory store
        memory_store.register_skill(
            skill_id=skill_id,
            name=skill_id,
            domain=domain,
            file_path=str(skill_file),
        )

        return f"Created skill '{skill_id}' at {skill_file}"

    return create_skill_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_skill_tools(
    registry: ToolRegistry,
    memory_store,
    skills_dir: str,
) -> None:
    """Register load_skill, list_skills, create_skill tools."""
    registry.register(
        "load_skill",
        _LOAD_SKILL_DEFINITION,
        _make_load_skill_handler(memory_store, skills_dir),
        read_only=True,
    )
    registry.register(
        "list_skills",
        _LIST_SKILLS_DEFINITION,
        _make_list_skills_handler(memory_store),
        read_only=True,
    )
    registry.register(
        "create_skill",
        _CREATE_SKILL_DEFINITION,
        _make_create_skill_handler(memory_store, skills_dir),
        read_only=False,
    )
