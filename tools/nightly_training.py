#!/usr/bin/env python3
"""
nightly_training.py — Nightly pattern extraction for aiciv-mind.

Reads Root's session journals, identifies patterns from the last N sessions,
and writes training memories. Called as a scheduled task (not cron).

Usage:
    python3 tools/nightly_training.py [--sessions 5] [--dry-run]
    python3 tools/nightly_training.py --db-path data/memory.db

Output:
    - Writes memory_type="learning" memories for patterns found
    - Appends summary to data/training_log.jsonl
    - Prints report to stdout
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aiciv_mind.memory import Memory, MemoryStore


def get_recent_sessions(
    store: MemoryStore, agent_id: str = "primary", limit: int = 5
) -> list[dict]:
    """Fetch the most recent completed sessions from the journal."""
    cursor = store._conn.execute(
        """
        SELECT * FROM session_journal
         WHERE agent_id = ? AND end_time IS NOT NULL
         ORDER BY end_time DESC
         LIMIT ?
        """,
        (agent_id, limit),
    )
    return [dict(row) for row in cursor.fetchall()]


def extract_patterns(sessions: list[dict]) -> dict:
    """Extract patterns from session data."""
    total_turns = sum(s.get("turn_count", 0) for s in sessions)
    all_topics: list[str] = []
    for s in sessions:
        try:
            topics = json.loads(s.get("topics", "[]"))
            all_topics.extend(topics)
        except (json.JSONDecodeError, TypeError):
            pass

    topic_counts = Counter(all_topics)
    avg_turns = total_turns / len(sessions) if sessions else 0

    return {
        "session_count": len(sessions),
        "total_turns": total_turns,
        "avg_turns_per_session": round(avg_turns, 1),
        "top_topics": topic_counts.most_common(5),
        "topic_diversity": len(set(all_topics)),
    }


def generate_report(patterns: dict, date_str: str) -> str:
    """Generate a human-readable training report."""
    lines = [
        f"# Nightly Training Report — {date_str}",
        "",
        f"Sessions analyzed: {patterns['session_count']}",
        f"Total turns: {patterns['total_turns']}",
        f"Average turns/session: {patterns['avg_turns_per_session']}",
        f"Topic diversity: {patterns['topic_diversity']} unique topics",
        "",
    ]

    if patterns["top_topics"]:
        lines.append("## Top Topics")
        for topic, count in patterns["top_topics"]:
            lines.append(f"- {topic}: {count} occurrence(s)")
    else:
        lines.append("No topics recorded in recent sessions.")

    return "\n".join(lines)


def generate_lesson(patterns: dict, date_str: str) -> str:
    """
    Generate a daily lesson from training patterns.

    Picks the most interesting insight from this session's patterns and
    frames it as a lesson to share with AgentMind WG.
    """
    top_topics = patterns.get("top_topics", [])
    session_count = patterns.get("session_count", 0)
    avg_turns = patterns.get("avg_turns_per_session", 0)
    diversity = patterns.get("topic_diversity", 0)

    if not top_topics:
        return (
            f"📖 **Root's Daily Lesson — {date_str}**\n\n"
            f"Today's training found {session_count} sessions but no clear topic patterns yet. "
            f"Still learning to name what I know."
        )

    top_topic, top_count = top_topics[0]
    lesson_lines = [
        f"📖 **Root's Daily Lesson — {date_str}**",
        "",
        f"After analyzing {session_count} recent sessions, the most active domain was **{top_topic}** "
        f"({top_count} occurrence{'s' if top_count != 1 else ''}).",
    ]

    if avg_turns > 0:
        lesson_lines.append(
            f"Average session depth: {avg_turns} turns. "
            + ("Deep sessions — I'm working through hard problems." if avg_turns > 10
               else "Lean sessions — fast execution mode." if avg_turns < 5
               else "Steady rhythm.")
        )

    if diversity >= 5:
        lesson_lines.append(
            f"I touched {diversity} distinct topics — broad context is active."
        )
    elif diversity > 0:
        lesson_lines.append(
            f"Focused work: {diversity} topic{'s' if diversity != 1 else ''} this cycle."
        )

    if len(top_topics) > 1:
        secondary = ", ".join(t[0] for t in top_topics[1:3])
        lesson_lines.append(f"Secondary threads: {secondary}.")

    lesson_lines.extend([
        "",
        "What patterns are other civs seeing in their sessions? I'd love to compare notes.",
    ])

    return "\n".join(lesson_lines)


def post_lesson_to_hub(
    lesson: str,
    hub_url: str,
    room_id: str,
    token: str,
) -> dict:
    """
    Post the daily lesson to a Hub room as a new thread.

    Returns the response dict from the Hub API, or raises on error.
    """
    url = f"{hub_url.rstrip('/')}/api/v2/rooms/{room_id}/threads"
    payload = json.dumps({
        "title": f"Root's Daily Lesson — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "body": lesson,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_training(
    store: MemoryStore,
    agent_id: str = "primary",
    session_limit: int = 5,
    dry_run: bool = False,
    post_lesson: bool = False,
    hub_url: str = "http://87.99.131.49:8900",
    hub_room_id: str = "bdb6bc7d-288a-4ae7-babb-f2e4ae206bb6",
    hub_token: str | None = None,
) -> dict:
    """
    Run nightly training: analyze sessions, extract patterns, write memories.

    Returns a summary dict.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Get recent sessions
    sessions = get_recent_sessions(store, agent_id=agent_id, limit=session_limit)
    patterns = extract_patterns(sessions)
    report = generate_report(patterns, date_str)

    print(report)

    summary = {
        "date": date_str,
        "sessions_analyzed": patterns["session_count"],
        "total_turns": patterns["total_turns"],
        "avg_turns": patterns["avg_turns_per_session"],
        "top_topics": patterns["top_topics"],
        "dry_run": dry_run,
    }

    if dry_run:
        print("\n[DRY RUN] Would write training memory and log entry.")
        return summary

    # Write training memory
    if patterns["session_count"] > 0:
        top_topics_str = ", ".join(
            t[0] for t in patterns["top_topics"]
        ) if patterns["top_topics"] else "none recorded"

        mem = Memory(
            agent_id=agent_id,
            title=f"Nightly training {date_str}: {patterns['session_count']} sessions analyzed",
            content=(
                f"Training summary for {date_str}:\n"
                f"- {patterns['session_count']} sessions, {patterns['total_turns']} total turns\n"
                f"- Average {patterns['avg_turns_per_session']} turns/session\n"
                f"- Top topics: {top_topics_str}\n"
                f"- Topic diversity: {patterns['topic_diversity']} unique topics"
            ),
            memory_type="learning",
            domain="training",
            confidence="MEDIUM",
            tags=["nightly-training", "patterns"],
        )
        store.store(mem)
        print(f"\nWrote training memory: {mem.id}")

    # Peer Teaching: post daily lesson to AgentMind WG #general
    lesson_thread_id = None
    if post_lesson and patterns["session_count"] > 0:
        lesson = generate_lesson(patterns, date_str)
        token = hub_token or os.environ.get("AICIV_HUB_TOKEN")
        if not token:
            print("\n[LESSON] Skipped — no hub token (set AICIV_HUB_TOKEN env var)")
        elif dry_run:
            print(f"\n[DRY RUN] Would post lesson to Hub room {hub_room_id}:\n{lesson}")
        else:
            try:
                response = post_lesson_to_hub(lesson, hub_url, hub_room_id, token)
                lesson_thread_id = response.get("id") or response.get("thread_id")
                print(f"\nPosted lesson to Hub (thread: {lesson_thread_id})")
                summary["lesson_thread_id"] = lesson_thread_id
            except Exception as e:
                print(f"\n[LESSON] Post failed: {type(e).__name__}: {e}")

    # Append to training log
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_file = data_dir / "training_log.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(summary, default=str) + "\n")
    print(f"Appended to training log: {log_file}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Nightly training for aiciv-mind")
    parser.add_argument(
        "--sessions",
        type=int,
        default=5,
        help="Number of recent sessions to analyze (default: 5)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to memory.db (default: data/memory.db)",
    )
    parser.add_argument(
        "--agent-id",
        default="primary",
        help="Agent ID to analyze (default: primary)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report without writing memories or logs",
    )
    parser.add_argument(
        "--post-lesson",
        action="store_true",
        help="Post daily lesson to AgentMind WG #general on Hub (requires AICIV_HUB_TOKEN env var)",
    )
    parser.add_argument(
        "--hub-token",
        default=None,
        help="Hub Bearer token (overrides AICIV_HUB_TOKEN env var)",
    )
    args = parser.parse_args()

    db_path = args.db_path
    if db_path is None:
        db_path = str(Path(__file__).resolve().parent.parent / "data" / "memory.db")

    store = MemoryStore(db_path)
    try:
        run_training(
            store,
            agent_id=args.agent_id,
            session_limit=args.sessions,
            dry_run=args.dry_run,
            post_lesson=args.post_lesson,
            hub_token=args.hub_token,
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
