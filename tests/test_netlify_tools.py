"""
Tests for aiciv_mind.tools.netlify_tools — netlify_deploy and netlify_status.

Covers: tool definitions, handlers with mocked HTTP, error cases, registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_netlify_tools.py -v
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.netlify_tools import (
    _DEPLOY_DEFINITION,
    _STATUS_DEFINITION,
    _deploy_handler,
    _status_handler,
    register_netlify_tools,
    AICIV_INC_SITE_ID,
)


# ---------------------------------------------------------------------------
# Definition tests
# ---------------------------------------------------------------------------


def test_deploy_definition_name():
    assert _DEPLOY_DEFINITION["name"] == "netlify_deploy"


def test_deploy_definition_requires_deploy_dir():
    schema = _DEPLOY_DEFINITION["input_schema"]
    assert "deploy_dir" in schema["properties"]
    assert "deploy_dir" in schema["required"]


def test_status_definition_name():
    assert _STATUS_DEFINITION["name"] == "netlify_status"


def test_status_definition_has_description():
    assert isinstance(_STATUS_DEFINITION["description"], str)
    assert len(_STATUS_DEFINITION["description"]) > 10


# ---------------------------------------------------------------------------
# Deploy handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deploy_missing_dir():
    result = await _deploy_handler({"deploy_dir": ""})
    assert "ERROR" in result
    assert "No deploy_dir" in result


@pytest.mark.asyncio
async def test_deploy_nonexistent_dir():
    result = await _deploy_handler({"deploy_dir": "/nonexistent/path/xyz"})
    assert "ERROR" in result
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_deploy_no_token(tmp_path, monkeypatch):
    """Deploy fails gracefully when no Netlify token is available."""
    monkeypatch.delenv("NETLIFY_AUTH_TOKEN", raising=False)
    # Create a file so the dir is not empty
    (tmp_path / "index.html").write_text("<h1>hi</h1>")

    with patch("aiciv_mind.tools.netlify_tools._get_netlify_token", return_value=None):
        result = await _deploy_handler({"deploy_dir": str(tmp_path)})
    assert "ERROR" in result
    assert "token" in result.lower()


@pytest.mark.asyncio
async def test_deploy_success(tmp_path):
    """Deploy succeeds with mocked Netlify API."""
    (tmp_path / "index.html").write_text("<h1>Hello</h1>")
    (tmp_path / "style.css").write_text("body { color: red; }")

    deploy_response = MagicMock()
    deploy_response.json.return_value = {
        "id": "deploy-abc-123",
        "required": [],
        "ssl_url": "https://ai-civ.com",
        "state": "ready",
    }
    deploy_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=deploy_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("aiciv_mind.tools.netlify_tools._get_netlify_token", return_value="fake-token"):
        with patch("aiciv_mind.tools.netlify_tools.httpx.AsyncClient", return_value=mock_client):
            result = await _deploy_handler({
                "deploy_dir": str(tmp_path),
                "deploy_message": "test deploy",
            })

    assert "deploy-abc-123" in result
    assert "ready" in result.lower()
    assert "2 total" in result


# ---------------------------------------------------------------------------
# Status handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_no_token():
    with patch("aiciv_mind.tools.netlify_tools._get_netlify_token", return_value=None):
        result = await _status_handler({})
    assert "ERROR" in result
    assert "token" in result.lower()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_netlify_tools():
    registry = ToolRegistry()
    register_netlify_tools(registry)
    names = registry.names()
    assert "netlify_deploy" in names
    assert "netlify_status" in names
    # deploy is NOT read_only, status IS read_only
    assert not registry.is_read_only("netlify_deploy")
    assert registry.is_read_only("netlify_status")
