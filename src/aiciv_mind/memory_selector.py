"""
aiciv_mind.memory_selector — AI-powered memory relevance selection.

Uses a cheap/fast model call to rerank FTS5 search candidates and select
the most relevant memories for a given task.  This is the Phase 2 upgrade
from naive BM25-only injection.

Architecture:
  1. FTS5 search produces N candidate memories (existing code)
  2. MemorySelector receives candidates + task text
  3. Cheap model call (~256 tokens) scores each candidate
  4. Top-K highest-scored memories are selected for injection

Falls back to FTS5 order if the selector model call fails.

Usage:
    selector = MemorySelector(
        api_url="http://localhost:4000",
        api_key="sk-1234",
        model="ollama/phi3",
    )
    selected = await selector.select(task, candidates, top_k=5)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


class MemorySelector:
    """
    AI-powered memory relevance selector.

    Given a task and a list of candidate memories (from FTS5 search),
    uses a cheap model to score relevance and return the top-K most
    relevant memories.
    """

    # Default model for selection (should be cheap/fast)
    DEFAULT_MODEL = "ollama/phi3"

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_selection_tokens: int = 512,
        timeout_s: float = 10.0,
    ) -> None:
        self._api_url = api_url or os.environ.get("MIND_API_URL", "http://localhost:4000")
        self._api_key = api_key or os.environ.get("MIND_API_KEY", "sk-1234")
        self._model = model or self.DEFAULT_MODEL
        self._max_tokens = max_selection_tokens
        self._timeout_s = timeout_s
        # Stats
        self.calls: int = 0
        self.failures: int = 0
        self.total_latency_ms: int = 0

    async def select(
        self,
        task: str,
        candidates: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Select the top-K most relevant memories for the given task.

        Args:
            task: The user's task text
            candidates: List of memory dicts from FTS5 search (must have 'id', 'title', 'content')
            top_k: Number of memories to select

        Returns:
            List of selected memory dicts (subset of candidates), ordered by relevance.
            On failure, returns candidates[:top_k] (FTS5 order fallback).
        """
        if len(candidates) <= top_k:
            return candidates  # Nothing to select — all candidates fit

        # Build compact summaries for the selector
        summaries = []
        for i, mem in enumerate(candidates):
            title = mem.get("title", "(untitled)")
            content = mem.get("content", "")[:200]
            summaries.append(f"{i}: {title} — {content}")

        prompt = (
            "You are a memory relevance scorer. Given a task and a list of candidate memories, "
            "select the most relevant ones.\n\n"
            f"TASK: {task[:300]}\n\n"
            "CANDIDATE MEMORIES:\n"
            + "\n".join(summaries)
            + "\n\n"
            f"Return ONLY a JSON array of the {top_k} most relevant candidate indices "
            f"(0-based), ordered by relevance. Example: [2, 0, 5]\n"
            "JSON:"
        )

        t0 = time.monotonic()
        self.calls += 1

        try:
            client = anthropic.AsyncAnthropic(
                base_url=self._api_url,
                api_key=self._api_key,
            )

            coro = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )

            response = await asyncio.wait_for(coro, timeout=self._timeout_s)
            latency_ms = int((time.monotonic() - t0) * 1000)
            self.total_latency_ms += latency_ms

            # Parse the response — expect a JSON array of indices
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text

            selected_indices = self._parse_indices(text, len(candidates), top_k)

            if selected_indices:
                result = [candidates[i] for i in selected_indices if i < len(candidates)]
                logger.info(
                    "MemorySelector: selected %d/%d candidates in %dms (model: %s)",
                    len(result), len(candidates), latency_ms, self._model,
                )
                return result
            else:
                logger.warning(
                    "MemorySelector: failed to parse indices from model response, falling back"
                )
                self.failures += 1
                return candidates[:top_k]

        except Exception as e:
            latency_ms = int((time.monotonic() - t0) * 1000)
            self.total_latency_ms += latency_ms
            self.failures += 1
            logger.warning(
                "MemorySelector: model call failed (%dms): %s — falling back to FTS5 order",
                latency_ms, e,
            )
            return candidates[:top_k]

    @staticmethod
    def _parse_indices(text: str, max_index: int, top_k: int) -> list[int]:
        """
        Parse a JSON array of integers from model output.

        Handles common model output quirks:
        - Extra text before/after the JSON array
        - Markdown code blocks
        - Trailing commas

        Returns list of valid indices, or empty list on parse failure.
        """
        text = text.strip()

        # Strip markdown code blocks
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        # Find the JSON array in the text
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []

        array_text = text[start:end + 1]

        # Fix trailing comma before ]
        array_text = array_text.replace(",]", "]").replace(", ]", "]")

        try:
            parsed = json.loads(array_text)
        except json.JSONDecodeError:
            return []

        if not isinstance(parsed, list):
            return []

        # Filter to valid integer indices within range
        indices = []
        seen = set()
        for item in parsed:
            try:
                idx = int(item)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < max_index and idx not in seen:
                indices.append(idx)
                seen.add(idx)
            if len(indices) >= top_k:
                break

        return indices

    @property
    def stats(self) -> dict:
        """Return selector statistics."""
        avg_latency = self.total_latency_ms / self.calls if self.calls else 0
        return {
            "calls": self.calls,
            "failures": self.failures,
            "success_rate": (self.calls - self.failures) / self.calls if self.calls else 0.0,
            "avg_latency_ms": int(avg_latency),
        }
