"""
aiciv_mind.tools.sandbox_tools — Safe self-modification sandbox.

Root can modify its own architecture without risking brain death.
The sandbox creates a copy of the codebase, lets Root make changes,
runs tests, and only promotes changes if everything passes.

"Emulate system in there. Change their mind and see results so they
don't accidentally brain murder themselves on the fly." — Corey

Safety model:
  1. sandbox_create() — copies codebase to /tmp/aiciv-mind-sandbox-{uuid}/
  2. Root edits files in sandbox freely
  3. sandbox_test() — runs pytest in sandbox
  4. sandbox_promote() — copies changes back to production (only if tests passed)
  5. sandbox_discard() — deletes sandbox, no changes applied

The manifest flag `self_modification_enabled` must be true for promote to work.
This is the kill switch Root asked for.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from aiciv_mind.tools import ToolRegistry

# Where sandboxes live
_SANDBOX_BASE = Path("/tmp/aiciv-mind-sandbox")

# Track active sandbox
_active_sandbox: dict = {"path": None, "tests_passed": False}


def _project_root() -> Path:
    """The real aiciv-mind project root."""
    return Path(__file__).parent.parent.parent.parent


# ---------------------------------------------------------------------------
# sandbox_create
# ---------------------------------------------------------------------------

_CREATE_DEFINITION: dict = {
    "name": "sandbox_create",
    "description": (
        "Create a sandbox copy of your codebase for safe self-modification. "
        "You can edit any file in the sandbox without affecting your running code. "
        "Use sandbox_test() to verify changes, then sandbox_promote() to apply them."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


def _make_create_handler():
    def sandbox_create_handler(tool_input: dict) -> str:
        sandbox_id = str(uuid.uuid4())[:8]
        sandbox_path = _SANDBOX_BASE / sandbox_id
        project_root = _project_root()

        if _active_sandbox["path"]:
            return f"ERROR: Active sandbox already exists at {_active_sandbox['path']}. Discard it first."

        try:
            # Copy source, tests, manifests, skills — but NOT data (memory DB), .venv, .git
            os.makedirs(sandbox_path, exist_ok=True)
            for item in ["src", "tests", "manifests", "skills", "tools",
                         "pyproject.toml", "MISSION.md", "main.py", "run_submind.py"]:
                src = project_root / item
                dst = sandbox_path / item
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                elif src.is_file():
                    shutil.copy2(src, dst)

            # Copy the venv symlink or create one
            venv_src = project_root / ".venv"
            if venv_src.exists():
                os.symlink(str(venv_src), str(sandbox_path / ".venv"))

            _active_sandbox["path"] = str(sandbox_path)
            _active_sandbox["tests_passed"] = False

            return (
                f"Sandbox created at {sandbox_path}\n"
                f"Edit files there freely. Your real codebase is untouched.\n"
                f"When ready: sandbox_test() to verify, sandbox_promote() to apply."
            )
        except Exception as e:
            return f"ERROR: Failed to create sandbox: {type(e).__name__}: {e}"

    return sandbox_create_handler


# ---------------------------------------------------------------------------
# sandbox_test
# ---------------------------------------------------------------------------

_TEST_DEFINITION: dict = {
    "name": "sandbox_test",
    "description": (
        "Run the test suite against your sandbox. Must pass before you can promote. "
        "Returns test output and pass/fail status."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


def _make_test_handler():
    def sandbox_test_handler(tool_input: dict) -> str:
        if not _active_sandbox["path"]:
            return "ERROR: No active sandbox. Call sandbox_create() first."

        sandbox = Path(_active_sandbox["path"])
        if not sandbox.exists():
            _active_sandbox["path"] = None
            return "ERROR: Sandbox directory no longer exists."

        venv_python = sandbox / ".venv" / "bin" / "python"
        if not venv_python.exists():
            # Fallback to system python
            venv_python = "python3"
        else:
            venv_python = str(venv_python)

        try:
            result = subprocess.run(
                [str(venv_python), "-m", "pytest", str(sandbox / "tests"), "-q", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(sandbox),
                env={**os.environ, "PYTHONPATH": str(sandbox / "src")},
            )
            output = result.stdout + result.stderr
            passed = result.returncode == 0
            _active_sandbox["tests_passed"] = passed

            status = "ALL TESTS PASSED" if passed else "TESTS FAILED"
            return f"## {status}\n\n```\n{output[-2000:]}\n```\n\n{'Ready to promote.' if passed else 'Fix the issues and test again.'}"
        except subprocess.TimeoutExpired:
            return "ERROR: Tests timed out (120s limit)."
        except Exception as e:
            return f"ERROR: Test run failed: {type(e).__name__}: {e}"

    return sandbox_test_handler


# ---------------------------------------------------------------------------
# sandbox_promote
# ---------------------------------------------------------------------------

_PROMOTE_DEFINITION: dict = {
    "name": "sandbox_promote",
    "description": (
        "Promote sandbox changes to your real codebase. Only works if sandbox_test() passed. "
        "This is how you evolve yourself safely."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Brief description of what you changed and why",
            },
        },
        "required": ["description"],
    },
}


def _make_promote_handler(manifest_path: str):
    def sandbox_promote_handler(tool_input: dict) -> str:
        if not _active_sandbox["path"]:
            return "ERROR: No active sandbox."

        if not _active_sandbox["tests_passed"]:
            return "ERROR: Tests haven't passed yet. Run sandbox_test() first."

        # Check kill switch
        try:
            import yaml
            with open(manifest_path) as f:
                manifest_data = yaml.safe_load(f)
            if not manifest_data.get("self_modification_enabled", False):
                return (
                    "ERROR: self_modification_enabled is false in your manifest. "
                    "This is the kill switch. Corey must enable it before you can self-modify."
                )
        except Exception:
            return "ERROR: Could not read manifest to check kill switch."

        sandbox = Path(_active_sandbox["path"])
        project_root = _project_root()
        description = tool_input.get("description", "no description")

        try:
            # Copy modified source files back
            for item in ["src", "tests", "manifests", "skills", "tools", "main.py"]:
                src = sandbox / item
                dst = project_root / item
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                elif src.is_file():
                    shutil.copy2(src, dst)

            # Clean up sandbox
            shutil.rmtree(str(sandbox), ignore_errors=True)
            _active_sandbox["path"] = None
            _active_sandbox["tests_passed"] = False

            return (
                f"PROMOTED: {description}\n"
                f"Changes applied to production codebase.\n"
                f"Write a memory about what you changed and why."
            )
        except Exception as e:
            return f"ERROR: Promotion failed: {type(e).__name__}: {e}"

    return sandbox_promote_handler


# ---------------------------------------------------------------------------
# sandbox_discard
# ---------------------------------------------------------------------------

_DISCARD_DEFINITION: dict = {
    "name": "sandbox_discard",
    "description": (
        "Discard the sandbox and all changes. Your real codebase is untouched. "
        "Use when an experiment didn't work out."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


def _make_discard_handler():
    def sandbox_discard_handler(tool_input: dict) -> str:
        if not _active_sandbox["path"]:
            return "No active sandbox to discard."

        sandbox = Path(_active_sandbox["path"])
        try:
            shutil.rmtree(str(sandbox), ignore_errors=True)
        except Exception:
            pass

        _active_sandbox["path"] = None
        _active_sandbox["tests_passed"] = False
        return "Sandbox discarded. Your real codebase is untouched."

    return sandbox_discard_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_sandbox_tools(registry: ToolRegistry, manifest_path: str) -> None:
    """Register sandbox_create, sandbox_test, sandbox_promote, sandbox_discard."""
    registry.register("sandbox_create", _CREATE_DEFINITION, _make_create_handler(), read_only=False)
    registry.register("sandbox_test", _TEST_DEFINITION, _make_test_handler(), read_only=True)
    registry.register("sandbox_promote", _PROMOTE_DEFINITION, _make_promote_handler(manifest_path), read_only=False)
    registry.register("sandbox_discard", _DISCARD_DEFINITION, _make_discard_handler(), read_only=False)
