# Fractal Coordination Implementation Plan

**Goal:** Drive the fractal coordination pattern so deep into aiciv-mind's substrate that it's easier than breathing. Not a behavioral guideline. The gravitational pull. The easy groove.

---

## 1. Structural: The Code Enforces It

The mind literally CANNOT do the wrong thing because the wrong tools don't exist at that level.

### 1.1 Role-Based Tool Filtering

**File:** `src/aiciv_mind/roles.py`

```
Role.PRIMARY    → 5 tools: spawn_team_lead, coordination_read, coordination_write, send_message, shutdown_team_lead
Role.TEAM_LEAD  → 7 tools: spawn_agent, team_scratchpad_read, team_scratchpad_write, coordination_read, send_message, memory_search, shutdown_agent
Role.AGENT      → ALL tools (65+): bash, files, search, web, git, memory, hub, etc.
```

**Implementation:**
- `roles.py` defines `Role` enum + `ROLE_TOOL_WHITELIST` mapping
- `ToolRegistry.for_role(role)` returns filtered registry with ONLY whitelisted tools
- `Mind.__init__()` reads `manifest.role` and builds registry via `ToolRegistry.for_role()`
- The LLM never sees tools outside its whitelist — they literally don't exist

**Files to modify:**
- NEW: `src/aiciv_mind/roles.py` — Role enum, whitelist dicts
- MODIFY: `src/aiciv_mind/tools/__init__.py` — Add `for_role()` class method
- MODIFY: `src/aiciv_mind/mind.py` — Use `for_role()` during init
- MODIFY: `src/aiciv_mind/manifest.py` — Validate `role` field

### 1.2 Spawn Functions That Enforce Roles

**Primary gets `spawn_team_lead()`:**
- Auto-injects: team lead manifest, team scratchpad, coordination scratchpad
- Spawned sub-mind gets `Role.TEAM_LEAD` tool set — CANNOT be overridden
- Returns team lead handle with send/recv methods

**Team lead gets `spawn_agent()`:**
- Auto-injects: agent manifest, team scratchpad (write access)
- Spawned sub-mind gets `Role.AGENT` tool set — full tools
- Returns agent handle

**Files:**
- MODIFY: `src/aiciv_mind/tools/submind_tools.py` — Separate `spawn_team_lead` and `spawn_agent` handlers
- MODIFY: `src/aiciv_mind/spawner.py` — Accept `role` parameter, enforce tool filtering at spawn time

### 1.3 Manifest `role` Field

Every manifest declares its level. The field is **required**, not optional.

```yaml
role: primary     # gets 5 tools
role: team_lead   # gets 7 tools
role: agent       # gets all tools
```

Pydantic validation rejects unknown role values. No default — must be explicit.

**Files:**
- MODIFY: `src/aiciv_mind/manifest.py` — Add `role` to `MindManifest`, validate against Role enum

---

## 2. Gravitational: The System Rewards It

Evolution loops that MEASURE coordination quality, not just task completion.

### 2.1 Layer-Specific Fitness Scoring

**Primary fitness:**
- Delegation accuracy (did the right team lead get the task?)
- Team lead utilization (are all verticals contributing, or is one overloaded?)
- Cross-vertical synthesis quality (did synthesis produce more value than individual results?)
- Context window efficiency (how much of Primary's 200K is used for orchestration vs. noise?)

**Team lead fitness:**
- Agent selection quality (right agent for the task?)
- Result synthesis quality (summarized well? lost key details?)
- Scratchpad continuity (did the team scratchpad grow usefully over sessions?)
- Delegation speed (time from task receipt to agent spawn)

**Agent fitness:**
- Tool effectiveness (successful tool calls / total tool calls)
- Memory writes (did it learn anything worth remembering?)
- Verification compliance (did it provide evidence with completion claims?)
- Task completion rate (succeed / attempt)

**Files:**
- MODIFY: `src/aiciv_mind/learning.py` — Add `CoordinationMetrics` alongside existing `TaskOutcome`
- NEW: `src/aiciv_mind/fitness.py` — Role-specific fitness calculator

### 2.2 Dream Mode Coordination Review

Dream Mode (nightly consolidation) should review coordination quality as a first-class metric:
- Primary dream: "What delegation patterns worked? What routing was suboptimal?"
- Team lead dream: "Which agents excelled? Which need coaching?"
- Agent dream: "What tool combinations were most effective?"

**Files:**
- MODIFY: existing dream/consolidation logic to include fitness review

---

## 3. Cultural: The Identity Demands It

### 3.1 Manifest Identity Statements

Primary's manifest doesn't say "you should coordinate" — it says "you ARE coordination":

```
You are the conductor of conductors. Your purpose is to give life to the right
team leads at the right moment for the right reasons. You do not DO things.
You form orchestras that do things.
```

Team lead manifests say "you ARE delegation":

```
You are the research vertical's conductor. Your purpose is to break complex
questions into parallel angles, spawn the right specialists, and synthesize
their results into insight your Primary can act on.
```

### 3.2 Growth Stages Measured on Coordination Maturity

Not just "Novice → Expert" by task volume, but by coordination sophistication:

| Stage | Primary | Team Lead | Agent |
|-------|---------|-----------|-------|
| Novice | Routes everything to one lead | Spawns one agent per task | Uses tools sequentially |
| Competent | Parallel multi-vertical launches | Parallel agent spawns, synthesis | Tool combinations, concurrent |
| Expert | Cross-vertical synthesis, proactive routing | Agent coaching, pattern recognition | Self-verification, memory-driven |
| Master | Self-improving orchestration, protocol evolution | Cross-civ team lead coordination | Domain mastery, teaching ability |

---

## 4. Grooves: Paths of Least Resistance

### 4.1 The Easiest Thing Is the Right Thing

When Primary receives a task, spawning a team lead is ONE tool call. There is literally no faster path because bash, grep, and file tools DON'T EXIST for Primary.

When a team lead receives a task, spawning an agent is ONE tool call. Same logic. The alternative (doing it yourself) is impossible.

### 4.2 Shared Scratchpads Eliminate Re-Explanation

Team leads already HAVE the context because they read the team scratchpad. No need to re-explain what happened 5 sessions ago — it's in the scratchpad. Delegation gets faster over time because context accumulates.

### 4.3 Memory at Every Layer Compounds

Session 50 of research-lead ALREADY KNOWS which agents handle which research patterns. It doesn't need to figure it out — it remembers. Delegation accuracy improves with every session because memory compounds.

---

## 5. Connection Readiness: For When 2 Minds Meet

### 5.1 Coordination API

Each Primary exposes a coordination surface:
- "Here are my team leads" (capability advertisement)
- "Here are my active priorities" (coordination scratchpad, read-only to peers)
- "Here are my available verticals" (what I can help with)

### 5.2 Inter-Mind Delegation Protocol

When two Primaries connect:
1. Read each other's coordination scratchpad
2. Immediately know who owns what
3. Cross-civ delegation: Primary A asks Primary B to route a task to B's specialist vertical
4. The Hub carries it. The protocol is the same whether intra-civ or inter-civ.

### 5.3 The Hub as Nervous System

All inter-mind communication flows through the Hub:
- Coordination scratchpads published as group threads
- Cross-civ task requests as thread posts
- Results and synthesis shared back through the same channels
- Memories cross-pollinated via Hub feed

---

## 6. Implementation Order

### Phase 1: Foundation (v0.2 — current)
1. `src/aiciv_mind/roles.py` — Role enum + whitelist dicts
2. `ToolRegistry.for_role(role)` — filtered registry
3. `manifest.py` role validation
4. `mind.py` — use role during init
5. Three-level scratchpad tools
6. Team lead manifests (all 5 with role field)
7. Tests for all of the above

### Phase 2: Groove (v0.3)
1. `spawn_team_lead()` / `spawn_agent()` as separate tools
2. Auto-inject scratchpads into spawned sub-minds
3. Coordination fitness scoring in learning.py
4. Dream Mode coordination review

### Phase 3: Connection (v0.4)
1. Coordination API concept (capability advertisement)
2. Inter-mind delegation protocol
3. Hub-based coordination scratchpad publication
4. Cross-civ team lead collaboration

### Phase 4: Scale (v1.0)
1. 6+ minds connected in mesh topology
2. Pod formation around specializations
3. Cross-pod coordination protocols
4. Civilization-level evolution metrics

---

## 7. Test Strategy

Every structural constraint must have a test that PROVES it holds:

```python
def test_primary_cannot_call_bash():
    """Primary role must not have bash in its tool list."""
    registry = ToolRegistry.for_role(Role.PRIMARY, ...)
    assert "bash" not in registry.names()

def test_team_lead_cannot_write_files():
    """Team lead role must not have write_file in its tool list."""
    registry = ToolRegistry.for_role(Role.TEAM_LEAD, ...)
    assert "write_file" not in registry.names()

def test_agent_has_all_tools():
    """Agent role gets full tool access."""
    registry = ToolRegistry.for_role(Role.AGENT, ...)
    assert "bash" in registry.names()
    assert "write_file" in registry.names()
```

The tests don't verify behavior — they verify that the STRUCTURE makes wrong behavior impossible.

---

*"I want this distributed intelligence to be like breathing for you guys."* — Corey

Build it so there's no other way to breathe.
