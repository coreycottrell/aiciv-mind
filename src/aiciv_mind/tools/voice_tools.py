"""
aiciv_mind.tools.voice_tools — Text-to-speech via ElevenLabs API.

Root can generate audio from text and save it as MP3.
Uses the ElevenLabs REST API directly — no SDK dependency.

The generated audio files can be:
- Saved locally for later use
- Sent via other tools (Telegram, Hub, etc.)
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from aiciv_mind.tools import ToolRegistry

ELEVENLABS_API = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "RHY5GMXg2XfJq73yKR1a"  # ACG's configured voice
DEFAULT_MODEL = "eleven_turbo_v2_5"
OUTPUT_DIR = "/home/corey/projects/AI-CIV/aiciv-mind/data/audio"
TIMEOUT_SECONDS = 30
MAX_TEXT_LENGTH = 5000  # ElevenLabs limit for turbo model


_TTS_DEFINITION: dict = {
    "name": "text_to_speech",
    "description": (
        "Convert text to speech audio (MP3) using ElevenLabs. "
        "Returns the path to the generated audio file. "
        "Max text length: 5000 characters. "
        "Use for voice summaries, notifications, or audio content."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to convert to speech (max 5000 chars).",
            },
            "filename": {
                "type": "string",
                "description": (
                    "Output filename (without extension). "
                    "Default: 'tts-output'. File saved to data/audio/."
                ),
            },
        },
        "required": ["text"],
    },
}


async def _tts_handler(tool_input: dict) -> str:
    text = tool_input.get("text", "").strip()
    filename = tool_input.get("filename", "tts-output").strip()

    if not text:
        return "ERROR: No text provided"

    if len(text) > MAX_TEXT_LENGTH:
        return f"ERROR: Text too long ({len(text)} chars). Max: {MAX_TEXT_LENGTH}"

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        return "ERROR: ELEVENLABS_API_KEY not set in environment"

    # Ensure output directory exists
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "-_.")
    if not safe_filename:
        safe_filename = "tts-output"
    output_path = output_dir / f"{safe_filename}.mp3"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            r = await client.post(
                f"{ELEVENLABS_API}/text-to-speech/{DEFAULT_VOICE_ID}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": DEFAULT_MODEL,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
            )
            r.raise_for_status()

            output_path.write_bytes(r.content)
            size_kb = len(r.content) / 1024

            return (
                f"Audio generated: {output_path}\n"
                f"Size: {size_kb:.1f} KB\n"
                f"Text length: {len(text)} chars\n"
                f"Voice: {DEFAULT_VOICE_ID}\n"
                f"Model: {DEFAULT_MODEL}"
            )

    except httpx.HTTPStatusError as e:
        return f"ELEVENLABS API ERROR {e.response.status_code}: {e.response.text[:500]}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def register_voice_tools(registry: ToolRegistry) -> None:
    """Register voice/TTS tools."""
    registry.register("text_to_speech", _TTS_DEFINITION, _tts_handler, read_only=False)
