"""
Tests for aiciv_mind.Mind — anthropic SDK tool-use loop via LiteLLM proxy.

Uses unittest.mock to avoid any live API calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiciv_mind.manifest import MindManifest, ModelConfig, AuthConfig, MemoryConfig
from aiciv_mind.memory import MemoryStore
from aiciv_mind.mind import Mind


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_manifest():
    """Minimal manifest — in-memory db, no auto memory search."""
    return MindManifest(
        mind_id="test-mind",
        display_name="Test Mind",
        role="worker",
        system_prompt="You are a test agent.",
        model=ModelConfig(preferred="ollama/qwen2.5-coder:14b"),
        auth=AuthConfig(civ_id="acg", keypair_path="/tmp/test.json"),
        memory=MemoryConfig(db_path=":memory:", auto_search_before_task=False),
    )


@pytest.fixture
def memory_store():
    store = MemoryStore(":memory:")
    yield store
    store.close()


# ---------------------------------------------------------------------------
# Helpers — build mock anthropic responses
# ---------------------------------------------------------------------------


def make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def make_tool_use_block(tool_id: str, name: str, input_dict: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_dict
    return block


def make_response(text=None, tool_blocks=None, stop_reason="end_turn") -> MagicMock:
    """Build a mock anthropic messages.create() response."""
    content = []
    if text is not None:
        content.append(make_text_block(text))
    if tool_blocks:
        content.extend(tool_blocks)

    resp = MagicMock()
    resp.content = content
    resp.stop_reason = stop_reason
    return resp


# ---------------------------------------------------------------------------
# Tests: basic loop
# ---------------------------------------------------------------------------


async def test_run_task_no_tools_returns_text(minimal_manifest, memory_store):
    """When model returns no tool_use blocks, run_task returns the text content."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    with patch.object(
        mind._client.messages, "create", new_callable=AsyncMock,
        return_value=make_response(text="Hello world!"),
    ):
        result = await mind.run_task("Say hello", inject_memories=False)

    assert result == "Hello world!"


async def test_run_task_single_tool_call(minimal_manifest, memory_store):
    """Model calls one tool, gets result, then returns final text."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    tc = make_tool_use_block("call_001", "bash", {"command": "echo hi"})
    first = make_response(tool_blocks=[tc], stop_reason="tool_use")
    second = make_response(text="Done.")

    with patch.object(
        mind._client.messages, "create", new_callable=AsyncMock,
        side_effect=[first, second],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="hi\n"
        ) as mock_exec:
            result = await mind.run_task("Echo hi", inject_memories=False)

    assert result == "Done."
    assert mock_exec.call_count == 1
    mock_exec.assert_called_once_with("bash", {"command": "echo hi"})


async def test_tool_result_appended_as_tool_result_block(minimal_manifest, memory_store):
    """Tool results go back as role=user with type=tool_result content blocks."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    tc = make_tool_use_block("call_xyz", "bash", {"command": "ls"})
    first = make_response(tool_blocks=[tc], stop_reason="tool_use")
    second = make_response(text="Listed.")

    with patch.object(
        mind._client.messages, "create", new_callable=AsyncMock,
        side_effect=[first, second],
    ):
        with patch.object(mind._tools, "execute", new_callable=AsyncMock, return_value="a.txt"):
            await mind.run_task("List files", inject_memories=False)

    # Find the user message that contains tool_result
    tool_result_msgs = [
        m for m in mind._messages
        if m.get("role") == "user" and isinstance(m.get("content"), list)
    ]
    assert len(tool_result_msgs) == 1
    result_block = tool_result_msgs[0]["content"][0]
    assert result_block["type"] == "tool_result"
    assert result_block["tool_use_id"] == "call_xyz"
    assert result_block["content"] == "a.txt"


async def test_system_prompt_passed_to_api(minimal_manifest, memory_store):
    """System prompt from manifest is passed as the system= kwarg."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        return make_response(text="ok")

    with patch.object(mind._client.messages, "create", new_callable=AsyncMock, side_effect=capture):
        await mind.run_task("test", inject_memories=False)

    assert "system" in captured[0]
    assert "test agent" in captured[0]["system"]


async def test_model_name_from_manifest(minimal_manifest, memory_store):
    """The model name from the manifest is passed to the API call."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        return make_response(text="ok")

    with patch.object(mind._client.messages, "create", new_callable=AsyncMock, side_effect=capture):
        await mind.run_task("test", inject_memories=False)

    assert captured[0]["model"] == "ollama/qwen2.5-coder:14b"


async def test_multiple_tool_calls_all_executed(minimal_manifest, memory_store):
    """All tool_use blocks in one response are executed before the next API call."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    tc1 = make_tool_use_block("c1", "bash", {"command": "echo a"})
    tc2 = make_tool_use_block("c2", "bash", {"command": "echo b"})
    first = make_response(tool_blocks=[tc1, tc2], stop_reason="tool_use")
    second = make_response(text="Both done.")

    with patch.object(
        mind._client.messages, "create", new_callable=AsyncMock,
        side_effect=[first, second],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="out"
        ) as mock_exec:
            await mind.run_task("Run both", inject_memories=False)

    assert mock_exec.call_count == 2


async def test_clear_history_empties_messages(minimal_manifest, memory_store):
    """clear_history() resets the message list."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    mind._messages = [{"role": "user", "content": "hello"}]
    mind.clear_history()
    assert mind._messages == []


async def test_stop_exits_loop_early(minimal_manifest, memory_store):
    """stop() causes the tool loop to exit after the current iteration."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    tc = make_tool_use_block("c1", "bash", {"command": "echo loop"})
    loop_response = make_response(tool_blocks=[tc], stop_reason="tool_use")

    call_count = 0

    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        mind.stop()
        return loop_response

    with patch.object(mind._client.messages, "create", new_callable=AsyncMock, side_effect=mock_create):
        with patch.object(mind._tools, "execute", new_callable=AsyncMock, return_value="out"):
            await mind.run_task("loop task", inject_memories=False)

    assert call_count == 1


# ---------------------------------------------------------------------------
# Tests: tool format
# ---------------------------------------------------------------------------


def test_build_anthropic_tools_format(minimal_manifest, memory_store):
    """build_anthropic_tools returns Anthropic-format definitions."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    tools = mind._tools.build_anthropic_tools(enabled=["bash"])

    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == "bash"
    assert "description" in tool
    assert "input_schema" in tool
    assert tool["input_schema"]["type"] == "object"


def test_build_openai_tools_format(minimal_manifest, memory_store):
    """build_openai_tools wraps each tool in OpenAI function format."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    tools = mind._tools.build_openai_tools(enabled=["bash"])

    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert "function" in tools[0]
    assert tools[0]["function"]["name"] == "bash"
    assert "parameters" in tools[0]["function"]


# ---------------------------------------------------------------------------
# Tests: LiteLLM proxy config
# ---------------------------------------------------------------------------


def test_client_uses_env_api_url(minimal_manifest, memory_store, monkeypatch):
    """MIND_API_URL env var sets the client base_url."""
    monkeypatch.setenv("MIND_API_URL", "http://custom-proxy:9000")
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    assert "custom-proxy:9000" in str(mind._client.base_url)


async def test_run_task_empty_response(minimal_manifest, memory_store):
    """If model returns empty content, run_task returns empty string."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    with patch.object(
        mind._client.messages, "create", new_callable=AsyncMock,
        return_value=make_response(),  # no text, no tools
    ):
        result = await mind.run_task("Do nothing", inject_memories=False)

    assert result == ""
