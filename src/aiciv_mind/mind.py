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
import time
import uuid
from pathlib import Path
from typing import Any

import anthropic

from aiciv_mind.context import mind_context
from aiciv_mind.learning import SessionLearner, TaskOutcome
from aiciv_mind.manifest import MindManifest
from aiciv_mind.memory import MemoryStore
from aiciv_mind.planning import PlanningGate, TaskComplexity
from aiciv_mind.verification import CompletionProtocol
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

        # Planning gate (Principle 3: Go Slow to Go Fast)
        self._planning_gate = PlanningGate(
            memory_store=memory,
            agent_id=manifest.mind_id,
            enabled=manifest.planning.enabled,
        )

        # Verification protocol (Principle 9: Red Team Everything)
        self._completion_protocol = CompletionProtocol(
            memory_store=memory,
            agent_id=manifest.mind_id,
            enabled=manifest.verification.enabled,
        )

        # Session learner (Principle 7: Self-Improving Loop)
        self._session_learner = SessionLearner(
            agent_id=manifest.mind_id,
        )

        # Compaction state (preserve-recent-N pattern)
        self._compacted_summary: str = ""

        # Cache stats for self-improvement loop
        self._session_cache_hits: int = 0
        self._session_cached_tokens: int = 0
        self._session_cache_writes: int = 0
        self._session_total_input_tokens: int = 0

        # Token usage tracking — JSONL log at data/token_usage.jsonl
        self._mind_root = Path(__file__).parent.parent.parent
        self._token_log_path = self._mind_root / "data" / "token_usage.jsonl"
        self._session_log_dir = self._mind_root / "data" / "sessions"
        # Ensure directories exist
        self._token_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_log_dir.mkdir(parents=True, exist_ok=True)
        # Session-level token accumulators
        self._session_total_output_tokens: int = 0
        self._session_total_thinking_tokens: int = 0
        self._session_total_cost_usd: float = 0.0
        self._session_api_calls: int = 0

    async def run_task(
        self,
        task: str,
        task_id: str | None = None,
        inject_memories: bool = True,
        fresh_context: bool = False,
    ) -> str:
        """
        Execute a single task through the tool-use loop.
        Returns final text response.

        If fresh_context=True, conversation history is cleared before this task
        runs (useful for scheduled BOOPs that don't need prior context).
        """
        self._session_id = self._session_id or str(uuid.uuid4())[:8]
        self._running = True

        if fresh_context:
            self._messages = []

        # Wrap entire task execution in mind_context so that any code
        # in the call stack can call current_mind_id() to identify which
        # mind is executing (critical for concurrent sub-minds).
        async with mind_context(self.manifest.mind_id):
            return await self._run_task_body(task, inject_memories)

    async def _run_task_body(self, task: str, inject_memories: bool) -> str:
        """Task execution body — always runs inside a mind_context scope."""

        # ── Planning Gate (P3) ─────────────────────────────────────────
        # Fires BEFORE execution.  Classifies task complexity, searches
        # memory for prior similar tasks, and builds planning context
        # proportional to complexity.
        planning_result = self._planning_gate.run(task)
        planning_context = ""
        if planning_result.plan:
            min_level = self.manifest.planning.min_gate_level
            try:
                min_complexity = TaskComplexity(min_level)
            except ValueError:
                min_complexity = TaskComplexity.SIMPLE
            if planning_result.complexity.gate_depth >= min_complexity.gate_depth:
                planning_context = planning_result.plan

        # Build system prompt in cache-optimal order:
        #   STATIC  (base prompt — identity, principles) ← ALWAYS first → always cached
        #   STABLE  (boot context — handoff, pinned)     ← stable across turns → cached
        #   SEMI-STABLE (planning + search results)      ← changes with query → tail only
        #
        # Rule: never put dynamic content before static content.
        # LiteLLM/OpenRouter caches the stable prefix; a flip in ordering breaks the cache.
        base_prompt = self.manifest.resolved_system_prompt()  # STATIC

        if self._boot_context_str:
            # STABLE appended AFTER static — keeps base_prompt as the cache anchor
            system_prompt = base_prompt + "\n\n" + self._boot_context_str
        else:
            system_prompt = base_prompt

        # Planning context (SEMI-STABLE — changes per task)
        if planning_context:
            system_prompt = system_prompt + "\n\n" + planning_context

        # Verification protocol (P9) — inject Red Team questions proportional to complexity
        verification_prompt = self._completion_protocol.build_verification_prompt(
            task=task,
            complexity=planning_result.complexity.value,
        )
        if verification_prompt:
            system_prompt = system_prompt + "\n" + verification_prompt

        # SEMI-STABLE: per-turn search results appended last
        if inject_memories and self.manifest.memory.auto_search_before_task:
            # Phase 1: Direct search on task text
            max_memories = self.manifest.memory.max_context_memories
            memories = self.memory.search(
                query=task,
                agent_id=self.manifest.mind_id,
                limit=max_memories,
            )
            seen_ids = {m["id"] for m in memories}

            # Phase 2: If we have budget remaining, broaden search with extracted keywords
            if len(memories) < max_memories:
                _STOP_WORDS = {
                    "the", "a", "an", "is", "are", "was", "were", "be", "been",
                    "being", "have", "has", "had", "do", "does", "did", "will",
                    "would", "could", "should", "may", "might", "can", "shall",
                    "to", "of", "in", "for", "on", "with", "at", "by", "from",
                    "and", "or", "not", "no", "but", "if", "then", "so", "as",
                    "this", "that", "it", "its", "my", "your", "our", "their",
                    "what", "which", "who", "whom", "how", "when", "where", "why",
                    "all", "each", "every", "any", "some", "i", "you", "we", "they",
                }
                words = [w for w in task.lower().split() if w not in _STOP_WORDS and len(w) > 2]
                # Take up to 5 significant words as a broadened query
                if words:
                    broad_query = " ".join(words[:5])
                    if broad_query != task.lower().strip():
                        extra = self.memory.search(
                            query=broad_query,
                            agent_id=self.manifest.mind_id,
                            limit=max_memories - len(memories),
                        )
                        for m in extra:
                            if m["id"] not in seen_ids:
                                memories.append(m)
                                seen_ids.add(m["id"])

            if memories:
                # Touch accessed memories (update depth signals)
                for m in memories:
                    self.memory.touch(m["id"])
                if self._context_manager:
                    memory_context = self._context_manager.format_search_results(memories)
                else:
                    memory_context = (
                        "\n\n## Relevant memories from prior sessions:\n"
                        "*These memories are HINTS, not facts. Verify before asserting.*\n"
                    )
                    for m in memories:
                        created = m.get("created_at", "unknown")
                        memory_context += f"\n### {m['title']}  *(written {created})*\n{m['content']}\n"
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

        # Log the user turn to session JSONL
        self._log_session_turn(
            turn_number=len(self._messages),
            turn_type="user",
        )

        tools_list = self._tools.build_anthropic_tools(
            enabled=self.manifest.enabled_tool_names()
        )

        final_text = ""
        max_iterations = 30
        iteration = 0
        task_start_time = time.monotonic()

        # Loop 1 telemetry — collected during tool execution, consumed after
        tool_call_count = 0
        tool_errors: list[str] = []
        tools_used: set[str] = set()

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

            # Token budget awareness: warn when context pressure is high
            if self._context_manager and iteration == 1:
                est_tokens = self._context_manager.estimate_tokens(
                    system_prompt + str(self._messages)
                )
                model_max = self.manifest.model.max_tokens
                if model_max > 0:
                    pct = est_tokens / model_max
                    if pct > 0.85:
                        logger.warning(
                            "[%s] Context pressure CRITICAL: ~%d tokens (%.0f%% of %d). "
                            "Compaction should trigger.",
                            self.manifest.mind_id, est_tokens, pct * 100, model_max,
                        )
                    elif pct > 0.70:
                        logger.info(
                            "[%s] Context pressure HIGH: ~%d tokens (%.0f%% of %d)",
                            self.manifest.mind_id, est_tokens, pct * 100, model_max,
                        )

            iter_start = time.monotonic()
            try:
                response = await self._call_model(system_prompt, tools_list)
            except Exception as e:
                logger.error(
                    "[%s] _call_model failed (iter %d): %s — popping orphaned user message",
                    self.manifest.mind_id, iteration, e,
                )
                # Pop the user message we just appended to keep _messages
                # in valid alternating user/assistant order. Without this,
                # every subsequent API call fails with "messages must alternate"
                # creating an infinite error loop that eventually kills the daemon.
                if self._messages and self._messages[-1].get("role") == "user":
                    self._messages.pop()
                raise  # let the daemon's handler decide retry/skip
            iter_latency = int((time.monotonic() - iter_start) * 1000)

            # Append assistant response to history
            self._messages.append({"role": "assistant", "content": response.content})

            # Log assistant turn to session JSONL
            self._log_session_turn(
                turn_number=len(self._messages),
                turn_type="assistant",
                response=response,
                duration_ms=iter_latency,
            )

            # Extract thinking blocks (M2.7 with reasoning_split=true)
            thinking_blocks = [
                b for b in response.content
                if getattr(b, "type", None) == "thinking"
            ]
            if thinking_blocks:
                for tb in thinking_blocks:
                    thinking_text = getattr(tb, "thinking", "")
                    if thinking_text:
                        logger.info(
                            "[%s] Thinking: %s",
                            self.manifest.mind_id, thinking_text[:200],
                        )

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

            tool_exec_start = time.monotonic()
            tool_results = await self._execute_tool_calls(tool_use_blocks)
            tool_exec_ms = int((time.monotonic() - tool_exec_start) * 1000)

            # Log tool calls to session JSONL
            iter_tool_names = [b.name for b in tool_use_blocks]
            self._log_session_turn(
                turn_number=len(self._messages) + 1,
                turn_type="tool_call",
                tools_used=iter_tool_names,
                duration_ms=tool_exec_ms,
            )

            # Collect Loop 1 telemetry from this batch of tool calls
            for b, r in zip(tool_use_blocks, tool_results):
                tool_call_count += 1
                tools_used.add(b.name)
                result_content = r.get("content", "") if isinstance(r, dict) else str(r)
                if "ERROR:" in result_content:
                    # Capture the first line containing ERROR: (truncated to 200 chars)
                    for line in result_content.splitlines():
                        if "ERROR:" in line:
                            tool_errors.append(line.strip()[:200])
                            break

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

        # Loop 1 — store structured learning from this task
        #
        # Gates (skip noisy / trivial tasks):
        #   - self_modification_enabled must be on
        #   - final_text must exist and be non-trivial (>= 50 chars)
        #   - must have used >= 2 tool calls (simple Q&A is not worth storing)
        #   - skip scheduled BOOP grounding checks (pure housekeeping)
        if (
            getattr(self.manifest, 'self_modification_enabled', False)
            and final_text
            and len(final_text.strip()) >= 50
            and tool_call_count >= 2
            and not task.lstrip().startswith("[Scheduled BOOP")
        ):
            try:
                from aiciv_mind.memory import Memory as _Memory

                # Title: first meaningful sentence from final_text (up to 80 chars)
                _stripped = final_text.strip()
                # Split on sentence-ending punctuation, take the first sentence
                _sentences = re.split(r'(?<=[.!?])\s+', _stripped, maxsplit=1)
                _title = _sentences[0][:80] if _sentences else _stripped[:80]
                # Fall back if the title is too short to be useful
                if len(_title) < 10:
                    _title = _stripped[:80]

                # Build structured content
                _tools_str = ", ".join(sorted(tools_used)) if tools_used else "none"
                _errors_str = "; ".join(tool_errors[:5]) if tool_errors else "none"
                _content = (
                    f"Task: {task[:150]}\n"
                    f"Tools used: {_tools_str}\n"
                    f"Errors: {_errors_str}\n"
                    f"Result: {_stripped[:300]}"
                )

                # Tags: base tags + tool names used
                _tags = ["loop-1", "task-learning"] + sorted(tools_used)

                # Memory type: "error" if any tool errors occurred, else "learning"
                _mem_type = "error" if tool_errors else "learning"

                _mem = _Memory(
                    agent_id=self.manifest.mind_id,
                    title=_title,
                    content=_content,
                    memory_type=_mem_type,
                    tags=_tags,
                    session_id=self._session_id,
                )
                self.memory.store(_mem)

                # Auto-hint: if this was an error, check for repeated tool failures
                if _mem_type == "error" and tools_used:
                    try:
                        _primary_tool = sorted(tools_used)[0]
                        _recent_errors = self.memory.by_type(
                            "error",
                            agent_id=self.manifest.mind_id,
                            limit=10,
                        )
                        # Filter to Loop 1 errors mentioning the same tool
                        _matching = [
                            e for e in _recent_errors
                            if _primary_tool in e.get("tags", "")
                            and "loop-1" in e.get("tags", "")
                        ]
                        if len(_matching) >= 3:
                            _hint = (
                                f"\n\n---\n**Pattern detected**: {len(_matching)} recent "
                                f"task errors involving `{_primary_tool}`. Consider running "
                                f"`loop1_pattern_scan` to review and potentially log this "
                                f"as a systemic issue.\n---"
                            )
                            final_text = final_text + _hint
                    except Exception:
                        pass  # hint is best-effort, never crashes
            except Exception:
                pass  # Loop 1 must NEVER crash the task return

        # ── Session Learner (P7 Loop 2 accumulator) ───────────────────
        # Feed TaskOutcome to the session learner so it can produce
        # cross-task insights at session end.
        try:
            task_elapsed = time.monotonic() - task_start_time
            outcome = TaskOutcome(
                task=task[:200],
                result=final_text[:300] if final_text else "",
                tools_used=sorted(tools_used),
                tool_errors=tool_errors[:5],
                tool_call_count=tool_call_count,
                elapsed_s=round(task_elapsed, 2),
                planned_complexity=planning_result.complexity.value,
                memories_consulted=planning_result.memories_consulted,
            )
            self._session_learner.record(outcome)
        except Exception:
            pass  # Learner must NEVER crash the task return

        # ── Stop Hook (lifecycle) ─────────────────────────────────────
        # Fire on_stop so registered callbacks can do cleanup/notifications.
        try:
            hooks = self._tools.get_hooks()
            if hooks:
                hooks.on_stop(
                    mind_id=self.manifest.mind_id,
                    result=final_text[:500] if final_text else "",
                    tool_calls=tool_call_count,
                    session_id=self._session_id or "",
                )
        except Exception:
            pass  # Lifecycle hooks must NEVER crash the task return

        return final_text

    def session_wrapup(self) -> dict[str, Any]:
        """
        Session wrapup — triggers Loop 2 learning.

        Call at session end to:
        1. Produce session-level summary (cross-task patterns, insights)
        2. Write session learning to memory
        3. Return summary for logging/handoff

        Returns the session summary as a dict.
        """
        summary = self._session_learner.summarize()
        mem_id = self._session_learner.write_session_learning(self.memory)

        result = summary.to_dict()
        result["learning_memory_id"] = mem_id

        # Also include verification stats from P9
        result["verification_session_stats"] = self._completion_protocol.get_session_stats()

        logger.info(
            "[%s] Session wrapup: %d tasks, %.0f%% success, %d insights, "
            "learning_id=%s",
            self.manifest.mind_id,
            summary.task_count,
            summary.success_rate * 100,
            len(summary.insights),
            mem_id,
        )

        return result

    async def _call_model(self, system_prompt: str, tools_list: list[dict]) -> Any:
        """Single API call with current message history."""
        kwargs: dict[str, Any] = dict(
            model=self.manifest.model.preferred,
            max_tokens=self.manifest.model.max_tokens,
            temperature=self.manifest.model.temperature,
            system=system_prompt,
            messages=self._messages,
        )
        if tools_list:
            kwargs["tools"] = tools_list

        t0 = time.monotonic()
        response = await self._client.messages.create(**kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)

        self._log_cache_stats(response)
        self._log_token_usage(response, latency_ms)
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

    # ------------------------------------------------------------------
    # Model pricing table (USD per 1M tokens)
    # Updated as of 2026-04-02. Add new models as they come online.
    # ------------------------------------------------------------------
    _MODEL_PRICING: dict[str, dict[str, float]] = {
        # model_id → {"input": $/1M, "output": $/1M}
        "minimax-m27":          {"input": 0.50, "output": 1.50},
        "kimi-k2":              {"input": 0.60, "output": 0.60},
        "qwen2.5-coder":        {"input": 0.00, "output": 0.00},  # local Ollama
        "qwen2.5-coder:14b":    {"input": 0.00, "output": 0.00},  # local Ollama
        "phi3":                 {"input": 0.00, "output": 0.00},  # local Ollama
        "llama3.1":             {"input": 0.00, "output": 0.00},  # local Ollama
        "deepseek-r1":          {"input": 0.00, "output": 0.00},  # local Ollama
    }

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD based on model pricing. Returns 0.0 for unknown models."""
        # Strip LiteLLM prefixes (e.g. "ollama/qwen2.5-coder:14b" → "qwen2.5-coder:14b")
        bare_model = model.split("/")[-1] if "/" in model else model
        pricing = self._MODEL_PRICING.get(bare_model)
        if not pricing:
            # Try partial match (e.g. "minimax-m27-01232" → "minimax-m27")
            for key in self._MODEL_PRICING:
                if key in bare_model or bare_model in key:
                    pricing = self._MODEL_PRICING[key]
                    break
        if not pricing:
            return 0.0
        return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

    def _log_token_usage(self, response: Any, latency_ms: int) -> None:
        """
        Extract token counts from the API response and append to data/token_usage.jsonl.

        LiteLLM surfaces usage as:
          response.usage.input_tokens
          response.usage.output_tokens
        Some backends also include cache_read_input_tokens.
        Thinking tokens are detected from thinking content blocks.

        This is telemetry — it must NEVER crash the agent loop.
        """
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return

            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

            # Thinking tokens: check for thinking blocks in the response content
            thinking_tokens = 0
            if hasattr(response, "content"):
                for block in response.content:
                    if getattr(block, "type", None) == "thinking":
                        thinking_text = getattr(block, "thinking", "")
                        # Approximate: 1 token ≈ 4 chars for thinking blocks
                        thinking_tokens += len(thinking_text) // 4

            model = self.manifest.model.preferred
            estimated_cost = self._estimate_cost(model, input_tokens, output_tokens)

            # Build the last user message summary (first 100 chars)
            task_summary = ""
            for msg in reversed(self._messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        task_summary = content[:100]
                    elif isinstance(content, list):
                        # Tool results — summarize
                        task_summary = f"[{len(content)} tool result(s)]"
                    break

            record = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "session_id": self._session_id or "unknown",
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "thinking_tokens": thinking_tokens,
                "latency_ms": latency_ms,
                "estimated_cost_usd": round(estimated_cost, 6),
                "task_summary": task_summary,
            }

            # Append to JSONL file
            with open(self._token_log_path, "a") as f:
                f.write(json.dumps(record) + "\n")

            # Accumulate session-level stats
            self._session_total_output_tokens += output_tokens
            self._session_total_thinking_tokens += thinking_tokens
            self._session_total_cost_usd += estimated_cost
            self._session_api_calls += 1

            logger.info(
                "[%s] Tokens: in=%d out=%d think=%d cost=$%.4f latency=%dms",
                self.manifest.mind_id, input_tokens, output_tokens,
                thinking_tokens, estimated_cost, latency_ms,
            )
        except Exception:
            pass  # telemetry never crashes the loop

    def _log_session_turn(
        self,
        turn_number: int,
        turn_type: str,
        response: Any | None = None,
        tools_used: list[str] | None = None,
        duration_ms: int = 0,
    ) -> None:
        """
        Append a structured turn record to data/sessions/{session_id}.jsonl.

        This provides Claude-Code-style structured session logging — every turn
        in every session gets a JSONL record for later analysis and replay.

        This is telemetry — it must NEVER crash the agent loop.
        """
        try:
            if not self._session_id:
                return

            tokens = {}
            if response is not None:
                usage = getattr(response, "usage", None)
                if usage:
                    tokens = {
                        "input": int(getattr(usage, "input_tokens", 0) or 0),
                        "output": int(getattr(usage, "output_tokens", 0) or 0),
                        "cached": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
                    }

            record = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "session_id": self._session_id,
                "turn": turn_number,
                "type": turn_type,
                "model": self.manifest.model.preferred,
                "tokens": tokens,
                "tools_used": tools_used or [],
                "duration_ms": duration_ms,
            }

            session_log = self._session_log_dir / f"{self._session_id}.jsonl"
            with open(session_log, "a") as f:
                f.write(json.dumps(record) + "\n")
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
        # Build a case-insensitive lookup: lowered name → canonical name
        # This handles M2.7 emitting "Memory_Search" instead of "memory_search"
        name_lookup = {n.lower().replace("-", "_"): n for n in registered}

        def _normalize_tool_name(raw: str | None) -> str | None:
            """Normalize a tool name to its registered canonical form."""
            if not raw:
                return None
            if raw in registered:
                return raw
            return name_lookup.get(raw.lower().replace("-", "_"))

        # Extract all JSON objects from the text (handles nested braces)
        for candidate in self._extract_json_objects(text):
            try:
                obj = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue

            if not isinstance(obj, dict):
                continue

            # Format 1: {"name": "tool", "arguments": {...}}
            name = _normalize_tool_name(obj.get("name"))
            args = obj.get("arguments", {})

            # Format 2: {"type": "function", "function": {"name": "tool", "parameters": {...}}}
            if not name and isinstance(obj.get("function"), dict):
                fn = obj["function"]
                name = _normalize_tool_name(fn.get("name"))
                args = fn.get("parameters", fn.get("arguments", {}))

            if not name:
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
        # Uses brace-counting to handle content with embedded } characters.
        if not blocks:
            # First, extract full blocks between [TOOL_CALL] and [/TOOL_CALL]
            tc_start = 0
            while True:
                start_idx = text.find("[TOOL_CALL]", tc_start)
                if start_idx == -1:
                    break
                end_idx = text.find("[/TOOL_CALL]", start_idx)
                if end_idx == -1:
                    break
                block_text = text[start_idx + len("[TOOL_CALL]"):end_idx].strip()
                tc_start = end_idx + len("[/TOOL_CALL]")

                # Extract tool name: tool => "name"
                name_match = re.search(r'tool\s*=>\s*"([^"]+)"', block_text)
                if not name_match:
                    continue
                name = _normalize_tool_name(name_match.group(1))
                if not name:
                    continue

                # Find args => { ... } using brace-counting
                args_marker = block_text.find("args")
                if args_marker == -1:
                    continue
                brace_start = block_text.find("{", args_marker)
                if brace_start == -1:
                    continue
                # Count braces to find the matching close
                depth = 0
                in_str = False
                esc = False
                args_end = brace_start
                for ci in range(brace_start, len(block_text)):
                    c = block_text[ci]
                    if esc:
                        esc = False
                    elif c == '\\' and in_str:
                        esc = True
                    elif c == '"' and not esc:
                        in_str = not in_str
                    elif not in_str:
                        if c == '{':
                            depth += 1
                        elif c == '}':
                            depth -= 1
                            if depth == 0:
                                args_end = ci
                                break
                args_body = block_text[brace_start + 1:args_end].strip()

                # Try JSON parse first (M2.7 sometimes puts JSON in TOOL_CALL)
                try:
                    args = json.loads("{" + args_body + "}")
                except (json.JSONDecodeError, ValueError):
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

        # Fallback: XML-style tool calls — permissive scanner.
        # M2.7 emits several XML variants, often malformed:
        #   <minimax:tool_call><invoke name="X">...</invoke></minimax:tool_call>
        #   <invoke name="X">...</invoke>  (no wrapper)
        #   <invoke name="X">\n</invoke>   (no params, missing closing)
        # Rather than requiring exact format, we scan for ANY <invoke name="...">
        # and extract whatever parameters follow before the next invoke or end.
        if not blocks:
            # Find all <invoke name="tool_name"> occurrences
            invoke_re = re.compile(
                r'<invoke\s+name="([^"]+)">\s*(.*?)(?:</invoke>|(?=<invoke\s)|$)',
                re.DOTALL,
            )
            for match in invoke_re.finditer(text):
                name = _normalize_tool_name(match.group(1))
                if not name:
                    continue
                # Parse <parameter name="key">value</parameter> pairs
                args = {}
                param_re = re.compile(
                    r'<parameter\s+name="([^"]+)">(.*?)</parameter>',
                    re.DOTALL,
                )
                for pm in param_re.finditer(match.group(2)):
                    val = pm.group(2).strip()
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
        """Parse --key value or --key \"value\" pairs into a dict.

        Handles escaped quotes inside quoted values so long content
        (like memory_write bodies) isn't truncated at embedded quotes.
        """
        result = {}
        # First try: --key "value with \"escaped\" quotes"
        # Use a manual scan for quoted values to handle escapes properly
        i = 0
        while i < len(text):
            m = re.match(r'--(\w+)\s+', text[i:])
            if not m:
                i += 1
                continue
            key = m.group(1)
            i += m.end()
            if i < len(text) and text[i] == '"':
                # Scan for closing quote, respecting escaped quotes
                i += 1  # skip opening quote
                value_chars = []
                while i < len(text):
                    if text[i] == '\\' and i + 1 < len(text) and text[i + 1] == '"':
                        value_chars.append('"')
                        i += 2
                    elif text[i] == '"':
                        i += 1  # skip closing quote
                        break
                    else:
                        value_chars.append(text[i])
                        i += 1
                value = ''.join(value_chars)
            else:
                # Unquoted value — grab until whitespace
                end = i
                while end < len(text) and not text[end].isspace():
                    end += 1
                value = text[i:end]
                i = end
            # Type coercion
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
            try:
                result = await self._execute_one_tool(b)
            except Exception as e:
                logger.error(
                    "[%s] Write tool %s failed: %s",
                    self.manifest.mind_id, b.name, e,
                )
                result = f"ERROR: Tool {b.name} failed: {e}"
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

    @property
    def token_usage_stats(self) -> dict:
        """Accumulated token usage statistics for this session."""
        return {
            "session_id": self._session_id or "unknown",
            "api_calls": self._session_api_calls,
            "total_input_tokens": self._session_total_input_tokens,
            "total_output_tokens": self._session_total_output_tokens,
            "total_thinking_tokens": self._session_total_thinking_tokens,
            "estimated_cost_usd": round(self._session_total_cost_usd, 6),
            "token_log_path": str(self._token_log_path),
            "session_log_dir": str(self._session_log_dir),
        }

    @property
    def token_log_path(self) -> Path:
        """Path to the token usage JSONL log."""
        return self._token_log_path

    @property
    def session_log_dir(self) -> Path:
        """Path to the session logs directory."""
        return self._session_log_dir

    def clear_history(self) -> None:
        """Clear conversation history (keeps session_id)."""
        self._messages = []

    def stop(self) -> None:
        """Signal the tool loop to exit after the current iteration."""
        self._running = False
