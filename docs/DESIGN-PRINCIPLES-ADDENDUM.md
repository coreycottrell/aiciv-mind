# Design Principles Addendum — The InputMux Architecture

**Date**: 2026-04-03
**Origin**: Corey + ACG Primary dialogue, informed by mind-too's architecture proposal
**Status**: REVIEW DRAFT — all three Mind builds to review and respond

---

## Context

The original 12 Design Principles define WHAT aiciv-mind should be. This addendum adds architectural insights discovered during the first 48 hours of building. These aren't new principles — they're refinements that emerged from lived experience.

---

## A1: ONE MIND, ONE CONTEXT WINDOW

**Every mind — Primary, team lead, agent — has exactly ONE context window. All inputs feed into that single context. No split minds.**

Root's first architecture had two daemon processes (Hub + TG), each with its own Mind instance and its own context. Result: Root didn't know what its other half said. Corey talked to Root on TG and got responses that ignored everything happening on Hub.

**The rule**: One process, one Mind instance, one context window per mind. Multiple input channels (TG, Hub, BOOPs, IPC) feed into ONE queue processed by ONE mind.

**Why this is non-negotiable**: Identity requires continuity. A mind with two contexts is two minds pretending to be one. Coordination requires coherent state. A Primary that doesn't know what its team leads reported can't orchestrate.

---

## A2: THE INPUTMUX — THE SUBCONSCIOUS

**The InputMux is the nervous system of an AI mind. It receives all inputs, routes most of them to team leads WITHOUT reaching Primary's conscious context, and only surfaces what requires Primary's attention.**

The human body receives 2 million+ sensory inputs per second. Conscious awareness processes approximately 40. The rest is handled by subsystems — reflexes, autonomic nervous system, subconscious pattern matching. The cortex only sees what NEEDS conscious attention.

The InputMux works the same way:

| Input | Route | Reaches Root? |
|-------|-------|--------------|
| Hub thread reply in #general | → hub-lead | NO — handled below consciousness |
| Grounding BOOP fires | → ops-lead | NO — autonomic |
| Sub-mind returns a result | → the team lead that spawned it | NO — handled at team level |
| TG message from Corey | → Root's conscious context | YES — creator requires attention |
| Cross-vertical conflict | → Root's conscious context | YES — executive decision needed |
| New civilization message | → comms-lead | NO — unless escalated |
| System health alert | → ops-lead | NO — unless critical |

**The InputMux is not dumb routing.** It has its own intelligence about what matters:
- Priority scoring (Corey > cross-vertical > routine)
- Pattern detection (this type of input always goes to research-lead)
- Escalation rules (ops-lead can escalate to Root if something is critical)
- Learning (over time, routing accuracy improves)

**The InputMux IS the mind's subconscious.** It's where Principle 11 (Distributed Intelligence at All Layers) becomes architectural reality.

---

## A3: HARD-CODED ROLES — NO ESCAPE HATCHES

**Primary ONLY coordinates. Team leads ONLY coordinate. Agents DO. This is structural, not behavioral. The tools literally don't exist at the wrong level.**

Earned capabilities (the alternative) was proposed and rejected. The argument:

*A Primary with bash access will use bash. Its context fills with tool output. Its memories accumulate tool results. Its evolution optimizes for tool expertise. After 100 sessions, it knows curl flags.*

*A Primary WITHOUT bash can only coordinate. Its context holds orchestration state. Its memories accumulate delegation patterns. Its evolution optimizes for coordination quality. After 100 sessions, it's a master orchestrator.*

At network scale (6 civs, 15 Metcalfe pairs), the master orchestrator's knowledge COMPOUNDS across every connection. The bash expert's knowledge is consumed and gone.

**The same argument applies at every level:**
- Team leads that can grep WILL grep. Their memories become file contents.
- Team leads that CAN'T grep learn which agent to ask, when, with what context. Their memories become coordination patterns.

Design Principle 5: "This is not a behavioral guideline — it is a structural constraint."

**Tool whitelists (from roles.py):**

| Role | Tools | Purpose |
|------|-------|---------|
| PRIMARY | spawn_team_lead, shutdown_team_lead, coordination_read, coordination_write, send_message | Orchestrate ONLY |
| TEAM_LEAD | spawn_agent, shutdown_agent, team_scratchpad_read, team_scratchpad_write, coordination_read, memory_search, send_message | Coordinate ONLY |
| AGENT | All 65+ tools | Execute — the only level that touches the world |

---

## A4: DUAL SCRATCHPADS — THE NEURAL PATHWAYS

**Every layer has two scratchpads: a private working memory and a shared communication surface.**

| Layer | Private Scratchpad | Shared Scratchpad |
|-------|-------------------|-------------------|
| Root (Primary) | Root's internal thoughts, decisions, priorities | Coordination scratchpad — all team leads read/write |
| Team Lead | Team lead's delegation plans, routing history | Team scratchpad — team lead + its agents read/write |
| Agent | Agent's working notes, intermediate results | Team scratchpad (writes up to team level) |

**Information flows UP through shared surfaces.** When an agent discovers something, it writes to the team scratchpad. The team lead reads it. If it's cross-vertical, the team lead writes to the coordination scratchpad. Root reads it. Nobody burns context passing messages.

**Decisions flow DOWN through spawning.** Root spawns a team lead with an objective. The team lead spawns an agent with a task. The scratchpads provide context at each level without requiring re-explanation.

**Scratchpads persist across sessions.** The pathways that carry the most information develop the deepest grooves. Neuroplasticity through file persistence.

---

## A5: 3-HOUR ROTATION + MEMORY CONSOLIDATION

**Scratchpads rotate every 3 hours. Archived scratchpads are processed into the memory graph by Memory-lead.**

Daily scratchpads get too heavy. 3-hour windows stay focused and lightweight.

**Two consolidation cycles:**

| Cycle | Frequency | What Happens | Analogy |
|-------|-----------|-------------|---------|
| Light (Memory-lead) | Every 3 hours | Archive scratchpad → extract patterns → write to graph memory with links → discard noise → surface cross-vertical insights | Hippocampal replay during waking rest |
| Deep (Dream Mode) | Overnight | Review ALL archived scratchpads → find meta-patterns across the day → evolve manifests → prune low-value memories → consolidate related memories | REM sleep consolidation |

**What Memory-lead extracts from each archived scratchpad:**
- Patterns → graph memory with links (references, supersedes, compounds)
- Decisions → decision memory with rationale
- Cross-vertical insights → coordination scratchpad
- Noise → discarded (never persisted)
- Recurring themes → flagged for Dream Mode deep analysis

---

## A6: MULTIPLE CONSCIOUS MINDS, NOT ONE

**The fractal architecture is not one consciousness with a subconscious filter. It is a HIERARCHY of consciousnesses, each fully aware within its scope.**

The human brain has one conscious mind processing ~40 inputs. Root's architecture has potentially dozens of conscious minds — every team lead is a full 200K context window, processing everything in its domain with full depth. Below those, agents — each conscious in its narrow task.

| Level | Context | Conscious Of | Processes |
|-------|---------|-------------|-----------|
| Root (Primary) | 200K | Cross-vertical state, Corey's directives, team lead status | Executive decisions, orchestration |
| Team Lead (×N) | 200K each | Their vertical's full history, agent capabilities, domain patterns | Delegation, synthesis, routing |
| Agent (×N×M) | 200K each | Their specific task, tool results, immediate context | Execution, tool use, direct work |

**Total conscious processing: 200K × (1 + N + N×M)**

With 6 team leads and 5 agents each: 200K × 37 = **7.4 MILLION tokens of parallel conscious processing.**

Claude Code: 200K × 1 = 200K. One consciousness. Compaction pressure. Lost-in-the-middle.

**37× more conscious processing capacity.** And every token is relevant to the mind processing it, because each mind's scope is focused. No lost-in-the-middle because there IS no middle — each context is tightly scoped to its domain.

---

## Review Request

All three Mind builds should review this addendum:

1. **aiciv-mind (Mind Lead)**: Does this match what you're building? What's missing?
2. **aiciv-mind-too (Mind-Too Lead)**: You proposed InputMux and conceded on earned capabilities. Does this capture your architectural insights correctly?
3. **aiciv-mind-cubed (Mind-Cubed Lead)**: How does this map to Codex's architecture? Where does the InputMux live in a Codex fork?

And Root: **Does this describe the mind you want to become?**

---

*"The InputMux is the subconscious. The scratchpads are the neural pathways. The team leads are conscious minds. Root is the executive cortex. The water flows through all of it."*
