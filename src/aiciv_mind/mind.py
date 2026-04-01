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
import json
import logging
import os
import re
import uuid
from typing import Any

import anthropic

from aiciv_mind.manifest import MindManifest
from aiciv_mind.memory import MemoryStore
from aiciv_mind.tools import ToolRegistry
from aiciv_mind.session_store import SessionStore
from aiciv_mind.context_manager import ContextManager

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
        session_store: SessionStore | None = None,
        context_manager: ContextManager | None = None,
        boot_context_str: str = "",
    ) -> None:
        self.manifest = manifest
        self.memory = memory
        self.bus = bus
        self._tools = tools or ToolRegistry.default(memory_store=memory)

        # Attach hook governance if configured
        if manifest.hooks.enabled:
            from aiciv_mind.tools.hooks import HookRunner
            hooks = HookRunner(
                blocked_tools=manifest.hooks.blocked_tools,
                log_all=manifest.hooks.log_all,
            )
            self._tools.set_hooks(hooks)
        self._client = anthropic.AsyncAnthropic(
            base_url=os.environ.get("MIND_API_URL", "http://localhost:4000"),
            api_key=os.environ.get("MIND_API_KEY", "sk-1234"),
        )
        self._messages: list[dict] = []
        self._session_id: str | None = None
        self._running = False
        self._session_store = session_store
        self._context_manager = context_manager
        # Boot context injected once at startup (identity + handoff)
        self._boot_context_str = boot_context_str

        # Compaction state (preserve-recent-N pattern)
        self._compacted_summary: str = ""

        # Cache stats for self-improvement loop
        self._session_cache_hits: int = 0
        self._session_cached_tokens: int = 0
        self._session_cache_writes: int = 0
        self._session_total_input_tokens: int = 0

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

        # Build system prompt in cache-optimal order:
        #   STATIC  (base prompt — identity, principles) ← ALWAYS first → always cached
        #   STABLE  (boot context — handoff, pinned)     ← stable across turns → cached
        #   SEMI-STABLE (search results)                 ← changes with query → tail only
        #
        # Rule: never put dynamic content before static content.
        # LiteLLM/OpenRouter caches the stable prefix; a flip in ordering breaks the cache.
        base_prompt = self.manifest.resolved_system_prompt()  # STATIC

        if self._boot_context_str:
            # STABLE appended AFTER static — keeps base_prompt as the cache anchor
            system_prompt = base_prompt + "\n\n" + self._boot_context_str
        else:
            system_prompt = base_prompt

        # SEMI-STABLE: per-turn search results appended last
        if inject_memories and self.manifest.memory.auto_search_before_task:
            memories = self.memory.search(
                query=task,
                agent_id=self.manifest.mind_id,
                limit=self.manifest.memory.max_context_memories,
            )
            if memories:
                # Touch accessed memories (update depth signals)
                for m in memories:
                    self.memory.touch(m["id"])
                if self._context_manager:
                    memory_context = self._context_manager.format_search_results(memories)
                else:
                    memory_context = "\n\n## Relevant memories from prior sessions:\n"
                    for m in memories:
                        memory_context += f"\n### {m['title']}\n{m['content']}\n"
                system_prompt = system_prompt + memory_context

        # Record this turn in the session journal
        if self._session_store:
            # 16 words ~ 100 chars — enough to be recognizable in handoffs without being lossy.
            # 5 was too short: "Store a memory with the" lost "FTS index" context.
            # Root identified this pattern via 5-step self-audit (Build 3, 2026-04-01).
            _MAX_TOPIC_WORDS = 16
            _topic_words = task.strip().split()[:_MAX_TOPIC_WORDS]
            _topic = " ".join(_topic_words) if _topic_words else None
            self._session_store.record_turn(topic=_topic)

        self._messages.append({"role": "user", "content": task})

        tools_list = self._tools.build_anthropic_tools(
            enabled=self.manifest.enabled_tool_names()
        )

        final_text = ""
        max_iterations = 30
        iteration = 0

        while iteration < max_iterations and self._running:
            iteration += 1

            # Compaction check: if messages exceed token threshold, compact
            if (self.manifest.compaction.enabled
                    and self._context_manager
                    and self._context_manager.should_compact(
                        self._messages,
                        self.manifest.compaction.max_context_tokens,
                    )):
                self._messages, self._compacted_summary = (
                    self._context_manager.compact_history(
                        self._messages,
                        preserve_recent=self.manifest.compaction.preserve_recent,
                        existing_summary=self._compacted_summary,
                    )
                )
                logger.info(
                    "[%s] Compacted history: %d messages remain, summary %d chars",
                    self.manifest.mind_id, len(self._messages),
                    len(self._compacted_summary),
                )

            response = await self._call_model(system_prompt, tools_list)

            # Append assistant response to history
            self._messages.append({"role": "assistant", "content": response.content})

            # Extract text blocks
            text_blocks = [b for b in response.content if hasattr(b, "text")]
            if text_blocks:
                for tb in text_blocks:
                    final_text = tb.text
                    logger.debug("[%s] %s", self.manifest.mind_id, tb.text[:200])

            # Check for tool use — native blocks first, then text-embedded fallback
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            synthetic_calls = False

            if not tool_use_blocks and text_blocks:
                # Some models (M2.7 via Ollama) emit tool calls as JSON text
                # instead of structured tool_use blocks. Parse them out.
                tool_use_blocks = self._parse_text_tool_calls(final_text)
                synthetic_calls = bool(tool_use_blocks)

            if not tool_use_blocks:
                break
            # For native tool_use, end_turn means stop. For synthetic (text-parsed)
            # calls, end_turn is always set — ignore it and execute the tools.
            if not synthetic_calls and response.stop_reason == "end_turn":
                break

            tool_results = await self._execute_tool_calls(tool_use_blocks)

            if synthetic_calls:
                # For text-embedded tool calls, inject results as plain text
                # so the model sees them naturally (it never produced tool_use IDs)
                result_text = "\n".join(
                    f"[Tool result: {b.name}]\n{r['content']}"
                    for b, r in zip(tool_use_blocks, tool_results)
                )
                self._messages.append({"role": "user", "content": result_text})
            else:
                self._messages.append({"role": "user", "content": tool_results})

        self._running = False

        # Loop 1 — store what was learned from this task
        if getattr(self.manifest, 'self_modification_enabled', False) and final_text:
            try:
                _summary = final_text.strip()[:200]
                _task_topic = task.strip().split()[:5]
                _topic_str = " ".join(_task_topic) if _task_topic else "general"
                self.memory.store(
                    agent_id=self.manifest.mind_id,
                    title=f"Task result: {_topic_str}",
                    content=_summary,
                    memory_type="learning",
                    tags=["loop-1", "task-result"],
                )
            except Exception:
                pass  # never let memory write crash the task return

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

        response = await self._client.messages.create(**kwargs)
        self._log_cache_stats(response)
        return response

    def _log_cache_stats(self, response: Any) -> None:
        """
        Log prompt cache hit/miss from API response usage metadata.

        LiteLLM surfaces cache stats from OpenRouter/MiniMax in the anthropic
        usage object as cache_read_input_tokens / cache_creation_input_tokens.
        Not all backends return these fields — we log when present, skip silently
        when absent.  Wrapped in try/except: this is telemetry, never breaks the loop.
        """
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return

            # Use int() to guard against mock objects in tests
            cached  = int(getattr(usage, "cache_read_input_tokens",  None) or 0)
            created = int(getattr(usage, "cache_creation_input_tokens", None) or 0)
            total_in = int(getattr(usage, "input_tokens", None) or 0)

            if cached > 0:
                total = total_in + cached
                pct = cached / total * 100 if total else 0.0
                logger.info(
                    "[%s] Cache HIT: %d cached / %d total input tokens (%.0f%% hit rate)",
                    self.manifest.mind_id, cached, total, pct,
                )
            elif created > 0:
                logger.info(
                    "[%s] Cache WRITE: %d tokens written to cache",
                    self.manifest.mind_id, created,
                )
            else:
                logger.debug(
                    "[%s] No cache metadata (backend: %s)",
                    self.manifest.mind_id, self.manifest.model.preferred,
                )
            # Accumulate session-level stats
            if cached > 0:
                self._session_cache_hits += 1
                self._session_cached_tokens += cached
                self._session_total_input_tokens += total_in + cached
            elif created > 0:
                self._session_cache_writes += 1
                self._session_total_input_tokens += total_in + created
            elif total_in > 0:
                self._session_total_input_tokens += total_in
        except Exception:
            pass  # telemetry never crashes the loop

    def _parse_text_tool_calls(self, text: str) -> list:
        """
        Extract tool calls embedded as JSON in a text response.

        Some models (e.g. M2.7 via Ollama) emit tool calls as JSON text instead
        of structured tool_use content blocks.  This method detects patterns like:
            {"name": "tool_name", "arguments": {...}}
        and converts them into synthetic tool-block objects compatible with
        _execute_tool_calls().

        Strategy: find all top-level JSON objects in the text by scanning for
        balanced braces, then check if any are valid tool calls.

        Returns an empty list if no valid tool-call JSON is found.
        """
        blocks = []
        registered = set(self._tools.names())

        # Extract all JSON objects from the text (handles nested braces)
        for candidate in self._extract_json_objects(text):
            try:
                obj = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue

            if not isinstance(obj, dict):
                continue

            name = obj.get("name")
            args = obj.get("arguments", {})

            if not name or name not in registered:
                continue
            if not isinstance(args, dict):
                continue

            block = type("SyntheticToolUse", (), {
                "name": name,
                "input": args,
                "id": f"synthetic_{uuid.uuid4().hex[:12]}",
                "type": "tool_use",
            })()
            blocks.append(block)
            logger.info(
                "[%s] Parsed text tool call: %s(%s)",
                self.manifest.mind_id, name, str(args)[:100],
            )

        # Fallback: [TOOL_CALL] blocks (M2.7 native format)
        if not blocks:
            tool_call_re = re.compile(
                r'\[TOOL_CALL\]\s*\{tool\s*=>\s*"([^"]+)",\s*args\s*=>\s*\{(.*?)\}\s*\}\s*\[/TOOL_CALL\]',
                re.DOTALL,
            )
            for match in tool_call_re.finditer(text):
                name = match.group(1)
                args_body = match.group(2).strip()
                if name not in registered:
                    continue
                args = self._parse_cli_style_args(args_body)
                block = type("SyntheticToolUse", (), {
                    "name": name,
                    "input": args,
                    "id": f"synthetic_{uuid.uuid4().hex[:12]}",
                    "type": "tool_use",
                })()
                blocks.append(block)
                logger.info(
                    "[%s] Parsed TOOL_CALL block: %s(%s)",
                    self.manifest.mind_id, name, str(args)[:100],
                )

        # Fallback: <minimax:tool_call> XML blocks (M2.7 XML format)
        if not blocks:
            xml_re = re.compile(
                r'<minimax:tool_call>\s*<invoke\s+name="([^"]+)">\s*(.*?)</invoke>\s*</minimax:tool_call>',
                re.DOTALL,
            )
            for match in xml_re.finditer(text):
                name = match.group(1)
                if name not in registered:
                    continue
                # Parse <parameter name="key">value</parameter> pairs
                args = {}
                param_re = re.compile(
                    r'<parameter\s+name="([^"]+)">(.*?)</parameter>',
                    re.DOTALL,
                )
                for pm in param_re.finditer(match.group(2)):
                    val = pm.group(2).strip()
                    # Try to parse as JSON value (bool, int, etc.)
                    try:
                        args[pm.group(1)] = json.loads(val)
                    except (json.JSONDecodeError, ValueError):
                        args[pm.group(1)] = val
                block = type("SyntheticToolUse", (), {
                    "name": name,
                    "input": args,
                    "id": f"synthetic_{uuid.uuid4().hex[:12]}",
                    "type": "tool_use",
                })()
                blocks.append(block)
                logger.info(
                    "[%s] Parsed XML tool call: %s(%s)",
                    self.manifest.mind_id, name, str(args)[:100],
                )

        return blocks

    @staticmethod
    def _parse_cli_style_args(text: str) -> dict:
        """Parse --key value or --key \"value\" pairs into a dict."""
        result = {}
        pattern = re.compile(r'--(\w+)\s+(?:"([^"]*)"|([\S]+))')
        for match in pattern.finditer(text):
            key = match.group(1)
            value = match.group(2) if match.group(2) is not None else match.group(3)
            try:
                value = int(value)
            except (ValueError, TypeError):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    pass
            result[key] = value
        return result

    @staticmethod
    def _extract_json_objects(text: str) -> list[str]:
        """Extract balanced JSON object strings from text."""
        results = []
        i = 0
        while i < len(text):
            if text[i] == '{':
                depth = 0
                start = i
                in_string = False
                escape_next = False
                while i < len(text):
                    c = text[i]
                    if escape_next:
                        escape_next = False
                    elif c == '\\' and in_string:
                        escape_next = True
                    elif c == '"' and not escape_next:
                        in_string = not in_string
                    elif not in_string:
                        if c == '{':
                            depth += 1
                        elif c == '}':
                            depth -= 1
                            if depth == 0:
                                results.append(text[start:i + 1])
                                break
                    i += 1
            i += 1
        return results

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

    @property
    def cache_stats(self) -> dict:
        """Accumulated cache statistics for this session."""
        total_calls = self._session_cache_hits + self._session_cache_writes
        return {
            "cache_hits": self._session_cache_hits,
            "cache_writes": self._session_cache_writes,
            "cached_tokens": self._session_cached_tokens,
            "total_input_tokens": self._session_total_input_tokens,
            "hit_rate": (
                round(self._session_cache_hits / total_calls, 2)
                if total_calls > 0 else 0.0
            ),
        }

    def clear_history(self) -> None:
        """Clear conversation history (keeps session_id)."""
        self._messages = []

    def stop(self) -> None:
        """Signal the tool loop to exit after the current iteration."""
        self._running = False
