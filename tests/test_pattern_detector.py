"""Tests for aiciv_mind.pattern_detector — runtime pattern detection."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiciv_mind.pattern_detector import PatternDetector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def detector():
    return PatternDetector(agent_id="test-mind")


# ---------------------------------------------------------------------------
# Tests: observation basics
# ---------------------------------------------------------------------------


class TestObservation:
    def test_empty_detector_has_no_patterns(self, detector):
        assert detector.detected_patterns() == []
        assert detector.observation_count == 0

    def test_observe_increments_count(self, detector):
        detector.observe("bash", duration_ms=100)
        detector.observe("grep", duration_ms=50)
        assert detector.observation_count == 2

    def test_error_count_tracked(self, detector):
        detector.observe("bash", is_error=True)
        detector.observe("bash", is_error=False)
        detector.observe("bash", is_error=True)
        assert detector.error_count == 2


# ---------------------------------------------------------------------------
# Tests: sequence detection
# ---------------------------------------------------------------------------


class TestSequenceDetection:
    def test_detects_bigram_pattern(self, detector):
        """Repeating A→B 3+ times should be detected."""
        for _ in range(4):
            detector.observe("memory_search")
            detector.observe("memory_write")

        patterns = detector.detected_patterns()
        seq_patterns = [p for p in patterns if p.pattern_type == "tool_sequence"]
        assert len(seq_patterns) >= 1

        bigram = next(p for p in seq_patterns if p.details.get("length") == 2)
        assert bigram.count >= 3
        assert "memory_search" in bigram.details["sequence"]

    def test_detects_trigram_pattern(self, detector):
        """Repeating A→B→C 3+ times should be detected."""
        for _ in range(4):
            detector.observe("memory_search")
            detector.observe("bash")
            detector.observe("memory_write")

        patterns = detector.detected_patterns()
        trigrams = [p for p in patterns if p.details.get("length") == 3]
        assert len(trigrams) >= 1
        assert trigrams[0].count >= 3

    def test_no_sequence_below_threshold(self, detector):
        """Two occurrences should not trigger (threshold=3)."""
        for _ in range(2):
            detector.observe("a")
            detector.observe("b")

        patterns = detector.detected_patterns()
        seq_patterns = [p for p in patterns if p.pattern_type == "tool_sequence"]
        assert len(seq_patterns) == 0

    def test_too_few_observations_for_sequence(self, detector):
        detector.observe("a")
        detector.observe("b")
        assert detector.detected_patterns() == []


# ---------------------------------------------------------------------------
# Tests: error repeat detection
# ---------------------------------------------------------------------------


class TestErrorRepeatDetection:
    def test_detects_repeated_errors(self, detector):
        for _ in range(4):
            detector.observe("bash", is_error=True)

        patterns = detector.detected_patterns()
        error_patterns = [p for p in patterns if p.pattern_type == "error_repeat"]
        assert len(error_patterns) == 1
        assert error_patterns[0].details["tool"] == "bash"
        assert error_patterns[0].count == 4

    def test_no_error_pattern_below_threshold(self, detector):
        detector.observe("bash", is_error=True)
        detector.observe("bash", is_error=True)

        patterns = detector.detected_patterns()
        error_patterns = [p for p in patterns if p.pattern_type == "error_repeat"]
        assert len(error_patterns) == 0


# ---------------------------------------------------------------------------
# Tests: slow tool detection
# ---------------------------------------------------------------------------


class TestSlowToolDetection:
    def test_detects_slow_tools(self, detector):
        detector.observe("web_fetch", duration_ms=8000)
        detector.observe("web_fetch", duration_ms=12000)

        patterns = detector.detected_patterns()
        slow_patterns = [p for p in patterns if p.pattern_type == "slow_tool"]
        assert len(slow_patterns) == 1
        assert slow_patterns[0].details["avg_ms"] == 10000

    def test_no_slow_pattern_for_fast_tools(self, detector):
        detector.observe("grep", duration_ms=50)
        detector.observe("grep", duration_ms=30)

        patterns = detector.detected_patterns()
        slow_patterns = [p for p in patterns if p.pattern_type == "slow_tool"]
        assert len(slow_patterns) == 0

    def test_single_slow_call_not_detected(self, detector):
        """Need 2+ calls to detect slow pattern."""
        detector.observe("web_fetch", duration_ms=15000)

        patterns = detector.detected_patterns()
        slow_patterns = [p for p in patterns if p.pattern_type == "slow_tool"]
        assert len(slow_patterns) == 0


# ---------------------------------------------------------------------------
# Tests: dominant tool detection
# ---------------------------------------------------------------------------


class TestDominantToolDetection:
    def test_detects_dominant_tool(self, detector):
        for _ in range(8):
            detector.observe("bash")
        detector.observe("grep")
        detector.observe("read_file")

        patterns = detector.detected_patterns()
        dominant = [p for p in patterns if p.pattern_type == "dominant_tool"]
        assert len(dominant) == 1
        assert dominant[0].details["tool"] == "bash"
        assert dominant[0].details["ratio"] == 0.8

    def test_no_dominant_when_balanced(self, detector):
        for tool in ["bash", "grep", "read_file", "write_file", "memory_search"]:
            detector.observe(tool)

        patterns = detector.detected_patterns()
        dominant = [p for p in patterns if p.pattern_type == "dominant_tool"]
        assert len(dominant) == 0

    def test_too_few_observations(self, detector):
        detector.observe("bash")
        detector.observe("bash")
        patterns = detector.detected_patterns()
        dominant = [p for p in patterns if p.pattern_type == "dominant_tool"]
        assert len(dominant) == 0


# ---------------------------------------------------------------------------
# Tests: summary and export
# ---------------------------------------------------------------------------


class TestSummaryAndExport:
    def test_summary_empty(self, detector):
        assert "No patterns detected" in detector.summary()

    def test_summary_with_patterns(self, detector):
        for _ in range(4):
            detector.observe("bash", is_error=True)
        summary = detector.summary()
        assert "error_repeat" in summary
        assert "bash" in summary

    def test_to_jsonl(self, detector, tmp_path):
        for _ in range(4):
            detector.observe("bash", is_error=True, duration_ms=100)

        path = tmp_path / "patterns.jsonl"
        count = detector.to_jsonl(path)
        assert count >= 1

        lines = path.read_text().strip().splitlines()
        assert len(lines) == count
        record = json.loads(lines[0])
        assert record["agent_id"] == "test-mind"
        assert "type" in record

    def test_to_jsonl_no_patterns(self, detector, tmp_path):
        path = tmp_path / "patterns.jsonl"
        count = detector.to_jsonl(path)
        assert count == 0
        assert not path.exists()


# ---------------------------------------------------------------------------
# Tests: DetectedPattern.to_dict
# ---------------------------------------------------------------------------


class TestDetectedPatternDict:
    def test_to_dict(self):
        from aiciv_mind.pattern_detector import DetectedPattern
        p = DetectedPattern(
            pattern_type="test",
            description="test pattern",
            count=5,
            details={"extra": "value"},
        )
        d = p.to_dict()
        assert d["type"] == "test"
        assert d["description"] == "test pattern"
        assert d["count"] == 5
        assert d["extra"] == "value"
