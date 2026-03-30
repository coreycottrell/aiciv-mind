"""
aiciv_mind.tools — ToolRegistry and built-in tool set.

Every tool has:
  - A definition (Anthropic API format)
  - A handler (async or sync callable: dict -> str)
  - A read_only flag (True = safe to run concurrently with other read-only tools)

Usage:
    registry = ToolRegistry.default()
    tools = registry.build_anthropic_tools()        # all tools
    result = await registry.execute("bash", {"command": "echo hello"})
"""

from __future__ import annotations

import asyncio
from typing import Callable, Awaitable


class ToolRegistry:
    """Registry of tools available to a mind instance."""

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}       # name -> Anthropic tool definition
        self._handlers: dict[str, Callable] = {} # name -> handler function
        self._read_only: dict[str, bool] = {}    # name -> read_only flag

    def register(
        self,
        name: str,
        definition: dict,
        handler: Callable[[dict], Awaitable[str] | str],
        read_only: bool = False,
    ) -> None:
        """Register a tool with its definition, handler, and read_only flag."""
        self._tools[name] = definition
        self._handlers[name] = handler
        self._read_only[name] = read_only

    def build_openai_tools(self, enabled: list[str] | None = None) -> list[dict]:
        """
        Return tool definitions in OpenAI function-calling format.

        Converts from internal Anthropic format (input_schema) to OpenAI format
        (parameters inside a function wrapper).
        """
        anthropic_tools = self.build_anthropic_tools(enabled)
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for t in anthropic_tools
        ]

    def build_anthropic_tools(self, enabled: list[str] | None = None) -> list[dict]:
        """
        Return list of tool definitions in Anthropic API format.

        If enabled is None, return all registered tools.
        If enabled is a list of names, return only those (in order, skipping unknown names).
        """
        if enabled is None:
            return list(self._tools.values())
        return [self._tools[n] for n in enabled if n in self._tools]

    async def execute(self, name: str, tool_input: dict) -> str:
        """
        Execute a tool by name with the given input dict.

        Returns the tool's string output, or an error message if the tool
        is unknown or raises an exception.
        """
        if name not in self._handlers:
            return f"ERROR: Unknown tool '{name}'"
        try:
            handler = self._handlers[name]
            result = handler(tool_input)
            if asyncio.iscoroutine(result):
                result = await result
            return str(result)
        except Exception as e:
            return f"ERROR: Tool '{name}' failed: {type(e).__name__}: {e}"

    def is_read_only(self, name: str) -> bool:
        """Return True if the named tool is safe to run concurrently with other read-only tools."""
        return self._read_only.get(name, False)

    def names(self) -> list[str]:
        """Return sorted list of all registered tool names."""
        return list(self._tools.keys())

    @classmethod
    def default(
        cls,
        memory_store=None,
        agent_id: str = "primary",
        suite_client=None,
        context_store=None,
        get_message_count=None,
        spawner=None,
        primary_bus=None,
    ) -> "ToolRegistry":
        """
        Create a ToolRegistry with all built-in tools registered.

        If memory_store is provided, memory_search and memory_write are also registered.
        agent_id tags all written memories to the correct mind identity.
        If suite_client is provided, hub_post, hub_reply, hub_read are also registered.
        If context_store is provided, pin_memory, unpin_memory, introspect_context are registered.
        If spawner and primary_bus are both provided, spawn_submind and send_to_submind are registered.
        """
        from aiciv_mind.tools.bash import register_bash
        from aiciv_mind.tools.files import register_files
        from aiciv_mind.tools.search import register_search

        registry = cls()
        register_bash(registry)
        register_files(registry)
        register_search(registry)

        if memory_store is not None:
            from aiciv_mind.tools.memory_tools import register_memory_tools
            register_memory_tools(registry, memory_store, agent_id=agent_id)

        if suite_client is not None:
            from aiciv_mind.tools.hub_tools import register_hub_tools
            register_hub_tools(registry, suite_client)

        if context_store is not None:
            from aiciv_mind.tools.context_tools import register_context_tools
            register_context_tools(
                registry,
                memory_store=context_store,
                agent_id=agent_id,
                get_message_count=get_message_count,
            )

        if spawner is not None and primary_bus is not None:
            from aiciv_mind.tools.submind_tools import register_submind_tools
            register_submind_tools(registry, spawner=spawner, bus=primary_bus, primary_mind_id=agent_id)

        return registry
