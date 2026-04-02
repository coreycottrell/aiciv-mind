"""
aiciv_mind.context — Per-mind identity isolation via Python contextvars.

When multiple minds execute concurrently (e.g., Root + sub-minds in the same
process), shared utilities like memory search and tool logging need to know
*which* mind is calling. This module provides that identity without passing
`mind_id` through every function signature.

Usage:

    from aiciv_mind.context import mind_context, current_mind_id

    async with mind_context("research-lead"):
        # Any code in this scope can call current_mind_id()
        print(current_mind_id())  # → "research-lead"

    # Outside any context:
    print(current_mind_id())  # → None
"""

from __future__ import annotations

import contextvars
from contextlib import asynccontextmanager
from typing import AsyncIterator

# The ContextVar — stores the mind_id for the current async execution path.
# Each asyncio task gets its own copy automatically (contextvars semantics).
_CURRENT_MIND_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_mind_id", default=None
)


def current_mind_id() -> str | None:
    """Return the mind_id of the currently executing mind, or None if outside a mind context."""
    return _CURRENT_MIND_ID.get()


def set_mind_id(mind_id: str) -> contextvars.Token[str | None]:
    """
    Explicitly set the current mind ID. Returns a token for resetting.

    Prefer `mind_context()` for scoped usage. This is for cases where you need
    manual control (e.g., synchronous code paths, test fixtures).
    """
    return _CURRENT_MIND_ID.set(mind_id)


def reset_mind_id(token: contextvars.Token[str | None]) -> None:
    """Reset mind ID using a token from set_mind_id()."""
    _CURRENT_MIND_ID.reset(token)


@asynccontextmanager
async def mind_context(mind_id: str) -> AsyncIterator[None]:
    """
    Async context manager that scopes a mind_id to the current execution path.

    All code running within this scope (including nested async calls) will see
    `current_mind_id()` return the given mind_id. On exit, the previous value
    is restored — safe for nesting.

    Example:
        async with mind_context("root"):
            assert current_mind_id() == "root"
            async with mind_context("sub-mind-1"):
                assert current_mind_id() == "sub-mind-1"
            assert current_mind_id() == "root"
    """
    token = _CURRENT_MIND_ID.set(mind_id)
    try:
        yield
    finally:
        _CURRENT_MIND_ID.reset(token)
