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


def load_dotenv() -> None:
    """Load .env from project root if present (no external deps required)."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


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
    from aiciv_mind.session_store import SessionStore
    from aiciv_mind.context_manager import ContextManager

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

    # Session lifecycle + context management
    session_store = SessionStore(memory, agent_id=manifest.mind_id)
    boot = session_store.boot()

    ctx_mgr = ContextManager(
        max_context_memories=manifest.memory.max_context_memories,
        model_max_tokens=manifest.model.max_tokens,
    )
    boot_str = ctx_mgr.format_boot_context(boot)
    if boot_str:
        logging.getLogger("aiciv_mind.main").info(
            "Loaded boot context: session %s (prior sessions: %d)",
            boot.session_id,
            boot.session_count,
        )

    # Create mind
    mind = Mind(
        manifest=manifest,
        memory=memory,
        tools=tools,
        session_store=session_store,
        context_manager=ctx_mgr,
        boot_context_str=boot_str,
    )

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
        # Write session handoff before exit — the next session will load this
        session_store.shutdown(mind._messages)
        memory.close()


def main() -> None:
    load_dotenv()
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
