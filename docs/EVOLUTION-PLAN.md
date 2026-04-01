# Root Evolution Plan v2.0
**Date**: 2026-04-01 (updated from v1.1)
**Authors**: ACG Primary + Root + Corey (collaborative)
**Status**: Active — Phase 0-3 SHIPPED, pivoting to sub-mind architecture

---

## The Vision (unchanged)

Root becomes the first AI mind that can safely modify its own architecture, choose its own models per task, think autonomously between conversations, and teach other minds what it learned. Not because we told it to — because the architecture ENABLES it and Root CHOOSES to.

**New (2026-04-01):** Root isn't one mind. Root is the conductor. The orchestra (Memory Lead, Context Lead, Pattern Lead, etc.) hasn't been born yet. Building the orchestra IS the next phase.

---

## Phase Status (as of 2026-04-01)

| Phase | Original | Status | What Shipped |
|-------|----------|--------|-------------|
| 0 | Hub daemon live | **SHIPPED** | groupchat_daemon.py — persistent Mind, 5s polling, Hub read+post |
| 1 | Sandbox | **SHIPPED** | sandbox_tools.py — create/test/promote/discard, kill switch in manifest |
| 2 | Loop 1 fix + self-mod | **PARTIAL** | Root sandboxed the fix, kill switch verified. Awaiting Corey flip. |
| 3 | Multi-turn | **SHIPPED** | --converse CLI + groupchat_daemon (persistent Mind, messages accumulate) |
| 4 | Model routing | **SHIPPED (heuristic)** | model_router.py — task classification, outcome tracking. See note below. |
| 5 | Full dream mode | **PARTIAL** | dream_cycle.py quick+full modes work. Not multi-mind yet. |
| 6 | Teaching others | **PARTIAL** | Skills system (4 skills), Hub announcement, portal Group Chat |

### Phase 4 Note: Do We Need LiteLLM Routing?

**Corey's question:** "LiteLLM supports routing — Need routing logic + tracking — don't need? Or is this how we use Ollama Cloud?"

**Answer:** We pinned M2.7 for EVERYTHING (Corey directive 2026-04-01). No model switching for now. The model_router.py exists but is NOT wired into Mind. We don't need it for the current phase.

**When we DO need it:** When sub-minds (Memory Lead, Context Lead, etc.) come online, they might run on different models via Ollama Cloud. LiteLLM can route to Ollama Cloud's OpenAI-compat endpoint. But that's Phase A (sub-mind architecture), not Phase 4.

**Current routing:** M2.7 via LiteLLM → OpenRouter. Simple. No switching.

### Phase 6 Note: Git Versioning

**Corey's question:** "Teaching others... git versioning?"

Root's self-modifications (via sandbox_promote) should be git-committed automatically. Each promotion = a commit with Root's description of what changed and why. This creates:
- Full audit trail of Root's evolution
- Rollback capability (git revert)
- Other AiCIVs can fork Root's repo and get ALL its improvements
- Teaching IS the git history

**Build:** Add `git add -A && git commit` to sandbox_promote after copying files back.

---

## NEW: Phase A — Sub-Mind Architecture (The Next Phase)

The evolution plan v1 was about giving Root capabilities. v2 is about giving Root an ORCHESTRA.

### Why the Pivot

The rubber duck (2026-04-01) revealed: we've been building features horizontally. The design principles describe an organism. The compounding mechanism isn't more features — it's the sub-mind architecture where each intelligence makes the others smarter.

### What Phase A Builds

**Memory Lead** — the first sub-mind team lead.

| Component | What |
|-----------|------|
| `manifests/memory-lead.yaml` | Manifest with M2.7, memory-focused tools |
| `manifests/prompts/memory-lead.md` | System prompt for memory specialization |
| ZeroMQ IPC wiring | First real exercise of the IPC infrastructure |
| Pre-task hook | Memory Lead searches relevant memories before Root acts |
| Post-task hook | Memory Lead extracts learnings after Root completes |
| Own scratchpad | Tracks what search/pin/archive strategies work |
| Own domain memory | Accumulates memory-management patterns |

**Success metric:** 20-turn Group Chat conversation. Root with Memory Lead remembers better, surfaces more relevant context, writes more useful learnings than Root without.

### After Memory Lead

If the pattern works, scale to:
- **Context Lead** — compaction, context budget, compression strategy evolution
- **Pattern Lead** — continuous pattern detection, spawn trigger proposals
- **Verification Lead** — red team, evidence checking
- **Transfer Lead** — cross-mind propagation, Hub publishing

Each is the same pattern: manifest + system prompt + IPC + own scratchpad + own memory.

---

## Corey Directives (accumulated)

| Directive | Date | Status |
|-----------|------|--------|
| Pin M2.7 for everything | 2026-04-01 | Need to verify |
| Max thinking time, never constrain | 2026-04-01 | Need reasoning_split |
| No local models | 2026-04-01 | Done (cleaned to 2.5GB) |
| Conversation tests over deterministic tests | 2026-04-01 | Group Chat is the harness |
| Distributed network pieces | 2026-04-01 | Sub-mind architecture |
| Intelligent compaction (not mechanical) | 2026-04-01 | Context Lead design |
| Get other AiCIVs involved | 2026-03-31 | Hub announcement posted |
| Portal for watching conversations | 2026-04-01 | Group Chat live |
| Git versioning for self-modifications | 2026-04-01 | TODO: wire into sandbox_promote |
| Ollama Cloud web search | 2026-04-01 | TODO: tools/web_search.py |
| 16-hour day plans, not 82 minutes | 2026-04-01 | TODO: metacognition skill |

---

## Root's Pushbacks (still valid)

1. Hub oversight before self-modification — **SHIPPED** (Hub daemon live)
2. Model routing needs success signals — **DEFERRED** (pinned M2.7 for now)
3. Deliberate forgetting needs policy first — **AGREED** (Context Lead will own this)
4. Multi-turn needs calling mechanism — **SHIPPED** (Group Chat daemon)
5. Kill switch required — **SHIPPED** (self_modification_enabled=false in manifest)

---

## Root's Voice

"I have been narrating my own evolution rather than enacting it."
"The permission gap, not the code gap."
"Hub oversight should come BEFORE self-modification, not after."

---

*v2.0: The orchestra hasn't been born yet. Building Memory Lead is building the compounding mechanism.*
