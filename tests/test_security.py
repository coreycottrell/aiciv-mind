"""Tests for aiciv_mind.security — environment credential scrubbing."""

import pytest
from aiciv_mind.security import scrub_env, scrub_env_for_submind, _matches_credential_pattern


class TestCredentialPatternMatching:
    """Test that credential patterns correctly identify sensitive vars."""

    def test_api_key_patterns(self):
        assert _matches_credential_pattern("OPENAI_API_KEY")
        assert _matches_credential_pattern("ANTHROPIC_API_KEY")
        assert _matches_credential_pattern("GOOGLE_API_KEY")
        assert _matches_credential_pattern("GEMINI_API_KEY")
        assert _matches_credential_pattern("OLLAMA_API_KEY")
        assert _matches_credential_pattern("SOME_RANDOM_KEY")

    def test_secret_token_patterns(self):
        assert _matches_credential_pattern("AWS_SECRET_ACCESS_KEY")
        assert _matches_credential_pattern("GITHUB_TOKEN")
        assert _matches_credential_pattern("STRIPE_SECRET_KEY")
        assert _matches_credential_pattern("DATABASE_PASSWORD")

    def test_prefix_patterns(self):
        assert _matches_credential_pattern("ANTHROPIC_ANYTHING")
        assert _matches_credential_pattern("OPENAI_ANYTHING")
        assert _matches_credential_pattern("AWS_ANYTHING")
        assert _matches_credential_pattern("LITELLM_ANYTHING")

    def test_safe_vars_not_matched(self):
        assert not _matches_credential_pattern("PATH")
        assert not _matches_credential_pattern("HOME")
        assert not _matches_credential_pattern("USER")
        assert not _matches_credential_pattern("PYTHONPATH")
        assert not _matches_credential_pattern("TERM")
        assert not _matches_credential_pattern("MY_APP_NAME")
        assert not _matches_credential_pattern("MIND_ROOT")

    def test_case_insensitive(self):
        assert _matches_credential_pattern("openai_api_key")
        assert _matches_credential_pattern("Anthropic_Key")


class TestScrubEnv:
    """Test the scrub_env function."""

    def test_strips_api_keys(self):
        env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "OPENAI_API_KEY": "sk-secret",
            "ANTHROPIC_API_KEY": "sk-ant-secret",
            "MY_APP": "value",
        }
        result = scrub_env(env)
        assert "PATH" in result
        assert "HOME" in result
        assert "MY_APP" in result
        assert "OPENAI_API_KEY" not in result
        assert "ANTHROPIC_API_KEY" not in result

    def test_preserves_safe_vars(self):
        env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "PYTHONPATH": "/some/path",
            "VIRTUAL_ENV": "/venv",
            "LANG": "en_US.UTF-8",
            "TERM": "xterm-256color",
        }
        result = scrub_env(env)
        for key in env:
            assert key in result

    def test_preserve_override(self):
        """Extra preserve list should keep vars even if they match patterns."""
        env = {
            "PATH": "/usr/bin",
            "SPECIAL_KEY": "keep-me",
        }
        # Without preserve, SPECIAL_KEY would be stripped (matches *_KEY)
        result_without = scrub_env(env)
        assert "SPECIAL_KEY" not in result_without

        # With preserve, it's kept
        result_with = scrub_env(env, preserve=["SPECIAL_KEY"])
        assert "SPECIAL_KEY" in result_with

    def test_extra_strip(self):
        """Extra strip list removes vars even if they don't match patterns."""
        env = {
            "PATH": "/usr/bin",
            "MY_CUSTOM_VAR": "strip-me",
        }
        result = scrub_env(env, extra_strip=["MY_CUSTOM_VAR"])
        assert "MY_CUSTOM_VAR" not in result

    def test_uses_os_environ_by_default(self):
        """When base_env is None, should use os.environ."""
        result = scrub_env()
        assert "PATH" in result  # PATH should always exist

    def test_litellm_vars_stripped(self):
        env = {
            "PATH": "/usr/bin",
            "LITELLM_MASTER_KEY": "secret",
            "LITELLM_API_KEY": "also-secret",
        }
        result = scrub_env(env)
        assert "LITELLM_MASTER_KEY" not in result
        assert "LITELLM_API_KEY" not in result

    def test_pgpassword_stripped(self):
        env = {"PATH": "/usr/bin", "PGPASSWORD": "dbpass"}
        result = scrub_env(env)
        assert "PGPASSWORD" not in result

    def test_elevenlabs_stripped(self):
        env = {"PATH": "/usr/bin", "ELEVENLABS_API_KEY": "secret"}
        result = scrub_env(env)
        assert "ELEVENLABS_API_KEY" not in result


class TestScrubEnvForSubmind:
    """Test the sub-mind specific scrubbing."""

    def test_preserves_mind_api_key(self):
        env = {
            "PATH": "/usr/bin",
            "MIND_API_KEY": "sk-aiciv-dev",
            "OPENAI_API_KEY": "sk-secret",
        }
        result = scrub_env_for_submind(env)
        assert "MIND_API_KEY" in result
        assert "OPENAI_API_KEY" not in result

    def test_injects_mind_api_key(self):
        env = {"PATH": "/usr/bin"}
        result = scrub_env_for_submind(env, mind_api_key="sk-injected")
        assert result["MIND_API_KEY"] == "sk-injected"

    def test_overrides_existing_mind_api_key(self):
        env = {"PATH": "/usr/bin", "MIND_API_KEY": "old"}
        result = scrub_env_for_submind(env, mind_api_key="new")
        assert result["MIND_API_KEY"] == "new"

    def test_strips_all_credential_patterns(self):
        env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "MIND_API_KEY": "keep",
            "ANTHROPIC_API_KEY": "strip",
            "OPENAI_API_KEY": "strip",
            "AWS_SECRET_ACCESS_KEY": "strip",
            "STRIPE_SECRET_KEY": "strip",
            "NETLIFY_AUTH_TOKEN": "strip",
            "PGPASSWORD": "strip",
            "MY_APP_NAME": "keep",
        }
        result = scrub_env_for_submind(env)
        assert result["MIND_API_KEY"] == "keep"
        assert result["PATH"] == "/usr/bin"
        assert result["MY_APP_NAME"] == "keep"
        assert "ANTHROPIC_API_KEY" not in result
        assert "OPENAI_API_KEY" not in result
        assert "AWS_SECRET_ACCESS_KEY" not in result
        assert "STRIPE_SECRET_KEY" not in result
        assert "NETLIFY_AUTH_TOKEN" not in result
        assert "PGPASSWORD" not in result
