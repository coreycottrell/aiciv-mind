"""
Tests for aiciv_mind.context_manager — context window management.

Covers: boot context formatting, search result injection with staleness caveat,
compaction (preserve-recent-N, circuit breaker), token budget helpers.
"""

from __future__ import annotations

import pytest

from aiciv_mind.context_manager import ContextManager, _CHARS_PER_TOKEN
from aiciv_mind.session_store import BootContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx() -> ContextManager:
    """Default ContextManager — 10 memories, 4096 model tokens."""
    return ContextManager(max_context_memories=10, model_max_tokens=4096)


@pytest.fixture
def minimal_boot() -> BootContext:
    """BootContext with identity + handoff populated."""
    return BootContext(
        session_id="sess-001",
        session_count=5,
        agent_id="test-mind",
        identity_memories=[
            {"title": "My Name", "content": "I am the test mind."},
        ],
        handoff_memory={"content": "Last session I was writing tests."},
        pinned_memories=[
            {"title": "Prime Directive", "content": "Always test your code."},
        ],
    )


@pytest.fixture
def empty_boot() -> BootContext:
    """BootContext with nothing except session metadata."""
    return BootContext(
        session_id="sess-empty",
        session_count=0,
        agent_id="empty-mind",
    )


def _make_messages(n: int, char_size: int = 100) -> list[dict]:
    """Build a list of alternating user/assistant messages."""
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"Message {i}: " + "x" * char_size})
    return msgs


# ---------------------------------------------------------------------------
# Tests: format_boot_context
# ---------------------------------------------------------------------------


def test_format_boot_context_has_session_header(ctx: ContextManager, minimal_boot: BootContext):
    """Boot context includes session ID and count."""
    result = ctx.format_boot_context(minimal_boot)
    assert "sess-001" in result
    assert "5" in result


def test_format_boot_context_has_identity(ctx: ContextManager, minimal_boot: BootContext):
    """Boot context includes identity memories."""
    result = ctx.format_boot_context(minimal_boot)
    assert "## My Identity" in result
    assert "My Name" in result
    assert "I am the test mind." in result


def test_format_boot_context_has_handoff(ctx: ContextManager, minimal_boot: BootContext):
    """Boot context includes handoff from last session."""
    result = ctx.format_boot_context(minimal_boot)
    assert "## Previous Session Handoff" in result
    assert "writing tests" in result


def test_format_boot_context_has_pinned(ctx: ContextManager, minimal_boot: BootContext):
    """Boot context includes pinned memories."""
    result = ctx.format_boot_context(minimal_boot)
    assert "## Pinned Context" in result
    assert "Prime Directive" in result


def test_format_boot_context_empty_returns_empty(ctx: ContextManager, empty_boot: BootContext):
    """Boot context with no memories returns empty string."""
    result = ctx.format_boot_context(empty_boot)
    assert result == ""


def test_format_boot_context_ends_with_separator(ctx: ContextManager, minimal_boot: BootContext):
    """Non-empty boot context ends with the --- separator."""
    result = ctx.format_boot_context(minimal_boot)
    assert result.endswith("---\n\n")


def test_format_boot_context_evolution_trajectory(ctx: ContextManager):
    """Boot context includes evolution trajectory when present."""
    boot = BootContext(
        session_id="sess-evo",
        session_count=10,
        agent_id="evo-mind",
        identity_memories=[{"title": "Id", "content": "test"}],
        evolution_trajectory="I am learning to plan better.",
    )
    result = ctx.format_boot_context(boot)
    assert "## Evolution Trajectory" in result
    assert "learning to plan better" in result


def test_format_boot_context_top_by_depth(ctx: ContextManager):
    """Boot context includes top-by-depth memories with access counts."""
    boot = BootContext(
        session_id="sess-depth",
        session_count=3,
        agent_id="depth-mind",
        identity_memories=[{"title": "Id", "content": "test"}],
        top_by_depth_memories=[
            {"title": "Key Pattern", "content": "Always use FTS5.", "access_count": 42},
        ],
    )
    result = ctx.format_boot_context(boot)
    assert "## Core Knowledge" in result
    assert "Key Pattern" in result
    assert "42" in result


def test_format_boot_context_respects_max_memories(ctx: ContextManager):
    """Identity memories are capped at max_context_memories."""
    small_ctx = ContextManager(max_context_memories=2, model_max_tokens=4096)
    boot = BootContext(
        session_id="s", session_count=0, agent_id="a",
        identity_memories=[
            {"title": f"Mem {i}", "content": f"Content {i}"} for i in range(5)
        ],
    )
    result = small_ctx.format_boot_context(boot)
    assert "Mem 0" in result
    assert "Mem 1" in result
    assert "Mem 2" not in result


# ---------------------------------------------------------------------------
# Tests: minimal context mode (P2-11)
# ---------------------------------------------------------------------------


def test_minimal_mode_skips_identity(ctx: ContextManager, minimal_boot: BootContext):
    """Minimal context mode skips identity memories."""
    full_result = ctx.format_boot_context(minimal_boot, context_mode="full")
    minimal_result = ctx.format_boot_context(minimal_boot, context_mode="minimal")

    assert "My Identity" in full_result
    assert "My Identity" not in minimal_result


def test_minimal_mode_skips_handoff(ctx: ContextManager, minimal_boot: BootContext):
    """Minimal context mode skips handoff."""
    full_result = ctx.format_boot_context(minimal_boot, context_mode="full")
    minimal_result = ctx.format_boot_context(minimal_boot, context_mode="minimal")

    assert "Previous Session" in full_result
    assert "Previous Session" not in minimal_result


def test_minimal_mode_skips_pinned(ctx: ContextManager, minimal_boot: BootContext):
    """Minimal context mode skips pinned memories."""
    full_result = ctx.format_boot_context(minimal_boot, context_mode="full")
    minimal_result = ctx.format_boot_context(minimal_boot, context_mode="minimal")

    assert "Pinned Context" in full_result
    assert "Pinned Context" not in minimal_result


def test_minimal_mode_returns_empty(ctx: ContextManager, minimal_boot: BootContext):
    """Minimal context mode returns empty — no identity context needed."""
    minimal_result = ctx.format_boot_context(minimal_boot, context_mode="minimal")
    assert minimal_result == ""


def test_minimal_mode_empty_boot_also_empty(ctx: ContextManager, empty_boot: BootContext):
    """Empty boot in minimal mode returns empty string."""
    result = ctx.format_boot_context(empty_boot, context_mode="minimal")
    assert result == ""


def test_full_mode_is_default(ctx: ContextManager, minimal_boot: BootContext):
    """Default context_mode is full (backward compatible)."""
    default_result = ctx.format_boot_context(minimal_boot)
    full_result = ctx.format_boot_context(minimal_boot, context_mode="full")
    assert default_result == full_result


# ---------------------------------------------------------------------------
# Tests: format_search_results — staleness caveat
# ---------------------------------------------------------------------------


def test_search_results_empty_returns_empty(ctx: ContextManager):
    """No search results → empty string."""
    assert ctx.format_search_results([]) == ""


def test_search_results_staleness_caveat(ctx: ContextManager):
    """Search results include the staleness caveat header."""
    results = [{"title": "Fact A", "content": "Something.", "created_at": "2026-03-01"}]
    text = ctx.format_search_results(results)
    assert "HINTS, not facts" in text
    assert "staleness risk" in text


def test_search_results_include_timestamp(ctx: ContextManager):
    """Each result shows its created_at timestamp."""
    results = [{"title": "Note", "content": "Data.", "created_at": "2026-02-15"}]
    text = ctx.format_search_results(results)
    assert "2026-02-15" in text


def test_search_results_respects_token_budget(ctx: ContextManager):
    """Search results stop injecting when budget is exhausted."""
    tiny_ctx = ContextManager(max_context_memories=100, model_max_tokens=50)
    # Budget = 50 * 0.80 * 4 = 160 chars. The header alone is ~250+ chars.
    results = [{"title": f"Big {i}", "content": "x" * 200} for i in range(5)]
    text = tiny_ctx.format_search_results(results)
    # Either empty (header exceeded budget alone, so no memories fit → "")
    # or very short.  At minimum, not all 5 should appear.
    assert text.count("Big") < 5


# ---------------------------------------------------------------------------
# Tests: compact_history — basic behavior
# ---------------------------------------------------------------------------


def test_compact_history_produces_summary(ctx: ContextManager):
    """Compaction of long history returns a summary string."""
    msgs = _make_messages(12, char_size=50)
    compacted, summary = ctx.compact_history(msgs, preserve_recent=4)
    assert summary  # non-empty summary text
    assert len(compacted) < len(msgs)


def test_compact_history_preserves_recent_default(ctx: ContextManager):
    """Default preserve_recent=4 keeps at least 4 recent messages."""
    msgs = _make_messages(12, char_size=50)
    compacted, _ = ctx.compact_history(msgs, preserve_recent=4)
    # compacted = [summary_user, summary_assistant] + recent
    # recent should have at least 4 messages
    recent_block = compacted[2:]  # skip summary pair
    assert len(recent_block) >= 4


def test_compact_history_preserves_configurable_recent(ctx: ContextManager):
    """preserve_recent=6 keeps at least 6 recent messages."""
    msgs = _make_messages(14, char_size=50)
    compacted, _ = ctx.compact_history(msgs, preserve_recent=6)
    recent_block = compacted[2:]
    assert len(recent_block) >= 6


def test_compact_history_summary_pair_roles(ctx: ContextManager):
    """First two messages in compacted output are user/assistant summary pair."""
    msgs = _make_messages(12, char_size=50)
    compacted, _ = ctx.compact_history(msgs, preserve_recent=4)
    assert compacted[0]["role"] == "user"
    assert compacted[1]["role"] == "assistant"
    assert "COMPACTED CONTEXT" in compacted[0]["content"]


def test_compact_history_merges_existing_summary(ctx: ContextManager):
    """An existing summary is incorporated into the new summary."""
    msgs = _make_messages(12, char_size=50)
    _, summary = ctx.compact_history(msgs, preserve_recent=4, existing_summary="Prior context: debugging session")
    assert "Prior context" in summary or "debugging" in summary


def test_compact_history_too_short_returns_unchanged(ctx: ContextManager):
    """Messages too short for compaction are returned unchanged."""
    msgs = _make_messages(4, char_size=50)
    compacted, summary = ctx.compact_history(msgs, preserve_recent=4)
    assert compacted == msgs
    assert summary == ""


# ---------------------------------------------------------------------------
# Tests: should_compact threshold
# ---------------------------------------------------------------------------


def test_should_compact_respects_threshold(ctx: ContextManager):
    """should_compact returns True only when estimated tokens exceed max_tokens."""
    small_msgs = _make_messages(8, char_size=10)
    # 8 messages * ~17 chars each ≈ 136 chars → ~34 tokens
    assert ctx.should_compact(small_msgs, max_tokens=1000) is False

    big_msgs = _make_messages(8, char_size=5000)
    # 8 messages * ~5012 chars each ≈ 40096 chars → ~10024 tokens
    assert ctx.should_compact(big_msgs, max_tokens=1000) is True


def test_should_compact_false_for_few_messages(ctx: ContextManager):
    """should_compact is False when there are 6 or fewer messages (even if large)."""
    msgs = _make_messages(6, char_size=50000)
    assert ctx.should_compact(msgs, max_tokens=100) is False


# ---------------------------------------------------------------------------
# Tests: circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_disables_after_max_failures(ctx: ContextManager):
    """After MAX_CONSECUTIVE_COMPACTION_FAILURES, compaction is disabled."""
    msgs = _make_messages(12, char_size=50)

    # Force failures by patching _do_compact to raise
    original = ctx._do_compact
    def always_fail(*args, **kwargs):
        raise RuntimeError("simulated compaction failure")
    ctx._do_compact = always_fail

    for _ in range(ContextManager.MAX_CONSECUTIVE_COMPACTION_FAILURES):
        ctx.compact_history(msgs, preserve_recent=4)

    assert ctx._compaction_disabled is True

    # should_compact now returns False even for large inputs
    big_msgs = _make_messages(20, char_size=5000)
    assert ctx.should_compact(big_msgs, max_tokens=100) is False


def test_circuit_breaker_resets_on_success(ctx: ContextManager):
    """A successful compaction resets the consecutive failure counter."""
    msgs = _make_messages(12, char_size=50)

    # Force 2 failures (one short of threshold)
    original_do_compact = ctx._do_compact
    fail_count = 0

    def fail_twice(*args, **kwargs):
        nonlocal fail_count
        fail_count += 1
        if fail_count <= 2:
            raise RuntimeError("simulated failure")
        return original_do_compact(*args, **kwargs)

    ctx._do_compact = fail_twice

    # Two failures
    ctx.compact_history(msgs, preserve_recent=4)
    ctx.compact_history(msgs, preserve_recent=4)
    assert ctx._consecutive_compaction_failures == 2
    assert ctx._compaction_disabled is False

    # Third call succeeds
    ctx.compact_history(msgs, preserve_recent=4)
    assert ctx._consecutive_compaction_failures == 0
    assert ctx._compaction_disabled is False


def test_circuit_breaker_returns_unchanged_on_failure(ctx: ContextManager):
    """On compaction failure, original messages are returned unchanged."""
    msgs = _make_messages(12, char_size=50)

    ctx._do_compact = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))

    compacted, summary = ctx.compact_history(msgs, preserve_recent=4, existing_summary="old")
    assert compacted is msgs
    assert summary == "old"


# ---------------------------------------------------------------------------
# Tests: token budget helpers
# ---------------------------------------------------------------------------


def test_estimate_tokens(ctx: ContextManager):
    """estimate_tokens uses len//4 heuristic."""
    assert ctx.estimate_tokens("abcdefgh") == 2  # 8 // 4
    assert ctx.estimate_tokens("") == 0


def test_has_budget(ctx: ContextManager):
    """has_budget reflects the 80% token budget."""
    # model_max_tokens=4096, budget_chars = 4096 * 0.80 * 4 = 13107
    assert ctx.has_budget(0) is True
    assert ctx.has_budget(13000) is True
    assert ctx.has_budget(14000) is False


# ---------------------------------------------------------------------------
# Tests: _extract_message_text edge cases
# ---------------------------------------------------------------------------


def test_extract_text_from_string():
    """String content is returned as-is."""
    assert ContextManager._extract_message_text({"content": "hello"}) == "hello"


def test_extract_text_from_list_of_dicts():
    """List of text blocks is concatenated."""
    msg = {"content": [
        {"type": "text", "text": "line 1"},
        {"type": "text", "text": "line 2"},
    ]}
    result = ContextManager._extract_message_text(msg)
    assert "line 1" in result
    assert "line 2" in result


def test_extract_text_from_empty():
    """Empty content returns empty string."""
    assert ContextManager._extract_message_text({}) == ""
