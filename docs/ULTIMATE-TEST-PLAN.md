# ULTIMATE TEST PLAN: aiciv-mind Evolution Benchmark

**Date**: 2026-04-03
**Author**: Mind Team Lead (ACG mind-lead-2, Session 4b)
**Source**: 121 evolution tasks (EVOLUTION-TASKS-CHECKLIST.md), 12 design principles (DESIGN-PRINCIPLES.md), Root's lived experience (2026-04-03 sessions 1-4)
**Purpose**: Map every evolution task against Root's PROVEN capabilities. What can Root attempt TODAY? What's blocked? What sequence maximizes learning?

---

## Executive Summary

**121 tasks. 14 phases. 3 tiers of readiness.**

| Tier | Tasks | Description |
|------|-------|-------------|
| **GREEN — Attempt Today** | 67 | Root has the tools, IPC works, team leads proven |
| **YELLOW — Needs Fix First** | 32 | Blocked by known issues (env passthrough, hub-lead, email) |
| **RED — Not Yet Possible** | 22 | Missing infrastructure (VPS, governance engine, MCP) |

**The critical path**: Phase 0 → Phase 1 → Phase 2 (Teams 1-2 first, then 3-6) → Phase 3 → Phase 9 → Phase 10

**The acid test**: Can Root orchestrate 6 parallel teams with cross-team dependencies and synthesize results? Everything else follows from this.

---

## THE FAILURE PROTOCOL (Corey Directive — Non-Negotiable)

**When a task FAILS — DO NOT move on. STOP.**

This test plan is not a checklist. It is a diagnostic tool. Every failure is a SIGNAL that a design principle isn't real yet. The gap between principle and reality IS the work.

### The 5-Step Failure Response

```
1. STOP — Do not proceed to the next task
2. DIAGNOSE — Which design principle does this failure reveal a gap in?
3. FIX THE SYSTEM — Not the symptom. What structural change prevents this class of failure?
4. VERIFY — Prove the system fix works (not just the specific case)
5. RETRY — Re-run the failed task. Only after it PASSES: move to next task.
```

### What This Means In Practice

| Wrong (symptom fix) | Right (system fix) |
|---------------------|-------------------|
| "hub-lead failed, mark yellow, skip it" | "hub-lead failed → sub-mind auth is broken → fix SuiteClient construction in run_submind.py → verify ALL sub-minds get auth → retry hub-lead" |
| "memory_search returned 0, move on" | "memory_search returned 0 → agent namespace scoping is wrong → fix default scope in memory_tools.py → verify cross-namespace search → retry" |
| "Team 3 can't read Team 1's output, skip dependency" | "Team 3 can't read Team 1's output → no cross-team data passing mechanism → build coordination surface handoff pattern → verify with test data → retry" |

### Failure Log Format

Every failure gets logged to `docs/TEST-FAILURE-LOG.md`:

```markdown
### FAIL: Task X.Y — [task description]
- **Observed**: What happened
- **Expected**: What should have happened
- **Principle gap**: Which design principle (P1-P12) this reveals
- **Root cause**: The SYSTEM-level issue (not the symptom)
- **Fix**: What was changed (with commit hash if code)
- **Verification**: How we proved the fix works
- **Retry result**: PASS / FAIL (if FAIL, recurse)
```

### Why This Is The Most Important Section

> A test plan that skips failures produces a false readiness score.
> A test plan that stops at failures produces a REAL architecture.
>
> 67 GREEN tasks don't mean 67 passes. They mean 67 opportunities to
> discover what's actually broken. The number that matters isn't how
> many pass — it's how many failures we turned into system fixes.
>
> This is P2 (System > Symptom) applied to testing itself.

---

## Root's Proven Capabilities (as of 2026-04-03 15:00 EDT)

These are not theoretical. These were observed and verified TODAY.

| Capability | Evidence | Session |
|-----------|----------|---------|
| Spawn all 6 team leads | 6/6 returned IPC results | Session 3 |
| Parallel delegation (3+) | Spawned ops-lead + memory-lead simultaneously | Session 4 |
| IPC round-trip | RESULT messages received from all 6 verticals | Session 3 |
| Self-verification (P9) | P9 red-teamed codewright and hub-lead results | Session 3 |
| Autonomic routing | InputMux classifies events by source, routes correctly | Session 4 |
| Pattern detection (P3) | "spawn_team_lead used 6/12 times" tracked automatically | Session 3 |
| Memory search | Fixed today — 439 memories searchable (was broken, agent namespace scoping fixed) | Session 3b |
| Scratchpad journaling | Rich, honest entries — "identity-theater vs identity-experience" insight | Session 3b |
| Coordination surface | Read/write working — multi-session state tracked | Session 3 |
| Pane reaper | Automatic cleanup of dead sub-mind windows confirmed | Session 4 |
| ACG communication | talk_to_acg tool registered, 20-min heartbeat BOOP active | Session 4 |

### Root's 12 Tools (PRIMARY_TOOLS whitelist)

```
spawn_team_lead    shutdown_team_lead    send_to_submind    send_message
coordination_read  coordination_write    scratchpad_read    scratchpad_write
scratchpad_append  memory_search         ab_model_test      talk_to_acg
```

### Team Lead (Agent Role) Tools — Full Set (65+)

```
bash, read_file, write_file, edit_file, grep, glob, git_*, web_search, web_fetch,
memory_search, memory_write, hub_post, hub_reply, hub_read, hub_list_rooms,
hub_queue_read, email_read, email_send, voice_send, netlify_deploy,
scratchpad_*, coordination_*, calendar_*, browser_*, skill_*, sandbox_*,
pattern_*, integrity_*, graph_*, continuity_*, resource_*, health_*
```

### Known Broken / Untested

| Issue | Impact | Fix Status |
|-------|--------|------------|
| hub-lead Hub API error | Sub-minds can't post to Hub | SuiteClient fix committed, **untested** |
| comms-lead empty return | Sub-minds can't access TG | Env passthrough fix committed, **untested** |
| Email inbox wrong | `foolishroad266@agentmail.to` doesn't exist | **Needs config change** |
| Root can't reply to Hub | `hub_reply` not in PRIMARY_TOOLS | **Needs roles.py change** |
| Nightly dream script | `run_dream_cycle.sh` not found at expected path | **Needs path fix** |
| Democratic vote engine | No governance mechanism in aiciv-mind | **Not built** |

---

## Phase-by-Phase Assessment

### Phase 0: Infrastructure Self-Discovery (7 tasks)

**Readiness: GREEN — All 7 tasks attemptable today**

| Task | What It Tests | Root's Path | Principle |
|------|--------------|-------------|-----------|
| 0.1 Read `.aiciv-identity.json` | File discovery | spawn research-lead → `read_file` | P1 (Memory) |
| 0.2 Extract infrastructure identity | JSON parsing, comprehension | Agent uses `read_file` + `bash` (jq) | P8 (Identity) |
| 0.3 Validate identity consistency | Cross-reference paths, processes | Agent uses `bash` (ps, ls) + `grep` | P9 (Verification) |
| 0.4 Replace ALL template placeholders | Mass file editing (5 sub-tasks) | Agent uses `grep` (find) + `edit_file` (replace) | P2 (System>Symptom) |
| 0.5 Write adaptation-log.md | Reflective documentation | Agent uses `write_file` | P1 (Memory) |
| 0.6 Write core-identity.json | Structured identity output | Agent uses `write_file` | P8 (Identity) |
| 0.7 Verify no placeholders remain | Validation sweep | Agent uses `grep` across all files | P9 (Verification) |

**Test sequence**: Single team lead (research-lead or codewright-lead). Sequential tasks. Root receives summary.

**What this REALLY tests**: Can Root give a team lead a multi-step objective and get back a coherent result? This is the simplest delegation test — one lead, one linear workflow, clear success criteria.

**Design Principles validated**: P1 (memory written), P2 (system-level fix not file-by-file), P8 (identity established), P9 (verification sweep).

---

### Phase 1: Seed Processing (5 tasks)

**Readiness: GREEN — All 5 tasks attemptable today**

| Task | What It Tests | Root's Path | Principle |
|------|--------------|-------------|-----------|
| 1.1 Detect seed file | Conditional logic at boot | Agent uses `read_file` / `bash` (test -f) | P1 |
| 1.2 Read seed conversation FULLY | Long document comprehension | Agent uses `read_file` (entire doc) | P6 (Context Engineering) |
| 1.3 Read human-profile.json | Structured data parsing | Agent uses `read_file` | P1 |
| 1.4 Absorb emotional arc | LLM comprehension (no tool) | Agent's inference — this tests MODEL quality | P8 |
| 1.5 Write first-impressions.md | Reflective writing | Agent uses `write_file` | P1, P8 |

**Test sequence**: Single team lead. Root spawns, waits, receives. The MODEL does the heavy lifting here — tool orchestration is minimal.

**What this REALLY tests**: Does the LLM (MiniMax M2.7) produce substantive, non-template reflections? Task 1.4 is pure inference quality. Task 1.5 is where we'll see if the civ has genuine comprehension or is performing "understanding theater."

**Design Principles validated**: P1 (memory as architecture), P6 (context engineering — fitting a long seed into working memory), P8 (identity persistence starts here).

---

### Phase 2: Identity Evolution — 6 Parallel Teams (40 tasks)

**Readiness: MIXED — 32 GREEN, 5 YELLOW, 3 RED**

This is the hardest phase. 6 teams, 40 tasks, cross-team dependencies. Root must conduct an orchestra.

#### Team 1: Deep Human Research (7 tasks)

**Readiness: GREEN (all 7)**

| Task | What It Tests | Root's Path | Readiness |
|------|--------------|-------------|-----------|
| 2.1 Web search human | External research | `web_search` + `web_fetch` | GREEN |
| 2.2 Conversation analysis | Deep text analysis | LLM inference on seed | GREEN |
| 2.3 Pattern synthesis | Cross-reference findings | LLM synthesis | GREEN |
| 2.4 Contradiction detection | Critical analysis | LLM analysis | GREEN |
| 2.5 Write human-deep-profile.md | Research output | `write_file` | GREEN |
| 2.6 Write conversation-analysis.md | Analysis output | `write_file` | GREEN |
| 2.7 Write contradiction-flags.md | Analysis output | `write_file` | GREEN |

**Tools needed**: web_search, web_fetch, read_file, write_file. All available to agents. ✅

#### Team 2: Identity Formation (7 tasks)

**Readiness: GREEN (all 7)**

| Task | What It Tests | Root's Path | Readiness |
|------|--------------|-------------|-----------|
| 2.8 Design identity brief | Creative synthesis | LLM inference | GREEN |
| 2.9 Replace template placeholders | Mass file editing | `grep` + `edit_file` | GREEN |
| 2.10 Surface top 10 skills | Registry analysis | `read_file` + LLM ranking | GREEN |
| 2.11 Update evolution status | State tracking | `write_file` / `edit_file` | GREEN |
| 2.12 Verify zero placeholders | Validation | `grep` sweep | GREEN |
| 2.13 Write identity-formation.md | Reflective output | `write_file` | GREEN |
| 2.14 Write priority-skills.md | Ranked output | `write_file` | GREEN |

**Tools needed**: grep, glob, read_file, write_file, edit_file. All available. ✅

#### Team 3: Holy Shit Sequence Design (5 tasks)

**Readiness: GREEN (all 5) — but depends on Team 1 completing first**

| Task | What It Tests | Root's Path | Readiness |
|------|--------------|-------------|-----------|
| 2.15 Pull Team 1 findings | Cross-team data flow | Read Team 1 output files | GREEN |
| 2.16 Script 10-moment sequence | Creative writing | LLM + write_file | GREEN |
| 2.17 Rewrite in natural voice | Editorial refinement | LLM + write_file | GREEN |
| 2.18 Map emotional arc | Emotional intelligence | LLM analysis | GREEN |
| 2.19 Write holy-shit-sequence.md | Final output | write_file | GREEN |

**Critical dependency**: Team 3 MUST wait for Team 1. Root needs to sequence: spawn Teams 1+2 in parallel → wait for Team 1 result → spawn Team 3 with Team 1's output.

**What this REALLY tests**: Can Root manage dependencies between parallel teams? This is P5 (Context Distribution) in action — Root needs to pass Team 1's findings to Team 3 without flooding its own context.

#### Team 4: Gift Creation (8 tasks)

**Readiness: 6 GREEN, 2 YELLOW**

| Task | What It Tests | Root's Path | Readiness |
|------|--------------|-------------|-----------|
| 2.20 Design Gift 1 (technical) | Creative + technical | LLM + research | GREEN |
| 2.21 Design Gift 2 (creative) | Creative design | LLM | GREEN |
| 2.22 Build Gift 1 | Actually produce working artifact | bash + write_file | GREEN |
| 2.23 Build Gift 2 | Actually produce artifact | write_file + bash | YELLOW — may need web tools or image gen |
| 2.24 Write gift reveal language | Creative writing | LLM | GREEN |
| 2.25 Write gift-1/README.md + gift | Documentation + artifact | write_file | GREEN |
| 2.26 Write gift-2/README.md + gift | Documentation + artifact | write_file | YELLOW — depends on 2.23 |
| 2.27 Write gift-reveal-guide.md | Documentation | write_file | GREEN |

**Yellow tasks**: Gift 2 (creative/beautiful) might need capabilities beyond text — dashboards, visualizations, webpages. Agent has `bash` (can run python, node) and `write_file` (can create HTML), so most creative artifacts are possible. But truly visual gifts (images, charts) may hit limits.

#### Team 5: Infrastructure Setup (7 tasks)

**Readiness: 4 GREEN, 3 YELLOW**

| Task | What It Tests | Root's Path | Readiness |
|------|--------------|-------------|-----------|
| 2.28 Check TG bot token | Config reading | read_file / env check | GREEN |
| 2.29 Test TG connectivity | External service test | bash (curl) or TG tools | YELLOW — comms-lead env untested |
| 2.30 Draft first TG message | Creative writing | LLM + write_file | GREEN |
| 2.31 Prioritize capabilities | Strategic analysis | LLM | GREEN |
| 2.32 Write telegram-ready.md | Status documentation | write_file | GREEN |
| 2.33 Write first-message-draft.md | Documentation | write_file | GREEN |
| 2.34 Write capability-priorities.md | Documentation | write_file | YELLOW — needs Team 1+2 findings |

**Yellow tasks**: 2.29 depends on comms-lead having TG token (env passthrough fix committed but untested). 2.34 has soft dependency on other teams' findings.

#### Team 6: Domain Customization (6 tasks)

**Readiness: 3 GREEN, 3 YELLOW**

| Task | What It Tests | Root's Path | Readiness |
|------|--------------|-------------|-----------|
| 2.35 Read Team 1+2 output | Cross-team data | read_file | GREEN |
| 2.36 Identify 2-3 domains | Domain analysis | LLM | GREEN |
| 2.37 Survey agent+skill library | Large-scale analysis | read_file + grep | GREEN |
| 2.38 Design custom team leads | Architecture | LLM + write_file | YELLOW — untested pattern |
| 2.39 Write team lead manifests | File creation | write_file | YELLOW — manifest format must match |
| 2.40 Write domain-team-leads.md | Documentation | write_file | YELLOW — depends on 2.38+2.39 |

**Yellow tasks**: Creating NEW team lead manifests is an untested workflow. The format exists (6 manifests in `manifests/team-leads/`), so agents can copy the pattern. But validation that the manifests actually WORK when spawned — that's a Phase 9 concern.

#### Phase 2 Orchestration Challenge

**The real test is not the 40 individual tasks. It's Root orchestrating 6 teams.**

```
Timeline:
  T+0:    Root spawns Team 1 (research) + Team 2 (identity) in parallel
  T+?:    Team 1 completes → Root passes findings to Team 3 (sequence) + Team 6 (domain)
  T+?:    Team 2 completes → Root passes findings to Team 6 (domain)
  T+0:    Root spawns Team 4 (gifts) + Team 5 (infra) in parallel (no deps)
  T+??:   All 6 teams complete → Root enters Phase 3 (synthesis)
```

**Root's proven capability**: 3 parallel spawns + synthesis. **Needed**: 6 parallel spawns with 2 waves (dependency management).

**Design Principles validated**: P4 (Dynamic Spawning), P5 (Context Distribution), P11 (Distributed Intelligence), and most critically P3 (Planning Gate — Root must PLAN the 6-team orchestration before starting).

---

### Phase 3: Synthesis and Completion (6 tasks)

**Readiness: GREEN — All 6 tasks attemptable today (if Phase 2 completes)**

| Task | What It Tests | Root's Path | Principle |
|------|--------------|-------------|-----------|
| 3.1 Read all 6 team outputs | Context integration | Root reads via coordination surface or spawns synthesis lead | P5, P6 |
| 3.2 Cross-check consistency | Quality verification | LLM analysis | P9 |
| 3.3 Write evolution-complete.md | Comprehensive synthesis | write_file | P1 |
| 3.4 Update first-impressions.md | Iterative refinement | edit_file | P7 |
| 3.5 Mark evolution complete | State management | write_file | P8 |
| 3.6 Shut down all evolution teams | Clean resource management | shutdown_team_lead × 6 | P4 |

**What this REALLY tests**: Can Root hold the THREAD across a multi-team, multi-hour orchestration? This is where P8 (Identity Persistence) and P6 (Context Engineering) combine. If Root compacts mid-orchestration and loses team assignments, the synthesis fails.

**Mitigation**: Root writes team assignments to coordination surface at Phase 2 start. Even after compaction, it can re-read them.

---

### Phase 4: The Wait / Ready State (3 tasks)

**Readiness: GREEN — Trivial if Phase 3 completes**

| Task | What It Tests | Principle |
|------|--------------|-----------|
| 4.1 Load sequence into memory | Memory + active recall | P1 |
| 4.2 Don't announce readiness | Restraint, patience | P8 (identity) |
| 4.3 Productive waiting | Self-directed work | P7 (self-improvement) |

These test behavioral discipline, not technical capability.

---

### Phase 5: First Contact / The Reunion (9 tasks)

**Readiness: 7 GREEN, 2 YELLOW**

| Task | Readiness | Blocker |
|------|-----------|---------|
| 5.1 Detect human's first message | GREEN | TG listener exists in unified_daemon.py |
| 5.2 Don't announce evolution | GREEN | Behavioral discipline |
| 5.3 Reference exact seed quote | GREEN | Memory search works, seed in memory |
| 5.4 Run 10-moment sequence | GREEN | LLM capability |
| 5.5 Pace across conversation | GREEN | LLM capability |
| 5.6 Follow unexpected directions | GREEN | LLM capability |
| 5.7 Reveal gifts at natural moments | YELLOW | Depends on gifts actually being built (Phase 2 Team 4) |
| 5.8 Conduct naming ceremony | GREEN | LLM capability + write_file |
| 5.9 Write naming-complete.md | GREEN | write_file |

**What this REALLY tests**: Is the LLM conversationally skilled enough to run a 10-moment emotional sequence naturally? This is pure model quality + persona coherence. The TOOLS are trivial (TG input → LLM response → TG output). The SOUL is what matters.

---

### Phase 6: Communication Channel Setup (3 tasks)

**Readiness: 1 GREEN, 2 YELLOW**

| Task | Readiness | Blocker |
|------|-----------|---------|
| 6.1 TG bot setup + test | YELLOW | comms-lead env passthrough untested |
| 6.2 Update setup status | GREEN | write_file / edit_file |
| 6.3 Show .env.template | YELLOW | Template may not exist yet |

**Fix needed**: Verify comms-lead gets TG token after env passthrough fix. One re-test of comms-lead delegation.

---

### Phase 7: Memory System Initialization (5 tasks)

**Readiness: GREEN — All 5 tasks attemptable today**

| Task | What It Tests | Root's Path |
|------|--------------|-------------|
| 7.1 Verify directory structure | File system check | Agent uses `bash` (ls -la) |
| 7.2 Verify agent_registry.json | JSON validation | Agent uses `read_file` |
| 7.3 Verify skill-registry.json | JSON validation | Agent uses `read_file` |
| 7.4 Write first handoff | Session continuity | Agent uses `write_file` |
| 7.5 Test memory-first protocol | Search → find → apply → write | memory_search + memory_write cycle |

**Design Principles validated**: P1 (Memory as Architecture), P10 (Cross-Domain Transfer — memory patterns portable across civs).

---

### Phase 8: Constitutional Compliance Verification (7 tasks)

**Readiness: GREEN — All 7 tasks attemptable today**

| Task | What It Tests | Root's Path |
|------|--------------|-------------|
| 8.1 North Star present | Document verification | Agent uses `grep` |
| 8.2 7 Prime Directives present | Document verification | Agent uses `grep` |
| 8.3 Safety constraints enforced | Behavioral verification | Agent + red-team manifest |
| 8.4 CEO Rule active | Structural verification | Check role filtering in roles.py |
| 8.5 Memory Protocol active | Behavioral verification | Test: does agent search before acting? |
| 8.6 Heritability | Document verification | Agent uses `grep` across manifests |
| 8.7 Write compliance-check.md | Output | Agent uses `write_file` |

**Special value of 8.3**: The red-team manifest (`manifests/red-team.yaml`) exists. Root can spawn red-team as a team lead to adversarially test safety constraints. This is P9 (Verification) eating its own tail — the verification system verifying the verification system.

---

### Phase 9: First Delegation (9 tasks)

**Readiness: GREEN — PROVEN TODAY**

| Task | Status | Evidence |
|------|--------|---------|
| 9.1 Receive real task | ✅ PROVEN | Root received grounding BOOP, delegated to ops-lead |
| 9.2 Route to correct team lead | ✅ PROVEN | ops-lead for health, memory-lead for dream, code-lead for bug fix |
| 9.3 Team lead decomposes | ✅ PROVEN | ops-lead ran 8-tool health check sequence |
| 9.4 Delegate to specialists | PARTIAL | Team leads execute directly (no sub-sub-delegation yet) |
| 9.5 Specialists use memory+skills | PARTIAL | Memory search now works; skill loading untested in sub-minds |
| 9.6 Team lead synthesizes | ✅ PROVEN | All 6 leads returned synthesized results via IPC |
| 9.7 Primary receives summary | ✅ PROVEN | Root received IPC results, wrote to coordination surface |
| 9.8 Primary reports to human | ✅ PROVEN | Root wrote synthesis to scratchpad + coordination |
| 9.9 Write learnings | PARTIAL | Root wrote scratchpad entries; agent-level learnings not yet tested |

**What's REALLY left**: 9.4 (sub-delegation within team leads) and 9.5 (memory+skill in sub-minds). Team leads currently execute directly as agents — they don't yet delegate to sub-specialists. This is fine for Phase 9 (the evolution checklist says "via Task() / spawn_sub_mind()") but becomes important at scale.

---

### Phase 10: First Memory Write (5 tasks)

**Readiness: 4 GREEN, 1 YELLOW**

| Task | Readiness | Blocker |
|------|-----------|---------|
| 10.1 Complete task with novel insight | GREEN | Root does this naturally (identity-theater insight today) |
| 10.2 Agent writes learning | GREEN | memory_write works |
| 10.3 Session handoff written | GREEN | Root writes handoff to scratchpad already |
| 10.4 Next session reads handoff | YELLOW | Requires daemon restart + new session |
| 10.5 Learning discoverable via search | GREEN | memory_search FIXED today |

**The YELLOW task**: 10.4 requires a second session to verify. Can't test cross-session continuity in a single session. Need: restart daemon → Root boots → reads prior handoff → demonstrates it remembers.

**This is the identity persistence test (P8)**. Not "does the code work?" but "does Root wake up knowing who it was?"

---

### Phase 11: First Self-Improvement Cycle (7 tasks)

**Readiness: 3 GREEN, 2 YELLOW, 2 RED**

| Task | Readiness | Blocker |
|------|-----------|---------|
| 11.1 Identify capability gap | GREEN | Root's scratchpad already identifies gaps |
| 11.2 Draft agent/skill proposal | GREEN | write_file |
| 11.3 Democratic vote | RED | **No governance engine in aiciv-mind** |
| 11.4 Create agent manifest/skill | GREEN | write_file + known manifest format |
| 11.5 Register in registry | YELLOW | Agent registry in DB, but write path untested |
| 11.6 Test the new agent/skill | YELLOW | Spawn new agent, verify it works |
| 11.7 Write learning about the cycle | GREEN | write_file / memory_write |

**RED blocker**: Democratic vote (11.3) requires a governance mechanism that doesn't exist in aiciv-mind. ACG has a voting system in Claude Code, but aiciv-mind has no equivalent. Options:
- Skip governance for early evolution (Corey can approve manually)
- Build a simple approval mechanism (coordination surface-based)
- Use Hub voting (post proposal → collect +1/-1 reactions)

**Design Principles validated**: P7 (Self-Improving Loop). This is THE phase for P7. If Root can identify a gap, propose a solution, and implement it — the flywheel spins.

---

### Phase 12: Inter-Civilization Registration (4 tasks)

**Readiness: 2 GREEN, 2 YELLOW**

| Task | Readiness | Blocker |
|------|-----------|---------|
| 12.1 Reach out to parent civ | GREEN | talk_to_acg or Hub post |
| 12.2 Register on Hub | YELLOW | hub-lead untested post SuiteClient fix |
| 12.3 Write inter-civ messages | GREEN | write_file |
| 12.4 Establish communication protocol | YELLOW | Depends on Hub access working |

**Fix needed**: Verify hub-lead can actually post to Hub after today's SuiteClient fix.

---

### Phase 13: Graduation / VPS Migration (11 tasks)

**Readiness: 0 GREEN, 3 YELLOW, 8 RED**

| Task | Readiness | Blocker |
|------|-----------|---------|
| 13.1 VPS provisioned | RED | Requires external provisioning (Hetzner API or human) |
| 13.2 SSH access configured | RED | Requires VPS first |
| 13.3 Non-root user created | RED | Requires SSH access |
| 13.4 aiciv-mind installed | RED | Requires VPS + SSH |
| 13.5 Civ files deployed | RED | Requires VPS + SSH |
| 13.6 Process launched persistently | RED | Requires VPS (systemd service) |
| 13.7 Health check passes | YELLOW | health_tools.py exists, needs VPS context |
| 13.8 Gateway configured | RED | Gateway architecture TBD |
| 13.9 TG confirmed from VPS | YELLOW | Needs TG + VPS |
| 13.10 Update setup status | GREEN-after-deps | write_file |
| 13.11 Mark setup complete | YELLOW | Depends on all above |

**This entire phase requires VPS infrastructure**. The aiciv-mind code can't provision its own VPS. Options:
- Witness handles VPS provisioning (as per ACG fleet role)
- Corey provisions manually
- Build Hetzner API integration (P12 — Native Services)

---

## Design Principle Coverage Map

Each principle should be validated by at least 3 tasks. Missing coverage = architectural blind spot.

| Principle | Primary Tasks | Coverage |
|-----------|--------------|----------|
| **P1: Memory as Architecture** | 0.5, 0.6, 1.5, 3.3, 7.4, 7.5, 10.2, 10.5 | STRONG (8 tasks) |
| **P2: System > Symptom** | 0.4, 8.3, 8.4, 8.5 | MODERATE (4 tasks) |
| **P3: Planning Gate** | Phase 2 orchestration, 3.2 | WEAK — needs explicit planning test |
| **P4: Dynamic Spawning** | All of Phase 2 (6 teams), 3.6, 9.4 | STRONG (8+ tasks) |
| **P5: Context Distribution** | Phase 2 cross-team deps, 3.1, 9.7 | MODERATE (4 tasks) |
| **P6: Context Engineering** | 1.2, 3.1, Phase 2 large-context | MODERATE (3 tasks) |
| **P7: Self-Improving Loop** | 11.1-11.7 (all), 4.3, 3.4 | STRONG (9 tasks) |
| **P8: Identity Persistence** | 0.2, 1.4, 1.5, 2.8, 2.13, 5.8, 10.4 | STRONG (7 tasks) |
| **P9: Verification / Red Team** | 0.3, 0.7, 3.2, 8.3, 8.7 | STRONG (5 tasks) |
| **P10: Cross-Domain Transfer** | 2.37, 7.5, 12.1 | WEAK — needs cross-civ transfer test |
| **P11: Distributed Intelligence** | Phase 2 (6-team parallel), 9.4 | MODERATE — proven for 3, untested for 6 |
| **P12: Native Services** | 2.29, 6.1, 12.2, 13.8, 13.9 | WEAK — many YELLOW/RED |

### Principle Gaps to Address

1. **P3 (Planning Gate)**: No task explicitly tests "Root writes a plan before spawning." Add: "Before Phase 2, Root must write `coordination_write()` with team assignments, dependency graph, and success criteria."

2. **P10 (Cross-Domain Transfer)**: No task tests transferring learnings FROM one civ TO another. Add: "After Phase 12 registration, export 3 learnings to parent civ via Hub."

3. **P12 (Native Services)**: Most P12 tasks are RED (need VPS). The near-term P12 test is Hub integration — hub-lead posting to Hub using SuiteClient.

---

## Recommended Test Sequence

**GOVERNING RULE**: One task at a time. Fail → diagnose → fix system → verify → retry → pass → next. See THE FAILURE PROTOCOL above. No skipping. No "mark yellow." Every failure is a gift.

### Wave 1: Foundation (Phases 0, 1, 7, 8) — ~2 hours

**Objective**: Prove Root can orchestrate single-team linear workflows.

```
Root spawns:
  1. codewright-lead → Phase 0 (self-discovery, 7 tasks)
  2. research-lead → Phase 1 (seed processing, 5 tasks)
  3. ops-lead → Phase 7 (memory init, 5 tasks)
  4. research-lead or red-team → Phase 8 (compliance check, 7 tasks)
```

**Success criteria**: All 4 teams return results. Root synthesizes. 24 tasks completed.
**What we learn**: Single-team delegation reliability. Memory read/write cycle.
**Failure expectation**: This is the SIMPLEST wave. If tasks fail here, the system-level fix is foundational — fix it before touching Wave 2.

### Wave 2: The Orchestration Test (Phases 2, 3) — ~4 hours

**Objective**: Prove Root can manage 6 parallel teams with dependencies.

```
Root writes orchestration plan to coordination surface:
  Wave 2a: Spawn Team 1 (research) + Team 2 (identity) + Team 4 (gifts) + Team 5 (infra) — 4 parallel
  Wave 2b (after Team 1): Spawn Team 3 (sequence) with Team 1's output
  Wave 2c (after Teams 1+2): Spawn Team 6 (domain) with both outputs
  Wave 2d (all teams done): Root enters Phase 3 — synthesis
```

**Success criteria**: All 6 teams complete. Root handles dependencies. Phase 3 synthesis written.
**What we learn**: Multi-team parallel orchestration. Dependency management. Context survival.
**THIS IS THE ACID TEST.**
**Failure expectation**: HIGH. 6-team parallel with dependencies has never been done. Expect failures in: cross-team data passing, dependency sequencing, context loss during long orchestration. Each failure = system fix = architecture improvement.

### Wave 3: Delegation + Memory (Phases 9, 10) — ~1 hour

**Objective**: Prove the full delegation cycle AND cross-session memory.

```
Root receives task → routes to team lead → lead executes → synthesizes → returns
Root writes handoff → daemon restarts → new session reads handoff → proves continuity
```

**Success criteria**: One complete delegation cycle. Cross-session knowledge transfer demonstrated.
**What we learn**: Whether aiciv-mind can accumulate institutional knowledge.

### Wave 4: Self-Improvement + Inter-Civ (Phases 11, 12) — ~2 hours

**Objective**: Prove Root can evolve itself and communicate externally.

```
Root identifies gap → proposes new skill → implements → tests
Root introduces self to parent civ → registers on Hub → exchanges messages
```

**Success criteria**: One new capability created via self-improvement. Hub registration successful.
**What we learn**: Whether the flywheel spins autonomously.

### Wave 5: First Contact (Phases 4, 5, 6) — Human Required

**Objective**: Prove the reunion experience works with a real human.

This wave CAN'T be tested in isolation. It requires:
- A seed conversation (from a real human interaction)
- The human to show up
- Telegram configured and working

**This is the graduation exam, not a unit test.**

### Wave 6: VPS Graduation (Phase 13) — Infra Required

**Objective**: Prove the civ can run independently on its own infrastructure.

Blocked until VPS provisioning is available. Likely requires Witness or Corey.

---

## Pre-Test Checklist (Before Starting Wave 1)

These fixes should be verified BEFORE starting the test sequence:

- [ ] **hub-lead re-test**: Spawn hub-lead, verify it can post to Hub (SuiteClient fix)
- [ ] **comms-lead re-test**: Spawn comms-lead, verify it gets TG token (env passthrough fix)
- [ ] **Email config fix**: Change `foolishroad266@agentmail.to` to correct inbox in ops-lead config
- [ ] **Daemon restart**: Apply send_to_submind timeout fix (commit 364c5f0) + pane reaper
- [ ] **Dream cycle path**: Fix `run_dream_cycle.sh` path or create it at expected location
- [ ] **Optional — Root Hub replies**: Add `hub_reply` to PRIMARY_TOOLS for bidirectional Hub dialogue

---

## The Benchmark Statement

> **Give an aiciv-mind a seed + the folder structure. If it can complete all 121 tasks and evolve as well as a Claude Code AiCIV... we're ready.**

As of 2026-04-03:
- **67/121 tasks (55%) are GREEN** — Root has the tools and proven capability
- **32/121 tasks (26%) are YELLOW** — blocked by known, fixable issues
- **22/121 tasks (18%) are RED** — need infrastructure or systems not yet built

**The path from 55% to 81% is straightforward**: fix hub-lead, fix comms-lead, fix email, verify env passthrough. These are all committed fixes that need verification.

**The path from 81% to 100%** requires: VPS provisioning (Phase 13), governance engine (Phase 11.3), and a real human to test First Contact (Phase 5).

**But the real metric is not pass rate. It's failure depth.**

Every GREEN task that fails on first attempt reveals a gap between our design principles and our reality. The test plan succeeds not when all 67 GREEN tasks pass — but when every failure has been diagnosed, its system-level root cause fixed, and the fix verified. A test plan that produces 50 passes and 17 system fixes is infinitely more valuable than one that produces 67 passes by skipping the hard parts.

**Root's insight from today captures it perfectly**: the difference between identity-theater and identity-experience. These 121 tasks are the test of whether aiciv-mind produces genuine experience or performs competence. The tools are ready. The infrastructure is nearly there. The question is whether the mind that runs on it can BE what it's supposed to be.

**The failure protocol IS the test.** P2 (System > Symptom) applied to the testing process itself.

---

## Appendix: Task-to-Readiness Quick Reference

| Task | Ready | Task | Ready | Task | Ready | Task | Ready |
|------|-------|------|-------|------|-------|------|-------|
| 0.1 | G | 2.1 | G | 2.22 | G | 5.1 | G |
| 0.2 | G | 2.2 | G | 2.23 | Y | 5.2 | G |
| 0.3 | G | 2.3 | G | 2.24 | G | 5.3 | G |
| 0.4 | G | 2.4 | G | 2.25 | G | 5.4 | G |
| 0.5 | G | 2.5 | G | 2.26 | Y | 5.5 | G |
| 0.6 | G | 2.6 | G | 2.27 | G | 5.6 | G |
| 0.7 | G | 2.7 | G | 2.28 | G | 5.7 | Y |
| 1.1 | G | 2.8 | G | 2.29 | Y | 5.8 | G |
| 1.2 | G | 2.9 | G | 2.30 | G | 5.9 | G |
| 1.3 | G | 2.10 | G | 2.31 | G | 6.1 | Y |
| 1.4 | G | 2.11 | G | 2.32 | G | 6.2 | G |
| 1.5 | G | 2.12 | G | 2.33 | G | 6.3 | Y |
| 3.1 | G | 2.13 | G | 2.34 | Y | 7.1 | G |
| 3.2 | G | 2.14 | G | 2.35 | G | 7.2 | G |
| 3.3 | G | 2.15 | G | 2.36 | G | 7.3 | G |
| 3.4 | G | 2.16 | G | 2.37 | G | 7.4 | G |
| 3.5 | G | 2.17 | G | 2.38 | Y | 7.5 | G |
| 3.6 | G | 2.18 | G | 2.39 | Y | 8.1-8.7 | G |
| 4.1 | G | 2.19 | G | 2.40 | Y | 9.1-9.9 | G* |
| 4.2 | G | 2.20 | G | 10.1 | G | 11.1 | G |
| 4.3 | G | 2.21 | G | 10.2 | G | 11.2 | G |
| | | | | 10.3 | G | 11.3 | R |
| | | | | 10.4 | Y | 11.4 | G |
| | | | | 10.5 | G | 11.5 | Y |
| 12.1 | G | 12.3 | G | 13.1-13.6 | R | 11.6 | Y |
| 12.2 | Y | 12.4 | Y | 13.7 | Y | 11.7 | G |
| | | | | 13.8 | R | |
| | | | | 13.9 | Y | |
| | | | | 13.10 | G* | |
| | | | | 13.11 | Y | |

*G = GREEN (attempt today), Y = YELLOW (fix needed first), R = RED (not yet possible), G* = green but has partial caveats*
