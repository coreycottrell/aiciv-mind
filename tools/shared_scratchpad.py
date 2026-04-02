#!/usr/bin/env python3
"""
shared_scratchpad.py -- CLI to view Root and Mind-Lead scratchpads side-by-side.

Usage:
    python3 tools/shared_scratchpad.py                    # today
    python3 tools/shared_scratchpad.py --date 2026-04-01  # specific date
    python3 tools/shared_scratchpad.py --days 3           # last 3 days
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_SCRATCHPAD_DIR = Path("/home/corey/projects/AI-CIV/aiciv-mind/scratchpads")
MIND_LEAD_SCRATCHPAD_DIR = Path(
    "/home/corey/projects/AI-CIV/ACG/.claude/team-leads/mind/daily-scratchpads"
)


def _read_scratchpad(directory: Path, day: date) -> str | None:
    """Read a scratchpad file for the given date, returning None if absent."""
    path = directory / f"{day.isoformat()}.md"
    if path.exists():
        text = path.read_text().strip()
        return text if text else None
    return None


def render_day(day: date) -> str:
    """Render both scratchpads for a single day."""
    root = _read_scratchpad(ROOT_SCRATCHPAD_DIR, day)
    mind = _read_scratchpad(MIND_LEAD_SCRATCHPAD_DIR, day)

    lines: list[str] = [f"=== Shared Scratchpad: {day.isoformat()} ===", ""]

    lines.append("--- Root's Scratchpad ---")
    if root:
        lines.append(root)
    else:
        lines.append("(no scratchpad)")
    lines.append("")

    lines.append("--- Mind-Lead's Scratchpad ---")
    if mind:
        lines.append(mind)
    else:
        lines.append("(no scratchpad)")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View Root and Mind-Lead scratchpads side-by-side."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Specific date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Show last N days of scratchpads",
    )
    args = parser.parse_args()

    if args.days is not None:
        today = date.today()
        days = [today - timedelta(days=i) for i in range(args.days)]
        days.reverse()  # oldest first
        sections: list[str] = []
        for day in days:
            sections.append(render_day(day))
        print("\n\n".join(sections))
    else:
        if args.date:
            try:
                target = date.fromisoformat(args.date)
            except ValueError:
                print(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD.", file=sys.stderr)
                sys.exit(1)
        else:
            target = date.today()
        print(render_day(target))


if __name__ == "__main__":
    main()
