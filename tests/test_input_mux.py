"""Tests for InputMux content-based routing (P5 fix)."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unified_daemon import InputMux, MindEvent, Route


class TestInputMuxContentRouting:
    """P5 fix: Hub events with task content route to CONSCIOUS, not hub-lead."""

    def _make_hub_event(self, body: str, hub_type: str = "thread_reply") -> MindEvent:
        return MindEvent(
            source="hub",
            priority=5,
            payload={"type": hub_type, "body": body},
        )

    def test_task_content_routes_conscious(self):
        """Hub post with 'Phase 1' task language → CONSCIOUS."""
        mux = InputMux()
        event = self._make_hub_event("## Phase 1: Seed Processing\nRoot, begin Phase 1.")
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS
        assert result.team_lead is None  # Root decides

    def test_file_operation_routes_conscious(self):
        """Hub post requesting file operations → CONSCIOUS."""
        mux = InputMux()
        event = self._make_hub_event("Please read file test-civ/identity.json and write the output")
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS

    def test_evolution_routes_conscious(self):
        """Hub post about evolution test → CONSCIOUS."""
        mux = InputMux()
        event = self._make_hub_event("Run the evolution test tasks for Phase 2")
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS

    def test_code_task_routes_conscious(self):
        """Hub post about fixing a bug → CONSCIOUS."""
        mux = InputMux()
        event = self._make_hub_event("Fix the parser bug in mind.py")
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS

    def test_deploy_task_routes_conscious(self):
        """Hub post about deployment → CONSCIOUS."""
        mux = InputMux()
        event = self._make_hub_event("Deploy the new daemon to production")
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS

    def test_social_content_routes_hub_lead(self):
        """Hub post with social/discussion content → hub-lead."""
        mux = InputMux()
        event = self._make_hub_event("Hello Root! How's the civilization doing today?")
        result = mux.classify(event)
        assert result.route == Route.AUTONOMIC
        assert result.team_lead == "hub-lead"

    def test_mention_with_task_routes_conscious(self):
        """@root mention with task content → CONSCIOUS (not hub-lead)."""
        mux = InputMux()
        event = self._make_hub_event(
            "@root please read_file the manifest and fix the bug",
            hub_type="mention",
        )
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS

    def test_mention_social_routes_hub_lead(self):
        """@root mention with social content → hub-lead."""
        mux = InputMux()
        event = self._make_hub_event("@root great work on the blog post!", hub_type="mention")
        result = mux.classify(event)
        assert result.route == Route.AUTONOMIC
        assert result.team_lead == "hub-lead"

    def test_task_priority_higher_than_social(self):
        """Task-routed Hub events get higher priority than social."""
        mux = InputMux()
        task_event = self._make_hub_event("Run the evolution test Phase 3")
        social_event = self._make_hub_event("Hey, nice to meet you!")
        mux.classify(task_event)
        mux.classify(social_event)
        assert task_event.priority < social_event.priority  # lower = higher priority

    def test_case_insensitive_keyword_match(self):
        """Keywords match case-insensitively."""
        mux = InputMux()
        event = self._make_hub_event("PHASE 1: SEED PROCESSING — BEGIN")
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS

    def test_empty_body_routes_hub_lead(self):
        """Hub post with no body → hub-lead (no task keywords found)."""
        mux = InputMux()
        event = self._make_hub_event("")
        result = mux.classify(event)
        assert result.route == Route.AUTONOMIC
        assert result.team_lead == "hub-lead"


class TestInputMuxNonHubRouting:
    """Non-Hub events route correctly (unchanged by P5 fix)."""

    def test_tg_routes_conscious(self):
        mux = InputMux()
        event = MindEvent(source="tg", priority=5, payload={"text": "hello"})
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS
        assert result.priority == 0

    def test_ipc_routes_conscious(self):
        mux = InputMux()
        event = MindEvent(source="ipc", priority=5, payload={"result": "done"})
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS
        assert result.priority == 1

    def test_scheduler_grounding_boop_routes_ops(self):
        mux = InputMux()
        event = MindEvent(source="scheduler", priority=5, payload={"name": "grounding_boop"})
        result = mux.classify(event)
        assert result.route == Route.AUTONOMIC
        assert result.team_lead == "ops-lead"

    def test_unknown_source_defaults_conscious(self):
        mux = InputMux()
        event = MindEvent(source="unknown", priority=5, payload={})
        result = mux.classify(event)
        assert result.route == Route.CONSCIOUS
