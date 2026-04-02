"""
aiciv_mind.tools.handoff_tools — Rich handoff context for session continuity.

The problem: shutdown() writes "last thing I said" as the handoff. The next
session loads that and has no idea what was built, deployed, or fixed.

The fix: handoff_context gathers git commits, evolution log entries, tool
inventory, and scratchpad state — so the handoff is a true picture of
where things stand, not just the last utterance.

Can be called explicitly by Root, and is also used by the enhanced shutdown.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from aiciv_mind.tools import ToolRegistry

logger = logging.getLogger(__name__)

_HANDOFF_CONTEXT_DEFINITION: dict = {
    "name": "handoff_context",
    "description": (
        "Generate a rich handoff summary for session continuity. Gathers: "
        "recent git commits, evolution log entries, available tools, scratchpad "
        "state, and memory stats. Use before ending a session, or when you want "
        "to verify what the next session will know about this one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "since_commits": {
                "type": "integer",
                "description": "Number of recent git commits to include (default: 10)",
            },
        },
    },
}


def _git_recent_commits(mind_root: str, n: int = 10) -> str:
    """Get recent git log entries."""
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=5,
            cwd=mind_root,
        )
        return result.stdout.strip() if result.returncode == 0 else "(git log failed)"
    except Exception as exc:
        return f"(git error: {exc})"


def _git_changed_files(mind_root: str) -> str:
    """Get uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, timeout=5,
            cwd=mind_root,
        )
        out = result.stdout.strip()
        return out if out else "(clean — no uncommitted changes)"
    except Exception:
        return "(git status failed)"


def _make_handoff_context_handler(
    memory_store=None,
    mind_root: str | None = None,
    registry: ToolRegistry | None = None,
):
    """Return the handoff_context handler closure."""

    def handoff_context_handler(tool_input: dict) -> str:
        n_commits = int(tool_input.get("since_commits", 10))
        sections: list[str] = ["## Handoff Context\n"]

        # 1. Recent git commits
        if mind_root:
            sections.append("### Recent Commits")
            sections.append(f"```\n{_git_recent_commits(mind_root, n_commits)}\n```")

            sections.append("### Uncommitted Changes")
            sections.append(_git_changed_files(mind_root))

        # 2. Evolution log (recent entries)
        if memory_store is not None:
            try:
                evolutions = memory_store._conn.execute(
                    """
                    SELECT change_type, description, reasoning, created_at
                    FROM evolution_log
                    ORDER BY created_at DESC
                    LIMIT 5
                    """
                ).fetchall()
                if evolutions:
                    sections.append("\n### Recent Evolution Log")
                    for ev in evolutions:
                        sections.append(
                            f"- **{ev['change_type']}**: {ev['description'][:120]}"
                        )
                else:
                    sections.append("\n### Recent Evolution Log\n(no entries)")
            except Exception:
                sections.append("\n### Recent Evolution Log\n(table not found or query failed)")

        # 3. Memory stats
        if memory_store is not None:
            try:
                mem_count = memory_store._conn.execute(
                    "SELECT COUNT(*) FROM memories"
                ).fetchone()[0]
                sess_count = memory_store._conn.execute(
                    "SELECT COUNT(*) FROM session_journal"
                ).fetchone()[0]
                link_count = memory_store._conn.execute(
                    "SELECT COUNT(*) FROM memory_links"
                ).fetchone()[0]
                sections.append(f"\n### Memory Stats")
                sections.append(
                    f"- Memories: {mem_count} | Sessions: {sess_count} | Links: {link_count}"
                )

                # Recent learnings
                recent = memory_store.by_type(
                    memory_type="learning",
                    agent_id="primary",
                    limit=5,
                )
                if recent:
                    sections.append("\n### Recent Learnings")
                    for m in recent:
                        title = m.get("title", "untitled")[:80]
                        sections.append(f"- {title}")
            except Exception as exc:
                sections.append(f"\n### Memory Stats\n(error: {exc})")

        # 4. Available tools
        if registry is not None:
            tool_names = registry.names()
            sections.append(f"\n### Available Tools ({len(tool_names)})")
            # Group in columns for readability
            chunks = [tool_names[i:i + 5] for i in range(0, len(tool_names), 5)]
            for chunk in chunks:
                sections.append(", ".join(chunk))

        # 5. Scratchpad state
        if mind_root:
            from datetime import date
            scratchpad_dir = Path(mind_root) / "scratchpads"
            today_pad = scratchpad_dir / f"{date.today().isoformat()}.md"
            if today_pad.exists():
                content = today_pad.read_text().strip()
                # Show first 500 chars
                preview = content[:500]
                if len(content) > 500:
                    preview += "\n... (truncated)"
                sections.append(f"\n### Today's Scratchpad")
                sections.append(preview)
            else:
                sections.append(f"\n### Today's Scratchpad\n(none for {date.today().isoformat()})")

        return "\n".join(sections)

    return handoff_context_handler


def register_handoff_tools(
    registry: ToolRegistry,
    memory_store=None,
    mind_root: str | None = None,
) -> None:
    """Register handoff_context tool."""
    registry.register(
        "handoff_context",
        _HANDOFF_CONTEXT_DEFINITION,
        _make_handoff_context_handler(
            memory_store=memory_store,
            mind_root=mind_root,
            registry=registry,
        ),
        read_only=True,
    )
    logger.info("Registered handoff_context tool")
