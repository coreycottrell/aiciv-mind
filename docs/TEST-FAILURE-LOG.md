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
- **Status**: DIAGNOSED, NOT YET FIXED — **HIGHEST PRIORITY** (blocks ALL sub-mind file writes)
