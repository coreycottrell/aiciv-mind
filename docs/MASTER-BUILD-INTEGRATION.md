# Master Build Integration: Prior Art → Production

**Generated**: 2026-04-03
**Source**: PRIOR-ART-AUDIT.md (10 themes across Root, Thalweg, Cortex, ACG parent)
**Purpose**: Authoritative reference for ALL builds. Nobody rebuilds what exists. Nobody starts from scratch when a port is available.

---

## How to Read This Document

For each of the 10 themes:
- **USE**: Existing code that works today — just call it
- **WIRE**: Code exists but isn't connected to production — needs plumbing
- **NEW**: Genuinely missing — must be written from scratch
- **BEST PORT**: Which engine has the strongest implementation to steal from

---

## Theme 1: Challenger / Red Team

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's verification.py (514 lines, 8 adversarial questions, 3 scrutiny levels) | `src/aiciv_mind/verification.py` | Already LIVE — fires every task |
| **USE** | Root's challenger.py (structural per-turn adversary, 4 detection patterns) | `src/aiciv_mind/challenger.py` | LIVE as of 2250de9 — catches premature completion, empty work, stall |
| **WIRE** | Root's red-team manifest (standalone adversarial sub-mind) | `manifests/red-team.yaml` + `manifests/self/red-team.md` | Spawn via `spawn_team_lead` for deep verification on COMPLEX tasks |
| **WIRE** | Dream cycle Stage 5 (Red Team stage) | `tools/dream_cycle.py` lines 193-203 | Run dream_cycle.py — red team stage is coded |
| **NEW** | Feed red-team results back into coaching signals | — | Close the loop: red-team findings → fitness.py → system prompt |
| **BEST PORT** | **Cortex** — `codex-redteam/src/lib.rs` (256 lines, 4 tests). Spawns `--ephemeral --sandbox read-only` agents. Evidence scored by freshness. Uses cheap model for high-volume. | Port pattern: spawn red-team as read-only sub-mind on complex completions |

**Refactoring debt**: challenger.py should fold INTO verification.py (acknowledged, not blocking).

---

## Theme 2: State Tracking Enforcement

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's session_store.py (293 lines, boot→record→shutdown lifecycle) | `src/aiciv_mind/session_store.py` | Already LIVE |
| **USE** | Root's KAIROS log (207 lines, append-only daily audit trail) | `src/aiciv_mind/kairos.py` | Already LIVE |
| **USE** | Root's state file auto-update (dot-notation key navigation) | `src/aiciv_mind/tools/spawn_tools.py` | LIVE as of 2250de9 — auto-updates evolution-status.json |
| **WIRE** | Root's coordination.py (inter-mind state sharing, 283 lines) | `src/aiciv_mind/coordination.py` | Built, not active. Wire into unified_daemon event loop |
| **WIRE** | Root's registry.py (in-memory only, lost on restart) | `src/aiciv_mind/registry.py` | Persist to DB — spawner.py already has DB-backed registry, connect them |
| **NEW** | Fix parallel tool call state desync | `src/aiciv_mind/mind.py` | Known bug: parallel writes cause state divergence (TEST-FAILURE-LOG lines 31-38) |
| **BEST PORT** | **Thalweg** — `bus/src/types.rs` MindState enum enforces state machine transitions. Heartbeat detects dead minds. Token tracking per session. **Cortex** — MindStatus state machine (Initializing→Idle→Active→WaitingForResult→ShuttingDown→Terminated) with GrowthStage from session_count. | Port Cortex's state machine enum into Root's registry.py |

---

## Theme 3: Spawn Budgeting / Planning Gates

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's planning.py (384 lines, 5-signal complexity classification) | `src/aiciv_mind/planning.py` | Already LIVE — fires every task |
| **USE** | Root's spawn budget (per-task limits scaled by complexity) | `src/aiciv_mind/tools/spawn_tools.py` | LIVE as of 2250de9 — trivial=1 through variable=8 |
| **WIRE** | Root's planning gate → spawn prevention | — | Gate classifies but doesn't PREVENT spawning without planning (ULTIMATE-TEST-PLAN lines 502-515) |
| **NEW** | Turn budget enforcement | — | Planning gate outputs complexity but doesn't enforce iteration limits per complexity |
| **BEST PORT** | **Thalweg** — `intelligence/src/planning.rs` (446 lines, 19 tests). Turn budgets: Trivial=2, Simple=5, Medium=15, Complex=30, Critical=50. **Cortex** — `triggers.rs` TriggerEngine with 8 trigger types (PatternRepetition, BlockingDetected 2min, ContextPressure 85%+). | Port Thalweg's turn budgets + Cortex's TriggerEngine |

**Refactoring debt**: Spawn budget should move from spawn_tools.py INTO planning.py (acknowledged, not blocking).

---

## Theme 4: Agent Read Loops / Tool Use Discipline

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's 30-iteration cap | `src/aiciv_mind/mind.py` | Already LIVE |
| **USE** | Root's read_loop_guard.py (WARN=3, BLOCK=5, FORCE_STOP=10) | `src/aiciv_mind/read_loop_guard.py` | LIVE as of 2250de9, wired into _execute_one_tool |
| **USE** | Root's pattern_detector.py (253 lines, tool call frequency analysis) | `src/aiciv_mind/pattern_detector.py` | Built, detecting bigram/trigram/error/slow/dominant patterns |
| **USE** | Root's roles.py (tool filtering by role, 111 lines) | `src/aiciv_mind/roles.py` | Built — PRIMARY=12, TEAM_LEAD=7, AGENT=all |
| **WIRE** | Pattern detector findings → coaching signals | — | pattern_detector runs but findings aren't fed back into prompts |
| **NEW** | Content-based classification of tool calls (understand WHAT, not just count) | — | All engines do frequency analysis; none understand intent |
| **BEST PORT** | **Thalweg** — `coordination/src/filter.rs` RoleFilter removes tools at construction time (LLM never sees disallowed tools). **Cortex** — 3-layer: Registry + ExecPolicy + Landlock/seccomp kernel sandbox. | Root already has role filtering; port Cortex's exec policy as 2nd layer |

**Refactoring debt**: read_loop_guard.py should fold INTO pattern_detector.py (acknowledged, not blocking).

---

## Theme 5: Model Behavioral Coaching

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's verification.py (in-context coaching via challenge injection) | `src/aiciv_mind/verification.py` | Already LIVE |
| **USE** | Root's fitness.py (role-specific fitness scoring, 348 lines) | `src/aiciv_mind/fitness.py` | Built, scores generated |
| **USE** | Root's learning.py (3 nested learning loops, 371 lines) | `src/aiciv_mind/learning.py` | Built |
| **WIRE** | Fitness scores → system prompt for next session | — | Loop is OPEN: we score but don't act on scores |
| **WIRE** | Dream cycle → coaching consolidation | `tools/dream_cycle.py` | Dream cycle coded, never run. Would generate coaching insights |
| **NEW** | Closed-loop coaching: fitness_score → prompt_adjustment → measure_improvement | — | No engine has this end-to-end |
| **BEST PORT** | **ACG** — `nightly_training.py` (399+ lines, LIVE, 11 verticals, Dreyfus levels, Bloom's rotation). **Cortex** — AGENTS.md per-role coaching with "What NOT to Do" anti-patterns injected via PromptBuilder. | ACG's nightly training is the only coaching running in production. Port Cortex's anti-pattern injection as quick win. |

---

## Theme 6: Multi-Model Routing

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's model_router.py (220 lines, 3 profiles, 8 task types, outcome recording) | `src/aiciv_mind/model_router.py` | Built, tested |
| **USE** | Root's memory_selector.py (cheap model for memory reranking) | `src/aiciv_mind/memory_selector.py` | Built |
| **WIRE** | ModelRouter into mind.py main loop | — | **NEVER called in production**. Needs to be constructed and passed in. BUILD-ROADMAP P2-5 says "BUILT" but verify wiring. |
| **WIRE** | Manifest-level model selection | `manifests/*.yaml` | Each manifest specifies model but router can override |
| **NEW** | Performance-weighted model selection (Phase 2 of router) | — | Router tracks last 500 outcomes but doesn't use them for selection yet |
| **BEST PORT** | **Cortex** — `codex-llm/src/ollama.rs` ModelRouter with role-based selection, wired into ThinkDelegateHandler. **ACG** — `agentmind/classifier.py` 7 signals + `router.py` fallback chains. | Port ACG's 7-signal classifier into Root's model_router.py |

---

## Theme 7: Persistent Team Leads

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's spawner.py (persistent agent registry in DB, 173 lines) | `src/aiciv_mind/spawner.py` | Built |
| **USE** | Root's 6 team lead manifests | `manifests/team-leads/` | Built, never spawned in production |
| **WIRE** | Spawn team leads from manifests on complex tasks | — | Manifests exist, spawner works, but Root never delegates to team leads automatically |
| **NEW** | Persistent process model (team leads survive across tasks) | — | Currently all sub-minds are per-task ephemeral |
| **NEW** | Session continuity (restore team lead context from prior sessions) | — | Cortex has SQLite session persistence; Root doesn't |
| **BEST PORT** | **Thalweg** — `bus/src/spawner.rs` + `bus/src/server.rs`. `--serve` flag makes any mind a persistent gRPC server. Heartbeat health checks. This IS persistent team leads structurally. | Port Thalweg's `--serve` pattern: spawned mind binds socket, stays alive, handles multiple delegations |

---

## Theme 8: 3-Level Delegation

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's roles.py (PRIMARY=12 tools, TEAM_LEAD=7, AGENT=all) | `src/aiciv_mind/roles.py` | Built |
| **USE** | Root's coordination_tools.py (3-level scratchpad system) | `src/aiciv_mind/tools/coordination_tools.py` | Built |
| **USE** | Root's spawn_tools.py (spawn_team_lead + spawn_agent) | `src/aiciv_mind/tools/spawn_tools.py` | LIVE — proven in Phase 0-3 evolution test |
| **WIRE** | End-to-end Primary → TeamLead → Agent chain | — | Never executed in production (COREY-BRIEFING line 326). Evolution test proved it works. |
| **NEW** | Nothing genuinely new needed | — | All 3-level code exists and is tested |
| **BEST PORT** | **Thalweg** — **PROVEN LIVE**. Same binary + different manifest YAML = different role. This is the reference implementation. | Root's Python version works (proven in tests). Just run it in production. |

---

## Theme 9: Memory Consolidation / Dream Mode

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's dream_cycle.py (6-stage, 335 lines) | `tools/dream_cycle.py` | Built, NEVER run with live LLM |
| **USE** | Root's consolidation_lock.py (file-based lock, 216 lines) | `src/aiciv_mind/consolidation_lock.py` | Built |
| **USE** | Root's learning.py (3 nested learning loops, 371 lines) | `src/aiciv_mind/learning.py` | Built |
| **WIRE** | Run dream_cycle.py with live model access | — | Just needs LLM access. 54% of memories never read. One run would surface 4 days of patterns. |
| **WIRE** | KAIROS integration with dream cycle | `src/aiciv_mind/kairos.py` | KAIROS logs daily; dream cycle reads KAIROS. Both exist, connection not tested. |
| **NEW** | Automated dream scheduling (cron or daemon-triggered) | — | Manual-only currently |
| **BEST PORT** | **Cortex** — `codex-dream/src/engine.rs` (532 lines, 7 tests). 5-phase cycle with 7 finding types (Pattern, ArchiveCandidate, Contradiction, ManifestEvolution, RoutingUpdate, SkillProposal, TransferOpportunity). Memory graph with 5 link types and 4 tiers. | Port Cortex's DreamEngine finding types into Root's dream_cycle.py |

---

## Theme 10: InputMux / Subconscious Routing

| Category | What | File | Action |
|----------|------|------|--------|
| **USE** | Root's InputMux Phase 1 (static routing) | `unified_daemon.py` lines 222-322 | LIVE in production |
| **WIRE** | Content-based routing (fix source-only bug) | — | Known bug: routes by source (Hub→hub-lead) not content. File-read task via Hub goes to wrong lead. |
| **NEW** | Phase 2: Learn from delegation patterns | — | Design exists (ACG self-improving-delegation.md), no code |
| **NEW** | Phase 3: Predictive routing (only escalate novel events) | — | Pure design, no code anywhere |
| **BEST PORT** | **Thalweg** — `bus/src/mux.rs` (285 lines, 26 tests). Two-level: per-mind mux + Root-level RootRouter. RouteDecision: Conscious/Forward(team-lead)/QueueAndNotify. Content-aware. | Port Thalweg's RootRouter for content-aware routing. Fix Root's source-only bug. |

---

## Priority Matrix: What to Do First

### Immediate (zero new code — just wire or run existing)

| # | Action | Theme | Effort |
|---|--------|-------|--------|
| 1 | **Run dream_cycle.py once** with live LLM | 9 | 30min — just needs model access |
| 2 | **Verify ModelRouter wiring** in mind.py main loop | 6 | 1h — BUILD-ROADMAP says "BUILT" |
| 3 | **Run 3-level delegation in production** | 8 | Already proven in evolution test — deploy |
| 4 | **Connect registry.py to spawner.py DB** | 2 | 1h — both exist, just not connected |

### Short-term (port existing code)

| # | Action | Theme | Source | Effort |
|---|--------|-------|--------|--------|
| 5 | **Port Thalweg turn budgets** into planning.py | 3 | `intelligence/src/planning.rs` | 2h |
| 6 | **Port Cortex TriggerEngine** (8 spawn triggers) | 3 | `coordination/src/triggers.rs` | 3h |
| 7 | **Fix content-routing bug** using Thalweg's RootRouter pattern | 10 | `bus/src/mux.rs` | 2h |
| 8 | **Port Cortex exec policy** as 2nd enforcement layer | 4 | `codex-roles/src/lib.rs` | 3h |

### Medium-term (new code needed)

| # | Action | Theme | Effort |
|---|--------|-------|--------|
| 9 | **Close coaching loop** (fitness → prompt → measure) | 5 | 4-8h |
| 10 | **Persistent team lead process model** | 7 | 8-16h (port Thalweg --serve) |
| 11 | **InputMux Phase 2** (learn from delegation patterns) | 10 | 8h |
| 12 | **Fix parallel tool call state desync** | 2 | 4h |

### Do NOT Rebuild

- Planning gates (3 implementations exist)
- Role-based tool filtering (3 implementations exist)
- Dream mode design (4 designs exist — pick one and run it)
- Red team questions (canonical 8 already in verification.py)
- Memory storage (SQLite+FTS5 working in Root, redb in Thalweg, SQLite in Cortex)

---

## Cross-Reference: Prior Art Audit → BUILD-ROADMAP Items

| Audit Theme | BUILD-ROADMAP Items | Status |
|-------------|-------------------|--------|
| 1. Challenger | P3-4 (Red team manifest) | BUILT |
| 2. State Tracking | P0-3 (Session topics), P0-5 (Orphaned sessions), P2-4 (Persistent registry) | ALL BUILT |
| 3. Planning Gates | P3-5 (Pattern detection) | BUILT |
| 4. Tool Discipline | P0-0 (M2.7 pinning), P3-5 (Pattern detection) | BUILT |
| 5. Model Coaching | P2-2 (Dream mode), P3-6 (KAIROS) | BUILT |
| 6. Multi-Model | P2-5 (Model router) | BUILT — verify wiring |
| 7. Persistent TLs | P3-1 (Team leads) | BUILT (manifests only) |
| 8. 3-Level Delegation | P1-6 (Spawner tests) | BUILT — proven in evolution test |
| 9. Dream Mode | P2-2 (Dream mode), P3-6 (KAIROS) | BUILT — never run live |
| 10. InputMux | (not in BUILD-ROADMAP) | Phase 1 in unified_daemon |

---

*This document is the authoritative reference for what exists, what needs wiring, and what needs building. Read this before writing ANY new code for aiciv-mind.*
