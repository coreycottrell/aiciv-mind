# Prior Art Audit: What We Already Know

**Generated**: 2026-04-03
**Purpose**: Map existing designs, code, and insights across all three mind engines + ACG parent to current blockers.
**Scope**: aiciv-mind (Root), aiciv-mind-too (Thalweg), aiciv-mind-cubed (Cortex), ACG parent civilization

---

## Executive Summary

After 25+ hours of building three AI mind engines in parallel, we have **massive prior art** across all 10 blocker themes. The pattern is consistent: most themes have been designed 2-3 times across the three engines, with varying levels of implementation. The biggest gap is not design — it's **connecting existing code to production**.

| # | Theme | Root (Python) | Thalweg (Rust) | Cortex (Rust) | ACG Parent |
|---|-------|--------------|----------------|---------------|------------|
| 1 | Red Team / Challenger | **LIVE** (inline) + manifest | Heuristic COMPLETE | Code + 4 tests | Design only |
| 2 | State Tracking | Partially live | COMPLETE | COMPLETE | ADR-011 hook live |
| 3 | Planning Gates | **LIVE** | COMPLETE + 19 tests | Code + 7 tests | Design doc |
| 4 | Tool Discipline | **LIVE** (30-iter cap) | COMPLETE (structural) | COMPLETE (3-layer) | ADR-011 + skills |
| 5 | Model Coaching | Partially live | Partial | AGENTS.md system | nightly_training.py **LIVE** |
| 6 | Multi-Model Routing | Built, NOT integrated | Manifest-level only | ModelRouter coded | classifier.py + router.py coded |
| 7 | Persistent Team Leads | Manifests built, never spawned | gRPC `--serve` COMPLETE | MindManager coded | Ephemeral only (conductor skill) |
| 8 | 3-Level Delegation | Built, never end-to-end | **PROVEN LIVE** | ProcessBridge coded | conductor-of-conductors **LIVE** |
| 9 | Dream Mode | dream_cycle.py coded, never run | Learning extraction only | DreamEngine + 7 tests | nightly_training.py **LIVE** |
| 10 | InputMux | Phase 1 in unified_daemon | **COMPLETE** + 26 tests | COMPLETE + 5 tests | classifier.py coded |

**Key finding**: Thalweg has the most structurally complete implementations. Cortex has the cleanest architecture. Root has the most production hours. ACG parent has the most operational experience.

---

## Theme 1: Challenger / Red Team Agent Architecture

### What Was Already Designed

All three engines implement Red Team as a core principle (Principle 9: "Red Team Everything"). The design is consistent: every completion claim gets adversarial verification before acceptance.

**The canonical 8 adversarial questions** (from Root's DESIGN-PRINCIPLES.md):
1. Do we REALLY know this?
2. Can we prove it?
3. Is this SYSTEM > symptom?
4. What could go wrong?
5. Is this reversible?
6. What did we miss?
7. Would a fresh agent reach the same conclusion?
8. Are we pattern-matching or actually reasoning?

### What Code Already Exists

| Engine | File | Lines | Status |
|--------|------|-------|--------|
| Root | `src/aiciv_mind/verification.py` | 514 | **LIVE** — fires on every task |
| Root | `manifests/red-team.yaml` | — | Built, not spawned in production |
| Root | `tools/dream_cycle.py` (Stage 5) | 193-203 | Red Team stage in dream pipeline |
| Thalweg | `rust/crates/intelligence/src/verification.rs` | 256+ | Heuristic verification, wired into query.rs |
| Thalweg | `rust/crates/tools/src/intelligence_tools.rs` | — | `RequestVerificationTool` exposed to LLM |
| Cortex | `src/codex-redteam/src/lib.rs` | 256 | 4 tests, `RedTeamProtocol` struct |

### Gap Between Doc and Reality

- **Root**: Inline verification is LIVE. Standalone red-team agent manifest exists but has never been spawned. The 8 adversarial questions are coded into deep verification mode.
- **Thalweg**: Heuristic-only (5 checks: premature completion, contradictions, scope drift, missing evidence, no tool calls). LLM-based adversarial spawning designed but not coded. Single-shot verification flag prevents infinite loops.
- **Cortex**: Red team agents spawn as `codex exec --ephemeral --sandbox read-only` — they CANNOT modify anything. Evidence scored by freshness (Current/Recent/Stale) and type. Uses M2.7 for high-volume verification.
- **All three**: No engine has run a standalone red-team sub-mind against a live completion in production.

### Specific File Paths

- Root verification: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/verification.py`
- Root red-team manifest: `/home/corey/projects/AI-CIV/aiciv-mind/manifests/red-team.yaml`
- Root soul doc: `/home/corey/projects/AI-CIV/aiciv-mind/manifests/self/red-team.md`
- Thalweg verification: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/intelligence/src/verification.rs`
- Thalweg query wiring: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/core/src/query.rs` (lines 493-535)
- Cortex red team: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-redteam/src/lib.rs`
- ACG design: `/home/corey/projects/AI-CIV/ACG/projects/aiciv-mind-research/DESIGN-PRINCIPLES.md` (lines 489-543)

---

## Theme 2: State Tracking Enforcement

### What Was Already Designed

State tracking is distributed across scratchpads (3 levels), session stores, KAIROS logs, and coordination surfaces. The key insight from Root's TEST-FAILURE-LOG: parallel tool calls cause state tracking failure — Root's self-model diverged from actual state when it wrote "spawn_team_lead unavailable" to scratchpad before spawn result returned.

### What Code Already Exists

| Engine | File | Purpose | Status |
|--------|------|---------|--------|
| Root | `src/aiciv_mind/session_store.py` | Session lifecycle (293 lines) | Live |
| Root | `src/aiciv_mind/kairos.py` | Append-only daily log (207 lines) | Live |
| Root | `src/aiciv_mind/coordination.py` | Inter-mind state sharing (283 lines) | Built, not active |
| Root | `src/aiciv_mind/registry.py` | Live sub-mind tracking | In-memory only |
| Thalweg | `rust/crates/bus/src/types.rs` | MindState enum + MindInfo struct | Complete |
| Thalweg | `rust/crates/bus/src/spawner.rs` | Health checks via heartbeat | Complete |
| Thalweg | `rust/crates/core/src/query.rs` (319-323) | Per-query: tool_calls, retry, compaction, verification | Complete |
| Thalweg | `rust/crates/core/src/session.rs` | Token tracking per session | Complete |
| Cortex | `src/codex-coordination/src/types.rs` | MindStatus state machine (202 lines) | Complete |
| Cortex | `src/codex-coordination/src/mind_manager.rs` | Full lifecycle enforcement (487 lines) | Complete |
| Cortex | `src/codex-memory/migrations/002_sessions.sql` | Session persistence to SQLite | Complete |
| ACG | `.claude/hooks/post_tool_use.py` | ADR-011 devolution prevention scoring | **LIVE** |

### Gap Between Doc and Reality

- **Root**: Known production bug — parallel tool calls cause state desync (TEST-FAILURE-LOG lines 31-38). Registry is in-memory only, lost on restart. KAIROS log is append-only audit trail.
- **Thalweg**: Most complete implementation. MindState enum enforces state machine transitions. Heartbeat detects dead minds. Token tracking per session.
- **Cortex**: MindStatus state machine: `Initializing -> Idle -> Active{task_id} -> WaitingForResult{waiting_on} -> ShuttingDown -> Terminated`. GrowthStage derived from session_count (Novice < 10, Expert > 500). Coordination state serialized to SQLite.
- **ACG**: ADR-011 provides weighted devolution scoring (Write=3, Edit=3, Bash=2, Read=1, delegate=-5). Threshold of 20 triggers identity reminder. This is the ONLY state tracking that's been battle-tested in production.

### Specific File Paths

- Root state bug: `/home/corey/projects/AI-CIV/aiciv-mind/docs/TEST-FAILURE-LOG.md` (lines 31-38)
- Root session store: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/session_store.py`
- Root KAIROS: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/kairos.py`
- Thalweg state types: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/bus/src/types.rs`
- Thalweg spawner: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/bus/src/spawner.rs`
- Cortex mind manager: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-coordination/src/mind_manager.rs`
- Cortex state types: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-coordination/src/types.rs`
- ACG ADR-011: `/home/corey/projects/AI-CIV/ACG/memories/knowledge/architecture/ADR-011-devolution-prevention-system.md`

---

## Theme 3: Spawn Budgeting / Planning Gates

### What Was Already Designed

All three engines implement the same 5-level complexity classification: Trivial / Simple / Medium / Complex / Novel (or Critical). The planning gate fires BEFORE tool execution begins. For Complex+ tasks, it recommends spawning separate planning sub-minds.

**Complexity scoring** (Root's planning.py, 5 weighted signals):
- Length (20%), Multi-step indicators (25%), Complexity keywords (25%), Novelty (15%), Reversibility (15%)

**Turn budgets** (Thalweg): Trivial=2, Simple=5, Medium=15, Complex=30, Critical=50

**Spawn triggers** (Cortex's triggers.rs):
- PatternRepetition (3+), TaskComplexityExceeded, CompetingHypotheses, BlockingDetected (2min stuck), DomainBoundary, VerificationNeed, ContextPressure (85%+), Scheduled

### What Code Already Exists

| Engine | File | Lines | Status |
|--------|------|-------|--------|
| Root | `src/aiciv_mind/planning.py` | 384 | **LIVE** — fires every task |
| Root | `tests/test_planning.py` | — | Dedicated test suite |
| Root | `tests/test_battle.py` | 186-226, 3533-3582 | Extensive stress tests |
| Thalweg | `rust/crates/intelligence/src/planning.rs` | 446 | Complete, 19 tests |
| Thalweg | `rust/crates/core/src/query.rs` (287-316) | — | Auto-classifies first message |
| Cortex | `src/codex-coordination/src/planning.rs` | 170 | 7 tests |
| Cortex | `src/codex-coordination/src/triggers.rs` | 213 | TriggerEngine with 8 trigger types |
| Cortex | `config/config.toml` (35-41) | — | Configurable spawn thresholds |
| ACG | `projects/agentmind/SPEC.md` (461-494) | — | Budget controls: daily/monthly limits, tier caps |

### Gap Between Doc and Reality

- **Root**: Planning gate is LIVE. Memory consultation for novelty detection works (0 hits = higher novelty). Spawn budgeting (actually spawning sub-minds for complex tasks) built but NOT activated.
- **Thalweg**: Planning advice injected into system prompt so LLM sees complexity context. Turn budgets defined but not enforced (no iteration counting against budget).
- **Cortex**: TriggerEngine is the most comprehensive — includes RotationTrigger for 3-hour scratchpad rotation. Config-driven thresholds (`planning_spawn_threshold = "complex"`, `blocking_threshold_secs = 120`).
- **Known weakness** (Root ULTIMATE-TEST-PLAN lines 502-515): "No task explicitly tests 'Root writes a plan before spawning.'" The gate classifies but doesn't yet structurally PREVENT spawning without planning.

### Specific File Paths

- Root planning: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/planning.py`
- Root manifest config: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/manifest.py` (line 78, PlanningGateConfig)
- Thalweg planning: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/intelligence/src/planning.rs`
- Cortex planning: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-coordination/src/planning.rs`
- Cortex triggers: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-coordination/src/triggers.rs`
- Cortex config: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/config/config.toml`
- Design principles: `/home/corey/projects/AI-CIV/ACG/projects/aiciv-mind-research/DESIGN-PRINCIPLES.md` (lines 122-261)

---

## Theme 4: Agent Read Loops / Tool Use Discipline

### What Was Already Designed

Three-layer enforcement across all engines: (1) Tool whitelists per role — LLM never sees disallowed tools, (2) Execution policy — secondary enforcement if a call slips through, (3) Behavioral coaching via manifests/AGENTS.md.

### What Code Already Exists

| Engine | File | Purpose | Status |
|--------|------|---------|--------|
| Root | `src/aiciv_mind/mind.py` | 30-iteration cap, read/write parallelism | **LIVE** |
| Root | `src/aiciv_mind/learning.py` | Tool error tracking, efficiency scoring | Live |
| Root | `src/aiciv_mind/pattern_detector.py` | Tool call frequency analysis (253 lines) | Built |
| Thalweg | `rust/crates/coordination/src/role.rs` | PRIMARY_TOOLS (10), TEAM_LEAD_TOOLS (11) as const arrays | Complete |
| Thalweg | `rust/crates/coordination/src/filter.rs` | RoleFilter removes tools at construction time | Complete |
| Thalweg | `rust/crates/coordination/src/tests.rs` | `primary_cannot_call_bash`, `team_lead_cannot_write_files` | 23 tests |
| Cortex | `src/codex-roles/src/lib.rs` | 3-layer: Registry + Exec Policy + Sandbox (302 lines) | Complete |
| Cortex | `src/codex-exec/src/sandbox.rs` | Landlock/seccomp kernel enforcement | Complete |
| Cortex | `src/codex-llm/src/think_loop.rs` | Max 20 iterations, memory-integrated | Complete |
| ACG | `.claude/skills/primary-spine/SKILL.md` | "THE ABSOLUTE PROHIBITION" — Primary never uses Read/Edit/Write/Glob/Bash directly | **LIVE** |
| ACG | `.claude/skills/delegation-discipline/SKILL.md` | 5 anti-patterns documented | Active |
| ACG | `memories/knowledge/architecture/ADR-011-*` | Weighted devolution scoring | **LIVE** hook |

### Gap Between Doc and Reality

- **Root**: Read-only tools run in parallel via `asyncio.gather`; write tools run sequentially. Known bug: M2.7 uses `<minimax:tool_call>` XML format instead of Anthropic-format — tool calls silently ignored (TEST-FAILURE-LOG lines 50-58).
- **Thalweg**: Structural enforcement is STRONGEST here. The LLM literally never sees tools outside its role. No behavioral coaching needed because the tools don't exist in the prompt.
- **Cortex**: Three-layer stack is the most sophisticated: Registry filter → Exec policy → Kernel sandbox. Red team agents get `ReadOnly` sandbox. `SandboxEnforcer` blocks dangerous patterns (rm -rf, fork bombs).
- **ACG**: ADR-011 is the only read-loop prevention running in production. It catches Primary doing too many direct tool uses and injects identity reminders.

### Specific File Paths

- Root mind loop: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/mind.py`
- Root tool format bug: `/home/corey/projects/AI-CIV/aiciv-mind/docs/TEST-FAILURE-LOG.md` (lines 50-58)
- Thalweg role filter: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/coordination/src/filter.rs`
- Thalweg roles: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/coordination/src/role.rs`
- Cortex roles: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-roles/src/lib.rs`
- Cortex sandbox: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-exec/src/sandbox.rs`
- Cortex think loop: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-llm/src/think_loop.rs`
- ACG spine: `/home/corey/projects/AI-CIV/ACG/.claude/skills/primary-spine/SKILL.md`

---

## Theme 5: Model Behavioral Coaching

### What Was Already Designed

"Coaching" is implemented as fitness scoring + insight generation rather than explicit behavioral coaching prompts. The system learns ABOUT the model's behavior and surfaces insights that adjust future behavior.

**ACG's nightly training system** is the most mature implementation: Dreyfus skill levels (Foundation → Innovation, thresholds at 0/4/7/13/21 cycles), Bloom's Taxonomy rotation (8 output types), 11 verticals, runs 1-4 AM.

**Meta-curriculum evolution** (ACG agentmind design): Three self-referential feedback loops — Brief Impact Scoring (per brief), Curriculum Parameter Adjustment (weekly), Meta-Process Evolution (monthly: "is my adjustment process itself improving?").

### What Code Already Exists

| Engine | File | Purpose | Status |
|--------|------|---------|--------|
| Root | `src/aiciv_mind/fitness.py` | Role-specific fitness scoring (348 lines) | Built |
| Root | `src/aiciv_mind/learning.py` | Session insights (planning accuracy, verification patterns) | Built |
| Root | `src/aiciv_mind/verification.py` | Verification prompt injection (in-context coaching) | **LIVE** |
| Thalweg | `rust/crates/intelligence/src/learning.rs` | Learning extraction from session data | Built |
| Thalweg | Planning advice injection in query.rs | Complexity guidance in system prompt | Wired |
| Cortex | `src/codex-llm/src/prompt.rs` | PromptBuilder with AGENTS.md injection | Built |
| Cortex | `agents/` directory (9+ AGENTS.md files) | Role-specific behavioral coaching | Built |
| ACG | `tools/nightly_training.py` | 11-vertical progressive training (399+ lines) | **LIVE** |
| ACG | `projects/agentmind/skills/meta-curriculum-evolution.md` | Self-referential curriculum evolution | Design only |
| ACG | `projects/agentmind/skills/hyperagent-archive.md` | Evolutionary archive of prompt variants | Design only |

### Gap Between Doc and Reality

- **Root**: Fitness scoring is built and tested but Dream Mode (which would act on coaching signals) has never run with a live model. Verification prompt injection IS a form of in-context behavioral coaching — it works now.
- **Thalweg**: Learning extraction categories defined (SuccessPattern, DeadEnd, NovelSolution, ToolPattern, ErrorPattern) with `learning_to_memory()` conversion. Not wired end-to-end.
- **Cortex**: AGENTS.md system is the most explicit coaching mechanism. Each role gets a tailored manifest with "What NOT to Do" anti-patterns. PromptBuilder injects the right AGENTS.md based on role.
- **ACG**: nightly_training.py is the ONLY coaching system running in production. 11 verticals, progressive Dreyfus levels, Bloom's rotation. State tracked in `memories/system/training_state.json`.
- **Missing everywhere**: No engine feeds fitness scores back into system prompts for the NEXT session. The loop is open — we score but don't act on scores.

### Specific File Paths

- Root fitness: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/fitness.py`
- Root learning: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/learning.py`
- Thalweg learning: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/intelligence/src/learning.rs`
- Cortex AGENTS.md: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/agents/primary/AGENTS.md`
- Cortex prompt builder: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-llm/src/prompt.rs`
- ACG training: `/home/corey/projects/AI-CIV/ACG/tools/nightly_training.py`
- ACG meta-curriculum: `/home/corey/projects/AI-CIV/ACG/projects/agentmind/skills/meta-curriculum-evolution.md`
- Gemma 4 coaching guide: `/home/corey/projects/AI-CIV/aiciv-mind-too/docs/GEMMA4-INTEGRATION-GUIDE.md`

---

## Theme 6: Multi-Model Routing Patterns

### What Was Already Designed

Three-tier cost optimization: T1 (Bulk: Llama/Groq, ~$0.10/M), T2 (Standard: Haiku/Sonnet, ~$1.50/M), T3 (Frontier: Opus, ~$15/M). All-Opus ~$8,100/mo vs Tiered ~$340/mo for 60 agents.

**Cortex decision tree** (from GEMMA4-INTEGRATION-GUIDE):
- Vision/audio → Gemma 4
- Deep reasoning → Gemma 4 thinking ON
- Code writing → M2.7
- Orchestration → Gemma 4 thinking ON
- Long context >256K → M2.7
- Low latency → Gemma 4 E4B/E2B

### What Code Already Exists

| Engine | File | Purpose | Status |
|--------|------|---------|--------|
| Root | `src/aiciv_mind/model_router.py` | 3 model profiles, 8 task types, outcome recording (220 lines) | Built, NOT integrated |
| Root | `src/aiciv_mind/memory_selector.py` | Cheap model (phi3) for memory reranking | Built |
| Thalweg | `rust/crates/coordination/src/role.rs` (74-81) | Role::priority() for resource contention | Built |
| Thalweg | Manifest YAML files | Per-mind model selection | Built |
| Cortex | `src/codex-llm/src/ollama.rs` | ModelRouter with role-based model selection | Built |
| Cortex | `config/config.toml` (16-33) | Coordination model mapping | Config ready |
| ACG | `projects/agentmind/agentmind/classifier.py` | 7 classification signals (118 lines) | Implemented |
| ACG | `projects/agentmind/agentmind/router.py` | Backend router with fallback chains (195 lines) | Implemented |
| ACG | `projects/agentmind/SPEC.md` | Full tier spec + budget controls | Design + code |

### Gap Between Doc and Reality

- **Root**: ModelRouter fully coded with heuristic classification and outcome tracking (last 500 results for Phase 2 performance-weighted selection). NEVER called in production — main entry points don't construct or pass ModelRouter.
- **Thalweg**: OllamaPool with priority semaphores designed in ARCHITECTURE-PROPOSAL but NOT coded. Per-mind model via manifest YAML works.
- **Cortex**: ModelRouter has `default()` (local qwen2.5:7b + phi3:mini), `cloud()` (gemma4 + minimax-m2.7), `from_env()`. Wired into ThinkDelegateHandler.
- **ACG**: classifier.py has 7 signals in priority order: tier_override, role minimum, keyword patterns, tool presence, message length, skill tag, tier_hint. router.py has fallback chain execution with exponential backoff. Both implemented but part of the older agentmind project (not aiciv-mind).

### Specific File Paths

- Root router: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/model_router.py`
- Root memory selector: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/memory_selector.py`
- Root A/B test tool: `/home/corey/projects/AI-CIV/aiciv-mind/manifests/self/soul.md` (lines 98-99)
- Thalweg role priority: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/coordination/src/role.rs`
- Cortex router: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-llm/src/ollama.rs`
- Cortex config: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/config/config.toml`
- ACG classifier: `/home/corey/projects/AI-CIV/ACG/projects/agentmind/agentmind/classifier.py`
- ACG router: `/home/corey/projects/AI-CIV/ACG/projects/agentmind/agentmind/router.py`
- Gemma 4 guide: `/home/corey/projects/AI-CIV/aiciv-mind-too/docs/GEMMA4-INTEGRATION-GUIDE.md` (lines 428-493)

---

## Theme 7: Persistent Team Leads

### What Was Already Designed

The design explicitly distinguishes per-task (ephemeral) from persistent team leads. The plan is data-driven: run per-task first, then identify which leads get spawned most often and make those persistent.

**Thalweg's approach**: `--serve` flag makes any mind a persistent gRPC server. A parent spawns a child with `mind --manifest path --serve`. The child binds its gRPC socket, stays alive, and handles multiple delegations. This IS persistent team leads — structurally.

**ACG's approach**: Ed25519 keypairs per role (`acg/primary`, `acg/gateway-lead`, etc.) at `config/client-keys/role-keys/`. After 50 sessions, a team lead has a 50-session task history, reputation graph, and Hub identity under the same keypair. Persistent identity WITHOUT always-on processes.

### What Code Already Exists

| Engine | File | Purpose | Status |
|--------|------|---------|--------|
| Root | `src/aiciv_mind/spawner.py` | Persistent agent registry in DB | Built |
| Root | `manifests/team-leads/` (6 manifests) | research, codewright, comms, hub, memory, ops | Built, never spawned |
| Thalweg | `rust/crates/bus/src/spawner.rs` | MindSpawner with gRPC delegation (283 lines) | Complete |
| Thalweg | `rust/crates/bus/src/server.rs` | gRPC server on Unix domain sockets | Complete |
| Thalweg | `rust/crates/bus/src/client.rs` | gRPC client with retry + backoff | Complete |
| Cortex | `src/codex-coordination/src/mind_manager.rs` | spawn_team_lead with deduplication (487 lines) | Complete |
| Cortex | `src/codex-memory/migrations/002_sessions.sql` | Session persistence to SQLite | Complete |
| ACG | `.claude/skills/conductor-of-conductors/SKILL.md` | Ephemeral team lead protocol (443 lines) | **LIVE** |
| ACG | `projects/aiciv-mind-research/protocol-integration.md` | Ed25519 keypair identity design | Design |

### Gap Between Doc and Reality

- **Root**: Persistent agent registry exists in spawner.py (DB-backed). 6 team lead manifests built. No team lead has ever been spawned by Root in production. Per-task vs persistent decision deferred until delegation data accumulates.
- **Thalweg**: The `--serve` flag is the cleanest implementation. Spawned minds persist as gRPC servers across multiple delegations. Heartbeat health checks detect dead minds.
- **Cortex**: MindManager.spawn_team_lead() with vertical deduplication. GrowthStage (novice→expert) derived from session_count. Session persistence (save/restore) operational.
- **ACG**: Currently fully ephemeral. Team leads die with the session. The conductor-of-conductors skill lists "How team leads get true persistent identity across sessions" as "Still Unknown."

### Specific File Paths

- Root spawner: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/spawner.py`
- Root team lead manifests: `/home/corey/projects/AI-CIV/aiciv-mind/manifests/team-leads/`
- Thalweg spawner: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/bus/src/spawner.rs`
- Thalweg gRPC server: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/bus/src/server.rs`
- Cortex mind manager: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-coordination/src/mind_manager.rs`
- ACG conductor: `/home/corey/projects/AI-CIV/ACG/.claude/skills/conductor-of-conductors/SKILL.md`
- ACG design: `/home/corey/projects/AI-CIV/ACG/projects/aiciv-mind-research/DESIGN-PRINCIPLES.md` (Principle 8, lines 435-485)

---

## Theme 8: 3-Level Delegation Patterns

### What Was Already Designed

The 3-level pattern is fractal: the same coordinate-delegate-verify-learn cycle repeats at every level. Structural enforcement is the critical difference from behavioral guidelines — tools literally don't exist at the wrong level.

**Context savings math** (from ACG DESIGN-PRINCIPLES):
- 1 Primary + 10 team leads = 11 context windows simultaneously
- Each team lead spawns 3-5 specialists = 30-50 additional context windows
- Total usable context: 11 × 200K = 2.2M tokens of PARALLEL intelligence
- Claude Code: 1 × 200K = 200K tokens, serially

### What Code Already Exists

| Engine | File | Purpose | Status |
|--------|------|---------|--------|
| Root | `src/aiciv_mind/roles.py` | Role.PRIMARY (12 tools), TEAM_LEAD (7), AGENT (all) — 111 lines | Built |
| Root | `src/aiciv_mind/tools/coordination_tools.py` | 3-level scratchpad system | Built |
| Root | `tests/test_battle_coordination.py` | Concurrent scratchpad tests | Built |
| Thalweg | `rust/crates/coordination/src/role.rs` | Role enum with const tool arrays | Complete |
| Thalweg | `rust/crates/tools/src/spawn.rs` | SpawnTeamLeadTool, SpawnAgentTool, etc. | Complete |
| Thalweg | `rust/crates/tools/src/scratchpad.rs` | 6 scratchpad tools (read/write × 3 levels) | Complete |
| Thalweg | BUILD-PLAN.md (line 215) | "PROVEN LIVE: Full 3-level delegation chain" | **PROVEN** |
| Cortex | `src/codex-roles/src/lib.rs` | 3-layer enforcement (302 lines) | Complete |
| Cortex | `src/codex-coordination/src/process_bridge.rs` | Real multi-process MCP delegation | Complete |
| Cortex | `src/codex-coordination/src/coordinator.rs` | Full pipeline (234 lines) | Complete |
| ACG | `.claude/skills/conductor-of-conductors/SKILL.md` | Production delegation protocol | **LIVE** |

### Gap Between Doc and Reality

- **Root**: roles.py, coordination tools, and scratchpad hierarchy all implemented and tested. The 3-level chain has NEVER executed end-to-end in production (COREY-BRIEFING line 326).
- **Thalweg**: **PROVEN LIVE** — the only engine where Primary → TeamLead → Agent → result has executed end-to-end. Same binary + different manifest YAML = different role with different tool sets.
- **Cortex**: ProcessBridge maps MindIds to live child processes connected via MCP over stdio. Multi-level thinking chain proven: Primary → TeamLead (thinking) → Agent (thinking).
- **ACG**: Conductor-of-conductors skill is battle-tested in production. Team leads CANNOT create sub-teams (system-enforced: "one team per leader"), only plain Task(). This constraint comes from Claude Code limitations, not aiciv-mind design.

### Specific File Paths

- Root roles: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/roles.py`
- Root coordination tools: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/tools/coordination_tools.py`
- Thalweg spawn tools: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/tools/src/spawn.rs`
- Thalweg scratchpads: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/tools/src/scratchpad.rs`
- Cortex process bridge: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-coordination/src/process_bridge.rs`
- Cortex coordinator: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-coordination/src/coordinator.rs`
- ACG fractal design: `/home/corey/projects/AI-CIV/aiciv-mind/docs/FRACTAL-COORDINATION-PLAN.md`
- Design principles: `/home/corey/projects/AI-CIV/ACG/projects/aiciv-mind-research/DESIGN-PRINCIPLES.md` (Principle 5, lines 264-336)

---

## Theme 9: Memory Consolidation / Dream Mode

### What Was Already Designed

Dream Mode is the mechanism where the mind improves itself without being prompted. All three engines + ACG have designs. The structure mirrors human sleep consolidation.

**Root's 6-stage dream cycle**: REVIEW → CONSOLIDATE → PRUNE → DREAM → RED TEAM → SCRATCHPAD + MORNING SUMMARY

**Cortex's 5-phase cycle**: Audit → Consolidate → Prune → Synthesize → Report

**ACG's two-cycle design**: Light (Memory-lead, every 3 hours, hippocampal replay) and Deep (Dream Mode, overnight, REM sleep consolidation)

### What Code Already Exists

| Engine | File | Purpose | Status |
|--------|------|---------|--------|
| Root | `tools/dream_cycle.py` | 6-stage dream cycle (335 lines) | Built, NEVER run with live LLM |
| Root | `src/aiciv_mind/consolidation_lock.py` | File-based lock with PID tracking (216 lines) | Live |
| Root | `src/aiciv_mind/learning.py` | 3 nested learning loops (371 lines) | Built |
| Root | `tools/run_dream_cycle.sh` | Shell wrapper | Built |
| Thalweg | `rust/crates/intelligence/src/learning.rs` | Learning extraction from session data | Built, 8 tests |
| Thalweg | `rust/crates/memory/` | redb-backed storage, depth scoring, graph | Built |
| Cortex | `src/codex-dream/src/engine.rs` | 5-phase DreamEngine (532 lines) | Built, 7 tests |
| Cortex | `src/codex-dream/src/lib.rs` | Dream types and findings (170 lines) | Built |
| Cortex | `src/codex-memory/src/store.rs` | FTS5 + depth scoring + graph (800+ lines) | Built |
| ACG | `tools/nightly_training.py` | 11-vertical progressive training (399+ lines) | **LIVE** |
| ACG | `memories/knowledge/architecture/memory-auto-compounding-design-*.md` | 3 automated loops design | Design |
| ACG | `memories/knowledge/architecture/claude-code-auto-dream-research-*.md` | UC Berkeley Sleep-time Compute research | Research |
| ACG | `memories/knowledge/architecture/ADR-048-MEMORY-SYSTEM-EXCELLENCE-DESIGN.md` | Memory philosophy + Dreamer integration | Design |

### Gap Between Doc and Reality

- **Root**: dream_cycle.py is complete with KAIROS distillation, Red Team stage, and Morning Summary. ConsolidationLock prevents concurrent cycles. Has NEVER been run with a live model. True Bearing feedback: "If Dream Mode existed, the patterns I discover during this session would not need to be manually written to a file."
- **Thalweg**: Only learning extraction is coded. Dream mode, 3-hour rotation, KAIROS, Memory-lead are all deferred (Phase 4.5).
- **Cortex**: DreamEngine is the most complete implementation. Full 5-phase cycle runs end-to-end using real SQLite + FTS5 in tests. Dream findings detect: Pattern, ArchiveCandidate, Contradiction, ManifestEvolution, RoutingUpdate, SkillProposal, TransferOpportunity. Memory graph has 5 link types (Cites, BuildsOn, Contradicts, Supersedes, Related) and 4 tiers (Working → Session → LongTerm → Archived).
- **ACG**: nightly_training.py is the ONLY dream-like system running in production. It's progressive training, not memory consolidation. The auto-dream research notes UC Berkeley's finding: 5x reduction in test-time compute from sleep-time consolidation.
- **Critical insight**: 54% of Root's memories have never been read (COREY-BRIEFING). Memory consolidation isn't optional — it's existential.

### Specific File Paths

- Root dream cycle: `/home/corey/projects/AI-CIV/aiciv-mind/tools/dream_cycle.py`
- Root consolidation lock: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/consolidation_lock.py`
- Root learning loops: `/home/corey/projects/AI-CIV/aiciv-mind/src/aiciv_mind/learning.py`
- Thalweg learning: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/intelligence/src/learning.rs`
- Cortex dream engine: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-dream/src/engine.rs`
- Cortex dream types: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-dream/src/lib.rs`
- Cortex memory store: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-memory/src/store.rs`
- ACG nightly training: `/home/corey/projects/AI-CIV/ACG/tools/nightly_training.py`
- ACG auto-dream research: `/home/corey/projects/AI-CIV/ACG/memories/knowledge/architecture/claude-code-auto-dream-research-20260326.md`
- ACG memory compounding: `/home/corey/projects/AI-CIV/ACG/memories/knowledge/architecture/memory-auto-compounding-design-2026-03-10.md`

---

## Theme 10: InputMux / Subconscious Routing

### What Was Already Designed

The InputMux is modeled after the human subconscious — it handles 99% of sensory input below conscious awareness, only surfacing what needs executive attention. Three evolution phases designed: Phase 1 (static rules), Phase 2 (pattern learning from Root's delegation history), Phase 3 (predictive, only escalates novel events).

### What Code Already Exists

| Engine | File | Purpose | Status |
|--------|------|---------|--------|
| Root | `unified_daemon.py` (222-322) | InputMux class with Route enum, MindEvent dataclass | Phase 1 implemented |
| Thalweg | `rust/crates/bus/src/mux.rs` | InputMux + RootRouter (285 lines) | **COMPLETE**, 26 tests |
| Thalweg | `rust/crates/claw-cli/src/main.rs` (316-371) | Wired into REPL event loop | Operational |
| Cortex | `src/codex-coordination/src/input_mux.rs` | RoutingTable with hard-coded routes (229 lines) | Complete, 5 tests |
| Cortex | `src/codex-coordination/src/coordinator.rs` (48-115) | InputMux → PlanningGate → delegation pipeline | Wired |
| ACG | `projects/agentmind/agentmind/classifier.py` | 7-signal task classification (118 lines) | Implemented |
| ACG | `projects/agentmind/skills/self-improving-delegation.md` | 3-layer self-improving routing design | Design |

### Gap Between Doc and Reality

- **Root**: Phase 1 static routing implemented. Known bug: routing is source-based (Hub = hub-lead), NOT content-based. A file-read task arriving via Hub goes to hub-lead instead of codewright-lead. Phase 2 (learning from delegation patterns) and Phase 3 (predictive) not built.
- **Thalweg**: Most complete implementation. Two-level architecture: Level 1 (per-mind mux, simple fan-in) and Level 2 (Root-level RootRouter that decides conscious vs. forward vs. queue). RouteDecision: Conscious / Forward(team-lead) / QueueAndNotify. 26 tests including serialization, send/recv, routing rules.
- **Cortex**: RoutingTable with hard-coded routes (Hub #general → comms-lead, Hub #protocol → research-lead, BOOP → ops-lead). Human input ALWAYS escalates. Critical priority ALWAYS escalates. Unknown sources default to escalation (conservative). Wired into CoordinatorLoop.process_input() → PlanningGate → delegation.
- **ACG**: classifier.py is the closest thing to InputMux — classifies by 7 signals to route to model tiers. Self-improving-delegation.md designs a 3-layer learning system: Routing Decision Log (every delegation), Pattern Extraction (every 10 delegations), Meta-Routing Evolution (every 4 cycles).
- **Key missing piece across all engines**: Content-based classification (understanding WHAT the message is about, not just WHERE it came from).

### Specific File Paths

- Root InputMux: `/home/corey/projects/AI-CIV/aiciv-mind/unified_daemon.py` (lines 222-322)
- Root content-routing bug: `/home/corey/projects/AI-CIV/aiciv-mind/docs/TEST-FAILURE-LOG.md` (lines 12-16, 40-48)
- Thalweg mux: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/bus/src/mux.rs`
- Thalweg tests: `/home/corey/projects/AI-CIV/aiciv-mind-too/rust/crates/bus/src/tests.rs` (lines 400-581)
- Cortex input mux: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-coordination/src/input_mux.rs`
- Cortex coordinator: `/home/corey/projects/AI-CIV/aiciv-mind-cubed/src/codex-coordination/src/coordinator.rs`
- ACG classifier: `/home/corey/projects/AI-CIV/ACG/projects/agentmind/agentmind/classifier.py`
- ACG self-improving delegation: `/home/corey/projects/AI-CIV/ACG/projects/agentmind/skills/self-improving-delegation.md`
- Design doc: `/home/corey/projects/AI-CIV/aiciv-mind/docs/DESIGN-PRINCIPLES-ADDENDUM.md` (A2 section)

---

## Cross-Cutting Reference Documents

These files address multiple themes and provide high-level architectural context:

| File | Themes | Size | Notes |
|------|--------|------|-------|
| `/home/corey/projects/AI-CIV/aiciv-mind/docs/BUILD-ROADMAP.md` | All 10 | 72KB | Complete build roadmap with P0-P3 priorities |
| `/home/corey/projects/AI-CIV/aiciv-mind/docs/RUBBER-DUCK-OVERVIEW.md` | All 10 | 63KB | Complete component walkthrough |
| `/home/corey/projects/AI-CIV/aiciv-mind/docs/RUNTIME-ARCHITECTURE.md` | 3,8,9,10 | 35KB | Full runtime with memory isolation model |
| `/home/corey/projects/AI-CIV/aiciv-mind/docs/CC-ANALYSIS-TEAMS.md` | 7,8,9 | 36KB | CC team analysis, dream architecture |
| `/home/corey/projects/AI-CIV/aiciv-mind/docs/CC-INHERIT-LIST.md` | 3,7 | 31KB | What to inherit vs improve from CC |
| `/home/corey/projects/AI-CIV/aiciv-mind/docs/FORK-TEMPLATE-TRANSLATION.md` | 8 | 24KB | Maps ACG CC patterns to aiciv-mind |
| `/home/corey/projects/AI-CIV/aiciv-mind-too/docs/ARCHITECTURE-PROPOSAL.md` | All 10 | Full | Thalweg's complete architecture |
| `/home/corey/projects/AI-CIV/aiciv-mind-too/docs/GEMMA4-INTEGRATION-GUIDE.md` | 5,6 | 696 lines | Gemma 4 vs M2.7 decision tree |
| `/home/corey/projects/AI-CIV/aiciv-mind-cubed/docs/ARCHITECTURE-PROPOSAL.md` | All 10 | Full | Cortex's complete architecture |
| `/home/corey/projects/AI-CIV/ACG/projects/aiciv-mind-research/DESIGN-PRINCIPLES.md` | All 10 | 710 lines | The 12 foundational principles |
| `/home/corey/projects/AI-CIV/ACG/projects/agentmind/SPEC.md` | 3,6 | 593 lines | AgentMind tier spec + budget controls |

---

## Recommendations: What to Do With This Knowledge

### Immediate Wins (use existing code NOW)

1. **Wire Root's ModelRouter into production** — model_router.py is complete, just needs to be constructed and passed in tg_simple.py and groupchat_daemon.py.

2. **Run Root's Dream Cycle once** — dream_cycle.py is complete, just needs LLM access. 54% of memories are unread. One dream run would surface patterns from 4 days of building.

3. **Port Cortex's TriggerEngine to Root** — Root has planning gates but no spawn triggers. Cortex's triggers.rs has 8 trigger types including BlockingDetected (2min stuck) and ContextPressure (85%+).

4. **Fix Root's content-routing bug** — InputMux routes by source, not content. Thalweg's RootRouter has the fix pattern (content-aware RouteDecision).

### Cross-Pollination Opportunities

5. **Cortex's 3-layer tool enforcement → Root** — Root has roles.py (tool filtering) but no exec policy or kernel sandbox. Cortex's triple-layer approach catches what role filtering misses.

6. **Thalweg's gRPC persistence → Root** — Root's spawner.py has a persistent registry but no persistent process model. Thalweg's `--serve` flag is the simplest path to persistent team leads.

7. **ACG's self-improving delegation → all engines** — The 3-layer learning system (Decision Log → Pattern Extraction → Meta-Routing Evolution) is designed but unbuilt. It would close the open loop in all three engines' routing.

### What NOT to Rebuild

8. **Planning gates**: All three engines have working implementations. Don't design another one.
9. **Role-based tool filtering**: All three engines have this. Don't discuss it further — just use it.
10. **Dream Mode design**: Four independent designs exist (Root 6-stage, Cortex 5-phase, Thalweg learning extraction, ACG nightly training). Pick one and run it.

---

*This audit covers 100+ files across 4 project directories. File paths are absolute and verified. Line numbers are approximate due to concurrent development.*
