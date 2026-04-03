"""
Meta-engineering quality tests for aiciv-mind.

Proves structural properties of the codebase: module count, tool descriptions,
syntax validity, design docs presence, test coverage breadth, and code quality.

Run with:
    cd /home/corey/projects/AI-CIV/aiciv-mind
    python -m pytest tests/test_engineering.py -v
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

PROJECT_ROOT = Path("/home/corey/projects/AI-CIV/aiciv-mind")
SRC_ROOT = PROJECT_ROOT / "src" / "aiciv_mind"
TESTS_DIR = PROJECT_ROOT / "tests"
DOCS_DIR = PROJECT_ROOT / "docs"


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


def test_source_module_count():
    """The src/aiciv_mind/ tree has at least 40 non-__init__ .py files."""
    py_files = [
        f for f in SRC_ROOT.rglob("*.py")
        if f.name != "__init__.py"
    ]
    assert len(py_files) >= 40, (
        f"Expected >= 40 source modules, found {len(py_files)}: "
        f"{[str(f.relative_to(SRC_ROOT)) for f in sorted(py_files)]}"
    )


def test_all_tools_have_descriptions():
    """Every tool registered by ToolRegistry.default() has a non-empty description."""
    from aiciv_mind.tools import ToolRegistry
    from aiciv_mind.memory import MemoryStore

    store = MemoryStore(":memory:")
    try:
        registry = ToolRegistry.default(memory_store=store, agent_id="test")
        tools = registry.build_anthropic_tools()
        for tool in tools:
            name = tool.get("name", "(unnamed)")
            desc = tool.get("description", "")
            assert desc and len(desc.strip()) > 0, (
                f"Tool '{name}' has empty or missing description"
            )
    finally:
        store.close()


def test_no_syntax_errors():
    """Every .py file under src/aiciv_mind/ parses without syntax errors."""
    failures = []
    for py_file in SRC_ROOT.rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
            ast.parse(source, filename=str(py_file))
        except SyntaxError as e:
            failures.append(f"{py_file.relative_to(SRC_ROOT)}: {e}")
    assert not failures, (
        f"Syntax errors in {len(failures)} file(s):\n" + "\n".join(failures)
    )


def test_design_docs_exist():
    """Key design documents exist in the docs/ directory."""
    # DESIGN-PRINCIPLES.md may be in docs/ or docs/research/
    design_principles = (
        (DOCS_DIR / "DESIGN-PRINCIPLES.md").exists()
        or (DOCS_DIR / "research" / "DESIGN-PRINCIPLES.md").exists()
    )
    assert design_principles, "DESIGN-PRINCIPLES.md not found in docs/ or docs/research/"

    checklist = DOCS_DIR / "CC-VS-AICIV-MIND-CHECKLIST.md"
    assert checklist.exists(), f"{checklist} does not exist"


def test_test_file_count():
    """The tests/ directory has at least 30 test files."""
    test_files = list(TESTS_DIR.glob("test_*.py"))
    assert len(test_files) >= 30, (
        f"Expected >= 30 test files, found {len(test_files)}"
    )


def test_default_registry_tool_count():
    """ToolRegistry.default() with memory_store registers at least 40 tools."""
    from aiciv_mind.tools import ToolRegistry
    from aiciv_mind.memory import MemoryStore

    store = MemoryStore(":memory:")
    try:
        registry = ToolRegistry.default(memory_store=store, agent_id="test")
        tool_names = registry.names()
        assert len(tool_names) >= 40, (
            f"Expected >= 40 tools, found {len(tool_names)}: {tool_names}"
        )
    finally:
        store.close()


def test_behavioral_test_matrix_exists():
    """docs/BEHAVIORAL-TEST-MATRIX.md exists."""
    matrix = DOCS_DIR / "BEHAVIORAL-TEST-MATRIX.md"
    assert matrix.exists(), f"{matrix} does not exist"


def test_no_god_functions():
    """No function in src/ exceeds 500 lines.

    Note: _run_task_body in mind.py is ~441 lines (the main mind loop).
    The threshold is set at 500 to allow for this known case while still
    catching any truly enormous functions that would indicate poor structure.
    """
    MAX_FUNCTION_LINES = 500
    violations = []
    for py_file in SRC_ROOT.rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue  # caught by test_no_syntax_errors

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Calculate line span
                start = node.lineno
                end = node.end_lineno or start
                length = end - start + 1
                if length > MAX_FUNCTION_LINES:
                    rel = py_file.relative_to(SRC_ROOT)
                    violations.append(
                        f"{rel}:{start} — {node.name}() is {length} lines"
                    )

    assert not violations, (
        f"God functions found (> {MAX_FUNCTION_LINES} lines):\n" + "\n".join(violations)
    )


def test_all_source_modules_importable():
    """
    Every module under aiciv_mind can be imported without error.

    This catches broken imports, missing dependencies, and circular import issues
    at the module level (not at runtime call sites).
    """
    failures = []
    package_path = str(SRC_ROOT.parent)  # src/

    # Walk the package tree and try importing each module
    for py_file in SRC_ROOT.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        # Convert file path to module name
        rel = py_file.relative_to(SRC_ROOT.parent)
        module_name = str(rel).replace("/", ".").removesuffix(".py")
        try:
            importlib.import_module(module_name)
        except Exception as e:
            failures.append(f"{module_name}: {type(e).__name__}: {e}")

    assert not failures, (
        f"Import failures in {len(failures)} module(s):\n" + "\n".join(failures)
    )
