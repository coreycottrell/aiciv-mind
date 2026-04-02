# SPEC: `handoff_audit` Tool

## Status
- **Phase:** Design + Implementation
- **File:** `src/aiciv_mind/tools/handoff_audit_tools.py` (new)
- **Module registration:** Added to `ToolRegistry.default()` in `__init__.py`

---

## Purpose

**Problem:** Handoffs are written by a Root who *believes* things that may no longer be true. The belief is real at the time of writing. The failure mode is that handoffs are treated as fact rather than as *claims* that need verification.

**Specific failure modes:**

1. **Stale state claims** — "Loop 1 is broken" when Loop 1 was fixed 4 commits ago. The handoff writer didn't pull.
2. **Tool existence assumptions** — "X tool doesn't exist" when X was added last week. Never confirmed.
3. **Temporal drift** — A handoff references events from 2pm without checking if subsequent commits changed anything.
4. **No contradiction detection** — Session N wrote "X works", session N+1 wrote "X is broken". No one flagged the disagreement.
5. **No provenance** — Handoffs don't cross-reference git history against their claims.
6. **Incomplete handoff, next session already started** — The handoff was written but the session didn't end cleanly. A new session is running and using an incomplete or stale handoff. Nobody checked.

**The fix:** `handoff_audit` runs automated checks against the current state of reality and flags claims in the handoff that contradict it. It is the mirror of `handoff_context`: that tool generates rich context *for* a handoff; this tool verifies a written handoff *after* it's written.

---

## Architecture

### Module placement
New file: `src/aiciv_mind/tools/handoff_audit_tools.py`

Rationale: `handoff_tools.py` generates context, `handoff_audit_tools.py` verifies quality. `continuity_tools.py` manages lifecycle (write/read/history). Each module has one job. New file keeps concerns cleanly separated.

### Registration
```python
# In __init__.py, ToolRegistry.default():
from aiciv_mind.tools.handoff_audit_tools import register_handoff_audit_tools
register_handoff_audit_tools(registry, memory_store, mind_root, registry)
```

- `memory_store` — `aiciv_minds_memory.memory.MemoryStore` instance (installed package)
- `mind_root` — path to git root (same as `handoff_tools.py`)
- Inner `registry` — the `ToolRegistry` instance (to check tool existence)

---

## Tool Definition

**Name:** `handoff_audit`

**Description:** Audit the most recent handoff memory for quality and accuracy. Runs checks against git history, the tool registry, and prior handoffs. Flags stale claims, tool existence mismatches, unresolved contradictions, and missing context. Returns a JSON report with a trust score and per-check findings. Use this before trusting a handoff, or before writing a new one to see what the next session will actually receive.

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "verbose": {
      "type": "boolean",
      "description": "Include all check results, not just failures. Default: false (failures + warnings only)."
    },
    "handoff_id": {
      "type": "string",
      "description": "Specific handoff ID to audit. Default: most recent."
    }
  },
  "additionalProperties": false
}
```

**Output:** JSON string (see Output Format below).

---

## Data Sources

### Memory store queries (via `memory_store._conn`)

```python
# Most recent handoff memory
SELECT id, title, content, created_at, source_session_id
FROM memories
WHERE memory_type = 'handoff' AND agent_id = 'primary'
ORDER BY created_at DESC
LIMIT 1

# Previous handoff (for contradiction check)
SELECT id, title, content, created_at
FROM memories
WHERE memory_type = 'handoff' AND agent_id = 'primary'
ORDER BY created_at DESC
LIMIT 2

# Session journal (for open sessions check)
SELECT id, session_start, session_end, handoff
FROM session_journal
WHERE agent_id = 'primary'
ORDER BY session_start DESC
LIMIT 5

# Recent evolution log (for tool changes)
SELECT change_type, description, created_at
FROM evolution_log
ORDER BY created_at DESC
LIMIT 10
```

### Git integration (same pattern as `handoff_tools.py`)

```python
# Recent commits (for context)
subprocess.run(["git", "log", "--oneline", "-20"], cwd=mind_root, capture_output=True, text=True, timeout=5)

# Commits after handoff timestamp
subprocess.run(["git", "log", f"--since={handoff_timestamp}", "--oneline"], cwd=mind_root, capture_output=True, text=True, timeout=5)

# Specific commit existence
subprocess.run(["git", "cat-file", "-t", commit_hash], cwd=mind_root, capture_output=True, text=True, timeout=5)

# Files changed since handoff
subprocess.run(["git", "diff", "--name-only", f"{handoff_timestamp}..HEAD"], cwd=mind_root, capture_output=True, text=True, timeout=5)
```

### Tool registry

```python
registry.names()  # list of registered tool names
```

---

## Checks

Each check returns:
```json
{
  "check": "check_name",
  "status": "PASS | FAIL | WARN | SKIP",
  "summary": "One-line summary",
  "findings": [
    {
      "severity": "error | warning | info",
      "message": "Specific issue description"
    }
  ]
}
```

### Check 1: `handoff_exists`

Verify there is a recent handoff to audit.

**Logic:**
1. If `handoff_id` provided: load that handoff by ID via `memory_store.read(id)`.
2. Otherwise: query most recent `memory_type='handoff'` for `agent_id='primary'`.
3. Also check `session_journal` for any sessions with non-null `handoff` field.

**Findings:**
- `error`: No handoff found (no memories of type "handoff" and no session journal entries)
- `warning`: Handoff is >24 hours old
- `warning`: Handoff was written but the session is still open (no `session_end`) — see Check 7
- `info`: First handoff — no prior handoffs to compare against

---

### Check 2: `git_state_reconciliation`

Detect stale state — handoff claims that git history has since changed.

**Logic:**
1. Get all commits after the handoff timestamp.
2. Parse handoff for state claims: "is broken", "is done", "is working", "is fixed", "was added", "was removed".
3. Parse handoff for file paths and commit hashes.
4. For each claim, check if git history after handoff timestamp touches relevant files or contains relevant fixes.
5. For each commit hash mentioned, verify it exists.

**Findings:**
- `error`: Handoff references commit hash that doesn't exist in git log
- `error`: Handoff claims X is in state S, but git history after handoff shows X was changed to a different state
- `warning`: Handoff mentions a file that has new commits since handoff was written
- `info`: Handoff uses past tense ("was fixed") but git shows no corresponding commit in the expected window

---

### Check 3: `tool_existence`

Verify tool-related claims against the actual tool registry.

**Logic:**
1. Parse handoff for capitalized CamelCase identifiers (tool name pattern).
2. Cross-reference each against `registry.names()`.
3. Parse handoff for existence claims: "X tool exists", "X doesn't exist", "no X tool", "add X tool".
4. Check evolution log for tool-related changes after handoff timestamp.

**Findings:**
- `error`: Handoff claims "X tool doesn't exist" but X is registered
- `error`: Handoff claims "add X tool" but X is already registered
- `warning`: Handoff mentions a tool that was added or removed after the handoff was written
- `info`: All tool claims verified against registry

---

### Check 4: `prior_handoff_contradiction`

Detect unresolved contradictions between consecutive handoffs.

**Logic:**
1. Load the previous handoff (second-most-recent `memory_type='handoff'`).
2. Parse both current and previous handoffs for state claims.
3. Extract subject + state for each claim.
4. If same subject has different state in consecutive handoffs and no resolution mentioned → contradiction.

**Findings:**
- `error`: Current handoff says X is in state S1, previous handoff said X is in state S2 (S1 ≠ S2) with no resolution in current handoff
- `warning`: State flip detected but current handoff acknowledges the prior state — OK but flag for visibility
- `info`: No prior handoff to compare against (first handoff)
- `info`: No contradictions detected

---

### Check 5: `temporal_staleness`

Score how stale the handoff is based on age and pending items.

**Logic:**
1. Calculate hours since handoff was written.
2. Parse handoff JSON for `pending_items` and `open_loops` fields.
3. Count unresolved items.
4. If age > 12 hours AND unresolved items → WARN.
5. If age > 48 hours AND unresolved items → FAIL.

**Findings:**
- `error`: Handoff is >48 hours old with unresolved items — risks forwarding stale state
- `warning`: Handoff is N hours old with N pending items
- `info`: No pending items in handoff
- `info`: Handoff is fresh (<12 hours old)

---

### Check 6: `context_completeness`

Verify the handoff contains the minimum required fields.

**Logic:** Parse the JSON content of the handoff memory (or treat raw text as having no fields).
- `summary` — required: what happened this session
- `key_decisions` — required: why choices were made
- `pending_items` — required: what the next session needs to do
- `open_loops` — optional: known unresolved threads

**Findings:**
- `error`: `summary` is empty or missing
- `error`: `pending_items` is empty or missing
- `warning`: `key_decisions` is empty or missing
- `warning`: Handoff content is raw text (not structured JSON) — deep checks skipped
- `info`: All required fields present and non-empty

---

### Check 7: `session_overlap` *(handles the "next session already started" scenario)*

Detect when a new session has started but the previous session's handoff is incomplete or was never audited.

**Logic:**
1. Query `session_journal` for sessions sorted by `session_start` DESC.
2. Identify the two most recent sessions.
3. If the most recent session has `session_start > handoff.created_at` AND the most recent session has no `session_end` → a new session is running with this handoff.
4. Check: has this handoff been audited? (no audit memory exists for this handoff ID)
5. Check: is the handoff complete? (context_completeness status != PASS)
6. If new session is running + handoff incomplete + handoff unaudited → high severity.

**Findings:**
- `error`: A new session (ID: {session_id}) started at {start_time} and is currently running. The handoff it inherited is incomplete (context_completeness: {status}). Audit or rewrite before continuing.
- `error`: A new session is running with an unaudited handoff that has trust score {score}. The next session may be acting on stale or incorrect information.
- `warning`: A new session started {N} hours after this handoff was written. The handoff has not been re-audited since the new session began.
- `info`: No active session running with this handoff (or handoff was properly audited before new session started)

---

## Output Format

```json
{
  "handoff_id": "handoffs_2026-01-15_214503",
  "handoff_session_id": "session_2026-01-15_180000",
  "handoff_timestamp": "2026-01-15T21:45:03Z",
  "handoff_age_hours": 3.2,
  "audited_at": "2026-01-15T23:15:00Z",
  "tool_version": "1.0.0",

  "checks": [
    {
      "check": "handoff_exists",
      "status": "PASS",
      "summary": "Found handoff from 3.2 hours ago",
      "findings": []
    },
    {
      "check": "git_state_reconciliation",
      "status": "FAIL",
      "summary": "2 claims contradicted by git history",
      "findings": [
        {
          "severity": "error",
          "message": "Handoff claims 'Loop1 was broken and needs fixing' but commit b716a8b (2 commits after handoff) fixed Loop1. Update the handoff."
        },
        {
          "severity": "error",
          "message": "Handoff references commit abc1234 which does not exist in git log."
        },
        {
          "severity": "warning",
          "message": "Handoff mentions src/loop1.py which has 3 new commits since this handoff."
        }
      ]
    },
    {
      "check": "tool_existence",
      "status": "PASS",
      "summary": "All tool claims verified",
      "findings": []
    },
    {
      "check": "prior_handoff_contradiction",
      "status": "FAIL",
      "summary": "1 unresolved contradiction with previous handoff",
      "findings": [
        {
          "severity": "error",
          "message": "Previous handoff (session_2026-01-14): 'Loop1 is working correctly.' Current handoff: 'Loop1 is broken.' No resolution or explanation in current handoff."
        }
      ]
    },
    {
      "check": "temporal_staleness",
      "status": "WARN",
      "summary": "3.2 hours old with 4 pending items",
      "findings": [
        {
          "severity": "warning",
          "message": "Handoff is 3.2 hours old with 4 pending items. If session ends before resolving them, next session inherits a stale handoff."
        }
      ]
    },
    {
      "check": "context_completeness",
      "status": "PASS",
      "summary": "All required fields present",
      "findings": []
    },
    {
      "check": "session_overlap",
      "status": "FAIL",
      "summary": "New session running with incomplete, unaudited handoff",
      "findings": [
        {
          "severity": "error",
          "message": "New session (session_2026-01-15_230000) started at 2026-01-15T23:00:00Z and is currently running. The handoff it inherited has FAIL status on git_state_reconciliation, prior_handoff_contradiction, and context_completeness is PASS. Audit or rewrite before continuing."
        }
      ]
    }
  ],

  "trust_score": 38,
  "recommendation": "BLOCKED",
  "recommendation_reason": "Trust score 38 < 50. Multiple critical failures: git contradictions, unresolved prior handoff conflict, new session running with unaudited incomplete handoff."
}
```

### Trust score calculation

```python
def calculate_trust_score(checks: list[dict]) -> int:
    score = 100
    fail_count = 0
    for check in checks:
        status = check["status"]
        if status == "FAIL":
            score -= 25
            fail_count += 1
        elif status == "WARN":
            score -= 10
        elif status == "SKIP":
            score -= 5
    # Session overlap is a multiplier: if new session running with incomplete handoff, cap at 40
    overlap = next((c for c in checks if c["check"] == "session_overlap"), None)
    if overlap and overlap["status"] == "FAIL":
        score = min(score, 40)
    return max(0, min(100, score))
```

### Recommendation logic

```python
def get_recommendation(score: int, checks: list[dict], fail_count: int) -> str:
    if fail_count >= 3:
        return "BLOCKED"
    if score < 50:
        return "BLOCKED"
    if score < 80 or fail_count >= 1:
        return "REVISION_NEEDED"
    return "APPROVED"
```

---

## Implementation Notes

### Error handling
- Each check catches its own exceptions and returns SKIP with the error message
- Tool must not crash — partial results are better than no results
- If git subprocess fails → `git_state_reconciliation` returns SKIP
- If memory query fails → `handoff_exists` returns SKIP, other checks may be skipped
- `verbose=False` suppresses checks with status PASS and no findings

### Claim extraction (model responsibility)
The Python handler does:
1. Raw data gathering (git log, tool list, prior handoff, session journal)
2. JSON output formatting
3. Trust score and recommendation calculation

The claim extraction and contradiction logic is done by the model (3o) which has full context and can:
- Parse natural language state claims from handoff text
- Detect when a handoff contradicts git history
- Identify when consecutive handoffs disagree on a subject's state
- Assess whether a handoff acknowledges or resolves a prior contradiction

The handler provides the raw material; the model fills in the nuance.

### Dependencies
- `memory_store._conn` — sqlite3 connection for direct queries (same pattern as `handoff_tools.py`)
- `memory_store.by_type` — for fetching handoff memories
- `memory_store.read(id)` — for fetching specific handoff by ID
- `subprocess` — git commands (same pattern as `handoff_tools.py`)
- `registry.names()` — to check tool existence
- `json` — parse handoff content and serialize output
- `datetime` / `dateutil.parser` — timestamp comparison for staleness
- `re` — extract CamelCase tool names from text

---

## Acceptance Criteria

- [ ] `handoff_audit` is registered and appears in `registry.names()`
- [ ] Running `handoff_audit` with no args audits the most recent handoff
- [ ] Running `handoff_audit` with `handoff_id` audits that specific handoff
- [ ] Output is valid JSON (parseable by `json.loads()`)
- [ ] Each of the 7 checks executes and reports a status
- [ ] `git_state_reconciliation` correctly identifies commits after handoff timestamp
- [ ] `tool_existence` correctly checks CamelCase tool names against registry
- [ ] `prior_handoff_contradiction` correctly detects state flips between consecutive handoffs
- [ ] `session_overlap` detects when a new session is running with an incomplete/unaudited handoff
- [ ] Trust score reflects check results accurately (including session_overlap multiplier)
- [ ] Tool is read-only (no writes to memory or filesystem)
- [ ] Error in one check does not crash the entire tool
- [ ] `verbose=False` shows only non-PASS checks; `verbose=True` shows all checks
- [ ] `recommendation` is one of: APPROVED, REVISION_NEEDED, BLOCKED
