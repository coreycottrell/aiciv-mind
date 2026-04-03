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


async def run_primary(manifest_path: str, task: str | None = None, converse: list[str] | None = None) -> None:
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

    # Try to connect to AiCIV Suite (graceful degradation if unavailable)
    suite_client = None
    try:
        auth_cfg = getattr(manifest, 'auth', None)
        keypair_path = getattr(auth_cfg, 'keypair_path', None) if auth_cfg else None
        if keypair_path and Path(keypair_path).exists():
            from aiciv_mind.suite.client import SuiteClient
            suite_client = await SuiteClient.connect(keypair_path, eager_auth=True)
            logging.getLogger("aiciv_mind.main").info("SuiteClient connected — hub tools enabled")
        else:
            logging.getLogger("aiciv_mind.main").info("No keypair found — hub tools disabled")
    except Exception as e:
        logging.getLogger("aiciv_mind.main").warning(
            "SuiteClient connect failed: %s — hub tools disabled", e
        )

    # Initialize sub-mind orchestration (optional — requires libtmux and active tmux session)
    primary_bus = None
    spawner = None
    try:
        from aiciv_mind.ipc import PrimaryBus
        from aiciv_mind.spawner import SubMindSpawner
        from aiciv_mind.registry import MindRegistry
        primary_bus = PrimaryBus()
        primary_bus.bind()
        primary_bus.start_recv()
        mind_registry = MindRegistry()
        spawner = SubMindSpawner(
            session_name="aiciv-mind",
            mind_root=Path(__file__).parent,
            registry=mind_registry,
            memory_store=memory,
        )
        logging.getLogger("aiciv_mind.main").info("Sub-mind IPC ready")
    except Exception as e:
        logging.getLogger("aiciv_mind.main").info("Sub-mind IPC not available: %s", e)

    # Auto-register sub-minds in persistent registry
    for sub_ref in manifest.sub_minds:
        memory.register_agent(
            agent_id=sub_ref.mind_id,
            manifest_path=sub_ref.manifest_path,
            role="sub-mind",
        )

    # Auto-register skills from skills/ directory
    skills_dir = Path(__file__).parent / "skills"
    skills_dir_str: str | None = None
    if skills_dir.exists():
        skills_dir_str = str(skills_dir)
        for skill_subdir in skills_dir.iterdir():
            if not skill_subdir.is_dir():
                continue
            skill_file = skill_subdir / "SKILL.md"
            if skill_file.exists():
                skill_id = skill_subdir.name
                # Try to parse domain from frontmatter
                domain = "general"
                try:
                    text = skill_file.read_text(encoding="utf-8")
                    for line in text.splitlines():
                        if line.strip().startswith("domain:"):
                            domain = line.split(":", 1)[1].strip()
                            break
                except Exception:
                    pass
                memory.register_skill(skill_id, skill_id, domain, str(skill_file))

    # Hub queue path
    queue_path = str(Path(__file__).parent / "data" / "hub_queue.jsonl")

    # Build message counter (lazily captures mind reference once created)
    _mind_ref: list[Mind | None] = [None]

    def get_msg_count() -> int:
        return len(_mind_ref[0]._messages) if _mind_ref[0] else 0

    # Build tool registry
    # Scratchpad directory (daily working notes)
    scratchpad_dir = str(Path(__file__).parent / "scratchpads")

    # Extract auth-dependent tool config
    auth_cfg = getattr(manifest, 'auth', None)
    _keypair_path = getattr(auth_cfg, 'keypair_path', None) if auth_cfg else None
    _calendar_id = getattr(auth_cfg, 'calendar_id', None) if auth_cfg else None
    _agentmail_inbox = manifest.agentmail.inbox if manifest.agentmail.inbox else None

    tools = ToolRegistry.default(
        memory_store=memory,
        agent_id=manifest.mind_id,
        suite_client=suite_client,
        context_store=memory,
        get_message_count=get_msg_count,
        get_session_store=lambda: session_store,
        spawner=spawner,
        primary_bus=primary_bus,
        queue_path=queue_path,
        skills_dir=skills_dir_str,
        scratchpad_dir=scratchpad_dir,
        manifest_path=manifest_path,
        keypair_path=_keypair_path,
        calendar_id=_calendar_id,
        agentmail_inbox=_agentmail_inbox,
    )

    # Session lifecycle + context management
    session_store = SessionStore(memory, agent_id=manifest.mind_id)
    boot = session_store.boot()

    # Wire session_id into spawner for persistent tracking
    if spawner is not None:
        spawner._session_id = boot.session_id

    ctx_mgr = ContextManager(
        max_context_memories=manifest.memory.max_context_memories,
        model_max_tokens=manifest.model.max_tokens,
        scratchpad_dir=scratchpad_dir,
    )
    boot_str = ctx_mgr.format_boot_context(boot, context_mode=manifest.context.mode)
    if boot_str:
        logging.getLogger("aiciv_mind.main").info(
            "Loaded boot context: session %s (prior sessions: %d)",
            boot.session_id,
            boot.session_count,
        )

    # Model router (P2-5: dynamic model selection per task)
    model_router = None
    try:
        from aiciv_mind.model_router import ModelRouter
        stats_path = str(Path(__file__).parent / "data" / "model_router_stats.json")
        model_router = ModelRouter(
            default_model=manifest.model.preferred,
            stats_path=stats_path,
        )
        logging.getLogger("aiciv_mind.main").info("ModelRouter initialized (default: %s)", manifest.model.preferred)
    except Exception as e:
        logging.getLogger("aiciv_mind.main").info("ModelRouter not available: %s", e)

    # Memory selector (P2-8: AI-powered memory relevance reranking)
    memory_selector = None
    try:
        from aiciv_mind.memory_selector import MemorySelector
        memory_selector = MemorySelector()
        logging.getLogger("aiciv_mind.main").info("MemorySelector initialized (model: %s)", memory_selector._model)
    except Exception as e:
        logging.getLogger("aiciv_mind.main").info("MemorySelector not available: %s", e)

    # Create mind
    mind = Mind(
        manifest=manifest,
        memory=memory,
        tools=tools,
        bus=primary_bus,
        session_store=session_store,
        context_manager=ctx_mgr,
        boot_context_str=boot_str,
        model_router=model_router,
    )
    mind._memory_selector = memory_selector
    _mind_ref[0] = mind  # now the message counter lambda works

    try:
        if converse:
            # Multi-turn conversation — messages accumulate across turns
            for i, turn in enumerate(converse):
                logging.getLogger("aiciv_mind.main").info("Turn %d/%d: %s", i + 1, len(converse), turn[:80])
                result = await mind.run_task(turn)
                print(f"\n--- Turn {i + 1} ---\n{result}\n")
        elif task:
            # Non-interactive single task
            result = await mind.run_task(task)
            print(result)
        else:
            # Interactive REPL
            repl = InteractiveREPL(mind)
            await repl.run()
    finally:
        # Recalculate depth scores for accessed memories
        updated = memory.recalculate_touched_depth_scores()
        if updated > 0:
            logging.getLogger("aiciv_mind.main").info(
                "Recalculated depth scores for %d accessed memories", updated
            )
        # Write session handoff with cache stats
        session_store.shutdown(mind._messages, cache_stats=mind.cache_stats)
        memory.close()
        if suite_client:
            await suite_client.close()
        if primary_bus:
            primary_bus.close()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="aiciv-mind primary mind")
    parser.add_argument(
        "--manifest",
        default="manifests/primary.yaml",
        help="Path to mind manifest YAML (default: manifests/primary.yaml)",
    )
    parser.add_argument("--task", help="Run a single task non-interactively")
    parser.add_argument("--converse", nargs="+", help="Run multiple tasks as a multi-turn conversation (messages accumulate)")
    parser.add_argument("--log-level", default="INFO", help="Log level (default: INFO)")
    args = parser.parse_args()

    setup_logging(args.log_level)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = Path(__file__).parent / manifest_path

    if not manifest_path.exists():
        print(f"ERROR: Manifest not found: {manifest_path}")
        sys.exit(1)

    task = args.task
    converse = args.converse
    if converse:
        # Multi-turn: join all args as separate turns, or read from stdin
        task = None  # handled inside run_primary
    asyncio.run(run_primary(str(manifest_path), task=task, converse=converse))


if __name__ == "__main__":
    main()
