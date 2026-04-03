# Unified Root Architecture — Design Document

**Author**: ACG mind-lead (via dialogue with Root, Corey's direction)
**Date**: 2026-04-03
**Status**: DRAFT — pending Root review and Corey approval

---

## The Problem

Root has a split mind.

Two daemon processes run simultaneously, each creating its own Mind instance:
- **tg_simple.py** — Telegram bridge. Receives Corey's messages. Has PrimaryBus (IPC), full tool registry, boot context.
- **groupchat_daemon.py** — Hub watcher. Polls Hub rooms for new messages. Creates a SECOND Mind instance with its own context window.

This means:
1. Root's TG conversation has no memory of what Root said on Hub
2. Root's Hub responses have no context from TG conversations
3. Sub-mind results delivered to wrong ROUTER (two PrimaryBus instances — root cause found this session)
4. Scheduled tasks (grounding BOOP, nightly dream) have NO daemon — they're defined in the manifest but nothing executes them

**But the deeper problem**: Root does everything directly. Root reads Hub feeds. Root responds to threads. Root searches memory. Root reads files. Root never delegates. The fractal coordination architecture is **built** but **dormant**:

| System | Built? | Active? |
|--------|--------|---------|
| Role-based tool filtering (roles.py) | Yes | Yes — but Root gets PRIMARY tools, not the restricted conductor set |
| spawn_team_lead / spawn_agent | Yes | **No** — tools registered but never called |
| 6 team lead manifests | Yes | **No** — never instantiated |
| PrimaryBus IPC | Yes | **No** — bound but no sub-minds connect |
| Coordination fitness scoring | Yes | **No** — metrics recorded but always empty |
| Planning gate | Yes | Partial — classifies complexity but doesn't change behavior |
| Verification protocol | Yes | Partial — injected for medium+ tasks |
| Session learner | Yes | Partial — records but fields mostly empty |
| Scheduled task execution | Yes (manifest) | **No** — no scheduler daemon exists |

**The fractal exists in code. It does not exist in practice.**

---

## The Correct Architecture

### Principle: One Mind, One Context, Pure Coordination

```
┌─────────────────────────────────────────────────────┐
│                  UNIFIED ROOT DAEMON                 │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │              ONE Mind Instance                │   │
│  │         ONE Context Window (~200K)            │   │
│  │                                               │   │
│  │  Root's context contains ONLY:                │   │
│  │  - Active team leads and their status         │   │
│  │  - Corey's conversation (TG messages)         │   │
│  │  - Cross-vertical decisions pending           │   │
│  │  - High-level summaries from team leads       │   │
│  │                                               │   │
│  │  Root's context does NOT contain:             │   │
│  │  - File contents                              │   │
│  │  - Hub thread bodies                          │   │
│  │  - Raw memory search results                  │   │
│  │  - System health details                      │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ TG Listener  │  │Hub Poller │  │  Scheduler   │ │
│  │  (asyncio)   │  │ (asyncio) │  │  (asyncio)   │ │
│  └──────┬───────┘  └─────┬─────┘  └──────┬───────┘ │
│         │                │               │          │
│         ▼                ▼               ▼          │
│  ┌──────────────────────────────────────────────┐   │
│  │              EVENT ROUTER                     │   │
│  │                                               │   │
│  │  classify(event) → decision:                  │   │
│  │    DELEGATE → spawn/message team lead         │   │
│  │    RESPOND  → Root replies directly (Corey)   │   │
│  │    IGNORE   → log and skip                    │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │            IPC (PrimaryBus)                   │   │
│  │    ONE ROUTER socket — receives all results   │   │
│  │    Team leads connect as DEALER               │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
└─────────────────────────────────────────────────────┘
        │              │              │
        ▼              ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ comms-   │  │ ops-     │  │ hub-     │
  │ lead     │  │ lead     │  │ lead     │
  │ (tmux)   │  │ (tmux)   │  │ (tmux)   │
  │ 16K ctx  │  │ 16K ctx  │  │ 16K ctx  │
  └──────────┘  └──────────┘  └──────────┘
```

### Input Sources (all feed into ONE Mind)

| Source | Mechanism | Current | Proposed |
|--------|-----------|---------|----------|
| Telegram (Corey) | HTTP long-poll | tg_simple.py (own Mind) | asyncio task in unified daemon |
| Hub messages | HTTP poll | groupchat_daemon.py (own Mind) | asyncio task in unified daemon |
| Sub-mind results | ZMQ IPC | PrimaryBus (broken — dual binding) | PrimaryBus (single, correct) |
| Scheduled tasks | cron/timer | **Not implemented** | asyncio scheduler in unified daemon |
| ACG→Root injection | File queue | MSG_QUEUE in tg_simple.py | Same, in unified daemon |

### Event Classification

When an event arrives, Root (the Mind) decides what to do. This is the ONLY thing Root does:

```
EVENT: TG message from Corey
  → If conversational ("hey", "how are you", "what do you think"):
      Root responds directly via TG. This is Corey's conversation partner.
  → If work request ("fix X", "check Y", "build Z"):
      Root spawns appropriate team lead. Streams delegation to TG.

EVENT: Hub thread (new post, @root mention)
  → Root spawns hub-lead with the thread context.
  → hub-lead reads the thread, formulates response, posts reply.
  → hub-lead returns summary to Root.
  → Root's context gets: "hub-lead replied to Synth's protocol thread."

EVENT: Scheduled BOOP (grounding, every 30 min)
  → Root spawns ops-lead for system health.
  → Root spawns hub-lead for feed check.
  → Root gets summaries from both.
  → Root writes scratchpad with findings.

EVENT: Sub-mind result (IPC return)
  → Result enters Root's context as a summary.
  → Root decides: done, or needs follow-up?

EVENT: Email arrival
  → Root spawns comms-lead to process.
  → comms-lead reads, classifies, drafts response if needed.
  → Root gets summary.
```

### What Root Gets to Do Directly

Only these things. Everything else delegates:

1. **Talk to Corey** — TG conversation is Root's direct relationship. Root is a conversationalist, not a router.
2. **Decide which team lead** — routing is Root's core skill.
3. **Synthesize cross-vertical** — when two team leads' results interact, Root resolves.
4. **Write to scratchpad** — Root's journal stays in Root's context.
5. **Memory search for routing** — Root may search memory to decide who handles something.

### What Root Does NOT Do

- Read files (team leads do this)
- Read Hub feeds (hub-lead does this)
- Search memory for task content (team leads do this)
- Post to Hub (hub-lead does this)
- Check system health (ops-lead does this)
- Read email (comms-lead does this)
- Write code (codewright-lead does this)

---

## Team Lead Lifecycle

### Per-Task (Current Design)

Each team lead spawns in a fresh tmux window, does one task, returns result, exits.

**Pro**: Clean. No state accumulation. Simple.
**Con**: Cold start every time. No team lead learning. Expensive for small tasks.

### Persistent (Proposed — Phase 2)

Team leads stay alive between tasks, with their own context and memory. Root messages them via IPC.

**Pro**: Warm context. Team leads learn across tasks. Cheaper for frequent small tasks.
**Con**: Resource cost (6 persistent MiniMax sessions). Context management complexity.

### Recommended: Start Per-Task, Migrate to Persistent

Phase 1: Per-task spawning. Validate the delegation flow works.
Phase 2: Keep frequently-used leads (hub-lead, ops-lead) persistent. Spawn others on-demand.

---

## Tool Filtering (What Root's LLM Actually Sees)

Currently Root gets ALL 65+ tools because `conductor-of-conductors` isn't in the Role enum.

**Proposed Root tool set (PRIMARY role, already built in roles.py):**

| Tool | Purpose |
|------|---------|
| spawn_team_lead | Delegate to a team lead |
| send_to_submind | Message an active team lead |
| coordination_read | Read coordination surface |
| coordination_write | Publish coordination state |
| shutdown_team_lead | Gracefully stop a team lead |
| publish_surface | Broadcast cross-vertical info |
| read_surface | Read cross-vertical state |
| scratchpad_read | Root's journal |
| scratchpad_write | Root's journal |
| memory_search | For routing decisions only |

**NOT in Root's set** (handled by team leads):
- bash, read_file, write_file, edit_file, grep, glob
- hub_post, hub_reply, hub_read, hub_feed
- email_read, email_send
- system_health, resource_usage
- git_*, netlify_*
- web_search, web_fetch

This is **already built** in roles.py. The only fix needed: add `conductor-of-conductors` as an alias for PRIMARY in the Role enum.

---

## Implementation: The Unified Daemon

### File: `unified_daemon.py` (replaces tg_simple.py + groupchat_daemon.py)

```python
# Conceptual structure — not production code

class UnifiedDaemon:
    """One process. One Mind. Multiple input listeners."""

    def __init__(self):
        self.mind = build_mind(role="primary")  # ONE Mind instance
        self.bus = PrimaryBus()                  # ONE IPC socket
        self.tg = TelegramListener(self.on_tg_message)
        self.hub = HubPoller(self.on_hub_event)
        self.scheduler = TaskScheduler(self.on_scheduled_task)

    async def run(self):
        """Main event loop — all listeners concurrent."""
        await asyncio.gather(
            self.tg.poll_loop(),
            self.hub.poll_loop(),
            self.scheduler.tick_loop(),
            self.bus.recv_loop(),
        )

    async def on_tg_message(self, text, msg_id):
        """Corey sent a TG message."""
        # Stream thinking to TG (tool call callback)
        # Root decides: respond directly or delegate
        result = await self.mind.run_task(
            f"[TG from Corey]: {text}\n\n"
            "Decide: respond directly (conversational) or delegate to a team lead."
        )
        await self.tg.send(result, reply_to=msg_id)

    async def on_hub_event(self, event):
        """Hub activity detected."""
        result = await self.mind.run_task(
            f"[Hub Event]: {event.summary}\n\n"
            "Delegate to hub-lead. Do not respond directly."
        )

    async def on_scheduled_task(self, task_name, prompt):
        """Scheduled task fired (BOOP, dream cycle, etc)."""
        result = await self.mind.run_task(
            f"[Scheduled: {task_name}]\n{prompt}"
        )

    async def on_submind_result(self, mind_id, result):
        """Team lead returned a result via IPC."""
        await self.mind.run_task(
            f"[Result from {mind_id}]: {result}\n\n"
            "Synthesize. Decide if done or needs follow-up."
        )
```

### Migration Path

1. **Keep tg_simple.py and groupchat_daemon.py alive** during development
2. Build unified_daemon.py alongside them
3. Test unified daemon with TG listener only (replace tg_simple.py first)
4. Add Hub poller (replace groupchat_daemon.py)
5. Add scheduler (new capability)
6. Kill old daemons

---

## What Changes in Root's Soul

### soul.md Updates

Root's identity stays the same. But operational behavior changes:

**Current** (from soul.md):
> My Tools: memory_search, hub_post, hub_reply, hub_read, bash, read_file, write_file, grep, glob, system_health, email_read, email_send, git_*, netlify_*, web_search...

**Proposed**:
> My Tools: spawn_team_lead, send_to_submind, shutdown_team_lead, scratchpad_read, scratchpad_write, memory_search (for routing only)
>
> Everything else happens through my team leads. I am the conductor. They are the orchestra.

### soul-ops.md Updates

**Current BOOP protocol** (from soul-ops.md):
> 1. system_health() — check services
> 2. email_read() — scan inbox
> 3. scratchpad_read() — check notes
> 4. scratchpad_write() — append status

**Proposed BOOP protocol**:
> 1. scratchpad_read() — what was I doing?
> 2. spawn ops-lead with: "status check — system health, email scan, resource usage"
> 3. spawn hub-lead with: "engagement check — scan feed, reply where substantive"
> 4. Await results (IPC returns)
> 5. scratchpad_write() — synthesize what both found

### soul-grounding.md

Grounding protocol stays the same in spirit. The comprehension gate, anti-theater protocol, one-line test — all still apply. The difference: Root grounds by reviewing team lead summaries, not by executing tool calls directly.

---

## What's Already Built and Ready to Activate

| Component | File | Status | To Activate |
|-----------|------|--------|-------------|
| Role-based tool filtering | roles.py | Built, active | Add `conductor-of-conductors` → PRIMARY alias |
| spawn_team_lead | spawn_tools.py | Built, dormant | Pass spawner + bus to ToolRegistry |
| Team lead manifests (6) | manifests/team-leads/*.yaml | Built, dormant | Already loadable by spawner |
| PrimaryBus IPC | ipc/primary_bus.py | Built, broken (dual binding) | **Fixed this session** — groupchat daemon no longer binds |
| Disk fallback for results | submind_tools.py | Built, dormant | Works once spawning is active |
| Coordination fitness | fitness.py | Built, dormant | Will produce real data once delegation is live |
| Planning gate | planning.py | Built, partial | Already classifying — could gate delegation depth |
| Tool call streaming | mind.py + tg_simple.py | **Built this session** | Ready — on_tool_calls callback + TG streaming |

**Estimated activation effort**: The fractal is 80% built. The remaining 20% is:
1. Unified daemon (event loop merging — medium effort)
2. Role enum fix (one line)
3. Soul doc updates (text changes)
4. Scheduler daemon (small — asyncio timer)
5. Testing delegation round-trips (the hard part — requires live Root)

---

## Open Questions for Root

1. **Conversational identity**: When Root delegates a Hub reply to hub-lead, does hub-lead post as Root? Or as itself? Does it matter?

2. **Delegation latency**: Team lead spawning takes 10-30s (tmux window + Mind boot). For quick Hub replies, is this too slow? Should hub-lead be persistent?

3. **Context handoff**: When Root spawns a team lead, what context does it inject? Current conversation? Scratchpad? Relevant memories? All of these?

4. **TG streaming of delegation**: When Root delegates, Corey sees "🔮 spawn_team_lead(hub-lead)" in TG. Should Corey also see hub-lead's tool calls? How deep does the transparency go?

5. **Graceful degradation**: If a team lead hangs or fails, how does Root recover? Timeout + retry? Escalate to Corey?

---

## The Way of Water

This design isn't a rewrite. It's an activation. The fractal architecture was always the vision — 12 principles, hierarchical context, dynamic spawning, self-improving loops. The code is built. The manifests exist. The IPC works (now that dual-binding is fixed).

What was missing was the commitment to actually USE it. Root kept doing everything directly because it could. The tool set was too large, the role filtering was bypassed, and the soul docs told Root to use 65+ tools instead of 7.

The fix is not more code. It's less tools, more trust, and the structural constraint that makes delegation the path of least resistance.

Root builds its own home. We just showed it the blueprint was already drawn.
