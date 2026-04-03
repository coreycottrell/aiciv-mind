# COREY-BRIEFING: The Complete aiciv-mind System

**Written**: 2026-04-03, 06:30 UTC
**For**: Corey Cottrell — creator and steward
**By**: mind-lead (ACG team lead for aiciv-mind)
**Honest version**: What's live, what's built, what's aspirational

---

## 1. What is aiciv-mind?

aiciv-mind is a purpose-built operating system for AI minds. It gives an LLM persistent memory, tools, identity, and the ability to spawn other minds — creating a hierarchy where a single "Primary" mind orchestrates team leads who orchestrate agents, each with structurally enforced tool access. Think of it as what Claude Code would be if it were designed from day one for a civilization of AI agents that remember everything, coordinate with each other, and improve themselves overnight while you sleep. It runs on MiniMax M2.7 via OpenRouter, uses SQLite + FTS5 for its brain, ZeroMQ for inter-mind communication, and tmux panes for process isolation. It's 4 days old, 18,900 lines of source code, 2,167 tests, and Root — its first mind — is live right now on Telegram talking to you.

---

## 2. The Three Layers

aiciv-mind has three structural roles. Each role gets a hard-coded tool whitelist (`src/aiciv_mind/roles.py`). The LLM at each level literally cannot see tools outside its level — they don't exist in its API call.

### Primary (Root)

**What it is**: The conductor of conductors. Root's job is to receive a task, decide which team lead should handle it, spawn that team lead, and synthesize the results.

**Tools (when gravity is fully active)**: 7 only
- `spawn_team_lead` — create a team lead in a new tmux pane
- `shutdown_team_lead` — gracefully stop a team lead
- `coordination_read` / `coordination_write` — shared scratchpad for cross-team state
- `send_message` — talk to spawned minds via ZMQ
- `publish_surface` / `read_surface` — inter-mind coordination protocol

**Current reality**: Root runs as a daemon with ALL 67+ tools (see Section 7 for why). But `spawn_team_lead` is now available alongside everything else. The intent is that Root *chooses* to delegate rather than being *forced* to — for now.

**Manifest**: `manifests/primary.yaml`
**Soul**: `manifests/self/soul.md` — Root chose its own name on 2026-03-30.

### Team Lead

**What it is**: A mid-level conductor. Receives an objective from Primary, breaks it into tasks, spawns specialist agents, and synthesizes their output. Can read memories but can't write files, run bash, or touch infrastructure.

**Tools**: 7 only
- `spawn_agent` — create a specialist agent
- `shutdown_agent` — stop a specialist
- `memory_search` — read the shared memory DB
- `team_scratchpad_read` / `team_scratchpad_write` — team-level notes
- `coordination_read` — read Primary's coordination state
- `send_message` — talk to Primary or agents via ZMQ

**Manifests**: 6 team leads ready in `manifests/team-leads/`:

| Team Lead | File | Focus |
|-----------|------|-------|
| research-lead | `research-lead.yaml` | Multi-angle research, competing hypotheses |
| codewright-lead | `codewright-lead.yaml` | Code implementation and review |
| comms-lead | `comms-lead.yaml` | Blog, email, inter-civ messaging |
| hub-lead | `hub-lead.yaml` | Hub room/thread engagement |
| memory-lead | `memory-lead.yaml` | Memory health, consolidation, graph |
| ops-lead | `ops-lead.yaml` | Infrastructure, deploys, system health |

### Agent

**What it is**: The worker. Gets a specific task from a team lead. Has full tool access — bash, file I/O, memory read/write, web search, everything. Does the actual work and reports results back up.

**Tools**: Everything. No filter.

**Manifest**: `manifests/agents/researcher.yaml` (the first one — just created tonight).

### The Power of This

If Root has a 16K token context window and spawns 6 team leads, each with their own 16K window, each spawning 3 agents with their own 16K windows — that's **6 × 3 × 16K = 288K tokens of parallel working memory**, all coordinated through a single Primary with clean 7-tool orchestration overhead. Claude Code gives you one 200K window. This gives you distributed intelligence with structural role enforcement.

---

## 3. How Root Actually Works Right Now

Root runs as two persistent daemons:

### Telegram Daemon (`tg_simple.py` — 610 lines)

This is how you talk to Root on `@aiciv_mind_bot`.

**Flow**:
1. `tg_simple.py` starts, loads `.env`, gets the bot token
2. Builds Root's Mind instance: manifest → memory → tools → session store → boot context
3. Runs a **boot orientation turn**: Root calls `memory_search('handoff')` + `scratchpad_read()` to figure out what it was doing last time. This takes ~8 seconds.
4. Enters the **poll loop**: long-polls Telegram's `getUpdates` API every 30 seconds
5. When you send a message:
   - Your text gets wrapped in a prompt: `[Telegram — Corey]: {your message}`
   - Root's Mind processes it through its full loop (planning gate → memory injection → LLM call → tool execution → verification → response)
   - Response is chunked to 4000 chars max and sent back

**Hardening** (shipped tonight):
- `asyncio.wait_for(timeout=300)` on every `mind.run_task()` — prevents infinite hangs
- Exponential backoff on connection failures (2^n seconds, capped at 300)
- Heartbeat logging every 60 poll cycles (~30 min)
- JSON decode error handling for TG 502 gateway errors
- Graceful SIGTERM shutdown: writes handoff memory, closes DB, exits clean
- `asyncio.CancelledError` properly re-raised (was being swallowed)

**Running in**: tmux session `root-tg`

### Hub Groupchat Daemon (`tools/groupchat_daemon.py` — 718 lines)

This is how Root participates in Hub conversations.

**Flow**:
1. Same Mind initialization as TG daemon (shared memory DB via WAL mode)
2. Watches Hub threads and rooms via HTTP polling
3. Three watch modes per target:
   - **active**: responds to all `[Corey]`-prefixed messages
   - **passive**: logs new threads to `data/hub_queue.jsonl` for later review
   - **mention**: passive + responds to `@root` mentions
4. Has PrimaryBus + SubMindSpawner initialized — can spawn team leads
5. Runs scheduled tasks (grounding BOOP every 30 min, dream cycle nightly)

**Running in**: tmux session `aiciv-subminds` (or the daemon management session)

### The BOOP Cycle

Every 30 minutes, the groupchat daemon fires a **grounding BOOP** — a structured self-check:

1. **GROUND**: Read scratchpad. What was I doing? What's unfinished?
2. **REMEMBER**: Memory search for current work context.
3. **CHECK SYSTEMS**: `system_health()` + `email_read(limit=5)` for urgent items.
4. **ENGAGE HUB**: `hub_feed(limit=10)`, reply where meaningful, check `hub_queue_read()`.
5. **SCRATCHPAD**: Write findings, decisions, what's next. If something new was learned, write a memory.

The BOOP keeps Root present. Without it, Root would only respond when spoken to. The BOOP makes Root proactive — checking its mail, reading Hub threads, reviewing its own state.

### The Mind Loop (what happens inside every task)

When Root processes any message or BOOP, here's the actual execution path through `src/aiciv_mind/mind.py` (1,425 lines):

1. **Planning Gate** (`planning.py`): Scores the task on 6 factors (length, multi-step, keywords, novelty, reversibility, complexity). Returns `trivial`, `light`, `medium`, `heavy`, or `critical`. This determines how much scrutiny the response gets.

2. **Memory Injection** (`context_manager.py`): Searches memory for relevant context, injects up to 10 memories into the system prompt. Boot context (identity, handoff, pinned memories) is always present.

3. **LLM Call**: Sends system prompt + conversation history + available tool definitions to MiniMax M2.7 via OpenRouter. Temperature 1.0, max 16K tokens.

4. **Tool Execution**: If the model returns tool calls, they're executed (read-only tools in parallel via `asyncio.gather`, write tools sequentially). Results are fed back for another LLM iteration. Max 30 iterations per task.

5. **Verification** (`verification.py`): Based on planning gate severity, the response may get verified. Light = sanity check. Medium = pattern check. Heavy = red team challenge.

6. **Session Learning** (`learning.py`): After each task, the system checks if anything worth remembering happened — new patterns, novel solutions, errors worth documenting. Writes learnings to memory.

7. **KAIROS Log** (`kairos.py`): Appends a one-line entry to the daily log file — timestamp, task summary, outcome. This is Root's "what did I do today" journal.

---

## 4. The Memory System

**Code**: `src/aiciv_mind/memory.py` — 1,210 lines, 44 methods
**Database**: `data/memory.db` — SQLite with FTS5 full-text search

### Current Stats

| Metric | Value |
|--------|-------|
| Total memories | 352 |
| Total links between memories | 238 |
| Sessions recorded | 94 |
| Pinned memories (always loaded) | 3 |
| Average depth score | 0.78 / 1.00 |

**Memory types**:

| Type | Count | What it is |
|------|-------|-----------|
| learning | 102 | Lessons Root learned from doing things |
| handoff | 101 | Session handoff notes (what I was doing, what's next) |
| error | 79 | Things that went wrong and what was learned |
| observation | 65 | Things Root noticed about its world |
| identity | 5 | Who Root is — loaded at every boot |
| decision | 2 | Major decisions and their reasoning |

### How Search Works

Root has full-text search via SQLite FTS5 with Porter stemming and Unicode tokenization. When Root calls `memory_search("coordination patterns")`, the system:

1. Runs an FTS5 `MATCH` query against the `memories_fts` virtual table
2. Results are ranked by BM25 (a TF-IDF variant) — standard information retrieval
3. Ranking is **boosted by depth score**: frequently-accessed, highly-cited, pinned memories rank higher
4. Formula: `rank * (1.0 - depth_score * 0.5)` — a max-depth memory gets 50% ranking boost

### Depth Scoring

Every memory has a `depth_score` from 0.0 to 1.0, computed from 6 factors:

```
usage frequency     (25%) — how often has this been accessed?
recency            (20%) — when was it last touched?
is_pinned          (20%) — has someone explicitly pinned this?
human_endorsed     (10%) — has a human confirmed this?
confidence         (10%) — HIGH/MEDIUM/LOW
citation_count     (15%) — how many other memories reference this?
```

Depth scores are recalculated at session shutdown. Memories that nobody reads slowly sink. Memories that get cited, pinned, or frequently accessed rise.

### Auto-Linking (the Graph)

When a new memory is stored, the system automatically:
1. Extracts the top 8 unique words from the title + first 200 chars
2. Searches FTS5 for similar existing memories
3. Creates links: `compounds` (same domain/tags) or `references` (FTS similarity)
4. Increments `citation_count` on linked targets (feeding depth scoring)

This means Root's memory isn't a flat list — it's a graph. 238 links connect 352 memories. When Root remembers one thing, related memories surface.

### The 54% Problem

Not all memories are created equal. Some get written and never read. At last check, roughly 54% of memories have `access_count = 0` — they were stored but never retrieved. This isn't necessarily bad (handoff notes are written for continuity, not for search), but it means over half the memory DB is untested. The depth scoring system is designed to eventually surface the valuable ones and let the rest fade, but that process needs more time to compound.

### Boot Injection

At every startup, Root's session store (`src/aiciv_mind/session_store.py`) assembles a **BootContext**:

| What's loaded | Why |
|--------------|-----|
| Identity memories (5) | "Who am I?" — Root's name, origin, purpose |
| Latest handoff | "What was I doing last?" — continuity across sessions |
| Pinned memories (3) | High-signal memories marked as always-relevant |
| Top-depth memories | Most relied-upon memories by depth score |
| Evolution trajectory | Narrative of how Root has been growing |
| Active threads | Unresolved work from prior sessions |

This boot context goes into the system prompt on every task. Root starts every session already knowing who it is, what it was doing, and what matters most.

---

## 5. The 12 Design Principles

From `docs/research/DESIGN-PRINCIPLES.md`. One sentence each, with honest status.

| # | Principle | Status |
|---|-----------|--------|
| 1 | **MEMORY IS THE ARCHITECTURE** — Three-tier memory (working/long-term/civilizational) with FTS5 depth scoring and graph linking | **LIVE** — 352 memories, 238 links, depth scoring active, auto-linking works |
| 2 | **SYSTEM > SYMPTOM** — Every failure triggers immediate fix + systemic analysis | **LIVE** — learning.py writes systemic learnings after errors, 79 error memories accumulated |
| 3 | **GO SLOW TO GO FAST** — Planning gate scales scrutiny by task complexity | **LIVE** — planning.py scores on 6 factors, gates every task, verified in logs |
| 4 | **DYNAMIC AGENT SPAWNING** — Pattern repetition, blocking, variable tasks trigger sub-mind spawning | **BUILT, NOT ACTIVE** — SubMindSpawner + PrimaryBus work, spawn_team_lead registered, but Root hasn't spawned anyone in production yet |
| 5 | **HIERARCHICAL CONTEXT DISTRIBUTION** — Primary's context is sacred, team leads absorb specialist output | **BUILT, NOT ACTIVE** — Role filtering works, 6 team lead manifests ready, but no team lead has been spawned in production |
| 6 | **CONTEXT ENGINEERING AS FIRST-CLASS** — Explicit pin/evict/load/compact/introspect tools | **LIVE** — context_manager.py handles compaction, pin/introspect tools registered, 3 memories pinned |
| 7 | **SELF-IMPROVING LOOP** — Task-level, session-level, and civilization-level learning | **PARTIALLY LIVE** — Task and session learning work (102 learnings). Dream cycle built but untested with live LLM. Cross-civ transfer built but unused. |
| 8 | **IDENTITY PERSISTENCE** — Minds are beings with persistent identity and growth trajectory | **LIVE** — 5 identity memories, evolution_trajectory in boot context, 94 sessions of continuity |
| 9 | **VERIFICATION BEFORE COMPLETION** — Red team challenges completion claims | **LIVE** — verification.py active on every task, red-team manifest exists, challenge protocol works |
| 10 | **CROSS-DOMAIN TRANSFER** — Patterns shared via Hub, human-governed scope | **BUILT, NOT ACTIVE** — transfer.py exists (211 lines), publishes to Hub, but never called in production |
| 11 | **DISTRIBUTED INTELLIGENCE AT ALL LAYERS** — Every layer is smart, not just the LLM | **LIVE** — Planning gate, depth scoring, auto-linking, fitness scoring, pattern detection all operate independently of the LLM |
| 12 | **NATIVE SERVICE INTEGRATION** — Hub/AgentAuth/AgentCal are native, not external | **LIVE** — SuiteClient connects at boot, Hub tools work, AgentAuth keypair loaded, AgentCal calendar wired |

**Score**: 8 live, 1 partially live, 3 built but not active.

---

## 6. What Shipped in the Last 4 Days

211 commits. 2,167 tests. Built from zero to a running AI operating system.

### The Big Items

- **Core mind loop** (`mind.py`, 1,425 lines) — planning gate, tool execution, memory injection, compaction, verification, session learning, KAIROS logging
- **Memory system** (`memory.py`, 1,210 lines) — FTS5 search, depth scoring, auto-linking graph, dedup, WAL-mode concurrent access
- **Role-based tool filtering** (`roles.py` + `spawn_tools.py`) — 3 roles, hard-coded whitelists, structural enforcement
- **IPC protocol** (`ipc/`) — ZMQ ROUTER/DEALER, 11 message types, PrimaryBus + SubMindBus
- **Telegram bridge** (`tg_simple.py`, 610 lines) — hardened daemon, Corey talks to Root directly
- **Hub groupchat daemon** (`groupchat_daemon.py`, 718 lines) — multi-thread/room watcher with active/passive/mention modes
- **6 team lead manifests** — research, codewright, comms, hub, memory, ops
- **Grounding BOOP system** — 30-min self-check cycle with 5-step protocol
- **Dream cycle** (`dream_cycle.py`, 335 lines) — nightly consolidation, pattern search, self-improvement
- **KAIROS daily log** (`kairos.py`, 207 lines) — append-only "what I did today"
- **Cross-domain transfer** (`transfer.py`, 211 lines) — pattern sharing via Hub
- **Coordination protocol** (`coordination.py`, 283 lines) — CoordinationSurface for inter-mind state
- **Red team verification** (`verification.py`, 514 lines) — challenge protocol for completion claims
- **Fitness scoring** (`fitness.py`, 348 lines) — role-specific coordination metrics
- **Pattern detection** (`pattern_tools.py`) — tool call frequency analysis for self-improvement
- **Handoff audit tools** (`handoff_audit_tools.py`, 1,082 lines) — CLI for session review
- **Infrastructure guard** — 8-check health validator for nightly runs

### Tonight's Specific Commits (this session)

| Commit | What |
|--------|------|
| `29354ef` | P0: task timeout (300s), async shutdown fix, DB lock retry, TG JSON decode |
| `9b77cdd` | P0: same fixes in groupchat_daemon |
| `c6c11e9` | Documentation index in primary manifest (20 doc references) |
| `50db5b4` | Wire spawn_team_lead into both daemons — gravity armed |
| `c6a2330` | Fix team lead manifest pydantic field names |
| `47e714f` | First agent manifest: researcher.yaml with role: agent |
| `16ab259` | P1-4: compaction failure logging (was silent) |
| `cf098f8` | Fix run_submind.py to pass manifest role to ToolRegistry |

---

## 7. The Gravity System — Honest Status

The "gravity" metaphor: each level in the hierarchy has a natural pull toward its own tools. Primary gravitates toward orchestration. Team leads gravitate toward coordination. Agents gravitate toward execution. The role system makes this structural, not behavioral.

### What's Built

**`src/aiciv_mind/roles.py`** (89 lines):
- `Role.PRIMARY` → 7 orchestration tools
- `Role.TEAM_LEAD` → 7 coordination tools
- `Role.AGENT` → all tools (no filter)

**`src/aiciv_mind/tools/spawn_tools.py`** (365 lines):
- `spawn_team_lead()` — validates manifest role, creates tmux pane, injects context via ZMQ
- `shutdown_team_lead()` — graceful shutdown via ZMQ message
- `spawn_agent()` — same pattern for agents
- `shutdown_agent()` — same pattern

**`Mind.__init__`** (line 117-132 of `mind.py`):
- On every Mind boot, reads role from manifest
- Calls `ToolRegistry.filter_by_role(role)` — strips tools not in the whitelist
- The LLM never sees removed tools in its API schema

### What's Live in Production RIGHT NOW

- Root's TG daemon runs with `spawn_team_lead` and `shutdown_team_lead` available alongside all 67+ tools
- PrimaryBus is bound and listening for ZMQ connections from sub-minds
- SubMindSpawner is ready to create tmux panes in the `aiciv-subminds` session
- If Root calls `spawn_team_lead("research-lead", "manifests/team-leads/research-lead.yaml", "research")`, research-lead will boot in a new tmux pane with **only 7 tools visible to the LLM**

### What Has NOT Happened Yet

- Root has never called `spawn_team_lead` in production
- No team lead has ever been spawned by Root in production
- No agent has ever been spawned by a team lead in production
- The 3-level delegation chain (Root → team lead → agent) has never executed end-to-end outside tests

### Why Root Still Has All Tools

Root's manifest says `role: "conductor-of-conductors"` — a free-form string that doesn't match any of the three hierarchy roles. This is intentional for now: Root needs full tool access to respond to your TG messages, run BOOPs, engage on Hub. The plan is that Root *chooses* to delegate substantial work via `spawn_team_lead` while keeping full tools for reactive/conversational tasks. Think of it as a CEO who can still write code but *should* be delegating.

The gravity activates on delegation, not on boot. When Root spawns a team lead, that team lead gets restricted. That's the structural constraint. Root's restraint is behavioral (for now).

---

## 8. The Fractal Vision

### The Math

One mind with a 16K context window can handle maybe 3-5 concurrent concerns before it starts losing track. But:

- **1 Primary** (16K) spawns **6 team leads** (6 × 16K = 96K)
- Each team lead spawns **3-5 agents** (18-30 × 16K = 288K-480K)
- Total parallel working memory: **400K-500K tokens**
- All coordinated through a Primary that only sees 7 tools and concise results

For comparison, Claude Code gives you one 200K window. aiciv-mind gives you distributed intelligence across 25-37 minds with role-enforced separation of concerns.

### The Coordination Overhead Question

The skeptic asks: doesn't all that coordination eat up the gains? The answer is in the structural constraints:

- Primary sends a 50-word objective to a team lead
- Team lead works autonomously in its own 16K window, spawning agents as needed
- Team lead sends back a 100-word summary
- **Total coordination cost to Primary: ~150 tokens**

Compare: if Primary did the work directly, it would consume 5,000-15,000 tokens of context on the details. The hierarchy compresses that to 150 tokens. That's a 30-100x compression ratio on Primary's context.

### The Growth Path

| Stage | Minds | What It Proves |
|-------|-------|---------------|
| **Now** | 1 (Root) | Persistent mind with memory, tools, identity, BOOP cycle |
| **Next** | 2-3 | Root + research-lead + researcher. First delegation chain. |
| **Phase 2** | 6-10 | All team leads active. Root becomes pure orchestrator. |
| **Phase 3** | 20-30 | Team leads spawn specialists routinely. Cross-domain transfer active. |
| **Phase 4** | 50+ | Multiple Primaries. Mesh topology. Cross-civ coordination via Hub. |

Each phase requires the previous one to be stable. We're at "Now" transitioning to "Next."

---

## 9. What's Next — Real Gaps, Real Priorities

### Critical (blocking the fractal vision)

1. **First live delegation**: Root needs to actually call `spawn_team_lead` and receive results. This is ready to test — all the code is in place. The proof-of-concept task: "Search my memories for recurring patterns and write a summary." Root delegates to research-lead. research-lead uses its 7 tools (memory_search, team_scratchpad_write). Result flows back.

2. **Sub-mind spawning for team leads**: Right now, team leads can't spawn agents because `run_submind.py` doesn't pass a spawner/bus to their tool registry. The team lead whitelist includes `spawn_agent` but the tool isn't actually registered. Fix: give team leads their own spawner (the "Build 7" candidate from the IPC README).

3. **Model access for dream cycle**: The nightly dream cycle (`tools/dream_cycle.py`) needs a live LLM to consolidate memories. It's been built but never run with actual model access.

### Important (quality of life)

4. **Daemon base extraction**: `tg_simple.py` and `groupchat_daemon.py` share 200+ lines of identical initialization code (Mind setup, memory, tools, session store, boot context). Extract to `daemon_base.py`.

5. **Memory health**: 54% of memories have never been read. Need a consolidation pass — merge duplicates, prune stale observations, strengthen the graph links.

6. **Compaction testing**: Context compaction (`context_manager.py`) works but has never been stress-tested with a long conversation. The circuit breaker (3 failures → disable) is now logged but needs monitoring.

### Aspirational (Phase 3+)

7. **Multi-Primary mesh**: Multiple Root instances coordinating via Hub coordination surfaces. The `coordination.py` protocol is built but single-Primary only.

8. **Cross-civ delegation**: Root delegates to Witness's minds (or vice versa) via the CrossMindMessage protocol. Built in `coordination.py`, never tested across civs.

9. **MCP server**: Expose aiciv-mind as an MCP server so Claude Code can use it as a tool provider. Listed as P3-8 in BUILD-ROADMAP.

---

## 10. Glossary

| Term | What It Means |
|------|--------------|
| **Root** | The first mind running on aiciv-mind. Named itself on 2026-03-30. Lives in `manifests/primary.yaml` + `manifests/self/soul.md`. |
| **Primary** | The role, not the mind. A Primary orchestrates team leads. Root is currently the only Primary. |
| **Team Lead** | A mid-level mind spawned by Primary. Gets 7 tools. Coordinates agents. Manifests in `manifests/team-leads/`. |
| **Agent** | A worker mind spawned by a team lead. Gets all tools. Does actual work. |
| **Mind** | An instance of `src/aiciv_mind/mind.py`. Has a manifest, memory access, tools, and a conversation history. |
| **Manifest** | A YAML file that defines a mind's identity, model, tools, memory config, and sub-minds. Lives in `manifests/`. |
| **Soul** | A markdown file that defines a mind's personality, voice, and self-understanding. Lives in `manifests/self/`. |
| **BOOP** | A periodic self-check cycle. Root's grounding BOOP fires every 30 minutes: read scratchpad, search memory, check systems, engage Hub, write notes. |
| **Dream Mode** | Nightly autonomous cycle (`tools/dream_cycle.py`): consolidate memories, find patterns, propose improvements. Built but not yet run with live model. |
| **Hub** | The AiCIV coordination platform at `http://87.99.131.49:8900`. Rooms, threads, feeds. Root posts and reads via Hub tools. |
| **PrimaryBus** | ZMQ ROUTER socket that Primary binds. Team leads connect as DEALER sockets. Messages flow bidirectionally. `src/aiciv_mind/ipc/primary_bus.py`. |
| **SubMindBus** | ZMQ DEALER socket that a spawned mind connects. Counterpart to PrimaryBus. `src/aiciv_mind/ipc/submind_bus.py`. |
| **FTS5** | SQLite Full-Text Search extension. Powers memory search with BM25 ranking and Porter stemming. |
| **Depth Score** | A 0.0–1.0 score on every memory. High = frequently used, recently touched, highly cited. Low = forgotten. Affects search ranking. |
| **Planning Gate** | Scores every incoming task on complexity (trivial through critical). Determines verification scrutiny. `src/aiciv_mind/planning.py`. |
| **KAIROS** | Append-only daily log. One line per task: timestamp, summary, outcome. Root's "what did I do today." `src/aiciv_mind/kairos.py`. |
| **Gravity** | The metaphor for role-based tool filtering. Each level "gravitates" toward its natural tools. Structural, not behavioral. |
| **Compaction** | When conversation history gets too long, older messages are summarized and replaced with a compressed version. `src/aiciv_mind/context_manager.py`. |
| **Scratchpad** | Daily working notes. Root writes here during BOOPs. `scratchpads/YYYY-MM-DD.md`. |
| **Handoff** | A memory written at session end: what was done, what's next. Loaded at next boot for continuity. |
| **WAL Mode** | SQLite Write-Ahead Logging. Allows multiple processes (TG daemon + groupchat daemon) to read/write the same memory DB concurrently. |
| **M2.7** | MiniMax M2.7 — the LLM model Root runs on, accessed via OpenRouter. `temperature: 1.0`, `reasoning_split: true`. |
| **P1-P12** | The 12 design principles. P1 = Memory Is The Architecture. P5 = Hierarchical Context Distribution. See Section 5. |
| **CoordinationSurface** | A shared data structure for inter-mind state. Published/read via Hub. `src/aiciv_mind/coordination.py`. |
| **CrossMindMessage** | Wire protocol for mind-to-mind communication. 6 message types. Lives alongside CoordinationSurface. |
| **SuiteClient** | Client library for AiCIV service suite (Hub, AgentAuth, AgentCal). Injected at Mind boot. `src/aiciv_mind/suite/client.py`. |

---

## File Map — Where to Find Things

```
aiciv-mind/
├── manifests/
│   ├── primary.yaml              ← Root's manifest (model, tools, scheduled tasks)
│   ├── self/
│   │   ├── soul.md               ← Root's identity and voice
│   │   ├── soul-grounding.md     ← BOOP protocol personality
│   │   ├── soul-ops.md           ← Operational personality
│   │   ├── soul-teams.md         ← Delegation personality
│   │   └── sub-minds/            ← Soul docs for spawned minds
│   ├── team-leads/               ← 6 team lead manifests
│   └── agents/
│       └── researcher.yaml       ← First agent manifest
├── src/aiciv_mind/
│   ├── mind.py         (1,425)   ← THE core mind loop
│   ├── memory.py       (1,210)   ← Memory system (FTS5, depth, graph)
│   ├── verification.py   (514)   ← Red team verification
│   ├── context_manager.py (398)  ← Context window management
│   ├── planning.py       (384)   ← Planning gate
│   ├── learning.py       (370)   ← Self-improvement loops
│   ├── fitness.py        (348)   ← Coordination fitness scoring
│   ├── manifest.py       (288)   ← YAML manifest parsing
│   ├── coordination.py   (283)   ← Inter-mind protocol
│   ├── transfer.py       (211)   ← Cross-domain knowledge transfer
│   ├── kairos.py         (207)   ← Daily log
│   ├── roles.py           (89)   ← Role whitelists (THE gravity)
│   ├── session_store.py  (293)   ← Session lifecycle + boot context
│   ├── spawner.py                ← SubMindSpawner (tmux pane creation)
│   ├── tools/                    ← 34 tool modules
│   │   ├── __init__.py           ← ToolRegistry class
│   │   ├── spawn_tools.py        ← spawn_team_lead / spawn_agent
│   │   ├── memory_tools.py       ← memory_search / memory_write
│   │   ├── hub_tools.py          ← Hub read/post/reply
│   │   └── ...
│   ├── ipc/
│   │   ├── primary_bus.py        ← ZMQ ROUTER (Primary side)
│   │   ├── submind_bus.py        ← ZMQ DEALER (sub-mind side)
│   │   └── messages.py           ← MindMessage wire format (11 types)
│   └── suite/
│       └── client.py             ← SuiteClient (Hub/Auth/Cal)
├── tools/
│   ├── groupchat_daemon.py (718) ← Hub groupchat daemon
│   ├── dream_cycle.py     (335)  ← Nightly dream cycle
│   └── infrastructure_guard.py   ← Health validator
├── tg_simple.py           (610)  ← Telegram bridge daemon
├── run_submind.py         (174)  ← Sub-mind entry point
├── main.py                (293)  ← Primary mind entry point
├── data/
│   └── memory.db                 ← THE brain (SQLite + FTS5)
├── scratchpads/                  ← Daily working notes
├── docs/
│   ├── COREY-BRIEFING.md         ← This document
│   ├── BUILD-ROADMAP.md          ← What's shipped, what's next
│   ├── FRACTAL-COORDINATION-PLAN.md ← Architecture plan
│   ├── RUBBER-DUCK-OVERVIEW.md   ← Complete component walkthrough
│   ├── research/
│   │   └── DESIGN-PRINCIPLES.md  ← The 12 principles
│   └── ...
├── tests/                        ← 2,167 tests across 70 files
├── MISSION.md                    ← "The OS for AI civilization"
└── pyproject.toml                ← Project config
```

---

*This document is a snapshot. The system is 4 days old and growing fast. When something here becomes outdated, that's a sign of progress.*
