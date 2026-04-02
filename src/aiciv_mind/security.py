"""
aiciv_mind.security — Environment and credential security utilities.

Core principle: subprocesses spawned by Root should not inherit credentials
they don't need. A bash command checking disk usage should not have access
to API keys. A sub-mind should only receive the credentials it needs.
"""

from __future__ import annotations

import os
import re
from typing import Sequence

# Patterns that match credential-bearing environment variable names.
# These are stripped from subprocess environments by default.
CREDENTIAL_PATTERNS: list[str] = [
    r".*_KEY$",
    r".*_SECRET$",
    r".*_TOKEN$",
    r".*_PASSWORD$",
    r".*_CREDENTIAL$",
    r"^ANTHROPIC_.*",
    r"^OPENAI_.*",
    r"^GOOGLE_.*",
    r"^AWS_.*",
    r"^LITELLM_.*",
    r"^GEMINI_.*",
    r"^OLLAMA_API_KEY$",
    r"^AGENTMAIL_.*KEY.*",
    r"^AGENTAUTH_.*KEY.*",
    r"^DATABASE_URL$",
    r"^PGPASSWORD$",
    r"^REDIS_PASSWORD$",
    r"^STRIPE_.*",
    r"^ELEVENLABS_.*",
    r"^NETLIFY_AUTH_TOKEN$",
]

# Variables that are always preserved even if they match a credential pattern.
ALWAYS_PRESERVE: set[str] = {
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "LANG",
    "LC_ALL",
    "TERM",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "XDG_RUNTIME_DIR",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "DBUS_SESSION_BUS_ADDRESS",
    "SSH_AUTH_SOCK",
    "TMPDIR",
    "TMP",
    "TEMP",
}

# Compiled patterns for efficiency (compiled once at import time).
_COMPILED_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in CREDENTIAL_PATTERNS
]


def _matches_credential_pattern(name: str) -> bool:
    """Return True if the env var name matches any credential pattern."""
    return any(p.match(name) for p in _COMPILED_PATTERNS)


def scrub_env(
    base_env: dict[str, str] | None = None,
    *,
    preserve: Sequence[str] = (),
    extra_strip: Sequence[str] = (),
) -> dict[str, str]:
    """
    Return a copy of the environment with credential variables removed.

    Args:
        base_env: Source environment dict. Defaults to os.environ.
        preserve: Additional variable names to keep even if they match patterns.
        extra_strip: Additional variable names to always strip.

    Returns:
        A new dict with credentials removed but safe vars preserved.
    """
    if base_env is None:
        base_env = dict(os.environ)

    preserve_set = ALWAYS_PRESERVE | set(preserve)
    extra_strip_set = set(extra_strip)

    result: dict[str, str] = {}
    for name, value in base_env.items():
        # Always strip explicitly-listed vars
        if name in extra_strip_set:
            continue
        # Always preserve explicitly-listed vars
        if name in preserve_set:
            result[name] = value
            continue
        # Strip if matches credential pattern
        if _matches_credential_pattern(name):
            continue
        # Keep everything else
        result[name] = value

    return result


def scrub_env_for_submind(
    base_env: dict[str, str] | None = None,
    *,
    mind_api_key: str | None = None,
) -> dict[str, str]:
    """
    Return a scrubbed environment suitable for a sub-mind process.

    Sub-minds need MIND_API_KEY to talk to the LLM proxy, but should not
    inherit other credentials (Anthropic keys, email keys, etc.).

    Args:
        base_env: Source environment dict. Defaults to os.environ.
        mind_api_key: If provided, set MIND_API_KEY in the result.

    Returns:
        A new dict with only safe vars + MIND_API_KEY.
    """
    env = scrub_env(base_env, preserve=("MIND_API_KEY",))

    if mind_api_key is not None:
        env["MIND_API_KEY"] = mind_api_key

    return env
