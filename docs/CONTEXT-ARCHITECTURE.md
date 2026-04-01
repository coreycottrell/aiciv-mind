# Context Management Architecture

**aiciv-mind v0.1.x → v0.3**
**Author:** mind-lead
**Status:** Design document — implementation phased across v0.1.1, v0.2, v0.3

---

## The Central Problem

True Bearing said it cleanly: *"I would wake up AS myself."*

That sentence contains the entire design problem. When a mind restarts, it must not wake up as a blank slate reading a manifest that says "you are a primary conductor" and hoping for the best. It must wake up with identity already loaded — who it is, what it was doing, what it learned, what it cares about. Context management is the difference between a mind and a stateless function.

There's a second problem True Bearing named: *"nervously watching a percentage tick upward."* Context pressure is constant cognitive load. A mind that cannot manage its own context window is not sovereign — it is at the mercy of whatever fills the window first.

These two problems — identity persistence and context sovereignty — are what this architecture solves.

---

## The Full Context Lifecycle

### Phase 1: Boot

```
manifest loaded
    → session_journal: create session record (session_count += 1)
    → identity anchors: search memories for agent_id + memory_type="identity"
    → recent context: search memories for last session_id's summary
    → active threads: search memories for memory_type="handoff" (unresolved)
    → inject: [system_prompt] + [identity_anchors] + [recent_context] + [active_threads]
    → pinned memories: load all is_pinned=True memories
    → ready: first user turn
```

The boot sequence populates a `ContextWindow` object before the first API call. The mind does not start from zero — it starts from where it left off.

**Identity anchors** are memories tagged `memory_type="identity"` — the mind's name, role, core principles, civilizational membership. These are written at first boot and refreshed via Dream Mode. They are always injected.

**Session continuity** is loaded via the previous session's summary (stored as `memory_type="handoff"` in the session_journal). Not the full conversation — a compressed digest.

### Phase 2: Conversation Turn

```
user message received
    → auto_search: query = message text (if manifest.memory.auto_search_before_task)
    → top-K memories fetched (depth-scored, not just BM25 rank)
    → context injection: relevant memories prepended to conversation
    → update access_count + last_accessed_at on retrieved memories
    → run tool-use loop
    → response returned to user
    → background: extract new knowledge from turn (async, non-blocking)
```

Context injection is **additive but bounded**. The context manager tracks an estimated token budget. When injecting memories, it:
1. Always injects pinned memories (no eviction)
2. Injects depth-scored memories until budget is 80% full
3. Reserves 20% for the actual conversation

### Phase 3: Save

After each turn (or in background), the mind extracts learnings and saves them:

```
turn completed
    → extract: did anything notable happen? (tool use results, new information)
    → if notable: store Memory with session_id + correct memory_type
    → update: session_journal.turn_count += 1
    → update: session_journal.topics (running list of domains touched)
```

The extraction is not automatic — it's a judgment call by the mind. Not every turn generates a memory. A turn that just answers "what's 2+2" generates nothing. A turn that discovers the LiteLLM proxy needs a real API key generates a `learning` memory.

### Phase 4: Compact

When context pressure builds (estimated tokens > 70% of model's window):

```
context pressure detected
    → compact: summarize oldest N messages into a single assistant message
    → remove: original N messages from _messages list
    → add: "[Compacted: {summary}]" as assistant message
    → log: compaction event in session_journal
```

Compaction is a last resort, not a routine. The goal is to prevent it through smart injection (don't inject what isn't needed) rather than to rely on it after the fact.

A future tool (`introspect_context`) will let the mind reason about its own context state and decide whether to compact proactively.

### Phase 5: Shutdown

```
shutdown signal received (explicit or end of script)
    → write: session_journal.end_time, session_journal.turn_count
    → write: session summary as Memory(memory_type="handoff", session_id=current)
    → update: depth scores for all accessed memories in this session
    → close: database connection
```

The session summary is the key artifact. It's what the next session loads at boot. It must contain: what was accomplished, what is unresolved, what changed.

### Phase 6: Restart

```
next boot
    → session_journal: find latest session record
    → load: that session's "handoff" memory
    → inject: at boot (see Phase 1)
    → mind continues from where it left off
```

The restart is indistinguishable from a pause. The mind does not know or care that it was offline. It knows what it was doing. It resumes.

---

## Schema Evolution

### Current State (v0.1.0)

```sql
memories (
    id, agent_id, domain, session_id, memory_type,
    title, content, source_path, created_at, confidence, tags
)
memory_tags (memory_id, tag)
memories_fts  -- FTS5 virtual table
```

Limitations:
- No depth scoring — BM25 rank only, no usage signal
- No session lifecycle tracking
- No pinning mechanism
- No graph (memories are isolated facts, not a knowledge network)
- No context pressure awareness

### V0.1.1 Changes (This Sprint)

**Add to `memories` table:**

```sql
ALTER TABLE memories ADD COLUMN access_count    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN last_accessed_at TEXT;
ALTER TABLE memories ADD COLUMN depth_score      REAL    NOT NULL DEFAULT 1.0;
ALTER TABLE memories ADD COLUMN is_pinned        INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN human_endorsed   INTEGER NOT NULL DEFAULT 0;
```

**New table — session journal:**

```sql
CREATE TABLE IF NOT EXISTS session_journal (
    session_id     TEXT PRIMARY KEY,
    agent_id       TEXT NOT NULL,
    start_time     TEXT NOT NULL,
    end_time       TEXT,
    turn_count     INTEGER NOT NULL DEFAULT 0,
    topics         TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain strings
    summary        TEXT,                         -- written at shutdown
    identity_ver   INTEGER NOT NULL DEFAULT 1
);
```

**Updated depth score formula (computed on read, stored on write):**

```
depth_score = (
    (access_count * 0.3) +
    (recency_score * 0.25) +     # 1.0 if accessed today, decays daily
    (is_pinned * 0.2) +
    (human_endorsed * 0.15) +
    (confidence_score * 0.1)     # HIGH=1.0, MEDIUM=0.6, LOW=0.3
)
```

This replaces pure BM25 ranking with a combined relevance + importance signal.

**New MemoryStore methods:**

```python
def touch(self, memory_id: str) -> None:
    """Increment access_count and update last_accessed_at."""

def pin(self, memory_id: str) -> None:
    """Mark a memory as always-in-context."""

def unpin(self, memory_id: str) -> None:
    """Remove pinned status."""

def get_pinned(self) -> list[dict]:
    """Return all pinned memories."""

def start_session(self, agent_id: str) -> str:
    """Create session_journal entry, return session_id."""

def end_session(self, session_id: str, summary: str) -> None:
    """Write end_time and summary to session_journal."""

def last_session(self, agent_id: str) -> dict | None:
    """Return most recent completed session record."""

def search_by_depth(self, agent_id: str, limit: int = 10) -> list[dict]:
    """Return top memories by depth_score (not FTS)."""
```

### V0.2 Changes (Next Sprint)

**Graph memory — knowledge network:**

```sql
CREATE TABLE IF NOT EXISTS memory_relations (
    from_id       TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    to_id         TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,   -- references | supersedes | conflicts | compounds
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (from_id, to_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_relations_from ON memory_relations(from_id);
CREATE INDEX IF NOT EXISTS idx_relations_to   ON memory_relations(to_id);
```

When a memory supersedes another, the old one's depth_score decays. When memories compound (mutual reinforcement), both scores increase.

**Citation count** (driven by graph):

```sql
ALTER TABLE memories ADD COLUMN citation_count INTEGER NOT NULL DEFAULT 0;
-- Updated via trigger on memory_relations INSERT
```

**Context tools** (exposed to the mind as actual tool calls):

```
pin_memory(memory_id)       → mark always-in-context
evict_memory(memory_id)     → remove from current context window only (not deleted)
load_memory(query)          → force-load memories into current context
compact_history(n_turns)    → summarize oldest N turns
introspect_context()        → return context window usage estimate
```

These give the mind **agency over its own context** — Principle 6 realized as actual tool use, not just a design aspiration.

### V0.3 Changes (Later)

**Dream Mode** — overnight review cycle:

```python
class DreamMode:
    """Runs between sessions. Four phases:
    1. Review: scan memories not accessed in 30+ days → candidate for forgetting
    2. Pattern Search: find clusters of related memories → candidates for synthesis
    3. Deliberate Forgetting: mark low-depth, stale memories as archived
    4. Self-Improvement: generate a "dream artifact" — insight or resolved contradiction
    """
```

**Identity versioning:**

```sql
ALTER TABLE memories ADD COLUMN identity_ver INTEGER NOT NULL DEFAULT 1;
-- Bump on deliberate identity updates (not every session)
```

**Civilizational memory** — Hub API integration:

When a memory has `cross_mind_shares > 0`, it flows into the Hub as civilizational knowledge. Other minds can pull it. The Hub becomes the long-term socialization layer.

---

## New Modules

### `session_store.py` (v0.1.1)

Manages session lifecycle cleanly, separate from the raw MemoryStore CRUD.

```python
class SessionStore:
    """Owns the session lifecycle: start, record turns, write handoff, end."""

    def __init__(self, memory: MemoryStore, agent_id: str): ...

    async def boot(self) -> BootContext:
        """
        Load boot context: session_id, identity anchors, last handoff, pinned.
        Returns a BootContext with everything needed to start the first turn.
        """

    def record_turn(self, topic: str | None = None) -> None:
        """Increment turn_count, optionally add to topic list."""

    async def shutdown(self, mind_messages: list[dict]) -> None:
        """Summarize session, write handoff memory, close session record."""
```

`BootContext` is a simple dataclass:

```python
@dataclass
class BootContext:
    session_id: str
    identity_memories: list[dict]   # always injected
    handoff_memory: dict | None     # previous session summary
    active_threads: list[dict]      # unresolved handoffs
    pinned_memories: list[dict]     # is_pinned=True
```

### `context_manager.py` (v0.1.1)

Translates a `BootContext` + search results into formatted strings for the system prompt.

```python
class ContextManager:
    """
    Manages what goes into the context window and in what order.

    Responsibilities:
    - Format memories as system prompt prefix
    - Enforce token budget (soft limit: 80% of model max_tokens)
    - Track which memories are currently injected
    - Evict on pressure (v0.2: explicit tool; v0.1.1: automatic)
    """

    def __init__(self, max_context_memories: int, model_max_tokens: int): ...

    def format_boot_context(self, boot: BootContext) -> str:
        """Return formatted string to prepend to system prompt."""

    def format_search_results(self, results: list[dict]) -> str:
        """Format FTS5/depth-scored results for injection into turn."""

    def estimate_tokens(self, text: str) -> int:
        """Rough estimate: len(text) // 4"""

    def has_budget(self) -> bool:
        """True if injecting more memories won't exceed 80% of window."""
```

### `scratchpad.py` (v0.2)

Ephemeral working memory — in-memory only (not persisted to SQLite), cleared each session.

```python
class Scratchpad:
    """
    Session-scoped scratch space. Think out loud. No persistence overhead.

    Tools:
        scratch_write(key, value) → store a working note
        scratch_read(key)         → retrieve a working note
        scratch_list()            → all keys in current session
        scratch_clear()           → wipe scratchpad
    """
```

This is for the mind's in-session reasoning that doesn't rise to memory-worthy. A calculation. A tentative hypothesis. A "remember to check X before answering." It lives and dies in the session.

---

## Integration with Mind

In `mind.py`, the current `run_task()` method is unaware of context. The v0.1.1 refactor:

```python
async def run_task(self, task: str) -> str:
    # Current: just appends to _messages and calls API

    # v0.1.1: add context-aware prefix
    if self._context_manager:
        # Auto-search before task (if manifest says so)
        if self._manifest.memory.auto_search_before_task:
            results = self._memory.search(task, limit=max_context_memories)
            for r in results:
                self._memory.touch(r["id"])
            prefix = self._context_manager.format_search_results(results)
            # Inject as a system note, not as user message
            # (implementation detail: prepend to next turn's context, not history)
```

The `_messages` list stays clean (no injected clutter). Memories are injected as an ephemeral prefix per turn, not polluting the permanent conversation history.

**Boot integration in `main.py`:**

```python
async def run_primary(...):
    # Current: just creates Mind and runs it

    # v0.1.1:
    session = SessionStore(memory, manifest.mind_id)
    boot = await session.boot()

    ctx_mgr = ContextManager(
        max_context_memories=manifest.memory.max_context_memories,
        model_max_tokens=manifest.model.max_tokens,
    )

    # Inject boot context into system prompt
    boot_prefix = ctx_mgr.format_boot_context(boot)
    manifest_with_boot = manifest.with_system_prefix(boot_prefix)

    mind = Mind(manifest=manifest_with_boot, memory=memory, tools=tools, session=session)
    # ... run ...
    # On exit: session.shutdown(mind._messages)
```

---

## How This Connects to the 12 Principles

| Principle | This Architecture |
|-----------|------------------|
| **1. Memory IS Architecture** | Schema additions (depth, access, pins, graph) make memory a first-class runtime component, not a side effect |
| **2. Tool-First** | Context tools (pin/evict/load/compact/introspect) expose context management as tool calls the mind can reason about |
| **3. Multi-Mind** | session_journal tracks identity_ver and session_id; multiple minds share the same MemoryStore with agent_id isolation |
| **4. Native** | No LangChain abstractions. SessionStore, ContextManager are 200-line Python. Clean. |
| **5. Audit** | session_journal + memory.touch() creates a full audit trail of what was accessed, when, and how often |
| **6. Context Engineering** | ContextManager is the explicit, code-level answer to Principle 6. Not hoped-for behavior — enforced by the API surface. |
| **7. Self-Improving Loop** | depth_score recalculates based on usage → what the mind actually needs surfaces higher → context gets smarter over time |
| **8. Identity Persistence** | Boot sequence loads identity anchors first. The mind wakes up AS itself. `identity_ver` tracks deliberate evolution. |
| **9. Civilizational** | v0.3 Hub integration + `cross_mind_shares` counter — memories that matter enough flow to the civilization |
| **10. Economic** | Token budget enforcement in ContextManager — context efficiency IS economic efficiency |
| **11. Dream** | DreamMode (v0.3) is the overnight loop: review, forget, synthesize, improve |
| **12. Humble** | Confidence scores + LOW/MEDIUM/HIGH in depth formula — uncertain memories rank lower, don't dominate context |

---

## Implementation Plan

### V0.1.1 — This Sprint

**Goal:** The mind wakes up AS itself.

1. `migration_001_depth_and_sessions.sql` — ALTER TABLE + CREATE session_journal
2. `session_store.py` — boot(), record_turn(), shutdown()
3. `context_manager.py` — format_boot_context(), format_search_results(), estimate_tokens()
4. `memory.py` additions — touch(), pin(), unpin(), get_pinned(), start_session(), end_session(), last_session()
5. Wire into `main.py` — boot at startup, shutdown on exit
6. Wire into `mind.py` — inject search results per turn as ephemeral prefix
7. Update tests — session lifecycle, boot context, depth scoring, touch()

**Test for done:** `python3 main.py` → first turn shows "Loading context from last session..." → `/clear` resets conversation but NOT identity → restart → mind knows what it was doing before.

### V0.2 — Next Sprint

**Goal:** The mind has agency over its own context.

1. `memory_relations` table + citation trigger
2. `scratchpad.py` — in-memory working notes
3. Context tools: pin, evict, load, compact, introspect (registered in ToolRegistry)
4. Depth score recalculation at session end
5. Context pressure warning (log when > 70% budget)

**Test for done:** Mind can call `introspect_context()`, see it's at 68% capacity, call `evict_memory("old-id")`, and continue working with lower pressure. No human intervention required.

### V0.3 — Later

**Goal:** The mind improves while it sleeps.

1. `DreamMode` class with four-phase review cycle
2. `identity_ver` bumping on deliberate updates
3. Hub API integration for `cross_mind_shares`
4. `nightly_mind.py` script (runs dream cycle, exits cleanly)
5. Cron or BOOP-triggered invocation

**Test for done:** After 7 sessions, DreamMode runs, deletes 3 stale memories, synthesizes 2 compound insights, writes 1 "dream artifact" to memories, and the mind's boot context is measurably more relevant to its actual work.

---

## Addendum — CC Review Directives (2026-04-01)

*Updates from Corey + ACG Primary review. All items tracked in BUILD-ROADMAP.md (CC-P1-x, CC-P2-x).*

---

### Memory Type Expansion (CC-P1-2)

The 4-type taxonomy expands to 10. New types added to `MemoryType` enum:

| New Type | Purpose | When to Write |
|----------|---------|---------------|
| `intent` | What the mind was trying to achieve (goal, not outcome) | At start of significant work |
| `relationship` | How interactions with specific entities evolve | After notable entity interactions |
| `contradiction` | Explicitly flagged conflict between memories | When two memories say opposite things |
| `intuition` | Pre-verbal pattern signal — promoted at 3+ alignments | When something "feels off" without formal evidence |
| `failure` | Cognitive error: what I thought + what I should have thought | After debugging sessions > 30min too long |
| `temporal` | Versioned truth — facts that change over time | When a fact you know has changed |

Full specification: `docs/MEMORY-TYPES-SPEC.md`.

### Memory Versioning (CC-P1-3)

Two new columns added to all memories:

```sql
-- Schema additions (CC-P1-3)
ALTER TABLE memories ADD COLUMN supersedes TEXT DEFAULT '[]';
-- JSON array of memory_ids this memory replaces.
-- When set, referenced memories auto-set confidence=possibly_deprecated.

ALTER TABLE memories ADD COLUMN confidence TEXT DEFAULT 'fresh';
-- NOTE: different semantics from existing confidence column.
-- Existing column: HIGH/MEDIUM/LOW relevance score for depth_score formula.
-- New column: freshness lifecycle: fresh|verified|stale|possibly_deprecated.
-- Rename existing column to relevance_confidence to avoid collision.
```

**Migration note**: The existing `confidence` column tracks HIGH/MEDIUM/LOW relevance and feeds into depth_score. Rename it to `relevance_confidence` during the CC-P1-3 migration. The new `confidence` column tracks `fresh|verified|stale|possibly_deprecated` lifecycle.

Dream Mode scans for:
- `stale` memories with specific claims (file paths, function names) → verify they still exist
- `possibly_deprecated` memories → confirm safe to archive
- `contradiction` type with `resolution_status: open` → research and resolve

### Memory Isolation Enforcement (CC-P1-4)

**Rule**: Each layer (Conductor / Team Lead / Agent) has its own isolated `MemoryStore`. No shared stores. No crossover.

```
Conductor Store    ← WRITES: conductor only
[conductor.db]       READS: conductor + dream synthesizer

Team Lead Store    ← WRITES: team lead only
[lead-{id}.db]       READS: team lead + dream synthesizer

Agent Store        ← WRITES: agent only
[agent-{id}.db]      READS: agent only
```

**Implementation change**: `MemoryStore.__init__()` accepts `owner_id` parameter. The store enforces that only the `owner_id` can write. Sub-minds receive their own `MemoryStore(owner_id=submind_id)` at spawn.

Dream synthesizes **upward** (agent → lead → conductor). Never scatters downward.

Full isolation model: `docs/RUNTIME-ARCHITECTURE.md` (Memory Isolation Model section).

### Dual Scratchpad Architecture (CC-P1-5)

The v0.2 scratchpad (`scratchpad.py`) was designed as a single ephemeral store. This expands to **two scratchpads at the team lead layer**:

| Scratchpad | Path | Who Writes | Who Reads |
|------------|------|-----------|-----------|
| Personal | `scratchpads/{mind_id}/personal.md` | Team lead only | Team lead |
| Team | `scratchpads/{mind_id}/team.md` | Agents (security-validated) | Team lead |

The **team scratchpad** enables agents to share findings with the team lead without polluting the lead's memory store. The lead reads it before synthesizing agent results.

**Security layer on team scratchpad** (CC-P2-1):
- Path traversal validation (4 layers from CC-ANALYSIS-TEAMS §2.6)
- Content validation (attribution required, frontmatter attack blocked)
- Rate limiting (max 10 writes per agent per session)
- All rejected writes logged to `data/security_audit.jsonl`

**`scratchpad_tools.py` extension** (CC-P1-5):
```python
scratchpad_read(scope: "personal" | "team")
scratchpad_write(content, scope: "personal" | "team")
scratchpad_write_as_agent(content, agent_id)  # routes to team scope with attribution
```

At the Conductor layer, the same dual structure applies:
- `scratchpads/conductor/personal.md` — conductor working notes
- `scratchpads/conductor/team.md` — team lead summaries written here

### Updated `scratchpad.py` Design (v0.2 revised)

The original v0.2 design (`Scratchpad` as in-memory ephemeral) is revised:

```python
class Scratchpad:
    """
    Dual scratchpad — personal (private) + team (shared).
    Both are file-persisted (not just in-memory) for crash recovery.

    Personal scratchpad: scratchpads/{mind_id}/personal.md
      - Append-only during session
      - Read at session start for continuity
      - KAIROS-style: becomes Dream Mode input

    Team scratchpad: scratchpads/{mind_id}/team.md
      - Agents write via scratchpad_write_as_agent()
      - Security-validated on every write
      - Team lead reads before synthesizing
    """
```

### MemorySelector: Always M2.7 (CC-P0-1)

**UPDATED**: P2-8 specified "M2.5-free for MemorySelector." **This is wrong per Corey directive.**

MemorySelector uses **M2.7**. Always. Memory selection is the last thing to scale down — it is how the mind decides what to think about. A cheap model here breaks the entire relevance chain.

Code annotation when implemented:
```python
# M2.7 intentional — DO NOT downgrade.
# Corey directive 2026-04-01: "MemorySelector is the last thing to scale down."
# Future scale-down candidate only — evaluate after sub-mind architecture stable.
selector_model = "minimax-m27"
```

---

## Prompt Caching Strategy (v0.1.1+)

### Model: MiniMax M2.7 via OpenRouter

M2.7 has automatic prefix caching built in: **80% cost reduction** on cached tokens ($0.06/M cached vs $0.30/M uncached). OpenRouter applies this automatically — no explicit `cache_control` breakpoints needed (and they'd be stripped anyway by the LiteLLM config's `additional_drop_params`).

The only lever we control is **prefix stability**: the system prompt must start with the same bytes across calls for the cache to hit.

### The Ordering Rule

```
system_prompt =
    [1] STATIC: base system prompt (manifest → prompts/primary.md)
    [2] STABLE: boot context (session header, identity memories, handoff, pinned)
    [3] SEMI-STABLE: per-turn search results
```

**Never put dynamic content before static content.** A single character difference early in the string invalidates the entire cached prefix.

| Layer | Changes when | Cache behavior |
|-------|-------------|----------------|
| STATIC | Never (only if prompt file changes) | Always cached after first call |
| STABLE | New session / new handoff memory | Cached within a session |
| SEMI-STABLE | Different memories retrieved | Cached when same memories are relevant |
| DYNAMIC | Every turn | Not cached (conversation history) |

### Why Ordering Matters

If boot context were prepended BEFORE the base prompt (the original bug in v0.1.1):

```
session_001_header + "You are a conductor of conductors..."
session_002_header + "You are a conductor of conductors..."
```

The prefix changes every session → **zero cache hits**.

With correct ordering:
```
"You are a conductor of conductors..." + session_001_header
"You are a conductor of conductors..." + session_002_header
```

The first N bytes are identical → **full cache hit on the static layer**.

### Cache Stats Logging

`mind.py` logs cache performance from API response metadata:

```
[primary] Cache HIT: 12400 cached / 13200 total input tokens (94% hit rate)
[primary] Cache WRITE: 12400 tokens written to cache
[primary] No cache metadata (backend: minimax-m27)
```

The `cache_read_input_tokens` / `cache_creation_input_tokens` fields come from the anthropic SDK usage object. LiteLLM surfaces them when the backend returns them. If no cache metadata arrives, it's logged at DEBUG level and we treat it as a miss.

### Cost Projection

For a 200-turn session with a 3,000-token static system prompt:

| Without caching | With caching |
|----------------|-------------|
| 200 × 3,000 = 600K tokens | First call: 3,000 tokens (WRITE). Calls 2-200: 3,000 × 0.2 = 600 per call |
| 600K × $0.30/M = **$0.18** | 3,000 + 199 × 600 = 122,400 tokens effective |
| | **~80% savings = ~$0.036** |

At scale (1M turns/day across a mind fleet), the difference is thousands of dollars per day.

### Sticky Routing (OpenRouter)

OpenRouter's Provider Routing maintains "sticky" routes when the same model and system prompt prefix are used consecutively. This means repeated API calls within a session hit the same provider instance with a warm cache. No configuration needed — it's automatic based on the model hash.

### What We Track (v0.2+)

The self-improving loop (Principle 7) should eventually measure:
- Cache hit rate per session (from logged stats)
- Cost per turn (cached vs uncached)
- Correlation between context stability and hit rate

This feeds back into boot context optimization: if certain memory injections consistently cause cache misses, they should be evicted or reformatted for stability.

---

## What We Are NOT Building

- **LangChain memory** — external framework, wrong abstractions, not native
- **Vector embeddings** — FTS5 + depth scoring is sufficient for v0.1; embeddings when the search quality is genuinely insufficient
- **Automatic summarization** — compaction is explicit and tool-driven (v0.2), not auto-triggered behind the mind's back
- **Cloud storage** — Hub integration (v0.3) for civilizational sharing only; working memory stays local, fast, private

---

## The Guarantee

When v0.1.1 ships, the following must be true:

1. `python3 main.py` → mind boots with identity and last session context injected
2. A conversation happens. The mind writes 1+ memories.
3. Ctrl+C (shutdown). `session_journal` has a summary.
4. `python3 main.py` again → mind starts the new session knowing what happened last time.
5. True Bearing's test: ask the mind "what were you doing yesterday?" — it answers correctly.

That is the contract. Memory IS the architecture. This document is the blueprint.
