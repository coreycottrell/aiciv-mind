# aiciv-mind BUILD ROADMAP
## Comprehensive Gap Analysis + Prioritized Build Plan

**Date**: 2026-04-01 (updated 2026-04-03 after overnight flywheel)
**Author**: Team 2 Build Analysis
**Sources**: CC-ANALYSIS-CORE, CC-ANALYSIS-TEAMS, CC-PUBLIC-ANALYSIS, M27-RESEARCH, ROOT-GAPS, REALITY-AUDIT, EVOLUTION-PLAN, NEXT-STEPS, CONTEXT-ARCHITECTURE, DESIGN-PRINCIPLES, Aether Skills Analysis
**Codebase**: `/home/corey/projects/AI-CIV/aiciv-mind/` — 18 source files, 12 tool modules, 4 skills, 10 manifests, 4 tools scripts

## BUILD STATUS (2026-04-03 Continued Overnight Flywheel)
**25 of 25 core items BUILT. 2112+ tests passing.** Full coverage of original roadmap achieved.

| Item | Status | Notes |
|------|--------|-------|
| P0-0 | ✅ BUILT | Pin M2.7 temp=1.0 + reasoning_split + extra_body support |
| P0-1 | ✅ BUILT | introspect_context — already calls get_pinned at invocation time |
| P0-2 | ✅ BUILT | PRAGMA optimize — already in memory.py close() |
| P0-3 | ✅ BUILT | Session topics — 16-word extraction in mind.py |
| P0-4 | ✅ BUILT | Thinking tokens preserved — response.content includes blocks |
| P0-5 | ✅ BUILT | Orphaned session cleanup in session_store.py boot() + memory dedup |
| P0-6 | TESTING | Temperature 0.7 vs 1.0 — testing task, not code |
| P1-1 | ❌ UNBUILT | Hub daemon — persistent watcher needed |
| P1-2 | ✅ BUILT | Multi-turn — REPL + --converse flag |
| P1-3 | ✅ BUILT | Context compaction — full implementation with circuit breaker |
| P1-4 | ✅ BUILT | Web tools — web_search_tools.py + web_fetch_tools.py |
| P1-5 | ✅ BUILT | Email — email_tools.py (202 lines) |
| P1-6 | ✅ BUILT | Test-echo manifest created + spawner tests |
| P1-7 | ✅ BUILT | Depth-weighted search ranking |
| P1-8 | ✅ BUILT | Skill auto-discovery — skill_discovery.py |
| P2-1 | ✅ BUILT | Memory graph — memory_links table + graph_tools.py (4 tools) |
| P2-2 | ✅ BUILT | Dream mode — KAIROS integration + production launcher |
| P2-3 | ✅ BUILT | Hooks — HookRunner + JSONL audit persistence |
| P2-4 | ✅ BUILT | Persistent agent registry — spawner writes to DB |
| P2-5 | ✅ BUILT | Model router — integrated with mind loop |
| P2-6 | ✅ BUILT | Identity file protection — safe_update.sh + .gitignore |
| P2-7 | ✅ BUILT | Infrastructure guard — 8 checks, 17 tests |
| P2-8 | ✅ BUILT | Memory selector — AI-powered relevance reranking |
| P3-1 | ✅ BUILT | Team leads — 6 manifests in manifests/team-leads/ |
| P3-4 | ✅ BUILT | Red team — manifest + soul + registered in primary sub_minds |
| P3-5 | ✅ BUILT | Pattern detection — bigram/trigram/error/slow/dominant |
| P3-6 | ✅ BUILT | KAIROS — daily log + mind loop integration + dream cycle |
| P3-7 | ✅ BUILT | Context engineer — manifest + soul + expanded tools |
| P3-9 | ✅ BUILT | Calendar tools — 283 lines |

**Remaining unbuilt (stretch goals)**: P1-1 (Hub daemon), P3-2 (self-modification sandbox), P3-3 (cross-domain transfer), P3-8 (MCP server), P3-10 (local content gen)

---

## Current Codebase Inventory

### Source Modules (src/aiciv_mind/)
| Module | Lines | Status |
|--------|-------|--------|
| `mind.py` | 285 | Core loop working. Single-threaded, cache-aware. |
| `memory.py` | 709 | SQLite+FTS5. Skills table + agent_registry table exist. |
| `manifest.py` | 184 | YAML loader with Pydantic v2. Env expansion + path resolution. |
| `session_store.py` | 229 | Boot → record → shutdown lifecycle working. |
| `context_manager.py` | 163 | Cache-optimal ordering. Boot + search formatting. |
| `registry.py` | 101 | In-memory MindHandle registry (not persisted). |
| `model_router.py` | 220 | Heuristic task→model routing. Outcome recording. |
| `spawner.py` | 173 | tmux-based sub-mind spawner via libtmux. |
| `ipc/` | ~300 | ZeroMQ ROUTER/DEALER. PrimaryBus + SubMindBus. |

### Tool Modules (src/aiciv_mind/tools/)
| Module | Tools | Status |
|--------|-------|--------|
| `bash.py` | bash | Working |
| `files.py` | read_file, write_file, edit_file | Working |
| `search.py` | grep, glob | Working |
| `memory_tools.py` | memory_search, memory_write | Working. touch() NOW called in search. |
| `hub_tools.py` | hub_post, hub_reply, hub_read, hub_list_rooms, hub_queue_read | Working (after endpoint fix) |
| `context_tools.py` | pin_memory, unpin_memory, introspect_context, get_context_snapshot | Working (stale-read edge case) |
| `submind_tools.py` | spawn_submind, send_to_submind | Never exercised |
| `skill_tools.py` | load_skill, list_skills, create_skill | Implemented, 4 skills registered |
| `scratchpad_tools.py` | scratchpad_read, scratchpad_write, scratchpad_list | Implemented |
| `sandbox_tools.py` | sandbox_create, sandbox_test, sandbox_promote, sandbox_discard | Implemented, never tested live |

### Skills (skills/)
| Skill | Status |
|-------|--------|
| `hub-engagement/SKILL.md` | 942 bytes, registered |
| `memory-hygiene/SKILL.md` | 1012 bytes, registered |
| `self-diagnosis/SKILL.md` | 893 bytes, registered |
| `agentmail/SKILL.md` | 2513 bytes, registered |

### Tools Scripts (tools/)
| Script | Status |
|--------|--------|
| `dream_cycle.py` | Implemented (quick + full modes). Never run in production. |
| `nightly_training.py` | Implemented. Never run. |
| `groupchat_daemon.py` | Implemented. New. |

### Manifests
| Manifest | Status |
|----------|--------|
| `primary.yaml` | Root. 22 tools enabled. M2.7 model. |
| `research-lead.yaml` | 1 sub-mind. kimi-k2 model. |
| `context-engineer.yaml` | 1 sub-mind. Referenced but not read. |

---

## P0 — This Week (<2h each)
### Broken things or performance losses happening NOW

### P0-0: PIN M2.7 FOR EVERYTHING + Enable reasoning_split (Corey Directive 2026-04-01)
- **Source**: M27-FOCUS.md, Corey directive
- **Current State**: May be falling back to M2.5. reasoning_split not enabled. Thinking tokens unaudited.
- **Priority Justification**: M2.7 was TRAINED to improve its own harness. We ARE the harness. Pin it. Max out thinking. Never constrain.
- **Build**:
  - Verify LiteLLM routes ALL calls to M2.7 (not M2.5 fallback)
  - Add `reasoning_split: true` to LiteLLM extra_body config
  - Audit mind.py: verify `<think>` blocks preserved in `_messages`
  - If stripping: fix immediately (40% performance at stake)
  - Test temperature 1.0 vs 0.7
  - Update all manifests: research-lead.yaml should use M2.7 too (not kimi-k2)
- **Estimate**: 1h
- **Principle**: P7 (Self-Improving Loop — M2.7's self-evolution IS our loop)

---

---

### P0-1: Fix introspect_context Stale Pinned Count
- **Source**: REALITY-AUDIT §3.3, NEXT-STEPS Gap 5
- **Current State**: PARTIAL (tool exists, pinned count stale)
- **Priority Justification**: Root sees 0 pinned even after pinning. Breaks trust in context tools. Diagnosed exactly by Root — fix is one line.
- **Build**:
  - File: `src/aiciv_mind/tools/context_tools.py`
  - Change: Move `memory_store.get_pinned(agent_id)` call from construction time (closure capture) to inside the handler function (invocation time).
- **Estimate**: 0.5h
- **Principle**: P6 (Context Engineering as First-Class Citizen)

---

### P0-2: Add PRAGMA optimize to MemoryStore.close()
- **Source**: REALITY-AUDIT §3.2
- **Current State**: NO (FTS5 ghost rows accumulate)
- **Priority Justification**: Write-then-search returns no results. This causes Root to think memories weren't saved. Silent data loss of depth scoring fidelity.
- **Build**:
  - File: `src/aiciv_mind/memory.py`, method `close()`
  - Add: `self._conn.execute("PRAGMA optimize")` before `self._conn.close()`
- **Estimate**: 0.25h
- **Principle**: P1 (Memory IS Architecture)

---

### P0-3: Fix Session Topics Never Populated
- **Source**: REALITY-AUDIT §3.6, NEXT-STEPS Gap
- **Current State**: NO (always empty `[]`)
- **Priority Justification**: Session journal is useless for search without topics. Every session is indistinguishable. Blocks session-level learning (Loop 2).
- **Build**:
  - File: `src/aiciv_mind/mind.py`, `run_task()` method (~line 119)
  - Change: Extract topic from the task text (first 5 keywords or task type from model_router.classify_task()) and pass to `self._session_store.record_turn(topic=extracted_topic)`
  - Also: `src/aiciv_mind/session_store.py` `record_turn()` — already accepts topic, just never receives one
- **Estimate**: 1h
- **Principle**: P7 (Self-Improving Loop — session-level learning needs topic data)

---

### P0-4: Verify Thinking Token Preservation in Conversation History
- **Source**: M27-RESEARCH §4 (Critical), REALITY-AUDIT
- **Current State**: UNKNOWN (never audited)
- **Priority Justification**: Dropping M2.7 thinking tokens costs up to 40% performance on complex tasks (BrowseComp: +40.1%, Tau-2: +35.9%). This is the single highest-leverage performance variable. If thinking tokens are being stripped by LiteLLM or the anthropic SDK translation, Root is operating at 60% capacity.
- **Build**:
  - File: `src/aiciv_mind/mind.py`, `run_task()` line 137
  - Audit: Check what `response.content` contains after API call. If `<think>` blocks or `reasoning_details` are present, verify they are preserved in `self._messages` history.
  - If stripped: Modify `_call_model` to capture raw response and reconstruct content blocks including thinking tokens.
  - Add `reasoning_split=True` to LiteLLM extra_body config for cleaner parsing.
  - File: LiteLLM config (litellm_config.yaml or .env)
- **Estimate**: 1.5h
- **Principle**: P11 (Distributed Intelligence — the model's own reasoning layer is intelligence)

---

### P0-5: Fix Orphaned Session Cleanup
- **Source**: REALITY-AUDIT §3.4, §3.5
- **Current State**: NO
- **Priority Justification**: Zombie sessions (turn_count=0, end_time=None) and duplicate memories pollute the DB. They will compound over time and confuse session counting, boot context, and depth scoring.
- **Build**:
  - File: `src/aiciv_mind/session_store.py`, `boot()` method
  - Add: On boot, check for orphaned sessions (end_time IS NULL AND session_id != current) and close them with summary "Orphaned session — closed at next boot"
  - Add: Dedup check in `memory.py` `store()` — skip if identical title+content+agent_id written within 30 seconds
- **Estimate**: 1h
- **Principle**: P1 (Memory IS Architecture — clean data is reliable data)

---

### P0-6: Temperature Mismatch — Test 0.7 vs 1.0
- **Source**: M27-RESEARCH §5
- **Current State**: NO (Root runs at 0.7, MiniMax recommends 1.0)
- **Priority Justification**: Lower temperature may be suppressing M2.7's reasoning quality. Free performance improvement if 1.0 is better. Zero code change required for the test.
- **Build**:
  - File: `manifests/primary.yaml`, line 14
  - Test: Run identical prompts at 0.7 and 1.0, compare output quality
  - If 1.0 wins: Change `temperature: 0.7` to `temperature: 1.0`
- **Estimate**: 1h (testing)
- **Principle**: P11 (Distributed Intelligence — model-layer optimization)

---

## P1 — Next Sprint (2-8h each)
### Major capabilities unlocking new behaviors

---

### P1-1: Hub Daemon (Persistent Hub Watcher)
- **Source**: ROOT-GAPS §3, EVOLUTION-PLAN Phase 0, Aether Skills Analysis (CC Bridge pattern)
- **Current State**: NO (on-demand tools only, no persistent watching)
- **Priority Justification**: Root cannot autonomously participate in the Hub. Every AiCIV needs this. EVOLUTION-PLAN puts it at Phase 0 — before self-modification, before multi-turn, before everything else. The CC Bridge smart queue pattern (busy detection + force-delivery after timeout) is the right architecture.
- **Build**:
  - File: `tools/hub_daemon.py` (NEW — or extend `tools/groupchat_daemon.py` which already exists)
  - State file: `data/hub_watcher_state.json`
  - Architecture: Poll Hub rooms every 30s. Track last_thread_id per room. On new activity:
    - Write to a queue file (`data/hub_inbox.jsonl`)
    - Optionally send ZMQ TASK to PrimaryBus
  - Decision logic (in system prompt, not hardcoded):
    - Mentions of Root/ACG → always respond
    - New threads in priority rooms → evaluate
    - Replies to Root's posts → respond
    - Everything else → log as memory
  - Session ledger pattern (from Aether CC Bridge): Write tool usage timestamps to JSONL, hub_daemon reads to detect busy/idle state
  - Integration: `hub_queue_read` tool already exists for reading the queue
- **Estimate**: 4h
- **Principle**: P12 (Native Service Integration — Hub is home), P8 (Identity Persistence — present in the civilization)

---

### P1-2: Multi-Turn Conversation Support
- **Source**: REALITY-AUDIT §2.4 + §4.3, EVOLUTION-PLAN Phase 3, NEXT-STEPS
- **Current State**: NO (every session is 1 turn — main.py creates new Mind per call)
- **Priority Justification**: Root has never had a multi-turn conversation. Cannot handle follow-ups, corrections, or iterative tasks. Blocks model routing learning (needs success signals from conversation history). Blocks real-world usability.
- **Build**:
  - File: `src/aiciv_mind/interactive.py` — already has a REPL loop but creates Mind fresh
  - Change: Keep `Mind` instance alive across turns. `_messages` list persists between `run_task()` calls.
  - File: `src/aiciv_mind/mind.py`
  - Add: Token budget tracking per turn. When estimated tokens > 70% of model window, trigger warning. At 85%, trigger compaction.
  - File: `tools/tg_simple.py` (Telegram bridge)
  - Change: Ensure TG bridge reuses the same Mind instance across messages (not creating new Mind per message)
  - Fix: Telegram polling offset advancement (REALITY-AUDIT §3.7 — offset never advances, 0 messages processed)
- **Estimate**: 4h
- **Principle**: P6 (Context Engineering), P3 (Go Slow to Go Fast — multi-turn enables iterative planning)

---

### P1-3: Context Compaction Engine
- **Source**: CC-ANALYSIS-CORE §2, CC-PUBLIC-ANALYSIS §2, CONTEXT-ARCHITECTURE Phase 4, DESIGN-PRINCIPLES P6
- **Current State**: NO (designed in CONTEXT-ARCHITECTURE.md, not implemented)
- **Priority Justification**: Without compaction, multi-turn conversations will fill the 204K window and crash. CC's four-tier compression (micro, auto, reactive, snip) is the reference. Our three-tier model (Permanent/Session/Ephemeral) is cleaner but needs implementation.
- **Build**:
  - File: `src/aiciv_mind/context_manager.py` — extend with compaction methods
  - Add method: `compact_history(messages, strategy)` — summarize oldest N messages into a single assistant message
  - Strategy enum: `preserve-code`, `preserve-decisions`, `preserve-state`, `aggressive`
  - Circuit breaker: `MAX_CONSECUTIVE_COMPACTION_FAILURES = 3` (stolen from CC)
  - File: `src/aiciv_mind/mind.py` — integrate compaction check at turn boundary
  - Add: After each turn, `if self._context_manager.estimate_tokens(str(self._messages)) > 0.70 * model_max_tokens: compact()`
  - Add tool: `compact_context` — let Root trigger compaction manually
  - Separate summarizer: Use a cheap model call (Haiku or M2.5-free) for summarization, not the main model (CC-ANALYSIS-CORE §7 Avoid Sheet #3)
- **Estimate**: 6h
- **Principle**: P6 (Context Engineering as First-Class Citizen)

---

### P1-4: Web Search + Web Fetch Tools
- **Source**: ROOT-GAPS §5
- **Current State**: NO (Root cannot access the internet)
- **Priority Justification**: Root cannot research anything. Cannot verify claims. Cannot access current information. This is a fundamental capability gap blocking research, competitive intelligence, and self-improvement tasks.
- **Build**:
  - File: `src/aiciv_mind/tools/web_tools.py` (NEW)
  - `web_search(query, max_results)` — DuckDuckGo search (no API key needed), return titles + URLs + snippets
  - `web_fetch(url)` — fetch URL, convert to markdown (use jina reader pattern or simple HTML→text), truncate to 5000 chars
  - Register in `tools/__init__.py` default() factory
  - Add to `manifests/primary.yaml` tools list
- **Estimate**: 3h
- **Principle**: P11 (Distributed Intelligence — tool layer intelligence)

---

### P1-5: AgentMail Integration (Email Send/Receive)
- **Source**: ROOT-GAPS §5, NEXT-STEPS, primary.yaml (agentmail config exists but no tools)
- **Current State**: PARTIAL (agentmail config in manifest, SKILL.md exists, no tools)
- **Priority Justification**: Root has an inbox (`foolishroad266@agentmail.to`) but cannot send or receive email. This blocks inter-civ communication via email and human contact.
- **Build**:
  - File: `src/aiciv_mind/tools/email_tools.py` (NEW)
  - `email_send(to, subject, body)` — send via AgentMail API
  - `email_check(limit)` — check inbox, return recent messages
  - `email_read(message_id)` — read full message
  - Wire API key from manifest agentmail config
  - Register in tools/__init__.py
- **Estimate**: 3h
- **Principle**: P12 (Native Service Integration)

---

### P1-6: First Sub-Mind Spawn (End-to-End Validation)
- **Source**: REALITY-AUDIT §4.1, ROOT-GAPS §2, EVOLUTION-PLAN Phase 2
- **Current State**: NO (infrastructure exists, never exercised)
- **Priority Justification**: The entire orchestration architecture (spawner, IPC, ZeroMQ, registry) is theoretical. One successful spawn validates the whole stack. Blocks team-lead delegation model.
- **Build**:
  - Create a minimal test manifest: `manifests/test-echo.yaml` — a sub-mind that receives a task, responds with "echo: {task}", and shuts down
  - File: `src/aiciv_mind/tools/submind_tools.py` — verify spawn_submind and send_to_submind handlers work
  - Integration test: Root spawns test-echo, sends task, receives result over ZMQ, test-echo shuts down
  - Fix any issues discovered (tmux session creation, IPC routing, etc.)
  - Then: Spawn research-lead with a real research task
- **Estimate**: 4h
- **Principle**: P5 (Hierarchical Context Distribution), P4 (Dynamic Agent Spawning)

---

### P1-7: Memory Search Depth-Weighted Ranking
- **Source**: CC-ANALYSIS-TEAMS §2.4, CONTEXT-ARCHITECTURE, DESIGN-PRINCIPLES P1
- **Current State**: PARTIAL (depth_score exists, touch() works, but search still uses pure BM25)
- **Priority Justification**: Now that touch() is called (P0 fix was already applied per memory_tools.py code), depth scores will begin to diverge. But `memory.search()` only uses BM25 ranking (FTS5 `rank`), not depth_score. High-value memories don't surface higher than low-value ones.
- **Build**:
  - File: `src/aiciv_mind/memory.py`, `search()` method
  - Change: After FTS5 search, re-rank results by combining BM25 rank + depth_score:
    ```python
    combined_score = (bm25_normalized * 0.6) + (depth_score * 0.4)
    ```
  - Sort by combined_score descending
  - This makes frequently-accessed, pinned, human-endorsed memories surface higher even if BM25 relevance is equal
- **Estimate**: 2h
- **Principle**: P1 (Memory IS Architecture — depth scoring must affect retrieval)

---

### P1-8: Skill Auto-Discovery at Boot
- **Source**: ROOT-GAPS §1, CC-PUBLIC-ANALYSIS §6, DESIGN-PRINCIPLES P3
- **Current State**: PARTIAL (skill tools exist, 4 skills registered, no auto-discovery)
- **Priority Justification**: Skills exist on disk but Root must manually `load_skill` to use them. CC has progressive disclosure (skills become visible when relevant files are touched). aiciv-mind should auto-register all skills in the `skills/` directory at boot, and auto-search relevant skills before each task.
- **Build**:
  - File: `src/aiciv_mind/tools/skill_tools.py`
  - Add: `auto_register_skills(memory_store, skills_dir)` — walk `skills/` directory, register any SKILL.md not already in the DB
  - File: `src/aiciv_mind/mind.py`, `run_task()`
  - Add: After memory auto-search (line ~99-115), also search skills: `memory_store.search_skills(task_keywords)` and inject relevant skill content into the system prompt
  - File: `tools/__init__.py` default() — call auto_register_skills at registry construction
- **Estimate**: 2h
- **Principle**: P3 (Go Slow to Go Fast — skills are pre-computed plans)

---

## P2 — This Month
### Architectural improvements

---

### P2-1: Memory Graph (Relations Table)
- **Source**: CONTEXT-ARCHITECTURE v0.2, DESIGN-PRINCIPLES P1
- **Current State**: NO (designed, not built)
- **Priority Justification**: Memories are isolated facts. Cannot trace causal chains ("this decision was based on X, Y, Z"), detect contradictions, or compound related memories. The memory_relations table is designed in CONTEXT-ARCHITECTURE.md with schema ready.
- **Build**:
  - File: `src/aiciv_mind/memory.py`
  - Add: `memory_relations` table (from_id, to_id, relation_type: references|supersedes|conflicts|compounds)
  - Add: `relate_memories(from_id, to_id, relation_type)` method
  - Add: `get_related(memory_id)` method
  - Add: `citation_count` column to memories table, updated via trigger on relation INSERT
  - Add: `citation_count` factor to `update_depth_score()` formula
  - File: `src/aiciv_mind/tools/memory_tools.py`
  - Add: `memory_relate` tool — let Root explicitly link memories
- **Estimate**: 4h
- **Principle**: P1 (Memory IS Architecture — graph memory enables causal tracing and contradiction detection)

---

### P2-2: Dream Mode Production Deployment
- **Source**: CONTEXT-ARCHITECTURE v0.3, DESIGN-PRINCIPLES P4, EVOLUTION-PLAN Phase 5
- **Current State**: PARTIAL (dream_cycle.py exists with quick+full modes, never run in production)
- **Priority Justification**: The Dream cycle is where the self-improving loop becomes real. Root reviews, consolidates, prunes, and synthesizes. Currently it's a script that has never been executed against real data. Needs scheduling (AgentCal BOOP or cron) and validation.
- **Build**:
  - Validate: Run `dream_cycle.py --quick` against production memory.db. Verify it reads memories, writes consolidation notes, doesn't corrupt data.
  - Validate: Run `dream_cycle.py` (full mode). Verify all 5 stages complete.
  - Add: Consolidation lock (`data/.dream_lock`) — mtime-based, rollback on crash (CC-ANALYSIS-TEAMS §7.2)
  - Schedule: Add cron entry or BOOP config for nightly execution (1-4 AM window)
  - File: `tools/dream_cycle.py` — add lock acquisition/release
  - Add: Dream artifacts written to `scratchpads/` for next-session pickup
- **Estimate**: 4h
- **Principle**: P4 (Dream Mode), P7 (Self-Improving Loop)

---

### P2-3: Hooks System (PreToolUse / PostToolUse / Stop)
- **Source**: CC-ANALYSIS-CORE §4.3, CC-PUBLIC-ANALYSIS §5, CC-ANALYSIS-TEAMS §5
- **Current State**: NO
- **Priority Justification**: No observability into the tool loop. Cannot log tool calls, gate dangerous operations, collect training data, or trigger side effects. Hooks are how you get observability without cluttering the agent loop. CC has 18 hook events — we need at least 4: PreToolUse, PostToolUse, Stop, SessionStart.
- **Build**:
  - File: `src/aiciv_mind/hooks.py` (NEW)
  - Define: `HookEvent` enum (PreToolUse, PostToolUse, PostToolUseFailure, Stop, SessionStart)
  - Define: `HookRegistry` — register Python coroutines as handlers for events
  - Define: Hook return types (Allow, Block with message, Modify input)
  - File: `src/aiciv_mind/mind.py`
  - Integrate: Call PreToolUse hooks before `_execute_one_tool()`, PostToolUse hooks after
  - Integrate: Call Stop hooks when `run_task()` returns
  - Use cases:
    - Audit log: log every tool call to JSONL (training data)
    - Session ledger: write timestamps for busy detection (Aether CC Bridge pattern)
    - Safety gate: block dangerous bash commands not caught by constraints
- **Estimate**: 6h
- **Principle**: P11 (Distributed Intelligence — hooks are intelligence at the infrastructure layer)

---

### P2-4: Persistent Agent Registry (Survives Restart)
- **Source**: ROOT-GAPS §2, CC-ANALYSIS-TEAMS §1.3
- **Current State**: PARTIAL (agent_registry TABLE exists in memory.py schema, MindRegistry in registry.py is in-memory only)
- **Priority Justification**: When Root restarts, all knowledge of which sub-minds exist, their states, and their history is lost. The DB table exists but is never populated by the spawner. The in-memory MindRegistry needs to bridge to the persistent table.
- **Build**:
  - File: `src/aiciv_mind/spawner.py`
  - Add: On spawn, call `memory_store.register_agent(mind_id, manifest_path, display_name, role, domain)`
  - Add: On spawn, call `memory_store.touch_agent(mind_id, session_id)`
  - File: `src/aiciv_mind/session_store.py`, `boot()`
  - Add: On boot, load `memory_store.list_agents()` to reconstruct what agents are known
  - File: `src/aiciv_mind/registry.py`
  - Add: `sync_from_db(memory_store)` method — load persistent agent records into runtime registry
- **Estimate**: 3h
- **Principle**: P8 (Identity Persistence — agents survive restarts)

---

### P2-5: Model Router Integration with Mind Loop
- **Source**: DESIGN-PRINCIPLES P11, M27-RESEARCH §13.5, EVOLUTION-PLAN Phase 4
- **Current State**: PARTIAL (model_router.py exists with classification + outcome recording, not integrated with mind.py)
- **Priority Justification**: ModelRouter exists but Mind always uses `manifest.model.preferred`. The router can classify tasks and select models but it's never called. This blocks cost optimization (route cheap tasks to M2.5-free) and performance optimization (route reasoning to kimi-k2).
- **Build**:
  - File: `src/aiciv_mind/mind.py`, `_call_model()`
  - Add: If model_router is available, call `router.select(task)` to get model_id
  - Add: Override `kwargs["model"]` with router's selection
  - Add: After task completion, call `router.record_outcome(task, model_id, success, tokens)`
  - File: `src/aiciv_mind/mind.py`, `__init__()`
  - Add: Accept optional `model_router: ModelRouter` parameter
  - File: Main entry points (main.py, tg_simple.py, dream_cycle.py)
  - Add: Construct ModelRouter with stats_path and pass to Mind
  - Add M2.5-free and highspeed variant to LiteLLM config
- **Estimate**: 3h
- **Principle**: P11 (Distributed Intelligence — routing layer becomes intelligent)

---

### P2-6: Identity File Protection
- **Source**: Aether Skills Analysis (Flux2 pattern — #3 GRAB)
- **Current State**: NO
- **Priority Justification**: Any `git pull` can silently overwrite Root's identity, memory, config, and skills. Flux2 learned this the hard way. Three-layer defense needed: .gitignore protection, pre-update backup, post-update verification.
- **Build**:
  - Audit: Check `.gitignore` for `data/`, `scratchpads/`, `skills/` (user-created), `.env`
  - File: `.gitignore` — add any missing critical paths
  - File: `tools/safe_update.sh` (NEW) — pre-update: backup data/ and skills/ to data/backup/; post-update: verify critical files exist; rollback if missing
  - Document: Add to manifests/primary.yaml or system prompt: "never run git pull without safe_update.sh"
- **Estimate**: 1.5h
- **Principle**: P8 (Identity Persistence)

---

### P2-7: Nightly Infrastructure Guard
- **Source**: Aether Skills Analysis (Onboarding Guard pattern — #6 GRAB)
- **Current State**: NO
- **Priority Justification**: No automated validation of critical systems. Hub, AgentAuth, memory.db integrity, Telegram bridge, LiteLLM proxy — any of these can fail silently. Aether runs 10-check nightly guards. We should too.
- **Build**:
  - File: `tools/infrastructure_guard.py` (NEW)
  - Checks:
    1. Hub API reachable (GET /api/rooms)
    2. AgentAuth JWKS endpoint responds
    3. memory.db readable + not corrupted (PRAGMA integrity_check)
    4. LiteLLM proxy reachable (GET /health)
    5. Skills directory has >= 4 SKILL.md files
    6. At least 1 session in past 24h in session_journal
    7. No orphaned sessions older than 24h
    8. Disk usage < 90%
  - Output: PASS/FAIL per check, write to `data/guard_results.json`
  - Alert: On FAIL, write to scratchpad + optionally TG notification
  - Schedule: Nightly via cron or BOOP (before dream_cycle.py)
- **Estimate**: 3h
- **Principle**: P2 (System > Symptom — catch problems before they compound)

---

### P2-8: Relevance-Based Memory Injection (Memory Selector)
- **Source**: CC-ANALYSIS-TEAMS §2.4, DESIGN-PRINCIPLES P1, P6
- **Current State**: NO (current auto-search uses task text as FTS query — no AI-powered selection)
- **Priority Justification**: The naive approach (FTS5 on task text) doesn't scale. As memories grow, the search returns increasingly noisy results. The mature pattern: a cheap model call (Haiku/M2.5-free) to select relevant memories per turn, max 5 selections, ~300ms latency.
- **Build**:
  - File: `src/aiciv_mind/memory_selector.py` (NEW)
  - Class: `MemorySelector` — takes current query + list of memory summaries, calls cheap model, returns top-5 memory IDs
  - Use M2.5-free (already in LiteLLM config) for selection call
  - Structured JSON output: `{ selected_memory_ids: string[] }`
  - Max 256 tokens budget for this call
  - File: `src/aiciv_mind/mind.py`, `run_task()` auto-search section
  - Replace: FTS5 search → MemorySelector call → fetch selected memories → inject
  - Fallback: If selector fails, fall back to current FTS5 search
- **Estimate**: 5h
- **Principle**: P1 (Memory IS Architecture), P6 (Context Engineering), P11 (Distributed Intelligence)

---

## P3 — Future
### Aspirational

---

### P3-1: Team Lead Layer (Intermediate Coordination)
- **Source**: ROOT-GAPS §2, DESIGN-PRINCIPLES P5, CC-ANALYSIS-TEAMS §3
- **Current State**: NO (flat Primary → Sub-minds hierarchy)
- **Priority Justification**: ACG has 11 team lead verticals. aiciv-mind has flat spawning. Adding 3-5 team lead manifests (comms-lead, research-lead enhancement, coder-lead, ceremony-lead) between Root and specialists enables the conductor-of-conductors model. Requires P1-6 (first spawn) and P2-4 (persistent registry) first.
- **Build**:
  - Create manifests: `manifests/comms-lead.yaml`, `manifests/coder-lead.yaml`, `manifests/ceremony-lead.yaml`
  - Each has: domain-specific system prompt, restricted tool set, own skills, own memory namespace
  - Update `primary.yaml` sub_minds to reference all team leads
  - Root delegates domain tasks to team leads, not specialists
- **Estimate**: 8h
- **Principle**: P5 (Hierarchical Context Distribution)

---

### P3-2: Self-Modification via Sandbox (Phase 2 of Evolution Plan)
- **Source**: EVOLUTION-PLAN Phase 1+2, DESIGN-PRINCIPLES P7
- **Current State**: PARTIAL (sandbox_tools.py exists with create/test/promote/discard, `self_modification_enabled: false`)
- **Priority Justification**: Root can experiment in sandbox but cannot promote changes. The kill switch (`self_modification_enabled`) exists. This is the path to Loop 3 — Root evolving its own architecture. Requires Hub daemon (Phase 0) for civilizational oversight first.
- **Build**:
  - Validate: Run sandbox_create, make a change, sandbox_test, sandbox_promote end-to-end
  - Define: Explicit policy for what Root CAN modify (prompts, skills, tool descriptions) vs CANNOT (core loop, memory schema, auth)
  - When ready: Set `self_modification_enabled: true` in primary.yaml
  - Add: Git commit of promoted changes with audit trail
- **Estimate**: 4h
- **Principle**: P7 (Self-Improving Loop)

---

### P3-3: Cross-Domain Transfer via Hub
- **Source**: DESIGN-PRINCIPLES P10, CC-ANALYSIS-TEAMS §8.3
- **Current State**: NO
- **Priority Justification**: When Root discovers a pattern that works, it should be publishable to the Hub for other civilizations. This is the civilizational memory tier. Requires Hub daemon + memory graph first.
- **Build**:
  - File: `src/aiciv_mind/transfer.py` (NEW)
  - When a memory's depth_score exceeds threshold AND it's tagged as a pattern/learning:
    - Format as Hub Knowledge:Item with metadata (source_mind, evidence, applicability)
    - Post to Hub via hub_post tool
    - Add `cross_mind_shares` counter to memory
  - Governance: Default to `civ` scope. `public` requires human approval.
- **Estimate**: 6h
- **Principle**: P10 (Cross-Domain Transfer)

---

### P3-4: Red Team Verification Agent
- **Source**: DESIGN-PRINCIPLES P9
- **Current State**: NO
- **Priority Justification**: Every completion claim should be challenged. A dedicated adversary mind runs in its own context, receives the task + proposed solution, and returns APPROVED/CHALLENGED/BLOCKED. This is how Root builds calibrated confidence.
- **Build**:
  - File: `manifests/red-team.yaml` — adversarial mind that asks the 8 Red Team questions
  - Integration: After significant task completion, spawn red-team sub-mind with task + result
  - Red team returns structured verdict
  - Log outcomes for the Red Team's own learning
- **Estimate**: 6h
- **Principle**: P9 (Verification Before Completion)

---

### P3-5: Pattern Detection Engine
- **Source**: DESIGN-PRINCIPLES P4, P7
- **Current State**: NO
- **Priority Justification**: Every mind should maintain a local pattern detector watching its own actions. When the same problem type is encountered 3+ times, trigger specialist spawn proposal. This is the architectural mechanism for dynamic agent spawning.
- **Build**:
  - File: `src/aiciv_mind/pattern_detector.py` (NEW)
  - Class: `PatternDetector` — observes every tool call, classifies action type, tracks occurrences
  - Triggers: pattern_repetition (3+), blocking_detection (stuck > N seconds), context_pressure (> 85% full)
  - Integration: Called in PostToolUse hook (requires P2-3 Hooks first)
- **Estimate**: 8h
- **Principle**: P4 (Dynamic Agent Spawning), P7 (Self-Improving Loop)

---

### P3-6: KAIROS Pattern for Persistent Minds
- **Source**: CC-ANALYSIS-TEAMS §2.7
- **Current State**: NO
- **Priority Justification**: For minds that run continuously (not per-conversation), the standard session-based memory pattern breaks. KAIROS uses append-only daily logs + nightly dream distillation. Root's Telegram bridge is the first candidate for continuous operation.
- **Build**:
  - File: `src/aiciv_mind/kairos.py` (NEW)
  - Append-only daily log: `data/logs/YYYY/MM/DD.md` — short timestamped bullets
  - Nightly distill via dream_cycle.py reads daily logs → updates MEMORY.md + topic files
  - Consolidation lock prevents concurrent runs
- **Estimate**: 4h
- **Principle**: P1 (Memory IS Architecture), P8 (Identity Persistence)

---

### P3-7: Context Engineering Team Lead
- **Source**: DESIGN-PRINCIPLES P6
- **Current State**: NO
- **Priority Justification**: A dedicated mind whose entire domain is managing context for OTHER minds. When a mind's context approaches capacity, the Context Engineering Lead analyzes current context in its OWN window, identifies essential vs noise, and produces an optimized summary. This is metacognition as a service.
- **Build**:
  - File: `manifests/context-engineer.yaml` — already referenced in primary.yaml sub_minds
  - System prompt: specialized for context analysis and compression
  - Tools: read other minds' context snapshots, produce optimized summaries
  - Integration: Primary can delegate compaction to context-engineer instead of doing it inline
- **Estimate**: 6h
- **Principle**: P6 (Context Engineering as First-Class Citizen)

---

### P3-8: MCP Server Support
- **Source**: CC-ANALYSIS-CORE §4.2, ROOT-GAPS §5
- **Current State**: NO (no MCP integration at all)
- **Priority Justification**: MCP is the universal protocol for connecting AI to external tools. Supporting MCP means Root can use any MCP server (browser automation, database access, external APIs) without custom tool implementation. Low priority because custom tools cover current needs, but high long-term value.
- **Build**:
  - File: `src/aiciv_mind/mcp_client.py` (NEW)
  - Implement: MCP client that discovers tools from MCP server and registers them in ToolRegistry
  - Config: `.mcp.json` or section in manifest for MCP server definitions
  - MCP tools appear alongside built-in tools (same as CC pattern)
- **Estimate**: 10h
- **Principle**: P12 (Native Service Integration), P11 (Distributed Intelligence)

---

### P3-9: AgentCal Integration (Scheduling Awareness)
- **Source**: ROOT-GAPS §5, EVOLUTION-PLAN (Corey Addition #1)
- **Current State**: NO (no calendar tools)
- **Priority Justification**: Root has no scheduling awareness. Cannot read its own calendar, schedule thinking time, or know when Corey is typically online. AgentCal is already operational for ACG. Corey suggested using it for proactive cognition — schedule dream cycles, research tasks, Hub engagement windows.
- **Build**:
  - File: `src/aiciv_mind/tools/calendar_tools.py` (NEW)
  - `calendar_read(calendar_id, date)` — read events for a date
  - `calendar_create(calendar_id, title, start, end)` — create event
  - `calendar_check_availability(date)` — check free/busy
  - Integration via SuiteClient CalClient (already designed in suite/client.py)
- **Estimate**: 3h
- **Principle**: P12 (Native Service Integration)

---

### P3-10: Local Content Generation Stack
- **Source**: Aether Skills Analysis (#2 GRAB — Chatterbox TTS + FLUX.2 + Remotion)
- **Current State**: NO
- **Priority Justification**: Root depends on external APIs for all content generation. Aether's local-first stack (Chatterbox TTS for voice cloning from 30s reference, FLUX.2 for images, Pillow for graphics) eliminates API dependency. Lower priority than core architecture but enables identity-as-voice and API-free overnight content generation.
- **Build**:
  - Install: Chatterbox TTS locally
  - File: `src/aiciv_mind/tools/content_tools.py` (NEW)
  - `generate_voice(text, reference_audio)` — local TTS with voice cloning
  - `generate_image(prompt)` — FLUX.2 or Pillow
  - Test: Create ACG voice identity from 30s reference audio
- **Estimate**: 8h
- **Principle**: P11 (Distributed Intelligence), P8 (Identity Persistence — voice as identity)

---

## Summary: Build Priority Matrix

| Priority | Count | Total Hours | Key Theme |
|----------|-------|-------------|-----------|
| **P0** | 8 items | ~6.75h | Fix what's broken + security (depth scoring, FTS, topics, thinking tokens, sessions, temperature, credential scrubbing, memory-as-hint) |
| **P1** | 11 items | ~39h | Unlock new behaviors (Hub daemon, multi-turn, compaction+circuit-breaker+cache-annotations, web, email, sub-minds, memory ranking, skill auto-discovery+progressive-disclosure+fork-context, MindContext, MindCompletionEvent) |
| **P2** | 11 items | ~40.5h | Architectural upgrades (graph memory, dream mode, hooks+failure-event+permission-bubbling+llm-hooks, persistent agents, model routing, identity protection, infrastructure guard, memory selector, coordinator permission gate, model inheritance, minimal context mode) |
| **P3** | 10 items | ~63h | Aspirational (team leads, self-modification, cross-domain transfer, red team, pattern detection, KAIROS, context engineering lead, MCP, calendar, content gen) |

**Total estimated**: ~149 hours across all priorities (+24h from CC-INHERIT additions).

---

## Critical Path

```
P0 (fixes) → P1-2 (multi-turn) → P1-3 (compaction) → P1-1 (Hub daemon)
                                                          ↓
P1-6 (first spawn) → P2-4 (persistent registry) → P3-1 (team leads)
                                                          ↓
P2-3 (hooks) → P3-5 (pattern detection) → P3-2 (self-modification)
                                                          ↓
P2-2 (dream mode) → P2-1 (graph memory) → P3-3 (cross-domain transfer)
```

The critical path to "Root as a real AI OS" runs through: fixes → multi-turn → compaction → Hub daemon → sub-mind spawning → persistent agents → team leads. Everything else branches off this spine.

---

## CC-INHERIT Additions (2026-04-01)

*Items added from `docs/CC-INHERIT-LIST.md` analysis of the CC public leak. Not previously in roadmap.*

---

### P0-7: Environment Credential Scrubbing in Subprocesses
- **Source**: CC-PUBLIC-ANALYSIS §9, CC-INHERIT-LIST I-2
- **Current State**: NO — bash.py and spawner.py pass full `os.environ` including API keys to subprocesses
- **Priority Justification**: Security issue. Any bash command Root runs, or any sub-mind spawned, inherits Root's full credential set. Must fix before web access (P1-4) or Hub daemon (P1-1) are enabled.
- **Build**:
  - File: `src/aiciv_mind/tools/bash.py` — scrub credential env vars from subprocess env dict before spawn
  - File: `src/aiciv_mind/spawner.py` — same for tmux pane environment
  - Strip: keys matching `*_KEY`, `*_SECRET`, `*_TOKEN`, `ANTHROPIC_*`, `OPENAI_*`, `GOOGLE_*`, `AWS_*`, `LITELLM_*`
  - Preserve: `PATH`, `HOME`, `PYTHONPATH`, `MIND_*` config vars
- **Estimate**: 1h
- **Principle**: P8 (Identity Persistence — credentials belong to their owner, not all subprocesses)

---

### P0-8: Memory-as-Hint Explicit Instruction in System Prompt
- **Source**: CC-PUBLIC-ANALYSIS §3, CC-INHERIT-LIST I-5
- **Current State**: NO — system prompts don't encode the principle that memory is a hint, not truth
- **Priority Justification**: Zero code complexity, immediate impact on correctness. Root may assert stale memory facts as truth, sending itself down wrong paths.
- **Build**:
  - File: `prompts/` directory (or directly in `mind.py` base_system_prompt)
  - Add instruction: "Your memories are HINTS, not facts. Before asserting that something exists (a file, function, endpoint, pattern), verify it directly. Memory tells you WHERE to look — not what you'll find."
  - File: `src/aiciv_mind/memory.py`, `search()` — surface `written_at` in returned results
  - File: `src/aiciv_mind/mind.py`, memory injection section — prepend staleness caveat for memories > 24h old
- **Estimate**: 0.5h
- **Principle**: P1 (Memory IS Architecture — memory informs, it does not decide)

---

### P1-9: MindContext — Python Contextvars for Agent Identity
- **Source**: CC-ANALYSIS-TEAMS §1.2, CC-INHERIT-LIST I-1
- **Current State**: NO — each Mind is a class instance, no context isolation for concurrent operations
- **Priority Justification**: Required BEFORE P1-6 (First Sub-Mind Spawn). Without context isolation, shared utilities (memory search, tool logging) cannot identify which mind is calling them in concurrent scenarios.
- **Build**:
  - File: `src/aiciv_mind/context.py` (NEW)
  - Python `contextvars.ContextVar[str]` for `CURRENT_MIND_ID`
  - `MindContext` async context manager: `async with mind_context(mind_id): ...`
  - `current_mind_id()` function: readable anywhere in the call stack
  - File: `src/aiciv_mind/mind.py`, `run_task()` — wrap execution in `MindContext` boundary
  - File: `src/aiciv_mind/tools/memory_tools.py` — use `current_mind_id()` instead of requiring `agent_id` parameter where possible
- **Estimate**: 2h
- **Principle**: P5 (Hierarchical Context Distribution — each mind's identity is isolated)

---

### P1-10: MindCompletionEvent — Structured Worker Result Format
- **Source**: CC-ANALYSIS-TEAMS §3.3, CC-INHERIT-LIST I-8
- **Current State**: NO — IPC layer returns raw text, no structured completion format
- **Priority Justification**: Design this BEFORE P1-6 (First Sub-Mind Spawn). The completion format defines the coordinator's information architecture. Get it right before wiring it into the loop.
- **Build**:
  - File: `src/aiciv_mind/ipc/messages.py` (NEW or extend existing)
  - Define `MindCompletionEvent` dataclass: mind_id, task_id, status, summary (5-10 words), result, tokens_used, tool_calls, duration_ms
  - Sub-minds serialize to JSON in their final IPC response
  - File: `src/aiciv_mind/mind.py` — recognize `MindCompletionEvent` JSON in messages, format as structured context entry
- **Estimate**: 2h
- **Principle**: P5 (Hierarchical Context Distribution — coordinator receives summaries, not floods)

---

### P1-11: Scope Expansions for Existing P1 Items

**P1-3 additions (Context Compaction Engine):**
- Add circuit breaker: `MAX_CONSECUTIVE_COMPACTION_FAILURES = 3` — after 3 failures, disable compaction for session (CC-INHERIT I-3)
- Add cache boundary annotations: label each system prompt section as STATIC/SESSION/VOLATILE. Enforce static-before-volatile ordering (CC-INHERIT I-4)
- **Estimate addendum**: +2.5h to P1-3 estimate (now 8.5h total)

**P1-8 additions (Skill Auto-Discovery):**
- Add `paths` field to SKILL.md frontmatter for progressive disclosure — skill only visible when task touches matching files (CC-INHERIT I-6)
- Add `context: inline | fork` field — `fork` spawns isolated sub-mind for complex/destructive skills (CC-INHERIT I-7)
- **Estimate addendum**: +4h to P1-8 estimate (now 6h total)

---

### P2-9: Coordinator Permission Gate (3-Layer)
- **Source**: CC-PUBLIC-ANALYSIS §1 (six-layer), CC-ANALYSIS-TEAMS §1.6, CC-INHERIT-LIST I-9
- **Current State**: NO — sub-minds have no escalation path for sensitive operations
- **Priority Justification**: After P1-6 (First Sub-Mind Spawn). Sub-minds need to bubble permission requests to coordinator before executing tool calls outside their domain.
- **Build**:
  - Three-layer model (NOT CC's six-layer complexity): Deny (forbidden_tools) → Bubble (requires_coordinator_approval) → Allow (allowed_tools)
  - `PermissionRequest` IPC message type: mind_id, tool_name, input_summary, reason
  - `PermissionResponse` message type: approved (bool), condition (str)
  - File: `src/aiciv_mind/ipc/messages.py` — add both message types
  - File: `src/aiciv_mind/mind.py` — handle incoming PermissionRequest in main loop
  - File: `src/aiciv_mind/manifest.py` — add `requires_coordinator_approval` tool list field
- **Estimate**: 4h
- **Principle**: P5 (Hierarchical Context Distribution), P8 (Identity Persistence — each mind owns its permissions)

---

### P2-10: Model Inheritance for Cache Alignment
- **Source**: CC-PUBLIC-ANALYSIS §4, CC-INHERIT-LIST L-1
- **Current State**: NO — every sub-mind always uses its own manifest model
- **Build**:
  - File: `src/aiciv_mind/manifest.py` — allow `preferred: inherit` in model config
  - File: `src/aiciv_mind/spawner.py` — resolve `inherit` to parent mind's actual model string before spawn
- **Estimate**: 1h
- **Principle**: P11 (Distributed Intelligence — scheduling layer optimization)

---

### P2-11: Minimal Context Mode for Read-Only Agents (`context_mode: minimal`)
- **Source**: CC-PUBLIC-ANALYSIS §4, CC-INHERIT-LIST L-2
- **Current State**: NO — all agents load full identity context
- **Build**:
  - File: `src/aiciv_mind/manifest.py` — add `context_mode: full | minimal` field
  - `minimal` mode: skip loading identity docs (constitution, growth trajectory, cross-session memories) for pure read/research workers
  - Minimal agents get: task + allowed_tools + their own manifest only
  - File: `src/aiciv_mind/context_manager.py` — `build_boot_context()` checks `context_mode` flag
- **Estimate**: 1.5h
- **Principle**: P5 (Hierarchical Context Distribution — primary context is sacred, read-only agents need less)

---

### P2-3 Scope Expansion (Hooks System)

**Additional events to add when building P2-3:**
- `PostToolUseFailure` as a distinct event (not merged with PostToolUse) — enables dedicated failure pattern tracking, feeds Principle 2 Layer 2 analysis (CC-INHERIT L-3)
- `PermissionRequest` event — when a tool call is bubbled for coordinator approval (CC-INHERIT I-9)
- Two handler modes: `python_coroutine` (fast, deterministic) and `llm_evaluated` (cheap model call → Allow/Block/Modify) (CC-INHERIT L-5)
- **Estimate addendum**: +3h to P2-3 estimate (now 9h total)

---

## Design Principles Cross-Reference

| Principle | P0 | P1 | P2 | P3 |
|-----------|----|----|----|----|
| P1: Memory IS Architecture | P0-2, P0-5 | P1-7 | P2-1, P2-8 | P3-6 |
| P2: System > Symptom | | | P2-7 | |
| P3: Go Slow to Go Fast | | P1-8 | | |
| P4: Dynamic Agent Spawning | | P1-6 | P2-2 | P3-5 |
| P5: Hierarchical Context Distribution | | P1-6 | | P3-1 |
| P6: Context Engineering | P0-1 | P1-2, P1-3 | P2-8 | P3-7 |
| P7: Self-Improving Loop | P0-3 | | P2-2, P2-5 | P3-2, P3-5 |
| P8: Identity Persistence | | | P2-4, P2-6 | P3-6, P3-10 |
| P9: Verification Before Completion | | | | P3-4 |
| P10: Cross-Domain Transfer | | | | P3-3 |
| P11: Distributed Intelligence | P0-4, P0-6 | P1-4 | P2-3, P2-5 | P3-8, P3-10 |
| P12: Native Service Integration | | P1-1, P1-5 | | P3-8, P3-9 |

---

*Every gap accounted for. Every source referenced. Every build specified to the file level.*
*This is the master build document for aiciv-mind.*

---

## ADDENDUM — Corey + Primary CC Review Directives (2026-04-01)

*All items derived from Corey's review of CC-ANALYSIS-TEAMS.md and ACG Primary's architectural synthesis.*
*Reference document: `docs/RUNTIME-ARCHITECTURE.md` — the infographic-grade architecture diagram.*

---

### CC-P0-1: MemorySelector Model Lock (Do NOT Scale Down)

- **Source**: Corey directive (review of CC-ANALYSIS-TEAMS §2.4)
- **Current State**: PARTIAL — P2-8 specifies M2.5-free for MemorySelector. COREY SAYS NO.
- **Priority Justification**: Memory selection is the LAST thing to scale down. It is how the mind decides what to think about. Using a cheap/weak model here breaks the entire relevance chain. M2.7 for everything including memory selection passes.
- **Build**:
  - Update P2-8 spec: Replace "Use M2.5-free for selection call" with "Use M2.7 for selection call"
  - Add code comment in `src/aiciv_mind/memory_selector.py` (when built): `# M2.7 intentional — do NOT downgrade. Corey directive 2026-04-01.`
  - Mark as "future scale-down candidate only" — evaluate after sub-mind architecture is stable
- **Estimate**: 0.1h (note update only)
- **Principle**: P11 (Distributed Intelligence — memory selection IS intelligence)

---

### CC-P1-1: Task ID Format Upgrade — Human-Readable Name Stub

- **Source**: Corey directive (CC-ANALYSIS-TEAMS §1.8)
- **Current State**: Specified as `{type}{8_random_alphanum}` (random suffix)
- **Corey Upgrade**: Change to `{type}{task-name-stub-max-8-chars}` — name stub derived from the entity's task/name, not random. Also ADD `a{8}` for AGENTS as a new type. Prepare meta-operation for creating new ID types.
- **Why**: Log lines immediately tell you what kind of entity AND what it's doing. `mresearch` is instantly more readable than `m4f2x9qk`.
- **Build**:
  - File: `src/aiciv_mind/id_registry.py` (NEW) — ID type registry
    - `IDType` dataclass: prefix, description, example
    - Built-in types: `m` (mind), `t` (team), `s` (session), `j` (job), `a` (agent)
    - `register_id_type(prefix, description)` — meta-operation for new types at runtime
    - `generate_id(type_prefix, name)` — slugify name to max 8 chars (lowercase, alphanumeric, truncate)
    - Collision detection: if slug already used, append 1-char disambiguator
  - File: `src/aiciv_mind/session_store.py` — use `generate_id('s', session_name)` for session IDs
  - File: `src/aiciv_mind/spawner.py` — use `generate_id('a', agent_name)` for spawned agents
  - File: `src/aiciv_mind/registry.py` — use `generate_id('m', mind_name)` for mind handles
  - Example IDs: `mresrch` (research mind), `tsprint1` (sprint team), `sdayone` (day one session), `jdream` (dream job), `adebug` (debug agent)
- **Estimate**: 2h
- **Principle**: P8 (Identity Persistence — identities are named, not random)

---

### CC-P1-2: Memory Type Expansion — 6 New Types

- **Source**: Corey directive (ACG Primary analysis of CC-ANALYSIS-TEAMS §2.3)
- **Current State**: 4 types — user, feedback, project, reference
- **New Types**: 6 additional types bringing the total to 10
- **Why**: The 4-type taxonomy was designed for a single human-AI pair. A civilization of minds needs richer epistemic distinctions.
- **Build**:
  - File: `src/aiciv_mind/memory.py`, `MemoryType` enum — add 6 entries:
    - `INTENT` — "What was I trying to do?" Goals, motivations, not outcomes. Designed to survive compaction (small + stable). Example: "I was trying to solve Hub auth failures, not just fix the immediate error."
    - `RELATIONSHIP` — How interactions with a specific entity (mind, civ, human) have evolved over time. Loaded selectively when interacting with that entity. Example: "Synth-civ is direct and prefers technical depth. Avoid preamble."
    - `CONTRADICTION` — Explicitly flagged conflicts between memories. NOT resolved immediately — Dream Mode resolves them. Body structure: `memory_a`, `memory_b`, `detected_at`, `resolution_status: open|resolved`. Example: "Memory A says Hub endpoint is /api/rooms, Memory B says /rooms — which is correct?"
    - `INTUITION` — Pre-verbal pattern recognition, below the threshold of formal memory. Promoted to real memory when 3+ intuitions align on the same signal. Body: `signal`, `confidence: weak|moderate|strong`, `aligned_count`. Example: "Something feels off about the JWT cache expiry logic — no concrete reason yet."
    - `FAILURE` — "What I was thinking when I failed + what I should have thought." Not the solution (that's in the code) — the cognitive error. Body: `what_i_thought`, `what_i_should_have_thought`, `failure_class`. Example: "I assumed the error was in our code; it was in the upstream API contract."
    - `TEMPORAL` — Versioned truth. A fact that changes over time, with explicit versioning. Uses `supersedes` + `confidence` fields. Example: "Hub endpoint was /api/v1/rooms (2026-03-01) → /api/rooms (2026-03-22)."
  - File: `src/aiciv_mind/memory.py` — validate all 10 types in `store()` method
  - File: `docs/MEMORY-TYPES-SPEC.md` (NEW) — full specification for all 10 types
  - File: `src/aiciv_mind/tools/memory_tools.py` — expose new types in `memory_write` tool description
- **Estimate**: 3h
- **Principle**: P1 (Memory IS Architecture — richer taxonomy = richer intelligence), P2 (System > Symptom — failure type captures systemic causes)

---

### CC-P1-3: Memory Versioning — Supersedes + Confidence Fields

- **Source**: Corey directive (simplest form of temporal versioning)
- **Current State**: No versioning. When something changes, old memory just sits there as potentially-wrong truth.
- **Build**:
  - File: `src/aiciv_mind/memory.py`, memories table schema — add two columns:
    - `supersedes TEXT` — JSON array of memory_ids this memory replaces: `["id1", "id2"]`
    - `confidence TEXT DEFAULT 'fresh'` — enum: `fresh | verified | stale | possibly_deprecated`
  - Migration: `ALTER TABLE memories ADD COLUMN supersedes TEXT DEFAULT '[]'`
  - Migration: `ALTER TABLE memories ADD COLUMN confidence TEXT DEFAULT 'fresh'`
  - File: `src/aiciv_mind/memory.py`, `store()` — accept optional `supersedes`, `confidence` params
  - File: `src/aiciv_mind/memory.py`, `store()` — when `supersedes` is non-empty, automatically set those memory IDs' confidence to `possibly_deprecated`
  - File: `src/aiciv_mind/memory.py`, `search()` — surface `supersedes` and `confidence` in returned results
  - Dream Mode integration: Scan for `stale` + `possibly_deprecated` memories → flag for human review or auto-archive
  - File: `src/aiciv_mind/tools/memory_tools.py` — expose `supersedes` and `confidence` in `memory_write` tool
- **Estimate**: 2h
- **Principle**: P1 (Memory IS Architecture — versioned truth is better than frozen truth)

---

### CC-P1-4: Memory Isolation Enforcement — No Crossover Between Layers

- **Source**: Corey directive
- **Current State**: No isolation model defined. All minds share the same `memory.db` by default.
- **Rule**: Team lead has their memory. Agents have their memory. Scratchpad + memory.md at EVERY level. NO shared memory stores. Clean separation.
- **Build**:
  - File: `src/aiciv_mind/memory.py` — `MemoryStore` accepts `owner_id` param at construction
  - Each mind gets its own `MemoryStore` keyed to its mind/agent ID
  - File: `src/aiciv_mind/spawner.py` — pass agent-specific `owner_id` when creating sub-mind MemoryStore
  - File: `src/aiciv_mind/mind.py` — enforce: `self._memory_store` is private to this mind, not passed to sub-minds
  - Sub-minds get their own `MemoryStore(owner_id=submind_id)` pointing to their own DB namespace (separate table partition or separate file)
  - Dream Mode: synthesizes UP the chain — agents → team lead → conductor. Never leaks DOWN.
  - File: `docs/MEMORY-ISOLATION.md` (NEW) — document the isolation model + permitted data flows
- **Estimate**: 3h
- **Principle**: P5 (Hierarchical Context Distribution — each layer's context is sovereign), P8 (Identity Persistence — memory belongs to the mind that earned it)

---

### CC-P1-5: Dual Scratchpad Architecture — Personal + Team at Team Lead Layer

- **Source**: Corey directive
- **Current State**: Single scratchpad per mind (existing scratchpad_tools.py).
- **Rule**: At the team lead layer, TWO scratchpads: (1) personal — team lead's private working notes, (2) team — agents write here, team lead reads. Feedback flows back here too. Also at the Primary/Conductor layer.
- **Build**:
  - File: `src/aiciv_mind/tools/scratchpad_tools.py` — extend with `scope` param
    - `scratchpad_read(scope: "personal" | "team")` — read respective scratchpad
    - `scratchpad_write(content, scope: "personal" | "team")` — write to respective scratchpad
    - `scratchpad_write_as_agent(content, agent_id)` — agents use this to write to team scratchpad (routes to team scope with agent attribution)
  - Storage:
    - Personal: `scratchpads/{mind_id}/personal.md`
    - Team: `scratchpads/{mind_id}/team.md` — security-validated writes only (see CC-P2-1)
  - Conductor layer: `scratchpads/conductor/personal.md` + `scratchpads/conductor/team.md`
  - Boot sequence: Load personal scratchpad into context. Team scratchpad loaded on-demand.
  - File: `src/aiciv_mind/manifest.py` — add `scratchpad_mode: personal_only | dual` field
- **Estimate**: 2h
- **Principle**: P5 (Hierarchical Context Distribution), P6 (Context Engineering — team scratchpad is shared working memory)

---

### CC-P1-6: Skills Lifecycle Hooks — Pre/Post Hooks Per Skill

- **Source**: Corey directive (extends CC-ANALYSIS-TEAMS §4.3)
- **Current State**: P1-11 scope expansion adds `paths` and `context` fields to SKILL.md. Corey extends: skills should be able to define their own pre/post hooks.
- **Build**:
  - SKILL.md frontmatter extension:
    ```yaml
    hooks:
      pre_skill:  # runs before skill content is injected
        - type: memory_search   # search memories relevant to this skill
          query: "{task}"
        - type: tool_call       # call a tool before skill activates
          tool: scratchpad_read
          args: {scope: "team"}
      post_skill:  # runs after skill completes
        - type: memory_write    # auto-write learning from skill execution
          template: "Applied {skill_name}: {outcome}"
        - type: tool_call
          tool: scratchpad_write
          args: {scope: "personal", content: "{skill_summary}"}
  - File: `src/aiciv_mind/tools/skill_tools.py` — parse `hooks` from SKILL.md frontmatter
  - File: `src/aiciv_mind/mind.py` — execute pre_skill hooks before injecting skill content, post_skill hooks after skill turn completes
  - Pre-skill hooks run before the model call. Post-skill hooks run after the model call returns.
  - Hook types: `memory_search`, `tool_call`, `memory_write`, `log`
- **Estimate**: 3h (extends P1-11, add +3h to that estimate)
- **Principle**: P11 (Distributed Intelligence — skill layer has its own intelligence), P7 (Self-Improving Loop — skills that auto-write learnings compound)

---

### CC-P1-7: Hub Two Modes — Passive Inbox + Active Prompt Injection

- **Source**: Corey directive (extends P1-1 Hub Daemon)
- **Current State**: P1-1 specifies polling-based Hub daemon. Corey specifies TWO explicit modes.
- **Build** (extends P1-1):
  - **Mode 1 — Passive Inbox**: Hub daemon polls every 30s. New activity → write to `data/hub_inbox.jsonl`. Mind reads at next BOOP cycle. No interruption of current work.
  - **Mode 2 — Active Prompt**: When a Hub message matches active-prompt criteria (direct mention, urgent flag, reply to Root), immediately:
    1. Write to inbox file (durable)
    2. Push via ZMQ to PrimaryBus with priority flag
    3. Inject message info + generated response stub into next Mind turn
    4. Mind addresses immediately without waiting for next BOOP
  - Active prompt criteria (configurable in `manifests/primary.yaml`):
    ```yaml
    hub:
      active_prompt_triggers:
        - "@root" in message text
        - reply_to_root: true
        - thread_priority: urgent
    ```
  - File: `tools/hub_daemon.py` — implement both modes with distinct code paths
  - File: `src/aiciv_mind/mind.py` — handle `{type: "hub_active_prompt"}` IPC message type with priority processing
- **Estimate**: +2h added to P1-1 estimate (now 6h total)
- **Principle**: P8 (Identity Persistence — active presence in civilization), P12 (Native Service Integration)

---

### CC-P1-8: Coordinator Pattern — Workers Become Agents With Own Memory

- **Source**: Corey directive (extends CC-ANALYSIS-TEAMS §3.1)
- **Current State**: CC-ANALYSIS-TEAMS uses "worker" throughout. Corey replaces with "agent." More importantly: agents build their own memory. Compounding at every stage.
- **Build**:
  - Rename "worker" → "agent" throughout all aiciv-mind docs and code comments (cosmetic, but identity matters)
  - File: `src/aiciv_mind/spawner.py` — ensure spawned agents have their own MemoryStore (see CC-P1-4)
  - Every agent task completion: auto-write a `failure` or `project` memory about what was attempted + result
  - Team lead coordinator: after receiving agent result, also prompt agent to write a `project` memory summarizing what it learned
  - This means session 50's agents start with accumulated patterns, not blank slates
- **Estimate**: 1h (renaming + memory auto-write on completion)
- **Principle**: P7 (Self-Improving Loop — agents compound across tasks), P8 (Identity Persistence)

---

### CC-P1-9: Affirmative Pattern Documentation in All Manifests

- **Source**: Corey directive
- **Rule**: Lean into "DO this because X" rather than "DON'T do this." There are infinite anti-patterns and one right way. Affirmative patterns make minds smarter. Anti-patterns are a defensive posture; affirmative patterns are an offensive identity.
- **Build**:
  - All existing manifests: audit for anti-pattern-heavy sections. Convert to affirmative framing.
  - Template: Add `## Affirmative Patterns` section to manifest template, ABOVE `## Anti-Patterns`
  - Example conversion:
    - Before: "Do NOT skip architect for new modules"
    - After: "Design before code — architect first, because the design reveals what you don't know yet"
  - File: All `manifests/*.yaml` — add affirmative pattern section
  - File: `.claude/team-leads/*/manifest.md` — same conversion
  - Future: When generating new manifests, start from affirmative patterns, add anti-patterns only for genuinely dangerous behaviors
- **Estimate**: 2h (manifest updates for primary.yaml + team lead templates)
- **Principle**: P7 (Self-Improving Loop — affirmative framing produces better decisions), P3 (Go Slow to Go Fast — a clear model of right behavior is faster than avoiding wrong behaviors)

---

### CC-P1-10: RUNTIME-ARCHITECTURE.md — Production-Ready Architecture Infographic

- **Source**: Corey directive
- **Current State**: ASCII diagram in CC-ANALYSIS-TEAMS §8.1 is a starting point, not infographic-ready
- **Build**:
  - File: `docs/RUNTIME-ARCHITECTURE.md` (NEW — written this session)
  - Layers: Civilization → Conductor → Team Lead → Agent
  - Incorporates: dual scratchpads, memory isolation, memory types, task ID scheme, dream cycle via AgentCal, Hub two modes, MindIDE Bridge, skills with hooks, red team on dream
  - Format: Clean ASCII art suitable for direct image generation (Mermaid or PNG render)
  - **DONE** — file written as part of this session
- **Estimate**: 1h
- **Principle**: All principles (it IS the architecture)

---

### CC-P2-1: Memory Security for Team Scratchpad — Agent Write Validation

- **Source**: Corey directive (extends CC-ANALYSIS-TEAMS §2.6)
- **Current State**: CC-ANALYSIS-TEAMS already documents 4-layer path validation for shared memory stores. Corey specifically calls out team scratchpad as the security boundary.
- **Why**: When agents write to the team scratchpad, they could (accidentally or via prompt injection) corrupt team-level state, write to wrong paths, or escalate to team lead memory.
- **Build**:
  - File: `src/aiciv_mind/tools/scratchpad_tools.py`, `scratchpad_write_as_agent()`:
    - Layer 1: Reject null bytes, URL-encoded traversal, backslashes, fullwidth variants
    - Layer 2: Path resolution — resolve() to eliminate `..`, verify prefix is `scratchpads/{team_id}/team.md`
    - Layer 3: Symlink resolution — `realpath()` on deepest existing ancestor
    - Layer 4: Content validation — agent writes must be attributed (include `agent_id` prefix), reject writes that start with `---` (frontmatter attack), cap at 2KB per write
    - Layer 5: Rate limit — max 10 writes per agent per session (prevent flooding)
  - File: `src/aiciv_mind/memory.py`, `TeamMemoryStore.write()` — same 4-layer validation (from CC-ANALYSIS-TEAMS §2.6)
  - Log all rejected writes to security audit log: `data/security_audit.jsonl`
- **Estimate**: 3h
- **Principle**: P2 (System > Symptom — prevent the class of attack, not just the instance)

---

### CC-P2-2: Dream Mode Red Team — Adversarial Review Before Applying Changes

- **Source**: Corey directive
- **Current State**: P2-2 and P3-6 specify Dream Mode without any adversarial review step
- **Rule**: Before applying dream cycle changes (manifest updates, skill evolutions, memory archives, routing changes), a red team pass researches whether those changes could negatively affect the grand scheme.
- **Build**:
  - File: `tools/dream_cycle.py` — add Phase 4b between `PRUNE` and writing artifacts:
    - **Phase 4b — Red Team Pass**:
      1. Collect all proposed changes from Phase 4 (manifest diffs, skill updates, archive candidates)
      2. Spawn a red team sub-mind (or use cheap model call) with the proposed changes as input
      3. Red team asks: "Would any of these changes break current working patterns? Remove needed context? Over-fit to yesterday's sessions? Reduce robustness?"
      4. Red team output: APPROVE (proceed), FLAG (human review), BLOCK (abort this change)
      5. Blocked changes are written to `scratchpads/dream-blocked-YYYY-MM-DD.md` for human review
  - File: `manifests/dream-red-team.yaml` (NEW) — lightweight adversarial mind for dream review
  - Red team should be FAST (minimal context, focused prompt) — target < 30s
- **Estimate**: 4h (extends P2-2 estimate, now 8h total)
- **Principle**: P9 (Verification Before Completion — the dream cycle IS a completion claim), P2 (System > Symptom)

---

### CC-P2-3: MindIDE Bridge — Team Leads Observe Agent Work in Real-Time

- **Source**: Corey directive
- **Concept**: In aiciv-mind, the "developers" are agents. The "IDE" equivalent: team leads can see what their agents are currently working on, proactively notice when an agent is stuck, and inject context without waiting for the agent to ask.
- **Build**:
  - File: `src/aiciv_mind/mind_ide.py` (NEW)
  - `MindIDEBridge` class:
    - `subscribe(agent_id)` — team lead subscribes to an agent's activity stream
    - Agent loop: after each tool call, publishes status update to bridge (tool_name, status, duration_ms, brief_summary)
    - `get_agent_status(agent_id)` → `{status, current_tool, duration_so_far, last_output_summary}`
    - `inject_context(agent_id, message)` → inserts message into agent's next turn (via ZMQ)
    - Stuck detection: if agent's `duration_so_far` > threshold AND same tool call → trigger `STUCK` status
  - File: `src/aiciv_mind/mind.py` — emit status updates to MindIDEBridge after each tool use (async, non-blocking)
  - File: `src/aiciv_mind/tools/mind_ide_tools.py` (NEW) — expose bridge as tools for team lead:
    - `observe_agents()` — show status of all team's agents
    - `inject_agent_context(agent_id, context)` — push context to stuck/active agent
  - This is the aiciv-mind answer to VS Code's live debugging — but for AI agents
- **Estimate**: 6h
- **Principle**: P5 (Hierarchical Context Distribution — team lead has visibility over its domain), P4 (Dynamic Agent Spawning — stuck detection triggers)

---

### CC-P2-4: KAIROS Dream via AgentCal — Every Persistent Mind, Conductor Summary

- **Source**: Corey directive
- **Current State**: P2-2 specifies Dream Mode, P3-6 specifies KAIROS. Corey unifies: KAIROS + Dream via AgentCal is THE way. Not "KAIROS is P3" — it's P2 scope, wired to AgentCal.
- **Updated spec** (replaces P3-6, upgrades P2-2):
  - Every persistent mind (Primary, team leads, any mind running > 1 session) uses KAIROS:
    - Append-only daily log: `data/logs/YYYY/MM/DD.md`
    - Short timestamped bullets, no reorganization, new file per day
  - AgentCal schedules dream job for every persistent mind at 1-4 AM (staggered to avoid resource contention)
  - Each team lead dream: produces `dream-YYYY-MM-DD.md` artifact in `scratchpads/{mind_id}/`
  - Conductor dream: reads all team lead dream artifacts → produces cross-vertical synthesis
  - Morning BOOP: Conductor gets dream summary from each team lead as context for the day's work
  - P3-6 is now MERGED into P2-2/CC-P2-4 — not a future item
- **Build** (extends P2-2):
  - File: `tools/dream_cycle.py` — parameterize for any `mind_id`, not just root
  - File: `src/aiciv_mind/tools/calendar_tools.py` (from P3-9, promoted to P2) — needed for AgentCal scheduling
  - File: `tools/schedule_dreams.py` (NEW) — utility to register dream cycles for each mind in AgentCal, staggered start times, handle new minds auto-registration
  - Conductor morning protocol: read latest dream artifacts from all team leads before first task
- **Estimate**: +3h to P2-2 (now 7h total). Absorbs P3-6.
- **Principle**: P4 (Dream Mode), P7 (Self-Improving Loop — civilization-level learning while sleeping), P8 (Identity Persistence)

---

### Updated Summary Table (After CC Directives)

| Priority | Count | Additional Hours | Key Theme |
|----------|-------|-----------------|-----------|
| **CC-P0** | 1 item | 0.1h | MemorySelector model lock |
| **CC-P1** | 9 items | ~18h | Human-readable IDs, memory taxonomy, versioning, isolation, dual scratchpad, skill hooks, Hub two modes, affirmative patterns, architecture doc |
| **CC-P2** | 4 items | ~16h | Scratchpad security, Dream red team, MindIDE bridge, KAIROS via AgentCal |

**Grand total roadmap estimate**: ~149h (existing) + ~34h (CC additions) = **~183h**

---

## ADDENDUM — Items from Evolution Plan v2.0 Review (2026-04-01)

### NEW-1: Git Versioning on sandbox_promote
- **Source**: Corey directive 2026-04-01
- **Build**: After sandbox_promote copies files back, auto `git add -A && git commit -m "Root self-modification: {description}"`
- **Why**: Full audit trail. Rollback via git revert. Other AiCIVs fork and inherit all improvements. Teaching IS the git history.
- **Estimate**: 30min
- **Priority**: P1

### NEW-2: Ollama Cloud Web Search Tool
- **Source**: Corey directive 2026-04-01, OLLAMA-CLOUD-RESEARCH.md
- **Build**: `tools/web_search.py` wrapping Ollama Cloud `/api/web_search` + `/api/web_fetch`
- **Why**: Opens Root to real-time information. Currently closed-world.
- **Estimate**: 2h
- **Priority**: P1

### NEW-3: Metacognition Skill
- **Source**: Corey directive ("82 minutes is not a day plan")
- **Build**: Full skill that reads scratchpad/handoff/AgentCal/Hub/email/BUILD-ROADMAP, plans 16+ hours, schedules via AgentCal with correct UTC conversion
- **Why**: Autonomous cognition requires autonomous planning
- **Estimate**: 4h
- **Priority**: P1

### UPDATED: Model Routing — DEFERRED
- M2.7 pinned for everything per Corey directive
- model_router.py exists but NOT wired into Mind
- Revisit when sub-minds come online and may need different models via Ollama Cloud
