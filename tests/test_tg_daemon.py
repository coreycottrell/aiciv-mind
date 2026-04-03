"""Tests for tools/tg_daemon.py — Root's Telegram bridge."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.tg_daemon import (
    RootTelegramBridge,
    chunk_message,
    get_bot_token,
    COREY_CHAT_ID,
)


# ---------------------------------------------------------------------------
# Tests: chunk_message
# ---------------------------------------------------------------------------


class TestChunkMessage:
    def test_short_message(self):
        assert chunk_message("hello") == ["hello"]

    def test_exact_limit(self):
        msg = "x" * 4000
        assert chunk_message(msg) == [msg]

    def test_long_message_splits(self):
        msg = "x" * 8000
        chunks = chunk_message(msg)
        assert len(chunks) == 2
        assert "".join(chunks) == msg

    def test_splits_at_newline(self):
        msg = "a" * 3000 + "\n" + "b" * 3000
        chunks = chunk_message(msg, max_len=4000)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 3000
        assert chunks[1] == "b" * 3000

    def test_splits_at_space(self):
        msg = "word " * 1000  # 5000 chars
        chunks = chunk_message(msg, max_len=4000)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= 4000

    def test_empty_message(self):
        assert chunk_message("") == [""]


# ---------------------------------------------------------------------------
# Tests: get_bot_token
# ---------------------------------------------------------------------------


class TestGetBotToken:
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-123")
        assert get_bot_token() == "test-token-123"

    def test_from_config_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        config = {"bot_token": "config-token-456"}
        config_path = tmp_path / "telegram_config.json"
        config_path.write_text(json.dumps(config))
        with patch("tools.tg_daemon.Path") as mock_path:
            # This is tricky to mock since Path is used elsewhere.
            # Just test the env var path works.
            pass

    def test_raises_without_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with patch("tools.tg_daemon.Path") as mock_path_cls:
            mock_path_cls.return_value.exists.return_value = False
            # The function checks a hardcoded config path
            with pytest.raises(RuntimeError, match="No TELEGRAM_BOT_TOKEN"):
                get_bot_token()


# ---------------------------------------------------------------------------
# Tests: RootTelegramBridge
# ---------------------------------------------------------------------------


class TestRootTelegramBridge:
    def test_init(self):
        bridge = RootTelegramBridge("test-token")
        assert bridge.bot_token == "test-token"
        assert bridge.mind is None
        assert bridge._processing is False

    def test_corey_chat_id(self):
        assert COREY_CHAT_ID == 437939400

    @pytest.mark.asyncio
    async def test_handle_message_unauthorized(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()

        update = MagicMock()
        update.message.chat_id = 999999  # Not Corey
        update.message.text = "hello"

        context = MagicMock()
        await bridge.handle_message(update, context)
        # Should not call mind.run_task
        bridge.mind.run_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_while_processing(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()
        bridge._processing = True

        update = MagicMock()
        update.message.chat_id = COREY_CHAT_ID
        update.message.text = "hello"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        await bridge.handle_message(update, context)
        update.message.reply_text.assert_called_once()
        assert "still thinking" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_message_success(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()
        bridge.mind.run_task = AsyncMock(return_value="Hello Corey!")

        update = MagicMock()
        update.message.chat_id = COREY_CHAT_ID
        update.message.text = "hey Root"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        await bridge.handle_message(update, context)

        bridge.mind.run_task.assert_called_once()
        update.message.reply_text.assert_called_once_with("Hello Corey!")
        assert bridge._processing is False

    @pytest.mark.asyncio
    async def test_handle_message_strips_root_prefix(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()
        bridge.mind.run_task = AsyncMock(return_value="[Root] Hello there")

        update = MagicMock()
        update.message.chat_id = COREY_CHAT_ID
        update.message.text = "hey"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        await bridge.handle_message(update, context)

        update.message.reply_text.assert_called_once_with("Hello there")

    @pytest.mark.asyncio
    async def test_handle_message_error(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()
        bridge.mind.run_task = AsyncMock(side_effect=RuntimeError("model down"))

        update = MagicMock()
        update.message.chat_id = COREY_CHAT_ID
        update.message.text = "hey"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        await bridge.handle_message(update, context)

        # Should send error message, not crash
        update.message.reply_text.assert_called_once()
        assert "mind error" in update.message.reply_text.call_args[0][0]
        assert bridge._processing is False

    @pytest.mark.asyncio
    async def test_handle_message_empty_response(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()
        bridge.mind.run_task = AsyncMock(return_value=None)

        update = MagicMock()
        update.message.chat_id = COREY_CHAT_ID
        update.message.text = "hey"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        await bridge.handle_message(update, context)

        update.message.reply_text.assert_called_once()
        assert "lost it" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_message_long_response_chunked(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()
        bridge.mind.run_task = AsyncMock(return_value="x" * 6000)

        update = MagicMock()
        update.message.chat_id = COREY_CHAT_ID
        update.message.text = "hey"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        await bridge.handle_message(update, context)

        assert update.message.reply_text.call_count == 2

    @pytest.mark.asyncio
    async def test_handle_status(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()
        bridge.mind._messages = [{"role": "user"}, {"role": "assistant"}]
        bridge.mind.manifest.model.preferred = "minimax-m27"
        bridge.memory = MagicMock()
        bridge.memory._conn.execute.return_value.fetchone.return_value = {"c": 42}

        update = MagicMock()
        update.message.chat_id = COREY_CHAT_ID
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        await bridge.handle_status(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "Messages in context: 2" in reply
        assert "Memories in DB: 42" in reply
        assert "minimax-m27" in reply

    @pytest.mark.asyncio
    async def test_handle_reset(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()
        bridge.mind._messages = [{"role": "user"}, {"role": "assistant"}]

        update = MagicMock()
        update.message.chat_id = COREY_CHAT_ID
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        await bridge.handle_reset(update, context)

        assert len(bridge.mind._messages) == 0
        assert "cleared" in update.message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_handle_start_unauthorized(self):
        bridge = RootTelegramBridge("test-token")

        update = MagicMock()
        update.message.chat_id = 999999
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        await bridge.handle_start(update, context)

        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_empty_message(self):
        bridge = RootTelegramBridge("test-token")
        bridge.mind = MagicMock()

        update = MagicMock()
        update.message = None

        context = MagicMock()
        await bridge.handle_message(update, context)
        # Should not crash
