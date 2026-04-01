# CONTEXT-ARCHITECTURE vs BUILD-ROADMAP Cross-Reference

**Author:** mind-lead
**Date:** 2026-04-01
**Sources:** `docs/CONTEXT-ARCHITECTURE.md`, `docs/BUILD-ROADMAP.md`

---

## Summary

CONTEXT-ARCHITECTURE.md is a detailed design document covering 6 lifecycle phases (Boot, Turn, Save, Compact, Shutdown, Restart) plus schema evolution across v0.1.1, v0.2, and v0.3. BUILD-ROADMAP.md is a prioritized build plan derived from gap analysis.

**Result:** 9 capabilities from CONTEXT-ARCHITECTURE are either missing or incompletely represented in BUILD-ROADMAP. 3 contradictions exist between the two documents.

---

## Items in CONTEXT-ARCHITECTURE That ARE in BUILD-ROADMAP

| CONTEXT-ARCHITECTURE Capability | BUILD-ROADMAP Item(s) | Notes |
|----------------------------------|----------------------|-------|
| Session journal table + lifecycle (start/end/topics/summary) | P0-3, P0-5 | Topics gap and orphaned session cleanup both reference session_journal |
| depth_score + access_count + is_pinned + human_endorsed schema | P1-7 | Depth-weighted ranking item covers schema + search |
| `touch()` — update access_count + last_accessed_at | P1-7 | Explicitly required for depth scoring to diverge |
| `pin()`, `unpin()`, `get_pinned()` methods | P0-1 | Context tools fix references get_pinned() stale read |
| `start_session()`, `end_session()`, `last_session()` | P0-5 | Orphaned session cleanup requires these methods |
| `session_store.py` module — boot(), record_turn(), shutdown() | P0-5 | Covered by orphaned session fix scope |
| `context_manager.py` module — format, estimate, budget | P1-3 | Compaction engine extends context_manager |
| Context compaction (Phase 4 — summarize oldest N turns) | P1-3 | Full compaction engine item |
| `introspect_context()` tool | P0-1 | Stale pinned count fix |
| `memory_relations` table (graph: references/supersedes/conflicts/compounds) | P2-1 | Full memory graph item |
| `citation_count` column | P2-1 | Included in graph item |
| `scratchpad.py` — in-memory working notes | Already shipped | Present in codebase inventory (scratchpad_tools.py implemented) |
| Context tools as tool calls (pin, compact, introspect) | P0-1, P1-3 | Partially covered — see Missing section for gaps |
| Dream Mode (4-phase: review, pattern search, forgetting, synthesis) | P2-2 | Dream Mode production deployment |
| `identity_ver` versioning (v0.3) | P2-2 | Mentioned in Dream Mode item but not explicitly scoped |
| Hub API civilizational memory + `cross_mind_shares` | P3-3 | Cross-domain transfer item |
| Prompt caching static → stable → semi-stable → dynamic ordering | P0-0 | Referenced in LiteLLM/reasoning_split item |
| BootContext dataclass | P0-5 | Implied by session_store scope |

---

## Items in CONTEXT-ARCHITECTURE That Are MISSING from BUILD-ROADMAP

These are capabilities explicitly described in CONTEXT-ARCHITECTURE.md with no corresponding BUILD-ROADMAP item.

---

### MISSING-1: Identity Anchor Initialization (First Boot)

**CONTEXT-ARCHITECTURE reference:** Boot Phase — "Identity anchors are memories tagged `memory_type='identity'` — the mind's name, role, core principles, civilizational membership. These are written at first boot and refreshed via Dream Mode. They are always injected."

**Gap:** There is no BUILD-ROADMAP item for the first-boot initialization of identity anchor memories. SESSION_STORE boot() assumes they exist in the DB, but if the DB is empty (first run ever), no identity anchors are present and boot context is incomplete.

**Recommended addition:** P1 item — "Identity Anchor Seeding: On first boot (session_count=0), write identity memories from manifest fields (mind_id, role, system_prompt summary) to DB with `memory_type='identity'` and `is_pinned=True`. Subsequent boots load these rather than re-creating them."

---

### MISSING-2: Background Async Knowledge Extraction

**CONTEXT-ARCHITECTURE reference:** Conversation Turn Phase — "background: extract new knowledge from turn (async, non-blocking)". Save Phase — "The extraction is not automatic — it's a judgment call by the mind."

**Gap:** CONTEXT-ARCHITECTURE explicitly designs an async background extraction step after each turn. Currently, Root writes memories only when it explicitly calls `memory_write`. There is no hook or pipeline that evaluates each turn for notable information. This means memories are only created when Root consciously decides to — the judgment-call model — but no infrastructure ensures turns are even evaluated.

**Recommended addition:** P2 item — "Turn Knowledge Extractor: After each `run_task()` returns, call a lightweight background coroutine that evaluates the turn for memorability (tool-use results, new information, contradictions discovered). Runs non-blocking via asyncio.create_task(). Falls back gracefully if fails."

---

### MISSING-3: Evict and Load Context Tools

**CONTEXT-ARCHITECTURE reference:** v0.2 Context Tools — lists 5 tools: `pin_memory`, `evict_memory`, `load_memory`, `compact_history`, `introspect_context`.

**Gap:** BUILD-ROADMAP P1-3 (Context Compaction Engine) only adds `compact_context`. P0-1 covers `introspect_context`. But `evict_memory` (remove from current context window without deleting) and `load_memory` (force-load specific memories) are not listed in any BUILD-ROADMAP item. These are distinct capabilities — `evict` manages context pressure; `load` enables deliberate context enrichment.

**Recommended addition:** Extend P1-3 scope to explicitly include `evict_memory(memory_id)` and `load_memory(query)` tool implementations alongside the compaction work. Or create a dedicated P1 item: "Context Agency Tools: Implement `evict_memory` and `load_memory` as tool calls, giving Root direct control over context window contents without compaction."

---

### MISSING-4: Depth Score Batch Recalculation at Session Shutdown

**CONTEXT-ARCHITECTURE reference:** Shutdown Phase — "update: depth scores for all accessed memories in this session".

**Gap:** This is a shutdown-time batch operation: recalculate depth_score for every memory accessed during the session using the final access_count, last_accessed_at, and recency values. Currently session_store.shutdown() writes the handoff summary but does not trigger a depth score recalculation sweep. Without this, depth_score values go stale — they only update when touch() is called, not when the recency decay factor changes overnight.

**Recommended addition:** P2 item — "Shutdown Depth Score Sweep: Add `memory.recalculate_depth_scores(agent_id, session_id)` called during session_store.shutdown(). Recalculates depth_score for all memories accessed this session using current recency values. This is what makes long-unused memories decay properly."

---

### MISSING-5: Cache Performance Metrics and Self-Improvement Loop

**CONTEXT-ARCHITECTURE reference:** Prompt Caching Strategy section — "What We Track (v0.2+): Cache hit rate per session, Cost per turn (cached vs uncached), Correlation between context stability and hit rate. This feeds back into boot context optimization: if certain memory injections consistently cause cache misses, they should be evicted or reformatted for stability."

**Gap:** No BUILD-ROADMAP item tracks or acts on cache performance data. BUILD-ROADMAP P0-0 adds reasoning_split but doesn't include the cache stats logging or the feedback loop. This is a self-improving loop capability (Principle 7) with direct cost impact.

**Recommended addition:** P2 item — "Cache Performance Tracking: Log cache_read_input_tokens and cache_creation_input_tokens from API response metadata per session. Write to `data/cache_stats.jsonl`. After 10 sessions, analyze which boot context elements correlate with cache misses and surface findings as a dream artifact."

---

### MISSING-6: Search-by-Depth Method

**CONTEXT-ARCHITECTURE reference:** v0.1.1 New MemoryStore Methods — includes `search_by_depth(agent_id, limit)` — "Return top memories by depth_score (not FTS)".

**Gap:** This method is not mentioned in any BUILD-ROADMAP item. P1-7 adds depth weighting to FTS5 search (combined score) but `search_by_depth` is a pure depth-rank query independent of text search — useful for "what does this mind care most about?" queries and for boot context loading.

**Recommended addition:** Include `search_by_depth()` explicitly in P1-7 scope, or note it as part of P0-5 session_store work since boot() needs it to load identity anchors by depth.

---

### MISSING-7: The "What We Are NOT Building" Constraints

**CONTEXT-ARCHITECTURE reference:** Final section — explicitly excludes: LangChain memory, vector embeddings, automatic summarization, cloud storage.

**Gap:** These architectural exclusions are not documented in BUILD-ROADMAP. When future sessions propose adding these, there's no roadmap-level record of why they were rejected. A future agent might reasonably propose "add vector embeddings" without knowing this was already deliberated.

**Recommended addition:** Add a "Architectural Exclusions" section to BUILD-ROADMAP with these four items and their rationale (preserved from CONTEXT-ARCHITECTURE).

---

### MISSING-8: Session Continuity Guarantee (Acceptance Test)

**CONTEXT-ARCHITECTURE reference:** "The Guarantee" section — 5 specific testable assertions that define v0.1.1 completion, including True Bearing's test: "ask the mind 'what were you doing yesterday?' — it answers correctly."

**Gap:** These acceptance criteria are not in BUILD-ROADMAP. There's no formal test for session continuity defined anywhere in the roadmap. Tests in BUILD-ROADMAP items are implementation-level (pytest), not behavior-level (end-user contracts).

**Recommended addition:** Add "Session Continuity Acceptance Test" to the P1-2 (Multi-Turn) item or as a standalone test item: the 5 assertions from CONTEXT-ARCHITECTURE "The Guarantee" section become the E2E test definition.

---

### MISSING-9: `manifest.with_system_prefix()` API

**CONTEXT-ARCHITECTURE reference:** Integration with Mind section — `manifest_with_boot = manifest.with_system_prefix(boot_prefix)` — requires Manifest class to support prefix injection without mutating the original.

**Gap:** This API method is implied by session_store boot integration but not explicitly called out in any BUILD-ROADMAP item. If `manifest.py` doesn't have this method, the boot context wiring in main.py cannot be implemented cleanly.

**Recommended addition:** Include `manifest.with_system_prefix(prefix: str) -> Manifest` in the session_store integration work (already partially scoped in P0-5 or session_store items).

---

## Contradictions Between the Two Documents

### Contradiction 1: Context Compaction Threshold

| Document | Value |
|----------|-------|
| CONTEXT-ARCHITECTURE Phase 4 | Compact when > **70%** of model's window |
| BUILD-ROADMAP P1-2 | Warning at **70%**, compact at **85%** |

**Impact:** P1-3 (Compaction Engine) will be implemented against BUILD-ROADMAP values (85% trigger). CONTEXT-ARCHITECTURE designed a more aggressive 70% trigger.

**Recommendation:** Adopt BUILD-ROADMAP's two-tier model (70% warning, 85% compact) as it's more conservative and better aligns with not disrupting active work. Update CONTEXT-ARCHITECTURE to reflect this clarification.

---

### Contradiction 2: Context Tool Naming — compact_history vs compact_context

| Document | Tool Name |
|----------|-----------|
| CONTEXT-ARCHITECTURE v0.2 | `compact_history(n_turns)` |
| BUILD-ROADMAP P1-3 | `compact_context` |

**Impact:** Two names for the same tool will confuse the mind when system prompt references one vs implementation uses the other.

**Recommendation:** Standardize on `compact_history(n_turns)` as named in CONTEXT-ARCHITECTURE (more descriptive — it compacts history, not "context" generally). Update P1-3 build spec.

---

### Contradiction 3: Memory Injection Token Budget

| Document | Value |
|----------|-------|
| CONTEXT-ARCHITECTURE ContextManager | Inject until budget is **80%** full, reserve **20%** for conversation |
| BUILD-ROADMAP P1-2 | Token budget tracking — no explicit injection limit stated |

**Impact:** context_manager.py currently has `max_context_memories` as the limit, not a token budget. If injection fills 80% of tokens with few memories but long ones, the budget is not enforced.

**Recommendation:** Ensure P1-3 (Compaction Engine) implementation explicitly enforces the 80% injection budget as designed in CONTEXT-ARCHITECTURE, not just a count-based limit.

---

## Recommended Additions to BUILD-ROADMAP

These items should be added, organized by priority:

### New P1 Items

**P1-NEW-A: Identity Anchor Seeding (First Boot)**
- Source: CONTEXT-ARCHITECTURE Boot Phase
- Build: Detect first boot (session_count=0 in session_journal), create identity memories from manifest fields (mind_id, role, system_prompt first 200 chars), tag memory_type='identity', set is_pinned=True
- Estimate: 1.5h
- Principle: P8 (Identity Persistence)

**P1-NEW-B: `evict_memory` and `load_memory` Context Tools**
- Source: CONTEXT-ARCHITECTURE v0.2 Context Tools
- Build: Implement `evict_memory(memory_id)` (remove from current context, not deleted) and `load_memory(query)` (force-inject matching memories into next turn prefix). Add to ToolRegistry in P1-3 scope.
- Estimate: 1.5h (add to P1-3 scope)
- Principle: P6 (Context Engineering as First-Class Citizen)

### New P2 Items

**P2-NEW-A: Shutdown Depth Score Sweep**
- Source: CONTEXT-ARCHITECTURE Shutdown Phase
- Build: `memory.recalculate_depth_scores(agent_id, session_id)` called in session_store.shutdown(). Recalculates all accessed memories using current recency decay.
- Estimate: 2h
- Principle: P1 (Memory IS Architecture)

**P2-NEW-B: Cache Performance Tracking**
- Source: CONTEXT-ARCHITECTURE Prompt Caching §What We Track
- Build: Log cache_read/write tokens per session to data/cache_stats.jsonl. After 10 sessions, dream artifact surfaces cache patterns.
- Estimate: 2h
- Principle: P7 (Self-Improving Loop)

### Additions to Existing Items

**Add to P1-7 scope:** Explicitly include `search_by_depth(agent_id, limit)` method as a named deliverable.

**Add to P1-3 scope (Compaction Engine):**
- Add `evict_memory` and `load_memory` tools (see P1-NEW-B above)
- Rename `compact_context` → `compact_history(n_turns)` to match CONTEXT-ARCHITECTURE
- Explicitly enforce 80% injection budget in context_manager, not just count-based limit

**Add to BUILD-ROADMAP structure:**
- "Architectural Exclusions" section listing the 4 things explicitly NOT being built (from CONTEXT-ARCHITECTURE)
- "Session Continuity Acceptance Test" as a named test in P1-2 or standalone

---

## Cross-Reference Summary

| Status | Count |
|--------|-------|
| CONTEXT-ARCHITECTURE items covered in BUILD-ROADMAP | 18 |
| CONTEXT-ARCHITECTURE items MISSING from BUILD-ROADMAP | 9 |
| Contradictions between documents | 3 |
| Recommended new BUILD-ROADMAP items | 4 (+ 4 scope expansions) |
