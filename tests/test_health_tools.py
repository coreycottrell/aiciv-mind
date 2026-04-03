"""
Tests for aiciv_mind.tools.health_tools — System health monitoring.

Covers: tool definition (system_health), handler with mocked subprocess/httpx,
memory DB reporting, git status, disk usage, verbose flag, and registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_health_tools.py -v
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.health_tools import (
    _HEALTH_DEFINITION,
    _make_health_handler,
    register_health_tools,
)


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_health_definition_has_required_keys():
    """system_health definition must have name, description, and input_schema."""
    assert _HEALTH_DEFINITION["name"] == "system_health"
    assert "description" in _HEALTH_DEFINITION
    assert len(_HEALTH_DEFINITION["description"]) > 20
    schema = _HEALTH_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "verbose" in schema["properties"]


def test_health_definition_verbose_property():
    """verbose property should be boolean type."""
    prop = _HEALTH_DEFINITION["input_schema"]["properties"]["verbose"]
    assert prop["type"] == "boolean"


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_health_tools(registry):
    """system_health should appear in registry after registration."""
    register_health_tools(registry)
    assert "system_health" in registry.names()


def test_system_health_is_read_only(registry):
    """system_health should be marked read_only."""
    register_health_tools(registry)
    assert registry.is_read_only("system_health") is True


def test_register_health_tools_with_all_params(registry):
    """Registration should succeed with both memory_store and mind_root."""
    mock_store = MagicMock()
    register_health_tools(registry, memory_store=mock_store, mind_root="/tmp/test")
    assert "system_health" in registry.names()


# ---------------------------------------------------------------------------
# Handler tests — httpx and subprocess are imported inside the handler body,
# so we patch them at the package level (httpx.get, subprocess.run).
# ---------------------------------------------------------------------------


@patch("httpx.get")
@patch("subprocess.run")
def test_handler_basic_report(mock_subproc_run, mock_httpx_get):
    """Handler should return a System Health Report header."""
    mock_subproc_run.return_value = MagicMock(stdout="", returncode=0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_httpx_get.return_value = mock_resp

    handler = _make_health_handler()
    result = handler({})

    assert "System Health Report" in result


@patch("httpx.get")
@patch("subprocess.run")
def test_handler_with_memory_store(mock_subproc_run, mock_httpx_get):
    """Handler should report memory count when memory_store is provided."""
    mock_subproc_run.return_value = MagicMock(stdout="", returncode=0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_httpx_get.return_value = mock_resp

    mock_store = MagicMock()
    mock_store._db_path = ":memory:"
    # memories table
    mock_store._conn.execute.return_value.fetchone.return_value = (150,)

    handler = _make_health_handler(memory_store=mock_store)
    result = handler({})

    assert "Total memories" in result
    assert "150" in result


@patch("httpx.get")
@patch("subprocess.run")
def test_handler_reports_running_processes(mock_subproc_run, mock_httpx_get):
    """Handler should report aiciv-related running processes."""
    ps_output = (
        "corey  1234  0.0  0.1 12345 6789 ?  S  10:00 0:00 python3 aiciv_mind daemon\n"
        "corey  5678  0.0  0.2 12345 6789 ?  S  10:01 0:00 python3 groupchat_daemon.py\n"
        "corey  9999  0.0  0.3 12345 6789 ?  S  10:02 0:00 python3 unrelated_process\n"
    )
    mock_subproc_run.return_value = MagicMock(stdout=ps_output, returncode=0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_httpx_get.return_value = mock_resp

    handler = _make_health_handler()
    result = handler({})

    assert "Running processes" in result


@patch("httpx.get")
@patch("subprocess.run")
def test_handler_reports_hub_status(mock_subproc_run, mock_httpx_get):
    """Handler should report Hub status based on HTTP response."""
    mock_subproc_run.return_value = MagicMock(stdout="", returncode=0)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_httpx_get.return_value = mock_resp

    handler = _make_health_handler()
    result = handler({})

    assert "Hub" in result
    assert "UP" in result


@patch("httpx.get")
@patch("subprocess.run")
def test_handler_hub_down(mock_subproc_run, mock_httpx_get):
    """Handler should report Hub DOWN when httpx raises an exception."""
    mock_subproc_run.return_value = MagicMock(stdout="", returncode=0)
    mock_httpx_get.side_effect = ConnectionError("timeout")

    handler = _make_health_handler()
    result = handler({})

    assert "Hub" in result
    assert "DOWN" in result or "unreachable" in result


@patch("httpx.get")
@patch("subprocess.run")
def test_handler_git_status_clean(mock_subproc_run, mock_httpx_get):
    """Handler should report 'clean' git status when no changes."""
    def _run_side_effect(cmd, **kwargs):
        if cmd[0] == "git" and "status" in cmd:
            return MagicMock(stdout="", returncode=0)
        if cmd[0] == "git" and "log" in cmd:
            return MagicMock(stdout="abc1234 latest commit msg", returncode=0)
        if cmd[0] == "ps":
            return MagicMock(stdout="", returncode=0)
        if cmd[0] == "df":
            return MagicMock(
                stdout="Filesystem Size Used Avail Use% Mounted\n/dev/sda1 100G 50G 50G 50% /home",
                returncode=0,
            )
        return MagicMock(stdout="", returncode=0)

    mock_subproc_run.side_effect = _run_side_effect

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_httpx_get.return_value = mock_resp

    handler = _make_health_handler(mind_root="/tmp/test-repo")
    result = handler({})

    assert "Git status" in result
    assert "clean" in result
    assert "Last commit" in result


@pytest.mark.asyncio
@patch("httpx.get")
@patch("subprocess.run")
async def test_handler_via_registry_execute(mock_subproc_run, mock_httpx_get, registry):
    """system_health should work through the registry.execute path."""
    mock_subproc_run.return_value = MagicMock(stdout="", returncode=0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_httpx_get.return_value = mock_resp

    register_health_tools(registry)
    result = await registry.execute("system_health", {})

    assert "System Health Report" in result
