"""
Tests for browser automation tools (Playwright integration).

Tests mock Playwright internals to avoid requiring a real browser.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from aiciv_mind.tools.browser_tools import (
    NAVIGATE_DEFINITION,
    CLICK_DEFINITION,
    TYPE_DEFINITION,
    SNAPSHOT_DEFINITION,
    SCREENSHOT_DEFINITION,
    EVALUATE_DEFINITION,
    CLOSE_DEFINITION,
    _handle_navigate,
    _handle_click,
    _handle_type,
    _handle_snapshot,
    _handle_screenshot,
    _handle_evaluate,
    _handle_close,
    _format_a11y_node,
    register_browser_tools,
)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    def test_navigate_definition_has_required_fields(self):
        assert NAVIGATE_DEFINITION["name"] == "browser_navigate"
        assert "url" in NAVIGATE_DEFINITION["input_schema"]["properties"]
        assert "url" in NAVIGATE_DEFINITION["input_schema"]["required"]

    def test_click_definition_has_required_fields(self):
        assert CLICK_DEFINITION["name"] == "browser_click"
        assert "selector" in CLICK_DEFINITION["input_schema"]["properties"]
        assert "selector" in CLICK_DEFINITION["input_schema"]["required"]

    def test_type_definition_has_required_fields(self):
        assert TYPE_DEFINITION["name"] == "browser_type"
        assert "selector" in TYPE_DEFINITION["input_schema"]["properties"]
        assert "text" in TYPE_DEFINITION["input_schema"]["properties"]
        assert "selector" in TYPE_DEFINITION["input_schema"]["required"]
        assert "text" in TYPE_DEFINITION["input_schema"]["required"]

    def test_snapshot_definition(self):
        assert SNAPSHOT_DEFINITION["name"] == "browser_snapshot"

    def test_screenshot_definition(self):
        assert SCREENSHOT_DEFINITION["name"] == "browser_screenshot"

    def test_evaluate_definition(self):
        assert EVALUATE_DEFINITION["name"] == "browser_evaluate"
        assert "expression" in EVALUATE_DEFINITION["input_schema"]["required"]

    def test_close_definition(self):
        assert CLOSE_DEFINITION["name"] == "browser_close"

    def test_all_definitions_have_description(self):
        for defn in [
            NAVIGATE_DEFINITION, CLICK_DEFINITION, TYPE_DEFINITION,
            SNAPSHOT_DEFINITION, SCREENSHOT_DEFINITION, EVALUATE_DEFINITION,
            CLOSE_DEFINITION,
        ]:
            assert "description" in defn
            assert len(defn["description"]) > 10


# ---------------------------------------------------------------------------
# Accessibility tree formatting
# ---------------------------------------------------------------------------


class TestA11yFormatting:
    def test_format_simple_node(self):
        node = {"role": "button", "name": "Submit"}
        lines = []
        _format_a11y_node(node, lines, indent=0)
        assert lines == ['button "Submit"']

    def test_format_node_with_value(self):
        node = {"role": "textbox", "name": "Email", "value": "test@example.com"}
        lines = []
        _format_a11y_node(node, lines, indent=0)
        assert lines == ['textbox "Email" [test@example.com]']

    def test_format_nested_nodes(self):
        node = {
            "role": "navigation",
            "name": "Main",
            "children": [
                {"role": "link", "name": "Home"},
                {"role": "link", "name": "About"},
            ],
        }
        lines = []
        _format_a11y_node(node, lines, indent=0)
        assert len(lines) == 3
        assert lines[0] == 'navigation "Main"'
        assert lines[1] == '  link "Home"'
        assert lines[2] == '  link "About"'

    def test_format_empty_node(self):
        node = {}
        lines = []
        _format_a11y_node(node, lines, indent=0)
        assert lines == []  # No role, name, or value → nothing to add

    def test_format_role_only(self):
        node = {"role": "separator"}
        lines = []
        _format_a11y_node(node, lines, indent=0)
        assert lines == ["separator"]


# ---------------------------------------------------------------------------
# Handler tests (mocked Playwright)
# ---------------------------------------------------------------------------


def _make_mock_page(
    title: str = "Test Page",
    url: str = "https://example.com",
    body_text: str = "Hello World",
    a11y_snapshot: dict | None = None,
):
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.title = AsyncMock(return_value=title)
    page.url = url
    page.inner_text = AsyncMock(return_value=body_text)
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.press = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.screenshot = AsyncMock()
    page.evaluate = AsyncMock(return_value="eval_result")
    page.close = AsyncMock()
    page.is_closed = MagicMock(return_value=False)

    # Accessibility
    accessibility = AsyncMock()
    accessibility.snapshot = AsyncMock(return_value=a11y_snapshot)
    page.accessibility = accessibility

    return page


class TestNavigateHandler:
    @pytest.mark.asyncio
    async def test_navigate_success(self):
        mock_page = _make_mock_page(title="Example", body_text="Page content here")
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_navigate({"url": "https://example.com"})
        assert "Example" in result
        assert "Page content here" in result
        mock_page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_missing_url(self):
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True):
            result = await _handle_navigate({})
        assert "required" in result.lower()

    @pytest.mark.asyncio
    async def test_navigate_truncates_long_content(self):
        long_text = "x" * 60000
        mock_page = _make_mock_page(body_text=long_text)
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_navigate({"url": "https://example.com"})
        assert "truncated" in result
        assert len(result) < 55000

    @pytest.mark.asyncio
    async def test_navigate_not_installed(self):
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=False):
            result = await _handle_navigate({"url": "https://example.com"})
        assert "not installed" in result.lower()

    @pytest.mark.asyncio
    async def test_navigate_with_wait_for(self):
        mock_page = _make_mock_page()
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            await _handle_navigate({"url": "https://example.com", "wait_for": "networkidle"})
        mock_page.goto.assert_called_once_with(
            "https://example.com", wait_until="networkidle", timeout=30000
        )

    @pytest.mark.asyncio
    async def test_navigate_error_returns_message(self):
        mock_page = _make_mock_page()
        mock_page.goto.side_effect = Exception("Connection refused")
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_navigate({"url": "https://bad.example.com"})
        assert "error" in result.lower()
        assert "Connection refused" in result


class TestClickHandler:
    @pytest.mark.asyncio
    async def test_click_success(self):
        mock_page = _make_mock_page(body_text="Clicked page content")
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_click({"selector": "#submit-btn"})
        assert "Clicked" in result
        mock_page.click.assert_called_once_with("#submit-btn", timeout=10000)

    @pytest.mark.asyncio
    async def test_click_missing_selector(self):
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True):
            result = await _handle_click({})
        assert "required" in result.lower()


class TestTypeHandler:
    @pytest.mark.asyncio
    async def test_type_success(self):
        mock_page = _make_mock_page()
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_type({"selector": "#email", "text": "test@example.com"})
        assert "Typed" in result
        mock_page.fill.assert_called_once_with("#email", "test@example.com", timeout=10000)

    @pytest.mark.asyncio
    async def test_type_with_enter(self):
        mock_page = _make_mock_page()
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_type({
                "selector": "#search",
                "text": "query",
                "press_enter": True,
            })
        assert "Enter" in result
        mock_page.press.assert_called_once_with("#search", "Enter")

    @pytest.mark.asyncio
    async def test_type_missing_fields(self):
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True):
            result = await _handle_type({"selector": "#email"})
        assert "required" in result.lower()


class TestSnapshotHandler:
    @pytest.mark.asyncio
    async def test_snapshot_with_a11y_tree(self):
        a11y = {
            "role": "WebArea",
            "name": "Test Page",
            "children": [
                {"role": "heading", "name": "Welcome"},
                {"role": "button", "name": "Click me"},
            ],
        }
        mock_page = _make_mock_page(a11y_snapshot=a11y)
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_snapshot({})
        assert "Welcome" in result
        assert "Click me" in result

    @pytest.mark.asyncio
    async def test_snapshot_falls_back_to_text(self):
        mock_page = _make_mock_page(body_text="Fallback text content")
        mock_page.accessibility.snapshot = AsyncMock(return_value=None)
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_snapshot({})
        assert "Fallback text content" in result


class TestScreenshotHandler:
    @pytest.mark.asyncio
    async def test_screenshot_default_path(self):
        mock_page = _make_mock_page()
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_screenshot({})
        assert "/tmp/browser_screenshot.png" in result
        mock_page.screenshot.assert_called_once_with(
            path="/tmp/browser_screenshot.png", full_page=False
        )

    @pytest.mark.asyncio
    async def test_screenshot_custom_path(self):
        mock_page = _make_mock_page()
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_screenshot({"path": "/tmp/custom.png", "full_page": True})
        mock_page.screenshot.assert_called_once_with(
            path="/tmp/custom.png", full_page=True
        )


class TestEvaluateHandler:
    @pytest.mark.asyncio
    async def test_evaluate_success(self):
        mock_page = _make_mock_page()
        mock_page.evaluate = AsyncMock(return_value=42)
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True), \
             patch("aiciv_mind.tools.browser_tools._ensure_page", return_value=mock_page):
            result = await _handle_evaluate({"expression": "1 + 1"})
        assert "42" in result

    @pytest.mark.asyncio
    async def test_evaluate_missing_expression(self):
        with patch("aiciv_mind.tools.browser_tools._playwright_available", return_value=True):
            result = await _handle_evaluate({})
        assert "required" in result.lower()


class TestCloseHandler:
    @pytest.mark.asyncio
    async def test_close(self):
        with patch("aiciv_mind.tools.browser_tools._close_browser", new_callable=AsyncMock) as mock_close:
            result = await _handle_close({})
        assert "closed" in result.lower()
        mock_close.assert_called_once()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_browser_tools(self):
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        register_browser_tools(registry)
        names = registry.names()
        assert "browser_navigate" in names
        assert "browser_click" in names
        assert "browser_type" in names
        assert "browser_snapshot" in names
        assert "browser_screenshot" in names
        assert "browser_evaluate" in names
        assert "browser_close" in names

    def test_browser_tools_count(self):
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        register_browser_tools(registry)
        browser_tools = [n for n in registry.names() if n.startswith("browser_")]
        assert len(browser_tools) == 7

    def test_navigate_has_long_timeout(self):
        from aiciv_mind.tools import ToolRegistry
        registry = ToolRegistry()
        register_browser_tools(registry)
        # Navigate should have a longer timeout than default
        timeout = registry._timeouts.get("browser_navigate", 15.0)
        assert timeout >= 60.0
