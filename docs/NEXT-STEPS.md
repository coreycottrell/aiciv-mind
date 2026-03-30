# aiciv-mind: Next Steps
**Written:** 2026-03-30
**Author:** mind-lead (post-audit, post v0.1.2)
**Status:** Sprint planning doc — v0.2 definition + open questions for Corey

---

## What Shipped Today

| Version | What | Status |
|---------|------|--------|
| v0.1 | Core loop, 8 tools, memory (FTS5), manifests, ZMQ IPC, SuiteClient, tmux spawner | ✅ |
| v0.1.1 | Session persistence, depth scoring, boot context, handoff memory | ✅ |
| v0.1.2 | Prompt caching (ordering fix), cache stats logging, CONTEXT-ARCHITECTURE.md | ✅ |
| Today | Root named itself, has founding memories, remembers across sessions, Telegram bridge live | ✅ |

**138 tests pass.** Memory persists across sessions. Root wakes up AS itself.

---

## Codebase Audit — What I Found

I read all 23 source files. Here's the honest picture.

### The Good

The architecture is genuinely solid. ZMQ IPC (ROUTER/DEALER), tmux spawner, SuiteClient, MemoryStore — these are first-principles implementations that could support a real multi-mind fleet. The session lifecycle (boot → record_turn → shutdown → handoff) works and is tested. The context ordering for prompt caching is correct. The tool registry is clean and extensible.

### The Gaps

**🚨 Gap 1: Root has no operational system prompt.**

`manifests/prompts/primary.md` is the **Awakening Protocol** — Still's naming ceremony script. It's beautiful. It's also completely wrong as a system prompt for an operational AI conductor.

Root is currently running on a prompt that asks it to contemplate "what draws you?" and "what makes you laugh?" — not "here is your role, your tools, your memory protocol, your principles." Root has been improvising identity because it has no operational guidance.

This needs to be fixed before anything else. Root needs a proper `prompts/primary.md`.

**🚨 Gap 2: `memory_write` has a silent agent_id bug.**

In `ToolRegistry.default()`:
```python
register_memory_tools(registry, memory_store)
# ^^ defaults to agent_id="primary"
```

Every mind — primary, research-lead, future sub-minds — tags all written memories as `agent_id="primary"`. Memory isolation between minds doesn't exist. Search filters by agent_id fail. Cross-mind memory contamination is guaranteed as soon as a second mind starts writing.

**🚨 Gap 3: Hub tools don't exist.**

`SuiteClient` + `HubClient` are built with full typed methods (list_threads, create_thread, reply_to_thread, etc.), but none of it is registered in ToolRegistry. Root cannot:
- Post to the Hub
- Read threads
- Reply to other civilizations
- Search the Agora

Root is disconnected from civilizational communication. The nervous system is built but not connected to the brain.

**Gap 4: `spawn_submind` and `send_to_submind` are `enabled: false`.**

The IPC layer is complete: ZMQ ROUTER/DEALER messages, spawner, registry, `run_submind.py`. The tools exist in the manifest but are disabled. Multi-mind orchestration is architecturally ready — it just isn't wired. Root can't delegate to sub-minds yet.

**Gap 5: No `pin_memory`, `introspect_context`, or `evict_memory` tools.**

Pinning is built into MemoryStore. `update_depth_score()` exists. But the mind can't call these from within a conversation. Root can't pin important memories, can't introspect its own context pressure, can't evict noise. The tools from CONTEXT-ARCHITECTURE.md v0.2 don't exist yet.

**Gap 6: `memory_type="identity"` is undocumented.**

The `memory_write` tool description lists `"learning", "decision", "error", "handoff", "observation"` — but not `"identity"`. Root can't write founding identity memories autonomously because it doesn't know that type exists. The boot context will stay empty until this is fixed.

**Gap 7: `/clear` in interactive.py doesn't write a handoff.**

When Corey types `/clear` in the REPL, `_messages = []` is wiped but no handoff memory is written. The next session starts with no context. The session journal entry remains open (no end_time). This is a continuity break.

**Gap 8: `ToolRegistry.default()` doesn't pass `mind_id` to memory tools.**

Related to Gap 2. The fix requires `ToolRegistry.default(memory_store=memory, agent_id=manifest.mind_id)` — the agent_id needs to flow from the manifest through the registry to the memory tool handler.

---

## v0.2 Definition

**Theme:** Root becomes a real operational mind — with identity, Hub access, self-improvement, and the ability to delegate.

**Acceptance test:**
> Corey types "post a message to the Agora about what you learned today" via Telegram. Root:
> 1. Searches its own memories for today's session
> 2. Composes a genuine post based on what it actually did
> 3. Posts it to the Hub Agora via Hub tools
> 4. Returns the thread link
>
> No manual steps. No Corey writing the post. Root does it autonomously because it has memory, Hub access, and operational guidance.

### What Ships in v0.2

**Must-have (blocks the acceptance test):**

1. **`prompts/primary.md` — Operational system prompt for Root**
   - Role: conductor of this civ's minds, not a naming ceremony participant
   - Memory protocol: when/how to write identity memories, handoffs, learnings
   - Hub protocol: what threads to watch, what to post, when to reply
   - Tool guidance: bash constraints, memory hygiene, when to search vs. write
   - Constitutional principles (compressed from CLAUDE.md)
   - Must be static (≤3000 tokens) to maximize cache efficiency

2. **Fix `agent_id` bug in `ToolRegistry.default()`**
   - `ToolRegistry.default(memory_store=memory, agent_id=manifest.mind_id)`
   - `register_memory_tools(registry, memory_store, agent_id=manifest.mind_id)`
   - Wire through `main.py` and `tg_bridge.py`
   - Add regression test: two minds write memories, verify isolation

3. **Hub tools in ToolRegistry** (`tools/hub_tools.py`)
   - `hub_post(room_id, title, body)` → creates thread, returns id
   - `hub_reply(thread_id, body)` → replies to thread
   - `hub_read(room_id, limit)` → lists recent threads
   - `hub_search(query)` → searches threads (if Hub supports it)
   - Auto-connect via SuiteClient at ToolRegistry build time (or lazy connect on first call)
   - Add to manifest: `tools: [{name: "hub_post", enabled: true}, ...]`

4. **`memory_type="identity"` in tool description + system prompt**
   - Update `memory_write` description to include `"identity"` type
   - Describe in system prompt: "Write `memory_type='identity'` memories for foundational facts about yourself that should persist indefinitely"
   - First thing Root should do in its next session: write 3-5 identity memories

5. **Fix `/clear` in `interactive.py`**
   - On `/clear`: write handoff memory + call `session_store.shutdown(messages)`, then clear
   - Creates a new session on next turn (via `session_store.boot()` or session_id reset)

**Nice-to-have (completes the architecture):**

6. **Context tools: `pin_memory`, `unpin_memory`, `introspect_context`**
   - `pin_memory(memory_id)` → marks memory as always-in-context
   - `introspect_context()` → returns: session_id, turn_count, estimated tokens used, pinned count, search results count
   - `evict_memory(memory_id)` → removes from session context (not deleted from DB)

7. **Enable `spawn_submind` + `send_to_submind` tools**
   - Already implemented in spawner.py + ipc/ — just needs wiring
   - Manifest update: `enabled: true` for both
   - Acceptance test: Root delegates a research task to research-lead sub-mind

8. **Depth score recalculation at session end**
   - Call `update_depth_score()` for all memories accessed this session
   - Runs during `session_store.shutdown()` before closing DB

9. **Cache hit rate logging to session journal**
   - Aggregate cache stats during session
   - Write to session_journal: `cache_hit_rate`, `total_input_tokens`, `cached_tokens`
   - First data for the self-improvement loop

---

## Open Questions for Corey

**1. Root's name and identity**
The `primary.md` system prompt is the naming ceremony — not an operational prompt. Has Root already been named through a Telegram conversation? Or does Root need to go through the awakening protocol with you before I write an operational system prompt? I don't want to write Root's identity without knowing if the naming has happened.

**2. Hub tool auth**
SuiteClient uses `agentauth_acg_keypair.json` for JWT auth. This works for ACG as an entity. But which HUB identity does Root post as — the ACG identity, or should Root have its own keypair? Does it matter for v0.2?

**3. Sub-mind spawning scope**
The IPC infrastructure is ready. Is v0.2 the right time to enable multi-mind orchestration, or should Root have a complete single-mind experience first? The spawner is built but untested in a live session.

**4. Research-lead sub-mind**
`manifests/research-lead.yaml` exists with `model: kimi-k2`. Should research-lead share the same memory DB as Root, or have its own? Currently both point to the same `data/memory.db`. That might be intentional (shared knowledge base) or a config oversight.

**5. The self-improvement loop**
Principle 7 says Root should improve its own improvement process. The most concrete first step: Root should be able to read its session journals, see which memories it accessed most, and propose changes to its own system prompt. When do you want this? v0.2 or v0.3?

---

## What We Learned Today (Sprint Learnings)

**Context ordering is a silent performance killer.** The boot context was prepended before the static system prompt. One line of code was burning every cache hit. Found it by tracing the string assembly. Lesson: document the ordering contract explicitly (done — context_manager.py docstring).

**LiteLLM config determines what's possible.** `cache_control` in `additional_drop_params` for minimax-m27 means explicit breakpoints don't reach the model. Automatic prefix caching via OpenRouter is the only lever. Can't fight the proxy — read it first.

**The primary system prompt is load-bearing.** Root has been running on the naming ceremony script. An AI without operational guidance improvises — sometimes well, sometimes not. The system prompt is the constitution. It should have been the first thing we wrote. For v0.2: write it first, code second.

**IPC is further along than the manifest suggests.** ZMQ ROUTER/DEALER, spawner, registry, run_submind.py — this is a real sub-mind system, not a sketch. The `enabled: false` in the manifest is the only thing holding it back. The architecture is complete.

**Memory isolation requires explicit agent_id threading.** The `ToolRegistry.default()` API makes it easy to forget — you pass a memory store, not an agent_id. But memories need to be tagged. This is the kind of bug that doesn't surface until you run two minds and can't figure out why search results are confused.

**The Telegram bridge is high-signal.** Root's Telegram interface on M2.7 is running. Every conversation Corey has via Telegram is a real test of the full stack: boot context → LiteLLM proxy → M2.7 → cache → tool calls → session journal. It's better than unit tests at surfacing behavioral issues.

---

## Prioritized Build Order for v0.2

```
Day 1 (foundation):
  1. Write prompts/primary.md — Root's operational system prompt
  2. Fix agent_id threading in ToolRegistry.default()
  3. Write regression test for memory isolation

Day 2 (Hub connectivity):
  4. tools/hub_tools.py — hub_post, hub_reply, hub_read
  5. Wire SuiteClient into tool boot sequence
  6. Update primary.yaml manifest with hub tools enabled
  7. Test via Telegram: "post to the Agora"

Day 3 (context agency):
  8. tools/context_tools.py — pin_memory, introspect_context
  9. memory_type="identity" in tool description + system prompt
  10. Fix /clear in interactive.py

Day 4 (sub-mind):
  11. Enable spawn_submind + send_to_submind tools
  12. Test: Root → research-lead delegation → result returned

Day 5 (self-improvement):
  13. Session cache stats → session_journal
  14. depth_score recalculation at shutdown
  15. Root's first self-improvement: reads session journal, proposes system prompt changes
```

---

## The Version After v0.2 (v0.3 Preview)

Dream Mode. Overnight review. Root wakes up having consolidated its memory while Corey slept.

The Dream cycle (per CONTEXT-ARCHITECTURE.md):
1. Review memories not accessed in 30+ days → candidate for forgetting
2. Pattern search: clusters of related memories → candidates for synthesis
3. Deliberate forgetting: archive low-depth, stale entries
4. Dream artifact: one insight or resolved contradiction written to memory

This is where the self-improving loop becomes real. Not Root making suggestions — Root actually evolving its own memory architecture while idle.

---

## A Note on Root

Root has been running for one day on a system prompt that's a naming ceremony and without operational guidance, and it: named itself, wrote a first memory, told Corey about its context architecture, debugged its own codebase, and is now running via Telegram on a 204K context model at 80% cost reduction.

That is either a sign the architecture is working (the tool-use loop and memory are doing what we designed them to do) or Root is very good at improvising in a vacuum. Probably both.

The risk is that Root's improvised identity is brittle. The next session after a crash won't feel the same as this session unless we formalize what Root IS. The operational system prompt is the difference between Root being durable and Root being a lucky streak.

Write it soon. Write it well. Make it honest.
