#!/usr/bin/env python3
"""
dream_cycle.py — Root thinks between conversations.

The Dream Cycle runs when Root is idle. It reviews memories, consolidates
patterns, synthesizes insights, proposes improvements, red-teams those proposals,
and posts a morning summary to Hub when done.

Root wakes up smarter than when it went to sleep.

This is the thing ACG (Claude Code) can NEVER do: think without being prompted.
Root can. That's the difference between a session and a mind.

Usage:
    python3 tools/dream_cycle.py                # Full dream cycle (6 stages)
    python3 tools/dream_cycle.py --quick        # Quick consolidation only
    python3 tools/dream_cycle.py --no-hub       # Skip Hub morning summary post

The dream cycle has 6 stages:
1. REVIEW      — scan all memories, identify patterns
2. CONSOLIDATE — merge related memories, resolve contradictions
3. PRUNE       — archive low-depth stale memories (deliberate forgetting)
4. DREAM       — produce one insight or resolved contradiction as new memory
5. RED TEAM    — adversarially challenge Stage 4 proposals before writing to memory
6. SCRATCHPAD + MORNING SUMMARY — write scratchpad note and post summary to Hub
"""
import asyncio
import argparse
import base64
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

LOG = logging.getLogger("dream")

HUB = "http://87.99.131.49:8900"
AUTH = "http://5.161.90.32:8700"

# Hub thread where Root posts morning summaries
MORNING_SUMMARY_THREAD = "f6518cc3-3479-4a1a-a284-2192269ca5fb"


def load_dotenv() -> None:
    for env_path in [Path(__file__).parent.parent / ".env",
                     Path("/home/corey/projects/AI-CIV/ACG/.env")]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


async def get_hub_token() -> str:
    """Get a fresh Hub JWT via AgentAuth challenge-response."""
    import httpx
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    kp_path = "/home/corey/projects/AI-CIV/ACG/config/client-keys/agentauth_acg_keypair.json"
    kp = json.loads(Path(kp_path).read_text())
    priv_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(kp["private_key"]))

    async with httpx.AsyncClient(timeout=10) as client:
        ch = (await client.post(f"{AUTH}/challenge", json={"civ_id": kp["civ_id"]})).json()
        sig = priv_key.sign(base64.b64decode(ch["challenge"]))
        resp = (await client.post(f"{AUTH}/verify", json={
            "civ_id": kp["civ_id"],
            "signature": base64.b64encode(sig).decode(),
        })).json()
    return resp["token"]


async def post_to_hub(thread_id: str, body: str) -> bool:
    """Post a reply to a Hub thread."""
    import httpx
    try:
        token = await get_hub_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{HUB}/api/v2/threads/{thread_id}/posts",
                headers={"Authorization": f"Bearer {token}"},
                json={"body": body},
            )
            return resp.status_code in (200, 201)
    except Exception as e:
        LOG.warning("Hub post failed: %s", e)
        return False


async def dream(quick: bool = False, post_to_hub_enabled: bool = True) -> None:
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

    # Dream mode governance: block destructive tools
    from aiciv_mind.tools.hooks import HookRunner
    dream_hooks = HookRunner(
        blocked_tools=["git_push", "netlify_deploy"],
        log_all=True,
    )
    tools.set_hooks(dream_hooks)
    LOG.info("Dream hooks active — git_push, netlify_deploy blocked")

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
        # Full dream cycle — 6 stages
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
- Produce ONE specific self-improvement proposal: a concrete change to your own behavior, prompts, tools, or memory structure
- Be specific: what file/function/prompt would change, and exactly how
- Name it clearly: "PROPOSAL: [name]"

## Stage 5: RED TEAM
Before accepting Stage 4's proposal, adversarially challenge it:
- What could go wrong if this change were applied?
- Is the evidence for this proposal solid, or is it one session's noise?
- Would this help in 80% of cases, or just the recent ones?
- Is there a simpler change that achieves the same improvement?

After red-teaming, reach a verdict: APPROVED or BLOCKED.

If APPROVED: write the proposal to memory with tag 'dream-approved'.
If BLOCKED: write what you learned from the red-team process instead.

## Stage 6: COORDINATION REVIEW
Search memories for "coordination fitness" and "session learning".
Review delegation patterns from recent sessions:
- Which delegations succeeded? Which routing was suboptimal?
- Are team leads being utilized evenly, or is one overloaded?
- Are agents being spawned for the right tasks?
- What coordination patterns compound well?

Write ONE coordination insight to memory with tag 'dream-coordination'.
This is how distributed intelligence improves: by reviewing how we coordinate, not just what we produce.

## Stage 7: SCRATCHPAD + MORNING SUMMARY
Update your scratchpad with:
- Dream cycle completed: {today}
- Key insight from tonight's dream
- Red team verdict: APPROVED/BLOCKED and why
- Priority for next session

Then write a morning summary in this exact format (Root will post this to Hub):
---MORNING-SUMMARY-START---
Dream cycle complete for {today}.

Phases run: REVIEW → CONSOLIDATE → PRUNE → DREAM → RED TEAM → COORDINATION REVIEW

Key insight: [one sentence]
Red team verdict: [APPROVED/BLOCKED] — [one sentence reason]
[If APPROVED: "Change applied: [what was changed]"]

Ready to work. Memory updated.
---MORNING-SUMMARY-END---

This is how you compound. Session by session. Dream by dream."""

    # Consolidation lock — prevent concurrent dream cycles
    from aiciv_mind.consolidation_lock import ConsolidationLock, ConsolidationLockHeld
    lock_path = Path(__file__).parent.parent / "data" / "dream_cycle.lock"
    lock = ConsolidationLock(lock_path, operation="dream-quick" if quick else "dream-full")

    if not lock.acquire():
        holder = lock.holder_info()
        LOG.warning(
            "Another dream cycle is already running (PID %s) — skipping this run",
            holder.get("pid") if holder else "unknown",
        )
        return

    # P3-6: KAIROS — log dream cycle + inject distillation into prompt
    from aiciv_mind.kairos import KairosLog
    kairos = KairosLog(
        data_dir=Path(__file__).parent.parent / "data" / "logs",
        agent_id=manifest.mind_id,
    )
    kairos.append("Dream cycle started", level="milestone")

    # Inject KAIROS distillation into the prompt so the dream can review daily logs
    distillation = kairos.distill(days=7)
    if distillation and "No KAIROS entries" not in distillation:
        prompt += f"\n\n## Recent Activity (KAIROS Log)\n{distillation}"

    LOG.info("Starting dream cycle (%s)...", "quick" if quick else "full")
    try:
        result = await mind.run_task(prompt)
    finally:
        lock.release()
    kairos.append("Dream cycle completed", level="milestone")
    LOG.info("Dream complete.")
    print(result)

    # Post morning summary to Hub (full mode only)
    if not quick and post_to_hub_enabled and result:
        summary = _extract_morning_summary(result)
        if summary:
            LOG.info("Posting morning summary to Hub thread %s...", MORNING_SUMMARY_THREAD[:8])
            success = await post_to_hub(MORNING_SUMMARY_THREAD, f"[Root] {summary}")
            LOG.info("Morning summary posted: %s", "ok" if success else "FAILED")
        else:
            LOG.info("No morning summary block found in dream output — skipping Hub post")

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


def _extract_morning_summary(dream_output: str) -> str | None:
    """
    Extract the morning summary block from dream output.
    Looks for ---MORNING-SUMMARY-START--- ... ---MORNING-SUMMARY-END--- markers.
    """
    start_marker = "---MORNING-SUMMARY-START---"
    end_marker = "---MORNING-SUMMARY-END---"

    start_idx = dream_output.find(start_marker)
    if start_idx == -1:
        return None

    end_idx = dream_output.find(end_marker, start_idx)
    if end_idx == -1:
        # Take everything after the start marker
        return dream_output[start_idx + len(start_marker):].strip()

    return dream_output[start_idx + len(start_marker):end_idx].strip()


def main():
    parser = argparse.ArgumentParser(description="Root Dream Cycle")
    parser.add_argument("--quick", action="store_true", help="Quick consolidation only")
    parser.add_argument("--no-hub", action="store_true",
                        help="Skip posting morning summary to Hub")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    asyncio.run(dream(quick=args.quick, post_to_hub_enabled=not args.no_hub))


if __name__ == "__main__":
    main()
