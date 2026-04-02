"""Tests for aiciv_mind.context — per-mind identity isolation via contextvars."""

from __future__ import annotations

import asyncio

import pytest

from aiciv_mind.context import current_mind_id, mind_context, set_mind_id, reset_mind_id


# ---------------------------------------------------------------------------
# Basic read/write
# ---------------------------------------------------------------------------


def test_default_is_none():
    """Outside any context, current_mind_id() returns None."""
    assert current_mind_id() is None


@pytest.mark.asyncio
async def test_mind_context_sets_and_restores():
    """mind_context sets the mind_id and restores it on exit."""
    assert current_mind_id() is None

    async with mind_context("root"):
        assert current_mind_id() == "root"

    assert current_mind_id() is None


@pytest.mark.asyncio
async def test_nested_contexts():
    """Nested mind_context restores correctly at each level."""
    async with mind_context("root"):
        assert current_mind_id() == "root"

        async with mind_context("sub-mind-1"):
            assert current_mind_id() == "sub-mind-1"

        assert current_mind_id() == "root"

    assert current_mind_id() is None


# ---------------------------------------------------------------------------
# Concurrent tasks — the whole point of contextvars
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_tasks_isolated():
    """
    Two concurrent async tasks each get their own mind_id,
    even when running on the same event loop.
    """
    seen_ids: dict[str, list[str | None]] = {"a": [], "b": []}

    async def worker(name: str, mind_id: str):
        async with mind_context(mind_id):
            seen_ids[name].append(current_mind_id())
            await asyncio.sleep(0.01)  # yield to other task
            seen_ids[name].append(current_mind_id())

    await asyncio.gather(
        worker("a", "research-lead"),
        worker("b", "memory-lead"),
    )

    assert seen_ids["a"] == ["research-lead", "research-lead"]
    assert seen_ids["b"] == ["memory-lead", "memory-lead"]


# ---------------------------------------------------------------------------
# Manual set/reset (for synchronous code paths)
# ---------------------------------------------------------------------------


def test_manual_set_and_reset():
    """set_mind_id / reset_mind_id work for synchronous code."""
    assert current_mind_id() is None

    token = set_mind_id("manual-mind")
    assert current_mind_id() == "manual-mind"

    reset_mind_id(token)
    assert current_mind_id() is None


# ---------------------------------------------------------------------------
# Exception safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_restores_on_exception():
    """mind_context restores previous value even if body raises."""
    assert current_mind_id() is None

    with pytest.raises(ValueError, match="boom"):
        async with mind_context("exploding-mind"):
            assert current_mind_id() == "exploding-mind"
            raise ValueError("boom")

    assert current_mind_id() is None
