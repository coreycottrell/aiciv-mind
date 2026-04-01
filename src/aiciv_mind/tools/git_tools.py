"""
aiciv_mind.tools.git_tools — Scoped git operations for Root.

Root can commit and push its own code in the aiciv-mind repo.
All operations are hard-scoped to REPO_PATH — Root cannot touch any other repo.

Safety:
  - No force push, branch deletion, or reset --hard.
  - Commit messages are auto-prefixed with [Root].
  - All commands run with cwd=REPO_PATH and a 30-second timeout.
"""

from __future__ import annotations

import asyncio

from aiciv_mind.tools import ToolRegistry

REPO_PATH = "/home/corey/projects/AI-CIV/aiciv-mind"
TIMEOUT_SECONDS = 30

# Patterns that are never allowed in any git command.
BLOCKED_PATTERNS: list[str] = [
    "--force",
    "-f",
    "branch -D",
    "branch -d",
    "reset --hard",
    "clean -f",
    "push --delete",
    "checkout --",
    "restore --staged",
]


async def _run_git(args: str) -> str:
    """Run a git command scoped to REPO_PATH. Returns stdout or error."""
    cmd = f"git -C {REPO_PATH} {args}"
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=REPO_PATH,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"TIMEOUT: git command exceeded {TIMEOUT_SECONDS}s"

        output = stdout.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            return f"GIT ERROR (exit {proc.returncode}):\n{output}"
        return output if output else "(no output)"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def _check_blocked(args: str) -> str | None:
    """Return an error string if the git args contain a blocked pattern."""
    for pattern in BLOCKED_PATTERNS:
        if pattern in args:
            return f"BLOCKED: git operation contains blocked pattern: '{pattern}'"
    return None


# ---------------------------------------------------------------------------
# git_status
# ---------------------------------------------------------------------------

_STATUS_DEFINITION: dict = {
    "name": "git_status",
    "description": (
        "Show the working tree status of the aiciv-mind repo. "
        "Returns modified, staged, and untracked files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


async def _status_handler(tool_input: dict) -> str:
    return await _run_git("status")


# ---------------------------------------------------------------------------
# git_diff
# ---------------------------------------------------------------------------

_DIFF_DEFINITION: dict = {
    "name": "git_diff",
    "description": (
        "Show changes in the aiciv-mind repo. "
        "By default shows unstaged changes. Use staged=true for staged changes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "If true, show staged changes (--cached). Default: false.",
            },
            "file_path": {
                "type": "string",
                "description": "Optional: diff a specific file (relative to repo root).",
            },
        },
    },
}


async def _diff_handler(tool_input: dict) -> str:
    args = "diff"
    if tool_input.get("staged"):
        args += " --cached"
    file_path = tool_input.get("file_path", "").strip()
    if file_path:
        # Reject absolute paths outside repo
        if file_path.startswith("/") and not file_path.startswith(REPO_PATH):
            return f"BLOCKED: file_path must be relative to {REPO_PATH}"
        args += f" -- {file_path}"
    return await _run_git(args)


# ---------------------------------------------------------------------------
# git_log
# ---------------------------------------------------------------------------

_LOG_DEFINITION: dict = {
    "name": "git_log",
    "description": (
        "Show recent commit history of the aiciv-mind repo. "
        "Returns the last N commits (default 10) in oneline format."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "Number of commits to show (default: 10, max: 50).",
            },
            "verbose": {
                "type": "boolean",
                "description": "If true, show full commit messages instead of oneline.",
            },
        },
    },
}


async def _log_handler(tool_input: dict) -> str:
    count = min(tool_input.get("count", 10), 50)
    if tool_input.get("verbose"):
        return await _run_git(f"log -{count} --format='%h %ai %s%n%b'")
    return await _run_git(f"log --oneline -{count}")


# ---------------------------------------------------------------------------
# git_add
# ---------------------------------------------------------------------------

_ADD_DEFINITION: dict = {
    "name": "git_add",
    "description": (
        "Stage files for commit in the aiciv-mind repo. "
        "Provide specific file paths (relative to repo root). "
        "Use files=['.'] to stage all changes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths to stage (relative to repo root).",
            },
        },
        "required": ["files"],
    },
}


async def _add_handler(tool_input: dict) -> str:
    files = tool_input.get("files", [])
    if not files:
        return "ERROR: No files provided"

    # Validate: no absolute paths outside repo
    for f in files:
        if f.startswith("/") and not f.startswith(REPO_PATH):
            return f"BLOCKED: file path must be relative to {REPO_PATH}: {f}"

    file_args = " ".join(f'"{f}"' for f in files)
    result = await _run_git(f"add {file_args}")
    if result == "(no output)":
        return f"Staged: {', '.join(files)}"
    return result


# ---------------------------------------------------------------------------
# git_commit
# ---------------------------------------------------------------------------

_COMMIT_DEFINITION: dict = {
    "name": "git_commit",
    "description": (
        "Create a git commit in the aiciv-mind repo. "
        "Your message will be auto-prefixed with '[Root] '. "
        "Stage files with git_add first."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Commit message (will be prefixed with '[Root] ').",
            },
        },
        "required": ["message"],
    },
}


async def _commit_handler(tool_input: dict) -> str:
    message = tool_input.get("message", "").strip()
    if not message:
        return "ERROR: No commit message provided"

    # Auto-prefix with [Root] if not already present
    if not message.startswith("[Root]"):
        message = f"[Root] {message}"

    # Escape single quotes in the message for shell safety
    safe_message = message.replace("'", "'\\''")
    return await _run_git(f"commit -m '{safe_message}'")


# ---------------------------------------------------------------------------
# git_push
# ---------------------------------------------------------------------------

_PUSH_DEFINITION: dict = {
    "name": "git_push",
    "description": (
        "Push commits to the remote (origin) of the aiciv-mind repo. "
        "Pushes the current branch. Force push is blocked."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


async def _push_handler(tool_input: dict) -> str:
    return await _run_git("push origin HEAD")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_git_tools(registry: ToolRegistry) -> None:
    """Register all git tools into the given ToolRegistry."""
    registry.register("git_status", _STATUS_DEFINITION, _status_handler, read_only=True)
    registry.register("git_diff", _DIFF_DEFINITION, _diff_handler, read_only=True)
    registry.register("git_log", _LOG_DEFINITION, _log_handler, read_only=True)
    registry.register("git_add", _ADD_DEFINITION, _add_handler, read_only=False)
    registry.register("git_commit", _COMMIT_DEFINITION, _commit_handler, read_only=False)
    registry.register("git_push", _PUSH_DEFINITION, _push_handler, read_only=False)
