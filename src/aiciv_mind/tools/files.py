"""
aiciv_mind.tools.files — File I/O tools: read_file, write_file, edit_file.

Design notes:
  - read_file returns content in cat -n format (line_num TAB line) for easy referencing.
  - write_file creates parent directories automatically.
  - edit_file requires the old_string to appear EXACTLY ONCE — ambiguous edits are rejected.
  - read_file is read_only=True; write/edit are read_only=False.
"""

from __future__ import annotations

from pathlib import Path

from aiciv_mind.tools import ToolRegistry

# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

_READ_DEFINITION: dict = {
    "name": "read_file",
    "description": (
        "Read a file and return its contents with line numbers. "
        "Optionally provide offset (1-based line number to start from) and limit "
        "(number of lines to return). Returns content in 'N\\tline' format."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to read",
            },
            "offset": {
                "type": "integer",
                "description": "1-based line number to start reading from (optional)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to return (optional)",
            },
        },
        "required": ["file_path"],
    },
}


def read_file_handler(tool_input: dict) -> str:
    """Read a file, return lines with line numbers in cat -n style."""
    file_path = tool_input.get("file_path", "").strip()
    offset: int = tool_input.get("offset", 1)
    limit: int | None = tool_input.get("limit")

    if not file_path:
        return "ERROR: No file_path provided"

    path = Path(file_path)
    if not path.exists():
        return f"ERROR: File not found: {file_path}"
    if not path.is_file():
        return f"ERROR: Path is not a file: {file_path}"

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return f"ERROR: Permission denied: {file_path}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

    lines = text.splitlines(keepends=True)

    # Normalise offset to 0-based index; clamp to valid range.
    start: int = max(0, (offset or 1) - 1)
    if limit is not None:
        end: int = start + limit
        selected = lines[start:end]
    else:
        selected = lines[start:]

    if not selected:
        return "(file is empty or offset beyond end of file)"

    result_lines: list[str] = []
    for i, line in enumerate(selected, start=start + 1):
        # Strip trailing newline for display; the format is "N\tline"
        result_lines.append(f"{i}\t{line.rstrip(chr(10)).rstrip(chr(13))}")

    return "\n".join(result_lines)


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

_WRITE_DEFINITION: dict = {
    "name": "write_file",
    "description": (
        "Write content to a file, overwriting it if it already exists. "
        "Parent directories are created automatically. "
        "Returns a summary of bytes written."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["file_path", "content"],
    },
}


def write_file_handler(tool_input: dict) -> str:
    """Write content to a file, creating parent directories as needed."""
    file_path = tool_input.get("file_path", "").strip()
    content: str = tool_input.get("content", "")

    if not file_path:
        return "ERROR: No file_path provided"

    path = Path(file_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        path.write_bytes(encoded)
        return f"Written {len(encoded)} bytes to {file_path}"
    except PermissionError:
        return f"ERROR: Permission denied: {file_path}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

_EDIT_DEFINITION: dict = {
    "name": "edit_file",
    "description": (
        "Replace a unique string in a file with a new string. "
        "The old_string must appear exactly once in the file — "
        "if it is not found or appears multiple times, the edit is rejected. "
        "Use read_file first to confirm the exact text to replace."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to edit",
            },
            "old_string": {
                "type": "string",
                "description": "The exact string to replace (must appear exactly once)",
            },
            "new_string": {
                "type": "string",
                "description": "The replacement string",
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    },
}


def edit_file_handler(tool_input: dict) -> str:
    """Replace a unique occurrence of old_string with new_string in a file."""
    file_path = tool_input.get("file_path", "").strip()
    old_string: str = tool_input.get("old_string", "")
    new_string: str = tool_input.get("new_string", "")

    if not file_path:
        return "ERROR: No file_path provided"

    path = Path(file_path)
    if not path.exists():
        return f"ERROR: File not found: {file_path}"
    if not path.is_file():
        return f"ERROR: Path is not a file: {file_path}"

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return f"ERROR: Permission denied: {file_path}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

    count = content.count(old_string)
    if count == 0:
        return "ERROR: old_string not found in file"
    if count > 1:
        return f"ERROR: old_string found {count} times — must be unique"

    new_content = content.replace(old_string, new_string, 1)
    try:
        path.write_text(new_content, encoding="utf-8")
    except PermissionError:
        return f"ERROR: Permission denied writing: {file_path}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

    return f"Replaced 1 occurrence in {file_path}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_files(registry: ToolRegistry) -> None:
    """Register read_file, write_file, and edit_file into the given ToolRegistry."""
    registry.register("read_file", _READ_DEFINITION, read_file_handler, read_only=True)
    registry.register("write_file", _WRITE_DEFINITION, write_file_handler, read_only=False)
    registry.register("edit_file", _EDIT_DEFINITION, edit_file_handler, read_only=False)
