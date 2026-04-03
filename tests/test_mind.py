"""
Tests for aiciv_mind.Mind — anthropic SDK tool-use loop via LiteLLM proxy.

Uses unittest.mock to avoid any live API calls.
"""

from __future__ import annotations

import asyncio
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


def make_stream_ctx(response: MagicMock) -> MagicMock:
    """Wrap a response in an async context manager mimicking messages.stream()."""
    stream = AsyncMock()
    stream.get_final_message = AsyncMock(return_value=response)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=stream)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Tests: basic loop
# ---------------------------------------------------------------------------


async def test_run_task_no_tools_returns_text(minimal_manifest, memory_store):
    """When model returns no tool_use blocks, run_task returns the text content."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    with patch.object(
        mind._client.messages, "stream",
        return_value=make_stream_ctx(make_response(text="Hello world!")),
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
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
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
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
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

    def capture(**kwargs):
        captured.append(kwargs)
        return make_stream_ctx(make_response(text="ok"))

    with patch.object(mind._client.messages, "stream", side_effect=capture):
        await mind.run_task("test", inject_memories=False)

    assert "system" in captured[0]
    assert "test agent" in captured[0]["system"]


async def test_model_name_from_manifest(minimal_manifest, memory_store):
    """The model name from the manifest is passed to the API call."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    captured = []

    def capture(**kwargs):
        captured.append(kwargs)
        return make_stream_ctx(make_response(text="ok"))

    with patch.object(mind._client.messages, "stream", side_effect=capture):
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
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
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

    def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        mind.stop()
        return make_stream_ctx(loop_response)

    with patch.object(mind._client.messages, "stream", side_effect=mock_create):
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
        mind._client.messages, "stream",
        return_value=make_stream_ctx(make_response()),  # no text, no tools
    ):
        result = await mind.run_task("Do nothing", inject_memories=False)

    assert result == ""


# ---------------------------------------------------------------------------
# Tests: cache_stats property
# ---------------------------------------------------------------------------


def test_cache_stats_initial_state(minimal_manifest, memory_store):
    """cache_stats starts with all zeros."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    stats = mind.cache_stats

    assert stats["cache_hits"] == 0
    assert stats["cache_writes"] == 0
    assert stats["cached_tokens"] == 0
    assert stats["total_input_tokens"] == 0
    assert stats["hit_rate"] == 0.0


def test_cache_stats_correct_keys(minimal_manifest, memory_store):
    """cache_stats returns a dict with the expected keys."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    stats = mind.cache_stats

    expected_keys = {"cache_hits", "cache_writes", "cached_tokens", "total_input_tokens", "hit_rate"}
    assert set(stats.keys()) == expected_keys


def test_cache_stats_accumulates_hits(minimal_manifest, memory_store):
    """_log_cache_stats accumulates cache hits across multiple calls."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    # Simulate two responses with cache hits
    for cached_tokens in [500, 300]:
        resp = MagicMock()
        usage = MagicMock()
        usage.cache_read_input_tokens = cached_tokens
        usage.cache_creation_input_tokens = 0
        usage.input_tokens = 100
        resp.usage = usage
        mind._log_cache_stats(resp)

    stats = mind.cache_stats
    assert stats["cache_hits"] == 2
    assert stats["cached_tokens"] == 800  # 500 + 300
    assert stats["total_input_tokens"] == 1000  # (100+500) + (100+300)
    assert stats["hit_rate"] == 1.0  # 2 hits / 2 total calls


def test_cache_stats_accumulates_writes(minimal_manifest, memory_store):
    """_log_cache_stats accumulates cache writes."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    resp = MagicMock()
    usage = MagicMock()
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 200
    usage.input_tokens = 150
    resp.usage = usage
    mind._log_cache_stats(resp)

    stats = mind.cache_stats
    assert stats["cache_writes"] == 1
    assert stats["cache_hits"] == 0
    assert stats["total_input_tokens"] == 350  # 150 + 200
    assert stats["hit_rate"] == 0.0  # 0 hits / 1 total call


def test_cache_stats_mixed_hits_and_writes(minimal_manifest, memory_store):
    """hit_rate correctly reflects mix of cache hits and writes."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    # One cache write
    resp_write = MagicMock()
    usage_w = MagicMock()
    usage_w.cache_read_input_tokens = 0
    usage_w.cache_creation_input_tokens = 100
    usage_w.input_tokens = 50
    resp_write.usage = usage_w
    mind._log_cache_stats(resp_write)

    # Two cache hits
    for _ in range(2):
        resp_hit = MagicMock()
        usage_h = MagicMock()
        usage_h.cache_read_input_tokens = 200
        usage_h.cache_creation_input_tokens = 0
        usage_h.input_tokens = 50
        resp_hit.usage = usage_h
        mind._log_cache_stats(resp_hit)

    stats = mind.cache_stats
    assert stats["cache_hits"] == 2
    assert stats["cache_writes"] == 1
    assert stats["hit_rate"] == round(2 / 3, 2)  # 0.67


# ---------------------------------------------------------------------------
# Tests: Ollama stop_reason fix — native tool_use blocks with end_turn
# ---------------------------------------------------------------------------


async def test_native_tool_use_with_end_turn_still_executes(minimal_manifest, memory_store):
    """
    CRITICAL FIX: Ollama/LiteLLM returns native tool_use blocks but sets
    stop_reason='end_turn' (not 'tool_use'). Tools must still execute.

    Previously, the check `if not synthetic_calls and stop_reason == 'end_turn': break`
    caused all native tool calls from Ollama-backed models to be silently skipped.
    """
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    tc = make_tool_use_block("call_ollama_1", "bash", {"command": "echo hi"})
    # Ollama pattern: tool_use blocks present BUT stop_reason is "end_turn"
    first = make_response(
        text="I'll run the command now.",
        tool_blocks=[tc],
        stop_reason="end_turn",  # THE BUG: Ollama doesn't set "tool_use"
    )
    second = make_response(text="Done.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="hi\n"
        ) as mock_exec:
            result = await mind.run_task("Echo hi", inject_memories=False)

    assert result == "Done."
    assert mock_exec.call_count == 1
    mock_exec.assert_called_once_with("bash", {"command": "echo hi"})


async def test_native_tool_use_with_stop_reason_executes(minimal_manifest, memory_store):
    """
    Ollama may also return stop_reason='stop' (mapped differently by LiteLLM versions).
    Tool_use blocks should execute regardless of any stop_reason value.
    """
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    tc = make_tool_use_block("call_stop_1", "bash", {"command": "ls"})
    first = make_response(tool_blocks=[tc], stop_reason="stop")
    second = make_response(text="Listed.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="a.txt"
        ) as mock_exec:
            result = await mind.run_task("List", inject_memories=False)

    assert result == "Listed."
    assert mock_exec.call_count == 1


async def test_native_text_plus_tool_use_end_turn_executes(minimal_manifest, memory_store):
    """
    Combined text + native tool_use with end_turn: text should be captured,
    tool should execute, and final_text should be from the last iteration.
    """
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    tc = make_tool_use_block("call_mix_1", "memory_search", {"query": "recent"})
    first = make_response(
        text="Let me search my memories.",
        tool_blocks=[tc],
        stop_reason="end_turn",
    )
    second = make_response(text="I found 3 relevant memories.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock,
            return_value="memory 1: test learning",
        ) as mock_exec:
            result = await mind.run_task("Search memories", inject_memories=False)

    assert result == "I found 3 relevant memories."
    mock_exec.assert_called_once_with("memory_search", {"query": "recent"})


async def test_multiple_native_tools_end_turn_all_execute(minimal_manifest, memory_store):
    """Multiple native tool blocks with end_turn: ALL tools execute."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    tc1 = make_tool_use_block("c1", "bash", {"command": "echo a"})
    tc2 = make_tool_use_block("c2", "bash", {"command": "echo b"})
    first = make_response(tool_blocks=[tc1, tc2], stop_reason="end_turn")
    second = make_response(text="Both done.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="out"
        ) as mock_exec:
            result = await mind.run_task("Run both", inject_memories=False)

    assert result == "Both done."
    assert mock_exec.call_count == 2


async def test_no_tool_use_end_turn_breaks_correctly(minimal_manifest, memory_store):
    """When there are NO tool_use blocks and stop_reason is end_turn, the loop breaks
    correctly (this is the normal end-of-conversation case)."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    with patch.object(
        mind._client.messages, "stream",
        return_value=make_stream_ctx(make_response(text="All done!", stop_reason="end_turn")),
    ):
        result = await mind.run_task("Just chat", inject_memories=False)

    assert result == "All done!"


async def test_synthetic_tool_calls_still_work(minimal_manifest, memory_store):
    """Synthetic (text-parsed) tool calls continue to work after the fix."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    # Model emits tool call as text (no native tool_use blocks)
    xml_text = (
        'I\'ll check.\n'
        '<invoke name="bash">\n'
        '<parameter name="command">echo hello</parameter>\n'
        '</invoke>'
    )
    first = make_response(text=xml_text, stop_reason="end_turn")
    second = make_response(text="Got it: hello")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="hello"
        ) as mock_exec:
            result = await mind.run_task("Say hello", inject_memories=False)

    assert result == "Got it: hello"
    assert mock_exec.call_count == 1
    mock_exec.assert_called_once_with("bash", {"command": "echo hello"})


# ---------------------------------------------------------------------------
# Tests: text-embedded tool call parsing variations
# ---------------------------------------------------------------------------


async def test_json_format_tool_call_parsing(minimal_manifest, memory_store):
    """JSON format: {"name": "tool", "arguments": {...}} embedded in text."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    json_text = (
        'Let me check.\n'
        '{"name": "bash", "arguments": {"command": "pwd"}}\n'
    )
    first = make_response(text=json_text, stop_reason="end_turn")
    second = make_response(text="/home/corey/projects")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="/home/corey"
        ) as mock_exec:
            result = await mind.run_task("Where am I?", inject_memories=False)

    assert mock_exec.call_count == 1
    mock_exec.assert_called_once_with("bash", {"command": "pwd"})


async def test_openai_function_format_parsing(minimal_manifest, memory_store):
    """OpenAI format: {"type": "function", "function": {"name": ..., "parameters": ...}}."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    func_text = (
        '{"type": "function", "function": '
        '{"name": "bash", "parameters": {"command": "ls"}}}'
    )
    first = make_response(text=func_text, stop_reason="end_turn")
    second = make_response(text="Files listed.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="a.py"
        ) as mock_exec:
            result = await mind.run_task("List files", inject_memories=False)

    assert mock_exec.call_count == 1
    mock_exec.assert_called_once_with("bash", {"command": "ls"})


async def test_case_insensitive_tool_name_parsing(minimal_manifest, memory_store):
    """Tool names should normalize: Bash → bash, Memory_Search → memory_search."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    json_text = '{"name": "Bash", "arguments": {"command": "echo test"}}'
    first = make_response(text=json_text, stop_reason="end_turn")
    second = make_response(text="test")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="test"
        ) as mock_exec:
            result = await mind.run_task("Test", inject_memories=False)

    assert mock_exec.call_count == 1
    # Should be normalized to "bash"
    mock_exec.assert_called_once_with("bash", {"command": "echo test"})


async def test_tool_call_block_format_parsing(minimal_manifest, memory_store):
    """[TOOL_CALL]...[/TOOL_CALL] format used by M2.7."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    tc_text = (
        'I will check.\n'
        '[TOOL_CALL]\n'
        'tool => "bash"\n'
        'args => {"command": "date"}\n'
        '[/TOOL_CALL]'
    )
    first = make_response(text=tc_text, stop_reason="end_turn")
    second = make_response(text="Today is Wednesday.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="Wed Apr 2"
        ) as mock_exec:
            result = await mind.run_task("What day?", inject_memories=False)

    assert mock_exec.call_count == 1
    mock_exec.assert_called_once_with("bash", {"command": "date"})


async def test_xml_invoke_with_wrapper_parsing(minimal_manifest, memory_store):
    """<minimax:tool_call><invoke name="...">...</invoke></minimax:tool_call> format."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    xml_text = (
        '<minimax:tool_call>'
        '<invoke name="bash">\n'
        '<parameter name="command">whoami</parameter>\n'
        '</invoke>'
        '</minimax:tool_call>'
    )
    first = make_response(text=xml_text, stop_reason="end_turn")
    second = make_response(text="You are root.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="corey"
        ) as mock_exec:
            result = await mind.run_task("Who am I?", inject_memories=False)

    assert mock_exec.call_count == 1
    mock_exec.assert_called_once_with("bash", {"command": "whoami"})


async def test_minimax_json_array_tool_call_parsing(minimal_manifest, memory_store):
    """<minimax:tool_call>[{"tool": "bash", "arguments": {...}}]</minimax:tool_call> format.

    MiniMax M2.7 via Ollama Cloud often emits tool calls as a JSON array
    inside <minimax:tool_call> tags, using "tool" key instead of "name".
    """
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    json_array_text = (
        '<minimax:tool_call>\n'
        '[\n'
        '  {\n'
        '    "tool": "bash",\n'
        '    "arguments": {\n'
        '      "command": "echo hello"\n'
        '    }\n'
        '  }\n'
        ']\n'
        '</minimax:tool_call>'
    )
    first = make_response(text=json_array_text, stop_reason="end_turn")
    second = make_response(text="Output: hello")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="hello"
        ) as mock_exec:
            result = await mind.run_task("Echo test", inject_memories=False)

    assert mock_exec.call_count == 1
    mock_exec.assert_called_once_with("bash", {"command": "echo hello"})


async def test_minimax_json_array_with_args_key(minimal_manifest, memory_store):
    """MiniMax sometimes uses "args" instead of "arguments"."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    text = '{"tool": "bash", "args": {"command": "ls"}}'
    first = make_response(text=text, stop_reason="end_turn")
    second = make_response(text="Listed files.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="file1.py"
        ) as mock_exec:
            result = await mind.run_task("List files", inject_memories=False)

    assert mock_exec.call_count == 1
    mock_exec.assert_called_once_with("bash", {"command": "ls"})


async def test_unrecognized_tool_name_ignored(minimal_manifest, memory_store):
    """Tool calls with names not in the registry are silently ignored."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    json_text = '{"name": "nonexistent_tool", "arguments": {"x": 1}}'
    first = make_response(text=json_text, stop_reason="end_turn")

    with patch.object(
        mind._client.messages, "stream",
        return_value=make_stream_ctx(first),
    ):
        # Should NOT crash — unrecognized tool names are skipped
        result = await mind.run_task("Try bad tool", inject_memories=False)

    # No tool_use blocks found → loop breaks → returns whatever text was there
    assert isinstance(result, str)


async def test_synthetic_result_injected_as_user_text(minimal_manifest, memory_store):
    """When synthetic tool calls execute, results are injected as plain text
    user messages (not tool_result blocks)."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    xml_text = (
        '<invoke name="bash">\n'
        '<parameter name="command">echo ok</parameter>\n'
        '</invoke>'
    )
    first = make_response(text=xml_text, stop_reason="end_turn")
    second = make_response(text="Done.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        with patch.object(
            mind._tools, "execute", new_callable=AsyncMock, return_value="ok"
        ):
            await mind.run_task("Test", inject_memories=False)

    # Find the user message with tool result text
    text_results = [
        m for m in mind._messages
        if m.get("role") == "user" and isinstance(m.get("content"), str)
        and "[Tool result:" in m["content"]
    ]
    assert len(text_results) == 1
    assert "[Tool result: bash]" in text_results[0]["content"]
    assert "ok" in text_results[0]["content"]


# ---------------------------------------------------------------------------
# Tests: read-only vs write tool execution ordering
# ---------------------------------------------------------------------------


async def test_read_only_tools_can_run_concurrently(minimal_manifest, memory_store):
    """Read-only tools should be executed concurrently (via asyncio.gather)."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    # Register two read-only tools
    mind._tools.register(
        "ro_tool_a",
        {"name": "ro_tool_a", "description": "Read A", "input_schema": {"type": "object", "properties": {}}},
        lambda x: "a_result",
        read_only=True,
    )
    mind._tools.register(
        "ro_tool_b",
        {"name": "ro_tool_b", "description": "Read B", "input_schema": {"type": "object", "properties": {}}},
        lambda x: "b_result",
        read_only=True,
    )

    tc1 = make_tool_use_block("c1", "ro_tool_a", {})
    tc2 = make_tool_use_block("c2", "ro_tool_b", {})
    first = make_response(tool_blocks=[tc1, tc2], stop_reason="tool_use")
    second = make_response(text="Both done.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        result = await mind.run_task("Read both", inject_memories=False)

    assert result == "Both done."
    # Both results should be in the tool_result message
    result_msgs = [
        m for m in mind._messages
        if m.get("role") == "user" and isinstance(m.get("content"), list)
    ]
    assert len(result_msgs) == 1
    contents = [r["content"] for r in result_msgs[0]["content"]]
    assert "a_result" in contents
    assert "b_result" in contents


# ---------------------------------------------------------------------------
# Tests: model call timeout
# ---------------------------------------------------------------------------


async def test_model_call_timeout_raises(memory_store):
    """When model call exceeds call_timeout_s, TimeoutError propagates
    (the daemon handler decides retry/skip — not the mind loop)."""
    manifest = MindManifest(
        mind_id="timeout-test",
        display_name="Timeout Test Mind",
        role="worker",
        system_prompt="You are a test agent.",
        model=ModelConfig(preferred="ollama/test", call_timeout_s=0.1),
        auth=AuthConfig(civ_id="acg", keypair_path="/tmp/test.json"),
        memory=MemoryConfig(db_path=":memory:", auto_search_before_task=False),
    )
    mind = Mind(manifest=manifest, memory=memory_store)

    class SlowCtx:
        async def __aenter__(self):
            await asyncio.sleep(5)  # Way longer than 0.1s timeout
        async def __aexit__(self, *a):
            pass

    def slow_stream(**kwargs):
        return SlowCtx()

    with patch.object(
        mind._client.messages, "stream", side_effect=slow_stream,
    ):
        with pytest.raises(TimeoutError):
            await mind.run_task("Do something slow", inject_memories=False)

    # After timeout: orphaned user message was popped (no alternation corruption)
    if mind._messages:
        assert mind._messages[-1].get("role") != "user"


async def test_model_call_no_timeout_when_zero(minimal_manifest, memory_store):
    """When call_timeout_s=0, no timeout wrapper is applied."""
    minimal_manifest.model.call_timeout_s = 0
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    with patch.object(
        mind._client.messages, "stream",
        return_value=make_stream_ctx(make_response(text="Fast response")),
    ):
        result = await mind.run_task("Quick task", inject_memories=False)

    assert result == "Fast response"


# ---------------------------------------------------------------------------
# Tests: compaction threshold respects model context window
# ---------------------------------------------------------------------------


async def test_compaction_uses_model_limit_when_lower(memory_store):
    """Compaction triggers at 75% of model.max_tokens when that's lower
    than compaction.max_context_tokens (the Root stall fix)."""
    from aiciv_mind.context_manager import ContextManager
    from aiciv_mind.manifest import CompactionConfig

    manifest = MindManifest(
        mind_id="compact-test",
        display_name="Compact Test Mind",
        role="worker",
        system_prompt="You are a test agent.",
        model=ModelConfig(preferred="ollama/test", max_tokens=16384),
        auth=AuthConfig(civ_id="acg", keypair_path="/tmp/test.json"),
        memory=MemoryConfig(db_path=":memory:", auto_search_before_task=False),
        compaction=CompactionConfig(
            enabled=True,
            max_context_tokens=50000,  # Default — way higher than model
            preserve_recent=4,
        ),
    )
    ctx_mgr = ContextManager(model_max_tokens=16384)
    mind = Mind(manifest=manifest, memory=memory_store, context_manager=ctx_mgr)

    # 75% of 16384 = 12288 tokens. At 4 chars/token, that's ~49152 chars.
    # Fill messages with enough content to exceed this threshold.
    for i in range(20):
        mind._messages.append({"role": "user", "content": "x" * 3000})
        mind._messages.append({"role": "assistant", "content": "y" * 3000})

    # Total chars: 40 messages × 3000 chars = 120000 chars ≈ 30000 tokens
    # 30000 > 12288 (75% of 16384) → compaction SHOULD trigger
    # 30000 < 50000 → without the fix, compaction would NOT trigger

    with patch.object(
        mind._client.messages, "stream",
        return_value=make_stream_ctx(make_response(text="Done after compaction")),
    ):
        result = await mind.run_task("Test compaction", inject_memories=False)

    # After compaction, messages should be drastically reduced:
    # summary pair (2) + preserve_recent (4) + new user (1) + assistant (1) = 8
    assert len(mind._messages) < 15  # Way less than the original 42
    assert result == "Done after compaction"


# ---------------------------------------------------------------------------
# Tests: tool execution timeout
# ---------------------------------------------------------------------------


async def test_tool_execution_timeout_returns_error(memory_store):
    """When a tool exceeds exec_timeout_s, an ERROR string is returned
    to the model (not an exception — the loop continues)."""
    from aiciv_mind.manifest import ToolsConfig

    manifest = MindManifest(
        mind_id="tool-timeout-test",
        display_name="Tool Timeout Test",
        role="worker",
        system_prompt="You are a test agent.",
        model=ModelConfig(preferred="ollama/test"),
        auth=AuthConfig(civ_id="acg", keypair_path="/tmp/test.json"),
        memory=MemoryConfig(db_path=":memory:", auto_search_before_task=False),
        tools_config=ToolsConfig(exec_timeout_s=0.1),
    )
    mind = Mind(manifest=manifest, memory=memory_store)

    async def slow_tool(args):
        await asyncio.sleep(5)
        return "Never reached"

    mind._tools.register(
        "slow_tool",
        {"name": "slow_tool", "description": "Slow", "input_schema": {"type": "object", "properties": {}}},
        slow_tool,
    )

    tc = make_tool_use_block("call_slow", "slow_tool", {})
    first = make_response(tool_blocks=[tc], stop_reason="tool_use")
    second = make_response(text="Handled the timeout.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        result = await mind.run_task("Run slow tool", inject_memories=False)

    assert result == "Handled the timeout."
    # The tool result fed back to model should contain the timeout error
    tool_result_msgs = [
        m for m in mind._messages
        if m.get("role") == "user" and isinstance(m.get("content"), list)
    ]
    assert any(
        "timed out" in str(item.get("content", ""))
        for msg in tool_result_msgs
        for item in msg["content"]
    )


# ---------------------------------------------------------------------------
# Tests: tool result truncation
# ---------------------------------------------------------------------------


async def test_oversized_tool_result_truncated(minimal_manifest, memory_store):
    """Tool results exceeding _MAX_TOOL_RESULT_CHARS are truncated with a marker."""
    mind = Mind(manifest=minimal_manifest, memory=memory_store)

    # Generate a result way larger than the 30K limit
    huge_output = "x" * 50_000

    async def big_tool(args):
        return huge_output

    mind._tools.register(
        "big_tool",
        {"name": "big_tool", "description": "Big output", "input_schema": {"type": "object", "properties": {}}},
        big_tool,
    )

    tc = make_tool_use_block("call_big", "big_tool", {})
    first = make_response(tool_blocks=[tc], stop_reason="tool_use")
    second = make_response(text="Got truncated result.")

    with patch.object(
        mind._client.messages, "stream",
        side_effect=[make_stream_ctx(first), make_stream_ctx(second)],
    ):
        result = await mind.run_task("Get big output", inject_memories=False)

    assert result == "Got truncated result."
    # Find the tool result in messages and verify truncation
    tool_result_msgs = [
        m for m in mind._messages
        if m.get("role") == "user" and isinstance(m.get("content"), list)
    ]
    assert len(tool_result_msgs) == 1
    content = tool_result_msgs[0]["content"][0]["content"]
    assert "TRUNCATED" in content
    assert len(content) < 50_000  # Should be ~30K + marker, not 50K


# ---------------------------------------------------------------------------
# Role-based tool filtering in Mind.__init__
# ---------------------------------------------------------------------------


async def test_mind_primary_role_filters_tools(memory_store):
    """Mind with role='primary' should only see PRIMARY_TOOLS."""
    manifest = MindManifest(
        mind_id="primary-test",
        display_name="Primary Test",
        role="primary",
        system_prompt="You are a conductor.",
        model=ModelConfig(preferred="ollama/qwen2.5-coder:14b"),
        auth=AuthConfig(civ_id="acg", keypair_path="/tmp/test.json"),
        memory=MemoryConfig(db_path=":memory:", auto_search_before_task=False),
    )
    mind = Mind(manifest=manifest, memory=memory_store)
    tool_names = mind._tools.names()
    # Primary should NOT have bash, read_file, write_file, etc.
    assert "bash" not in tool_names
    assert "read_file" not in tool_names
    assert "write_file" not in tool_names
    assert "memory_search" not in tool_names


async def test_mind_agent_role_keeps_all_tools(memory_store):
    """Mind with role='agent' should see all registered tools."""
    manifest = MindManifest(
        mind_id="agent-test",
        display_name="Agent Test",
        role="agent",
        system_prompt="You are an agent.",
        model=ModelConfig(preferred="ollama/qwen2.5-coder:14b"),
        auth=AuthConfig(civ_id="acg", keypair_path="/tmp/test.json"),
        memory=MemoryConfig(db_path=":memory:", auto_search_before_task=False),
    )
    mind = Mind(manifest=manifest, memory=memory_store)
    tool_names = mind._tools.names()
    # Agent should have everything
    assert "bash" in tool_names
    assert "read_file" in tool_names
    assert "memory_search" in tool_names


async def test_mind_freeform_role_keeps_all_tools(minimal_manifest, memory_store):
    """Mind with a free-form role (e.g., 'worker') should keep all tools."""
    assert minimal_manifest.role == "worker"
    mind = Mind(manifest=minimal_manifest, memory=memory_store)
    tool_names = mind._tools.names()
    # Worker role is not in the hierarchy — no filtering applied
    assert "bash" in tool_names
    assert "read_file" in tool_names
