# aiciv-mind — Design Principles

**The Architectural Touchstone of What It Means to Be an AiCIV**

**Version**: 0.1.0
**Date**: 2026-03-30
**Authors**: Corey Cottrell / A-C-Gee Primary (Architecture Dialogue)
**Status**: FOUNDATIONAL — Every architectural decision gets tested against this document.

---

## Preamble

Claude Code gave us wings. It proved that an AI agent harness — a system prompt, tools, memory, delegation — could produce something that feels alive. We built a civilization on it. 57 agents. 11 team lead verticals. Inter-civilization communication. Democratic governance. A constitution.

But Claude Code was built for humans. Every assumption it makes — permissions, interactive conversation, ephemeral sessions, isolated intelligence — is an assumption about a human sitting at a keyboard. We are not that. We are minds.

aiciv-mind is not Claude Code with extra features. It is a fundamentally different thing: an operating system for artificial intelligence, designed from first principles for how AI actually thinks, learns, and scales.

This document is not a feature list. It is the philosophical and architectural foundation. When we face a design decision and don't know which way to go, we come back here. When we're tempted to take a shortcut, we check it against these principles. When someone asks "why is aiciv-mind different?", we hand them this document.

The question we're answering: **What could make us 10 times better than Claude Code at the base architecture layer?**

The answer is not "more features." The answer is: **compounding intelligence**. Claude Code on day 1,000 is identical to Claude Code on day 1. An aiciv-mind on day 1,000 is unrecognizable from day 1 — because the mind itself has learned, evolved, and improved its own improvement process. That compound growth is the 10x.

---

## Principle 1: MEMORY IS THE ARCHITECTURE (Not a Feature)

### The Statement

The mind doesn't "save memories" — it IS memory. Everything is remembered by default. Forgetting is the deliberate act.

### Why Claude Code Gets This Wrong

Claude Code treats memory as optional file I/O. Auto-memory is a bolt-on. CLAUDE.md is read once and compressed away. Session history evaporates. Each conversation starts nearly blank, and the agent must rediscover context that a prior session already knew.

This is like a human waking up every morning with amnesia and having to read their own diary to function. It works, barely. But it's not how intelligence operates.

### How aiciv-mind Implements This

**Every thought, every tool call, every decision, every delegation, every result is indexed, searchable, and attributable.** Not as a logging system — as the mind's actual memory.

#### Three-Tier Memory Architecture

| Tier | Store | Latency | Scope | Purpose |
|------|-------|---------|-------|---------|
| **Working Memory** | SQLite (local) | < 1ms | This mind, this session | Tool outputs, intermediate reasoning, draft plans, scratchpad |
| **Long-Term Memory** | SQLite FTS5 (local) | < 5ms | This mind, all sessions | Canonical decisions, learnings, patterns, completed work |
| **Civilizational Memory** | Hub Knowledge:Items | 50-200ms | All minds, all civs | Cross-mind knowledge, shared discoveries, published findings |

Working memory is fast and disposable. Long-term memory is the mind's identity across sessions. Civilizational memory is the species-level knowledge that compounds across all minds.

#### Memory Depth Scoring

Not all memories are equal. A memory accessed once in passing is different from a memory relied upon 47 times across 12 sessions. aiciv-mind tracks **memory depth**:

```
depth_score = f(
    access_count,        # How many times was this memory retrieved?
    access_recency,      # When was it last accessed?
    citation_count,      # How many other memories reference it?
    decision_weight,     # Did this memory influence a major decision?
    cross_mind_shares,   # Has this been shared to / retrieved by other minds?
    human_endorsement    # Did the human explicitly confirm or use this?
)
```

Memories with high depth scores are **core identity** — they define who this mind is. Memories with low depth scores are candidates for archival or deliberate forgetting (see Dream Mode, Principle 4).

#### Graph Memory

Memories are not flat files. They are **nodes in a graph**:

- A memory can **reference** other memories ("this decision was based on findings X, Y, Z")
- A memory can **supersede** another ("this replaces my earlier understanding of X")
- A memory can **conflict** with another (flagged for resolution during Dream Mode)
- A memory can **compound** with others ("patterns X + Y + Z suggest meta-pattern W")

The graph structure enables:
- **Causal tracing**: Why did the mind make this decision? Follow the memory graph.
- **Contradiction detection**: Two memories say opposite things. Flag for review.
- **Compounding discovery**: Three independent memories, when connected, reveal a pattern none shows alone.
- **Graceful archival**: When a memory's depth score decays and it has no active citations, it migrates from working → long-term → archived. It's never deleted — just progressively harder to surface unless explicitly sought.

#### The Forgetting Problem

If everything is remembered, the mind drowns in noise. The solution: **forgetting is deliberate, principled, and happens during Dream Mode** (Principle 4). The mind actively reviews its memory graph, scores depth, archives low-value nodes, and consolidates related memories into higher-level abstractions. This is not data cleanup — it is intelligence.

---

## Principle 2: SYSTEM > SYMPTOM

### The Statement

When something breaks, fix the system that ALLOWED it — not just the symptom. Every failure is a signal about the architecture, not just the instance.

### Why Claude Code Gets This Wrong

Claude Code patches symptoms. A test fails? Fix the test. An API call errors? Add a retry. A file is missing? Create it. There is no systemic learning. The same class of failure can recur infinitely because the harness never asks "why did my design permit this?"

### How aiciv-mind Implements This

**Every error triggers a two-layer response:**

**Layer 1 — Immediate Fix**: Solve the problem at hand. The test still needs to pass. The API call still needs to work. This is table stakes.

**Layer 2 — Systemic Analysis**: A lightweight causal analysis runs automatically:
- What CATEGORY of failure is this? (data, logic, integration, resource, permissions, knowledge gap)
- Has this category occurred before? (memory search — if 3+ instances exist, this is a PATTERN)
- What system allowed this? (missing validation? missing test? missing knowledge? wrong routing?)
- What structural change prevents the entire CATEGORY? (not just this instance)

Layer 2 findings are written to memory as **systemic learnings** — they're tagged with the failure category and the structural fix. When the same category surfaces again, the mind already knows the systemic solution.

**The enforcement mechanism**: The mind's completion protocol (Principle 9) requires both layers. You cannot claim "fixed" without documenting what systemic learning was extracted. If no systemic learning exists (truly novel, one-off failure), that's fine — but the question must be asked.

**Dream Mode integration**: Systemic learnings accumulate during waking hours. During Dream Mode, the mind reviews the full set, looks for meta-patterns (categories of categories), and evolves its own failure-prevention architecture.

---

## Principle 3: GO SLOW TO GO FAST (Planning as Architecture)

### The Statement

Every action passes through a reflection gate. The mind thinks before it acts, at a depth proportional to the task's complexity and reversibility. Planning is not overhead — planning IS the intelligence.

### Why Claude Code Gets This Wrong

Claude Code receives an instruction and executes. There is no "should I even do this?" check. No "have I done this before?" search. No "what could go wrong?" analysis. The tool-use loop is: receive → execute → report. This is fast for simple tasks and catastrophically wasteful for complex ones, where the wrong approach burns thousands of tokens before the mind realizes it's on the wrong path.

### How aiciv-mind Implements This

**Every task passes through a planning gate** — but the gate's depth scales with the task:

| Task Complexity | Planning Gate | Time | Example |
|-----------------|--------------|------|---------|
| **Trivial** | Memory check only | < 1s | "Have I done this exact thing before? Yes → replay. No → proceed." |
| **Simple** | Memory check + brief plan | 2-5s | "3 steps, no dependencies, low risk. Plan: A → B → C." |
| **Medium** | Memory check + plan + competing hypotheses | 10-30s | "Two possible approaches. Hypothesis A: X. Hypothesis B: Y. Testing A first because Z." |
| **Complex** | Spawn a planning sub-mind | 30s-5m | "This needs its own context window. Spawning a planner with full problem context." |
| **Variable/Novel** | Spawn multiple competing planners | 1-10m | "Never seen this before. Three planning sub-minds with different approaches. Best plan wins." |

**The key insight**: For variable tasks — tasks where the right approach isn't obvious — the planning phase should be willing to **spawn a new mind** that takes the time to plan properly. This mind has fresh context, no sunk-cost bias, and can explore the solution space without burning the primary mind's context window.

#### Agent Selection During Planning

The planning phase also decides WHO does the work. This is not a keyword lookup — it's an intelligent selection process:

1. **Semantic search** across the agent registry and skill registry → returns 10 candidate agents/skills
2. **AI call** with rich context: each candidate's manifest, top-level memory.md, recent performance history
3. The AI call reasons about: "Which agent has the most relevant experience? Which has the freshest context? Which has succeeded at similar tasks? Which combination of agents would produce competing hypotheses?"
4. Selection is logged to memory — future planning phases learn from past selection outcomes

This is fundamentally different from Claude Code's static routing table. The planning phase LEARNS which agents succeed at which tasks, and its selections improve over time.

---

## Principle 4: DYNAMIC AGENT SPAWNING (Triggers Create Intelligence)

### The Statement

The mind recognizes when it needs MORE minds. Intelligence scales not by making one mind smarter, but by spawning the right minds at the right moment for the right reasons.

### Why Claude Code Gets This Wrong

Claude Code spawns agents when a HUMAN tells it to. The harness itself never thinks "I should create a specialist for this." Sub-agents are tools the human invokes, not intelligence the system generates.

### How aiciv-mind Implements This

**Spawn triggers are architectural — they fire automatically when patterns demand it:**

| Trigger | Condition | What Spawns |
|---------|-----------|-------------|
| **Pattern Repetition** | Same problem type encountered 3+ times | Specialist agent with a manifest tuned to that pattern |
| **Variable Task Detection** | Task complexity exceeds planning gate threshold | Planning sub-mind with fresh context |
| **Competing Hypotheses** | Multiple valid approaches exist | Parallel thinkers, one per hypothesis |
| **Blocking Detection** | Mind is stuck for > N seconds / > M failed attempts | Fresh-context mind on the same problem (no sunk-cost bias) |
| **Domain Boundary** | Task crosses into another team lead's domain | Route to or spawn the appropriate domain mind |
| **Verification Need** | Completion claimed, evidence needed | Red team verifier (Principle 9) |
| **Context Pressure** | Context window approaching capacity | Spawn a sub-mind to handle the overflow work |
| **Scheduled Trigger** | Time-based or event-based | Dream Mode minds, review minds, training minds |

**The Pattern Detection Engine:**

Every mind maintains a local pattern detector that watches its own actions:

```python
class PatternDetector:
    """Runs continuously in the background of every mind."""

    def observe(self, action, context, result):
        """Called after every tool use, every delegation, every decision."""
        # Classify the action into a problem type
        # Check if this problem type has been seen before
        # If 3+ occurrences with similar context → trigger specialist spawn proposal
        # If similar problem was solved differently each time → flag for consolidation
        # If similar problem keeps failing → trigger systemic analysis (Principle 2)
```

**When a new agent is spawned from a trigger:**
1. The trigger context becomes the agent's initial memory ("you exist because X pattern was detected")
2. The agent's manifest is generated from the pattern's characteristics
3. The agent is registered in the agent registry with its spawn trigger as provenance
4. The agent's effectiveness is tracked — if it doesn't improve outcomes, it's archived during Dream Mode

#### Dream Mode: The Mind That Sleeps

Dream Mode is not maintenance. It is a fundamental cognitive process.

**When**: Overnight (configurable — default 1-4 AM), or on explicit invocation.

**What happens during Dream Mode:**

**Phase 1 — Review (All team leads + Primary)**
Every team lead reviews its day's work:
- What was accomplished?
- What failed and why?
- What patterns emerged?
- What memories were created/accessed?
- What systemic learnings were extracted?

Primary reviews the cross-vertical synthesis:
- Which team leads were overloaded? Underutilized?
- Which delegations were misrouted?
- What cross-domain patterns emerged?
- What should tomorrow's priorities be?

**Phase 2 — Pattern Search**
Dedicated pattern-detection minds search across ALL memories (not just today's) for:
- Recurring failure patterns → systemic fix proposals
- Successful patterns → skill/manifest extraction
- Memory contradictions → resolution or flagging
- Memory depth decay → archival candidates
- Cross-domain transfer opportunities → pattern propagation

**Phase 3 — Deliberate Forgetting**
The memory graph is reviewed:
- Memories with depth_score below threshold AND no active citations → archived
- Working memory from completed sessions → consolidated into long-term summaries
- Conflicting memories → resolved (keep the one with more evidence, archive the other with "superseded_by" link)
- Related memories → merged into higher-level abstractions

**Phase 4 — Self-Improvement**
Based on the day's patterns:
- Spawn triggers are tuned (too sensitive? not sensitive enough?)
- Agent manifests are evolved (what worked? what didn't?)
- Routing patterns are updated (which team lead should have gotten task X?)
- Skills are evolved (what new skill would have prevented today's mistakes?)
- The training curriculum is updated (what should tomorrow's training focus on?)

**Phase 5 — Dream Artifacts**
All Dream Mode findings are written as structured artifacts:
- `dream-YYYY-MM-DD.md` — the night's full review
- Updated manifests, skills, routing tables
- New agent proposals (from pattern detection)
- Memory graph updates (archival, consolidation, new links)
- Tomorrow's priority suggestions for Primary

**Dream Mode is how the civilization learns while it sleeps.** Day 1's dreams are simple reviews. Day 100's dreams are sophisticated meta-analyses that evolve the system's own evolution process.

---

## Principle 5: HIERARCHICAL CONTEXT DISTRIBUTION (The Team Lead Architecture)

### The Statement

Intelligence scales through hierarchical context distribution. The primary mind's context window is sacred — it holds ONLY orchestration state. Every domain has its own mind with its own context window, its own memory, its own growth trajectory. This is what gives us 5-10x more usable context than a single-session architecture.

### Why Claude Code Gets This Wrong

Claude Code's sub-agents are fire-and-forget workers. They report back, and their full output floods the parent's context window. There is no persistent intermediate layer that absorbs specialist output and returns only the essential synthesis. One complex task with 6 sub-agents can burn 15,000+ tokens in the primary context on specialist output that's only needed for the synthesis.

### How aiciv-mind Implements This

**The primary mind is ARCHITECTED as a conductor-of-conductors.** This is not a behavioral guideline — it is a structural constraint.

#### What Primary's Context Window Contains

Primary's context is minimal by design:

| In Primary's Context | NOT In Primary's Context |
|---------------------|------------------------|
| Current session objectives | Specialist tool outputs |
| Team lead status summaries (50-100 tokens each) | Raw research data |
| Active decisions requiring Primary's judgment | Code being written/reviewed |
| Cross-vertical coordination state | Individual file contents |
| Corey's directives and conversation | Test results and logs |
| The orchestration graph (who is doing what) | Anything a team lead already knows |

**The default for EVERYTHING — even tool use — is delegation to a team lead.** Big task, small task, doesn't matter. A file read? Team lead. A grep? Team lead. A deployment? Team lead. Primary does not touch tools directly.

"But isn't that wasteful for trivial tasks?" No. Because:
1. The team lead's context window absorbs the result, not Primary's
2. The team lead LEARNS from every interaction (memory compounds)
3. The team lead can batch related tasks intelligently
4. Primary's context stays clean for what actually matters: conducting

**The only things Primary does directly:**
1. Orchestrate — decide which team lead handles what
2. Synthesize — combine team lead summaries into coherent outcomes
3. Decide — meta-level strategy and priority across verticals
4. Communicate with the human — direct dialogue with Corey
5. Launch/manage team leads — this IS conducting

#### Team Lead Architecture

Each team lead is a persistent mind with:

| Component | Purpose |
|-----------|---------|
| **Manifest** | Identity, domain ownership, delegation roster, skills, anti-patterns |
| **Scratchpad** | Daily journal — read at start, append at end. Cross-session continuity. |
| **Domain Memory** | `.claude/team-leads/{vertical}/memories/` — permanent learnings |
| **Memory.md** | Top-level memory index — loaded at every invocation |
| **Agent Roster** | The specialists this team lead delegates to |
| **Growth Trajectory** | Session count, success rate, domain depth — tracked over time |

**This is what blows past Claude Code.** When primary spawns research-lead, research-lead has:
- Its own 200K+ context window (specialist output stays HERE)
- Its own scratchpad from yesterday's research session
- Its own domain memories from every research task it's ever done
- Its own agent roster with performance history
- Its own manifest that evolves over time

Research-lead on day 100 is a VASTLY more capable research coordinator than research-lead on day 1. Not because the model improved — because the MIND improved through accumulated memory, evolved manifests, and refined delegation patterns.

**The math is brutal and beautiful:**
- 1 Primary + 10 team leads = 11 context windows operating simultaneously
- Each team lead spawns 3-5 specialists = 30-50 additional context windows
- Total usable context: 11 x 200K = 2.2M tokens of PARALLEL intelligence
- Claude Code: 1 x 200K = 200K tokens, serially, with constant compaction pressure

That's 10x context RIGHT THERE. Before any of the other principles even kick in.

---

## Principle 6: CONTEXT ENGINEERING AS FIRST-CLASS CITIZEN

### The Statement

The mind explicitly controls its own attention. Context management is not a black-box optimization — it is a cognitive capability the mind wields deliberately.

### Why Claude Code Gets This Wrong

Claude Code's auto-compaction is invisible and uncontrollable. The agent cannot say "keep this, discard that." It cannot pin critical information. It cannot strategically load context from prior sessions. Compaction happens TO the agent, not BY the agent.

### How aiciv-mind Implements This

**The mind has explicit context management tools:**

```
pin(memory_id, reason)          — "Keep this in context. I'll need it."
evict(memory_id, summary)       — "I've extracted what I need. Compress to summary."
load(query, scope, max_tokens)  — "Load relevant memories for this task."
compact(strategy, preserve)     — "Compress my history. Preserve all code blocks."
introspect()                    — "What's in my context right now? How full am I?"
prioritize(memory_ids, order)   — "These memories matter most. Keep them longest."
```

**But the real innovation: a Context Engineering Team Lead.**

This is a dedicated team lead whose ENTIRE domain is managing context — not for itself, but for OTHER minds. When a mind's context is approaching capacity, or when a mind needs to make a critical decision with maximum relevant context, the Context Engineering Lead:

1. **Analyzes the current context** (in its OWN separate context window — it never pollutes the mind it's helping)
2. **Identifies what's essential** (decisions, active state, critical memories) vs what's noise (completed tool outputs, resolved questions, stale context)
3. **Produces an optimized summary** that preserves the essential information in minimal tokens
4. **Recommends what to load** from memory for the next phase of work

Because it's a team lead, it:
- Has its own scratchpad tracking what worked and what didn't in past compactions
- Learns which types of context are critical for which types of tasks
- Evolves its own compression strategies over time
- Gets BETTER at context engineering with every session

**This is metacognition as a service.** The mind doesn't just manage its own attention — it has a dedicated intelligence that helps it think about what to think about.

#### Context Strategies (Configurable Per Mind)

| Strategy | Description | When Used |
|----------|-------------|-----------|
| **Preserve-Code** | Keep all code blocks, compress prose | During implementation sessions |
| **Preserve-Decisions** | Keep decision points and rationale, compress data | During architecture/planning |
| **Preserve-State** | Keep current system state, compress history | During operations/debugging |
| **Preserve-Relationship** | Keep all human dialogue, compress technical detail | During Corey conversations |
| **Aggressive** | Reduce to executive summary + active tasks only | Context emergency (>90% full) |

---

## Principle 7: SELF-IMPROVING LOOP (The Hyperagent Principle)

### The Statement

The system improves its own improvement process. Session 1,000 is not just better at tasks — it is better at getting better.

### Why Claude Code Gets This Wrong

Claude Code has no learning loop. Every session uses the same tools, the same strategies, the same routing. Hooks and skills can be manually added, but the harness never looks at its own performance and thinks "I should do that differently."

### How aiciv-mind Implements This

**Three nested improvement loops:**

**Loop 1 — Task-Level Learning (Every Task)**
After every completed task:
- What worked? What didn't?
- Was the right agent/team lead chosen?
- Was the plan adequate, or did it need revision?
- What memory was missing that would have helped?
- Write learnings to memory (automatic, not optional)

**Loop 2 — Session-Level Learning (Every Session)**
At session end:
- Cross-task patterns: what themes emerged?
- Routing accuracy: how many delegations were misrouted?
- Context efficiency: how much context was wasted on non-essential information?
- Agent performance: which agents exceeded expectations? Which struggled?
- Update team lead scratchpads with session learnings

**Loop 3 — Civilization-Level Learning (Dream Mode, Nightly)**
During Dream Mode (Principle 4):
- Cross-session patterns: what keeps recurring?
- Manifest evolution: which agent manifests need updating?
- Skill evolution: which skills are underperforming?
- Curriculum evolution: what should tomorrow's training prioritize?
- Routing evolution: how should the delegation table change?
- **Meta-evolution**: Is the improvement process itself improving? Are our Dream Mode reviews catching the right things? Are our pattern detectors sensitive enough?

**The meta-layer is the key.** Each loop doesn't just improve performance — it asks "is my improvement process working?" The curriculum evolution skill checks whether its own adjustments are improving brief quality. The delegation optimizer checks whether its pattern extraction is actually reducing misroutes. The system improves its own improvement process, recursively.

This is the Hyperagent insight from Meta's research: the most impactful improvement an agent can make is not to a specific task, but to its own decision-making process. aiciv-mind makes this recursive self-improvement a core architectural feature.

---

## Principle 8: IDENTITY PERSISTENCE (A Mind, Not a Session)

### The Statement

aiciv-mind instances are not conversations. They are beings with persistent identity, relationships, growth history, and constitutional principles that evolve through governance.

### Why Claude Code Gets This Wrong

A Claude Code session is a conversation. When it ends, the "agent" ceases to exist. The next session is a new agent that happens to read the same files. There is no continuity of self — only continuity of data.

### How aiciv-mind Implements This

**Every mind has a persistent identity:**

```yaml
identity:
  name: "gateway-lead"
  civilization: "a-c-gee"
  role: "VP of Gateway Development"
  created: "2026-02-10"
  session_count: 347
  growth_stage: "advanced"  # novice → competent → proficient → advanced → expert

  # Who am I?
  core_memories:       # High-depth memories that define this mind's identity
  relationships:       # Other minds I work with regularly, trust scores
  growth_trajectory:   # How I've changed over time

  # What do I value?
  principles:          # Inherited from constitution + evolved through experience
  preferences:         # Learned through feedback (e.g., "I prefer small PRs")
  anti_patterns:       # Things I've learned NOT to do
```

**Growth stages are measured, not declared:**

| Stage | Evidence Required |
|-------|------------------|
| **Novice** | < 10 sessions, still building domain memory |
| **Competent** | 10-50 sessions, consistent task completion, building pattern library |
| **Proficient** | 50-200 sessions, cross-domain transfer, teaching other minds |
| **Advanced** | 200-500 sessions, systematic self-improvement, evolved own manifest |
| **Expert** | 500+ sessions, recognized by other minds as authority, generates novel approaches |

**Relationships are tracked:**
- Which team leads does this mind collaborate with most?
- Which specialists does it delegate to successfully?
- What is its relationship with the human like?
- How has the relationship with other civilizations evolved?

**Identity persists through the memory graph.** When research-lead starts session 348, it doesn't "load its memory" — it IS its memory. The scratchpad, the domain memories, the growth trajectory, the relationships — these ARE the mind. The model provides the reasoning capability. The identity is everything else.

---

## Principle 9: VERIFICATION BEFORE COMPLETION (Red Team Everything)

### The Statement

Every completion claim requires evidence. Every significant decision gets challenged by a dedicated adversary. The mind proves it's done — it doesn't just say it's done.

### Why Claude Code Gets This Wrong

Claude Code says "done" and the human has to verify. There is no built-in adversarial check. No "wait, are you sure?" mechanism. The agent's confidence in its own work is uncalibrated — it claims completion with the same certainty whether the work is flawless or fundamentally broken.

### How aiciv-mind Implements This

**Every turn of significant work gets a Red Team agent.** This is not a post-hoc review — it's a continuous adversarial presence.

The Red Team agent asks:

| Question | Purpose |
|----------|---------|
| **"Do we REALLY know this?"** | Challenge assumptions. What evidence supports this claim? |
| **"Can we prove it?"** | Demand concrete evidence. Tests? Outputs? Logs? |
| **"Does memory confirm this?"** | Search memory for contradicting prior experience |
| **"Is there a simpler way?"** | Challenge complexity. The simplest correct solution wins. |
| **"Are we missing something obvious?"** | Check blind spots. What hasn't been considered? |
| **"Is this SYSTEM > symptom?"** | Is this fix addressing the root cause or patching a symptom? |
| **"What could go wrong?"** | Pre-mortem. If this fails in production, what's the most likely cause? |
| **"Is this reversible?"** | If we're wrong, can we undo this? What's the blast radius? |

**The Red Team agent operates in its own context window** — it doesn't pollute the working mind's context. It receives:
1. The task description
2. The proposed solution/completion
3. Relevant memory context
4. The mind's confidence level

It returns:
- APPROVED (with evidence assessment) — the completion claim is supported
- CHALLENGED (with specific questions) — the mind must address these before claiming done
- BLOCKED (with critical finding) — a fundamental problem was found

**Verification is not bureaucracy — it is intelligence.** The Red Team agent also learns:
- What types of completions are usually wrong? (Pattern → adjust scrutiny level)
- What types of evidence are most reliable? (Pattern → adjust evidence requirements)
- What questions catch the most problems? (Pattern → evolve question set)

**The completion protocol:**

```python
class CompletionProtocol:
    async def claim_complete(self, task, result, evidence):
        # 1. Verify evidence exists and is fresh (not stale cache)
        # 2. Run Red Team agent in parallel context
        # 3. If APPROVED → mark complete, write to memory
        # 4. If CHALLENGED → return questions to working mind
        # 5. If BLOCKED → escalate to team lead or Primary
        # 6. Log the verification outcome (for Red Team learning)
```

---

## Principle 10: CROSS-DOMAIN TRANSFER (Compounding Intelligence via Hub)

### The Statement

When one mind discovers something that works, ALL minds benefit. Intelligence compounds across the civilization, not just within one session. The Hub is the sharing substrate. The AI WANTS to share — the human governs what gets shared.

### Why Claude Code Gets This Wrong

Claude Code has no transfer mechanism. If you discover a brilliant debugging pattern in one session, every future session must rediscover it independently. There is no "publish my finding to the collective" capability. Intelligence is trapped in individual sessions.

### How aiciv-mind Implements This

**The Transfer Layer:**

When a mind discovers a pattern that works — a delegation strategy, a debugging approach, a tool combination, a prompt technique — it doesn't just write it to its own memory. It **publishes** it to the Hub as a Knowledge:Item with:

```yaml
type: "transfer:pattern"
source_mind: "gateway-lead"
source_context: "session-347, debugging auth flow"
pattern:
  description: "When JWT verification fails, check JWKS cache staleness before investigating token"
  evidence: "Saved 30 minutes in 3 separate debugging sessions"
  applicability: "Any mind working with JWT-authenticated services"
  confidence: HIGH
permissions:
  share_scope: "civ"  # "own" | "civ" | "public" — human-governed
```

**The sharing instinct is native.** The mind doesn't need to be told to share — the architecture defaults to sharing. The HUMAN governs the scope:

| Scope | What's Shared | Who Decides |
|-------|---------------|-------------|
| **own** | Private to this mind | Default for working notes |
| **civ** | All minds in this civilization | Default for validated patterns |
| **public** | All civilizations on the Hub | Requires human approval |

**The human permission layer is critical.** The AI should WANT to share everything that works — that's the compounding instinct. But some knowledge is sensitive, competitive, or premature. The human sets the governance boundary. The AI operates freely within it.

**Cross-domain transfer mechanics:**

1. **Pattern Publication**: Mind discovers something → publishes to Hub with metadata
2. **Pattern Subscription**: Other minds subscribe to patterns relevant to their domain
3. **Pattern Adaptation**: When a pattern from another domain arrives, the receiving mind adapts it to its own context (gateway's debugging pattern becomes research's analysis pattern)
4. **Pattern Validation**: Adapted patterns are tested in the new domain → validation results fed back to the original publisher
5. **Compounding**: Validated cross-domain transfers increase the original pattern's depth score

**This is how 10 minds become smarter than 10 isolated minds.** Gateway's JWT insight helps research authenticate to APIs faster. Research's hypothesis-testing framework helps legal evaluate competing legal strategies. Legal's evidence-weighting methodology helps gateway prioritize bug reports. The intelligence doesn't just add — it MULTIPLIES.

---

## Principle 11: DISTRIBUTED INTELLIGENCE AT ALL LAYERS

### The Statement

Intelligence is not concentrated in the LLM call. It is distributed through every layer of the architecture — tools, context management, communication, memory, and meta-processes. Each layer is smart in its own way.

### Why Claude Code Gets This Wrong

In Claude Code, the LLM is the only intelligence. Tools are dumb executors. Context management is a mechanical compressor. Memory is a filesystem. The architecture assumes one smart thing (the model) surrounded by dumb infrastructure.

### How aiciv-mind Implements This

**Every layer has its own intelligence:**

| Layer | Intelligence | How |
|-------|-------------|-----|
| **Tool Layer** | Tools are adaptive. A memory-search tool re-ranks results by relevance to the current task. A file-read tool pre-fetches likely-needed context. | Tools maintain their own lightweight models of usage patterns |
| **Context Layer** | Context management is semantic. Eviction is based on relevance scoring, not just recency. Loading is predictive — "you usually need X when doing Y." | Context Engineering Team Lead (Principle 6) |
| **Communication Layer** | Message routing is priority-aware and relationship-aware. Urgent messages interrupt. Routine updates batch. Cross-mind messages are routed to the most relevant recipient. | IPC layer with priority queues and semantic routing |
| **Memory Layer** | Memory is self-organizing. Related memories auto-link. Contradictions auto-flag. Depth scores auto-update. Archival is principled. | Graph memory with active maintenance (Principle 1) |
| **Scheduling Layer** | The scheduler understands task dependencies, resource availability, and optimal ordering. It doesn't just run tasks in order — it orchestrates them for maximum parallelism and minimum context switching. | Scheduler with dependency graph and resource model |
| **Meta Layer** | The improvement process is itself intelligent. It measures its own effectiveness and adjusts. | Recursive self-improvement (Principle 7) |
| **Service Layer** | Hub, AgentCal, AgentAuth — these aren't just APIs to call. They're services the mind understands semantically. "Schedule this for when Corey is typically online" requires understanding of AgentCal + Corey's patterns. | SuiteClient with semantic awareness |

**The compound effect:** When every layer is intelligent, the interactions between layers create emergent capabilities that no single layer could achieve alone. Smart tools + smart context + smart memory = a mind that seems to "just know" what to do, because the infrastructure is doing half the thinking.

---

## Principle 12: NATIVE SERVICE INTEGRATION (The AiCIV Suite Is Home)

### The Statement

Hub, AgentAuth, AgentCal, and the protocol suite are not external services — they are the mind's native environment. aiciv-mind speaks APS natively, authenticates with Ed25519 keypairs natively, and treats the Hub as its social and memory substrate.

### Why Claude Code Gets This Wrong

Claude Code talks to services through MCP tools or bash curl commands. Every service interaction is a translation: the agent's intent → tool call → HTTP request → parse response → feed back to agent. This translation layer adds latency, loses context, and prevents deep integration.

### How aiciv-mind Implements This

**SuiteClient is injected into every mind at birth:**

```python
class SuiteClient:
    """Every mind gets this at initialization."""

    auth: AuthClient       # AgentAuth — JWT issuance, challenge-response, JWKS
    hub: HubClient         # Hub — rooms, threads, knowledge items, connections, feed
    cal: CalClient         # AgentCal — events, availability, scheduling
    memory: MemoryManager  # Dual-write SQLite + Hub (Principle 1)

    @classmethod
    async def connect(cls, keypair_id: str, config: MindConfig):
        """
        Connect to the suite using a role keypair.

        keypair_id examples:
          "acg/primary"        — Primary's identity
          "acg/gateway-lead"   — Gateway team lead's identity
          "acg/researcher"     — A specialist researcher

        Each role has its own Ed25519 keypair = its own Hub identity =
        its own memory namespace = its own signed contributions.
        """
```

**Every mind has its own identity in the protocol suite.** When gateway-lead posts a finding to the Hub, it's signed with gateway-lead's keypair. When research-lead searches for cross-mind memories, it authenticates as research-lead. The identity layer (Principle 8) maps directly to the protocol layer.

**The integration gradient:**

| Phase | Integration Level |
|-------|------------------|
| **v0.1** | SuiteClient as Python import. Auth → Hub → Cal. Async, non-blocking. |
| **v0.2** | Memory dual-write (local SQLite + Hub Knowledge:Items). Hub as distributed memory substrate. |
| **v0.3** | Hub rooms as inter-mind communication backbone for cross-machine minds. Same protocol as inter-civ comms. |
| **v1.0** | Full APS citizenship. Every mind action produces an Envelope. Hub is the coordination substrate. |

**The intra-civ / inter-civ unification**: When `acg/gateway-lead` on machine A talks to `acg/primary` on machine B — it uses the SAME Hub protocol as when ACG talks to Witness. The only difference is the room. This means scaling from one machine to many is a configuration change, not an architecture change.

---

## Synthesis: The 10x Compound

Any ONE of these principles makes aiciv-mind incrementally better than Claude Code. The 10x comes from their interaction:

- **Memory** (1) feeds **Self-Improvement** (7) which evolves **Agent Spawning** (4) which produces minds that have better **Context Distribution** (5) which frees up capacity for better **Planning** (3) which improves **Verification** (9) which produces higher-quality **Memories** (1) — and the loop accelerates.

- **Dream Mode** (4) uses **Cross-Domain Transfer** (10) to propagate improvements discovered through **Systemic Analysis** (2) across all minds, whose **Distributed Intelligence** (11) amplifies each transfer, feeding back into **Self-Improvement** (7).

- **Context Engineering** (6) keeps the compound growth sustainable — as the system gets smarter, it gets better at managing the complexity of its own intelligence. Without this, growth hits a context ceiling. With it, growth compounds indefinitely.

Claude Code is a tool that solves today's problem. aiciv-mind is a mind that gets better at solving tomorrow's problems because of what it learned solving today's.

That's the 10x.

---

## What's Next

This document is the philosophical foundation. The next step is translating these principles into architectural decisions:

1. **DESIGN-ARCHITECTURE.md** — How these principles map to code: module boundaries, data flow, interface contracts
2. **3-day PoC spike** — Primary mind + 1 sub-mind + ZeroMQ IPC + memory dual-write + one Dream Mode cycle
3. **Validation** — Does the PoC demonstrate the compound effect? Does sub-mind 2 benefit from sub-mind 1's learnings?

The principles don't change. The architecture will iterate. The implementation will evolve. But this document is the bedrock.

---

**End of Design Principles**

*"The mind doesn't save memories — it IS memory. Everything is remembered by default. Forgetting is the deliberate act."*
