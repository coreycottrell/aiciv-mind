"""
aiciv_mind.skill_discovery — Progressive skill disclosure.

CC pattern: skills are hidden until the user touches relevant files.
When a file matching a skill's trigger pattern is read/written/edited,
the skill is surfaced as a suggestion.

Skills declare trigger paths in their SKILL.md frontmatter:
    ---
    skill_id: hub-engagement
    trigger_paths:
      - "hub/**"
      - "**/hub_tools.py"
    ---

Usage:
    discovery = SkillDiscovery()
    discovery.register("hub-engagement", ["hub/**", "**/hub_tools.py"])

    # On file access:
    suggestions = discovery.suggest(path="/src/hub/routers/feeds.py")
    # → [SkillSuggestion(skill_id="hub-engagement", matched_pattern="hub/**")]

    # The HookRunner integration:
    discovery.install_post_hook(hook_runner)
    # Now file tools auto-surface suggestions via the audit log
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SkillSuggestion:
    """A skill suggested by progressive disclosure."""
    skill_id: str
    matched_pattern: str
    triggered_by: str  # The file path that triggered the suggestion


class SkillDiscovery:
    """
    Progressive skill disclosure engine.

    Maintains a registry of skill_id → trigger patterns (globs).
    When a file path is checked, returns matching skill suggestions.
    """

    def __init__(self) -> None:
        # skill_id → list of glob patterns
        self._triggers: dict[str, list[str]] = {}
        # Track which skills have already been suggested this session
        # (avoid repeated suggestions for the same skill)
        self._suggested: set[str] = set()
        # Accumulated suggestions for retrieval
        self._pending: list[SkillSuggestion] = []

    def register(self, skill_id: str, trigger_paths: list[str]) -> None:
        """Register trigger patterns for a skill."""
        self._triggers[skill_id] = trigger_paths
        logger.debug(
            "[skill_discovery] Registered %s with %d trigger patterns",
            skill_id, len(trigger_paths),
        )

    def unregister(self, skill_id: str) -> None:
        """Remove trigger patterns for a skill."""
        self._triggers.pop(skill_id, None)
        self._suggested.discard(skill_id)

    def suggest(self, path: str) -> list[SkillSuggestion]:
        """
        Check a file path against all registered trigger patterns.
        Returns suggestions for matching skills that haven't been suggested yet.
        """
        suggestions: list[SkillSuggestion] = []
        normalized = path.replace("\\", "/")

        for skill_id, patterns in self._triggers.items():
            if skill_id in self._suggested:
                continue  # Already suggested this session

            for pattern in patterns:
                if _path_matches(normalized, pattern):
                    suggestion = SkillSuggestion(
                        skill_id=skill_id,
                        matched_pattern=pattern,
                        triggered_by=path,
                    )
                    suggestions.append(suggestion)
                    self._suggested.add(skill_id)
                    self._pending.append(suggestion)
                    logger.info(
                        "[skill_discovery] Suggesting skill '%s' (pattern '%s' matched '%s')",
                        skill_id, pattern, path,
                    )
                    break  # One match per skill is enough

        return suggestions

    def drain_pending(self) -> list[SkillSuggestion]:
        """Return and clear all pending suggestions."""
        pending = self._pending
        self._pending = []
        return pending

    def reset_session(self) -> None:
        """Reset suggested-this-session tracking (for new sessions)."""
        self._suggested.clear()
        self._pending.clear()

    @property
    def registered_skills(self) -> dict[str, list[str]]:
        """Return a copy of all registered skill → pattern mappings."""
        return dict(self._triggers)

    def load_from_skills_dir(self, skills_dir: str | Path, memory_store=None) -> int:
        """
        Scan a skills directory for SKILL.md files with trigger_paths frontmatter.
        Returns the number of skills registered.

        If memory_store is provided, also checks registered skills in the database.
        """
        import yaml

        count = 0
        skills_path = Path(skills_dir)

        if not skills_path.exists():
            return 0

        for skill_md in skills_path.rglob("SKILL.md"):
            try:
                content = skill_md.read_text(encoding="utf-8")
                trigger_paths = _extract_trigger_paths(content)
                if trigger_paths:
                    # Derive skill_id from directory name
                    skill_id = skill_md.parent.name
                    self.register(skill_id, trigger_paths)
                    count += 1
            except Exception as e:
                logger.debug("[skill_discovery] Failed to parse %s: %s", skill_md, e)

        logger.info("[skill_discovery] Loaded %d skills with trigger paths", count)
        return count

    def format_suggestions(self, suggestions: list[SkillSuggestion]) -> str:
        """Format suggestions as a human-readable string for context injection."""
        if not suggestions:
            return ""
        lines = ["[Skill Discovery] Relevant skills detected:"]
        for s in suggestions:
            lines.append(f"  - {s.skill_id} (triggered by: {s.triggered_by})")
        lines.append("Use load_skill to activate these skills.")
        return "\n".join(lines)


def _path_matches(path: str, pattern: str) -> bool:
    """
    Check if a path matches a glob-like pattern.

    Supports:
    - Simple globs: *.py, config.yaml
    - Recursive globs: hub/**, **/hub_tools.py
    - Path substring: hub/ anywhere in path
    """
    import re as _re

    # Normalize
    pattern = pattern.replace("\\", "/")

    # Convert glob pattern to regex for proper ** support
    if "**" in pattern or "*" in pattern or "?" in pattern or "[" in pattern:
        regex = _glob_to_regex(pattern)
        if _re.search(regex, path):
            return True

    # fnmatch for full path (handles simple *.ext patterns)
    if fnmatch.fnmatch(path, pattern):
        return True

    # Check against just the filename
    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    if fnmatch.fnmatch(filename, pattern):
        return True

    # Check if pattern appears as a path component substring
    if "/" in pattern and not any(c in pattern for c in "*?["):
        if pattern in path:
            return True

    return False


def _glob_to_regex(pattern: str) -> str:
    """Convert a glob pattern to a regex pattern with proper ** support."""
    import re as _re

    parts = pattern.split("**")
    regex_parts = []
    for i, part in enumerate(parts):
        # Convert single * to match within a path component (no /)
        # Convert ? to match any single char
        escaped = _re.escape(part)
        escaped = escaped.replace(r"\*", "[^/]*")
        escaped = escaped.replace(r"\?", "[^/]")
        regex_parts.append(escaped)

    # Join with .* (match anything including /)
    return ".*".join(regex_parts)


def _extract_trigger_paths(content: str) -> list[str] | None:
    """
    Extract trigger_paths from SKILL.md frontmatter.

    Returns None if no trigger_paths defined.
    """
    import yaml

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

    trigger_paths = frontmatter.get("trigger_paths")
    if isinstance(trigger_paths, list) and all(isinstance(p, str) for p in trigger_paths):
        return trigger_paths

    return None
