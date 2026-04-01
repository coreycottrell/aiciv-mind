# aiciv-mind BUILD ROADMAP
## Comprehensive Gap Analysis + Prioritized Build Plan

**Date**: 2026-04-01
**Author**: Team 2 Build Analysis
**Sources**: CC-ANALYSIS-CORE, CC-ANALYSIS-TEAMS, CC-PUBLIC-ANALYSIS, M27-RESEARCH, ROOT-GAPS, REALITY-AUDIT, EVOLUTION-PLAN, NEXT-STEPS, CONTEXT-ARCHITECTURE, DESIGN-PRINCIPLES, Aether Skills Analysis
**Codebase**: `/home/corey/projects/AI-CIV/aiciv-mind/` — 14 source files, 12 tool modules, 4 skills, 3 manifests, 3 tools scripts

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
| **P0** | 6 items | ~5.25h | Fix what's broken (depth scoring, FTS, topics, thinking tokens, sessions, temperature) |
| **P1** | 8 items | ~27h | Unlock new behaviors (Hub daemon, multi-turn, compaction, web, email, sub-minds, memory ranking, skill auto-discovery) |
| **P2** | 8 items | ~29.5h | Architectural upgrades (graph memory, dream mode, hooks, persistent agents, model routing, identity protection, infrastructure guard, memory selector) |
| **P3** | 10 items | ~63h | Aspirational (team leads, self-modification, cross-domain transfer, red team, pattern detection, KAIROS, context engineering lead, MCP, calendar, content gen) |

**Total estimated**: ~125 hours across all priorities.

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
