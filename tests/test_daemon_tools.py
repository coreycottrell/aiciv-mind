"""
Tests for aiciv_mind.tools.daemon_tools — Daemon & service health dashboard.

Covers: tool definition, daemon_health handler (HTTP checks, memory DB,
hub queue process detection, LiteLLM proxy), verbose flag, error paths,
and registration with ToolRegistry.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_daemon_tools.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.daemon_tools import (
    _DAEMON_HEALTH_DEFINITION,
    _check_http,
    _make_daemon_health_handler,
    register_daemon_tools,
)


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_daemon_health_definition_has_required_keys():
    """Definition must have name, description, and input_schema."""
    assert _DAEMON_HEALTH_DEFINITION["name"] == "daemon_health"
    assert "description" in _DAEMON_HEALTH_DEFINITION
    assert len(_DAEMON_HEALTH_DEFINITION["description"]) > 20
    schema = _DAEMON_HEALTH_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "verbose" in schema["properties"]


def test_daemon_health_definition_verbose_property():
    """verbose property should be boolean with a description."""
    prop = _DAEMON_HEALTH_DEFINITION["input_schema"]["properties"]["verbose"]
    assert prop["type"] == "boolean"
    assert "description" in prop


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_daemon_tools_adds_to_registry(registry):
    """register_daemon_tools should add daemon_health to the registry."""
    register_daemon_tools(registry)
    assert "daemon_health" in registry.names()


def test_daemon_health_is_read_only(registry):
    """daemon_health should be marked read_only."""
    register_daemon_tools(registry)
    assert registry.is_read_only("daemon_health") is True


def test_register_daemon_tools_with_memory_store(registry, memory_store):
    """Registration should succeed when memory_store is provided."""
    register_daemon_tools(registry, memory_store=memory_store)
    assert "daemon_health" in registry.names()


# ---------------------------------------------------------------------------
# _check_http tests — httpx is imported inside the function, so patch the
# module-level httpx.get via the httpx package itself
# ---------------------------------------------------------------------------


@patch("httpx.get")
def test_check_http_pass(mock_get):
    """_check_http returns PASS when endpoint returns 200."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status":"ok"}'
    mock_get.return_value = mock_resp

    status, detail = _check_http("http://example.com/health", "Test", verbose=False)
    assert status == "PASS"
    assert "ms" in detail


@patch("httpx.get")
def test_check_http_pass_verbose(mock_get):
    """_check_http includes response body snippet when verbose=True."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status":"ok"}'
    mock_get.return_value = mock_resp

    status, detail = _check_http("http://example.com/health", "Test", verbose=True)
    assert status == "PASS"
    assert '{"status":"ok"}' in detail


@patch("httpx.get")
def test_check_http_warn_on_non_200(mock_get):
    """_check_http returns WARN when endpoint returns non-200 status."""
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_get.return_value = mock_resp

    status, detail = _check_http("http://example.com/health", "Test", verbose=False)
    assert status == "WARN"
    assert "503" in detail


@patch("httpx.get")
def test_check_http_fail_on_exception(mock_get):
    """_check_http returns FAIL when request raises exception."""
    mock_get.side_effect = ConnectionError("refused")

    status, detail = _check_http("http://example.com/health", "Test", verbose=False)
    assert status == "FAIL"
    assert "unreachable" in detail
    assert "ConnectionError" in detail


# ---------------------------------------------------------------------------
# Handler tests (full handler, mocked HTTP + subprocess)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("subprocess.run")
@patch("httpx.get")
async def test_daemon_health_handler_all_pass(mock_httpx_get, mock_subproc_run, registry):
    """When all services pass, report should mention all service labels."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "ok"
    mock_httpx_get.return_value = mock_resp

    # Hub queue: simulate running process
    mock_subproc_run.return_value = MagicMock(
        stdout="12345 python groupchat_daemon.py\n",
        returncode=0,
    )

    register_daemon_tools(registry, memory_store=None)
    result = await registry.execute("daemon_health", {"verbose": False})

    assert "Daemon Health Dashboard" in result
    assert "Hub API" in result
    assert "AgentAuth" in result
    assert "AgentCal" in result


@pytest.mark.asyncio
@patch("subprocess.run")
@patch("httpx.get")
async def test_daemon_health_handler_with_memory_store(mock_httpx_get, mock_subproc_run, registry):
    """Handler should report memory DB status when memory_store is provided."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "ok"
    mock_httpx_get.return_value = mock_resp

    mock_subproc_run.return_value = MagicMock(stdout="", returncode=1)

    mock_store = MagicMock()
    mock_store._conn.execute.return_value.fetchone.return_value = (42,)

    register_daemon_tools(registry, memory_store=mock_store)
    result = await registry.execute("daemon_health", {})

    assert "Memory DB" in result
    assert "42 memories" in result
    assert "PASS" in result


@pytest.mark.asyncio
@patch("subprocess.run")
@patch("httpx.get")
async def test_daemon_health_no_memory_store_warns(mock_httpx_get, mock_subproc_run, registry):
    """When no memory_store is provided, Memory DB should show WARN."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "ok"
    mock_httpx_get.return_value = mock_resp

    mock_subproc_run.return_value = MagicMock(stdout="", returncode=1)

    register_daemon_tools(registry, memory_store=None)
    result = await registry.execute("daemon_health", {})

    assert "Memory DB" in result
    assert "no memory_store" in result
