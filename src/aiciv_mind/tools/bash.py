"""
aiciv_mind.tools.bash — Async subprocess bash tool with safety guards.

Safety model:
  - Blocked patterns list prevents the most dangerous commands.
  - Hard 30-second timeout; process is killed if exceeded.
  - stdout + stderr combined so the agent always sees full output.
  - Non-zero exit codes are reported explicitly (EXIT CODE N:).
"""

from __future__ import annotations

import asyncio

from aiciv_mind.tools import ToolRegistry

# Commands that are never allowed, regardless of context.
BLOCKED_PATTERNS: list[str] = [
    "rm -rf /",
    "rm -rf ~",
    "git push --force",
    "> /dev/",
    ":(){ :|:& };:",  # fork bomb
]

TIMEOUT_SECONDS: int = 30

DEFINITION: dict = {
    "name": "bash",
    "description": (
        "Execute a bash command and return its output. "
        "Use for file operations, running scripts, checking system state. "
        "Timeout: 30 seconds. Stdout + stderr combined."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute",
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory (optional, defaults to cwd)",
            },
        },
        "required": ["command"],
    },
}


async def bash_handler(tool_input: dict) -> str:
    """Execute a shell command and return combined stdout/stderr as a string."""
    command: str = tool_input.get("command", "").strip()
    working_dir: str | None = tool_input.get("working_dir")

    if not command:
        return "ERROR: No command provided"

    # Safety: block dangerous patterns before any execution.
    for pattern in BLOCKED_PATTERNS:
        if pattern in command:
            return f"BLOCKED: Command contains blocked pattern: '{pattern}'"

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=working_dir,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"TIMEOUT: Command exceeded {TIMEOUT_SECONDS}s limit"

        output: str = stdout.decode("utf-8", errors="replace")
        exit_code: int = proc.returncode  # type: ignore[assignment]

        if exit_code != 0:
            return f"EXIT CODE {exit_code}:\n{output}"
        return output if output else "(no output)"

    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def register_bash(registry: ToolRegistry) -> None:
    """Register the bash tool into the given ToolRegistry."""
    registry.register("bash", DEFINITION, bash_handler, read_only=False)
