"""Tests for aiciv_mind.manifest — YAML manifest loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from aiciv_mind.manifest import MindManifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_yaml(tmp_path: Path, data: dict) -> Path:
    """Write a dict as YAML to a temp file and return the path."""
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.dump(data))
    return p


MINIMAL_VALID = {
    "schema_version": "1.0",
    "mind_id": "test-mind",
    "display_name": "Test Mind",
    "role": "worker",
    "auth": {
        "civ_id": "acg",
        "keypair_path": "/tmp/test_key.json",
    },
    "memory": {
        "backend": "sqlite_fts5",
        "db_path": "/tmp/test_memory.db",
    },
}


# ---------------------------------------------------------------------------
# Test: full manifest round-trip
# ---------------------------------------------------------------------------


def test_load_full_manifest(tmp_path: Path) -> None:
    """Load a fully-specified manifest; verify all fields parse correctly."""
    prompt_file = tmp_path / "system_prompt.md"
    prompt_file.write_text("You are a test mind.")

    data = {
        "schema_version": "1.0",
        "mind_id": "primary",
        "display_name": "Primary Mind",
        "role": "conductor-of-conductors",
        "system_prompt_path": "system_prompt.md",
        "model": {
            "preferred": "openrouter/kimi-k2",
            "temperature": 0.5,
            "max_tokens": 8192,
        },
        "tools": [
            {"name": "bash", "enabled": True, "constraints": ["no rm -rf /"]},
            {"name": "disabled_tool", "enabled": False},
        ],
        "auth": {
            "civ_id": "acg",
            "keypair_path": "/absolute/path/key.json",
        },
        "memory": {
            "backend": "sqlite_fts5",
            "db_path": "/tmp/primary.db",
            "markdown_mirror": True,
            "auto_search_before_task": True,
            "max_context_memories": 15,
        },
        "sub_minds": [
            {
                "mind_id": "research-lead",
                "manifest_path": "manifests/research-lead.yaml",
                "auto_spawn": False,
            }
        ],
    }
    manifest_path = write_yaml(tmp_path, data)
    manifest = MindManifest.from_yaml(manifest_path)

    assert manifest.schema_version == "1.0"
    assert manifest.mind_id == "primary"
    assert manifest.display_name == "Primary Mind"
    assert manifest.role == "conductor-of-conductors"
    assert manifest.model.preferred == "openrouter/kimi-k2"
    assert manifest.model.temperature == 0.5
    assert manifest.model.max_tokens == 8192
    assert len(manifest.tools) == 2
    assert manifest.auth.civ_id == "acg"
    assert manifest.memory.max_context_memories == 15
    assert len(manifest.sub_minds) == 1
    assert manifest.sub_minds[0].mind_id == "research-lead"


# ---------------------------------------------------------------------------
# Test: minimal manifest
# ---------------------------------------------------------------------------


def test_minimal_manifest(tmp_path: Path) -> None:
    """A manifest with only required fields should succeed."""
    manifest_path = write_yaml(tmp_path, MINIMAL_VALID)
    manifest = MindManifest.from_yaml(manifest_path)

    assert manifest.mind_id == "test-mind"
    assert manifest.model.preferred == "ollama/qwen2.5-coder:14b"  # default
    assert manifest.tools == []
    assert manifest.sub_minds == []


# ---------------------------------------------------------------------------
# Test: missing required field
# ---------------------------------------------------------------------------


def test_missing_mind_id_raises(tmp_path: Path) -> None:
    """Omitting mind_id must raise a ValidationError."""
    data = {k: v for k, v in MINIMAL_VALID.items() if k != "mind_id"}
    manifest_path = write_yaml(tmp_path, data)

    with pytest.raises(ValidationError):
        MindManifest.from_yaml(manifest_path)


# ---------------------------------------------------------------------------
# Test: relative path resolution for system_prompt_path
# ---------------------------------------------------------------------------


def test_system_prompt_path_resolved_relative(tmp_path: Path) -> None:
    """system_prompt_path given as relative path resolves to absolute."""
    prompt_file = tmp_path / "prompts" / "primary.md"
    prompt_file.parent.mkdir()
    prompt_file.write_text("Hello from primary.")

    data = {**MINIMAL_VALID, "system_prompt_path": "prompts/primary.md"}
    manifest_path = write_yaml(tmp_path, data)
    manifest = MindManifest.from_yaml(manifest_path)

    assert Path(manifest.system_prompt_path).is_absolute()
    assert manifest.system_prompt_path == str(prompt_file)


# ---------------------------------------------------------------------------
# Test: enabled_tool_names
# ---------------------------------------------------------------------------


def test_enabled_tool_names(tmp_path: Path) -> None:
    """enabled_tool_names() only returns tools where enabled=True."""
    data = {
        **MINIMAL_VALID,
        "tools": [
            {"name": "bash", "enabled": True},
            {"name": "read_file", "enabled": True},
            {"name": "dangerous_tool", "enabled": False},
        ],
    }
    manifest_path = write_yaml(tmp_path, data)
    manifest = MindManifest.from_yaml(manifest_path)

    names = manifest.enabled_tool_names()
    assert "bash" in names
    assert "read_file" in names
    assert "dangerous_tool" not in names


# ---------------------------------------------------------------------------
# Test: resolved_system_prompt from file
# ---------------------------------------------------------------------------


def test_resolved_system_prompt_from_file(tmp_path: Path) -> None:
    """resolved_system_prompt() returns file content when path is set."""
    prompt_file = tmp_path / "prompt.md"
    expected = "I am the primary mind. I conduct orchestras."
    prompt_file.write_text(expected)

    data = {**MINIMAL_VALID, "system_prompt_path": "prompt.md"}
    manifest_path = write_yaml(tmp_path, data)
    manifest = MindManifest.from_yaml(manifest_path)

    assert manifest.resolved_system_prompt() == expected


def test_resolved_system_prompt_inline(tmp_path: Path) -> None:
    """resolved_system_prompt() returns inline string when no path is set."""
    data = {**MINIMAL_VALID, "system_prompt": "Inline prompt text."}
    manifest_path = write_yaml(tmp_path, data)
    manifest = MindManifest.from_yaml(manifest_path)

    assert manifest.resolved_system_prompt() == "Inline prompt text."


def test_resolved_system_prompt_default(tmp_path: Path) -> None:
    """resolved_system_prompt() returns the minimal default when nothing is set."""
    manifest_path = write_yaml(tmp_path, MINIMAL_VALID)
    manifest = MindManifest.from_yaml(manifest_path)

    assert manifest.resolved_system_prompt() == "You are an AI agent."


# ---------------------------------------------------------------------------
# Test: context mode (P2-11)
# ---------------------------------------------------------------------------


def test_context_mode_defaults_to_full(tmp_path: Path) -> None:
    """Default context mode is 'full'."""
    manifest_path = write_yaml(tmp_path, MINIMAL_VALID)
    manifest = MindManifest.from_yaml(manifest_path)
    assert manifest.context.mode == "full"


def test_context_mode_minimal(tmp_path: Path) -> None:
    """Manifest can specify minimal context mode."""
    data = {**MINIMAL_VALID, "context": {"mode": "minimal"}}
    manifest_path = write_yaml(tmp_path, data)
    manifest = MindManifest.from_yaml(manifest_path)
    assert manifest.context.mode == "minimal"
