"""
aiciv_mind.tools.integrity_tools -- Memory integrity self-check.

Writes a test memory, retrieves it via FTS5, verifies field round-trip,
then audits FTS5 sync, tag integrity, depth_score sanity, orphaned links,
and session journal health.  Returns a structured pass/fail report.

Registered only when a MemoryStore is provided.
"""

from __future__ import annotations

import json
import logging
import uuid

from aiciv_mind.memory import Memory, MemoryStore
from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)

_SELFCHECK_DEFINITION: dict = {
    "name": "memory_selfcheck",
    "description": (
        "Run an integrity check on the memory system. Writes a test memory, "
        "retrieves it via FTS5 search, verifies all fields survive the round-trip, "
        "then checks FTS5 index health, tag integrity, and depth_score consistency. "
        "Returns a pass/fail report for each check."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verbose": {
                "type": "boolean",
                "description": "Show detailed output for each check (default: false)",
            },
        },
    },
}

# Unique marker so the FTS5 search finds only our test row.
_MARKER = "integrityprobe"


def _delete_memory(store: MemoryStore, memory_id: str) -> None:
    """Delete a memory by ID.  The FTS5 trigger handles index cleanup."""
    store._conn.execute("DELETE FROM memory_tags WHERE memory_id = ?", (memory_id,))
    store._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    store._conn.commit()


def _make_selfcheck_handler(memory_store: MemoryStore):
    """Return a handler closure for the memory_selfcheck tool."""

    def handler(tool_input: dict) -> str:
        verbose = tool_input.get("verbose", False)
        checks: list[str] = []
        pass_count = 0
        warn_count = 0
        fail_count = 0

        # ------------------------------------------------------------------ #
        # 1. Round-trip test
        # ------------------------------------------------------------------ #
        test_id = str(uuid.uuid4())
        test_title = f"{_MARKER} roundtrip {test_id[:8]}"
        test_content = "Self-check probe content for integrity validation."
        test_tags = ["selfcheck", "probe"]
        try:
            mem = Memory(
                id=test_id,
                agent_id="__selfcheck__",
                title=test_title,
                content=test_content,
                domain="integrity",
                memory_type="observation",
                tags=test_tags,
                confidence="HIGH",
            )
            memory_store.store(mem)

            results = memory_store.search(_MARKER, agent_id="__selfcheck__", limit=5)
            match = next((r for r in results if r["id"] == test_id), None)

            if match is None:
                checks.append("FAIL Round-trip: wrote test memory but FTS5 search returned nothing")
                fail_count += 1
            else:
                mismatches: list[str] = []
                if match["title"] != test_title:
                    mismatches.append(f"title: got {match['title']!r}")
                if match["content"] != test_content:
                    mismatches.append("content mismatch")
                if match["agent_id"] != "__selfcheck__":
                    mismatches.append(f"agent_id: got {match['agent_id']!r}")
                if match["domain"] != "integrity":
                    mismatches.append(f"domain: got {match['domain']!r}")
                stored_tags = json.loads(match["tags"]) if isinstance(match["tags"], str) else match["tags"]
                if sorted(stored_tags) != sorted(test_tags):
                    mismatches.append(f"tags: got {stored_tags!r}")

                if mismatches:
                    detail = "; ".join(mismatches)
                    checks.append(f"FAIL Round-trip: fields diverged -- {detail}")
                    fail_count += 1
                else:
                    checks.append("PASS Round-trip: wrote test memory, retrieved via FTS5, fields match")
                    pass_count += 1
        except Exception as exc:
            checks.append(f"FAIL Round-trip: exception -- {exc}")
            fail_count += 1
        finally:
            try:
                _delete_memory(memory_store, test_id)
            except Exception:
                pass

        # ------------------------------------------------------------------ #
        # 2. FTS5 index sync
        # ------------------------------------------------------------------ #
        try:
            mem_count = memory_store._conn.execute(
                "SELECT COUNT(*) FROM memories"
            ).fetchone()[0]
            fts_count = memory_store._conn.execute(
                "SELECT COUNT(*) FROM memories_fts"
            ).fetchone()[0]
            if mem_count == fts_count:
                checks.append(f"PASS FTS5 sync: {mem_count} memories, {fts_count} FTS5 entries")
                pass_count += 1
            else:
                checks.append(
                    f"FAIL FTS5 sync: {mem_count} memories vs {fts_count} FTS5 entries (drift detected)"
                )
                fail_count += 1
        except Exception as exc:
            checks.append(f"FAIL FTS5 sync: exception -- {exc}")
            fail_count += 1

        # ------------------------------------------------------------------ #
        # 3. Tag integrity
        # ------------------------------------------------------------------ #
        try:
            sample = memory_store._conn.execute(
                "SELECT id, tags FROM memories ORDER BY RANDOM() LIMIT 10"
            ).fetchall()
            tag_mismatches: list[str] = []
            for row in sample:
                mid = row["id"]
                tags_raw = row["tags"]
                try:
                    tags_list = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
                except (json.JSONDecodeError, TypeError):
                    tags_list = []
                for tag in tags_list:
                    exists = memory_store._conn.execute(
                        "SELECT 1 FROM memory_tags WHERE memory_id = ? AND tag = ?",
                        (mid, tag),
                    ).fetchone()
                    if not exists:
                        tag_mismatches.append(f"memory {mid[:8]} has tag {tag!r} not in memory_tags")

            if not sample:
                checks.append("PASS Tag integrity: no memories to check")
                pass_count += 1
            elif tag_mismatches:
                detail = "; ".join(tag_mismatches[:5])
                checks.append(f"WARN Tag integrity: {len(tag_mismatches)} mismatch(es) ({detail})")
                warn_count += 1
            else:
                checked = len(sample)
                checks.append(f"PASS Tag integrity: {checked} memories sampled, all tags present")
                pass_count += 1
        except Exception as exc:
            checks.append(f"FAIL Tag integrity: exception -- {exc}")
            fail_count += 1

        # ------------------------------------------------------------------ #
        # 4. Depth-score sanity
        # ------------------------------------------------------------------ #
        try:
            bad_rows = memory_store._conn.execute(
                """
                SELECT COUNT(*) FROM memories
                WHERE depth_score IS NULL OR depth_score < 0 OR depth_score > 2.0
                """
            ).fetchone()[0]
            total = memory_store._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            if bad_rows == 0:
                checks.append(f"PASS Depth scores: all {total} in valid range")
                pass_count += 1
            else:
                checks.append(f"WARN Depth scores: {bad_rows}/{total} outside valid range (NULL, <0, or >2.0)")
                warn_count += 1
        except Exception as exc:
            checks.append(f"FAIL Depth scores: exception -- {exc}")
            fail_count += 1

        # ------------------------------------------------------------------ #
        # 5. Orphaned links
        # ------------------------------------------------------------------ #
        try:
            orphaned = memory_store._conn.execute(
                """
                SELECT COUNT(*) FROM memory_links
                WHERE source_id NOT IN (SELECT id FROM memories)
                   OR target_id NOT IN (SELECT id FROM memories)
                """
            ).fetchone()[0]
            if orphaned == 0:
                checks.append("PASS Links: no orphaned links")
                pass_count += 1
            else:
                checks.append(f"WARN Links: {orphaned} orphaned link(s) found")
                warn_count += 1
        except Exception as exc:
            checks.append(f"FAIL Links: exception -- {exc}")
            fail_count += 1

        # ------------------------------------------------------------------ #
        # 6. Session journal health
        # ------------------------------------------------------------------ #
        try:
            bad_sessions = memory_store._conn.execute(
                """
                SELECT COUNT(*) FROM session_journal
                WHERE agent_id IS NULL OR start_time IS NULL
                """
            ).fetchone()[0]
            total_sessions = memory_store._conn.execute(
                "SELECT COUNT(*) FROM session_journal"
            ).fetchone()[0]
            if bad_sessions == 0:
                checks.append(f"PASS Sessions: all {total_sessions} sessions healthy")
                pass_count += 1
            else:
                checks.append(
                    f"WARN Sessions: {bad_sessions}/{total_sessions} with NULL agent_id or start_time"
                )
                warn_count += 1
        except Exception as exc:
            checks.append(f"FAIL Sessions: exception -- {exc}")
            fail_count += 1

        # ------------------------------------------------------------------ #
        # Build report
        # ------------------------------------------------------------------ #
        icon = {"PASS": "ok", "WARN": "!!", "FAIL": "XX"}
        lines = ["## Memory Integrity Report\n"]
        for c in checks:
            status = c.split(" ", 1)[0]
            symbol = icon.get(status, "??")
            lines.append(f"[{symbol}] {c}")

        total_checks = pass_count + warn_count + fail_count
        summary_parts = [f"{pass_count}/{total_checks} PASS"]
        if warn_count:
            summary_parts.append(f"{warn_count} WARNING")
        if fail_count:
            summary_parts.append(f"{fail_count} FAIL")
        lines.append(f"\nOverall: {', '.join(summary_parts)}")

        if verbose:
            lines.append("\n### Verbose details")
            try:
                mem_total = memory_store._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                tag_total = memory_store._conn.execute("SELECT COUNT(*) FROM memory_tags").fetchone()[0]
                link_total = memory_store._conn.execute("SELECT COUNT(*) FROM memory_links").fetchone()[0]
                sess_total = memory_store._conn.execute("SELECT COUNT(*) FROM session_journal").fetchone()[0]
                lines.append(f"- Memories: {mem_total}")
                lines.append(f"- Tags: {tag_total}")
                lines.append(f"- Links: {link_total}")
                lines.append(f"- Sessions: {sess_total}")
            except Exception:
                lines.append("- (could not gather verbose stats)")

        return "\n".join(lines)

    return handler


def register_integrity_tools(registry: ToolRegistry, memory_store: MemoryStore) -> None:
    """Register memory_selfcheck tool."""
    registry.register(
        "memory_selfcheck",
        _SELFCHECK_DEFINITION,
        _make_selfcheck_handler(memory_store),
        read_only=True,
    )
    logger.info("Registered memory_selfcheck tool")
