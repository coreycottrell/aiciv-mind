"""
aiciv_mind.kairos — Append-only daily log for persistent minds.

Named after KAIROS (qualitative time). For minds that run continuously
(not per-conversation), the standard session-based memory breaks.
KAIROS uses:
  1. Append-only daily log: data/logs/YYYY/MM/DD.md — timestamped bullets
  2. Nightly distillation by dream_cycle reads daily logs → consolidates

Usage:
    kairos = KairosLog(data_dir="data/logs")
    kairos.append("Processed 3 Hub threads, replied to 2")
    kairos.append("Error: AgentAuth JWKS timeout", level="error")

    # Read today's log
    entries = kairos.read_today()

    # Distill recent logs (called by dream cycle)
    summary = kairos.distill(days=7)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class KairosEntry:
    """A single timestamped log entry."""
    timestamp: str
    level: str  # "info" | "warn" | "error" | "milestone"
    text: str

    def to_line(self) -> str:
        prefix = f"[{self.level.upper()}] " if self.level != "info" else ""
        return f"- `{self.timestamp}` {prefix}{self.text}\n"

    @classmethod
    def from_line(cls, line: str) -> KairosEntry | None:
        """Parse a markdown bullet line back into a KairosEntry."""
        line = line.strip()
        if not line.startswith("- `"):
            return None
        try:
            # Extract timestamp between backticks
            ts_start = line.index("`") + 1
            ts_end = line.index("`", ts_start)
            timestamp = line[ts_start:ts_end]
            rest = line[ts_end + 2:]  # skip "` "

            # Parse level tag if present
            level = "info"
            for tag in ["[ERROR]", "[WARN]", "[MILESTONE]"]:
                if rest.startswith(tag + " "):
                    level = tag[1:-1].lower()
                    rest = rest[len(tag) + 1:]
                    break

            return cls(timestamp=timestamp, level=level, text=rest)
        except (ValueError, IndexError):
            return None


class KairosLog:
    """
    Append-only daily log for persistent/continuous minds.

    Organizes entries into daily files: {data_dir}/YYYY/MM/DD.md
    Each file has a header and timestamped bullet entries.
    """

    def __init__(self, data_dir: str | Path, agent_id: str = "primary") -> None:
        self._data_dir = Path(data_dir)
        self._agent_id = agent_id

    def _daily_path(self, dt: datetime | None = None) -> Path:
        """Return the path for a given day's log file."""
        if dt is None:
            dt = datetime.now(timezone.utc)
        return self._data_dir / dt.strftime("%Y") / dt.strftime("%m") / f"{dt.strftime('%d')}.md"

    def append(self, text: str, level: str = "info", dt: datetime | None = None) -> Path:
        """
        Append an entry to today's log.

        Args:
            text: The log entry text
            level: "info", "warn", "error", or "milestone"
            dt: Override timestamp (default: now UTC)

        Returns:
            Path to the daily log file
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        path = self._daily_path(dt)
        path.parent.mkdir(parents=True, exist_ok=True)

        entry = KairosEntry(
            timestamp=dt.strftime("%H:%M:%S"),
            level=level,
            text=text.strip(),
        )

        # Create file with header if new
        if not path.exists():
            header = f"# {self._agent_id} — {dt.strftime('%Y-%m-%d')}\n\n"
            path.write_text(header, encoding="utf-8")

        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.to_line())

        return path

    def read_today(self) -> list[KairosEntry]:
        """Read all entries from today's log."""
        return self.read_day()

    def read_day(self, dt: datetime | None = None) -> list[KairosEntry]:
        """Read all entries from a specific day's log."""
        path = self._daily_path(dt)
        if not path.exists():
            return []

        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = KairosEntry.from_line(line)
            if entry:
                entries.append(entry)
        return entries

    def read_range(self, days: int = 7) -> dict[str, list[KairosEntry]]:
        """
        Read entries from the last N days.

        Returns:
            Dict mapping date strings to entry lists, e.g.:
            {"2026-04-03": [...], "2026-04-02": [...]}
        """
        now = datetime.now(timezone.utc)
        result: dict[str, list[KairosEntry]] = {}

        for offset in range(days):
            dt = now - timedelta(days=offset)
            date_str = dt.strftime("%Y-%m-%d")
            entries = self.read_day(dt)
            if entries:
                result[date_str] = entries

        return result

    def distill(self, days: int = 7) -> str:
        """
        Produce a distillation summary of recent logs.

        Returns a markdown summary suitable for writing to memory or
        feeding to the dream cycle.
        """
        logs = self.read_range(days)
        if not logs:
            return f"No KAIROS entries in the last {days} days."

        lines = [f"## KAIROS Distillation ({days}-day window)\n"]
        total_entries = 0
        error_count = 0
        milestone_count = 0

        for date_str in sorted(logs.keys(), reverse=True):
            entries = logs[date_str]
            total_entries += len(entries)
            errors = [e for e in entries if e.level == "error"]
            milestones = [e for e in entries if e.level == "milestone"]
            error_count += len(errors)
            milestone_count += len(milestones)

            lines.append(f"\n### {date_str} ({len(entries)} entries)")
            if milestones:
                for m in milestones:
                    lines.append(f"  - **MILESTONE** {m.text}")
            if errors:
                for e in errors:
                    lines.append(f"  - **ERROR** {e.text}")
            # Summarize non-error, non-milestone entries
            info_count = len(entries) - len(errors) - len(milestones)
            if info_count > 0:
                lines.append(f"  - {info_count} routine entries")

        lines.append(f"\n**Totals:** {total_entries} entries, {milestone_count} milestones, {error_count} errors")
        return "\n".join(lines)

    def entry_count(self, dt: datetime | None = None) -> int:
        """Count entries for a specific day."""
        return len(self.read_day(dt))

    def recent_errors(self, days: int = 3) -> list[KairosEntry]:
        """Get all error entries from the last N days."""
        errors = []
        logs = self.read_range(days)
        for entries in logs.values():
            errors.extend(e for e in entries if e.level == "error")
        return errors
