"""
aiciv_mind.context_manager — Context window management for aiciv-mind.

Translates BootContext + per-turn memory search results into formatted
strings that get injected into the system prompt.

## Cache-Optimal Ordering (critical for MiniMax M2.7 / OpenRouter prefix caching)

The system prompt is assembled in this exact order in mind.py:

    [1] STATIC  — base system prompt from manifest (identity, principles, role)
    [2] STABLE  — boot context: session header, identity memories, handoff, pinned
    [3] SEMI-STABLE — per-turn search results (changes with each query)
    [4] DYNAMIC — conversation history / user message (not in system prompt)

Rule: static content MUST come before dynamic content.
Any reversal invalidates the cached prefix, forcing a full re-ingestion of the prompt.

MiniMax M2.7 via OpenRouter uses automatic prefix caching (~80% cost reduction on hits).
`cache_control` params are dropped by the LiteLLM config, so we rely entirely on prefix
stability rather than explicit cache breakpoints.

Optimization target: keep layers 1 and 2 identical across turns within a session.
Layer 3 may change per turn but only affects the tail — cache is not invalidated for
layers 1+2.

Design goals:
- Identity anchors always injected (the mind knows who it is)
- Last handoff always injected (the mind knows what it was doing)
- Per-turn relevance search injected until 80% token budget
- Token estimation is rough (len//4) — good enough for budget tracking
"""

from __future__ import annotations

from aiciv_mind.session_store import BootContext


# Rough tokens-per-char estimate for budget tracking
_CHARS_PER_TOKEN = 4


class ContextManager:
    """
    Formats memory context for injection into the system prompt.

    Usage:
        ctx = ContextManager(max_context_memories=10, model_max_tokens=8192)
        boot_str = ctx.format_boot_context(boot)
        # prepend boot_str to system prompt at startup

        per_turn_str = ctx.format_search_results(search_results)
        # prepend per_turn_str to system prompt each turn
    """

    # Circuit breaker: after this many consecutive compaction failures,
    # disable compaction for the rest of the session.  Stolen from CC
    # (CC-INHERIT I-3) — they discovered this the hard way (250K wasted
    # API calls/day from runaway compaction loops).
    MAX_CONSECUTIVE_COMPACTION_FAILURES: int = 3

    def __init__(
        self,
        max_context_memories: int = 10,
        model_max_tokens: int = 4096,
        scratchpad_dir: str | None = None,
    ) -> None:
        self._max_memories = max_context_memories
        # Reserve 80% of token budget for memory injection
        self._budget_chars = int(model_max_tokens * 0.80) * _CHARS_PER_TOKEN
        self._scratchpad_dir = scratchpad_dir
        # Circuit breaker state
        self._consecutive_compaction_failures: int = 0
        self._compaction_disabled: bool = False

    # ------------------------------------------------------------------
    # Boot context formatting
    # ------------------------------------------------------------------

    def format_boot_context(
        self, boot: BootContext, context_mode: str = "full"
    ) -> str:
        """
        Return a formatted string to prepend to the system prompt at startup.

        context_mode:
            "full"    — All sections: identity, handoff, pinned, evolution, core knowledge, scratchpad.
            "minimal" — Session header only. For ephemeral read-only agents.

        Sections (full mode):
        1. Session header (session_id, count)
        2. Identity memories (who I am)
        3. Last handoff (what I was doing)
        4. Pinned memories (always-on context)
        5. Evolution trajectory
        6. Core knowledge
        7. Daily scratchpad
        """
        parts: list[str] = []

        # Session header — always included, even in minimal mode
        parts.append(
            f"## Session Context\n"
            f"Session ID: {boot.session_id} | "
            f"Prior sessions completed: {boot.session_count}"
        )

        if context_mode == "minimal":
            # Minimal mode: session header only — no identity, no memories
            if len(parts) == 1:
                return ""
            return "\n\n".join(parts) + "\n\n---\n\n"

        # ── Full mode: load everything ────────────────────────────────

        # Identity
        if boot.identity_memories:
            parts.append("## My Identity")
            for m in boot.identity_memories[: self._max_memories]:
                parts.append(f"### {m['title']}\n{m['content']}")

        # Handoff — what I was doing last session
        if boot.handoff_memory:
            parts.append("## Previous Session Handoff")
            parts.append(boot.handoff_memory["content"])

        # Pinned
        if boot.pinned_memories:
            parts.append("## Pinned Context (always loaded)")
            for m in boot.pinned_memories[: self._max_memories]:
                parts.append(f"### {m['title']}\n{m['content']}")

        # Evolution trajectory — "what was I becoming?"
        if boot.evolution_trajectory:
            parts.append(f"## Evolution Trajectory\n{boot.evolution_trajectory}")

        # Core knowledge — highest-depth memories
        if boot.top_by_depth_memories:
            parts.append("## Core Knowledge (most relied-upon memories)")
            for m in boot.top_by_depth_memories:
                access_count = m.get("access_count", 0)
                parts.append(f"### {m['title']}  *(accessed {access_count}x)*\n{m['content']}")

        # Daily scratchpad — working notes from today
        if self._scratchpad_dir:
            from datetime import date
            from pathlib import Path
            scratchpad_path = Path(self._scratchpad_dir) / f"{date.today().isoformat()}.md"
            if scratchpad_path.exists():
                content = scratchpad_path.read_text().strip()
                if content:
                    parts.append(f"## Today's Scratchpad\n{content}")

        if len(parts) == 1:
            # Only the header — nothing meaningful to inject
            return ""

        return "\n\n".join(parts) + "\n\n---\n\n"

    # ------------------------------------------------------------------
    # Per-turn search result formatting
    # ------------------------------------------------------------------

    def format_search_results(self, results: list[dict]) -> str:
        """
        Format FTS5 search results for per-turn injection.

        Injects up to max_memories results or until token budget is reached.
        Each memory includes its created_at timestamp so the mind can judge
        staleness.  A caveat header reminds the mind that memories are hints,
        not facts — verify before asserting.

        Returns empty string if no results.
        """
        if not results:
            return ""

        lines: list[str] = [
            "## Relevant memories from prior sessions:",
            (
                "*These memories are HINTS, not facts. They may be outdated, "
                "incomplete, or wrong. Before asserting something from memory, "
                "verify it directly (check the file, call the tool, test the claim). "
                "Timestamps show when each memory was written — older = higher "
                "staleness risk.*"
            ),
        ]
        chars_used = sum(len(ln) for ln in lines)

        for m in results[: self._max_memories]:
            created = m.get("created_at", "unknown")
            entry = f"\n### {m['title']}  *(written {created})*\n{m['content']}\n"
            if chars_used + len(entry) > self._budget_chars:
                break
            lines.append(entry)
            chars_used += len(entry)

        if len(lines) <= 2:
            # Only the header + caveat — no actual memories fit
            return ""

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Context compaction (preserve-recent-N pattern from clawd-code)
    # ------------------------------------------------------------------

    def should_compact(self, messages: list[dict], max_tokens: int) -> bool:
        """
        Check if messages should be compacted.

        All conditions must be true:
        1. Circuit breaker not tripped (fewer than MAX_CONSECUTIVE_COMPACTION_FAILURES)
        2. More messages than preserve_recent + 2 (room for summary pair)
        3. Estimated token count exceeds threshold
        """
        if self._compaction_disabled:
            return False
        if len(messages) <= 6:  # minimum: need old messages + summary pair + recent
            return False
        total_chars = sum(self._message_chars(m) for m in messages)
        return total_chars // _CHARS_PER_TOKEN > max_tokens

    def compact_history(
        self,
        messages: list[dict],
        preserve_recent: int = 4,
        existing_summary: str = "",
    ) -> tuple[list[dict], str]:
        """
        Compact conversation history while preserving recent messages verbatim.

        Strategy:
        - Split messages into old (to summarize) and recent (to keep)
        - Build heuristic summary from old messages, merging with prior summaries
        - Return [summary_user, summary_assistant] + recent (maintains alternation)

        Circuit breaker: tracks consecutive failures. After
        MAX_CONSECUTIVE_COMPACTION_FAILURES, disables compaction for the session.

        Returns (compacted_messages, updated_summary_text).
        """
        try:
            result = self._do_compact(messages, preserve_recent, existing_summary)
            # Success — reset the failure counter
            self._consecutive_compaction_failures = 0
            return result
        except Exception:
            self._consecutive_compaction_failures += 1
            if self._consecutive_compaction_failures >= self.MAX_CONSECUTIVE_COMPACTION_FAILURES:
                self._compaction_disabled = True
            # On failure, return messages unchanged
            return messages, existing_summary

    def _do_compact(
        self,
        messages: list[dict],
        preserve_recent: int,
        existing_summary: str,
    ) -> tuple[list[dict], str]:
        """Core compaction logic — called by compact_history with circuit breaker wrapper."""
        if len(messages) <= preserve_recent + 2:
            return messages, existing_summary

        # Find split point: ensure recent block starts with a user message
        split = len(messages) - preserve_recent
        while split < len(messages) and messages[split].get("role") != "user":
            split += 1

        if split >= len(messages) - 1:
            return messages, existing_summary

        old_messages = messages[:split]
        recent_messages = messages[split:]

        summary = self._build_compaction_summary(old_messages, existing_summary)

        # Summary pair maintains user/assistant alternation
        compacted = [
            {
                "role": "user",
                "content": (
                    "[COMPACTED CONTEXT — earlier conversation summarized]\n\n"
                    f"{summary}\n\n"
                    "[Recent messages follow verbatim. Continue without re-asking questions.]"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "I have the compacted context from our earlier conversation. "
                    "Continuing from where we left off."
                ),
            },
        ] + recent_messages

        return compacted, summary

    def _build_compaction_summary(self, messages: list[dict], existing: str) -> str:
        """Build a heuristic summary from messages being compacted."""
        topics: list[str] = []
        tools_used: set[str] = set()
        key_outputs: list[str] = []

        for msg in messages:
            text = self._extract_message_text(msg)
            role = msg.get("role", "")

            if role == "user":
                first_line = text.split("\n")[0][:150].strip()
                if first_line and not first_line.startswith("[Tool result"):
                    topics.append(first_line)
                for line in text.split("\n"):
                    if line.startswith("[Tool result:"):
                        try:
                            tool_name = line.split(":")[1].split("]")[0].strip()
                            tools_used.add(tool_name)
                        except IndexError:
                            pass

            elif role == "assistant":
                if len(text) > 50:
                    key_outputs.append(text[:300])

        parts: list[str] = []
        if existing:
            parts.append(f"Prior context: {existing[:500]}")
        if topics:
            parts.append("Topics covered:\n" + "\n".join(f"- {t}" for t in topics[-8:]))
        if tools_used:
            parts.append(f"Tools used: {', '.join(sorted(tools_used))}")
        if key_outputs:
            parts.append("Key responses:\n" + "\n---\n".join(key_outputs[-3:]))

        return "\n\n".join(parts) if parts else "Previous conversation context."

    @staticmethod
    def _extract_message_text(msg: dict) -> str:
        """Extract plain text from a message dict (handles str, list, content blocks)."""
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if hasattr(block, "text"):
                    parts.append(block.text)
                elif isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        parts.append(block.get("content", ""))
            return "\n".join(parts)
        return str(content)

    @staticmethod
    def _message_chars(msg: dict) -> int:
        """Estimate character count of a message."""
        content = msg.get("content", "")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            total = 0
            for block in content:
                if hasattr(block, "text"):
                    total += len(block.text)
                elif isinstance(block, dict):
                    total += len(str(block.get("content", "")))
                    total += len(str(block.get("text", "")))
            return total
        return len(str(content))

    # ------------------------------------------------------------------
    # Token budget helpers
    # ------------------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate: len(text) // 4."""
        return len(text) // _CHARS_PER_TOKEN

    def has_budget(self, used_chars: int) -> bool:
        """True if more context can be injected without exceeding 80% budget."""
        return used_chars < self._budget_chars
