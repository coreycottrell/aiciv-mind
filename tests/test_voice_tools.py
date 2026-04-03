"""
Tests for aiciv_mind.tools.voice_tools — text_to_speech tool.

Covers: tool definition, handler with mocked ElevenLabs API, error cases, registration.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_voice_tools.py -v
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.voice_tools import (
    _TTS_DEFINITION,
    _tts_handler,
    register_voice_tools,
    ELEVENLABS_API,
    DEFAULT_VOICE_ID,
    DEFAULT_MODEL,
    MAX_TEXT_LENGTH,
)


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


def test_tts_definition_name():
    assert _TTS_DEFINITION["name"] == "text_to_speech"


def test_tts_definition_has_description():
    desc = _TTS_DEFINITION["description"]
    assert isinstance(desc, str)
    assert len(desc) > 10


def test_tts_definition_input_schema_requires_text():
    schema = _TTS_DEFINITION["input_schema"]
    assert schema["type"] == "object"
    assert "text" in schema["properties"]
    assert "text" in schema["required"]


def test_tts_definition_has_optional_filename():
    schema = _TTS_DEFINITION["input_schema"]
    assert "filename" in schema["properties"]
    # filename should NOT be required
    assert "filename" not in schema.get("required", [])


# ---------------------------------------------------------------------------
# Handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tts_handler_missing_text():
    """Handler returns error when text is empty."""
    result = await _tts_handler({"text": ""})
    assert "ERROR" in result
    assert "No text provided" in result


@pytest.mark.asyncio
async def test_tts_handler_text_too_long():
    """Handler returns error when text exceeds max length."""
    result = await _tts_handler({"text": "x" * (MAX_TEXT_LENGTH + 1)})
    assert "ERROR" in result
    assert "too long" in result.lower()


@pytest.mark.asyncio
async def test_tts_handler_no_api_key(monkeypatch):
    """Handler returns error when ELEVENLABS_API_KEY is missing."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    result = await _tts_handler({"text": "hello world"})
    assert "ERROR" in result
    assert "ELEVENLABS_API_KEY" in result


@pytest.mark.asyncio
async def test_tts_handler_success(monkeypatch, tmp_path):
    """Handler calls ElevenLabs API and writes audio file on success."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-123")

    fake_audio = b"\xff\xfb\x90\x00" * 100  # fake MP3 bytes

    mock_response = MagicMock()
    mock_response.content = fake_audio
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Redirect output dir to tmp_path
    with patch("aiciv_mind.tools.voice_tools.OUTPUT_DIR", str(tmp_path)):
        with patch("aiciv_mind.tools.voice_tools.httpx.AsyncClient", return_value=mock_client):
            result = await _tts_handler({"text": "hello world", "filename": "test-audio"})

    assert "Audio generated" in result
    assert "test-audio.mp3" in result
    assert str(tmp_path) in result

    # Verify the API was called with correct URL and payload
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert DEFAULT_VOICE_ID in call_args[0][0]  # URL contains voice ID
    assert call_args[1]["json"]["text"] == "hello world"
    assert call_args[1]["json"]["model_id"] == DEFAULT_MODEL
    assert call_args[1]["headers"]["xi-api-key"] == "test-key-123"


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_register_voice_tools():
    """register_voice_tools adds text_to_speech to the registry."""
    registry = ToolRegistry()
    register_voice_tools(registry)
    assert "text_to_speech" in registry.names()
    # Should be registered as NOT read_only (it writes files)
    assert not registry.is_read_only("text_to_speech")
