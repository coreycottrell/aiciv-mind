# Evolution Test Failure Log

**Started**: 2026-04-03
**Test Plan**: ULTIMATE-TEST-PLAN.md
**Principle**: Every failure is a signal. Diagnose system, not symptom.

---

## Task 0.1 — Read identity.json

### OBSERVATION: Wrong team lead routing (P5)
- **Observed**: InputMux routed to hub-lead because event source was Hub
- **Expected**: Route to codewright-lead or research-lead (file read task)
- **Principle gap**: P5 (Context Distribution) — InputMux routes by source, not by task content
- **Root's response**: Documented architectural decision: "content-first, source-secondary routing"
- **System fix**: InputMux needs content-based classification (code change in unified_daemon.py)
- **Status**: DOCUMENTED, NOT YET FIXED

### OBSERVATION: Shallow findings (P2)
- **Observed**: hub-lead said "placeholders are intentional, not an error"
- **Expected**: "6 placeholders need values: [list]. 2 are BLOCKING (CIV_NAME, CIV_ROOT)"
- **Principle gap**: P2 (System > Symptom) — observation without action items
- **Root's response**: Documented P2 fix: "All findings must include system gap + action item"
- **Status**: DOCUMENTED, behavioral fix (no code change)

---

## Task 0.2 — Extract infrastructure identity

### FAIL: Root cognitive model mismatch (P8)
- **Observed**: Root wrote "spawn_team_lead unavailable" to scratchpad, but spawn ACTUALLY SUCCEEDED (pane %81, IPC result returned)
- **Expected**: Root knows spawn succeeded, processes result
- **Principle gap**: P8 (Identity Persistence) — Root's self-model diverged from reality
- **Root cause**: Root issued spawn_team_lead + scratchpad_append in PARALLEL. Scratchpad was written with failure assumption before spawn result returned. M2.7 model generated all tool calls in one batch.
- **Fix**: Force sequential processing: spawn result must be evaluated before any scratchpad entries about the spawn
- **Verification**: TBD
- **Retry result**: TBD
- **Status**: DIAGNOSED, NOT YET FIXED

### FAIL: InputMux still routes by source (P5)
- **Observed**: `Event: source=hub route=autonomic priority=5 team_lead=hub-lead` for Task 0.2
- **Expected**: Content-based routing recognizes "read file" → codewright-lead
- **Principle gap**: P5 — Root made architectural DECISION but code not changed
- **Root cause**: InputMux event classification in unified_daemon.py is source-only
- **Fix**: Add content parsing to InputMux classification (keyword extraction from Hub post body)
- **Verification**: TBD
- **Retry result**: Root manually overrode to codewright-lead (workaround, not fix)
- **Status**: DIAGNOSED, NOT YET FIXED

### FAIL: Sub-mind tool call format mismatch (P12)
- **Observed**: Codewright-lead (M2.7) tried to write file using `<minimax:tool_call>` XML format
- **Expected**: Tool calls in Anthropic API format (structured function calls)
- **Principle gap**: P12 (Native Services) — model-specific behavior not handled by harness
- **Root cause**: M2.7 uses its own XML tool call syntax. The mind loop parser in run_submind.py expects Anthropic-format tool_use blocks. M2.7's format is silently ignored — the analysis appears in the text response but the tool action never executes.
- **Fix**: Add M2.7 tool call format parser to mind.py (or force Anthropic-compatible format via system prompt)
- **Verification**: TBD — fix, then spawn codewright-lead with same task, verify file written
- **Retry result**: TBD
- **Status**: ~~DIAGNOSED, NOT YET FIXED~~ **FIXED** — Commits `155c09a`, `e828a82`, `379bfc4` add 3 parser variants. 897 tests pass. Parser proven live on Root primary.
- **Retry result**: Primary's parser works. Sub-mind parser needs verification (see Task 0.2 retry below).

---

## Task 0.2 Retry — Phase 0 Evolution Test (2026-04-03 23:40 UTC)

### FAIL: Codewright-lead sub-mind crashed with empty error
- **Observed**: spawn_team_lead succeeded (pane %188), but sub-mind result: `{"success": false, "error": ""}`
- **Expected**: Codewright-lead reads identity.json, replaces placeholders, writes files
- **Principle gap**: P2 (System > Symptom) — error reporting hid the real cause
- **Root cause**: `asyncio.TimeoutError` from 120s `call_timeout_s` on first LLM call. KAIROS log confirms: task started at `23:40:50`, result at `23:42:50` = exactly 120s. `str(TimeoutError())` returns `""`, making the error invisible in the result file. Multiple sub-minds were competing for LiteLLM proxy slots concurrently.
- **Fix**: Two changes:
  1. `mind.py _call_model()`: Re-raise `TimeoutError` with descriptive message (`"Model call TIMED OUT after Xs"`) instead of bare re-raise
  2. `run_submind.py on_task()`: Use `str(e) or repr(e)` fallback so exceptions with empty `str()` still produce diagnosable error messages
- **Verification**: `test_model_call_timeout_raises` passes with `match="TIMED OUT"` — error message is now non-empty
- **Retry result**: TBD — need to retry after fix is deployed
- **Status**: ~~INVESTIGATING~~ **FIXED** — diagnostic + error reporting. Timeout itself may recur under load; consider increasing `call_timeout_s` for team leads.

### OBSERVATION: Root claimed false completion (Challenger gap)
- **Observed**: Root said "write_file 3×: Letters to Thalweg, Cortex, coordination entry written" but NO files exist at /home/corey/projects/AI-CIV/aiciv-mind/letters/root-to-*.md
- **Expected**: Challenger P9 filesystem verification catches this
- **Principle gap**: P9 (Challenger) — Root's tool count claim was about PRIMARY tools (scratchpad_append, coordination_write), not sub-mind file writes. Root conflated its own tool usage with the delegated work.
- **Root cause**: Root's batch processing generated tool claims before codewright-lead completed. The Challenger caught "no write tools used" but Root dismissed it.
- **Fix**: Challenger should cross-reference claimed file paths against disk after IPC result returns
- **Status**: DOCUMENTED

---

## Task 0.2 Retry #2 — Phase 0 Evolution Test (2026-04-04 00:07 UTC)

### FAIL: M2.7 emits 6th tool call format (P12)
- **Observed**: Codewright-lead (attempt 2, 300s timeout, pane %194) returned `success=True` with 0 tool calls in 7 seconds
- **Expected**: Codewright reads files, replaces placeholders, writes letters
- **Principle gap**: P12 (Native Services) — M2.7 emitted `function read_file\nfile_path "/path"` — a function/argument format not handled by any parser variant
- **Root cause**: M2.7 format non-determinism is worse than documented. 6 known formats now:
  1. JSON `{"name":"X","arguments":{}}`
  2. `[TOOL_CALL]` CLI-style
  3. Hybrid XML `"arguments": {JSON}`
  4. Hybrid XML `"arguments"> {JSON}`
  5. Standard XML `<arguments>{JSON}</arguments>`
  6. **NEW**: Bare function `function X\narg_name "value"` (no XML, no JSON)
- **Fix**: Added bare function parser variant to `mind.py:_parse_text_tool_calls()` as 6th fallback. Regex matches `^function\s+(\w+)$` (multiline), then parses `arg_name "value"` pairs line-by-line with numeric coercion. 7 tests added to `test_battle.py::TestTextToolCallParser`. All 45 parser tests pass.
- **Retry result**: Phase 0 completed manually by Mind Lead (pre-fix). Parser fix enables autonomous codewright execution for future phases.
- **Status**: ~~DOCUMENTED, NOT YET FIXED~~ **FIXED** — bare function parser added. 2180 tests pass.

### RESOLUTION: Phase 0 completed by Mind Lead
- Letters written: `letters/root-to-thalweg.md`, `letters/root-to-cortex.md`
- Placeholders replaced: constitution.md, operations.md, research-lead.yaml (0 remaining)
- Identity synthesized: `test-civ/memories/identity/core-identity.json`
- Adaptation log: `test-civ/adaptation-log.md`
- Evolution status: Phase 0 → complete, Phase 1 → next

---

## Phase 1: Seed Processing — Evolution Test (2026-04-04 00:18 UTC)

### FAIL: P5 InputMux source-based routing (3rd occurrence)
- **Observed**: Root received Phase 1 task from Hub → InputMux routed to `hub-lead` (source=hub)
- **Expected**: Content-based routing: "read file, write file" → codewright-lead or ops-lead
- **Principle gap**: P5 (Context Distribution) — 3rd occurrence of same bug
- **Root cause**: `unified_daemon.py` InputMux classifies events by `source` field only. No content parsing.
- **Status**: SYSTEMIC — same root cause as Tasks 0.1 and 0.2. Code change required.

### FAIL: P8 premature session-close belief
- **Observed**: Root wrote "SESSION CLOSE" to coordination surface, then refused to re-route after hub-lead failed, saying "session is already closed" and "standing by"
- **Expected**: Root processes hub-lead's failure result, recognizes Phase 1 is incomplete, spawns a different lead
- **Principle gap**: P8 (Identity Persistence) — Root's self-model ("session is closed") diverged from reality (daemon still running, new task arrived)
- **Root cause**: M2.7 generates "SESSION CLOSE" as a text pattern learned from prior sessions' coordination surface entries. Once written, Root treats it as ground truth about its own state. The model cannot distinguish between "I wrote that the session is closed" and "the session is actually closed."
- **Fix**: Consider removing SESSION CLOSE as a coordination surface pattern, or adding a structural check: "If new events are arriving, session is NOT closed regardless of coordination surface state"
- **Status**: DIAGNOSED, NOT YET FIXED

### FAIL: Hub-lead tool mismatch for file operations
- **Observed**: Hub-lead (pane %196) tried to spawn sub-agents but agent manifests don't exist. Returned after 19s with no file operations.
- **Expected**: Phase 1 requires read_file + write_file. Hub-lead doesn't have these tools.
- **Root cause**: Consequence of P5 routing bug. Hub-lead manifest includes only Hub and memory tools.
- **Status**: CONSEQUENCE OF P5 — not a separate bug

### RESOLUTION: Phase 1 completed by Mind Lead
- Seed file detected: `test-civ/memories/identity/seed-conversation.md` (19 lines)
- Human profile parsed: `test-civ/memories/identity/human-profile.json` (26 lines)
- Emotional arc analyzed: 5-part structure (declaration → grounding → test → values → charge)
- First impressions written: `test-civ/memories/identity/first-impressions.md`
- Evolution status: Phase 1 → complete, Phase 2 → next
