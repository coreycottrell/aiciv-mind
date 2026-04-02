"""
aiciv_mind.tools.browser_tools — Browser automation via Playwright.

Provides tools for navigating, interacting with, and taking snapshots of web pages.
Uses Playwright's async API for headless Chromium.

Tools:
    browser_navigate  — Navigate to a URL and return page content
    browser_click     — Click an element by CSS selector
    browser_type      — Type text into an element
    browser_snapshot  — Get current page accessibility snapshot (text content)
    browser_screenshot — Take a screenshot of the current page
    browser_evaluate  — Execute JavaScript in the page context

Gracefully handles missing Playwright dependency — tools return an install
hint if playwright is not available.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any

from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy Playwright context — shared across tool calls
# ---------------------------------------------------------------------------

_playwright_instance = None
_browser = None
_page = None


def _playwright_available() -> bool:
    """Check if playwright is installed."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


async def _ensure_page():
    """Lazily initialize Playwright and return the current page."""
    global _playwright_instance, _browser, _page

    if _page is not None and not _page.is_closed():
        return _page

    from playwright.async_api import async_playwright

    if _playwright_instance is None:
        _playwright_instance = await async_playwright().start()

    if _browser is None or not _browser.is_connected():
        _browser = await _playwright_instance.chromium.launch(headless=True)

    _page = await _browser.new_page()
    return _page


async def _close_browser():
    """Close the browser and playwright instance."""
    global _playwright_instance, _browser, _page

    if _page is not None:
        try:
            await _page.close()
        except Exception:
            pass
        _page = None

    if _browser is not None:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None

    if _playwright_instance is not None:
        try:
            await _playwright_instance.stop()
        except Exception:
            pass
        _playwright_instance = None


_NOT_INSTALLED = (
    "Playwright is not installed. Install with:\n"
    "  pip install playwright\n"
    "  playwright install chromium"
)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


NAVIGATE_DEFINITION: dict = {
    "name": "browser_navigate",
    "description": (
        "Navigate to a URL in the browser and return the page's text content. "
        "Use this for dynamic/JS-rendered pages. For static pages, prefer web_fetch."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to navigate to.",
            },
            "wait_for": {
                "type": "string",
                "description": "Wait strategy: 'load', 'domcontentloaded', 'networkidle'. Default: 'load'.",
                "enum": ["load", "domcontentloaded", "networkidle"],
            },
        },
        "required": ["url"],
    },
}


CLICK_DEFINITION: dict = {
    "name": "browser_click",
    "description": (
        "Click an element on the current page by CSS selector. "
        "Returns the page text content after the click."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector of the element to click.",
            },
        },
        "required": ["selector"],
    },
}


TYPE_DEFINITION: dict = {
    "name": "browser_type",
    "description": (
        "Type text into an element on the current page. "
        "The element is identified by CSS selector."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector of the element to type into.",
            },
            "text": {
                "type": "string",
                "description": "The text to type.",
            },
            "press_enter": {
                "type": "boolean",
                "description": "Press Enter after typing. Default: false.",
            },
        },
        "required": ["selector", "text"],
    },
}


SNAPSHOT_DEFINITION: dict = {
    "name": "browser_snapshot",
    "description": (
        "Get the current page's accessibility snapshot — a structured text "
        "representation of visible page content. Lighter than a screenshot."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


SCREENSHOT_DEFINITION: dict = {
    "name": "browser_screenshot",
    "description": (
        "Take a screenshot of the current page. Returns the file path "
        "where the screenshot was saved."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to save the screenshot. Default: /tmp/browser_screenshot.png",
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture the full page (not just viewport). Default: false.",
            },
        },
    },
}


EVALUATE_DEFINITION: dict = {
    "name": "browser_evaluate",
    "description": (
        "Execute JavaScript in the current page context and return the result. "
        "Use for extracting data or interacting with page APIs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "JavaScript expression to evaluate.",
            },
        },
        "required": ["expression"],
    },
}


CLOSE_DEFINITION: dict = {
    "name": "browser_close",
    "description": "Close the browser and release resources.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def _handle_navigate(tool_input: dict) -> str:
    if not _playwright_available():
        return _NOT_INSTALLED

    url = tool_input.get("url", "")
    if not url:
        return "Error: 'url' is required."

    wait_for = tool_input.get("wait_for", "load")

    try:
        page = await _ensure_page()
        await page.goto(url, wait_until=wait_for, timeout=30000)
        title = await page.title()
        content = await page.inner_text("body")
        # Truncate to prevent context flooding
        if len(content) > 50000:
            content = content[:50000] + "\n\n... [truncated, 50K char limit]"
        return f"Page: {title}\nURL: {page.url}\n\n{content}"
    except Exception as e:
        return f"Browser navigation error: {type(e).__name__}: {e}"


async def _handle_click(tool_input: dict) -> str:
    if not _playwright_available():
        return _NOT_INSTALLED

    selector = tool_input.get("selector", "")
    if not selector:
        return "Error: 'selector' is required."

    try:
        page = await _ensure_page()
        await page.click(selector, timeout=10000)
        await page.wait_for_load_state("domcontentloaded")
        content = await page.inner_text("body")
        if len(content) > 50000:
            content = content[:50000] + "\n\n... [truncated]"
        return f"Clicked '{selector}'. Page content:\n\n{content}"
    except Exception as e:
        return f"Browser click error: {type(e).__name__}: {e}"


async def _handle_type(tool_input: dict) -> str:
    if not _playwright_available():
        return _NOT_INSTALLED

    selector = tool_input.get("selector", "")
    text = tool_input.get("text", "")
    press_enter = tool_input.get("press_enter", False)

    if not selector or not text:
        return "Error: 'selector' and 'text' are required."

    try:
        page = await _ensure_page()
        await page.fill(selector, text, timeout=10000)
        if press_enter:
            await page.press(selector, "Enter")
            await page.wait_for_load_state("domcontentloaded")
        return f"Typed '{text}' into '{selector}'" + (" and pressed Enter" if press_enter else "")
    except Exception as e:
        return f"Browser type error: {type(e).__name__}: {e}"


async def _handle_snapshot(tool_input: dict) -> str:
    if not _playwright_available():
        return _NOT_INSTALLED

    try:
        page = await _ensure_page()
        title = await page.title()
        url = page.url

        # Get accessibility tree snapshot
        snapshot = await page.accessibility.snapshot()
        if snapshot is None:
            # Fallback to inner_text
            content = await page.inner_text("body")
            if len(content) > 50000:
                content = content[:50000] + "\n\n... [truncated]"
            return f"Page: {title}\nURL: {url}\n\n{content}"

        # Format accessibility tree
        lines = [f"Page: {title}", f"URL: {url}", ""]
        _format_a11y_node(snapshot, lines, indent=0)
        result = "\n".join(lines)
        if len(result) > 50000:
            result = result[:50000] + "\n\n... [truncated]"
        return result
    except Exception as e:
        return f"Browser snapshot error: {type(e).__name__}: {e}"


def _format_a11y_node(node: dict, lines: list[str], indent: int) -> None:
    """Recursively format an accessibility tree node."""
    prefix = "  " * indent
    role = node.get("role", "")
    name = node.get("name", "")
    value = node.get("value", "")

    parts = []
    if role:
        parts.append(role)
    if name:
        parts.append(f'"{name}"')
    if value:
        parts.append(f"[{value}]")

    if parts:
        lines.append(f"{prefix}{' '.join(parts)}")

    for child in node.get("children", []):
        _format_a11y_node(child, lines, indent + 1)


async def _handle_screenshot(tool_input: dict) -> str:
    if not _playwright_available():
        return _NOT_INSTALLED

    path = tool_input.get("path", "/tmp/browser_screenshot.png")
    full_page = tool_input.get("full_page", False)

    try:
        page = await _ensure_page()
        await page.screenshot(path=path, full_page=full_page)
        return f"Screenshot saved to {path}"
    except Exception as e:
        return f"Browser screenshot error: {type(e).__name__}: {e}"


async def _handle_evaluate(tool_input: dict) -> str:
    if not _playwright_available():
        return _NOT_INSTALLED

    expression = tool_input.get("expression", "")
    if not expression:
        return "Error: 'expression' is required."

    try:
        page = await _ensure_page()
        result = await page.evaluate(expression)
        return str(result)
    except Exception as e:
        return f"Browser evaluate error: {type(e).__name__}: {e}"


async def _handle_close(tool_input: dict) -> str:
    await _close_browser()
    return "Browser closed."


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_browser_tools(registry: ToolRegistry) -> None:
    """Register all browser automation tools."""
    registry.register("browser_navigate", NAVIGATE_DEFINITION, _handle_navigate, timeout=60.0)
    registry.register("browser_click", CLICK_DEFINITION, _handle_click, timeout=30.0)
    registry.register("browser_type", TYPE_DEFINITION, _handle_type, timeout=15.0)
    registry.register("browser_snapshot", SNAPSHOT_DEFINITION, _handle_snapshot, timeout=30.0)
    registry.register("browser_screenshot", SCREENSHOT_DEFINITION, _handle_screenshot, timeout=30.0)
    registry.register("browser_evaluate", EVALUATE_DEFINITION, _handle_evaluate, timeout=15.0)
    registry.register("browser_close", CLOSE_DEFINITION, _handle_close)
