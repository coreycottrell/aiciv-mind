"""
Tests for aiciv_mind.model_router — dynamic model selection per task.

Covers: task classification, model selection by strength, fallback to default,
override, outcome recording, stats aggregation, persistence.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from aiciv_mind.model_router import (
    DEFAULT_PROFILES,
    ModelProfile,
    ModelRouter,
    RoutingOutcome,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def router() -> ModelRouter:
    """Router with default profiles, no persistence."""
    return ModelRouter()


@pytest.fixture
def custom_router() -> ModelRouter:
    """Router with custom profiles for deterministic testing."""
    profiles = [
        ModelProfile(
            model_id="cheap-general",
            strengths=["general", "conversation"],
            cost_tier="cheap",
            speed_tier="fast",
        ),
        ModelProfile(
            model_id="strong-reasoning",
            strengths=["reasoning", "analysis"],
            cost_tier="expensive",
            speed_tier="slow",
        ),
        ModelProfile(
            model_id="code-specialist",
            strengths=["code", "debugging"],
            cost_tier="medium",
            speed_tier="medium",
        ),
    ]
    return ModelRouter(profiles=profiles, default_model="cheap-general")


# ---------------------------------------------------------------------------
# Tests: task classification
# ---------------------------------------------------------------------------


def test_classify_code_task(router: ModelRouter):
    """Tasks mentioning code keywords are classified as 'code'."""
    assert router.classify_task("fix the bug in main.py") == "code"


def test_classify_reasoning_task(router: ModelRouter):
    """Tasks asking for analysis/planning are classified as 'reasoning'."""
    assert router.classify_task("analyze the architecture and design a strategy") == "reasoning"


def test_classify_general_fallback(router: ModelRouter):
    """Tasks with no pattern match fall back to 'general'."""
    assert router.classify_task("do the thing") == "general"


def test_classify_conversation_task(router: ModelRouter):
    """Greetings are classified as 'conversation'."""
    assert router.classify_task("hello, how are you?") == "conversation"


# ---------------------------------------------------------------------------
# Tests: model selection
# ---------------------------------------------------------------------------


def test_select_code_task_routes_to_code_model(router: ModelRouter):
    """Code tasks route to qwen2.5-coder (code strength)."""
    model = router.select("refactor the function in utils.py")
    assert model == "qwen2.5-coder"


def test_select_reasoning_routes_to_kimi(router: ModelRouter):
    """Reasoning tasks route to kimi-k2 (reasoning strength)."""
    model = router.select("analyze why this approach is better")
    assert model == "kimi-k2"


def test_select_general_routes_to_default(router: ModelRouter):
    """General/unknown tasks fall back to the default model."""
    model = router.select("do the thing now")
    assert model == "minimax-m27"


def test_select_with_override(router: ModelRouter):
    """Override forces a specific model regardless of task."""
    model = router.select("fix the code bug", override="custom-model-99")
    assert model == "custom-model-99"


def test_select_prefers_cheap_fast(custom_router: ModelRouter):
    """When multiple profiles match, cheap+fast wins."""
    # "general" is a strength of cheap-general only
    model = custom_router.select("do the thing")
    assert model == "cheap-general"


def test_select_fallback_when_no_strength_match(custom_router: ModelRouter):
    """When no profile lists the task type, default model is returned."""
    # "hub" isn't a strength of any custom profile
    model = custom_router.select("post to the hub thread")
    assert model == "cheap-general"


# ---------------------------------------------------------------------------
# Tests: outcome recording & stats
# ---------------------------------------------------------------------------


def test_record_outcome_stores_entry(router: ModelRouter):
    """record_outcome appends to internal outcomes list."""
    router.record_outcome("fix the bug", "qwen2.5-coder", success=True, tokens_used=500)
    assert len(router._outcomes) == 1
    assert router._outcomes[0].model_id == "qwen2.5-coder"
    assert router._outcomes[0].success is True


def test_get_stats_aggregates(router: ModelRouter):
    """get_stats groups outcomes by model:task_type."""
    router.record_outcome("fix a bug", "qwen2.5-coder", success=True, tokens_used=100)
    router.record_outcome("fix another bug", "qwen2.5-coder", success=False, tokens_used=200)
    stats = router.get_stats()
    key = "qwen2.5-coder:code"
    assert key in stats
    assert stats[key]["total"] == 2
    assert stats[key]["success"] == 1
    assert stats[key]["tokens"] == 300


# ---------------------------------------------------------------------------
# Tests: persistence
# ---------------------------------------------------------------------------


def test_persistence_round_trip():
    """Stats are persisted to disk and reloaded on new router creation."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        stats_path = f.name

    try:
        r1 = ModelRouter(stats_path=stats_path)
        r1.record_outcome("analyze plan", "kimi-k2", success=True, tokens_used=800)
        r1.record_outcome("explain why", "kimi-k2", success=True, tokens_used=600)

        # New router loads from the same file
        r2 = ModelRouter(stats_path=stats_path)
        assert len(r2._outcomes) == 2
        assert r2._outcomes[0].model_id == "kimi-k2"
    finally:
        Path(stats_path).unlink(missing_ok=True)


def test_persistence_caps_at_500():
    """Persistence keeps only the last 500 outcomes."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        stats_path = f.name

    try:
        r = ModelRouter(stats_path=stats_path)
        for i in range(510):
            r.record_outcome(f"task {i}", "minimax-m27", success=True, tokens_used=10)

        data = json.loads(Path(stats_path).read_text())
        assert len(data) == 500
    finally:
        Path(stats_path).unlink(missing_ok=True)
