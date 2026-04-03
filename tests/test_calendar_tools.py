"""
Tests for aiciv_mind.tools.calendar_tools — AgentCal calendar management.

Covers: tool definitions (list_events, create_event, delete_event),
handlers with mocked HTTP (httpx.AsyncClient), auth helper, error paths
(missing fields, invalid metadata, API errors), and registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_calendar_tools.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.calendar_tools import (
    _LIST_EVENTS_DEFINITION,
    _CREATE_EVENT_DEFINITION,
    _DELETE_EVENT_DEFINITION,
    _make_list_events_handler,
    _make_create_event_handler,
    _make_delete_event_handler,
    register_calendar_tools,
)


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_list_events_definition():
    """calendar_list_events definition should have correct name and schema."""
    assert _LIST_EVENTS_DEFINITION["name"] == "calendar_list_events"
    assert "description" in _LIST_EVENTS_DEFINITION
    schema = _LIST_EVENTS_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "limit" in schema["properties"]


def test_create_event_definition():
    """calendar_create_event definition should require title, start_time, end_time."""
    assert _CREATE_EVENT_DEFINITION["name"] == "calendar_create_event"
    schema = _CREATE_EVENT_DEFINITION["input_schema"]
    assert "title" in schema["properties"]
    assert "start_time" in schema["properties"]
    assert "end_time" in schema["properties"]
    assert set(schema["required"]) == {"title", "start_time", "end_time"}


def test_delete_event_definition():
    """calendar_delete_event definition should require event_id."""
    assert _DELETE_EVENT_DEFINITION["name"] == "calendar_delete_event"
    schema = _DELETE_EVENT_DEFINITION["input_schema"]
    assert "event_id" in schema["properties"]
    assert schema["required"] == ["event_id"]


def test_all_definitions_have_required_keys():
    """All three definitions must have name, description, input_schema with type=object."""
    for defn in [_LIST_EVENTS_DEFINITION, _CREATE_EVENT_DEFINITION, _DELETE_EVENT_DEFINITION]:
        assert "name" in defn
        assert "description" in defn
        assert defn["input_schema"]["type"] == "object"
        assert "properties" in defn["input_schema"]


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_calendar_tools(registry):
    """All three calendar tools should appear in registry after registration."""
    register_calendar_tools(registry, keypair_path="/fake/key.json", calendar_id="cal-1")
    names = registry.names()
    assert "calendar_list_events" in names
    assert "calendar_create_event" in names
    assert "calendar_delete_event" in names


def test_calendar_list_events_is_read_only(registry):
    """calendar_list_events should be read_only; create and delete should not."""
    register_calendar_tools(registry, keypair_path="/fake/key.json", calendar_id="cal-1")
    assert registry.is_read_only("calendar_list_events") is True
    assert registry.is_read_only("calendar_create_event") is False
    assert registry.is_read_only("calendar_delete_event") is False


# ---------------------------------------------------------------------------
# Helper: build a mock httpx.AsyncClient context manager
# ---------------------------------------------------------------------------


def _build_mock_async_client(response_status=200, response_json=None, response_text=""):
    """Return a mock that replaces httpx.AsyncClient() as a context manager."""
    mock_resp = MagicMock()
    mock_resp.status_code = response_status
    mock_resp.json.return_value = response_json if response_json is not None else {}
    mock_resp.text = response_text

    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=mock_resp)
    mock_client_instance.post = AsyncMock(return_value=mock_resp)
    mock_client_instance.delete = AsyncMock(return_value=mock_resp)

    # Make the context manager work: async with httpx.AsyncClient() as client:
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    return mock_ctx, mock_client_instance


# ---------------------------------------------------------------------------
# calendar_list_events handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_events_success():
    """list_events should return formatted events on success."""
    handler = _make_list_events_handler("/fake/key.json", "cal-123")

    events = [
        {"id": "e1", "summary": "Standup", "start": "2026-04-01T09:00Z", "end": "2026-04-01T09:30Z"},
        {"id": "e2", "summary": "Review", "start": "2026-04-01T14:00Z", "end": "2026-04-01T15:00Z"},
    ]

    mock_ctx, mock_client = _build_mock_async_client(200, events)

    with patch(
        "aiciv_mind.tools.calendar_tools._get_agentcal_token",
        new_callable=AsyncMock,
        return_value="tok-abc",
    ):
        with patch("httpx.AsyncClient", return_value=mock_ctx):
            result = await handler({"limit": 10})

    assert "Standup" in result
    assert "Review" in result
    assert "e1" in result


@pytest.mark.asyncio
async def test_list_events_empty():
    """list_events should return 'No events found' when API returns empty list."""
    handler = _make_list_events_handler("/fake/key.json", "cal-123")

    mock_ctx, _ = _build_mock_async_client(200, [])

    with patch(
        "aiciv_mind.tools.calendar_tools._get_agentcal_token",
        new_callable=AsyncMock,
        return_value="tok-abc",
    ):
        with patch("httpx.AsyncClient", return_value=mock_ctx):
            result = await handler({})

    assert "No events found" in result


@pytest.mark.asyncio
async def test_list_events_api_error():
    """list_events should return ERROR when API returns non-200."""
    handler = _make_list_events_handler("/fake/key.json", "cal-123")

    mock_ctx, _ = _build_mock_async_client(500, None, "Internal Server Error")

    with patch(
        "aiciv_mind.tools.calendar_tools._get_agentcal_token",
        new_callable=AsyncMock,
        return_value="tok-abc",
    ):
        with patch("httpx.AsyncClient", return_value=mock_ctx):
            result = await handler({})

    assert "ERROR" in result
    assert "500" in result


# ---------------------------------------------------------------------------
# calendar_create_event handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_event_success():
    """create_event should return confirmation with event ID on success."""
    handler = _make_create_event_handler("/fake/key.json", "cal-123")

    mock_ctx, _ = _build_mock_async_client(201, {"id": "evt-999"})

    with patch(
        "aiciv_mind.tools.calendar_tools._get_agentcal_token",
        new_callable=AsyncMock,
        return_value="tok-abc",
    ):
        with patch("httpx.AsyncClient", return_value=mock_ctx):
            result = await handler({
                "title": "Team Sync",
                "start_time": "2026-04-01T10:00:00Z",
                "end_time": "2026-04-01T11:00:00Z",
            })

    assert "Event created" in result
    assert "Team Sync" in result
    assert "evt-999" in result


@pytest.mark.asyncio
async def test_create_event_missing_required_fields():
    """create_event should return ERROR when title/start_time/end_time is missing."""
    handler = _make_create_event_handler("/fake/key.json", "cal-123")

    result = await handler({"title": "", "start_time": "2026-04-01T10:00:00Z", "end_time": ""})
    assert "ERROR" in result
    assert "required" in result


@pytest.mark.asyncio
async def test_create_event_invalid_metadata():
    """create_event should return ERROR for invalid JSON metadata."""
    handler = _make_create_event_handler("/fake/key.json", "cal-123")

    result = await handler({
        "title": "Test",
        "start_time": "2026-04-01T10:00:00Z",
        "end_time": "2026-04-01T11:00:00Z",
        "metadata": "not-valid-json{",
    })

    assert "ERROR" in result
    assert "metadata must be valid JSON" in result


@pytest.mark.asyncio
async def test_create_event_with_valid_metadata():
    """create_event should include parsed metadata in payload."""
    handler = _make_create_event_handler("/fake/key.json", "cal-123")

    mock_ctx, mock_client = _build_mock_async_client(201, {"id": "evt-m"})

    with patch(
        "aiciv_mind.tools.calendar_tools._get_agentcal_token",
        new_callable=AsyncMock,
        return_value="tok",
    ):
        with patch("httpx.AsyncClient", return_value=mock_ctx):
            result = await handler({
                "title": "With Meta",
                "start_time": "2026-04-01T10:00:00Z",
                "end_time": "2026-04-01T11:00:00Z",
                "metadata": '{"priority": "high"}',
            })

    assert "Event created" in result
    # Verify the POST payload included metadata
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert payload["metadata"] == {"priority": "high"}


# ---------------------------------------------------------------------------
# calendar_delete_event handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_event_success():
    """delete_event should return confirmation on success."""
    handler = _make_delete_event_handler("/fake/key.json", "cal-123")

    mock_ctx, _ = _build_mock_async_client(204)

    with patch(
        "aiciv_mind.tools.calendar_tools._get_agentcal_token",
        new_callable=AsyncMock,
        return_value="tok",
    ):
        with patch("httpx.AsyncClient", return_value=mock_ctx):
            result = await handler({"event_id": "evt-42"})

    assert "deleted successfully" in result
    assert "evt-42" in result


@pytest.mark.asyncio
async def test_delete_event_missing_event_id():
    """delete_event should return ERROR when event_id is empty or missing."""
    handler = _make_delete_event_handler("/fake/key.json", "cal-123")

    result = await handler({"event_id": ""})
    assert "ERROR" in result
    assert "event_id is required" in result

    result2 = await handler({})
    assert "ERROR" in result2
