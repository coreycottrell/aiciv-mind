"""
Battle tests for the fractal coordination architecture.

Stress tests, edge cases, and adversarial scenarios for:
- Role-based tool filtering under various conditions
- Fitness scoring with extreme/pathological data
- CoordinationMetrics accumulation at scale
- Spawn tool role enforcement
- Three-level scratchpad system under concurrent access
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiciv_mind.fitness import (
    AgentFitness,
    CoordinationMetrics,
    PrimaryFitness,
    TeamLeadFitness,
    score_agent,
    score_for_role,
    score_primary,
    score_team_lead,
)
from aiciv_mind.roles import (
    AGENT_TOOLS,
    PRIMARY_TOOLS,
    TEAM_LEAD_TOOLS,
    Role,
    tools_for_role,
)
from aiciv_mind.tools import ToolRegistry


# ---------------------------------------------------------------------------
# Role filtering stress tests
# ---------------------------------------------------------------------------


class TestRoleFilteringStress:
    """Stress the role filtering system with edge cases."""

    def test_filter_empty_registry(self):
        """Filtering an empty registry should return empty for any role."""
        reg = ToolRegistry()
        for role in Role:
            filtered = reg.filter_by_role(role)
            assert len(filtered.names()) == 0

    def test_filter_registry_with_100_tools(self):
        """Primary filtering 100 tools should still only return PRIMARY_TOOLS."""
        reg = ToolRegistry()
        for i in range(100):
            reg.register(f"tool_{i}", {"name": f"tool_{i}"}, lambda x: "ok")
        # Add the actual primary tools
        for name in PRIMARY_TOOLS:
            reg.register(name, {"name": name}, lambda x: "ok")

        filtered = reg.filter_by_role(Role.PRIMARY)
        assert set(filtered.names()) == set(PRIMARY_TOOLS)
        assert len(filtered.names()) == len(PRIMARY_TOOLS)

    def test_filter_preserves_handler_identity(self):
        """Filtered registry should have the same handler functions."""
        reg = ToolRegistry()
        handler = lambda x: "specific_handler"
        reg.register("coordination_read", {"name": "coordination_read"}, handler)

        filtered = reg.filter_by_role(Role.PRIMARY)
        assert filtered._handlers["coordination_read"] is handler

    def test_double_filter_is_idempotent(self):
        """Filtering twice should produce the same result."""
        reg = ToolRegistry()
        for name in PRIMARY_TOOLS:
            reg.register(name, {"name": name}, lambda x: "ok")
        reg.register("bash", {"name": "bash"}, lambda x: "ok")

        first = reg.filter_by_role(Role.PRIMARY)
        second = first.filter_by_role(Role.PRIMARY)
        assert set(first.names()) == set(second.names())

    def test_agent_filter_then_primary_filter(self):
        """Agent → Primary filter should still enforce PRIMARY_TOOLS."""
        reg = ToolRegistry()
        for name in list(PRIMARY_TOOLS) + ["bash", "write_file", "memory_search"]:
            reg.register(name, {"name": name}, lambda x: "ok")

        agent_filtered = reg.filter_by_role(Role.AGENT)
        primary_filtered = agent_filtered.filter_by_role(Role.PRIMARY)
        assert "bash" not in primary_filtered.names()
        assert "coordination_read" in primary_filtered.names()

    def test_role_enum_exhaustive(self):
        """Every Role enum member should have an entry in ROLE_TOOL_WHITELIST."""
        for role in Role:
            result = tools_for_role(role)
            if role == Role.AGENT:
                assert result is None
            else:
                assert isinstance(result, frozenset)

    def test_primary_tools_frozen(self):
        """PRIMARY_TOOLS should be immutable."""
        with pytest.raises(AttributeError):
            PRIMARY_TOOLS.add("bash")  # type: ignore

    def test_team_lead_tools_frozen(self):
        """TEAM_LEAD_TOOLS should be immutable."""
        with pytest.raises(AttributeError):
            TEAM_LEAD_TOOLS.add("bash")  # type: ignore


# ---------------------------------------------------------------------------
# Fitness scoring edge cases
# ---------------------------------------------------------------------------


class TestFitnessEdgeCases:
    """Pathological inputs for fitness scoring."""

    def test_1000_primary_metrics(self):
        """Score 1000 delegation events."""
        metrics = [
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target=f"lead-{i % 5}",
                delegation_correct=(i % 3 != 0),  # 67% correct
                team_leads_available=5,
                cross_vertical_synthesis=(i % 4 == 0),  # 25% synthesis
            )
            for i in range(1000)
        ]
        result = score_primary(metrics)
        assert result.tasks_scored == 1000
        assert result.tasks_judged == 1000
        assert 0.6 < result.delegation_accuracy < 0.7  # ~67%
        assert 0.2 < result.synthesis_rate < 0.3  # ~25%
        assert result.composite > 0  # Non-trivial composite

    def test_all_unjudged_delegations(self):
        """All delegations unjudged → 0 accuracy but non-zero utilization."""
        metrics = [
            CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target=f"lead-{i}",
                delegation_correct=None,
                team_leads_available=3,
            )
            for i in range(3)
        ]
        result = score_primary(metrics)
        assert result.delegation_accuracy == 0.0
        assert result.tasks_judged == 0
        assert result.utilization_balance > 0  # 3 different leads used

    def test_single_agent_metric(self):
        """Single agent task should still score."""
        metrics = [
            CoordinationMetrics(
                role=Role.AGENT,
                tools_attempted=1,
                tools_succeeded=1,
                memory_writes=0,
                verification_provided=True,
                task_completed=True,
            )
        ]
        result = score_agent(metrics)
        assert result.tasks_scored == 1
        assert result.tool_effectiveness == 1.0

    def test_zero_tool_attempts_all_agents(self):
        """No tool calls at all → 0 effectiveness."""
        metrics = [
            CoordinationMetrics(role=Role.AGENT, tools_attempted=0, tools_succeeded=0)
            for _ in range(5)
        ]
        result = score_agent(metrics)
        assert result.tool_effectiveness == 0.0

    def test_team_lead_extreme_latency(self):
        """Extremely slow delegation → 0 speed score."""
        metrics = [
            CoordinationMetrics(
                role=Role.TEAM_LEAD,
                delegation_latency_ms=1_000_000,  # 1000 seconds
            )
        ]
        result = score_team_lead(metrics)
        assert result.delegation_speed == 0.0

    def test_team_lead_zero_latency(self):
        """Zero latency (no latency data) → 0 speed score."""
        metrics = [
            CoordinationMetrics(role=Role.TEAM_LEAD, delegation_latency_ms=0)
        ]
        result = score_team_lead(metrics)
        assert result.delegation_speed == 0.0

    def test_mixed_roles_in_list(self):
        """Mixed role metrics — each scorer only counts its own role."""
        metrics = [
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", delegation_correct=True, team_leads_available=3),
            CoordinationMetrics(role=Role.TEAM_LEAD, agent_spawned="x", agent_selection_correct=True),
            CoordinationMetrics(role=Role.AGENT, tools_attempted=5, tools_succeeded=5, task_completed=True),
        ]
        p = score_primary(metrics)
        t = score_team_lead(metrics)
        a = score_agent(metrics)
        assert p.tasks_scored == 1
        assert t.tasks_scored == 1
        assert a.tasks_scored == 1

    def test_fitness_to_dict_serializable(self):
        """All fitness results should be JSON-serializable."""
        import json
        for role in Role:
            result = score_for_role(role, [])
            d = result.to_dict()
            json_str = json.dumps(d)
            assert json.loads(json_str) == d


# ---------------------------------------------------------------------------
# SessionLearner integration stress
# ---------------------------------------------------------------------------


class TestSessionLearnerCoordinationStress:
    def test_100_coordination_records(self):
        """Record 100 coordination metrics and summarize."""
        from aiciv_mind.learning import SessionLearner, TaskOutcome

        learner = SessionLearner(agent_id="stress-test")

        # Add task outcomes
        for i in range(50):
            learner.record(TaskOutcome(
                task=f"Task {i}",
                result=f"Result for task {i} completed successfully",
                tool_call_count=3,
            ))

        # Add coordination metrics
        for i in range(100):
            learner.record_coordination(CoordinationMetrics(
                role=Role.PRIMARY,
                delegation_target=f"lead-{i % 4}",
                delegation_correct=(i % 5 != 0),
                team_leads_available=4,
                cross_vertical_synthesis=(i % 3 == 0),
            ))

        assert learner.coordination_count == 100
        summary = learner.summarize()
        assert "primary" in summary.coordination_fitness
        assert summary.coordination_fitness["primary"]["tasks_scored"] == 100

    def test_multi_role_coordination_in_one_session(self):
        """A session with PRIMARY + TEAM_LEAD + AGENT metrics."""
        from aiciv_mind.learning import SessionLearner, TaskOutcome

        learner = SessionLearner(agent_id="multi-role")
        learner.record(TaskOutcome(task="X", result="Done successfully with detail", tool_call_count=2))

        learner.record_coordination(
            CoordinationMetrics(role=Role.PRIMARY, delegation_target="a", delegation_correct=True, team_leads_available=2)
        )
        learner.record_coordination(
            CoordinationMetrics(role=Role.TEAM_LEAD, agent_spawned="x", agent_selection_correct=True, result_synthesized=True)
        )
        learner.record_coordination(
            CoordinationMetrics(role=Role.AGENT, tools_attempted=10, tools_succeeded=9, task_completed=True)
        )

        summary = learner.summarize()
        assert "primary" in summary.coordination_fitness
        assert "team_lead" in summary.coordination_fitness
        assert "agent" in summary.coordination_fitness


# ---------------------------------------------------------------------------
# Scratchpad concurrent access
# ---------------------------------------------------------------------------


class TestScratchpadConcurrent:
    """Multiple writers hitting the same scratchpad file."""

    def test_concurrent_team_scratchpad_writes(self, tmp_path):
        """10 threads writing to the same team scratchpad simultaneously."""
        from aiciv_mind.tools import ToolRegistry
        from aiciv_mind.tools.coordination_tools import register_coordination_tools

        results = []
        errors = []

        def writer(thread_id: int):
            try:
                reg = ToolRegistry()
                register_coordination_tools(reg, str(tmp_path), writer_id=f"mind-{thread_id}")
                for i in range(10):
                    result = asyncio.run(reg.execute(
                        "team_scratchpad_write",
                        {"vertical": "research", "entry": f"Thread {thread_id} entry {i}"},
                    ))
                    results.append(result)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errors during concurrent write: {errors}"
        assert len(results) == 100  # 10 threads × 10 writes
        assert all("Appended" in r for r in results)

        # Verify content integrity
        scratchpad = (tmp_path / "teams" / "research-team.md").read_text()
        for thread_id in range(10):
            for entry_id in range(10):
                assert f"Thread {thread_id} entry {entry_id}" in scratchpad

    def test_concurrent_coordination_writes(self, tmp_path):
        """5 threads writing to the coordination scratchpad simultaneously."""
        from aiciv_mind.tools import ToolRegistry
        from aiciv_mind.tools.coordination_tools import register_coordination_tools

        results = []

        def writer(thread_id: int):
            reg = ToolRegistry()
            register_coordination_tools(reg, str(tmp_path), writer_id=f"lead-{thread_id}")
            for i in range(5):
                result = asyncio.run(reg.execute(
                    "coordination_write",
                    {"entry": f"Lead {thread_id} priority {i}"},
                ))
                results.append(result)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 25  # 5 threads × 5 writes
        content = (tmp_path / "coordination.md").read_text()
        for thread_id in range(5):
            for entry_id in range(5):
                assert f"Lead {thread_id} priority {entry_id}" in content


# ---------------------------------------------------------------------------
# Manifest role validation in spawn tools
# ---------------------------------------------------------------------------


class TestManifestRoleValidation:
    """Ensure spawn tools reject wrong-role manifests consistently."""

    def test_spawn_tl_rejects_primary_manifest(self, tmp_path):
        """spawn_team_lead should reject a manifest with role: primary."""
        m = tmp_path / "primary.yaml"
        m.write_text(
            "mind_id: p\ndisplay_name: P\nrole: primary\n"
            "auth:\n  civ_id: acg\n  keypair_path: /tmp/k.json\n"
            "memory:\n  db_path: /tmp/f.db\n"
        )
        from aiciv_mind.tools.spawn_tools import register_spawn_tools

        spawner = MagicMock()
        bus = MagicMock()
        bus.send = AsyncMock()
        reg = ToolRegistry()
        register_spawn_tools(reg, spawner, bus, "primary", role="primary")

        result = asyncio.run(reg.execute("spawn_team_lead", {
            "mind_id": "p",
            "manifest_path": str(m),
            "vertical": "research",
        }))
        assert "ERROR" in result
        assert "team_lead" in result
        spawner.spawn.assert_not_called()

    def test_spawn_agent_rejects_team_lead_manifest(self, tmp_path):
        """spawn_agent should reject a manifest with role: team_lead."""
        m = tmp_path / "tl.yaml"
        m.write_text(
            "mind_id: tl\ndisplay_name: TL\nrole: team_lead\n"
            "auth:\n  civ_id: acg\n  keypair_path: /tmp/k.json\n"
            "memory:\n  db_path: /tmp/f.db\n"
        )
        from aiciv_mind.tools.spawn_tools import register_spawn_tools

        spawner = MagicMock()
        bus = MagicMock()
        bus.send = AsyncMock()
        reg = ToolRegistry()
        register_spawn_tools(reg, spawner, bus, "tl", role="team_lead")

        result = asyncio.run(reg.execute("spawn_agent", {
            "mind_id": "tl",
            "manifest_path": str(m),
        }))
        assert "ERROR" in result
        assert "agent" in result
        spawner.spawn.assert_not_called()

    def test_spawn_tl_rejects_nonexistent_manifest(self):
        """spawn_team_lead with bad path should error gracefully."""
        from aiciv_mind.tools.spawn_tools import register_spawn_tools

        spawner = MagicMock()
        bus = MagicMock()
        bus.send = AsyncMock()
        reg = ToolRegistry()
        register_spawn_tools(reg, spawner, bus, "primary", role="primary")

        result = asyncio.run(reg.execute("spawn_team_lead", {
            "mind_id": "bad",
            "manifest_path": "/nonexistent/path.yaml",
            "vertical": "research",
        }))
        assert "ERROR" in result


# ---------------------------------------------------------------------------
# Role invariant: structural impossibility proofs
# ---------------------------------------------------------------------------


class TestStructuralImpossibility:
    """Prove that the WRONG thing is structurally impossible."""

    def test_primary_cannot_read_files_even_if_registered(self):
        """Even if read_file is registered, Primary filter removes it."""
        reg = ToolRegistry()
        reg.register("read_file", {"name": "read_file"}, lambda x: "secret data")
        reg.register("coordination_read", {"name": "coordination_read"}, lambda x: "ok")

        filtered = reg.filter_by_role(Role.PRIMARY)
        assert "read_file" not in filtered.names()
        # Trying to execute read_file on filtered registry returns error
        result = asyncio.run(filtered.execute("read_file", {"path": "/etc/passwd"}))
        assert "ERROR" in result or "Unknown tool" in result

    def test_team_lead_cannot_spawn_team_lead_even_if_registered(self):
        """Team lead whitelist doesn't include spawn_team_lead."""
        reg = ToolRegistry()
        reg.register("spawn_team_lead", {"name": "spawn_team_lead"}, lambda x: "spawned")
        reg.register("spawn_agent", {"name": "spawn_agent"}, lambda x: "spawned")

        filtered = reg.filter_by_role(Role.TEAM_LEAD)
        assert "spawn_team_lead" not in filtered.names()
        assert "spawn_agent" in filtered.names()

    def test_primary_cannot_write_memory(self):
        """Primary doesn't have memory_write in its whitelist."""
        assert "memory_write" not in PRIMARY_TOOLS
        assert "memory_search" not in PRIMARY_TOOLS

    def test_team_lead_cannot_write_files(self):
        """Team lead doesn't have write_file in its whitelist."""
        assert "write_file" not in TEAM_LEAD_TOOLS
        assert "bash" not in TEAM_LEAD_TOOLS

    def test_agent_tools_is_none_means_everything(self):
        """AGENT_TOOLS is None — filter_by_role keeps everything."""
        reg = ToolRegistry()
        for name in ["bash", "write_file", "memory_search", "spawn_team_lead", "coordination_read"]:
            reg.register(name, {"name": name}, lambda x: "ok")

        filtered = reg.filter_by_role(Role.AGENT)
        assert set(filtered.names()) == {"bash", "write_file", "memory_search", "spawn_team_lead", "coordination_read"}

    def test_no_tool_overlap_between_primary_and_team_lead(self):
        """PRIMARY and TEAM_LEAD tools should be mostly disjoint (except coordination_read, send_message)."""
        overlap = PRIMARY_TOOLS & TEAM_LEAD_TOOLS
        # coordination_read and send_message are shared
        assert overlap == {"coordination_read", "send_message"}

    def test_primary_tools_count_is_exactly_5(self):
        assert len(PRIMARY_TOOLS) == 5

    def test_team_lead_tools_count_is_exactly_7(self):
        assert len(TEAM_LEAD_TOOLS) == 7
