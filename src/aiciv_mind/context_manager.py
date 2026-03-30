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

    def __init__(
        self,
        max_context_memories: int = 10,
        model_max_tokens: int = 4096,
    ) -> None:
        self._max_memories = max_context_memories
        # Reserve 80% of token budget for memory injection
        self._budget_chars = int(model_max_tokens * 0.80) * _CHARS_PER_TOKEN

    # ------------------------------------------------------------------
    # Boot context formatting
    # ------------------------------------------------------------------

    def format_boot_context(self, boot: BootContext) -> str:
        """
        Return a formatted string to prepend to the system prompt at startup.

        Sections:
        1. Session header (session_id, count)
        2. Identity memories (who I am)
        3. Last handoff (what I was doing)
        4. Pinned memories (always-on context)
        """
        parts: list[str] = []

        # Session header
        parts.append(
            f"## Session Context\n"
            f"Session ID: {boot.session_id} | "
            f"Prior sessions completed: {boot.session_count}"
        )

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
        Returns empty string if no results.
        """
        if not results:
            return ""

        lines: list[str] = ["## Relevant memories from prior sessions:"]
        chars_used = len(lines[0])

        for m in results[: self._max_memories]:
            entry = f"\n### {m['title']}\n{m['content']}\n"
            if chars_used + len(entry) > self._budget_chars:
                break
            lines.append(entry)
            chars_used += len(entry)

        if len(lines) == 1:
            return ""

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Token budget helpers
    # ------------------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate: len(text) // 4."""
        return len(text) // _CHARS_PER_TOKEN

    def has_budget(self, used_chars: int) -> bool:
        """True if more context can be injected without exceeding 80% budget."""
        return used_chars < self._budget_chars
