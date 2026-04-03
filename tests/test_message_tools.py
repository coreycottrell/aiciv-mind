"""
Tests for aiciv_mind.tools.message_tools — Inter-mind messaging.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiciv_mind.tools import ToolRegistry
from aiciv_mind.tools.message_tools import register_message_tools


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.send = AsyncMock()
    return bus


@pytest.fixture
def registry(mock_bus):
    reg = ToolRegistry()
    register_message_tools(reg, bus=mock_bus, sender_id="primary")
    return reg


class TestSendMessage:
    def test_send_status(self, registry, mock_bus):
        result = asyncio.run(registry.execute("send_message", {
            "to": "research-lead",
            "content": "Start working on paper analysis",
        }))
        assert "Message sent" in result
        assert "research-lead" in result
        mock_bus.send.assert_called_once()

    def test_send_directive(self, registry, mock_bus):
        result = asyncio.run(registry.execute("send_message", {
            "to": "coder-lead",
            "content": "Implement auth module",
            "message_type": "directive",
        }))
        assert "directive" in result
        assert "coder-lead" in result

    def test_send_question(self, registry, mock_bus):
        result = asyncio.run(registry.execute("send_message", {
            "to": "research-lead",
            "content": "What did you find?",
            "message_type": "question",
        }))
        assert "question" in result

    def test_send_result(self, registry, mock_bus):
        result = asyncio.run(registry.execute("send_message", {
            "to": "primary",
            "content": "Analysis complete: 5 papers found",
            "message_type": "result",
        }))
        assert "result" in result

    def test_missing_to(self, registry):
        result = asyncio.run(registry.execute("send_message", {
            "content": "Hello",
        }))
        assert "ERROR" in result

    def test_missing_content(self, registry):
        result = asyncio.run(registry.execute("send_message", {
            "to": "someone",
        }))
        assert "ERROR" in result

    def test_invalid_message_type(self, registry):
        result = asyncio.run(registry.execute("send_message", {
            "to": "someone",
            "content": "Hello",
            "message_type": "invalid",
        }))
        assert "ERROR" in result

    def test_long_content_truncated_in_response(self, registry, mock_bus):
        long_content = "x" * 200
        result = asyncio.run(registry.execute("send_message", {
            "to": "someone",
            "content": long_content,
        }))
        assert "..." in result  # Truncated in confirmation
        mock_bus.send.assert_called_once()


class TestRegistration:
    def test_registered(self, registry):
        assert "send_message" in registry.names()

    def test_not_read_only(self, registry):
        assert registry.is_read_only("send_message") is False

    def test_survives_primary_filter(self, mock_bus):
        from aiciv_mind.roles import Role
        reg = ToolRegistry()
        register_message_tools(reg, bus=mock_bus, sender_id="primary")
        filtered = reg.filter_by_role(Role.PRIMARY)
        assert "send_message" in filtered.names()

    def test_survives_team_lead_filter(self, mock_bus):
        from aiciv_mind.roles import Role
        reg = ToolRegistry()
        register_message_tools(reg, bus=mock_bus, sender_id="tl")
        filtered = reg.filter_by_role(Role.TEAM_LEAD)
        assert "send_message" in filtered.names()
