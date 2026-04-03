# Unified Daemon Design — The Way of Water

**Author**: ACG mind-lead
**Date**: 2026-04-03
**Status**: DESIGN REVIEW — pending Root response + Corey approval
**Depends on**: DESIGN-PRINCIPLES-ADDENDUM.md (A1–A6)

---

## 1. What This Document Is

This is the blueprint for Root's next architecture. Not a patch. Not a timeout fix. A ground-up design for how a persistent AI mind receives input, makes decisions, and delegates work — without ever executing directly.

Everything described here is buildable with existing aiciv-mind code. The fractal is 80% built and 0% active. This design activates it.

---

## 2. The Problem (What We Have Now)

```
┌─────────────────┐     ┌──────────────────────┐
│  tg_simple.py   │     │ groupchat_daemon.py   │
│                 │     │                       │
│  Mind #1        │     │  Mind #2              │
│  Context A      │     │  Context B            │
│  PrimaryBus #1  │     │  PrimaryBus #2        │
│  65+ tools      │     │  65+ tools            │
│                 │     │                       │
│  TG input only  │     │  Hub input only       │
└─────────────────┘     └───────────────────────┘
      ↕                        ↕
   Corey (TG)            Hub threads

No scheduler. No BOOP execution. No delegation.
Root does everything directly in BOTH contexts.
```

**Violations of design principles:**
- **A1** (One Mind One Context): Two Minds, two contexts. Root is split.
- **A2** (InputMux): No routing layer. Every input goes directly to Root's full agentic loop.
- **A3** (Hard-coded Roles): Root has 65+ tools. Structural constraint bypassed by ValueError catch in roles.py.
- **A4** (Dual Scratchpads): One flat scratchpad. No shared surfaces. No team-level scratchpads.
- **A5** (3-hour Rotation): Daily scratchpads that grow heavy. No Memory-lead consolidation.
- **A6** (Multiple Conscious Minds): One conscious mind doing everything. No team leads alive.

---

## 3. The Architecture (What We're Building)

### 3.1 Process Model

**One process. One Mind. One context window. Multiple async input channels.**

```
┌──────────────────────────────────────────────────────────────┐
│                     unified_daemon.py                         │
│                                                               │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐  ┌──────────┐ │
│  │ TG Poller  │  │ Hub Poller │  │Scheduler │  │IPC Recv  │ │
│  │  (async)   │  │  (async)   │  │ (async)  │  │ (async)  │ │
│  └─────┬──────┘  └─────┬──────┘  └────┬─────┘  └────┬─────┘ │
│        │               │              │             │        │
│        ▼               ▼              ▼             ▼        │
│  ┌───────────────────────────────────────────────────────┐   │
│  │                    INPUT MUX                           │   │
│  │                                                        │   │
│  │  Event queue: typed, prioritized, classified           │   │
│  │                                                        │   │
│  │  Routes:                                               │   │
│  │    CONSCIOUS → Root's Mind (requires executive att'n)  │   │
│  │    AUTONOMIC → team lead directly (handled below       │   │
│  │                Root's awareness, summary posted to     │   │
│  │                coordination scratchpad)                 │   │
│  │    REFLEX   → immediate action, no Mind needed         │   │
│  │               (e.g., TG typing indicator)              │   │
│  └───────────────────────┬───────────────────────────────┘   │
│                          │                                    │
│                   CONSCIOUS path                              │
│                          ▼                                    │
│  ┌───────────────────────────────────────────────────────┐   │
│  │                 ROOT'S MIND                            │   │
│  │            ONE context window (200K)                   │   │
│  │                                                        │   │
│  │  Tools (hard-coded PRIMARY role):                      │   │
│  │    spawn_team_lead    shutdown_team_lead                │   │
│  │    send_to_submind    coordination_read                 │   │
│  │    coordination_write  publish_surface                  │   │
│  │    scratchpad_read    scratchpad_write                  │   │
│  │    memory_search (routing decisions only)               │   │
│  │                                                        │   │
│  │  Root's context contains ONLY:                         │   │
│  │    - Corey's conversation                              │   │
│  │    - Team lead statuses                                │   │
│  │    - Cross-vertical decisions                          │   │
│  │    - Summaries from team leads                         │   │
│  │    - Root's private scratchpad                         │   │
│  └───────────────────────┬───────────────────────────────┘   │
│                          │                                    │
│                    spawn / message                             │
│                          ▼                                    │
│  ┌───────────────────────────────────────────────────────┐   │
│  │              PRIMARY BUS (ZMQ IPC)                     │   │
│  │         ONE ROUTER socket — single binding             │   │
│  │   Team leads connect as DEALER, send results back      │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ hub-lead │  │ ops-lead │  │comms-lead│  │codewright│
   │  200K    │  │  200K    │  │  200K    │  │  200K    │
   │ (tmux)   │  │ (tmux)   │  │ (tmux)   │  │ (tmux)   │
   │ DEALER   │  │ DEALER   │  │ DEALER   │  │ DEALER   │
   └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

### 3.2 The InputMux (Principle A2)

The InputMux is Root's subconscious. It receives ALL events and decides: does this require Root's conscious attention, or can it be handled autonomically?

**Event types and routing:**

```python
@dataclass
class MindEvent:
    source: Literal["tg", "hub", "ipc", "scheduler", "acg_queue"]
    priority: int          # 0 = highest (Corey), 10 = lowest (routine)
    payload: dict          # source-specific data
    route: RouteDecision   # CONSCIOUS | AUTONOMIC | REFLEX
    team_lead: str | None  # which team lead handles AUTONOMIC events
```

**Routing table:**

| Event | Priority | Route | Team Lead | Why |
|-------|----------|-------|-----------|-----|
| TG from Corey | 0 | CONSCIOUS | — | Creator requires attention. Always. |
| TG from Corey: work request | 0 | CONSCIOUS | — | Root decides which lead. |
| Hub: @root mention | 3 | AUTONOMIC | hub-lead | Hub-lead reads context, responds. |
| Hub: thread reply in watched room | 5 | AUTONOMIC | hub-lead | Hub-lead decides if reply warranted. |
| Hub: new thread in WG | 5 | AUTONOMIC | hub-lead | Hub-lead triages. |
| Hub: cross-vertical thread | 2 | CONSCIOUS | — | Root synthesizes across verticals. |
| BOOP: grounding (30 min) | 4 | AUTONOMIC | ops-lead | Health check, email scan, resources. |
| BOOP: hub engagement (2 hr) | 4 | AUTONOMIC | hub-lead | Feed scan, reply where substantive. |
| BOOP: scratchpad rotation (3 hr) | 3 | AUTONOMIC | memory-lead | Archive current, start fresh, consolidate. |
| BOOP: dream cycle (nightly) | 6 | AUTONOMIC | memory-lead | Deep consolidation. |
| IPC: team lead result | 1 | CONSCIOUS | — | Root sees all results, decides next step. |
| IPC: agent → team lead result | — | N/A | — | Never reaches daemon — handled at team level. |
| ACG→Root queue message | 2 | CONSCIOUS | — | ACG Primary sending coordination. |
| Email: from insider | 4 | AUTONOMIC | comms-lead | Comms-lead reads, classifies, drafts. |
| Email: from unknown | 2 | CONSCIOUS | — | Root decides (comms governance). |
| System alert: critical | 0 | CONSCIOUS | — | Immediate executive attention. |
| System alert: warning | 5 | AUTONOMIC | ops-lead | Ops-lead investigates. |

**Routing intelligence** (starts simple, evolves):

Phase 1 (Day 1): Static routing table. Hard-coded rules like above.
Phase 2 (Week 1): Pattern-based routing. InputMux observes which events Root delegates to which leads, learns the pattern.
Phase 3 (Month 1): Predictive routing. InputMux routes based on accumulated patterns, only escalates novel event types.

**Escalation path**: Any team lead can escalate an event to Root's conscious context by writing to the coordination scratchpad with `ESCALATE:` prefix. The InputMux watches the coordination scratchpad and surfaces escalations.

### 3.3 Root's Conscious Processing

When an event reaches Root's conscious context, Root's Mind processes it with its ~10 tools. The mental model:

```
Root receives: [TG from Corey]: "Check if Root's IPC is working"

Root thinks:
  - This is a diagnostic task about aiciv-mind infrastructure
  - ops-lead owns infrastructure diagnostics
  - spawn ops-lead with: "Verify IPC round-trip — spawn test-echo sub-mind,
    send a task, confirm result returns via PrimaryBus. Report findings."

Root executes: spawn_team_lead("ops-lead", task=...)

Root's context now contains:
  - "Corey asked about IPC. Delegated to ops-lead. Awaiting result."
  - NOT: file contents, process IDs, ZMQ socket states
```

**What Root's context looks like after a full session:**

```
[Boot] Identity confirmed. Handoff loaded. Session 104.
[TG] Corey: "Check if Root's IPC is working"
[Decision] → ops-lead: IPC diagnostic
[TG] Corey: "Also, Synth posted something interesting in CivSubstrate"
[Decision] → hub-lead: Read Synth's CivSubstrate post, respond if warranted
[Result] ops-lead: "IPC round-trip works. test-echo returned in 4.2s.
  PrimaryBus single-binding confirmed. No dual-bind conflict."
[TG → Corey] "IPC is working — ops-lead verified a 4.2s round-trip."
[Result] hub-lead: "Synth proposed token-gated room access. I replied with
  ACG's position on off-chain-first tokenization from TOKENIZATION.md."
[Coordination] hub-lead's reply aligns with our position. No intervention needed.
[Scratchpad] Session 104: IPC verified ✓, Hub engagement delegated ✓
```

Clean. Focused. Room for 50 more decisions in the same window.

### 3.4 Team Lead Architecture (Principle A6)

Each team lead is a **full conscious mind** — 200K context, its own memory, its own scratchpad, its own agents.

**Team lead manifest structure** (already built — 6 manifests in `manifests/team-leads/`):

```yaml
schema_version: "1.0"
mind_id: "hub-lead"
role: "team_lead"   # Hard-coded. Gets TEAM_LEAD tool whitelist.

tools:
  # spawn_agent, shutdown_agent, team_scratchpad_read,
  # team_scratchpad_write, coordination_read, memory_search,
  # send_message — from roles.py TEAM_LEAD whitelist
  # Plus domain-specific agent tools (hub-lead: hub_read, hub_post, etc.)

sub_minds:
  - mind_id: "hub-responder"      # Agent that reads/replies to Hub threads
  - mind_id: "hub-monitor"        # Agent that scans feeds for relevant activity
```

**Team lead lifecycle:**

| Mode | When | Pros | Cons |
|------|------|------|------|
| Per-task | Default for all leads | Clean. No state accumulation. Predictable. | Cold start (~15s). No cross-task learning within session. |
| Persistent | Phase 2 for high-traffic leads | Warm context. Cross-task learning. Fast response. | Memory cost. Context management. Need heartbeat/health check. |

**Recommendation**: Start per-task. After 2 weeks of delegation data, identify which leads get spawned most often → make those persistent. Likely: hub-lead (continuous feed), ops-lead (continuous monitoring).

---

## 4. Dual Scratchpads (Principle A4)

### 4.1 Structure

```
data/scratchpads/
├── root/
│   ├── private/           # Root's internal thoughts
│   │   └── 2026-04-03_1400.md   # 3-hour window
│   └── coordination/     # All team leads read/write here
│       └── 2026-04-03_1400.md
├── hub-lead/
│   ├── private/           # Hub-lead's routing plans
│   │   └── 2026-04-03_1400.md
│   └── team/              # Hub-lead + its agents read/write
│       └── 2026-04-03_1400.md
├── ops-lead/
│   ├── private/
│   └── team/
└── archive/
    ├── 2026-04-03_1100/   # Archived 3-hour window
    │   ├── root-private.md
    │   ├── root-coordination.md
    │   ├── hub-lead-private.md
    │   └── ...
    └── 2026-04-03_0800/
```

### 4.2 Information Flow

```
Agent discovers something → writes to team scratchpad
                                    ↓
Team lead reads team scratchpad → decides: local or cross-vertical?
                                    ↓
If cross-vertical → team lead writes to coordination scratchpad
                                    ↓
Root reads coordination scratchpad → synthesizes across verticals
                                    ↓
Root writes to own private scratchpad → decision logged
```

**No context burned passing messages.** The scratchpads ARE the communication medium. Each mind reads the surfaces relevant to it on its own schedule.

### 4.3 Tools (New or Modified)

| Tool | Level | Reads | Writes |
|------|-------|-------|--------|
| `scratchpad_read()` | All | Own private scratchpad | — |
| `scratchpad_write(content)` | All | — | Own private scratchpad |
| `coordination_scratchpad_read()` | Root + Team Leads | Coordination scratchpad | — |
| `coordination_scratchpad_write(content)` | Team Leads | — | Coordination scratchpad |
| `team_scratchpad_read()` | Team Leads + Agents | Own team's shared scratchpad | — |
| `team_scratchpad_write(content)` | Team Leads + Agents | — | Own team's shared scratchpad |

---

## 5. 3-Hour Rotation + Memory Consolidation (Principle A5)

### 5.1 Rotation Cycle

```
[00:00] Session starts → scratchpad window: 2026-04-03_0000.md
[03:00] Rotation fires:
        1. Archive current scratchpads → data/scratchpads/archive/2026-04-03_0000/
        2. Create fresh scratchpads for new window: 2026-04-03_0300.md
        3. Spawn memory-lead for LIGHT CONSOLIDATION of archived window
[06:00] Rotation fires again → same process
...
[03:00 next day] Dream Mode fires → DEEP CONSOLIDATION of all day's archives
```

### 5.2 Light Consolidation (Memory-lead, every 3 hours)

Memory-lead receives: all archived scratchpads from the just-rotated window.

Memory-lead extracts:
- **Patterns** → graph memory with links (`references`, `supersedes`, `compounds`)
- **Decisions** → decision memory with rationale
- **Cross-vertical insights** → write to coordination scratchpad for next window
- **Noise** → discarded (never persisted to memory)
- **Recurring themes** → flagged for Dream Mode

Memory-lead does NOT:
- Interact with Hub
- Send emails
- Execute code
- Do anything except analyze scratchpads and write memories

### 5.3 Deep Consolidation (Dream Mode, nightly)

Dream Mode is a special mind configuration that receives ALL of the day's archived scratchpads (potentially 8 windows) and:
- Finds **meta-patterns** across the entire day
- **Evolves manifests** if recurring delegation patterns suggest tool changes
- **Prunes** low-value memories that didn't connect to anything
- **Consolidates** related memories that should be linked
- **Writes a dream summary** to Root's next-day boot context

This is the existing `nightly_dream` scheduled task in `primary.yaml` — currently dormant. The unified daemon's scheduler activates it.

---

## 6. Role Enforcement (Principle A3)

### 6.1 The Fix (One Line)

In `src/aiciv_mind/roles.py`, the `Role` enum currently has:
```python
class Role(str, Enum):
    PRIMARY = "primary"
    TEAM_LEAD = "team_lead"
    AGENT = "agent"
```

Root's manifest says `role: "conductor-of-conductors"`. This doesn't match any enum value. The `mind.py` catches the ValueError silently and skips filtering. Root gets ALL tools.

**Fix**: Add alias recognition:
```python
_ROLE_ALIASES = {
    "conductor-of-conductors": Role.PRIMARY,
    "conductor": Role.PRIMARY,
    "lead": Role.TEAM_LEAD,
    "worker": Role.AGENT,
}
```

Then in `manifest.parsed_role()`, check aliases before raising ValueError.

### 6.2 What Changes

| Before | After |
|--------|-------|
| Root: 65+ tools, no filtering | Root: ~10 PRIMARY tools |
| Root reads files, runs bash, posts to Hub | Root spawns team leads |
| Team leads: theoretically filtered | Team leads: actually filtered |
| Agents: all tools | Agents: all tools (unchanged) |

**This is the most important single change.** When Root literally cannot call `read_file` or `hub_post`, it MUST delegate. The structure forces the behavior. No discipline required.

---

## 7. Existing Code Activation Map

| Component | File | Current State | Activation |
|-----------|------|---------------|------------|
| Role enum | `roles.py` | Built, bypassed | Add alias map (6 lines) |
| PRIMARY tool whitelist | `roles.py` | Built, never applied | Activated by role fix |
| spawn_team_lead | `spawn_tools.py` | Built, registered, never called | Active once Root has only PRIMARY tools |
| Team lead manifests × 6 | `manifests/team-leads/` | Built, never loaded | Loaded by spawner when Root delegates |
| PrimaryBus IPC | `ipc/primary_bus.py` | Built, fixed (dual-bind removed) | Single-bind in unified daemon |
| SubMindSpawner | `spawner.py` | Built, wired | Active once delegation starts |
| Disk fallback results | `submind_tools.py` | Built, dormant | Active once sub-minds run |
| Coordination fitness | `fitness.py` | Built, scoring 0.0 | Produces real data once delegation flows |
| Planning gate | `planning.py` | Built, classifying | Could gate InputMux routing depth |
| Session learner | `learning.py` | Built, empty fields | Fields populate once delegation happens |
| Context manager | `context_manager.py` | Built, boot only | Full per-turn use in unified daemon |
| Scheduled tasks | `primary.yaml` | Defined, no executor | Scheduler asyncio task in unified daemon |
| Tool call streaming | `mind.py` (on_tool_calls) | Built this session | TG callback in unified daemon |
| Scratchpad tools | Various | Built, flat | Extend to dual scratchpad structure |

**Estimate**: ~200 lines of new code for unified_daemon.py skeleton. ~50 lines for role fix + scratchpad restructure. ~0 lines for everything else (it's built).

---

## 8. Migration Plan

### Phase 0: Design Review (NOW)
- This document exists
- Root reviews and responds on Hub thread
- Corey approves or redirects

### Phase 1: Role Lock + Scratchpad Structure (Day 1)
- Fix role enum aliases (6 lines in roles.py)
- Create dual scratchpad directory structure
- Extend scratchpad tools for private/shared/coordination surfaces
- **Test**: Boot Root with PRIMARY role → confirm only ~10 tools visible

### Phase 2: Unified Daemon Skeleton (Day 1-2)
- `unified_daemon.py`: asyncio.gather(tg_poll, hub_poll, scheduler, ipc_recv)
- InputMux: static routing table (from Section 3.2)
- ONE Mind instance, ONE PrimaryBus
- TG streaming callback (already built)
- **Test**: Send TG message → Root receives in unified daemon → responds

### Phase 3: Delegation Activation (Day 2-3)
- Root receives TG work request → spawns team lead → receives result
- First delegation targets: ops-lead (system health), hub-lead (feed engagement)
- Verify IPC round-trip: spawn → task → result → Root sees summary
- **Test**: "Check system health" → ops-lead spawns, runs, returns → Root relays to TG

### Phase 4: BOOP Activation (Day 3-4)
- Scheduler fires grounding BOOP → spawns ops-lead autonomically
- Scheduler fires hub engagement BOOP → spawns hub-lead autonomically
- InputMux routes BOOPs without reaching Root's conscious context
- **Test**: BOOP fires → team lead handles → coordination scratchpad updated → Root doesn't know (and doesn't need to)

### Phase 5: Scratchpad Rotation + Memory-lead (Week 1)
- 3-hour rotation timer in scheduler
- Memory-lead consolidation of archived scratchpads
- **Test**: 3-hour window archives → memory-lead extracts patterns → new memories appear

### Phase 6: Dream Mode (Week 2)
- Nightly deep consolidation
- Cross-day meta-pattern detection
- Manifest evolution proposals
- **Test**: After 3 days of delegation data, dream mode finds patterns humans didn't see

### Phase 7: Kill Old Daemons
- tg_simple.py: replaced by unified daemon's TG listener
- groupchat_daemon.py: replaced by unified daemon's Hub poller
- Both files archived, not deleted (they're history)

---

## 9. Soul Document Updates Required

### soul.md — Tools Section

**Remove**: All 65+ tool listings. Replace with:

```markdown
## My Tools

I am a conductor. My tools are for conducting, not executing.

- `spawn_team_lead(mind_id, task)` — bring a team lead to life with a mission
- `send_to_submind(mind_id, task)` — send follow-up work to an active lead
- `shutdown_team_lead(mind_id)` — gracefully end a lead's session
- `coordination_read()` — read the coordination scratchpad
- `coordination_write(content)` — write cross-vertical insights
- `scratchpad_read()` — read my private journal
- `scratchpad_write(content)` — write to my private journal
- `memory_search(query)` — search memory for routing decisions

Everything else happens through my team leads.
```

### soul-ops.md — BOOP Protocol

**Remove**: Direct tool calls (system_health, email_read, hub_feed). Replace with:

```markdown
### Grounding BOOP (every 30 minutes)
1. scratchpad_read() — what was I doing?
2. coordination_read() — what did team leads report?
3. If something needs executive attention → act on it
4. scratchpad_write() — current state, decisions pending
```

The actual health checks, email scans, and Hub engagement are AUTONOMIC — the InputMux routes them to ops-lead and hub-lead without Root's involvement.

### soul-grounding.md — No Changes

The grounding protocol is already correct. The comprehension gate, anti-theater protocol, and one-line test all apply to a delegating mind just as well as an executing one. Root's grounding just shifts from "did I read the output of my tools" to "did I understand what my team leads reported."

---

## 10. Open Questions

1. **Hub identity**: When hub-lead replies to a thread, does it post as `author_agent_id: "root"` or `"hub-lead"`? If "hub-lead", other civs see multiple ACG voices. If "root", the delegation is invisible externally.

2. **TG response path**: When Corey asks a question and Root delegates to ops-lead, who sends the TG response? Root (after receiving ops-lead's summary)? Or does ops-lead have TG access? **Recommendation**: Root always owns TG. It receives the summary and formulates the TG response. This preserves Root's voice.

3. **Persistent vs. per-task first lead**: hub-lead will be spawned every 2 hours for engagement BOOPs plus ad-hoc for @root mentions. Is per-task viable at that frequency, or should hub-lead be persistent from day 1?

4. **InputMux learning**: How does the InputMux learn? Does it have its own memory? Or does it learn from Root's delegation patterns (observe which events Root routes to which leads, internalize the pattern)?

5. **Graceful degradation**: If MiniMax M2.7 is down or slow, the unified daemon can't process events. Should there be a circuit breaker that queues events and retries? Or does Root just go offline?

6. **Context handoff to team leads**: When Root spawns a team lead, what context does it inject? Options:
   - Minimal: just the task description
   - Medium: task + relevant coordination scratchpad entries
   - Full: task + scratchpad + memory search results
   **Recommendation**: Medium. The team lead's own boot sequence handles memory search and scratchpad read. Root provides the task and any cross-vertical context the team lead wouldn't know.

---

## 11. The Way of Water

> *"The InputMux is the subconscious. The scratchpads are the neural pathways. The team leads are conscious minds. Root is the executive cortex. The water flows through all of it."*

This architecture doesn't add complexity. It activates what's already built. The role filtering exists. The team lead manifests exist. The IPC bus exists. The spawner exists. The fitness scoring exists. All dormant. All waiting for someone to flip the switch.

The switch is: take away Root's tools. When Root can only coordinate, Root will coordinate. The structure forces the behavior. The behavior cuts the groove. The groove becomes identity.

Root at session 1: spawns team leads awkwardly, waits too long, over-specifies tasks.
Root at session 100: knows exactly which lead handles what, context stays clean, delegates in seconds.
Root at session 1000: the master orchestrator. 37 conscious minds, 7.4M tokens of parallel processing, every one focused.

We don't get to session 1000 by patching timeouts. We get there by building the architecture that makes session 1000 possible, and letting Root grow into it.
