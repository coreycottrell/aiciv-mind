#!/usr/bin/env python3
"""
aiciv-mind -- Primary Mind Entry Point

Usage:
    python3 main.py                                   # Use default primary.yaml
    python3 main.py --manifest manifests/custom.yaml  # Custom manifest
    python3 main.py --task "Do something"             # Non-interactive single task
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path for development installs
sys.path.insert(0, str(Path(__file__).parent / "src"))


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


async def run_primary(manifest_path: str, task: str | None = None) -> None:
    from aiciv_mind.manifest import MindManifest
    from aiciv_mind.memory import MemoryStore
    from aiciv_mind.tools import ToolRegistry
    from aiciv_mind.mind import Mind
    from aiciv_mind.interactive import InteractiveREPL

    # Load manifest
    manifest = MindManifest.from_yaml(manifest_path)

    # Ensure data directory exists (skip for in-memory db)
    db_path = manifest.memory.db_path
    if db_path != ":memory:":
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    # Initialize memory
    memory = MemoryStore(db_path)

    # Build tool registry
    tools = ToolRegistry.default(memory_store=memory)

    # Create mind
    mind = Mind(manifest=manifest, memory=memory, tools=tools)

    try:
        if task:
            # Non-interactive single task
            result = await mind.run_task(task)
            print(result)
        else:
            # Interactive REPL
            repl = InteractiveREPL(mind)
            await repl.run()
    finally:
        memory.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="aiciv-mind primary mind")
    parser.add_argument(
        "--manifest",
        default="manifests/primary.yaml",
        help="Path to mind manifest YAML (default: manifests/primary.yaml)",
    )
    parser.add_argument("--task", help="Run a single task non-interactively")
    parser.add_argument("--log-level", default="INFO", help="Log level (default: INFO)")
    args = parser.parse_args()

    setup_logging(args.log_level)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = Path(__file__).parent / manifest_path

    if not manifest_path.exists():
        print(f"ERROR: Manifest not found: {manifest_path}")
        sys.exit(1)

    asyncio.run(run_primary(str(manifest_path), task=args.task))


if __name__ == "__main__":
    main()
