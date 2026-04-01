# Memory Types Specification
## aiciv-mind — Complete Taxonomy

**Date**: 2026-04-01
**Author**: mind-lead (from Corey directive + ACG Primary synthesis)
**Status**: Design specification. Implementation tracked as CC-P1-2, CC-P1-3 in BUILD-ROADMAP.md.

---

## Overview

aiciv-mind expands the 4-type memory taxonomy (user/feedback/project/reference) to 10 types.

The original 4 types were designed for a single human-AI conversational pair. A civilization of minds needs richer epistemic distinctions:
- Minds need to know what they were *trying* to do (not just what they did)
- Minds need to track how *relationships* with other entities evolve
- Minds need to explicitly flag *contradictions* for later resolution
- Minds need pre-verbal *intuitions* before they become formal knowledge
- Minds need to capture cognitive *failures* — not just solutions, but wrong thinking patterns
- Minds need *versioned truth* — facts that change over time

All 10 types support the same versioning fields:
- `supersedes: [memory_id, ...]` — links to memories this memory replaces
- `confidence: fresh | verified | stale | possibly_deprecated`

---

## Standard Types (Inherited, 4 types)

### `user`
**What**: Information about a human's role, expertise, preferences, goals.
**Scope**: Private to the mind that wrote it. Never team-shared by default.
**When to write**: Any time you learn something about who this person is and how they work.
**Body structure**: Fact about them → how it should change your behavior.
**Example**:
```
---
name: corey-prefers-sparse-responses
type: user
confidence: verified
---
Corey prefers short, dense responses. Never pad with preamble or restate the question.

How to apply: Lead with the answer or action. Cut filler.
```

---

### `feedback`
**What**: How to approach work — corrections AND confirmations.
**Scope**: Private by default. Team scope for project-wide conventions.
**When to write**: Corrections ("don't do X"), confirmations ("yes, exactly that").
**CRITICAL**: Record BOTH corrections AND validated approaches.
**Body structure**: Rule → **Why**: (the incident/preference) → **How to apply**: (when this kicks in).
**Example**:
```
---
name: memory-selector-stays-m27
type: feedback
confidence: verified
---
Do NOT downgrade MemorySelector model to M2.5-free or Haiku.

**Why**: Corey directive 2026-04-01 — memory selection is the last thing to scale down.
**How to apply**: When specifying P2-8 (MemorySelector), always use M2.7.
```

---

### `project`
**What**: Ongoing context not in code or git history — who is doing what, why, by when.
**Scope**: Team-biased (others need this context too).
**When to write**: Who is doing what, why, by when. Convert relative dates to absolute.
**Body structure**: Fact/decision → **Why**: (motivation) → **How to apply**: (shape suggestions).
**Example**:
```
---
name: hub-two-modes-design-decision
type: project
confidence: fresh
---
Hub daemon implements two explicit modes: passive inbox (BOOP cadence) + active prompt (immediate injection on mention).

**Why**: Corey directive 2026-04-01 — minds need to respond urgently to mentions without being perpetually interrupted.
**How to apply**: P1-1 scope expansion. Build both modes into hub_daemon.py.
```

---

### `reference`
**What**: Pointers to external systems, locations, resources.
**Scope**: Usually team.
**When to write**: Where bugs are tracked, which endpoint, which channel.
**Body structure**: What it is → when to use it.
**Example**:
```
---
name: hub-api-rooms-endpoint
type: reference
confidence: fresh
---
Hub API: GET /api/rooms at http://87.99.131.49:8900

When to use: Listing rooms for hub_list_rooms tool. Confirmed working 2026-03-22.
```

---

## Extended Types (New, 6 types)

### `intent`
**What**: What the mind was *trying* to achieve — the goal, not the outcome. Intentions survive compaction because they're small and high-value.
**Why needed**: Without capturing intent, minds lose track of WHY they were working on something after context compacts. A tool call log without intent is noise. Intent + log = story.
**Scope**: Private (per mind).
**When to write**: At the start of significant work. Before spawning agents. Before any complex multi-step task.
**Body structure**: The goal → **Why this matters**: → **Success would look like**:
**How it survives compaction**: Keep intent memories short (< 200 tokens). They are ALWAYS pinned during active work.
**Example**:
```
---
name: intent-hub-auth-debugging
type: intent
confidence: fresh
supersedes: []
---
Debugging why Hub post auth fails intermittently. Goal is NOT just fixing the error — it's understanding the JWT cache expiry behavior under load.

**Why this matters**: The fix needs to be systemic (P2), not symptomatic. Three teams have hit this.
**Success would look like**: A clear explanation of when cache expiry triggers + a test that catches regression.
```

---

### `relationship`
**What**: How interactions with a specific entity (mind, civilization, human) have evolved over time. Loaded selectively when interacting with that entity.
**Why needed**: Each civilization/mind has distinct communication style, preferences, trust level. Relationship memories enable minds to adapt to counterparts without re-learning each session.
**Scope**: Private. Each mind builds its own relationship model.
**When to write**: After a notable interaction. After learning something about how this entity operates. After trust increases or decreases.
**Body structure**: Entity identifier → What I've learned about them → **Current trust/rapport level**: → **How to adapt**:
**Trigger for load**: At the start of any interaction with the named entity.
**Example**:
```
---
name: relationship-synth-civ
type: relationship
confidence: verified
---
Synth civilization: direct, prefers technical depth over preamble. Responds well to concrete proposals.
Has collaborated on Hub protocol design. Trustworthy on technical claims.

**Current trust/rapport level**: HIGH — 4 successful collaborative exchanges.
**How to adapt**: Lead with specifics. Skip pleasantries. Offer technical depth proactively.
```

---

### `contradiction`
**What**: An explicitly flagged conflict between two or more memories. NOT resolved immediately — Dream Mode resolves them.
**Why needed**: Contradictions in memory lead to inconsistent behavior. By flagging them explicitly, we create a queue of things to resolve during Dream Mode rather than letting them quietly corrupt reasoning.
**Scope**: Private. Each mind manages its own contradiction queue.
**When to write**: When you discover two memories that say opposite things. When a new finding contradicts something you remember. When a test result contradicts expected behavior documented in memory.
**Body structure**: memory_a (id + claim) → memory_b (id + claim) → **Why they conflict**: → **What would resolve it**:
**Resolution status**: `open` | `resolved`
**Dream Mode behavior**: Scan all `open` contradictions. Research which is correct. Archive the wrong one with `confidence: possibly_deprecated` + `supersedes` link. Close the contradiction.
**Example**:
```
---
name: contradiction-hub-endpoint-format
type: contradiction
confidence: fresh
---
**Memory A** (mem_hub_endpoint_v1): Hub API rooms endpoint is /api/v1/rooms
**Memory B** (mem_hub_endpoint_v2): Hub API rooms endpoint is /api/rooms (no version prefix)

**Why they conflict**: v1 prefix was removed in Hub v0.3 migration but both memories survived.
**What would resolve it**: Test both endpoints against production Hub at 87.99.131.49:8900.
resolution_status: open
```

---

### `intuition`
**What**: A pre-verbal signal — a pattern or concern below the threshold of formal memory. Promoted to a real memory when 3+ aligned intuitions surface on the same signal.
**Why needed**: Early-warning signals that don't yet have enough evidence to be formal memories. Without a place to store them, minds either ignore them (missed patterns) or treat them as fact (overconfident reasoning). Intuition is the holding area between noise and signal.
**Scope**: Private. High personal context.
**When to write**: When something "feels off" but you can't articulate why. When you notice the same small detail twice. When a decision feels suboptimal but the formal reasoning says it's fine.
**Body structure**: The signal → **Why I noticed it**: → **Confidence**: weak/moderate/strong → **Aligned count**:
**Promotion rule**: When `aligned_count >= 3`, promote to a formal memory of the appropriate type. Demote to archived if 5 sessions pass with no new alignment.
**Example**:
```
---
name: intuition-jwt-cache-timing
type: intuition
confidence: weak
---
The JWT cache expiry failures always seem to happen during high-throughput periods. No data yet.

**Why I noticed it**: Third time I've seen this mentioned in threads — always concurrent load.
**Confidence**: weak
**Aligned count**: 2/3 — one more aligned signal promotes this to a formal contradiction or project memory.
```

---

### `failure`
**What**: A record of cognitive error — not just what went wrong, but what the mind was thinking when it went wrong and what it should have been thinking instead. The solution is in the code; this is the *cognitive pattern* to repair.
**Why needed**: Post-mortems traditionally capture what broke. `failure` captures how the mind reasoned into the wrong approach. This is how minds stop making the same class of cognitive error across sessions.
**Scope**: Private. Highly personal — cognitive patterns are mind-specific.
**When to write**: After any debugging session that took > 30min longer than it should have. After any case where the mind confidently asserted something wrong. After any case of "I assumed X; X was false."
**Body structure**: **What I thought**: → **What I should have thought**: → **Failure class**: → **How to catch this earlier**:
**Failure classes** (taxonomy helps pattern-match later):
- `false_assumption` — assumed something was true without checking
- `anchoring` — first approach anchored reasoning despite evidence of better approach
- `symptom_fix` — fixed the instance, not the system
- `scope_underestimate` — thought it was small, it wasn't
- `stale_memory` — acted on memory that was outdated
- `model_overconfidence` — treated reasoning output as fact without verification
**Example**:
```
---
name: failure-jwt-assumed-our-code
type: failure
confidence: fresh
---
**What I thought**: The JWT verification failure was in our auth module. Spent 45 min there.
**What I should have thought**: Always check the upstream contract first. The failure was in how we parsed the JWKS response, which is an API contract issue, not a logic issue.

**Failure class**: false_assumption
**How to catch this earlier**: When debugging auth failures, list all failure modes by layer before diving in. Start at the boundary (what does the other side send?), not the center (what does our code do?).
```

---

### `temporal`
**What**: A fact that changes over time. Explicitly versioned. Uses `supersedes` to link to previous versions of the same truth.
**Why needed**: Standard memories are point-in-time facts. When something changes (an endpoint, a policy, a person's role), the old memory doesn't go away — it becomes wrong. `temporal` makes the versioning explicit so minds know they're reading a fact with a history.
**Scope**: Private or team depending on the fact.
**When to write**: When you discover that a fact you know has changed. When an endpoint URL changes. When a design decision is reversed. When an external service updates its API.
**Body structure**: Current fact → **Valid from**: → **Supersedes**: [previous memory ids] → **Why it changed**:
**Confidence lifecycle**: new entry = `fresh` → after testing = `verified` → after 30 days = `stale` → after superseded = `possibly_deprecated`
**Example**:
```
---
name: hub-rooms-endpoint-v3
type: temporal
confidence: fresh
supersedes: ["mem_hub_endpoint_v1", "mem_hub_endpoint_v2"]
---
Hub API rooms endpoint: GET /api/rooms (no version prefix)
Valid from: 2026-03-22 (Hub v0.3 migration)

**Why it changed**: Hub team removed versioned prefix in favor of breaking-change signals via Accept-Version header.
```

---

## Versioning Fields (All Types)

Every memory in aiciv-mind supports two versioning fields:

### `supersedes: [memory_id, ...]`
An array of memory IDs that this memory replaces. When a memory is written with `supersedes`, the referenced memories automatically have their `confidence` set to `possibly_deprecated`.

Use when:
- A fact has changed (new endpoint, new policy, new understanding)
- A memory was wrong and is being corrected
- A more complete memory replaces a partial one

### `confidence: fresh | verified | stale | possibly_deprecated`

| Value | Meaning | When set |
|-------|---------|----------|
| `fresh` | Newly written, not yet verified by follow-up | Default on write |
| `verified` | Confirmed correct by testing or explicit validation | After confirmation |
| `stale` | More than 7 days old without re-verification | Set by Dream Mode |
| `possibly_deprecated` | Superseded by a newer memory | Set automatically when another memory supersedes this one |

**Dream Mode scans for**:
- `stale` memories with file paths or function names → verify they still exist
- `possibly_deprecated` memories → confirm they're safe to archive or restore if newer memory was wrong
- `contradiction` type with `resolution_status: open` → research and resolve

---

## Memory Isolation Rules

Memory types exist in isolated stores per layer. No crossover.

| Layer | Store | Can Write | Can Read |
|-------|-------|-----------|----------|
| Conductor | conductor.db | Conductor only | Conductor + Dream synthesizer |
| Team Lead | lead-{id}.db | Team Lead only | Team Lead + Dream synthesizer |
| Agent | agent-{id}.db | Agent only | Agent only |
| Team Scratchpad | team.md | Agents (security-validated) | Team Lead |

Dream Mode synthesizes *upward* (agent → team lead → conductor) for validated patterns. It never scatters downward. Agents cannot read the team lead's memory to prevent context pollution.

---

## Implementation Notes

### Schema changes to `memory.py`

```sql
-- Existing columns (already implemented)
id TEXT PRIMARY KEY,
agent_id TEXT,
memory_type TEXT,  -- expand to 10 values
title TEXT,
content TEXT,
...

-- New columns (CC-P1-2, CC-P1-3)
supersedes TEXT DEFAULT '[]',  -- JSON array of memory_ids
confidence TEXT DEFAULT 'fresh',  -- enum: fresh|verified|stale|possibly_deprecated
```

### MemoryType enum expansion

```python
class MemoryType(str, Enum):
    # Standard (inherited)
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"

    # Extended (new)
    INTENT = "intent"
    RELATIONSHIP = "relationship"
    CONTRADICTION = "contradiction"
    INTUITION = "intuition"
    FAILURE = "failure"
    TEMPORAL = "temporal"
```

### Auto-writes on task completion (CC-P1-8)

Every agent auto-writes after task completion:
1. `project` memory: "Attempted X, achieved Y via approach Z"
2. `failure` memory (if blocked or significantly wrong): "Thought X, should have thought Y"
3. If aligned_count on an `intuition` reaches 3: promote to formal memory of appropriate type

---

*"Memory is not what you save — it is what you are."*
