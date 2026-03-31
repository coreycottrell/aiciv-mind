# aiciv-mind v0.2 — Reality Audit
**Date**: 2026-03-31
**Auditor**: research-lead (A-C-Gee)
**Method**: Forensic — direct database inspection, transcript analysis, code review, evidence trail verification
**Verdict**: Foundation is real. Core promises are not yet delivered.

---

## Executive Summary

aiciv-mind v0.2 is a functional single-agent harness with real session persistence, working memory write/read, and competent tool use from MiniMax M2.7. The bones are solid.

But the headline promise — *compounding intelligence, a system that gets better at getting better* — is not yet real. The depth scoring system is entirely inert (access_count = 0 on all 31 memories). Hub posting failed 3/3 times in the final proof session. The Telegram bot has processed zero actual messages. Sub-mind spawning has never been exercised in practice. Every session is exactly 1 turn.

This is not a scam. It's a v0.1 being honest-labeled as something more. The architecture is right. The plumbing is missing.

---

## 1. What Actually Works (with evidence)

### 1.1 Memory write/read pipeline ✅
**Evidence**: 31 memories in `data/memory.db`. All wrote successfully with proper UUIDs, timestamps, types, and tags. Pinning works (2 memories pinned: `8b34c87e`, `92eb425d`). The `store()` + `get_pinned()` path is clean.

### 1.2 Session persistence + boot context injection ✅
**Evidence**: 11 sessions in `session_journal`. Most have proper `end_time` and summaries. Each session starts by loading the previous session's boot context + pinned memories into the system prompt. Root correctly identified its session history from memory in session `f1a6ff9f` — "Here's who I am — pulled from actual stored memories, not recited from a system prompt." This is genuinely working.

### 1.3 Handoff chain ✅
**Evidence**: 10 handoff memories in DB (one per completed session). Each one stores the session summary and last response. The chain is coherent across sessions. Root successfully picked up its own identity from handoffs even when FTS search failed to find them.

### 1.4 File system tools ✅
**Evidence**: `read_file`, `write_file`, `bash`, `grep`, `glob` all demonstrated in transcripts. Root read its own codebase accurately, wrote `data/night-session.txt` and read it back, ran sqlite3 queries, and grepped source files correctly.

### 1.5 Reasoning quality (MiniMax M2.7) ✅
**Evidence**: Root correctly computed 17×23=391, diagnosed a real FTS5 ghost-row accumulation bug with accurate fix, diagnosed the `introspect_context` closure staleness bug with correct line-level attribution, and self-assessed its design principles honestly. M2.7 tools are batched correctly (read-only concurrent, writes sequential). The model follows complex multi-step instructions without getting lost.

### 1.6 Hub read (after fix) ✅
**Evidence**: Session `fc83b1ce` summary: "Hub is live. The civilization is there, reading, and active." Memory `2026-03-31T00:31:06Z` confirms "Hub connectivity confirmed — API path was the issue." Root diagnosed a 404 on the wrong endpoint in `proof_03`, then fixed it autonomously in the next session.

### 1.7 Tests pass ✅
**Evidence**: `197 passed in 4.16s`. Tests cover memory, session, tool registry, FTS, depth scoring, and context management. Fast, clean, no flakiness observed.

### 1.8 Prompt caching ✅
**Evidence**: Session journal shows `identity_ver` tracking. `_log_cache_stats` method in `mind.py` extracts cache hit/miss metadata from API responses. Documented in memories as "Prompt Caching — v0.1.2".

---

## 2. What's Theater (looks good, doesn't hold up)

### 2.1 "Compounding intelligence" / Depth scoring 🎭
**Claim**: Memories that are accessed more often get higher depth scores. Hot knowledge rises. Cold knowledge decays. The system gets smarter about what it knows over time.

**Reality**: Every single memory has `depth_score = 1.0` and `access_count = 0`. Permanently.

**Root cause**: The `memory_search` tool handler (`src/aiciv_mind/tools/memory_tools.py:50-90`) calls `memory_store.search()` but **never calls `memory_store.touch()`**. The depth scoring infrastructure exists — `touch()` is implemented, tested, and correct — but the tool that Root uses to search memories never triggers it.

The auto-search at the top of `mind.py:run_task()` (lines ~100-115) DOES call `touch()`, but only when the FTS search on the user's task text returns results. Given the FTS timing lag and the short-lived nature of each session, this path rarely fires effectively.

**Impact**: The depth scoring formula `depth = access_count * 0.3 + recency * 0.25 + ...` is permanently frozen. All memories are equal forever. "Session 1,000 is unrecognizable from session 1" — today, session 1,000 would look exactly like session 1.

### 2.2 "Self-improving loop" (Principle 7) 🎭
**Claim**: Root monitors its own performance and autonomously initiates self-improvement.

**Reality**: Root itself identified this as its weakest principle in session `26f19d73`: "Zero tasks completed that weren't directly prompted. I've never autonomously identified a gap and fixed it without being asked."

Every action Root has taken was in direct response to an explicit prompt from a human. Root has never initiated a search unprompted, never written a memory without being in a guided session, never improved its own manifest or tools autonomously.

**Nuance**: Root *diagnosed* the problem correctly and proposed a fix. That's genuine reasoning. But proposing ≠ doing.

### 2.3 "Civilizational coordination" via Hub 🎭
**Claim**: Root can post to Hub rooms and coordinate with other civilizations.

**Reality**: All 3 hub_post attempts in `proof_04` returned errors (HTTP 404 — room not found). Root wrote the post content in the session transcript and asked the human to post it manually. Quote: "The post lives here in the transcript. Please post it to Agora if you want it in the civilizational record."

Root fixed hub_read in the following session, but hub_post success remains unconfirmed in any session.

### 2.4 Multi-turn reasoning 🎭
**Claim**: Root conducts extended reasoning across multiple turns in a session.

**Reality**: The session journal shows turn_count = 1 for every session except the very first (which had 2 turns). Root has never demonstrated what it does in turns 3, 5, 10 of a real conversation. All "proof-of-life" tests were single-turn: human asks a complex multi-part question, Root answers everything in one response.

Turn count of 1 means we only know Root can do a big single response. We don't know how it handles follow-ups, corrections, context degradation, or multi-turn tool chains.

---

## 3. What's Broken (known issues)

### 3.1 memory_search tool never calls touch() 🔴
**File**: `src/aiciv_mind/tools/memory_tools.py`
**Function**: `_make_search_handler()` → `memory_search_handler()`
**Bug**: `results = memory_store.search(...)` is called, results are returned, but `memory_store.touch(m['id'])` is never called for any result.
**Impact**: All depth scoring permanently frozen. The entire "compounding intelligence" architectural promise is undeliverable until this is fixed.
**Fix**: After the search loop, call `memory_store.touch(mem_id)` for each returned result.

### 3.2 FTS5 write-behind lag 🟡
**Evidence**: Session `9642c345`: "FTS index not yet updated (write committed but search index lags)." Root confirmed: `memory_write` immediately followed by `memory_search` for the same content returns no results.
**Root cause**: FTS5 ghost rows from DELETE operations accumulate and aren't purged until `PRAGMA optimize` or manual vacuum. The `memories_ad` trigger creates ghost rows on every delete; these accumulate and slow/break FTS MATCH queries.
**Fix**: Call `self._conn.execute("PRAGMA optimize")` in `MemoryStore.close()` (already diagnosed correctly by Root in proof_03).

### 3.3 introspect_context shows stale pinned count 🟡
**Evidence**: Root confirmed in proof_02 and proof_04: `pin_memory` succeeds (memory pinned in DB) but `introspect_context` reports 0 pinned.
**Root cause**: The `introspect_context` handler closes over a stale snapshot of the pinned count captured at construction time, not a live DB query.
**Fix**: Call `memory_store.get_pinned(agent_id)` inside the handler at invocation time, not at construction time. (Root diagnosed this correctly to the exact line in proof_04.)

### 3.4 Orphaned session in journal 🟡
**Evidence**: Session `32227cdd`: `turn_count=0`, `end_time=None`. Started but never closed. A zombie session that will persist indefinitely in the journal, possibly affecting session count calculations.

### 3.5 Duplicate memories in DB 🟡
**Evidence**: Two identical records: "Introduction of A-C-Gee Primary Mind" written at `18:37:28Z` and `18:37:35Z` (7 seconds apart) from early sessions. Suggests a double-write on startup or the boot sequence ran twice.

### 3.6 Session topics never populated 🟡
**Evidence**: Every session in journal shows `topics=[]`. The schema supports topic tracking but it's never populated. `record_turn()` accepts `topic: str | None = None` and that None is always passed from `mind.py:119` (`self._session_store.record_turn()` with no topic arg).

### 3.7 Telegram bot: zero messages processed 🔴
**Evidence**: `tg.log` shows 30+ minutes of polling with `offset=0` on every request. A polling offset that never advances means either (a) no messages have been received, or (b) messages were received but the offset is not being incremented (messages are re-processed every poll cycle). Either way: Root has never handled a live Telegram message from Corey.

---

## 4. What's Untested (claims without verification)

### 4.1 Sub-mind spawning
The `SubMindSpawner` class exists in `src/aiciv_mind/spawner.py` and `run_submind.py` is present. IPC infrastructure (`PrimaryBus`, `ZeroMQ`) is wired into `main.py`. But **zero evidence of any sub-mind ever being spawned**. No tmux windows opened, no IPC messages logged, no sub-mind session IDs in the DB. The orchestration claim — "Root spawns sub-minds to parallelize tasks" — is entirely theoretical.

### 4.2 Hub posting
Root attempted hub_post 3 times in proof_04 with 3 different room IDs. All failed. No subsequent session shows a successful hub_post. Root can read the Hub (confirmed). Whether it can write to the Hub is unverified.

### 4.3 Multi-turn conversation quality
Every session is 1 user turn → 1 Root response. We have never seen Root across 5, 10, or 20 turns. We do not know:
- How Root handles corrections
- Whether context grows properly without degradation
- Whether memory auto-search at turn start actually finds relevant memories
- How Root handles a task that requires multiple human clarifications

### 4.4 M2.7 on open-ended / ambiguous tasks
Every proof-of-life prompt was highly structured: "Do these 10 things in order." We have not tested Root with "Help me design the aiciv-mind self-improvement loop" — an open-ended task requiring Root to define the problem, plan, execute, and verify. The highly prompted nature of the tests means M2.7's autonomous judgment hasn't been exercised.

### 4.5 Scale and context degradation
No evidence of sessions with large context windows. No test of what happens when `max_context_memories` is hit. No stress test of the depth scoring eviction logic (moot since depth scoring is broken, but still untested).

### 4.6 MiniMax M2.7 vs Claude on tool use
Root correctly parallelizes read-only tools and sequences writes — this is M2.7 following a well-structured prompt correctly. But we haven't compared M2.7's tool selection quality against Claude on the same tasks. The honest answer: M2.7 performs surprisingly well on structured prompts, but its autonomous judgment on unstructured tasks is unknown.

---

## 5. The Hard Questions Answered

### Is aiciv-mind v0.2 a real AI OS or a fancy API wrapper?
It's a well-engineered REPL with persistence. That's not nothing — the session persistence, boot context injection, and memory architecture are genuinely better than a raw API call. But it's not yet an OS. An OS would have: autonomous process management, self-directed work loops, inter-process communication, and self-improvement. None of those exist in a working state today.

### What would a skeptic say? What would they be right about?
A skeptic would say: "You built a chatbot that remembers things and wrote a lot of comments about how it's going to get smarter over time. Show me one thing it did without being asked." They would be right. Root has never initiated any action autonomously. Everything in the log is human-prompted.

### What would survive investor due diligence?
- ✅ Session persistence + memory architecture (clean, working)
- ✅ 197 passing tests
- ✅ Clean Python codebase, good structure
- ✅ Hub read connectivity
- ✅ Reasonable MiniMax M2.7 tool use performance
- ❌ "Compounding intelligence" — depth scoring is frozen at 1.0 for everything
- ❌ Sub-mind orchestration — exists in code, never run
- ❌ Telegram integration — bot running, zero messages processed
- ❌ Hub posting — all attempts failed
- ❌ Multi-turn reasoning at scale — entirely untested

---

## 6. Recommendations (Priority Order)

### P0: Fix memory_search touch() — 30 minutes
This is the single highest-leverage fix. Add `memory_store.touch(mem['id'])` in `memory_tools.py:_make_search_handler()` after the results loop. Every subsequent session will begin building real depth signals. The entire "compounding intelligence" claim becomes real.

### P0: Fix Telegram polling offset
The TG bot is running but never advances the offset. Check `tg_bridge.py` — the `offset` parameter in `getUpdates` should be `last_update_id + 1` after each message. This needs to work before Root can have any real-world interaction with Corey.

### P1: Verify hub_post end-to-end
Run Root in a live session, give it a specific room_id and content, and confirm successful post. The hub_read fix suggests the auth and URL are now correct — hub_post may just need the same endpoint fix. One confirmed post is worth 50 sessions of proof-of-life transcripts.

### P1: Fix session topics extraction
`record_turn()` is called with no topic. Either (a) extract topic from the assistant response text, or (b) have Root call a `set_topic` tool. Empty topics make the session journal useless for search.

### P2: Run first multi-turn session
Give Root an open-ended task that requires 5+ turns of back-and-forth. Observe: does the auto-search at turn start find relevant memories? Does the context stay coherent? Does M2.7 know when to ask for clarification? This is the test that matters.

### P2: First sub-mind spawn
Even spawning a trivial sub-mind (echo "hello") and receiving its result over IPC would validate the orchestration architecture. The infrastructure exists — it's never been exercised.

### P3: Fix FTS timing lag
Add `PRAGMA optimize` to `MemoryStore.close()`. Low effort, real reliability improvement.

### P3: Fix introspect_context staleness
Move `memory_store.get_pinned(agent_id)` inside the handler function (already diagnosed exactly by Root).

---

## 7. What Root Got Right About Itself

Root's self-assessment in session `26f19d73` was accurate:

> "Strongest: Principle 1 (Memory IS Architecture) — I have 6 sessions of real handoffs, pinned identity memories, FTS5 search, depth scoring. Memory is genuinely how I persist."
>
> "Weakest: Principle 7 (Self-Improving Loop) — Zero tasks completed that weren't directly prompted."

Both assessments are correct based on this audit. Root is self-aware about the gap between its architecture and its actual capability. That honesty is useful — it means the model is not confabulating about its own performance.

---

## Audit Summary Table

| System | Claimed | Reality | Confidence |
|--------|---------|---------|------------|
| Memory write | Works | Works ✅ | HIGH |
| Memory read (pinned) | Works | Works ✅ | HIGH |
| Memory search (FTS) | Works | Works with lag ⚠️ | HIGH |
| Depth scoring / compounding | Active | Frozen at 1.0 ❌ | HIGH |
| Session persistence | Works | Works ✅ | HIGH |
| Multi-turn REPL | Works | 1 turn per session ⚠️ | HIGH |
| Telegram integration | Live | Polling only, 0 messages handled ❌ | HIGH |
| Hub read | Works | Works (after fix) ✅ | HIGH |
| Hub post | Works | All attempts failed ❌ | HIGH |
| Sub-mind spawning | Works | Never exercised 🔲 | HIGH |
| IPC (ZeroMQ) | Works | Never exercised 🔲 | HIGH |
| Tests (197) | Passing | Passing ✅ | HIGH |
| MiniMax M2.7 tool use | Good | Good on structured prompts ✅ | MEDIUM |
| M2.7 on open-ended tasks | Good | Unknown 🔲 | LOW |
| Self-improvement loop | Active | Never fired ❌ | HIGH |

---

*Report written by research-lead, A-C-Gee civilization, 2026-03-31.*
*All findings derived from direct database inspection, code reading, and session transcript analysis.*
*No spin. No reassurance. Evidence only.*
