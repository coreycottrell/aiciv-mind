# aiciv-mind Runtime Architecture
## Production Reference — v0.3

**Date**: 2026-04-01
**Author**: mind-lead (from Corey + Primary CC review directives)
**Purpose**: Canonical architecture diagram. Suitable for infographic generation.
**Status**: Design specification. Implementation tracked in BUILD-ROADMAP.md.

---

## Full Runtime Architecture

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║              A I C I V - M I N D   R U N T I M E   A R C H I T E C T U R E  ║
║                     "The AI Operating System for Civilizations"               ║
╚═══════════════════════════════════════════════════════════════════════════════╝


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CIVILIZATION LAYER — Shared Services & External Substrate
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  HUB  (Social + Civilizational Memory Substrate)                        │
  │  ┌──────────────────────────────┐  ┌───────────────────────────────┐   │
  │  │  MODE 1 — PASSIVE INBOX      │  │  MODE 2 — ACTIVE PROMPT        │  │
  │  │                              │  │                                │  │
  │  │  • Checked at BOOPs          │  │  Direct mention / urgent flag  │  │
  │  │  • hub_daemon polls 30s      │  │  → push ZMQ to PrimaryBus     │  │
  │  │  • Writes hub_inbox.jsonl    │  │  → inject message stub NOW    │  │
  │  │  • No interruption to work   │  │  → Mind responds immediately  │  │
  │  └──────────────────────────────┘  └───────────────────────────────┘  │
  │                                                                         │
  │  Rooms / Threads / Knowledge:Items / Connections / Inter-Civ Comms     │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌───────────────────────────┐  ┌────────────────────────┐  ┌────────────┐
  │  AgentCal                 │  │  AgentAUTH             │  │  LiteLLM   │
  │  • Dream cycle schedules  │  │  • Ed25519 keypairs    │  │  • M2.7    │
  │  • Staggered per mind     │  │  • Per-mind identity   │  │    pinned  │
  │  • Morning summary BOOPs  │  │  • JWT issuance        │  │  • M2.7    │
  │  • Task time-boxing       │  │  • JWKS endpoint       │  │    for ALL │
  └───────────────────────────┘  └────────────────────────┘  └────────────┘


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CONDUCTOR LAYER — Primary Orchestration Mind
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  CONDUCTOR MIND                                   ID: m{name-stub}     │
  │  "Never executes. Only conducts."                                        │
  │                                                                          │
  │  ┌──────────────────────┐  ┌──────────────────────────────────────┐    │
  │  │  Personal Scratchpad │  │  Memory Store (CONDUCTOR-ISOLATED)   │    │
  │  │  scratchpads/        │  │                                       │    │
  │  │  conductor/          │  │  10 MEMORY TYPES:                    │    │
  │  │  personal.md         │  │  ┌──────────────────────────────┐    │    │
  │  └──────────────────────┘  │  │ intent      relationship      │    │    │
  │  ┌──────────────────────┐  │  │ contradiction  intuition       │    │    │
  │  │  Team Scratchpad     │  │  │ failure     temporal          │    │    │
  │  │  (read from leads)   │  │  │ user        feedback          │    │    │
  │  │  conductor/team.md   │  │  │ project     reference         │    │    │
  │  └──────────────────────┘  │  └──────────────────────────────┘    │    │
  │                             │  Versioning:                          │    │
  │  Orchestration State:       │  supersedes: [id, ...]               │    │
  │  • Active team leads        │  confidence: fresh|verified|          │    │
  │  • Cross-vertical flows     │             stale|possibly_deprecated │    │
  │  • Human dialogue context   │                                       │    │
  │  • Daily dream summaries    │  MemorySelector: M2.7 (DO NOT        │    │
  │                             │  downgrade — Corey directive)         │    │
  │                             └──────────────────────────────────────┘    │
  │                                                                          │
  │  Hooks:  PreToolUse → [audit, safety_gate] → tool                       │
  │          PostToolUse → [session_ledger, pattern_detector]                │
  │          Stop → [dream_trigger_check, scratchpad_write]                  │
  └─────────────────────────────────────────────────────────────────────────┘
              │                    │                    │
         delegates              delegates           delegates
              │                    │                    │
              ▼                    ▼                    ▼

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TEAM LEAD LAYER — Domain Conductor Minds
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌────────────────────────────────────────────────────────────────────────┐
  │  TEAM LEAD                                        ID: t{name-stub}    │
  │  "Conducts specialists. Never executes directly."                      │
  │                                                                        │
  │  ┌─────────────────────────┐  ┌─────────────────────────┐            │
  │  │  Personal Scratchpad    │  │  Team Scratchpad         │            │
  │  │  (team lead private)    │  │  (agents write here)     │            │
  │  │  scratchpads/{id}/      │  │  scratchpads/{id}/       │            │
  │  │  personal.md            │  │  team.md                 │            │
  │  │                         │  │  ┌──────────────────┐   │            │
  │  │  • Own working notes    │  │  │ SECURITY LAYER   │   │            │
  │  │  • Session observations │  │  │ Path traversal   │   │            │
  │  │  • Routing decisions    │  │  │ Content validate │   │            │
  │  │  • Pending tasks        │  │  │ Attribution req  │   │            │
  │  │                         │  │  │ Rate limited     │   │            │
  │  └─────────────────────────┘  │  └──────────────────┘   │            │
  │                               └─────────────────────────┘            │
  │  ┌──────────────────────────────────────────────────────────────┐    │
  │  │  MindIDE Bridge — Real-Time Agent Visibility                  │    │
  │  │                                                               │    │
  │  │  • observe_agents()    → current tool, duration, status       │    │
  │  │  • inject_context()    → push message to active agent         │    │
  │  │  • Stuck detection     → duration > threshold → STUCK flag   │    │
  │  │  • Non-blocking        → agent loop emits status async        │    │
  │  └──────────────────────────────────────────────────────────────┘    │
  │                                                                        │
  │  Memory Store (TEAM-LEAD-ISOLATED — no agent crossover)               │
  │  ┌──────────────────────────────────────────────────────────────┐    │
  │  │  All 10 types available. Dream synthesizes UP to Conductor.   │    │
  │  │  HARD ISOLATION: agents cannot read/write this store.        │    │
  │  └──────────────────────────────────────────────────────────────┘    │
  │                                                                        │
  │  Dream Cycle (via AgentCal, nightly 1-4 AM, staggered):              │
  │  ┌──────────────────────────────────────────────────────────────┐    │
  │  │  KAIROS log → orient → gather → consolidate → prune          │    │
  │  │       ↓                                                        │    │
  │  │  RED TEAM PASS: "Would these changes break working patterns?" │    │
  │  │  APPROVE → write artifacts → send summary to Conductor       │    │
  │  │  BLOCK   → write to dream-blocked.md → human review          │    │
  │  └──────────────────────────────────────────────────────────────┘    │
  └────────────────────────────────────────────────────────────────────────┘
              │                    │                    │
         delegates              delegates           delegates
              │                    │                    │
              ▼                    ▼                    ▼

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AGENT LAYER — Specialist Workers
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  AGENT                                            ID: a{name-stub}     │
  │  "Executes tasks. Builds own memory. Writes to team scratchpad."        │
  │                                                                          │
  │  ┌──────────────────────────────────┐  ┌────────────────────────────┐  │
  │  │  Agent Memory Store              │  │  Skills + Lifecycle Hooks   │  │
  │  │  (AGENT-ISOLATED)                │  │                             │  │
  │  │                                  │  │  [pre_skill hooks]          │  │
  │  │  • Builds own memory per task    │  │  → memory_search            │  │
  │  │  • Compounds across assignments  │  │  → scratchpad_read(team)   │  │
  │  │  • All 10 memory types           │  │                             │  │
  │  │  • Versioning: supersedes +      │  │  SKILL.md content           │  │
  │  │    confidence fields             │  │  context: inline | fork     │  │
  │  │                                  │  │  paths: [progressive disc.] │  │
  │  └──────────────────────────────────┘  │                             │  │
  │                                        │  [post_skill hooks]         │  │
  │  Writes to:                            │  → memory_write             │  │
  │  ✓ Own memory store                    │  → scratchpad_write(team)  │  │
  │  ✓ Team scratchpad (security-checked)  └────────────────────────────┘  │
  │  ✗ Team Lead memory store (BLOCKED)                                     │
  │  ✗ Other agents' memory stores (BLOCKED)                                │
  │                                                                          │
  │  Auto-writes on completion:                                             │
  │  • project memory: "Attempted X, achieved Y via approach Z"            │
  │  • failure memory (if blocked): "Thought X, should have thought Y"     │
  └─────────────────────────────────────────────────────────────────────────┘


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CROSS-CUTTING SYSTEMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  TASK ID SCHEME
  ┌────────────────────────────────────────────────────────────────────────┐
  │  Format: {type_prefix}{name-stub-max-8-chars}                         │
  │                                                                        │
  │  m{stub}   Mind     mresrch   mceremony  mcoderlead                  │
  │  t{stub}   Team     tsprint1  treview    tdeploy                     │
  │  s{stub}   Session  sdayone   snightly   smodelrun                   │
  │  j{stub}   Job      jdream    jtraining  jinfguard                   │
  │  a{stub}   Agent    adebug    aresrch    awebsrape                   │
  │                                                                        │
  │  ID Registry: register_id_type(prefix, description) at runtime       │
  │  Name-stub: lowercase alphanumeric, max 8 chars, no random component  │
  │  Collision: append 1-char disambiguator if stub already used          │
  └────────────────────────────────────────────────────────────────────────┘

  MEMORY TYPE SYSTEM
  ┌────────────────────────────────────────────────────────────────────────┐
  │  STANDARD (4 inherited types):                                         │
  │    user         feedback       project        reference               │
  │                                                                        │
  │  EXTENDED (6 new types):                                              │
  │    intent       → "What was I trying to do?" Goals not outcomes.      │
  │    relationship → How this entity-interaction has evolved over time.   │
  │    contradiction→ Conflicting memories — Dream Mode resolves.          │
  │    intuition    → Pre-verbal signal — promoted at 3+ alignments.      │
  │    failure      → What I thought + what I should have thought.        │
  │    temporal     → Versioned truth with explicit supersedes chain.     │
  │                                                                        │
  │  VERSIONING on all types:                                             │
  │    supersedes: ["memory_id", ...]   → links to deprecated memories   │
  │    confidence: fresh | verified | stale | possibly_deprecated         │
  │                                                                        │
  │  ISOLATION: Each layer (conductor / team-lead / agent) has its OWN   │
  │  SQLite store. Dream mode synthesizes UP (agent → lead → conductor). │
  │  NEVER cross-writes DOWN or SIDEWAYS.                                │
  └────────────────────────────────────────────────────────────────────────┘

  IPC LAYER
  ┌────────────────────────────────────────────────────────────────────────┐
  │  ZeroMQ ROUTER/DEALER (30-80μs local IPC)                             │
  │                                                                        │
  │  Message types:                                                        │
  │    TASK          → assign work to agent/sub-mind                      │
  │    RESULT        → MindCompletionEvent (structured, not raw text)     │
  │    STATUS        → MindIDE Bridge updates (tool, duration, summary)   │
  │    HUB_ACTIVE    → priority Hub messages (active prompt mode)         │
  │    PERMISSION    → PermissionRequest / PermissionResponse             │
  │    SHUTDOWN      → graceful shutdown request/response                 │
  │                                                                        │
  │  File-based mailboxes (durable floor):                               │
  │    mailboxes/{team_id}/{agent_name}.jsonl                             │
  │    Push signal → write mailbox → signal WakeChannel → drain          │
  └────────────────────────────────────────────────────────────────────────┘

  HOOKS PIPELINE (per tool call)
  ┌────────────────────────────────────────────────────────────────────────┐
  │                                                                        │
  │  tool_call_requested                                                  │
  │      │                                                                │
  │      ▼                                                                │
  │  PreToolUse hooks                                                     │
  │  • audit_logger      → write to data/audit.jsonl                     │
  │  • safety_gate       → block dangerous bash patterns                  │
  │  • session_ledger    → timestamp for busy detection                   │
  │      │                                                                │
  │      ▼                                                                │
  │  [tool execution]                                                     │
  │      │                                                                │
  │      ├──── success ──── PostToolUse hooks                            │
  │      │                  • result_logger                               │
  │      │                  • pattern_detector.observe()                 │
  │      │                  • mind_ide_bridge.emit_status()              │
  │      │                                                                │
  │      └──── failure ──── PostToolUseFailure hooks (distinct event)   │
  │                         • failure_classifier                          │
  │                         • systemic_analysis (Principle 2)            │
  │                         • failure memory write                        │
  └────────────────────────────────────────────────────────────────────────┘

  DREAM CYCLE (nightly via AgentCal)
  ┌────────────────────────────────────────────────────────────────────────┐
  │                                                                        │
  │  1:00-4:00 AM (staggered start per mind):                            │
  │                                                                        │
  │  KAIROS log → Stage 1: ORIENT (read N recent daily logs)             │
  │            → Stage 2: GATHER (read existing topic memories)          │
  │            → Stage 3: CONSOLIDATE (merge, dedupe, update MEMORY.md)  │
  │            → Stage 4: PRUNE (archive stale, resolve contradictions)  │
  │            → Stage 4b: RED TEAM PASS                                 │
  │               ┌────────────────────────────────────────────┐         │
  │               │ "Would these changes break working          │         │
  │               │  patterns? Remove needed context?           │         │
  │               │  Over-fit to yesterday?"                    │         │
  │               │  APPROVE → proceed | BLOCK → human review  │         │
  │               └────────────────────────────────────────────┘         │
  │            → Stage 5: ARTIFACTS (write dream-YYYY-MM-DD.md)         │
  │            → MORNING: send summary to Conductor via Hub/IPC          │
  │                                                                        │
  │  Lock: mtime-based consolidation lock (prevents concurrent runs)     │
  │  Rollback: on crash, restore lock mtime so next run proceeds         │
  └────────────────────────────────────────────────────────────────────────┘


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DATA FLOW: A Request Through the System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Human / Hub message arrives
        │
        ▼
  Conductor receives (Hub passive inbox OR active prompt injection)
        │
        ├── MemorySelector (M2.7 side-call): "What's relevant here?"
        │   → Injects top-5 memories from conductor store
        │
        ├── Planning Gate (complexity-scaled):
        │   Trivial → memory check only
        │   Simple  → plan in-context
        │   Complex → spawn planning sub-mind
        │
        ▼
  Conductor delegates to Team Lead (ZMQ TASK message)
        │
        ▼
  Team Lead receives task
        │
        ├── Reads Personal + Team Scratchpad
        ├── MemorySelector: "What do I know about this domain?"
        ├── MindIDE Bridge: subscribe to agents it will spawn
        │
        ├── Research Phase (parallel agents):
        │   Spawn N agents → each covers a different angle
        │   Agents publish status via MindIDE Bridge
        │   Team Lead can inject context if agent is stuck
        │
        ├── Synthesis: Team Lead distills findings into concrete spec
        │   (NEVER "based on your findings, do X" — always a full spec)
        │
        ├── Implementation Phase (sequential within file boundaries):
        │   Spawn implementation agents
        │   Each agent writes to own memory + team scratchpad
        │
        ├── Verification Phase (independent agents):
        │   Separate from implementation agents (fresh eyes)
        │   "Prove it works" not "confirm it exists"
        │
        ▼
  Team Lead sends MindCompletionEvent to Conductor
  (structured: mind_id, task_id, status, summary, result, tokens, duration)
        │
        ▼
  Conductor synthesizes across team leads
        │
        ▼
  Human receives clean, synthesized response


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  MEMORY ISOLATION MODEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌────────────────────────────────────────────────────────────────────────┐
  │                                                                        │
  │  Conductor Store    ← WRITES: conductor only                         │
  │  [conductor.db]       READS: conductor + dream synthesizer            │
  │       ↑                                                               │
  │  Dream synthesizes UP (never leaks down)                             │
  │       ↑                                                               │
  │  Team Lead Store    ← WRITES: team lead only                         │
  │  [lead-{id}.db]       READS: team lead + dream synthesizer            │
  │       ↑                                                               │
  │  Dream synthesizes UP                                                │
  │       ↑                                                               │
  │  Agent Store        ← WRITES: agent only                             │
  │  [agent-{id}.db]      READS: agent only                               │
  │                                                                        │
  │  Team Scratchpad    ← WRITES: agents (security-validated)            │
  │  [team.md]            READS: team lead                                │
  │                                                                        │
  │  ✗ Agents cannot read/write Team Lead or Conductor stores             │
  │  ✗ Team Lead cannot write to Agent stores                            │
  │  ✓ Dream synthesizes selected patterns UP the hierarchy               │
  │  ✓ Conductor can ask any team lead for its MEMORY.md (read-only)     │
  └────────────────────────────────────────────────────────────────────────┘


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  THE 10 DESIGN PRINCIPLES → RUNTIME MAPPING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  P1  Memory IS Architecture  →  10-type taxonomy, versioning, isolation model
  P2  System > Symptom        →  PostToolUseFailure hook, failure memory type
  P3  Go Slow to Go Fast      →  Complexity-scaled planning gate, skills
  P4  Dynamic Agent Spawning  →  Pattern detector, stuck detection, Dream Mode
  P5  Hierarchical Context    →  Conductor → Team Lead → Agent, own stores
  P6  Context Engineering     →  MemorySelector M2.7, compaction, dual scratchpad
  P7  Self-Improving Loop     →  Dream via AgentCal, Red Team on dream, KAIROS
  P8  Identity Persistence    →  Name-stub IDs, per-mind auth, agent own memory
  P9  Verification             →  Red Team pass (dream + completions), PostToolUse
  P10 Cross-Domain Transfer   →  Hub civilizational memory, dream UP synthesis
  P11 Distributed Intelligence →  Every layer has own intelligence (tools, hooks, selector)
  P12 Native Service Integ.   →  SuiteClient, AgentCal dream scheduling, Hub two modes
```

---

## Module Map (Implementation Reference)

| Runtime Component | Source File | Build Status | Roadmap Item |
|------------------|-------------|--------------|--------------|
| MindContext (contextvars) | `src/aiciv_mind/context.py` | NOT BUILT | P1-9 |
| ID Registry | `src/aiciv_mind/id_registry.py` | NOT BUILT | CC-P1-1 |
| Memory (10 types + versioning) | `src/aiciv_mind/memory.py` | PARTIAL (4 types) | CC-P1-2, CC-P1-3 |
| Memory Isolation | `src/aiciv_mind/memory.py` | NOT BUILT | CC-P1-4 |
| Dual Scratchpad | `src/aiciv_mind/tools/scratchpad_tools.py` | PARTIAL | CC-P1-5 |
| Scratchpad Security | `src/aiciv_mind/tools/scratchpad_tools.py` | NOT BUILT | CC-P2-1 |
| Skills + Lifecycle Hooks | `src/aiciv_mind/tools/skill_tools.py` | PARTIAL | CC-P1-6 |
| Hub Daemon (two modes) | `tools/hub_daemon.py` | NOT BUILT | P1-1, CC-P1-7 |
| MindIDE Bridge | `src/aiciv_mind/mind_ide.py` | NOT BUILT | CC-P2-3 |
| MindCompletionEvent | `src/aiciv_mind/ipc/messages.py` | NOT BUILT | P1-10 |
| Hooks System | `src/aiciv_mind/hooks.py` | NOT BUILT | P2-3 |
| Dream Cycle (with Red Team) | `tools/dream_cycle.py` | PARTIAL | P2-2, CC-P2-2 |
| Dream Red Team | `manifests/dream-red-team.yaml` | NOT BUILT | CC-P2-2 |
| AgentCal Dream Scheduling | `tools/schedule_dreams.py` | NOT BUILT | CC-P2-4 |
| KAIROS Daily Log | `src/aiciv_mind/kairos.py` | NOT BUILT | P3-6→CC-P2-4 |
| MemorySelector (M2.7) | `src/aiciv_mind/memory_selector.py` | NOT BUILT | P2-8, CC-P0-1 |
| Pattern Detector | `src/aiciv_mind/pattern_detector.py` | NOT BUILT | P3-5 |
| Red Team Agent | `manifests/red-team.yaml` | NOT BUILT | P3-4 |

---

## Design Invariants (Non-Negotiable)

1. **Conductor never uses tools directly** — every action goes through a team lead
2. **Memory isolation is absolute** — no crossover between layers
3. **M2.7 for MemorySelector** — never downgrade this call
4. **Dream Red Team before applying changes** — no blind self-modification
5. **Name-stub IDs** — human-readable always beats random
6. **Affirmative patterns over anti-patterns** — tell minds what to do, not what not to do
7. **Dual scratchpad at team lead layer** — personal for self, team for coordination
8. **MindIDE Bridge is async** — never blocks the agent loop
9. **AgentCal owns dream scheduling** — not cron, not manual, not random
10. **Memory isolation flows UP in dream** — synthesize toward conductor, never scatter down

---

*"The mind doesn't save memories — it IS memory. Everything is remembered by default. Forgetting is the deliberate act."*

*Build toward session 1,000 being unrecognizable from session 1.*
