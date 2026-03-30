"""
aiciv_mind.tools.search — File search tools: grep and glob.

Both tools are read_only=True (safe for concurrent execution).

grep: Regex-based content search across files.
  - Returns matching lines in '{file}:{line_num}: {content}' format.
  - Optional context lines (before/after each match).
  - Truncates output at 200 lines to avoid flooding context.

glob: File discovery by path pattern.
  - Uses pathlib rglob for recursive patterns.
  - Returns sorted paths, one per line.
  - Truncates at 200 results.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from aiciv_mind.tools import ToolRegistry

MAX_LINES: int = 200
MAX_FILES: int = 200

# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------

_GREP_DEFINITION: dict = {
    "name": "grep",
    "description": (
        "Search file contents using a regex pattern. "
        "Returns matching lines in '{file}:{line_num}: {content}' format. "
        "Optionally filter by glob pattern (e.g. '*.py') and include context lines. "
        "Results truncated at 200 lines."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "Directory or file path to search in",
            },
            "glob": {
                "type": "string",
                "description": (
                    "Glob pattern to filter files (e.g. '*.py', '**/*.ts'). "
                    "Only used when path is a directory."
                ),
            },
            "context": {
                "type": "integer",
                "description": "Number of lines of context to show before and after each match",
            },
        },
        "required": ["pattern", "path"],
    },
}


def _iter_files(search_path: Path, glob_pattern: str | None) -> Iterator[Path]:
    """Yield files to search, respecting glob filter if provided."""
    if search_path.is_file():
        yield search_path
        return

    if not search_path.is_dir():
        return

    pattern = glob_pattern or "**/*"
    for p in sorted(search_path.rglob(pattern if "**" in pattern else f"**/{pattern}")):
        if p.is_file():
            yield p


def grep_handler(tool_input: dict) -> str:
    """Search files for a regex pattern, returning matching lines."""
    pattern_str: str = tool_input.get("pattern", "")
    path_str: str = tool_input.get("path", "")
    glob_pattern: str | None = tool_input.get("glob")
    context_lines: int = int(tool_input.get("context", 0))

    if not pattern_str:
        return "ERROR: No pattern provided"
    if not path_str:
        return "ERROR: No path provided"

    search_path = Path(path_str)
    if not search_path.exists():
        return f"ERROR: Path not found: {path_str}"

    try:
        regex = re.compile(pattern_str)
    except re.error as e:
        return f"ERROR: Invalid regex pattern: {e}"

    output_lines: list[str] = []
    total_matches: int = 0

    for file_path in _iter_files(search_path, glob_pattern):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except (PermissionError, IsADirectoryError, OSError):
            continue

        lines = text.splitlines()
        match_indices: list[int] = [i for i, line in enumerate(lines) if regex.search(line)]

        if not match_indices:
            continue

        # Collect lines to emit (with context, deduplicated by index).
        emit_set: set[int] = set()
        for idx in match_indices:
            start = max(0, idx - context_lines)
            end = min(len(lines) - 1, idx + context_lines)
            for j in range(start, end + 1):
                emit_set.add(j)

        for line_idx in sorted(emit_set):
            is_match = line_idx in set(match_indices)
            separator = ":" if is_match else "-"
            line_num = line_idx + 1  # 1-based
            output_lines.append(f"{file_path}:{line_num}{separator} {lines[line_idx]}")
            if is_match:
                total_matches += 1

            if len(output_lines) >= MAX_LINES:
                output_lines.append(f"... (truncated at {MAX_LINES} lines)")
                return "\n".join(output_lines)

    if not output_lines:
        return "No matches found"

    return "\n".join(output_lines)


# ---------------------------------------------------------------------------
# glob
# ---------------------------------------------------------------------------

_GLOB_DEFINITION: dict = {
    "name": "glob",
    "description": (
        "Find files by glob pattern. "
        "Returns sorted list of matching file paths, one per line. "
        "Use '**/*.py' for recursive search. "
        "Results truncated at 200 entries."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match (e.g. '**/*.py', '*.json')",
            },
            "path": {
                "type": "string",
                "description": "Base directory to search from (optional, defaults to cwd)",
            },
        },
        "required": ["pattern"],
    },
}


def glob_handler(tool_input: dict) -> str:
    """Find files matching a glob pattern, return sorted list."""
    pattern: str = tool_input.get("pattern", "")
    path_str: str | None = tool_input.get("path")

    if not pattern:
        return "ERROR: No pattern provided"

    base = Path(path_str) if path_str else Path.cwd()

    if not base.exists():
        return f"ERROR: Base path not found: {base}"
    if not base.is_dir():
        return f"ERROR: Base path is not a directory: {base}"

    try:
        # Use rglob if pattern contains ** or no slash (treat as recursive).
        # Otherwise use glob from base.
        if "**" in pattern:
            matches = sorted(str(p) for p in base.glob(pattern) if p.is_file())
        else:
            matches = sorted(str(p) for p in base.glob(pattern) if p.is_file())
            if not matches:
                # Also try rglob for bare patterns without leading **
                matches = sorted(str(p) for p in base.rglob(pattern) if p.is_file())
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

    if not matches:
        return "No matches found"

    if len(matches) > MAX_FILES:
        result = matches[:MAX_FILES]
        result.append(f"... (truncated at {MAX_FILES} results, {len(matches)} total)")
        return "\n".join(result)

    return "\n".join(matches)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_search(registry: ToolRegistry) -> None:
    """Register grep and glob into the given ToolRegistry."""
    registry.register("grep", _GREP_DEFINITION, grep_handler, read_only=True)
    registry.register("glob", _GLOB_DEFINITION, glob_handler, read_only=True)
