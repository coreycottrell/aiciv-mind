"""
Tests for aiciv_mind.tools.sandbox_tools — Safe self-modification sandbox.

Covers: tool definitions, sandbox_create, sandbox_test, sandbox_promote,
sandbox_discard handlers, kill-switch enforcement, and registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_sandbox_tools.py -v
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.sandbox_tools import (
    _CREATE_DEFINITION,
    _TEST_DEFINITION,
    _PROMOTE_DEFINITION,
    _DISCARD_DEFINITION,
    _active_sandbox,
    _make_create_handler,
    _make_test_handler,
    _make_promote_handler,
    _make_discard_handler,
    register_sandbox_tools,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_active_sandbox():
    """Reset the module-level _active_sandbox state before each test."""
    _active_sandbox["path"] = None
    _active_sandbox["tests_passed"] = False
    yield
    # Clean up any sandbox directories created during tests
    if _active_sandbox["path"] and Path(_active_sandbox["path"]).exists():
        shutil.rmtree(_active_sandbox["path"], ignore_errors=True)
    _active_sandbox["path"] = None
    _active_sandbox["tests_passed"] = False


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_create_definition_has_required_keys():
    """sandbox_create definition must have name, description, input_schema."""
    assert _CREATE_DEFINITION["name"] == "sandbox_create"
    assert "description" in _CREATE_DEFINITION
    assert len(_CREATE_DEFINITION["description"]) > 10
    schema = _CREATE_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "properties" in schema


def test_promote_definition_has_required_keys():
    """sandbox_promote definition must have name, description, input_schema with required fields."""
    assert _PROMOTE_DEFINITION["name"] == "sandbox_promote"
    assert "description" in _PROMOTE_DEFINITION
    schema = _PROMOTE_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "description" in schema["properties"]
    assert "description" in schema["required"]


def test_all_definitions_have_name_description_schema():
    """All four sandbox tool definitions must have the standard keys."""
    for defn in [_CREATE_DEFINITION, _TEST_DEFINITION, _PROMOTE_DEFINITION, _DISCARD_DEFINITION]:
        assert "name" in defn
        assert "description" in defn
        assert "input_schema" in defn
        assert defn["input_schema"]["type"] == "object"


# ---------------------------------------------------------------------------
# sandbox_create handler tests
# ---------------------------------------------------------------------------


def test_create_handler_creates_sandbox(tmp_path):
    """sandbox_create should copy files into a sandbox directory."""
    with patch("aiciv_mind.tools.sandbox_tools._project_root", return_value=tmp_path):
        # Create minimal project structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "example.py").write_text("# code", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "main.py").write_text("# main", encoding="utf-8")

        handler = _make_create_handler()
        result = handler({})

    assert "Sandbox created at" in result
    assert _active_sandbox["path"] is not None
    assert _active_sandbox["tests_passed"] is False


def test_create_handler_rejects_duplicate():
    """sandbox_create should reject if a sandbox already exists."""
    _active_sandbox["path"] = "/tmp/fake-sandbox"
    handler = _make_create_handler()
    result = handler({})
    assert "ERROR" in result
    assert "Active sandbox already exists" in result


# ---------------------------------------------------------------------------
# sandbox_test handler tests
# ---------------------------------------------------------------------------


def test_test_handler_no_active_sandbox():
    """sandbox_test should return error when no sandbox exists."""
    handler = _make_test_handler()
    result = handler({})
    assert "ERROR" in result
    assert "No active sandbox" in result


def test_test_handler_missing_directory():
    """sandbox_test should error if sandbox directory was deleted."""
    _active_sandbox["path"] = "/tmp/nonexistent-sandbox-xyz"
    handler = _make_test_handler()
    result = handler({})
    assert "ERROR" in result
    assert "no longer exists" in result
    assert _active_sandbox["path"] is None


# ---------------------------------------------------------------------------
# sandbox_promote handler tests
# ---------------------------------------------------------------------------


def test_promote_handler_no_active_sandbox():
    """sandbox_promote should error when no sandbox exists."""
    handler = _make_promote_handler("/tmp/fake-manifest.yaml")
    result = handler({"description": "test"})
    assert "ERROR" in result
    assert "No active sandbox" in result


def test_promote_handler_tests_not_passed():
    """sandbox_promote should reject if tests haven't passed."""
    _active_sandbox["path"] = "/tmp/some-sandbox"
    _active_sandbox["tests_passed"] = False
    handler = _make_promote_handler("/tmp/fake-manifest.yaml")
    result = handler({"description": "test"})
    assert "ERROR" in result
    assert "Tests haven't passed" in result


def test_promote_handler_kill_switch_disabled(tmp_path):
    """sandbox_promote should reject when self_modification_enabled is false."""
    _active_sandbox["path"] = str(tmp_path)
    _active_sandbox["tests_passed"] = True

    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("self_modification_enabled: false\n", encoding="utf-8")

    handler = _make_promote_handler(str(manifest))
    result = handler({"description": "test change"})
    assert "ERROR" in result
    assert "self_modification_enabled is false" in result


def test_promote_handler_kill_switch_missing_manifest():
    """sandbox_promote should error when manifest can't be read."""
    _active_sandbox["path"] = "/tmp/some-sandbox"
    _active_sandbox["tests_passed"] = True
    handler = _make_promote_handler("/tmp/nonexistent-manifest.yaml")
    result = handler({"description": "test"})
    assert "ERROR" in result
    assert "Could not read manifest" in result


# ---------------------------------------------------------------------------
# sandbox_discard handler tests
# ---------------------------------------------------------------------------


def test_discard_handler_no_sandbox():
    """sandbox_discard with no active sandbox should return friendly message."""
    handler = _make_discard_handler()
    result = handler({})
    assert "No active sandbox to discard" in result


def test_discard_handler_cleans_up(tmp_path):
    """sandbox_discard should delete the sandbox directory and reset state."""
    sandbox_dir = tmp_path / "test-sandbox"
    sandbox_dir.mkdir()
    (sandbox_dir / "file.txt").write_text("data", encoding="utf-8")
    _active_sandbox["path"] = str(sandbox_dir)
    _active_sandbox["tests_passed"] = True

    handler = _make_discard_handler()
    result = handler({})

    assert "Sandbox discarded" in result
    assert _active_sandbox["path"] is None
    assert _active_sandbox["tests_passed"] is False


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_sandbox_tools_adds_all_four():
    """register_sandbox_tools should register all 4 sandbox tools."""
    registry = ToolRegistry()
    register_sandbox_tools(registry, "/tmp/manifest.yaml")
    names = registry.names()
    assert "sandbox_create" in names
    assert "sandbox_test" in names
    assert "sandbox_promote" in names
    assert "sandbox_discard" in names


def test_sandbox_tools_read_only_flags():
    """sandbox_test should be read-only; create, promote, discard should not."""
    registry = ToolRegistry()
    register_sandbox_tools(registry, "/tmp/manifest.yaml")
    assert registry.is_read_only("sandbox_test") is True
    assert registry.is_read_only("sandbox_create") is False
    assert registry.is_read_only("sandbox_promote") is False
    assert registry.is_read_only("sandbox_discard") is False
