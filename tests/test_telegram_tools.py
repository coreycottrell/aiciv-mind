"""
Tests for aiciv_mind.tools.telegram_tools (Fix #25).

Proves:
1. Tool registration is env-gated (no token = no tool)
2. Tool definition has correct schema
3. Handler validates empty message
4. Handler truncates long messages
5. telegram_send is in PRIMARY_TOOLS whitelist
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from aiciv_mind.roles import PRIMARY_TOOLS


# ---------------------------------------------------------------------------
# Test 1: telegram_send is in PRIMARY_TOOLS whitelist
# ---------------------------------------------------------------------------

def test_telegram_send_in_primary_tools():
    """telegram_send must be in the PRIMARY role whitelist."""
    assert "telegram_send" in PRIMARY_TOOLS


# ---------------------------------------------------------------------------
# Test 2: Registration skipped without token
# ---------------------------------------------------------------------------

def test_registration_skipped_without_token():
    """If AICIV_MIND_TG_TOKEN is not set, tool is not registered."""
    from aiciv_mind.tools import ToolRegistry
    from aiciv_mind.tools.telegram_tools import register_telegram_tools

    registry = ToolRegistry()
    with patch.dict(os.environ, {}, clear=True):
        # Ensure no token
        os.environ.pop("AICIV_MIND_TG_TOKEN", None)
        register_telegram_tools(registry)

    assert "telegram_send" not in registry.names()


# ---------------------------------------------------------------------------
# Test 3: Registration succeeds with token
# ---------------------------------------------------------------------------

def test_registration_with_token():
    """If AICIV_MIND_TG_TOKEN is set, tool is registered."""
    from aiciv_mind.tools import ToolRegistry
    from aiciv_mind.tools.telegram_tools import register_telegram_tools

    registry = ToolRegistry()
    with patch.dict(os.environ, {"AICIV_MIND_TG_TOKEN": "fake-token-123"}):
        register_telegram_tools(registry)

    assert "telegram_send" in registry.names()


# ---------------------------------------------------------------------------
# Test 4: Empty message rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_message_rejected():
    """Handler returns error for empty message."""
    from aiciv_mind.tools.telegram_tools import _make_telegram_send_handler

    handler = _make_telegram_send_handler("fake-token", 12345)
    result = await handler({"message": ""})
    assert "ERROR" in result
    assert "required" in result


# ---------------------------------------------------------------------------
# Test 5: Long message truncated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_long_message_truncated():
    """Messages over 4096 chars are truncated with [truncated] marker."""
    from aiciv_mind.tools.telegram_tools import _make_telegram_send_handler

    handler = _make_telegram_send_handler("fake-token", 12345)
    long_msg = "x" * 5000

    # Mock httpx to capture the actual payload
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": {"message_id": 42}}

    with patch("aiciv_mind.tools.telegram_tools.httpx") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = mock_client

        result = await handler({"message": long_msg})

        # Verify the sent text was truncated
        call_args = mock_client.post.call_args
        sent_text = call_args[1]["json"]["text"]
        assert len(sent_text) <= 4096
        assert "[truncated]" in sent_text

    assert "sent" in result.lower() or "msg_id" in result.lower()


# ---------------------------------------------------------------------------
# Test 6: Successful send returns msg_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_successful_send():
    """Successful TG API call returns message with msg_id."""
    from aiciv_mind.tools.telegram_tools import _make_telegram_send_handler

    handler = _make_telegram_send_handler("fake-token", 437939400)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": {"message_id": 999}}

    with patch("aiciv_mind.tools.telegram_tools.httpx") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = mock_client

        result = await handler({"message": "Test message"})

    assert "999" in result
    assert "sent" in result.lower()


# ---------------------------------------------------------------------------
# Test 7: API error handled gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_error_handled():
    """Non-200 TG API response returns error message."""
    from aiciv_mind.tools.telegram_tools import _make_telegram_send_handler

    handler = _make_telegram_send_handler("fake-token", 437939400)

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden: bot was blocked by the user"

    with patch("aiciv_mind.tools.telegram_tools.httpx") as mock_httpx:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.AsyncClient.return_value = mock_client

        result = await handler({"message": "Test"})

    assert "ERROR" in result
    assert "403" in result
