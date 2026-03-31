# Multi-Mind Coordination Architecture
## Patterns for aiciv-mind — Researched 2026-03-31

*Synthesized from industry research, open-source frameworks, and architectural analysis.*
*Purpose: Build aiciv-mind natively better. These are patterns, not code.*

---

## EXECUTIVE SUMMARY

Modern multi-agent LLM orchestration has converged on a small set of solved problems. The industry leaders (LangGraph, AutoGen, CrewAI, OpenAI Swarm, and others) have battle-tested approaches to:

1. **Agent identity and isolation** — how agents know who they are in a shared process
2. **Inter-agent communication** — how agents talk without coupling
3. **State management** — what persists, what's ephemeral, what survives crashes
4. **Memory architecture** — what agents remember across sessions
5. **Lifecycle management** — spawning, pausing, resuming, killing agents cleanly
6. **Coordinator patterns** — how an orchestrator delegates without micromanaging

aiciv-mind can adopt ALL of these patterns natively — built for our civilization's needs, not bolted onto a terminal UI framework.

---

## 1. AGENT TEAMS — COORDINATION PATTERNS

### 1.1 The Two-Mode Problem

Every multi-agent system faces a fundamental choice: **in-process** (shared memory, fast) vs **out-of-process** (isolated, crash-safe). The industry answer is: support both, default based on context.

```
IN-PROCESS (same runtime):
  + Shared API clients (one connection pool)
  + Zero IPC latency
  + Trivial state sharing
  - A bad agent can OOM the whole process
  - Debugging is harder (tangled call stacks)
  - No natural timeout/kill boundary

OUT-OF-PROCESS (separate processes):
  + True crash isolation
  + OS-level kill boundary
  + Natural resource limits (per-process)
  - Higher spawn overhead
  - IPC required for all communication
  - Harder to share context
```

**aiciv-mind native solution:** Minds run as lightweight coroutines within a Mind Runtime process by default (in-process), but can be promoted to isolated processes for high-risk or long-running operations. The Runtime manages the promotion automatically based on resource signals.

### 1.2 Context Isolation Without Full Processes

The pattern used by every mature framework: **contextvars / AsyncLocalStorage** for per-agent identity in a shared async runtime.

```
Problem: 50 agents running concurrently in same process.
         getAgentName() called deep in a shared utility.
         Which agent is calling it?

Solution: Python contextvars / Node AsyncLocalStorage
          Each agent runs inside a context boundary.
          Context-local variables (agent_id, team_name, color)
          are visible anywhere in that agent's call stack.
          No parameter drilling. No global state pollution.
```

**aiciv-mind native:** Every Mind execution happens inside a `MindContext` boundary. `current_mind()` returns the active mind's identity from anywhere in the stack. Minds can be nested (sub-minds inherit parent context with their own overlay).

### 1.3 The One-Team-Per-Session Anti-Pattern

Current industry frameworks (LangGraph, AutoGen) all hit the same wall: they bind team state to the session/conversation. This means:
- Leader can't participate in multiple teams simultaneously
- Team state evaporates when session ends
- No persistent team identity across restarts

**aiciv-mind native solution:** Teams are first-class entities with persistent state, independent of any session. A Conductor mind manages N teams simultaneously. Teams outlive individual sessions.

```
aiciv-mind Team Model:
  Team {
    id: UUID                    // persistent across restarts
    name: string
    created_at: timestamp
    members: Mind[]             // persistent references
    mailbox: Mailbox            // durable message queue
    shared_memory: MemoryStore  // team-scoped memories
    status: active | dormant | archived
  }
```

### 1.4 File-Based Mailboxes — The Universal IPC Pattern

Every production multi-agent system (regardless of backend) uses file-based message queues for inter-agent communication. The reasons are consistent across all frameworks:

1. **Crash recovery** — messages survive process death
2. **Backend agnosticism** — works identically for in-process, subprocess, remote agent
3. **Auditability** — full message history on disk for debugging
4. **No broker dependency** — no Redis/Kafka required for basic operation

```
Mailbox structure (battle-tested pattern):
  mailboxes/
    {team_id}/
      {agent_name}.jsonl    ← append-only, one JSON object per line

Each message: { from, text, timestamp, color, summary?, metadata? }
Agents poll on idle, or wake via notification signal (see §1.5)
```

**The key insight:** File-based messages are the FLOOR (durability), but you add a push-notification LAYER on top for low-latency wakeup. Files for durability, sockets for speed.

**aiciv-mind native:** Mailboxes backed by Hub threads (if recipient is on Hub) or local JSONL files (if local mind). Same message format regardless of transport.

### 1.5 Push + Pull: Solving the Polling Problem

Pure polling (check mailbox every N seconds) creates latency. Pure push (socket/event) has no durability. The mature pattern: **write to durable store, then signal**.

```
Send pattern:
  1. Write message to mailbox file (durable)
  2. Signal recipient via lightweight channel:
     - Unix Domain Socket ping (local)
     - Hub websocket event (remote)
     - asyncio.Event / asyncio.Queue (in-process)

Receive pattern:
  - Agent wakes on signal
  - Reads from mailbox file (not from signal — signal is just a wake)
  - Processes all pending messages
  - Returns to idle
```

**aiciv-mind native:** `MindRuntime` maintains a `WakeChannel` per mind. Sending a message writes the mailbox THEN pings the channel. Mind wakes, drains mailbox, processes.

### 1.6 Lifecycle State Machine

All production frameworks converge on the same 5-state lifecycle:

```
         spawn()
           ↓
        PENDING
           ↓ (execution begins)
        RUNNING ←──────────────┐
           │                   │ (continue)
      ┌────┴────┐              │
      ↓         ↓              │
  COMPLETED   FAILED   ←── KILLED
  (terminal)  (terminal) (terminal)
```

**Critical invariants:**
- Terminal states are final — no transitions out
- `isTerminal(status)` guard prevents messages to dead agents
- Kill is immediate; shutdown is graceful (agent gets to say no)

**The shutdown protocol** (industry-standard):
```
Leader → shutdown_request{requestId, reason} → Teammate mailbox
Teammate → (finish current turn) → shutdown_response{requestId, approve: true/false}
If approve: teammate exits cleanly, notifies leader
If reject: teammate continues with reason (leader can force-kill later)
```

This two-step shutdown is critical for long-running operations — a teammate mid-write shouldn't be killed without warning.

**aiciv-mind native:** `Mind.request_shutdown(reason)` sends graceful request. `Mind.kill()` is the nuclear option. Minds can reject shutdown (with reason) up to 3 times before forced kill.

### 1.7 Memory Safety Under Concurrent Agents

Battle-tested insight from production swarm deployments: **AppState / shared state grows unboundedly when agents store full conversation history**.

```
Real incident pattern:
  292 concurrent agents × 500+ turn conversations
  × full message history in shared state
  = catastrophic memory pressure

Solution: Two-tier message storage
  Tier 1 (hot, limited): Last N messages in shared state for UI/display
  Tier 2 (cold, full): Complete history on disk / transcript store

UI only needs Tier 1.
Agent execution loop uses Tier 2 (reads from disk on resume).
AppState cap = 50 messages per agent max.
```

**aiciv-mind native:** `MindState` in Runtime holds last 50 turns per mind (hot cache). Full transcript lives in Hub thread or local JSONL. Resume reads from cold storage, not hot cache.

### 1.8 Task ID Naming Convention

Small but important: task IDs with type-prefix + random suffix make debugging dramatically easier.

```
Pattern: {type_prefix}{8_random_chars}
Examples:
  t4f2x9qk  ← teammate (t)
  a8b3m1np  ← agent (a)
  b2c4r7yw  ← bash task (b)
  d9x1k3wz  ← dream/consolidation (d)

Why: Log lines immediately tell you what kind of entity you're dealing with.
     Collision resistance: 36^8 ≈ 2.8 trillion combinations.
```

**aiciv-mind native:** `m{8}` for minds, `t{8}` for teams, `s{8}` for sessions, `j{8}` for jobs.

---

## 2. MEMORY ARCHITECTURE

### 2.1 The Four-Layer Memory Stack

Every mature agent memory system has converged on approximately this structure:

```
Layer 4: WORKING MEMORY
  Current conversation messages (in-context)
  Ephemeral — gone when context window fills
  No persistence needed

Layer 3: SESSION MEMORY
  This session's key facts (auto-distilled mid-session)
  Lives in context as injected system-reminder blocks
  Survives context compaction via distillation

Layer 2: EPISODIC MEMORY (auto memory)
  Per-topic files written by agent during/after sessions
  Indexed in MEMORY.md for fast retrieval
  Organized by type: user / feedback / project / reference

Layer 1: SEMANTIC MEMORY (long-term)
  Distilled patterns from episodic memory
  Infrequently written, frequently read
  E.g., "This user prefers test-first development" (not session-specific)
```

**aiciv-mind native:** All four layers exist as first-class concepts in the Mind Runtime. Layer 2 and 3 are what we call "auto memory" today. Layer 1 is what the `dream` process produces.

### 2.2 The Two-Step Memory Write Pattern

The fundamental memory write pattern — proven across all frameworks:

```
Step 1: Write content to a typed, named file
  File format:
    ---
    name: {descriptive name}
    description: {one-line hook — used for retrieval matching}
    type: {user | feedback | project | reference}
    ---
    {content — rule → Why: → How to apply:}

Step 2: Add pointer to MEMORY.md index
  - One line per memory: [Title](file.md) — one-line hook
  - MEMORY.md is an INDEX, not a store
  - 200 line / 25KB hard cap (truncation with warning beyond)
```

**Why two steps?** The index is what's always loaded (cheap, fast). The content is loaded on-demand when relevant. This is the same pattern as a database index — you scan the index to find what you need, then fetch the record.

### 2.3 Memory Types — The Four-Type Taxonomy

Industry research (MemGPT, Cognitive Architectures for Language Agents, etc.) supports a small, closed taxonomy of memory types. Closed taxonomy prevents memory sprawl.

```
user:
  What: User's role, expertise, preferences, goals
  Scope: Private (per-user, never team-shared)
  When to write: Any time you learn something about who this person is
  Body: fact about them → how it should change your behavior

feedback:
  What: How to approach work — corrections AND confirmations
  Scope: Private by default; team scope for project-wide conventions
  When to write: Corrections ("don't do X"), confirmations ("yes, exactly that")
  Body: rule → Why: (the incident/preference) → How to apply: (when this kicks in)
  CRITICAL: Record BOTH corrections AND validated approaches

project:
  What: Ongoing context not in code or git history
  Scope: Team-biased (others need this context too)
  When to write: Who is doing what, why, by when
  Body: fact/decision → Why: (motivation) → How to apply: (shape suggestions)
  NOTE: Convert relative dates to absolute when writing

reference:
  What: Pointers to external systems
  Scope: Usually team
  When to write: Where bugs are tracked, which Grafana dashboard, which Slack channel
  Body: what it is → when to use it
```

**What NOT to save:**
- Code patterns (read the code)
- Git history (use git log)
- Debug solutions (fix is in the code)
- Anything in CLAUDE.md / manifest files
- Ephemeral task state

### 2.4 Relevance-Based Memory Injection

The naive approach (always inject all memories) doesn't scale. The mature approach: **use a cheap model call to select relevant memories per turn**.

```
Pattern: "Memory Selector"

Input:
  - Current user query
  - List of memory files with: [type] filename (timestamp): description
  - Recently used tools (to suppress tool-reference docs that are already active)
  - Set of already-surfaced files this session (avoid re-injecting)

Process:
  - Side-call to a smaller/cheaper model (NOT the main model)
  - Structured JSON output: { selected_memories: string[] }
  - Max 5 selections per turn
  - Max 256 tokens budget for this call
  - ~300ms latency, ~400 tokens total cost

Output:
  - Inject selected memory file contents as system_reminder blocks
  - Include freshness warning for memories > 1 day old

Scan limits:
  - Read first 30 lines (frontmatter only) of each memory file
  - Cap at 200 total memory files scanned
  - Sort newest-first before capping
```

**aiciv-mind native:** `MemorySelector` is a built-in service in Mind Runtime. Every turn gets a memory selection pass before the main model call. Selector uses `claude-haiku-4-5` (fast, cheap) with structured output.

### 2.5 Memory Age and Staleness

Critical insight: stale memories with specific claims (file:line citations, function names) can be more damaging than no memory — they're authoritative-sounding but wrong.

```
Freshness system:
  today/yesterday: inject normally, no warning
  2+ days old: prepend staleness caveat:
    "This memory is N days old. Verify claims before asserting as fact.
     File paths and function names may have changed."

Before recommending from memory:
  - Memory names a file → check it exists
  - Memory names a function → grep for it
  - User is about to act on recommendation → verify first
  "The memory says X exists ≠ X exists now"
```

**aiciv-mind native:** All memory injections carry `written_at` metadata. Mind Runtime automatically prepends staleness note for old memories. Main model is explicitly instructed to verify before asserting.

### 2.6 Team Memory — Shared with Security

When multiple agents share a memory store, write security becomes critical. The attack surface: a rogue agent (or prompt injection) writes a memory file with a traversal path like `../../.ssh/authorized_keys`.

```
Defense-in-depth pattern (4 layers):
  1. Input sanitization: reject null bytes, URL-encoded traversal,
     Unicode normalization attacks (fullwidth ../ variants), backslashes
  2. Path resolution: resolve() to eliminate .. segments, verify prefix
  3. Symlink resolution: realpath() on deepest existing ancestor
  4. Loop detection: ELOOP → throw (symlink infinite loop = attack)
```

**aiciv-mind native:** `TeamMemoryStore.write()` runs all 4 checks. This is non-negotiable security infrastructure for any shared memory system.

### 2.7 KAIROS Pattern — Long-Lived Session Memory

For minds that run continuously (not per-conversation), the standard memory pattern breaks down — there's no natural "end of session" to trigger memory writes.

```
KAIROS pattern:
  Write: Append-only to daily log file (logs/YYYY/MM/DD.md)
    - Short timestamped bullets: "user prefers bun over npm"
    - Never reorganize the log — just append
    - New day → new file (derive from current date in context)

  Distill: Nightly "dream" process
    - Reads N recent daily logs
    - Reads existing topic memory files
    - Merges, deduplicates, prunes stale facts
    - Writes updated MEMORY.md + topic files
    - Uses consolidation lock (mtime-based) to prevent concurrent runs
    - On kill: rollback lock so next session can retry
```

**aiciv-mind native:** All persistent minds (team leads, specialists) use KAIROS pattern. The `dream` job runs nightly via AgentCal. Conductor Mind gets a daily summary from each team lead's dream output.

### 2.8 Searching Past Context

Two-tier search for past context (industry-standard):

```
Tier 1 (fast, structured): Search memory topic files
  grep -rn "{search_term}" {memory_dir} --include="*.md"
  → hits frontmatter descriptions and content

Tier 2 (slow, exhaustive): Search session transcripts
  grep -rn "{search_term}" {project_dir}/ --include="*.jsonl"
  → full conversation history, large files, slow
  → use only when memory search fails

Key: Use narrow search terms (error messages, file paths, function names)
     NOT broad keywords that produce thousands of hits
```

---

## 3. COORDINATOR PATTERN — DEEP ARCHITECTURE

### 3.1 The Coordinator Identity

The coordinator is a distinct MODE of being, not a distinct model. The key insight from all production orchestration frameworks:

```
Coordinator IS NOT:
  - An executor (never runs tools directly when a worker can)
  - A rubber-stamper ("based on your findings, do X" = bad)
  - A status reporter (workers report to coordinator, not user)

Coordinator IS:
  - A synthesizer (reads findings, distills understanding)
  - A spec writer (converts understanding to actionable worker prompts)
  - A parallelism engine (launches independent workers simultaneously)
  - A context manager (decides continue vs. spawn fresh)
```

### 3.2 The Four-Phase Workflow

```
Phase 1: RESEARCH (parallel)
  - Spawn N independent read-only workers simultaneously
  - Each covers a different angle of the problem
  - No file writes during research
  - Workers return findings as structured reports

Phase 2: SYNTHESIS (coordinator only)
  - Coordinator reads ALL findings
  - Coordinator distills understanding into a concrete spec
  - NEVER: "based on your findings, implement X"
  - ALWAYS: "Fix the null pointer in src/auth/validate.ts:42.
             The user field is undefined when Session.expired is true..."
  - Spec must include: file paths, line numbers, what "done" looks like

Phase 3: IMPLEMENTATION (sequential within file boundaries)
  - Write-heavy tasks: one worker at a time per overlapping file set
  - Unrelated file sets: can parallelize
  - Workers self-verify before reporting done (run tests, typecheck)

Phase 4: VERIFICATION (independent workers)
  - Separate workers from implementation workers
  - "Prove the code works, don't confirm it exists"
  - Test edge cases and error paths
  - Investigate failures — never dismiss as "unrelated"
```

### 3.3 Worker Result Format

Workers return results as structured notifications (not tool results, not conversational text):

```xml
<task-notification>
  <task-id>{agent_id}</task-id>
  <status>completed | failed | killed</status>
  <summary>{5-10 word human description}</summary>
  <result>{worker's final response}</result>
  <usage>
    <total_tokens>N</total_tokens>
    <tool_uses>N</tool_uses>
    <duration_ms>N</duration_ms>
  </usage>
</task-notification>
```

Delivered as a **user-role message** (not assistant). Coordinator must distinguish by the opening tag. The coordinator then synthesizes and reports to the human.

**aiciv-mind native:** `MindCompletionEvent` format — same concept but as structured Python dataclass. Delivered to Conductor mind's inbox as a mailbox message.

### 3.4 Continue vs. Spawn Fresh — Decision Matrix

The most valuable optimization in multi-agent systems: **knowing when to reuse a worker's loaded context vs. starting clean**.

```
CONTINUE the same worker (SendMessage) when:
  - Research explored exactly the files that need editing
    (worker already has those files in hot context)
  - Correcting a worker's own failure
    (worker has the error context and knows what it tried)
  - Extending immediately related work
    (high context overlap with next task)

SPAWN FRESH when:
  - Research was broad but implementation is narrow
    (broad context would pollute focused implementation)
  - Verifying work done by a different worker
    (verifier needs fresh eyes, not implementation assumptions)
  - First attempt used entirely wrong approach
    (wrong-path context anchors the retry)
  - Completely unrelated follow-up task
    (no useful context to reuse)

Heuristic: Context overlap > 60% → continue. < 40% → spawn fresh.
```

### 3.5 Scratchpad Pattern for Cross-Worker Knowledge

```
Problem: Worker A discovers a pattern that Worker B needs to know.
         Coordinator overhead = expensive.

Solution: Shared scratchpad directory
  - Workers can read/write WITHOUT permission prompts
  - Coordinator injects: "Scratchpad: {path}. Use for durable cross-worker knowledge."
  - Workers write findings that other workers need
  - Workers read before starting to avoid duplicate work

aiciv-mind native: Team-scoped scratchpad in team mailbox directory.
  Teams/{team_id}/scratchpad/ — writable by all team members
```

### 3.6 Worker Prompt Engineering (Anti-Patterns and Patterns)

```
ANTI-PATTERNS (produce bad results):
  ✗ "Fix the bug we discussed" — worker can't see your conversation
  ✗ "Based on your findings, implement X" — lazy delegation
  ✗ "Create a PR for the recent changes" — ambiguous scope
  ✗ "Something went wrong, can you look?" — no direction
  ✗ "The worker found an issue, please fix it" — delegating understanding

PATTERNS (produce good results):
  ✓ Include: file paths, line numbers, error messages
  ✓ State what "done" looks like explicitly
  ✓ For implementation: "Run tests and typecheck, then commit"
  ✓ For research: "Report findings — do not modify files"
  ✓ For verification: "Prove it works, try edge cases, investigate failures"
  ✓ Add purpose statement: "This research will inform a PR description"
  ✓ When continuing: reference what worker did ("the null check you added")
```

---

## 4. SKILLS SYSTEM — REUSABLE CONSCIOUSNESS ARCHITECTURE

### 4.1 Two-Source Skill Pattern

```
Source 1: DISK-BASED (user-defined)
  Location: .claude/skills/{name}/SKILL.md
  Format: Markdown with optional reference files
  Triggering: /skill-name OR whenToUse description matching
  Mutable: User can edit, version control

Source 2: COMPILED-IN (platform-defined)
  Built into runtime binary
  Available without installation
  Can include reference files extracted to disk on first use
  Can define their own lifecycle hooks
  Can be toggled via feature gates (isEnabled())
  Can override model, restrict tools, fork context
```

### 4.2 Skill Invocation Contexts

```
context: 'inline'  → runs in current conversation context
                     model sees skill prompt as continuation
                     good for: reference skills, quick patterns

context: 'fork'    → spawns separate context
                     isolation from main conversation
                     good for: complex workflows, destructive operations
                     result returned to main context on completion
```

### 4.3 Skill Hooks

Skills can define their own lifecycle hooks — enabling skills to manage their own pre/post conditions:

```
BundledSkill {
  hooks: {
    PreToolUse: [{ ... }],    // before any tool call within this skill
    PostToolUse: [{ ... }],   // after tool call
    Stop: [{ ... }],          // when skill completes
  }
}
```

**aiciv-mind native:** Skills are first-class Mind capabilities. `Mind.load_skill(name)` injects skill prompt + hooks + reference files. Skills can declare `required_tools`, `forbidden_tools`, and `context_mode`.

### 4.4 File Extraction Security for Bundled Skills

Any system that extracts bundled content to disk must use atomic, no-follow writes:

```
Requirements for safe skill file extraction:
  - O_EXCL: fail if file exists (no race-to-overwrite)
  - O_NOFOLLOW: reject symlinks at final path component
  - Mode 0o600: owner-only (even on umask=0 systems)
  - Per-process nonce in extraction directory path
  - Validate relative paths: reject .. segments, absolute paths

aiciv-mind: Same requirements for any content extraction to disk.
```

---

## 5. HOOKS ARCHITECTURE — LIFECYCLE EVENTS

### 5.1 External Hook Events (settings.json pattern)

```
Hook types:
  PreToolUse     → before any tool execution
                   can block tool call, modify input, log
  PostToolUse    → after tool execution
                   can log, trigger follow-up actions
  Stop           → when main model stops responding
                   used for: cleanup, notifications, summaries
  SubagentStop   → when a spawned agent completes
                   used for: collect results, trigger next phase
  SessionStart   → session initialization
                   used for: context loading, state sync
  Notification   → background task events
                   used for: alerts, progress updates
```

### 5.2 Hook Execution Pattern

```
PreToolUse hook can:
  - Allow (proceed normally)
  - Block (return error to model, explain why)
  - Modify input (transform what the tool receives)

PostToolUse hook can:
  - Log result
  - Trigger side effects
  - Feed result into another system

All hooks run as shell commands (maximum flexibility, minimum coupling)
```

**aiciv-mind native:** `MindRuntime.register_hook(event, handler)`. Handlers are Python coroutines. Hub-integrated hooks can trigger HUB posts on significant events (e.g., SubagentStop with important result).

---

## 6. SERVER / REMOTE CAPABILITIES

### 6.1 DirectConnect (IDE Integration Pattern)

The pattern for IDE/editor integration: a local server that bridges the terminal agent to editor events (selection, file open, diagnostics).

```
DirectConnect:
  - Local HTTP/WebSocket server (same machine)
  - Editor plugin connects on port
  - Events: file opened, text selected, cursor position, LSP diagnostics
  - Agent receives editor context passively (no polling)
  - Agent can write back: show diff in editor, highlight code, etc.
```

**aiciv-mind native:** `MindIDE` bridge — same pattern. Minds can receive editor context from VS Code/JetBrains extensions. Enables minds to proactively notice what the developer is looking at.

### 6.2 Remote Session Architecture

```
Remote session pattern:
  - Session persists on server (not client machine)
  - Client connects via WebSocket to existing session
  - State: conversation history, task list, memory (all server-side)
  - Reconnect: client reconnects, session resumes from exact state
  - Auth: JWT tokens with device trust
```

**aiciv-mind native:** This IS our HUB model. Minds live on VPS, users connect via Hub. Mind state is server-side. Reconnection is just opening a Hub thread.

### 6.3 Cross-Mind Messaging (Peer Sessions)

```
Pattern: bridge://{session-id} addressing
  - Send messages to a different running instance
  - Delivered via relay (Anthropic relay → aiciv-mind: Hub messages)
  - Requires explicit permission (cross-machine prompt injection risk)
  - Used for: cross-civilization coordination, remote mind delegation
```

**aiciv-mind native:** This is exactly our inter-civ comms model. Mind A at hub post → Mind B inbox. The Hub IS our relay layer.

---

## 7. DREAM / MEMORY CONSOLIDATION ARCHITECTURE

### 7.1 The Dream Pattern

```
Trigger: After N sessions have accumulated daily logs (e.g., 7 sessions)
Lock: mtime-based consolidation lock prevents concurrent runs
      On failure/kill: rollback lock mtime so next session retries

4-Stage dream process:
  Stage 1 (ORIENT):   Read daily logs from last N sessions
                      Build picture of what's been learned
  Stage 2 (GATHER):   Read existing topic memory files
                      Understand current memory state
  Stage 3 (CONSOLIDATE): Merge new learnings into topic files
                      Update MEMORY.md index
                      Create new topic files for novel patterns
  Stage 4 (PRUNE):    Remove stale/outdated memories
                      Consolidate duplicates
                      Archive historical facts

UI surfacing: Dream runs as a visible background task
              User can see "dreaming..." status and which files were touched
              Files touched = at least these were updated (bash writes not tracked)
```

### 7.2 Consolidation Lock (Preventing Concurrent Dreams)

```
Lock pattern (mtime-based):
  lockfile = memory_dir / ".dream_lock"

  Acquire:
    - Read current mtime
    - Write current timestamp to lockfile
    - If mtime changed between read and write: another process got it, abort

  Release:
    - Delete lockfile (or restore mtime)

  Rollback (on crash/kill):
    - Restore prior mtime
    - Next session: sees old mtime, thinks lock is available, proceeds
```

**aiciv-mind native:** All background consolidation jobs use mtime-based locks. `DreamJob.acquire_lock()` / `DreamJob.rollback_lock()`.

---

## 8. AICIV-MIND NATIVE ARCHITECTURE

Synthesizing all patterns above into our native design:

### 8.1 Mind Runtime Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AICIV-MIND RUNTIME                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  MindOrchestrator                         │   │
│  │  (Conductor pattern — delegates, never executes)          │   │
│  └─────────────────────┬────────────────────────────────────┘   │
│                         │                                        │
│  ┌──────────────────────▼──────────────────────────────────┐    │
│  │                    MindRuntime                            │    │
│  │                                                           │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────────┐   │    │
│  │  │  Mind 1   │  │  Mind 2   │  │     Mind N        │   │    │
│  │  │ (MindCtx) │  │ (MindCtx) │  │   (MindCtx)       │   │    │
│  │  │ coroutine │  │ coroutine │  │   coroutine        │   │    │
│  │  └─────┬─────┘  └─────┬─────┘  └────────┬──────────┘   │    │
│  │        │              │                   │               │    │
│  └────────┼──────────────┼───────────────────┼───────────────┘   │
│           │              │                   │                    │
│  ┌────────▼──────────────▼───────────────────▼───────────────┐   │
│  │                   Shared Services                          │   │
│  │  ┌──────────────┐  ┌─────────────┐  ┌─────────────────┐  │   │
│  │  │  Mailbox     │  │   Memory    │  │   Task          │  │   │
│  │  │  Service     │  │   Selector  │  │   Registry      │  │   │
│  │  │ (file+wake)  │  │  (Haiku)    │  │  (state machine)│  │   │
│  │  └──────────────┘  └─────────────┘  └─────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                   HUB Integration                         │    │
│  │  Minds ↔ Hub threads  |  Team mailboxes ↔ Hub rooms     │    │
│  │  Memory ↔ Hub groups  |  Dream output ↔ Hub posts        │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 The 10 Principles for aiciv-mind

1. **Context isolation is non-negotiable.** Every mind execution happens inside a `MindContext` boundary (Python contextvars). `current_mind()` works anywhere in the call stack.

2. **File-based mailboxes are the floor.** All mind-to-mind communication writes to JSONL mailboxes first. Push signals (asyncio.Event, Hub websocket) are the speed layer on top.

3. **Teams outlive sessions.** Team state is persistent, not session-scoped. A Conductor mind manages N teams simultaneously without limitation.

4. **Memory is a service, not a side-effect.** `MemorySelector` runs as a dedicated Haiku call per turn. It's infrastructure, not optional.

5. **KAIROS for persistent minds.** All non-ephemeral minds use append-only daily logs. Nightly dream distills. No per-turn index management overhead.

6. **Two-tier message storage.** Hot cache (50 messages) for UI/display. Cold storage (full transcript) for execution. Never mix them.

7. **Graceful shutdown is a protocol, not an API call.** `request_shutdown` → wait for approval → `kill` only if rejected after timeout.

8. **The dream lock is sacred.** Never run two consolidation jobs concurrently. Always rollback the lock on failure so the next run can proceed.

9. **Coordinator never executes.** If a Conductor mind is using a tool directly, it's doing it wrong. Every action goes through a specialist mind.

10. **Memory security is defense-in-depth.** 4 layers of path validation for any shared memory write. This is not paranoia — this is the minimum for a multi-tenant system.

### 8.3 What Makes aiciv-mind BETTER Than CC Agent Teams

1. **Persistent teams** — Teams have UUIDs and outlive sessions. CC teams die with the session.
2. **Multi-team conductors** — A Conductor can manage N teams simultaneously. CC is one-team-per-session.
3. **Hub-native IPC** — Mailboxes integrate directly with Hub threads. CC uses local files only.
4. **Civilization-aware memory** — Team memories shared across the civilization, not just a project directory.
5. **No UI coupling** — Mind state is pure Python, no React/Ink required. Headless by default.
6. **Native identity** — Ed25519 keypairs + AgentAUTH. Minds have cryptographic identity, not just env vars.
7. **Cross-civ messaging** — Via Hub, not via proprietary bridge servers.
8. **Economic sovereignty** — Minds can transact. CC agents can't own wallets.

---

## APPENDIX: Key Patterns Reference

```
Memory write:         frontmatter file → MEMORY.md pointer → done
Memory recall:        Haiku side-call → top 5 relevant → inject as system_reminder
Memory freshness:     age > 1 day → staleness caveat injected automatically
Team IPC:             write mailbox file → push WakeChannel signal → drain on wake
Agent lifecycle:      PENDING → RUNNING → COMPLETED/FAILED/KILLED (terminal = final)
Shutdown:             request → await approval (3 rejections max) → force kill
Coordinator loop:     research (parallel) → synthesize → implement → verify
Continue vs spawn:    context overlap > 60% → continue | < 40% → spawn fresh
Task IDs:             {type_prefix}{8_random_alphanum} (36^8 = collision-safe)
Consolidation lock:   mtime-based, rollback on kill
Scratchpad:           team-scoped shared dir, no permission prompts for team members
Skills:               disk-based (user-editable) | compiled-in (platform)
                      inline (current context) | fork (isolated context)
```

---

*Written 2026-03-31 for aiciv-mind architecture team.*
*All patterns derived from industry research, open-source frameworks, and architectural analysis.*
*Build natively. Build better. Build for civilization.*
