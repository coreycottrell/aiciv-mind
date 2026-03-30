"""
aiciv_mind.manifest — YAML manifest loader with Pydantic v2 validation.

A manifest defines a mind's identity, model configuration, tools, auth,
memory backend, and sub-mind references. It is the single source of truth
for everything a mind needs to know about itself at startup.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator, model_validator


class ToolConfig(BaseModel):
    """Configuration for a single tool available to the mind."""

    name: str
    enabled: bool = True
    constraints: list[str] = []


class ModelConfig(BaseModel):
    """LLM model configuration."""

    preferred: str = "claude-sonnet-4-6"
    temperature: float = 0.7
    max_tokens: int = 4096


class AuthConfig(BaseModel):
    """AgentAuth identity configuration."""

    civ_id: str
    keypair_path: str  # Resolved to absolute by MindManifest.from_yaml


class MemoryConfig(BaseModel):
    """Memory backend configuration."""

    backend: str = "sqlite_fts5"
    db_path: str  # Resolved to absolute by MindManifest.from_yaml
    markdown_mirror: bool = True
    markdown_root: str | None = None
    auto_search_before_task: bool = True
    max_context_memories: int = 10


class SubMindRef(BaseModel):
    """Reference to a sub-mind that this mind can spawn."""

    mind_id: str
    manifest_path: str  # Resolved to absolute by MindManifest.from_yaml
    auto_spawn: bool = False


class MindManifest(BaseModel):
    """
    Complete manifest for an aiciv-mind instance.

    Loaded from YAML. All relative paths are resolved relative to the
    directory containing the manifest file.
    """

    schema_version: str = "1.0"
    mind_id: str
    display_name: str
    role: str
    system_prompt: str | None = None
    system_prompt_path: str | None = None
    model: ModelConfig = ModelConfig()
    tools: list[ToolConfig] = []
    auth: AuthConfig
    memory: MemoryConfig
    sub_minds: list[SubMindRef] = []

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MindManifest":
        """
        Load a MindManifest from a YAML file.

        Steps:
        1. Read and parse the YAML file.
        2. Expand environment variables in all string values (recursively).
        3. Resolve relative paths to absolute, anchored at the manifest's
           parent directory.
        4. Validate with Pydantic and return the instance.
        """
        manifest_path = Path(path).resolve()
        manifest_dir = manifest_path.parent

        with open(manifest_path) as f:
            raw = yaml.safe_load(f)

        if raw is None:
            raw = {}

        # Expand env vars throughout the entire dict tree.
        raw = _expand_env_vars(raw)

        # Resolve relative paths anchored at the manifest directory.
        _resolve_paths(raw, manifest_dir)

        return cls.model_validate(raw)

    def resolved_system_prompt(self) -> str:
        """
        Return the system prompt text.

        Priority:
        1. system_prompt_path (reads file contents)
        2. system_prompt (inline string)
        3. Minimal default
        """
        if self.system_prompt_path:
            return Path(self.system_prompt_path).read_text(encoding="utf-8")
        if self.system_prompt:
            return self.system_prompt
        return "You are an AI agent."

    def enabled_tool_names(self) -> list[str]:
        """Return names of all enabled tools."""
        return [t.name for t in self.tools if t.enabled]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand environment variables in all string values."""
    if isinstance(obj, str):
        return os.path.expandvars(obj)
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


def _resolve_paths(raw: dict, base_dir: Path) -> None:
    """
    Mutate *raw* in place, resolving relative paths to absolute.

    Paths resolved:
    - auth.keypair_path
    - system_prompt_path (top-level)
    - memory.db_path
    - sub_minds[*].manifest_path
    """

    def _abs(p: str) -> str:
        """Return absolute path; if already absolute, return as-is."""
        if not p:
            return p
        candidate = Path(p)
        if candidate.is_absolute():
            return p
        return str((base_dir / candidate).resolve())

    # system_prompt_path
    if "system_prompt_path" in raw and raw["system_prompt_path"]:
        raw["system_prompt_path"] = _abs(raw["system_prompt_path"])

    # auth.keypair_path
    auth = raw.get("auth", {})
    if isinstance(auth, dict) and "keypair_path" in auth and auth["keypair_path"]:
        auth["keypair_path"] = _abs(auth["keypair_path"])

    # memory.db_path
    memory = raw.get("memory", {})
    if isinstance(memory, dict) and "db_path" in memory and memory["db_path"]:
        memory["db_path"] = _abs(memory["db_path"])

    # sub_minds[*].manifest_path
    for sub in raw.get("sub_minds", []):
        if isinstance(sub, dict) and "manifest_path" in sub and sub["manifest_path"]:
            sub["manifest_path"] = _abs(sub["manifest_path"])
