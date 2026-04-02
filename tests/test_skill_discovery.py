"""
Tests for aiciv_mind.skill_discovery — Progressive skill disclosure.
"""

from __future__ import annotations

import pytest

from aiciv_mind.skill_discovery import (
    SkillDiscovery,
    SkillSuggestion,
    _path_matches,
    _extract_trigger_paths,
)


# ---------------------------------------------------------------------------
# _path_matches
# ---------------------------------------------------------------------------


class TestPathMatches:
    def test_exact_filename_match(self):
        assert _path_matches("hub_tools.py", "hub_tools.py") is True

    def test_glob_extension_match(self):
        assert _path_matches("server.py", "*.py") is True
        assert _path_matches("server.ts", "*.py") is False

    def test_double_star_glob(self):
        assert _path_matches("src/hub/routers/feeds.py", "hub/**") is True

    def test_double_star_prefix(self):
        assert _path_matches("src/deep/hub_tools.py", "**/hub_tools.py") is True

    def test_path_substring(self):
        assert _path_matches("src/hub/routers/feeds.py", "hub/") is True

    def test_no_match(self):
        assert _path_matches("src/memory.py", "hub/**") is False

    def test_filename_extracted_from_path(self):
        assert _path_matches("/long/path/to/config.yaml", "*.yaml") is True

    def test_case_sensitive(self):
        # fnmatch is case-sensitive on Linux
        assert _path_matches("File.PY", "*.py") is False


# ---------------------------------------------------------------------------
# _extract_trigger_paths
# ---------------------------------------------------------------------------


class TestExtractTriggerPaths:
    def test_extracts_trigger_paths(self):
        content = """---
skill_id: hub-engagement
trigger_paths:
  - "hub/**"
  - "**/hub_tools.py"
---

# Hub Engagement"""
        result = _extract_trigger_paths(content)
        assert result == ["hub/**", "**/hub_tools.py"]

    def test_returns_none_when_no_frontmatter(self):
        assert _extract_trigger_paths("No frontmatter here") is None

    def test_returns_none_when_no_trigger_paths(self):
        content = """---
skill_id: basic
---

Content."""
        assert _extract_trigger_paths(content) is None

    def test_returns_none_when_trigger_paths_is_not_list(self):
        content = """---
trigger_paths: not-a-list
---

Content."""
        assert _extract_trigger_paths(content) is None

    def test_returns_none_when_list_has_non_strings(self):
        content = """---
trigger_paths:
  - 123
  - true
---

Content."""
        assert _extract_trigger_paths(content) is None

    def test_handles_malformed_yaml(self):
        content = """---
trigger_paths: [bad: yaml
---

Content."""
        assert _extract_trigger_paths(content) is None


# ---------------------------------------------------------------------------
# SkillDiscovery — registration and suggestion
# ---------------------------------------------------------------------------


class TestSkillDiscovery:
    def test_register_and_suggest(self):
        disc = SkillDiscovery()
        disc.register("hub-engagement", ["hub/**"])
        suggestions = disc.suggest("src/hub/routers/feeds.py")
        assert len(suggestions) == 1
        assert suggestions[0].skill_id == "hub-engagement"
        assert suggestions[0].matched_pattern == "hub/**"

    def test_no_match_returns_empty(self):
        disc = SkillDiscovery()
        disc.register("hub-engagement", ["hub/**"])
        suggestions = disc.suggest("src/memory.py")
        assert suggestions == []

    def test_multiple_skills_can_match(self):
        disc = SkillDiscovery()
        disc.register("hub-engagement", ["hub/**"])
        disc.register("python-style", ["*.py"])
        suggestions = disc.suggest("src/hub/server.py")
        skill_ids = {s.skill_id for s in suggestions}
        assert "hub-engagement" in skill_ids
        assert "python-style" in skill_ids

    def test_same_skill_suggested_only_once(self):
        """Progressive disclosure: once suggested, don't repeat."""
        disc = SkillDiscovery()
        disc.register("hub-engagement", ["hub/**"])
        s1 = disc.suggest("src/hub/server.py")
        s2 = disc.suggest("src/hub/models.py")
        assert len(s1) == 1
        assert len(s2) == 0  # Already suggested

    def test_reset_session_allows_re_suggestion(self):
        disc = SkillDiscovery()
        disc.register("hub-engagement", ["hub/**"])
        disc.suggest("src/hub/server.py")
        disc.reset_session()
        s2 = disc.suggest("src/hub/models.py")
        assert len(s2) == 1

    def test_unregister_removes_skill(self):
        disc = SkillDiscovery()
        disc.register("hub-engagement", ["hub/**"])
        disc.unregister("hub-engagement")
        suggestions = disc.suggest("src/hub/server.py")
        assert suggestions == []

    def test_registered_skills_property(self):
        disc = SkillDiscovery()
        disc.register("a", ["*.py"])
        disc.register("b", ["*.ts"])
        assert disc.registered_skills == {"a": ["*.py"], "b": ["*.ts"]}

    def test_drain_pending(self):
        disc = SkillDiscovery()
        disc.register("hub", ["hub/**"])
        disc.suggest("hub/server.py")
        pending = disc.drain_pending()
        assert len(pending) == 1
        # Drain should clear
        assert disc.drain_pending() == []

    def test_format_suggestions_empty(self):
        disc = SkillDiscovery()
        assert disc.format_suggestions([]) == ""

    def test_format_suggestions_non_empty(self):
        disc = SkillDiscovery()
        suggestions = [
            SkillSuggestion("hub-engagement", "hub/**", "hub/server.py"),
        ]
        result = disc.format_suggestions(suggestions)
        assert "hub-engagement" in result
        assert "Skill Discovery" in result
        assert "load_skill" in result


# ---------------------------------------------------------------------------
# SkillDiscovery — load_from_skills_dir
# ---------------------------------------------------------------------------


class TestLoadFromSkillsDir:
    def test_loads_skills_with_trigger_paths(self, tmp_path):
        # Create a skill with trigger_paths
        skill_dir = tmp_path / "hub-engagement"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
skill_id: hub-engagement
trigger_paths:
  - "hub/**"
  - "**/hub_tools.py"
---

# Hub Engagement Skill""")

        disc = SkillDiscovery()
        count = disc.load_from_skills_dir(str(tmp_path))
        assert count == 1
        assert "hub-engagement" in disc.registered_skills

    def test_skips_skills_without_trigger_paths(self, tmp_path):
        skill_dir = tmp_path / "basic-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
skill_id: basic-skill
---

No triggers.""")

        disc = SkillDiscovery()
        count = disc.load_from_skills_dir(str(tmp_path))
        assert count == 0

    def test_handles_nonexistent_dir(self, tmp_path):
        disc = SkillDiscovery()
        count = disc.load_from_skills_dir(str(tmp_path / "nonexistent"))
        assert count == 0

    def test_loads_multiple_skills(self, tmp_path):
        for name, patterns in [("a", ["*.py"]), ("b", ["*.ts"])]:
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"""---
skill_id: {name}
trigger_paths:
  - "{patterns[0]}"
---

Skill {name}.""")

        disc = SkillDiscovery()
        count = disc.load_from_skills_dir(str(tmp_path))
        assert count == 2

    def test_loaded_skills_actually_trigger(self, tmp_path):
        skill_dir = tmp_path / "deploy-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
skill_id: deploy-review
trigger_paths:
  - "**/deploy.py"
  - "Dockerfile"
---

# Deploy Review""")

        disc = SkillDiscovery()
        disc.load_from_skills_dir(str(tmp_path))
        suggestions = disc.suggest("infra/deploy.py")
        assert len(suggestions) == 1
        assert suggestions[0].skill_id == "deploy-review"
