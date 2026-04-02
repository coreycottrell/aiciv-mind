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

_UNLOAD_SKILL_DEFINITION: dict = {
    "name": "unload_skill",
    "description": (
        "Unload a skill, removing any hooks it installed. "
        "Use this to deactivate skill-defined governance rules."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": "The skill ID to unload (e.g. 'deployment-review')",
            },
        },
        "required": ["skill_id"],
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


def _parse_skill_hooks(content: str) -> dict | None:
    """
    Parse hooks configuration from SKILL.md frontmatter.

    Looks for a YAML frontmatter block delimited by --- lines, then extracts
    the 'hooks:' key. Returns None if no hooks defined.

    Supported frontmatter format:
        ---
        skill_id: deployment-review
        hooks:
          blocked_tools:
            - git_push
            - netlify_deploy
          pre_tool_use:
            - tool: bash
              action: warn
              reason: "Running bash in deployment review mode"
        ---
    """
    import yaml

    # Extract frontmatter
    if not content.startswith("---"):
        return None

    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return None

    frontmatter_text = content[3:end_idx].strip()
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except Exception:
        return None

    if not isinstance(frontmatter, dict):
        return None

    hooks = frontmatter.get("hooks")
    if not isinstance(hooks, dict):
        return None

    return hooks


def _make_load_skill_handler(memory_store, skills_dir: str, registry=None):
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

        # Install skill-defined hooks if the skill declares them
        if registry is not None:
            hooks_config = _parse_skill_hooks(content)
            if hooks_config is not None:
                hook_runner = registry.get_hooks()
                if hook_runner is not None:
                    hook_runner.install_skill_hooks(skill_id, hooks_config)

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


def _make_unload_skill_handler(registry=None):
    """Return an unload_skill handler."""

    def unload_skill_handler(tool_input: dict) -> str:
        skill_id: str = tool_input["skill_id"]

        if registry is not None:
            hook_runner = registry.get_hooks()
            if hook_runner is not None:
                hook_runner.uninstall_skill_hooks(skill_id)
                return f"Unloaded skill '{skill_id}' — hooks removed."

        return f"Skill '{skill_id}' unloaded (no hooks were active)."

    return unload_skill_handler


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
        _make_load_skill_handler(memory_store, skills_dir, registry=registry),
        read_only=True,
    )
    registry.register(
        "list_skills",
        _LIST_SKILLS_DEFINITION,
        _make_list_skills_handler(memory_store),
        read_only=True,
    )
    registry.register(
        "unload_skill",
        _UNLOAD_SKILL_DEFINITION,
        _make_unload_skill_handler(registry=registry),
        read_only=False,
    )
    registry.register(
        "create_skill",
        _CREATE_SKILL_DEFINITION,
        _make_create_skill_handler(memory_store, skills_dir),
        read_only=False,
    )
