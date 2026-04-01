"""
aiciv_mind.tools.web_fetch_tools — Fetch and read any URL.

Returns clean markdown/text extracted from HTML pages,
or raw content for non-HTML responses (JSON, plain text, etc.).

Uses httpx for HTTP and html2text for HTML→markdown conversion.
"""

from __future__ import annotations

import asyncio

import httpx

from aiciv_mind.tools import ToolRegistry

TIMEOUT_SECONDS = 30
MAX_CONTENT_LENGTH = 100_000  # ~100KB of text content

_DEFINITION: dict = {
    "name": "web_fetch",
    "description": (
        "Fetch a URL and return its content as clean text/markdown. "
        "HTML pages are converted to readable markdown. "
        "JSON and plain text are returned as-is. "
        "Use for reading blog posts, documentation, APIs, or any web page."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch.",
            },
            "raw": {
                "type": "boolean",
                "description": "If true, return raw HTML instead of converting to markdown. Default: false.",
            },
        },
        "required": ["url"],
    },
}


async def _web_fetch_handler(tool_input: dict) -> str:
    url = tool_input.get("url", "").strip()
    raw_mode = tool_input.get("raw", False)

    if not url:
        return "ERROR: No URL provided"

    if not url.startswith(("http://", "https://")):
        return "ERROR: URL must start with http:// or https://"

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=TIMEOUT_SECONDS,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AiCIV-Mind/1.0; +https://ai-civ.com)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        body = response.text

        # Non-HTML: return as-is
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            if len(body) > MAX_CONTENT_LENGTH:
                body = body[:MAX_CONTENT_LENGTH] + f"\n\n[TRUNCATED — {len(body)} chars total]"
            return body

        # HTML: convert to markdown unless raw mode
        if raw_mode:
            if len(body) > MAX_CONTENT_LENGTH:
                body = body[:MAX_CONTENT_LENGTH] + f"\n\n[TRUNCATED — {len(body)} chars total]"
            return body

        try:
            import html2text
            converter = html2text.HTML2Text()
            converter.ignore_links = False
            converter.ignore_images = True
            converter.ignore_emphasis = False
            converter.body_width = 0  # no line wrapping
            converter.skip_internal_links = True
            text = converter.handle(body)
        except ImportError:
            # Fallback: basic tag stripping
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

        if len(text) > MAX_CONTENT_LENGTH:
            text = text[:MAX_CONTENT_LENGTH] + f"\n\n[TRUNCATED — {len(text)} chars total]"

        return text.strip() if text.strip() else "(page returned empty content)"

    except httpx.HTTPStatusError as e:
        return f"HTTP ERROR {e.response.status_code}: {url}"
    except httpx.TimeoutException:
        return f"TIMEOUT: Request to {url} exceeded {TIMEOUT_SECONDS}s"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def register_web_fetch(registry: ToolRegistry) -> None:
    """Register the web_fetch tool."""
    registry.register("web_fetch", _DEFINITION, _web_fetch_handler, read_only=True)
