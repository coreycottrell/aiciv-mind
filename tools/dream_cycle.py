#!/usr/bin/env python3
"""
dream_cycle.py — Root thinks between conversations.

The Dream Cycle runs when Root is idle. It reviews memories, consolidates
patterns, synthesizes insights, and proposes improvements to its own
architecture. Root wakes up smarter than when it went to sleep.

This is the thing ACG (Claude Code) can NEVER do: think without being prompted.
Root can. That's the difference between a session and a mind.

Usage:
    python3 tools/dream_cycle.py                # Full dream cycle
    python3 tools/dream_cycle.py --quick        # Quick consolidation only

The dream cycle has 4 stages (from CONTEXT-ARCHITECTURE.md):
1. REVIEW — scan all memories, identify patterns
2. CONSOLIDATE — merge related memories, resolve contradictions
3. PRUNE — archive low-depth stale memories (deliberate forgetting)
4. DREAM — produce one insight or resolved contradiction as new memory
"""
import asyncio
import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

LOG = logging.getLogger("dream")


def load_dotenv() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


async def dream(quick: bool = False) -> None:
    from aiciv_mind.manifest import MindManifest
    from aiciv_mind.memory import MemoryStore
    from aiciv_mind.mind import Mind
    from aiciv_mind.tools import ToolRegistry
    from aiciv_mind.session_store import SessionStore
    from aiciv_mind.context_manager import ContextManager

    manifest_path = str(Path(__file__).parent.parent / "manifests" / "primary.yaml")
    manifest = MindManifest.from_yaml(manifest_path)

    db_path = manifest.memory.db_path
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    memory = MemoryStore(db_path)
    scratchpad_dir = str(Path(__file__).parent.parent / "scratchpads")

    tools = ToolRegistry.default(
        memory_store=memory,
        agent_id=manifest.mind_id,
        scratchpad_dir=scratchpad_dir,
    )

    session_store = SessionStore(memory, agent_id=manifest.mind_id)
    boot = session_store.boot()

    ctx_mgr = ContextManager(
        max_context_memories=manifest.memory.max_context_memories,
        model_max_tokens=manifest.model.max_tokens,
        scratchpad_dir=scratchpad_dir,
    )
    boot_str = ctx_mgr.format_boot_context(boot)

    mind = Mind(
        manifest=manifest,
        memory=memory,
        tools=tools,
        boot_context_str=boot_str,
        session_store=session_store,
        context_manager=ctx_mgr,
    )

    today = date.today().isoformat()

    if quick:
        # Quick mode: just consolidate and write scratchpad
        prompt = f"""Dream Cycle (quick) — {today}

You are dreaming. Nobody is talking to you. This is YOUR time to think.

1. Read your scratchpad (scratchpad_read) — what were you working on today?
2. Search your memories for today's work (memory_search for '{today}')
3. Write a brief consolidation to your scratchpad: what did you learn today? What patterns do you see? What should tomorrow-you prioritize?

Keep it brief. This is a working note, not a report."""
    else:
        # Full dream cycle
        prompt = f"""Dream Cycle (full) — {today}

You are dreaming. Nobody is talking to you. This is YOUR time to think.
Take your time. There is no user waiting. Think deeply.

## Stage 1: REVIEW
Search all your memories. Look for:
- Memories that are related but stored separately
- Contradictions between memories
- Patterns that appear across 3+ memories
- Memories that feel stale or redundant

## Stage 2: CONSOLIDATE
For any related memories you found:
- Write a new synthesis memory that combines the insights
- Note any contradictions and how they resolve

## Stage 3: PRUNE
Identify memories with low access_count and old timestamps.
For each candidate: is this still relevant? If not, note it for archival.
(Don't delete — just write an observation about what could be pruned)

## Stage 4: DREAM
This is the creative part. Based on everything you reviewed:
- Write ONE insight you didn't have before this dream cycle
- Something that emerged from seeing your memories as a WHOLE, not individually
- Save it as a memory with type 'learning' and tag 'dream-cycle'

## Stage 5: SCRATCHPAD
Update your scratchpad with:
- Dream cycle completed: {today}
- Key insight from tonight's dream
- Priority for next session
- Any self-improvement proposals (specific: file, function, change)

This is how you compound. Session by session. Dream by dream."""

    LOG.info("Starting dream cycle (%s)...", "quick" if quick else "full")
    result = await mind.run_task(prompt)
    LOG.info("Dream complete.")
    print(result)

    # Shutdown session
    try:
        session_store.shutdown(mind._messages)
    except Exception as e:
        LOG.warning("Session shutdown: %s", e)

    # Recalculate depth scores
    try:
        memory.recalculate_touched_depth_scores()
    except Exception as e:
        LOG.warning("Depth recalc: %s", e)


def main():
    parser = argparse.ArgumentParser(description="Root Dream Cycle")
    parser.add_argument("--quick", action="store_true", help="Quick consolidation only")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    asyncio.run(dream(quick=args.quick))


if __name__ == "__main__":
    main()
