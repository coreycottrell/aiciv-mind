"""
Tests for aiciv_mind.tools.web_fetch_tools and web_search_tools.

Covers: tool definitions, handlers with mocked HTTP, error cases, registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_web_tools.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.web_fetch_tools import (
    _DEFINITION as WEB_FETCH_DEFINITION,
    _web_fetch_handler,
    register_web_fetch,
)
from aiciv_mind.tools.web_search_tools import (
    _WEB_SEARCH_DEFINITION,
    _web_search_handler,
    register_web_search,
)


# ===========================================================================
# web_fetch — definition tests
# ===========================================================================


def test_web_fetch_definition_name():
    assert WEB_FETCH_DEFINITION["name"] == "web_fetch"


def test_web_fetch_definition_has_description():
    assert isinstance(WEB_FETCH_DEFINITION["description"], str)
    assert len(WEB_FETCH_DEFINITION["description"]) > 10


def test_web_fetch_requires_url():
    schema = WEB_FETCH_DEFINITION["input_schema"]
    assert "url" in schema["properties"]
    assert "url" in schema["required"]


# ===========================================================================
# web_fetch — handler tests
# ===========================================================================


@pytest.mark.asyncio
async def test_web_fetch_missing_url():
    result = await _web_fetch_handler({"url": ""})
    assert "ERROR" in result
    assert "No URL" in result


@pytest.mark.asyncio
async def test_web_fetch_invalid_scheme():
    result = await _web_fetch_handler({"url": "ftp://example.com"})
    assert "ERROR" in result
    assert "http" in result.lower()


@pytest.mark.asyncio
async def test_web_fetch_success_json():
    """Fetching a JSON endpoint returns raw content."""
    mock_response = MagicMock()
    mock_response.text = '{"key": "value"}'
    mock_response.headers = {"content-type": "application/json"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("aiciv_mind.tools.web_fetch_tools.httpx.AsyncClient", return_value=mock_client):
        result = await _web_fetch_handler({"url": "https://api.example.com/data"})

    assert '"key"' in result
    assert '"value"' in result


@pytest.mark.asyncio
async def test_web_fetch_success_html():
    """Fetching an HTML page converts to text (or returns html2text output)."""
    html = "<html><body><h1>Hello World</h1><p>Content here.</p></body></html>"
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.headers = {"content-type": "text/html; charset=utf-8"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("aiciv_mind.tools.web_fetch_tools.httpx.AsyncClient", return_value=mock_client):
        result = await _web_fetch_handler({"url": "https://example.com"})

    # Either html2text or fallback regex strip — both should extract text
    assert "Hello World" in result
    assert "Content here" in result


# ===========================================================================
# web_search — definition tests
# ===========================================================================


def test_web_search_definition_name():
    assert _WEB_SEARCH_DEFINITION["name"] == "web_search"


def test_web_search_definition_has_description():
    assert isinstance(_WEB_SEARCH_DEFINITION["description"], str)
    assert len(_WEB_SEARCH_DEFINITION["description"]) > 10


def test_web_search_requires_query():
    schema = _WEB_SEARCH_DEFINITION["input_schema"]
    assert "query" in schema["properties"]
    assert "query" in schema["required"]


# ===========================================================================
# web_search — handler tests
# ===========================================================================


@pytest.mark.asyncio
async def test_web_search_no_api_key(monkeypatch):
    """Handler returns informative message when OLLAMA_API_KEY is missing."""
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    result = await _web_search_handler({"query": "test query"})
    assert "unavailable" in result.lower() or "OLLAMA_API_KEY" in result


@pytest.mark.asyncio
async def test_web_search_success(monkeypatch):
    """Handler returns formatted results on success."""
    monkeypatch.setenv("OLLAMA_API_KEY", "test-ollama-key")

    fake_results = {
        "results": [
            {"title": "Result One", "url": "https://one.com", "snippet": "First result snippet"},
            {"title": "Result Two", "url": "https://two.com", "snippet": "Second result snippet"},
        ]
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = fake_results

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # httpx is imported inside the handler, so we patch it at the top-level module
    import httpx as _httpx
    with patch.dict("sys.modules", {"httpx": MagicMock(AsyncClient=MagicMock(return_value=mock_client))}):
        result = await _web_search_handler({"query": "aiciv mind"})

    assert "Result One" in result
    assert "Result Two" in result
    assert "https://one.com" in result


# ===========================================================================
# Registration tests
# ===========================================================================


def test_register_web_fetch():
    registry = ToolRegistry()
    register_web_fetch(registry)
    assert "web_fetch" in registry.names()
    assert registry.is_read_only("web_fetch")


def test_register_web_search():
    registry = ToolRegistry()
    register_web_search(registry)
    assert "web_search" in registry.names()
    assert registry.is_read_only("web_search")
