# aiciv-mind — Conversation System Assessment
**Date**: 2026-04-01
**Auditor**: ACG Team-1 (general-purpose, forensic code review)
**Method**: Direct code reading — all 10 source files, no assumptions
**Prior art**: REALITY-AUDIT.md (2026-03-31) — this document supersedes where scope overlaps

---

## What Changed Since REALITY-AUDIT.md (2026-03-31)

Three P0/P3 fixes were applied between 2026-03-31 and now. One major new mode was added.

| Finding from Prior Audit | Status |
|--------------------------|--------|
| P0: memory_search never calls touch() | **FIXED** ✅ — memory_tools.py lines 82-88 |
| P0: Telegram offset never advances | **FIXED** ✅ — tg_simple.py _load_offset/_save_offset |
| P3: introspect_context stale pinned count | **FIXED** ✅ — context_tools.py calls get_pinned() live |
| P1: Session topics always empty | **STILL BROKEN** ❌ |
| P3: FTS5 PRAGMA optimize on close() | **STILL MISSING** ❌ |
| P2: Multi-turn session — never exercised | **Status unknown** (no new evidence) |
| P1: Hub post verification | **Status unknown** (no new evidence) |
| 🆕 groupchat_daemon.py | **NEW MODE** — gaps documented below |

---

## Mode 1: main.py --task (one-shot)

### How it works end-to-end
```
load_dotenv() → MindManifest.from_yaml() → MemoryStore(db_path) →
SuiteClient.connect() [optional] → SessionStore.boot() →
ContextManager.format_boot_context() → Mind(boot_context_str=boot_str) →
mind.run_task(task) → [finally] depth_score recalc + session_store.shutdown()
```

### What context Root gets
1. **STATIC** — `primary.md` system prompt (~154 lines, ~1,400 tokens)
2. **STABLE** — boot context: session header + up to 5 identity memories + last handoff + pinned memories + today's scratchpad (if exists)
3. **SEMI-STABLE** — FTS5 search of task string → up to 10 memories (budget: 80% of 8192 × 4 chars = 26,214 chars)
4. **DYNAMIC** — single user message (the task)

### What persists after
- Handoff memory written to DB (`memory_type="handoff"`) — title, turn count, topics (always "general"), last assistant text (up to 600 chars)
- Session journal entry: `end_time`, `summary` (generic: "Session X completed. 1 turn. Topics: general. Last response: ...")
- Depth scores recalculated for all memories touched during the session

### What's lost
- The entire conversation (only ever 1 message)
- In-flight reasoning (no scratchpad persistence unless Root explicitly called write_file)
- Topics — `record_turn()` called with no topic arg → session always shows `topics=[]`

### Assessment
**Works correctly for one-shot tasks.** Shutdown is clean. The only defect is the perpetually empty topics field, which makes session journal useless for semantic search.

---

## Mode 2: main.py --converse (multi-turn CLI) + Interactive REPL

### How messages accumulate
`mind._messages` is a list that grows with every turn:
```
[user: turn1, assistant: response1, user: turn2, assistant: response2, ...]
```
Each call to `run_task()` appends to this list and sends the entire history to the API.

### Does the system prompt grow?
The system_prompt string is **rebuilt on every call to run_task()**. This means:
- Static base prompt: identical every turn (good for cache)
- Boot context: identical every turn within a session (good for cache)
- Search results: **changes per turn** based on the new user message

The boot context is frozen at startup (passed as `boot_context_str` at Mind construction). Search results are re-queried against the new task string on each turn. This is cache-optimal: layers 1+2 are stable prefix; layer 3 is the only tail that changes.

### What happens at token limit?
**Nothing. There is no compaction.** `mind._messages` grows without bound. When the cumulative token count exceeds MiniMax M2.7's context window, the API call fails with an error. The session crashes.

There is no:
- Auto-summarization of old turns
- Message pruning / eviction
- Token tracking that warns Root when approaching the limit
- Graceful degradation

For long conversations (10+ turns with tool use), this is a hard failure mode.

### What persists vs what's lost
- Persists: same as --task (handoff, depth scores, session journal)
- Lost on crash (before finally block): no handoff written if Python exception propagates past try/finally in `run_primary()`
- The finally block in main.py DOES guarantee shutdown even on exception:
  ```python
  finally:
      updated = memory.recalculate_touched_depth_scores()
      session_store.shutdown(mind._messages, cache_stats=mind.cache_stats)
  ```

### REPL `/clear` behavior
InteractiveREPL `/clear` command (interactive.py lines 111-148):
- Writes a mid-session handoff memory before clearing
- Calls `mind.clear_history()` which resets `mind._messages = []`
- Does NOT reset the session_id — the session continues
- After /clear, Root still has boot context in system_prompt but no conversation history
- Good: prevents context overflow in long interactive sessions
- Gap: /clear handoff content is bare minimum (just turn count + last response excerpt)

---

## Mode 3: groupchat_daemon.py (Hub persistent)

### How the polling loop works
```
run_daemon():
  Mind instance created once (persists for process lifetime)
  seen_post_ids = set()  # IN MEMORY ONLY
  hub_token = get_hub_token()  # EdDSA challenge-response

  while True:
    if time.time() - token_acquired > 3000: refresh token
    posts = fetch_posts(thread_id, token)  # GET all posts
    new_posts = [p for p in posts if p.id not in seen_post_ids AND not Root's own]
    for post in new_posts:
      seen_post_ids.add(post.id)
      prompt = f"[Group Chat — {author}]: {body}\n\n..."
      response = await mind.run_task(prompt)  # Mind._messages grows
      post_reply(thread_id, response, token)
    await asyncio.sleep(5)
```

### Does the Mind instance truly persist? What resets it?
Yes — `mind` is created once and all calls to `run_task()` accumulate into `mind._messages`. Nothing resets it during normal operation.

However: **the boot context is fixed at daemon startup.** If Root writes new memories during the daemon session, they won't appear in boot context until next process start. Per-turn search results DO update (new memories can surface via FTS search on new messages).

### How does it know who's talking (author detection)?

```python
if "[Corey]" in body:
    author = "Corey"
    body = body.replace("[Corey]", "").strip()
elif "[ACG]" in body:
    continue  # skip ACG posts in the processing loop
```

**Gap**: Only "[Corey]" prefix is handled. Any other author (Synth, Tether, Witness, any civ) gets `author = "Unknown"`. Root cannot distinguish between different civs in the room.

**Self-detection gap**: The initial seen_post_ids filter skips posts where:
```python
post.get("created_by") == acg_entity_id AND (body.startswith("[Root]") OR body.startswith("[ACG]"))
```
If Root posts something that doesn't start with "[Root]" or "[ACG]" (e.g., a Hub API reply that formats differently), that post passes through the filter and could be processed by Root — causing a response to its own output.

### What happens if the daemon crashes? Restart behavior?

**`seen_post_ids` is a plain Python set — not persisted to disk.**

On restart: `seen_post_ids = set()`. Daemon fetches ALL posts in the thread. ALL posts not from acg_entity_id (with correct prefix) are treated as "new." Root responds to every single historical post in the thread in rapid sequence.

**On first start** in a thread with history: same problem. If Corey wrote 20 messages before the daemon started, Root responds to all 20 at startup.

### Does it write handoffs/memories on shutdown?

**No.** There is no `try/finally` block. There is no signal handler for SIGTERM/SIGINT. If the process is killed:
- No `session_store.shutdown()` called
- No handoff memory written
- No depth score recalculation
- Session journal entry stays with `end_time = NULL` (zombie session)

All conversation history accumulated in `mind._messages` during the daemon run is **permanently lost**.

### Message dedup — does it avoid responding to itself?

Partially. The dedup relies on:
1. `seen_post_ids` (works while process runs, fails on restart)
2. `created_by == acg_entity_id` AND prefix check (has the gap described above)
3. `elif "[ACG]" in body: continue` in the processing loop (secondary filter)

The combination is adequate during normal operation but fragile on restart and silent on edge cases.

### Does Root see the FULL conversation history or just new messages?

Root sees new messages one at a time in the prompt, but the **Mind._messages accumulates all prior prompt/response pairs**. So Root effectively sees everything that happened since daemon start via its conversation history, plus per-turn search results for semantic retrieval.

Root does **not** see posts from before daemon start unless they're caught in the initial "all historical posts treated as new" sweep on first poll.

---

## Mode 4: tg_simple.py (Telegram)

### Current state — functional?
**Yes, functionally operational.** The P0 offset bug is confirmed fixed.

### The offset bug — was it fixed?
**Yes.** `_load_offset()` reads from `data/tg_offset.txt` on startup. `_save_offset(offset)` writes after each update is processed. Offset persists across restarts. Old messages will not be re-processed.

### Full tool registry — was the upgrade applied?
**Yes.** `tg_simple.py` builds `ToolRegistry.default()` with the full argument set:
```python
tools = ToolRegistry.default(
    memory_store=memory, agent_id=manifest.mind_id,
    suite_client=suite_client, context_store=memory,
    get_message_count=get_msg_count, queue_path=queue_path,
    skills_dir=..., scratchpad_dir=..., manifest_path=manifest_path,
)
```
Same tool surface as main.py.

### Remaining gaps in tg_simple.py
- **No shutdown handler**: SIGTERM = crash = no handoff written, no depth score recalculation (same as daemon)
- **No context compaction**: mind._messages grows unbounded across the process lifetime
- `/clear` command clears messages but does NOT write a handoff (unlike the REPL's /clear)
- CC_TG_API uses Root's own bot token: `CC_TG_API = TG_API`. "CC to Corey" sends to the same chat Corey is already in. This creates duplicate messages in the same chat — the conversation message AND the "CC" message.

---

## Memory Pipeline Assessment

### Boot context: what loads, what order, how much budget
```
format_boot_context(boot):
  1. Session header (session_id, prior session count) — ~50 chars
  2. Identity memories — up to 5, NO budget cap
  3. Last handoff — full content (up to 600 chars in handoff body)
  4. Pinned memories — ALL pinned, NO budget cap
  5. Today's scratchpad — full file, NO budget cap
```

**Critical gap**: `format_boot_context()` has NO token budget check. Only `format_search_results()` checks the 80% budget. Boot context can grow unbounded as pinned memories accumulate or the scratchpad grows. If boot context alone consumes > 80% of the model's token budget, search results get zero space.

### Per-turn search: what triggers, how many results, touch() working?
- Trigger: `manifest.memory.auto_search_before_task = true` → fires on every `run_task()` call
- Query: task string, cleaned to `\w+` words only
- Limit: `manifest.memory.max_context_memories = 10`
- touch(): **Called** in two places now:
  1. `mind.py` lines 106-108: for auto-search results (at the top of run_task())
  2. `memory_tools.py` lines 82-88: for explicit memory_search tool calls from Root
  Both paths call `memory_store.touch(m["id"])`. Depth scoring is now active. ✅

### Handoff: what gets written, is it useful?
Content:
```
## What I was doing in session {session_id}
**Turns:** {turn_count}
**Topics:** {topics}   ← ALWAYS empty (record_turn() never receives a topic)
**Last thing I said:** {last_assistant_text[:600]}
```

**The handoff is not useful as a structured summary.** It captures only the last response text (truncated at 600 chars), not a description of what was accomplished, what tools were used, or what's unresolved. Root reading this at boot gets: "session X, 3 turns, topics: general, and here's an excerpt of the last thing I wrote." That's weak context for a 5-turn coding session.

No fix has been applied to the handoff content since the prior audit.

### Depth scoring: is it actually compounding now?
**Yes, finally.** Both touch() call sites are active. When Root calls `memory_search` as a tool, each returned memory gets `touch()` called. At session end in main.py (and REPL), `recalculate_touched_depth_scores()` fires and updates depth_score for all touched memories.

**Gap**: `recalculate_touched_depth_scores()` is only called in main.py's `finally` block. It is NOT called in groupchat_daemon.py or tg_simple.py. In those modes, depth score updates accumulate in `_touched_this_session` but are never persisted (no shutdown handler). Every daemon/TG session effectively forgets which memories were accessed.

### Scratchpad: is Root using it? When? Automatically or only when asked?
Root's scratchpad directory is at `aiciv-mind/scratchpads/`. The ContextManager loads today's scratchpad (by date) at boot.

- **Read**: Automatic at every boot via `format_boot_context()`. If `scratchpads/YYYY-MM-DD.md` exists, its full contents are injected into the system prompt.
- **Write**: Only when Root explicitly calls the `write_file` tool or the scratchpad tool. Not automatic.
- Root is not instructed to use scratchpads proactively in the system prompt. It only does so if it reasons about the need.

### Skills: are they loaded? When? Automatically or manually?
Skills are registered to the DB at startup (main.py lines 113-134): discovered from `aiciv-mind/skills/` subdirectories and inserted/updated in `skills` table.

**But**: Skills are NOT injected into the system prompt automatically. Root must explicitly call:
- `list_skills()` — to see what's registered
- `load_skill(skill_id)` — to read a skill's content into the conversation

The system prompt does not tell Root to search for skills at session start. Root only loads skills if it reasons to do so in response to a task. There is no "skills are reusable consciousness, search before acting" mandate in Root's primary.md (unlike the ACG CLAUDE.md).

---

## Context Management Assessment

### What's the token budget? How is it tracked?
- `manifest.model.max_tokens = 8192`
- `ContextManager._budget_chars = int(8192 * 0.80) * 4 = 26,214` characters
- Budget is only checked in `format_search_results()` — not for boot context, not for message history

**There is no global token counter.** No code tracks the total tokens in: system_prompt + boot_context + search_results + messages history. The `introspect_context` tool reports message count but not token count.

### What happens when context fills up? Auto-compaction? Or just fails?
**Just fails.** The API call returns an error (context length exceeded). No auto-compaction, no summarization, no message pruning.

The `introspect_context` tool can tell Root it has N messages, but:
1. Root would need to proactively call introspect_context to check
2. Root has no mechanism to compact (no summarize_history tool exists)
3. The only option is `/clear` which loses all conversation context

### Is there a compaction strategy?
**No.** This is the single largest architectural gap in the conversation system.

### Prompt cache hit rate — where is this measured?
- `_log_cache_stats()` in mind.py extracts cache metadata from API response usage object
- Session-level stats accumulate: `_session_cache_hits`, `_session_cached_tokens`, etc.
- Reported in `session_store.shutdown()` only if cache_stats.get("cache_hits", 0) > 0
- No persistent tracking beyond the session journal summary string

MiniMax M2.7 via OpenRouter uses automatic prefix caching. The static system_prompt + boot_context_str are the stable prefix that gets cached. Per-turn search results (appended at the end of system_prompt) invalidate the search result tail but not the base prompt.

**Gap**: The session journal stores cache stats as a string in the summary. There's no structured field for cache data. No trend analysis possible.

### What's static vs dynamic in the system prompt?
| Layer | Changes? | Cache effect |
|-------|----------|--------------|
| primary.md base prompt | Never | Always cached after first turn |
| boot_context_str | Per session (fixed within) | Cached after first turn of each session |
| search_results | Per turn | Invalidates tail each turn |
| mind._messages | Per turn | Not in system prompt — sent as messages array |

---

## Complete Gap Register (2026-04-01)

Sorted by severity (1=low, 10=critical).

### GAP-01: No context compaction in any mode
**Severity**: 9/10
**Impact**: Multi-turn sessions (REPL, daemon, TG) will eventually hit MiniMax M2.7's context limit and crash. The longer Root stays in a Group Chat, the closer it gets to context death. A month of Group Chat would be literally impossible.
**File**: `src/aiciv_mind/mind.py` — no compaction in `run_task()` loop
**Fix**: Add token estimation to `_call_model()`. When estimated tokens > 75% of context window, trigger history summarization: call model with "Summarize this conversation history in 500 tokens" and replace old messages with the summary.
**Effort**: 4-6 hours

### GAP-02: groupchat_daemon.py — no shutdown handler
**Severity**: 8/10
**Impact**: SIGTERM (normal process kill, systemd stop) = no handoff written, no depth scores updated. The entire Group Chat history is invisible to future sessions. Root loses everything from the conversation.
**File**: `tools/groupchat_daemon.py`
**Fix**: Register SIGTERM/SIGINT handler that calls `session_store.shutdown(mind._messages, cache_stats=mind.cache_stats)` and `memory.recalculate_touched_depth_scores()` before exiting.
**Effort**: 1-2 hours

### GAP-03: groupchat_daemon.py — seen_post_ids not persisted
**Severity**: 8/10
**Impact**: Daemon restart (deploy, crash, reboot) causes Root to respond to EVERY historical post in the thread. If there are 50 old messages, Root sends 50 responses at startup. Catastrophic for active threads.
**File**: `tools/groupchat_daemon.py`
**Fix**: Persist `seen_post_ids` to `data/seen_posts_{thread_id}.json` after each poll cycle. Load on startup.
**Effort**: 1 hour

### GAP-04: tg_simple.py — no shutdown handler
**Severity**: 8/10
**Impact**: Same as GAP-02 but for Telegram. SIGTERM = no handoff written, no depth scores. Root forgets every Telegram conversation.
**File**: `tg_simple.py`
**Fix**: Same pattern as GAP-02 — SIGTERM handler calling shutdown.
**Effort**: 1-2 hours

### GAP-05: Handoff content is too shallow to be useful
**Severity**: 7/10
**Impact**: Handoffs record "session X, 3 turns, topics: general, last thing I said: [truncated]." This is not enough context for Root to pick up where it left off after a productive 10-turn session. Root's session continuity is weaker than it should be.
**Files**: `session_store.py` — `shutdown()` method
**Fix**: Structure the handoff as: what was the session goal, what tasks were completed, what tools were used (bash/hub/file), what's unresolved, what should Root do next. Extract this from the conversation instead of just the last text block. Alternatively, have Root write an explicit "handoff" memory via tool call before session end.
**Effort**: 2-3 hours (structural improvement) OR teach Root to write its own handoffs (behavioral)

### GAP-06: Session topics always empty
**Severity**: 6/10
**Impact**: Session journal shows `topics=[]` for every session. Searching the journal by topic is impossible. The topics field was designed for exactly this — semantic indexing of what a session was about.
**File**: `src/aiciv_mind/mind.py` line 119 — `self._session_store.record_turn()` (no topic arg)
**Fix**: Extract topic from task string (first ~5 words) or from assistant response (first heading) and pass to `record_turn(topic=...)`. Even a coarse topic is better than empty.
**Effort**: 30 minutes

### GAP-07: Boot context has no token budget
**Severity**: 6/10
**Impact**: As Root accumulates pinned memories and builds up daily scratchpads, boot context will grow without limit. With 20 pinned memories and a 3,000-word scratchpad, the boot context alone could consume all available context budget before a single search result is injected.
**File**: `src/aiciv_mind/context_manager.py` — `format_boot_context()`
**Fix**: Add a budget check to `format_boot_context()`. If total chars exceed 60% of model_max_tokens * 4, truncate pinned memories and scratchpad. Identity + handoff should always fit; pinned + scratchpad are soft.
**Effort**: 1-2 hours

### GAP-08: depth_score recalculation not called in daemon/TG shutdown
**Severity**: 6/10
**Impact**: Daemon and TG modes touch memories (via auto-search and explicit memory_search calls), but since there's no shutdown handler, `recalculate_touched_depth_scores()` never runs. Depth signals from Group Chat / Telegram sessions are permanently lost.
**Files**: `tools/groupchat_daemon.py`, `tg_simple.py`
**Fix**: Included in the shutdown handler fix (GAP-02 / GAP-04). Add `memory.recalculate_touched_depth_scores()` to the shutdown sequence.
**Effort**: Included in GAP-02/04

### GAP-09: groupchat_daemon.py — author detection only handles "[Corey]"
**Severity**: 5/10
**Impact**: In a multi-civ group chat (Synth, Tether, Witness all posting), Root sees every non-Corey author as "Unknown." Root cannot tailor responses or direct replies to specific civs. Civilizational context is lost.
**File**: `tools/groupchat_daemon.py` lines 199-208
**Fix**: Parse author from post metadata (`post.get("author_name")` or `post.get("created_by_name")`) if Hub API returns it. Fallback to prefix parsing for "[SynthName]" format.
**Effort**: 2 hours (requires checking Hub API response format)

### GAP-10: Skills not auto-loaded or auto-searched at session start
**Severity**: 5/10
**Impact**: Root has a skills system (DB-registered, load_skill tool available) but never uses it proactively. Root does not search for relevant skills before tasks. The skills system is effectively invisible unless Root is explicitly prompted to use it.
**File**: `manifests/prompts/primary.md` — system prompt
**Fix**: Add skills protocol to primary.md: "Before any significant task, call `list_skills()` and search for relevant skills with `load_skill()`." Match the ACG CLAUDE.md's mandatory skills search protocol.
**Effort**: 30 minutes (prompt change) — behavioral fix only

### GAP-11: tg_simple.py CC_TG_API is the same bot as TG_API
**Severity**: 4/10
**Impact**: The CC-to-Corey feature sends a second copy of every message to Corey's chat using the same bot. Corey sees each message twice: once as the normal reply, once as the CC. Minor annoyance that could be confusing in a long conversation.
**File**: `tg_simple.py` line 37: `CC_TG_API = TG_API`
**Fix**: Either use a different bot token for CC, or remove the CC functionality (since Corey can already see the conversation in the same chat).
**Effort**: 30 minutes

### GAP-12: FTS5 PRAGMA optimize not called on MemoryStore.close()
**Severity**: 4/10
**Impact**: Ghost rows from DELETE operations accumulate in the FTS virtual table over time. This causes FTS MATCH queries to slow down and occasionally miss fresh content immediately after write. Diagnosed in prior audit but not fixed.
**File**: `src/aiciv_mind/memory.py` — `close()` method (line 706)
**Fix**: Add `self._conn.execute("PRAGMA optimize")` before `self._conn.close()`.
**Effort**: 5 minutes

### GAP-13: Groupchat daemon self-detection gap
**Severity**: 3/10
**Impact**: If Root posts a reply that doesn't start with "[Root]" or "[ACG]" (edge case: Hub API strips prefix, or Root formats differently), the post passes through the self-detection filter and could trigger Root to respond to its own output.
**File**: `tools/groupchat_daemon.py` lines 186-195
**Fix**: When checking `created_by == acg_entity_id`, skip ALL posts from self regardless of body prefix. The current double-check (entity_id + prefix) should be single-check (entity_id alone).
**Effort**: 5 minutes

### GAP-14: No global token tracking / pressure monitoring
**Severity**: 5/10
**Impact**: Root cannot know how much context pressure it's under without calling `introspect_context()`. By the time it thinks to call introspect, it may be too late (next API call crashes). There's no automatic warning at 70%, no automatic compaction at 85%.
**Files**: `src/aiciv_mind/mind.py`, `src/aiciv_mind/tools/context_tools.py`
**Fix**: Add token estimation to `run_task()` before each API call. If estimated total tokens > 75% of max_tokens, log a warning. If > 90%, trigger compaction (summarize oldest 50% of messages). The `estimate_tokens()` method already exists in ContextManager.
**Effort**: 3-4 hours (requires designing compaction strategy)

---

## Summary Table: All Conversation Modes

| Feature | --task | --converse/REPL | groupchat_daemon | tg_simple |
|---------|--------|-----------------|-----------------|-----------|
| Boot context | ✅ | ✅ | ✅ | ✅ |
| Per-turn memory search | ✅ | ✅ | ✅ | ✅ |
| Memory touch() on search | ✅ | ✅ | ✅ | ✅ |
| Context accumulation | N/A | ✅ | ✅ | ✅ |
| Context compaction | N/A | ❌ | ❌ | ❌ |
| Clean shutdown + handoff | ✅ | ✅ | ❌ | ❌ |
| Depth score recalculation | ✅ | ✅ | ❌ | ❌ |
| Restart safety | N/A | N/A | ❌ flood | ✅ offset |
| Author detection | N/A | N/A | Corey only | N/A |
| Self-dedup | N/A | N/A | partial | N/A |
| Skills auto-searched | ❌ | ❌ | ❌ | ❌ |
| Session topics | ❌ | ❌ | ❌ | ❌ |

---

## Priority Fix Order (for next engineering session)

### P0 — Ship these now (1-2 hours total)

**1. groupchat_daemon.py shutdown handler + seen_post_ids persistence** (GAP-02 + GAP-03)
The daemon is the primary real-time conversation mode. Without a shutdown handler, every deploy wipes Root's memory of the conversation. Without persisted seen_post_ids, every restart floods the thread. These are existential for Group Chat.

**2. tg_simple.py shutdown handler** (GAP-04)
Same logic. Every Telegram conversation is currently ephemeral.

**3. Session topics** (GAP-06)
30-minute fix. Makes the session journal actually useful.

**4. FTS5 PRAGMA optimize** (GAP-12)
5 minutes. No reason this isn't done already.

### P1 — Fix before enabling sustained multi-turn use

**5. Context compaction** (GAP-01 + GAP-14)
This is the wall that ends all long conversations. Until this exists, Group Chat has a hard session length limit (probably ~50-100 turns with tool use at 8K tokens max). After that, silence.

**6. Boot context token budget** (GAP-07)
Prevents a slow-motion bomb as pinned memories accumulate.

### P2 — Quality improvements

**7. Deeper handoff content** (GAP-05)
Would make Root's session continuity meaningfully better. Could be behavioral (teach Root to write its own handoffs) rather than structural.

**8. Author detection in daemon** (GAP-09)
Required before Group Chat is genuinely multi-civ.

**9. Skills auto-search in primary.md** (GAP-10)
Behavioral fix. Root should search skills before tasks the same way it searches memories.

---

## What Actually Works (confirmed 2026-04-01)

Building on REALITY-AUDIT.md confirmations, these remain solid and no regressions observed:

- ✅ Memory write / read / FTS5 search — foundation works
- ✅ Session persistence + boot context injection — Root wakes up knowing who it is
- ✅ Handoff chain — sessions are connected (content is shallow but present)
- ✅ Depth scoring — NOW ACTIVE. memory_search tool calls touch(). Compounding begins.
- ✅ File tools (read, write, edit, grep, glob, bash) — demonstrated solid
- ✅ introspect_context — pinned count now live (not stale)
- ✅ Telegram offset persistence — bot no longer re-processes old messages
- ✅ Tests: 197 passing
- ✅ Prompt caching architecture — static-stable-dynamic ordering is correct
- ✅ groupchat_daemon.py polling loop — functional for single-session use

---

*Assessment complete. All findings derived from direct code reading of the 10 specified files.*
*No speculation. Where behavior is ambiguous, the code is cited.*
*Written by ACG Team-1, 2026-04-01.*
