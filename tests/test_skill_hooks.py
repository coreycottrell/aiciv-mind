"""
Tests for skill-defined hooks — skills that register their own governance rules.
"""

from __future__ import annotations

import pytest

from aiciv_mind.tools.hooks import HookRunner
from aiciv_mind.tools.skill_tools import _parse_skill_hooks


# ---------------------------------------------------------------------------
# _parse_skill_hooks
# ---------------------------------------------------------------------------


class TestParseSkillHooks:
    def test_extracts_hooks_from_frontmatter(self):
        content = """---
skill_id: deployment-review
hooks:
  blocked_tools:
    - git_push
    - netlify_deploy
---

# Deployment Review Skill
Review all deployments carefully."""

        hooks = _parse_skill_hooks(content)
        assert hooks is not None
        assert hooks["blocked_tools"] == ["git_push", "netlify_deploy"]

    def test_returns_none_when_no_frontmatter(self):
        content = "# Just a regular markdown file\nNo frontmatter here."
        assert _parse_skill_hooks(content) is None

    def test_returns_none_when_no_hooks_key(self):
        content = """---
skill_id: basic-skill
domain: meta
---

No hooks defined."""
        assert _parse_skill_hooks(content) is None

    def test_returns_none_when_hooks_is_not_dict(self):
        content = """---
hooks: just-a-string
---

Bad format."""
        assert _parse_skill_hooks(content) is None

    def test_extracts_pre_tool_use_rules(self):
        content = """---
hooks:
  pre_tool_use:
    - tool: bash
      action: warn
      reason: Careful with bash in this mode
---

Content."""
        hooks = _parse_skill_hooks(content)
        assert hooks is not None
        assert len(hooks["pre_tool_use"]) == 1
        assert hooks["pre_tool_use"][0]["tool"] == "bash"
        assert hooks["pre_tool_use"][0]["action"] == "warn"

    def test_handles_malformed_yaml(self):
        content = """---
skill_id: broken
hooks:
  - this: [is: broken yaml
---

Content."""
        assert _parse_skill_hooks(content) is None

    def test_handles_missing_end_delimiter(self):
        content = """---
skill_id: no-end
hooks:
  blocked_tools: [bash]
"""
        assert _parse_skill_hooks(content) is None


# ---------------------------------------------------------------------------
# HookRunner.install_skill_hooks / uninstall_skill_hooks
# ---------------------------------------------------------------------------


class TestInstallSkillHooks:
    def test_install_blocks_tools(self):
        hooks = HookRunner()
        hooks.install_skill_hooks("deploy-review", {
            "blocked_tools": ["git_push", "netlify_deploy"],
        })
        assert "git_push" in hooks.blocked_tools
        assert "netlify_deploy" in hooks.blocked_tools

    def test_install_multiple_skills(self):
        hooks = HookRunner()
        hooks.install_skill_hooks("skill-a", {"blocked_tools": ["git_push"]})
        hooks.install_skill_hooks("skill-b", {"blocked_tools": ["netlify_deploy"]})
        assert "git_push" in hooks.blocked_tools
        assert "netlify_deploy" in hooks.blocked_tools

    def test_uninstall_removes_blocked_tools(self):
        hooks = HookRunner()
        hooks.install_skill_hooks("deploy-review", {
            "blocked_tools": ["git_push"],
        })
        assert "git_push" in hooks.blocked_tools
        hooks.uninstall_skill_hooks("deploy-review")
        assert "git_push" not in hooks.blocked_tools

    def test_uninstall_preserves_other_skill_blocks(self):
        """If two skills block the same tool, uninstalling one doesn't unblock it."""
        hooks = HookRunner()
        hooks.install_skill_hooks("skill-a", {"blocked_tools": ["git_push"]})
        hooks.install_skill_hooks("skill-b", {"blocked_tools": ["git_push"]})
        hooks.uninstall_skill_hooks("skill-a")
        # skill-b still blocks git_push
        assert "git_push" in hooks.blocked_tools

    def test_uninstall_nonexistent_skill_is_noop(self):
        hooks = HookRunner()
        hooks.uninstall_skill_hooks("nonexistent")  # Should not raise

    def test_active_skill_hooks_property(self):
        hooks = HookRunner()
        hooks.install_skill_hooks("skill-a", {"blocked_tools": ["bash"]})
        active = hooks.active_skill_hooks
        assert "skill-a" in active
        assert active["skill-a"]["blocked_tools"] == ["bash"]

    def test_active_skill_hooks_empty_by_default(self):
        hooks = HookRunner()
        assert hooks.active_skill_hooks == {}

    def test_install_with_warn_rules(self):
        hooks = HookRunner()
        hooks.install_skill_hooks("careful-skill", {
            "pre_tool_use": [
                {"tool": "bash", "action": "warn", "reason": "Be careful!"},
            ],
        })
        assert hasattr(hooks, "_skill_warn_rules")
        assert "bash" in hooks._skill_warn_rules
        assert hooks._skill_warn_rules["bash"][0]["reason"] == "Be careful!"

    def test_uninstall_removes_warn_rules(self):
        hooks = HookRunner()
        hooks.install_skill_hooks("careful-skill", {
            "pre_tool_use": [
                {"tool": "bash", "action": "warn", "reason": "Be careful!"},
            ],
        })
        hooks.uninstall_skill_hooks("careful-skill")
        assert "bash" not in hooks._skill_warn_rules

    def test_install_empty_config(self):
        hooks = HookRunner()
        hooks.install_skill_hooks("empty-skill", {})
        assert "empty-skill" in hooks.active_skill_hooks

    def test_blocked_tool_denies_execution(self):
        """Skill-blocked tools should be denied by pre_tool_use."""
        hooks = HookRunner()
        hooks.install_skill_hooks("deploy-lock", {
            "blocked_tools": ["git_push"],
        })
        result = hooks.pre_tool_use("git_push", {"branch": "main"})
        assert not result.allowed
        assert "blocked" in result.message.lower()

    def test_unblocked_tool_allowed_after_uninstall(self):
        hooks = HookRunner()
        hooks.install_skill_hooks("deploy-lock", {
            "blocked_tools": ["git_push"],
        })
        hooks.uninstall_skill_hooks("deploy-lock")
        result = hooks.pre_tool_use("git_push", {"branch": "main"})
        assert result.allowed

    def test_base_blocked_tools_preserved(self):
        """Skill uninstall should not remove tools blocked by the base config."""
        hooks = HookRunner(blocked_tools=["git_push"])
        hooks.install_skill_hooks("extra-block", {
            "blocked_tools": ["git_push", "netlify_deploy"],
        })
        hooks.uninstall_skill_hooks("extra-block")
        # git_push was in both base AND skill — base should keep it blocked
        # (but our implementation only tracks skill-level blocks, so base stays)
        # netlify_deploy was only in the skill — should be unblocked
        assert "netlify_deploy" not in hooks.blocked_tools
        # git_push is still in _blocked_tools because the base config set it
        assert "git_push" in hooks.blocked_tools


# ---------------------------------------------------------------------------
# Integration: load_skill installs hooks
# ---------------------------------------------------------------------------


class TestLoadSkillIntegration:
    """Test that load_skill actually installs hooks from SKILL.md frontmatter."""

    def test_load_skill_installs_hooks(self, tmp_path):
        """When a skill with hooks frontmatter is loaded, hooks should be installed."""
        from aiciv_mind.tools import ToolRegistry
        from aiciv_mind.tools.hooks import HookRunner

        # Create a mock memory store
        class MockMemoryStore:
            def get_skill(self, skill_id):
                return {
                    "skill_id": skill_id,
                    "file_path": str(tmp_path / skill_id / "SKILL.md"),
                }
            def touch_skill(self, skill_id):
                pass
            def list_skills(self):
                return []
            def register_skill(self, **kwargs):
                pass

        # Write a skill with hooks
        skill_dir = tmp_path / "deploy-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
skill_id: deploy-review
hooks:
  blocked_tools:
    - git_push
---

# Deploy Review
Review before pushing.""")

        # Set up registry with hooks
        registry = ToolRegistry()
        hook_runner = HookRunner()
        registry.set_hooks(hook_runner)

        from aiciv_mind.tools.skill_tools import register_skill_tools
        register_skill_tools(registry, MockMemoryStore(), str(tmp_path))

        # Load the skill
        import asyncio
        result = asyncio.run(
            registry.execute("load_skill", {"skill_id": "deploy-review"})
        )
        assert "Deploy Review" in result

        # Check that the hook was installed
        assert "git_push" in hook_runner.blocked_tools
        assert "deploy-review" in hook_runner.active_skill_hooks

    def test_load_skill_without_hooks_does_not_crash(self, tmp_path):
        """Skills without hooks frontmatter should load normally."""
        from aiciv_mind.tools import ToolRegistry

        class MockMemoryStore:
            def get_skill(self, skill_id):
                return {
                    "skill_id": skill_id,
                    "file_path": str(tmp_path / skill_id / "SKILL.md"),
                }
            def touch_skill(self, skill_id):
                pass
            def list_skills(self):
                return []
            def register_skill(self, **kwargs):
                pass

        skill_dir = tmp_path / "basic-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
skill_id: basic-skill
---

# Basic Skill
No hooks here.""")

        registry = ToolRegistry()
        from aiciv_mind.tools.skill_tools import register_skill_tools
        register_skill_tools(registry, MockMemoryStore(), str(tmp_path))

        import asyncio
        result = asyncio.run(
            registry.execute("load_skill", {"skill_id": "basic-skill"})
        )
        assert "Basic Skill" in result

    def test_unload_skill_removes_hooks(self, tmp_path):
        """unload_skill should remove hooks installed by load_skill."""
        from aiciv_mind.tools import ToolRegistry
        from aiciv_mind.tools.hooks import HookRunner

        class MockMemoryStore:
            def get_skill(self, skill_id):
                return {
                    "skill_id": skill_id,
                    "file_path": str(tmp_path / skill_id / "SKILL.md"),
                }
            def touch_skill(self, skill_id):
                pass
            def list_skills(self):
                return []
            def register_skill(self, **kwargs):
                pass

        skill_dir = tmp_path / "deploy-lock"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
skill_id: deploy-lock
hooks:
  blocked_tools:
    - netlify_deploy
---

# Deploy Lock""")

        registry = ToolRegistry()
        hook_runner = HookRunner()
        registry.set_hooks(hook_runner)

        from aiciv_mind.tools.skill_tools import register_skill_tools
        register_skill_tools(registry, MockMemoryStore(), str(tmp_path))

        import asyncio

        # Load skill — installs hooks
        asyncio.run(
            registry.execute("load_skill", {"skill_id": "deploy-lock"})
        )
        assert "netlify_deploy" in hook_runner.blocked_tools

        # Unload skill — removes hooks
        result = asyncio.run(
            registry.execute("unload_skill", {"skill_id": "deploy-lock"})
        )
        assert "unloaded" in result.lower() or "removed" in result.lower()
        assert "netlify_deploy" not in hook_runner.blocked_tools
