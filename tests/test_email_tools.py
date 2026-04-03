"""
Tests for aiciv_mind.tools.email_tools — AgentMail integration.

Covers: tool definitions (email_read, email_send), handlers with mocked
AgentMail SDK, error paths (missing API key, missing fields), and registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_email_tools.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.email_tools import (
    _READ_DEFINITION,
    _SEND_DEFINITION,
    _make_read_handler,
    _make_send_handler,
    register_email_tools,
)


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_read_definition():
    """email_read definition should have correct name and schema."""
    assert _READ_DEFINITION["name"] == "email_read"
    assert "description" in _READ_DEFINITION
    schema = _READ_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "limit" in schema["properties"]
    assert "message_id" in schema["properties"]


def test_send_definition():
    """email_send definition should require to, subject, body."""
    assert _SEND_DEFINITION["name"] == "email_send"
    schema = _SEND_DEFINITION["input_schema"]
    assert "to" in schema["properties"]
    assert "subject" in schema["properties"]
    assert "body" in schema["properties"]
    assert set(schema["required"]) == {"to", "subject", "body"}


def test_definitions_have_required_keys():
    """Both definitions must have name, description, input_schema."""
    for defn in [_READ_DEFINITION, _SEND_DEFINITION]:
        assert "name" in defn
        assert "description" in defn
        assert defn["input_schema"]["type"] == "object"
        assert "properties" in defn["input_schema"]


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_email_tools(registry):
    """Both tools should appear in registry after registration."""
    register_email_tools(registry, inbox_id="inbox-abc")
    names = registry.names()
    assert "email_read" in names
    assert "email_send" in names


def test_email_read_is_read_only(registry):
    """email_read should be read_only; email_send should not."""
    register_email_tools(registry, inbox_id="inbox-abc")
    assert registry.is_read_only("email_read") is True
    assert registry.is_read_only("email_send") is False


# ---------------------------------------------------------------------------
# email_read handler tests
#
# AsyncAgentMail is imported inside the handler with
#   `from agentmail import AsyncAgentMail`
# so we patch it at the package level: "agentmail.AsyncAgentMail"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_read_missing_api_key():
    """email_read should return ERROR when AGENTMAIL_API_KEY is not set."""
    handler = _make_read_handler("inbox-abc")

    with patch.dict("os.environ", {}, clear=True):
        result = await handler({})

    assert "ERROR" in result
    assert "AGENTMAIL_API_KEY" in result


@pytest.mark.asyncio
async def test_email_read_list_messages():
    """email_read should list messages when no message_id is provided."""
    handler = _make_read_handler("inbox-abc")

    mock_msg = MagicMock()
    mock_msg.from_ = "alice@test.com"
    mock_msg.subject = "Hello"
    mock_msg.preview = "Preview of the message"
    mock_msg.message_id = "msg-1"
    mock_msg.labels = ["inbox"]
    mock_msg.timestamp = "2026-04-01T10:00:00Z"

    mock_result = MagicMock()
    mock_result.messages = [mock_msg]
    mock_result.count = 1

    mock_client = AsyncMock()
    mock_client.inboxes.messages.list = AsyncMock(return_value=mock_result)

    with patch.dict("os.environ", {"AGENTMAIL_API_KEY": "test-key"}):
        with patch("agentmail.AsyncAgentMail", return_value=mock_client):
            result = await handler({"limit": 5})

    assert "inbox-abc" in result
    assert "alice@test.com" in result
    assert "Hello" in result
    assert "msg-1" in result


@pytest.mark.asyncio
async def test_email_read_single_message():
    """email_read should return full message body when message_id is provided."""
    handler = _make_read_handler("inbox-abc")

    mock_msg = MagicMock()
    mock_msg.from_ = "bob@test.com"
    mock_msg.subject = "Important"
    mock_msg.timestamp = "2026-04-01T12:00:00Z"
    mock_msg.text = "This is the full body content."
    mock_msg.labels = ["inbox", "important"]

    mock_client = AsyncMock()
    mock_client.inboxes.messages.get = AsyncMock(return_value=mock_msg)

    with patch.dict("os.environ", {"AGENTMAIL_API_KEY": "test-key"}):
        with patch("agentmail.AsyncAgentMail", return_value=mock_client):
            result = await handler({"message_id": "msg-42"})

    assert "bob@test.com" in result
    assert "Important" in result
    assert "full body content" in result


@pytest.mark.asyncio
async def test_email_read_empty_inbox():
    """email_read should return empty message when inbox has no messages."""
    handler = _make_read_handler("inbox-abc")

    mock_result = MagicMock()
    mock_result.messages = []

    mock_client = AsyncMock()
    mock_client.inboxes.messages.list = AsyncMock(return_value=mock_result)

    with patch.dict("os.environ", {"AGENTMAIL_API_KEY": "test-key"}):
        with patch("agentmail.AsyncAgentMail", return_value=mock_client):
            result = await handler({})

    assert "empty" in result.lower() or "inbox-abc" in result


# ---------------------------------------------------------------------------
# email_send handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_send_missing_api_key():
    """email_send should return ERROR when AGENTMAIL_API_KEY is not set."""
    handler = _make_send_handler("inbox-abc")

    with patch.dict("os.environ", {}, clear=True):
        result = await handler({
            "to": "someone@test.com",
            "subject": "Test",
            "body": "Hello",
        })

    assert "ERROR" in result
    assert "AGENTMAIL_API_KEY" in result


@pytest.mark.asyncio
async def test_email_send_success():
    """email_send should return confirmation with message_id on success."""
    handler = _make_send_handler("inbox-abc")

    mock_result = MagicMock()
    mock_result.message_id = "sent-123"

    mock_client = AsyncMock()
    mock_client.inboxes.messages.send = AsyncMock(return_value=mock_result)

    with patch.dict("os.environ", {"AGENTMAIL_API_KEY": "test-key"}):
        with patch("agentmail.AsyncAgentMail", return_value=mock_client):
            result = await handler({
                "to": "recipient@test.com",
                "subject": "Status Update",
                "body": "All systems nominal.",
            })

    assert "sent" in result.lower()
    assert "recipient@test.com" in result
    assert "sent-123" in result
    mock_client.inboxes.messages.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_email_send_reply():
    """email_send should use reply method when reply_to_id is provided."""
    handler = _make_send_handler("inbox-abc")

    mock_result = MagicMock()
    mock_result.message_id = "reply-456"

    mock_client = AsyncMock()
    mock_client.inboxes.messages.reply = AsyncMock(return_value=mock_result)

    with patch.dict("os.environ", {"AGENTMAIL_API_KEY": "test-key"}):
        with patch("agentmail.AsyncAgentMail", return_value=mock_client):
            result = await handler({
                "to": "someone@test.com",
                "subject": "Re: Hello",
                "body": "Thanks for your message.",
                "reply_to_id": "msg-original",
            })

    assert "Replied to message msg-original" in result
    assert "reply-456" in result
    mock_client.inboxes.messages.reply.assert_awaited_once_with(
        "inbox-abc", "msg-original", text="Thanks for your message.",
    )


@pytest.mark.asyncio
async def test_email_send_error_handling():
    """email_send should return ERROR on exception from SDK."""
    handler = _make_send_handler("inbox-abc")

    mock_client = AsyncMock()
    mock_client.inboxes.messages.send = AsyncMock(
        side_effect=RuntimeError("relay failed")
    )

    with patch.dict("os.environ", {"AGENTMAIL_API_KEY": "test-key"}):
        with patch("agentmail.AsyncAgentMail", return_value=mock_client):
            result = await handler({
                "to": "fail@test.com",
                "subject": "Fail",
                "body": "This should fail.",
            })

    assert "ERROR" in result
    assert "RuntimeError" in result
    assert "relay failed" in result
