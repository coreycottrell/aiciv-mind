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
import logging
from pathlib import Path
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# Default tool execution timeout (seconds).
# CC uses 15s for "proactive blocking budget".
# We allow per-tool overrides via register(..., timeout=N).
DEFAULT_TOOL_TIMEOUT: float = 15.0

# Tools that get longer timeouts by default (they legitimately take time)
_LONG_RUNNING_TOOLS: set[str] = {
    "bash", "web_search", "web_fetch", "voice_send",
    "netlify_deploy", "spawn_submind", "send_to_submind",
    "spawn_team_lead",
}
LONG_TOOL_TIMEOUT: float = 120.0


class ToolRegistry:
    """Registry of tools available to a mind instance."""

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}       # name -> Anthropic tool definition
        self._handlers: dict[str, Callable] = {} # name -> handler function
        self._read_only: dict[str, bool] = {}    # name -> read_only flag
        self._timeouts: dict[str, float] = {}    # name -> timeout seconds
        self._hooks = None  # Optional HookRunner for pre/post governance

    def set_hooks(self, hooks) -> None:
        """Attach a HookRunner for pre/post tool execution governance."""
        self._hooks = hooks

    def get_hooks(self):
        """Return the attached HookRunner, or None."""
        return self._hooks

    def register(
        self,
        name: str,
        definition: dict,
        handler: Callable[[dict], Awaitable[str] | str],
        read_only: bool = False,
        timeout: float | None = None,
    ) -> None:
        """Register a tool with its definition, handler, read_only flag, and optional timeout."""
        self._tools[name] = definition
        self._handlers[name] = handler
        self._read_only[name] = read_only
        if timeout is not None:
            self._timeouts[name] = timeout

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

    def _sanitize_tool_input(self, name: str, tool_input: dict) -> dict:
        """Coerce tool_input values to match the tool's schema types.

        Open-source models (M2.7, Gemma, etc.) frequently emit malformed
        tool arguments — trailing commas on integers ("10,"), stringified
        booleans ("true"), etc. This method uses the tool's input_schema to
        fix these before any handler sees them.

        SYSTEM > SYMPTOM: one sanitization point protects ALL tools.
        """
        schema = self._tools.get(name, {}).get("input_schema", {})
        props = schema.get("properties", {})
        if not props:
            return tool_input

        sanitized = dict(tool_input)
        for key, spec in props.items():
            if key not in sanitized:
                continue
            val = sanitized[key]
            expected = spec.get("type")

            if expected == "integer" and not isinstance(val, int):
                # Strip trailing commas/whitespace, then coerce
                try:
                    sanitized[key] = int(str(val).rstrip(", \t\n"))
                except (ValueError, TypeError):
                    pass  # Leave as-is; handler will deal with it

            elif expected == "number" and not isinstance(val, (int, float)):
                try:
                    sanitized[key] = float(str(val).rstrip(", \t\n"))
                except (ValueError, TypeError):
                    pass

            elif expected == "boolean" and not isinstance(val, bool):
                sv = str(val).strip().lower()
                if sv in ("true", "1", "yes"):
                    sanitized[key] = True
                elif sv in ("false", "0", "no"):
                    sanitized[key] = False

        return sanitized

    async def execute(self, name: str, tool_input: dict) -> str:
        """
        Execute a tool by name with the given input dict.

        If a HookRunner is attached, pre-hooks can deny the call and
        post-hooks can log or modify the output.

        Tools have a timeout budget (default 15s, long-running tools 120s).
        If a tool exceeds its timeout, the call is cancelled and an error
        is returned. This prevents a hung tool from blocking the mind loop.

        Returns the tool's string output, or an error/blocked message.
        """
        # Sanitize input using tool schema BEFORE any processing
        tool_input = self._sanitize_tool_input(name, tool_input)

        # Pre-hook: can deny the tool call
        if self._hooks:
            pre = self._hooks.pre_tool_use(name, tool_input)
            if not pre.allowed:
                return f"BLOCKED: {pre.message}"

        if name not in self._handlers:
            return f"ERROR: Unknown tool '{name}'"

        # Determine timeout for this tool
        if name in self._timeouts:
            timeout = self._timeouts[name]
        elif name in _LONG_RUNNING_TOOLS:
            timeout = LONG_TOOL_TIMEOUT
        else:
            timeout = DEFAULT_TOOL_TIMEOUT

        is_error = False
        try:
            handler = self._handlers[name]
            result = handler(tool_input)
            if asyncio.iscoroutine(result):
                result = await asyncio.wait_for(result, timeout=timeout)
            result = str(result)
        except asyncio.TimeoutError:
            result = (
                f"ERROR: Tool '{name}' timed out after {timeout:.0f}s. "
                "The tool was cancelled to prevent blocking the mind loop."
            )
            is_error = True
            logger.warning(
                "[tools] TIMEOUT: %s exceeded %.0fs budget", name, timeout,
            )
        except Exception as e:
            result = f"ERROR: Tool '{name}' failed: {type(e).__name__}: {e}"
            is_error = True

        # Post-hook: log and optionally modify output
        if self._hooks:
            post = self._hooks.post_tool_use(name, tool_input, result, is_error)
            if not post.allowed:
                return f"BLOCKED (post): {post.message}"
            if post.modified_output is not None:
                result = post.modified_output

        return result

    def is_read_only(self, name: str) -> bool:
        """Return True if the named tool is safe to run concurrently with other read-only tools."""
        return self._read_only.get(name, False)

    def names(self) -> list[str]:
        """Return sorted list of all registered tool names."""
        return list(self._tools.keys())

    def filter_by_role(self, role) -> "ToolRegistry":
        """
        Return a new ToolRegistry containing only tools allowed for the given role.

        Uses ROLE_TOOL_WHITELIST from aiciv_mind.roles.  If the whitelist is None
        (Role.AGENT), returns a copy with all tools.  Otherwise, keeps only tools
        whose names are in the whitelist.

        The hooks reference is shared (not copied) so governance still applies.
        """
        from aiciv_mind.roles import tools_for_role

        whitelist = tools_for_role(role)
        if whitelist is None:
            # Agent role — keep everything
            filtered = ToolRegistry()
            filtered._tools = dict(self._tools)
            filtered._handlers = dict(self._handlers)
            filtered._read_only = dict(self._read_only)
            filtered._timeouts = dict(self._timeouts)
            filtered._hooks = self._hooks
            return filtered

        filtered = ToolRegistry()
        for name in whitelist:
            if name in self._tools:
                filtered._tools[name] = self._tools[name]
                filtered._handlers[name] = self._handlers[name]
                filtered._read_only[name] = self._read_only[name]
                if name in self._timeouts:
                    filtered._timeouts[name] = self._timeouts[name]
        filtered._hooks = self._hooks
        return filtered

    @classmethod
    def default(
        cls,
        memory_store=None,
        agent_id: str = "primary",
        role: str = "agent",
        suite_client=None,
        context_store=None,
        get_message_count=None,
        get_session_store=None,
        spawner=None,
        primary_bus=None,
        queue_path: str | None = None,
        skills_dir: str | None = None,
        scratchpad_dir: str | None = None,
        manifest_path: str | None = None,
        agentmail_inbox: str | None = None,
        keypair_path: str | None = None,
        calendar_id: str | None = None,
        mind_lead_scratchpad_dir: str | None = None,
    ) -> "ToolRegistry":
        """
        Create a ToolRegistry with all built-in tools registered.

        If memory_store is provided, memory_search and memory_write are also registered.
        agent_id tags all written memories to the correct mind identity.
        If suite_client is provided, hub_post, hub_reply, hub_read, hub_list_rooms are also registered.
        If context_store is provided, pin_memory, unpin_memory, introspect_context are registered.
        If spawner and primary_bus are both provided, spawn_submind and send_to_submind are registered.
        If skills_dir is provided and memory_store is available, skill tools are registered.
        web_search is always registered (reads OLLAMA_API_KEY from env at call-time).
        """
        from aiciv_mind.tools.bash import register_bash
        from aiciv_mind.tools.files import register_files
        from aiciv_mind.tools.search import register_search
        from aiciv_mind.tools.web_search_tools import register_web_search
        from aiciv_mind.tools.git_tools import register_git_tools
        from aiciv_mind.tools.web_fetch_tools import register_web_fetch
        from aiciv_mind.tools.netlify_tools import register_netlify_tools
        from aiciv_mind.tools.voice_tools import register_voice_tools
        from aiciv_mind.tools.browser_tools import register_browser_tools

        registry = cls()
        register_bash(registry)
        register_files(registry)
        register_search(registry)
        register_web_search(registry)
        register_git_tools(registry)
        register_web_fetch(registry)
        register_netlify_tools(registry)
        register_voice_tools(registry)
        register_browser_tools(registry)

        if memory_store is not None:
            from aiciv_mind.tools.memory_tools import register_memory_tools
            register_memory_tools(registry, memory_store, agent_id=agent_id)

            from aiciv_mind.tools.continuity_tools import register_continuity_tools
            register_continuity_tools(registry, memory_store, agent_id=agent_id)

            from aiciv_mind.tools.graph_tools import register_graph_tools
            register_graph_tools(registry, memory_store)

            from aiciv_mind.tools.pattern_tools import register_pattern_tools
            register_pattern_tools(registry, memory_store, agent_id=agent_id)

            from aiciv_mind.tools.integrity_tools import register_integrity_tools
            register_integrity_tools(registry, memory_store)

            from aiciv_mind.tools.daemon_tools import register_daemon_tools
            register_daemon_tools(registry, memory_store)

        if suite_client is not None:
            from aiciv_mind.tools.hub_tools import register_hub_tools
            register_hub_tools(registry, suite_client, queue_path=queue_path)

            # Inter-mind coordination API (publish/read coordination surfaces)
            from aiciv_mind.tools.coordination_api_tools import register_coordination_api_tools
            register_coordination_api_tools(
                registry, suite_client,
                mind_id=agent_id, civ_id="acg",
            )

        if context_store is not None:
            from aiciv_mind.tools.context_tools import register_context_tools
            register_context_tools(
                registry,
                memory_store=context_store,
                agent_id=agent_id,
                get_session_store=get_session_store,
                get_message_count=get_message_count,
            )

        if spawner is not None and primary_bus is not None:
            from aiciv_mind.tools.submind_tools import register_submind_tools
            register_submind_tools(registry, spawner=spawner, bus=primary_bus, primary_mind_id=agent_id)

            # Role-enforced spawn tools (defense-in-depth alongside filter_by_role)
            from aiciv_mind.tools.spawn_tools import register_spawn_tools
            register_spawn_tools(
                registry, spawner=spawner, bus=primary_bus,
                mind_id=agent_id, role=role, scratchpad_dir=scratchpad_dir,
            )

            # Inter-mind messaging (PRIMARY and TEAM_LEAD both get this)
            from aiciv_mind.tools.message_tools import register_message_tools
            register_message_tools(registry, bus=primary_bus, sender_id=agent_id)

            # A/B model testing (PRIMARY spawns two sub-minds on different models)
            from aiciv_mind.tools.ab_test_tools import register_ab_test_tools
            register_ab_test_tools(registry, spawner=spawner, bus=primary_bus, mind_id=agent_id)

        if skills_dir is not None and memory_store is not None:
            from aiciv_mind.tools.skill_tools import register_skill_tools
            register_skill_tools(registry, memory_store, skills_dir)

        if scratchpad_dir is not None:
            from aiciv_mind.tools.scratchpad_tools import register_scratchpad_tools
            register_scratchpad_tools(registry, scratchpad_dir, mind_lead_scratchpad_dir)

            # Three-level scratchpad system: team + coordination tools
            from aiciv_mind.tools.coordination_tools import register_coordination_tools
            register_coordination_tools(registry, scratchpad_dir, writer_id=agent_id)

        if manifest_path is not None:
            from aiciv_mind.tools.sandbox_tools import register_sandbox_tools
            register_sandbox_tools(registry, manifest_path)

        if agentmail_inbox:
            from aiciv_mind.tools.email_tools import register_email_tools
            register_email_tools(registry, agentmail_inbox)

        if memory_store is not None:
            from aiciv_mind.tools.handoff_tools import register_handoff_tools
            mind_root_path = str(Path(__file__).parent.parent.parent.parent)
            register_handoff_tools(registry, memory_store, mind_root=mind_root_path)

        # ACG communication tool — always registered (any mind can talk to ACG)
        from aiciv_mind.tools.acg_tools import register_acg_tools
        register_acg_tools(registry)

        # system_health is always registered
        from aiciv_mind.tools.health_tools import register_health_tools
        register_health_tools(
            registry,
            memory_store=memory_store,
            mind_root=str(Path(__file__).parent.parent.parent.parent) if memory_store else None,
        )

        # resource tracking tools — always registered
        from aiciv_mind.tools.resource_tools import register_resource_tools
        register_resource_tools(
            registry,
            mind_root=str(Path(__file__).parent.parent.parent.parent),
        )

        if keypair_path is not None and calendar_id is not None:
            from aiciv_mind.tools.calendar_tools import register_calendar_tools
            register_calendar_tools(registry, keypair_path, calendar_id)

        # Apply role-based tool filtering (Design Principle A3: hard-coded roles)
        # PRIMARY gets ~12 coordination tools. TEAM_LEAD gets ~7. AGENT gets all.
        if role != "agent":
            from aiciv_mind.roles import Role
            try:
                parsed_role = Role.from_str(role)
                registry = registry.filter_by_role(parsed_role)
                logger.info(
                    "Role filter applied: %s → %d tools (from full registry)",
                    role, len(registry._tools),
                )
            except ValueError:
                logger.warning("Unknown role '%s' — returning full registry (no filter)", role)

        return registry
