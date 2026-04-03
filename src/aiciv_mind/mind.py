"""
Mind — the core agent loop for aiciv-mind.

Uses OpenAI-compatible API via LiteLLM proxy (default: localhost:4000).
LiteLLM translates OpenAI chat format to Ollama, OpenRouter, or any other backend.

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

from openai import AsyncOpenAI


# ---------------------------------------------------------------------------
# Response normalization — adapts OpenAI ChatCompletion to the Anthropic-like
# interface (.content list of blocks, .stop_reason, .usage) that the rest of
# mind.py relies on.  This lets us swap the SDK without touching parsing code.
# ---------------------------------------------------------------------------

class _TextBlock:
    __slots__ = ("type", "text")
    def __init__(self, text: str):
        self.type = "text"
        self.text = text

class _ToolUseBlock:
    __slots__ = ("type", "id", "name", "input")
    def __init__(self, id: str, name: str, input: dict):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input

class _NormalizedUsage:
    __slots__ = ("input_tokens", "output_tokens",
                 "cache_read_input_tokens", "cache_creation_input_tokens")
    def __init__(self, openai_usage: Any):
        self.input_tokens = getattr(openai_usage, "prompt_tokens", 0) or 0
        self.output_tokens = getattr(openai_usage, "completion_tokens", 0) or 0
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0

class _NormalizedResponse:
    """Adapts an OpenAI ChatCompletion to the Anthropic-like interface."""
    __slots__ = ("content", "stop_reason", "usage", "_raw_tool_calls")

    def __init__(self, openai_response: Any):
        choice = openai_response.choices[0]
        msg = choice.message

        self.content: list = []
        if msg.content:
            self.content.append(_TextBlock(msg.content))

        self._raw_tool_calls = msg.tool_calls or []
        for tc in self._raw_tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    args = {}
            self.content.append(_ToolUseBlock(
                id=tc.id,
                name=tc.function.name,
                input=args,
            ))

        # Normalize finish_reason → Anthropic-style stop_reason
        fr = choice.finish_reason
        if fr == "tool_calls":
            self.stop_reason = "tool_use"
        elif fr == "stop":
            self.stop_reason = "end_turn"
        else:
            self.stop_reason = fr or "end_turn"

        self.usage = _NormalizedUsage(openai_response.usage) if openai_response.usage else None

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
    Core agent loop. Loads a manifest, connects to LiteLLM proxy via OpenAI SDK,
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
        model_router=None,  # Optional ModelRouter for dynamic model selection
    ) -> None:
        self.manifest = manifest
        self.memory = memory
        self.bus = bus
        self._tools = tools or ToolRegistry.default(memory_store=memory)
        self._model_router = model_router
        self._current_task: str = ""  # Track for model router outcome recording
        self._memory_selector = None  # P2-8: AI-powered memory relevance selection

        # P3-5: Pattern detector — observes tool calls for self-improvement
        from aiciv_mind.pattern_detector import PatternDetector
        self._pattern_detector = PatternDetector(agent_id=manifest.mind_id)

        # P3-6: KAIROS — append-only daily log for persistent minds
        from aiciv_mind.kairos import KairosLog
        _mind_root = Path(__file__).parent.parent.parent
        self._kairos = KairosLog(
            data_dir=_mind_root / "data" / "logs",
            agent_id=manifest.mind_id,
        )

        # Attach hook governance if configured
        if manifest.hooks.enabled:
            from aiciv_mind.tools.hooks import HookRunner
            _mind_root = Path(__file__).parent.parent.parent
            hooks = HookRunner(
                blocked_tools=manifest.hooks.blocked_tools,
                log_all=manifest.hooks.log_all,
                audit_log_path=str(_mind_root / "data" / "tool_audit.jsonl"),
            )
            self._tools.set_hooks(hooks)
        self._client = AsyncOpenAI(
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

        # Register verify_completion tool
        from aiciv_mind.tools.verification_tools import register_verification_tools
        register_verification_tools(self._tools, self._completion_protocol)

        # Apply role-based tool filtering (Design Principle 5: structural constraint).
        # This ensures the LLM never sees tools outside its role's whitelist.
        # Only filter when the role is a recognized hierarchy level (primary/team_lead/agent).
        try:
            role = manifest.parsed_role()
            self._tools = self._tools.filter_by_role(role)
            logger.info(
                "[%s] Role-based filtering applied: role=%s, %d tools available",
                manifest.mind_id, role.value, len(self._tools.names()),
            )
        except (ValueError, AttributeError, KeyError):
            # Free-form role string (e.g. "worker") or mock manifest — skip filtering
            logger.debug(
                "[%s] Role '%s' is not a hierarchy level — skipping tool filtering",
                manifest.mind_id, getattr(manifest, 'role', 'unknown'),
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

        self._current_task = task  # for model router classification

        # Wrap entire task execution in mind_context so that any code
        # in the call stack can call current_mind_id() to identify which
        # mind is executing (critical for concurrent sub-minds).
        async with mind_context(self.manifest.mind_id):
            return await self._run_task_body(task, inject_memories)

    async def _run_task_body(self, task: str, inject_memories: bool) -> str:
        """Task execution body — always runs inside a mind_context scope."""

        # P3-6: KAIROS — log task start
        try:
            task_preview = task[:120].replace("\n", " ")
            self._kairos.append(f"Task started: {task_preview}")
        except Exception:
            pass  # KAIROS is observability — never crashes the loop

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
            memory_context = await self._inject_memories(task)
            if memory_context:
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

        tools_list = self._tools.build_openai_tools(
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

            # Compaction check: if messages exceed token threshold, compact.
            # Use the LOWER of compaction.max_context_tokens and 80% of model
            # context window — prevents the "50K threshold vs 16K model" mismatch
            # that caused Root's daemon stall (2026-04-02).
            _compact_limit = self.manifest.compaction.max_context_tokens
            if self.manifest.model.max_tokens > 0:
                _model_limit = int(self.manifest.model.max_tokens * 0.75)
                _compact_limit = min(_compact_limit, _model_limit)
            if (self.manifest.compaction.enabled
                    and self._context_manager
                    and self._context_manager.should_compact(
                        self._messages,
                        _compact_limit,
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
            if self._context_manager:
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

            # Append assistant response to history (OpenAI chat format)
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": None}
            text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
            if text_parts:
                assistant_msg["content"] = "\n".join(text_parts)
            if response._raw_tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in response._raw_tool_calls
                ]
            self._messages.append(assistant_msg)

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

            # Log tool detection path for diagnostics
            logger.info(
                "[%s] Tool blocks found: %d (%s), stop_reason=%s",
                self.manifest.mind_id,
                len(tool_use_blocks),
                "synthetic" if synthetic_calls else "native",
                getattr(response, "stop_reason", "?"),
            )

            # IMPORTANT: If tool_use blocks are present, ALWAYS execute them.
            # Previously this had a check: if native blocks + stop_reason=="end_turn" → break.
            # That was wrong — Ollama/LiteLLM returns stop_reason="end_turn" even when
            # tool_use blocks are intentional (Ollama doesn't set stop_reason="tool_use").
            # For Anthropic Claude, native tool_use blocks always come with
            # stop_reason="tool_use", so this change is a no-op for Claude.

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

                # ── Coordination metrics (P7 Loop 2: fitness scoring) ──────
                # Record coordination metrics when spawn/delegation tools are used.
                # This feeds the fitness scoring system that was previously dead code.
                try:
                    from aiciv_mind.fitness import CoordinationMetrics
                    is_error = "ERROR:" in result_content
                    if b.name == "spawn_team_lead":
                        role = self.manifest.parsed_role()
                        self._session_learner.record_coordination(CoordinationMetrics(
                            role=role,
                            delegation_target=b.input.get("mind_id", ""),
                            delegation_correct=None if is_error else True,
                            delegation_latency_ms=tool_exec_ms,
                        ))
                    elif b.name == "spawn_agent":
                        role = self.manifest.parsed_role()
                        self._session_learner.record_coordination(CoordinationMetrics(
                            role=role,
                            agent_spawned=b.input.get("mind_id", ""),
                            agent_selection_correct=None if is_error else True,
                            delegation_latency_ms=tool_exec_ms,
                        ))
                    elif b.name == "send_message":
                        role = self.manifest.parsed_role()
                        self._session_learner.record_coordination(CoordinationMetrics(
                            role=role,
                            result_synthesized=True,
                        ))
                except (ValueError, AttributeError, KeyError):
                    pass  # Free-form roles or mock manifests — skip coordination tracking

            if synthetic_calls:
                # For text-embedded tool calls, inject results as plain text
                # so the model sees them naturally (it never produced tool_use IDs)
                result_text = "\n".join(
                    f"[Tool result: {b.name}]\n{r['content']}"
                    for b, r in zip(tool_use_blocks, tool_results)
                )
                self._messages.append({"role": "user", "content": result_text})
            else:
                # OpenAI format: each tool result is a separate message
                for r in tool_results:
                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": r["tool_use_id"],
                        "content": r["content"],
                    })

        self._running = False

        # P9 — Auto-verify completion claims
        if final_text and self._completion_protocol._enabled:
            from aiciv_mind.tools.verification_tools import auto_verify_response, format_challenge_injection

            # Collect tool result strings for evidence extraction
            _tool_result_strs = []
            for msg in self._messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                # OpenAI format: tool results are role="tool" messages
                if role == "tool" and isinstance(content, str):
                    _tool_result_strs.append(content)
                elif isinstance(content, str) and "[Tool result:" in content:
                    _tool_result_strs.append(content)

            _complexity = getattr(self, "_current_complexity", "simple")
            _verification = auto_verify_response(
                protocol=self._completion_protocol,
                response_text=final_text,
                task=task,
                tool_results=_tool_result_strs,
                complexity=_complexity,
            )

            if _verification and not _verification["passed"]:
                _challenge_text = format_challenge_injection(_verification)
                if _challenge_text:
                    logger.info(
                        "[P9] Injecting %d challenges back into context",
                        len(_verification.get("challenges", [])),
                    )
                    # Inject challenges as a system note in messages
                    self._messages.append({
                        "role": "user",
                        "content": _challenge_text,
                    })

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

            # Record agent-level coordination metrics (tool effectiveness)
            try:
                role = self.manifest.parsed_role()
                from aiciv_mind.fitness import CoordinationMetrics
                from aiciv_mind.roles import Role
                if role == Role.AGENT:
                    self._session_learner.record_coordination(CoordinationMetrics(
                        role=role,
                        tools_attempted=tool_call_count,
                        tools_succeeded=tool_call_count - len(tool_errors),
                        task_completed=outcome.succeeded,
                    ))
            except (ValueError, AttributeError, KeyError):
                pass  # Free-form roles — skip
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

        # P3-5: Log detected patterns at task end
        patterns = []
        try:
            patterns = self._pattern_detector.detected_patterns()
            if patterns:
                _mind_root = Path(__file__).parent.parent.parent
                self._pattern_detector.to_jsonl(
                    _mind_root / "data" / "patterns.jsonl",
                )
                logger.info(
                    "[P3-5] %d pattern(s) detected: %s",
                    len(patterns),
                    "; ".join(p.description for p in patterns[:3]),
                )
        except Exception:
            pass  # Pattern detection is observability — never crashes

        # P3-6: KAIROS — log task completion + any pattern alerts
        try:
            task_preview = task[:80].replace("\n", " ")
            self._kairos.append(
                f"Task completed: {task_preview} ({tool_call_count} tool calls)",
            )
            if patterns:
                for p in patterns[:3]:
                    self._kairos.append(
                        f"Pattern: {p.description}", level="warn",
                    )
        except Exception:
            pass  # KAIROS is observability — never crashes

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

    # ------------------------------------------------------------------
    # Memory injection (extracted for readability — P2-8 integration)
    # ------------------------------------------------------------------

    _STOP_WORDS: set[str] = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "and", "or", "not", "no", "but", "if", "then", "so", "as",
        "this", "that", "it", "its", "my", "your", "our", "their",
        "what", "which", "who", "whom", "how", "when", "where", "why",
        "all", "each", "every", "any", "some", "i", "you", "we", "they",
    }

    async def _inject_memories(self, task: str) -> str:
        """
        Search memories relevant to the task, optionally rerank with AI selector,
        touch accessed memories, and return formatted context string (or "").
        """
        max_memories = self.manifest.memory.max_context_memories

        # Phase 1: Direct FTS5 search on task text
        memories = self.memory.search(
            query=task,
            agent_id=self.manifest.mind_id,
            limit=max_memories,
        )
        seen_ids = {m["id"] for m in memories}

        # Phase 2: Broaden search with extracted keywords if budget remains
        if len(memories) < max_memories:
            words = [w for w in task.lower().split() if w not in self._STOP_WORDS and len(w) > 2]
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

        # Phase 3 (P2-8): AI-powered reranking if selector available
        if memories and self._memory_selector and len(memories) > max_memories:
            try:
                memories = await self._memory_selector.select(
                    task, memories, top_k=max_memories,
                )
            except Exception as e:
                logger.debug("MemorySelector failed, using FTS5 order: %s", e)

        if not memories:
            return ""

        # Touch accessed memories (update depth signals)
        for m in memories:
            self.memory.touch(m["id"])

        if self._context_manager:
            return self._context_manager.format_search_results(memories)

        context = (
            "\n\n## Relevant memories from prior sessions:\n"
            "*These memories are HINTS, not facts. Verify before asserting.*\n"
        )
        for m in memories:
            created = m.get("created_at", "unknown")
            context += f"\n### {m['title']}  *(written {created})*\n{m['content']}\n"
        return context

    async def _call_model(self, system_prompt: str, tools_list: list[dict]) -> Any:
        """Single API call with current message history (OpenAI chat format)."""
        # Model selection: use router if available, else manifest default
        model_id = self.manifest.model.preferred
        if self._model_router is not None and self._current_task:
            try:
                model_id = self._model_router.select(self._current_task)
            except Exception as e:
                logger.debug("ModelRouter.select failed, using default: %s", e)

        # OpenAI format: system prompt is the first message
        api_messages = [{"role": "system", "content": system_prompt}] + self._messages

        kwargs: dict[str, Any] = dict(
            model=model_id,
            max_tokens=self.manifest.model.max_tokens,
            temperature=self.manifest.model.temperature,
            messages=api_messages,
        )
        if tools_list:
            kwargs["tools"] = tools_list

        t0 = time.monotonic()
        timeout = self.manifest.model.call_timeout_s
        coro = self._client.chat.completions.create(**kwargs)
        if timeout > 0:
            try:
                raw_response = await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                latency_ms = int((time.monotonic() - t0) * 1000)
                logger.error(
                    "[%s] Model call TIMED OUT after %.0fs (%dms). "
                    "Context may be too large for model.",
                    self.manifest.mind_id, timeout, latency_ms,
                )
                raise
        else:
            raw_response = await coro
        latency_ms = int((time.monotonic() - t0) * 1000)

        response = _NormalizedResponse(raw_response)
        self._log_cache_stats(response)
        self._log_token_usage(response, latency_ms)
        return response

    def _log_cache_stats(self, response: Any) -> None:
        """
        Log prompt cache hit/miss from API response usage metadata.

        LiteLLM surfaces cache stats from OpenRouter/MiniMax in the
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

            # Format 3: {"tool": "tool_name", "arguments": {...}} or "args": {...}
            # MiniMax M2.7 emits this inside <minimax:tool_call> wrappers
            if not name:
                name = _normalize_tool_name(obj.get("tool"))
                if name:
                    args = obj.get("arguments", obj.get("args", {}))

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

    # Max chars in a single tool result before truncation.
    # 30K chars ≈ 7500 tokens — keeps any single result from blowing context.
    _MAX_TOOL_RESULT_CHARS: int = 30_000

    async def _execute_one_tool(self, block: Any) -> str:
        """Execute a single tool_use block. Returns string result.
        Applies tools_config.exec_timeout_s to prevent runaway commands.
        Truncates oversized results to _MAX_TOOL_RESULT_CHARS."""
        tool_input = block.input if hasattr(block, "input") else {}
        logger.info("[%s] Tool: %s(%s)", self.manifest.mind_id, block.name, str(tool_input)[:100])
        timeout = self.manifest.tools_config.exec_timeout_s
        t0 = time.monotonic()
        coro = self._tools.execute(block.name, tool_input)
        if timeout > 0:
            try:
                result = await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                dur_ms = int((time.monotonic() - t0) * 1000)
                logger.error(
                    "[%s] Tool %s TIMED OUT after %.0fs",
                    self.manifest.mind_id, block.name, timeout,
                )
                self._pattern_detector.observe(
                    block.name, is_error=True, duration_ms=dur_ms,
                )
                return f"ERROR: Tool {block.name} timed out after {timeout}s"
        else:
            result = await coro
        dur_ms = int((time.monotonic() - t0) * 1000)
        result = str(result)
        is_error = "ERROR:" in result
        self._pattern_detector.observe(
            block.name, is_error=is_error, duration_ms=dur_ms,
        )
        if len(result) > self._MAX_TOOL_RESULT_CHARS:
            truncated_len = len(result)
            result = (
                result[:self._MAX_TOOL_RESULT_CHARS]
                + f"\n\n... [TRUNCATED: {truncated_len} chars → {self._MAX_TOOL_RESULT_CHARS}]"
            )
            logger.warning(
                "[%s] Tool %s result truncated: %d → %d chars",
                self.manifest.mind_id, block.name, truncated_len, self._MAX_TOOL_RESULT_CHARS,
            )
        logger.debug("[%s] Tool result: %s", self.manifest.mind_id, result[:200])
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
