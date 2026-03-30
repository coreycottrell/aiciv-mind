"""
Mind — the core agent loop for aiciv-mind.

Uses anthropic Python SDK pointed at LiteLLM proxy (default: localhost:4000).
LiteLLM translates Anthropic API format to Ollama, OpenRouter, or any other backend.

Environment variables:
  MIND_API_URL  — LiteLLM proxy URL (default: http://localhost:4000)
  MIND_API_KEY  — API key for the proxy (default: sk-1234)

Model names use LiteLLM routing format in the manifest, e.g.:
  "ollama/qwen2.5-coder:14b"
  "openrouter/kimi-k2"
"""
import asyncio
import logging
import os
import uuid
from typing import Any

import anthropic

from aiciv_mind.manifest import MindManifest
from aiciv_mind.memory import MemoryStore
from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)


class Mind:
    """
    Core agent loop. Loads a manifest, connects to LiteLLM proxy via anthropic SDK,
    executes tool-use loop until end_turn.
    """

    def __init__(
        self,
        manifest: MindManifest,
        memory: MemoryStore,
        tools: ToolRegistry | None = None,
        bus=None,  # SubMindBus | None — for IPC with primary
    ) -> None:
        self.manifest = manifest
        self.memory = memory
        self.bus = bus
        self._tools = tools or ToolRegistry.default(memory_store=memory)
        self._client = anthropic.AsyncAnthropic(
            base_url=os.environ.get("MIND_API_URL", "http://localhost:4000"),
            api_key=os.environ.get("MIND_API_KEY", "sk-1234"),
        )
        self._messages: list[dict] = []
        self._session_id: str | None = None
        self._running = False

    async def run_task(
        self,
        task: str,
        task_id: str | None = None,
        inject_memories: bool = True,
    ) -> str:
        """
        Execute a single task through the tool-use loop.
        Returns final text response.
        """
        self._session_id = self._session_id or str(uuid.uuid4())[:8]
        self._running = True

        system_prompt = self.manifest.resolved_system_prompt()
        if inject_memories and self.manifest.memory.auto_search_before_task:
            memories = self.memory.search(
                query=task,
                agent_id=self.manifest.mind_id,
                limit=self.manifest.memory.max_context_memories,
            )
            if memories:
                memory_context = "\n\n## Relevant memories from prior sessions:\n"
                for m in memories:
                    memory_context += f"\n### {m['title']}\n{m['content']}\n"
                system_prompt = system_prompt + memory_context

        self._messages.append({"role": "user", "content": task})

        tools_list = self._tools.build_anthropic_tools(
            enabled=self.manifest.enabled_tool_names()
        )

        final_text = ""
        max_iterations = 30
        iteration = 0

        while iteration < max_iterations and self._running:
            iteration += 1

            response = await self._call_model(system_prompt, tools_list)

            # Append assistant response to history
            self._messages.append({"role": "assistant", "content": response.content})

            # Extract text blocks
            text_blocks = [b for b in response.content if hasattr(b, "text")]
            if text_blocks:
                for tb in text_blocks:
                    final_text = tb.text
                    logger.debug("[%s] %s", self.manifest.mind_id, tb.text[:200])

            # Check for tool use
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if not tool_use_blocks or response.stop_reason == "end_turn":
                break

            tool_results = await self._execute_tool_calls(tool_use_blocks)
            self._messages.append({"role": "user", "content": tool_results})

        self._running = False
        return final_text

    async def _call_model(self, system_prompt: str, tools_list: list[dict]) -> Any:
        """Single API call with current message history."""
        kwargs: dict[str, Any] = dict(
            model=self.manifest.model.preferred,
            max_tokens=self.manifest.model.max_tokens,
            system=system_prompt,
            messages=self._messages,
        )
        if tools_list:
            kwargs["tools"] = tools_list

        return await self._client.messages.create(**kwargs)

    async def _execute_tool_calls(self, tool_blocks: list) -> list[dict]:
        """
        Execute all tool_use blocks from a response.
        Read-only tools run concurrently; write tools run sequentially.
        Returns list of tool_result content blocks.
        """
        results: list[dict] = []

        read_only = [b for b in tool_blocks if self._tools.is_read_only(b.name)]
        write_ops = [b for b in tool_blocks if not self._tools.is_read_only(b.name)]

        if read_only:
            tasks = [self._execute_one_tool(b) for b in read_only]
            concurrent_results = await asyncio.gather(*tasks, return_exceptions=True)
            for b, result in zip(read_only, concurrent_results):
                if isinstance(result, Exception):
                    result = f"ERROR: {result}"
                results.append({
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": str(result),
                })

        for b in write_ops:
            result = await self._execute_one_tool(b)
            results.append({
                "type": "tool_result",
                "tool_use_id": b.id,
                "content": str(result),
            })

        return results

    async def _execute_one_tool(self, block: Any) -> str:
        """Execute a single tool_use block. Returns string result."""
        tool_input = block.input if hasattr(block, "input") else {}
        logger.info("[%s] Tool: %s(%s)", self.manifest.mind_id, block.name, str(tool_input)[:100])
        result = await self._tools.execute(block.name, tool_input)
        logger.debug("[%s] Tool result: %s", self.manifest.mind_id, str(result)[:200])
        return result

    def clear_history(self) -> None:
        """Clear conversation history (keeps session_id)."""
        self._messages = []

    def stop(self) -> None:
        """Signal the tool loop to exit after the current iteration."""
        self._running = False
