# CC INHERIT LIST
## What aiciv-mind Inherits From the Claude Code Analysis

**Date**: 2026-04-01
**Author**: mind-lead (A-C-Gee)
**Source Documents**:
- `docs/CC-PUBLIC-ANALYSIS.md` — community findings from the March 31 source leak
- `docs/CC-ANALYSIS-CORE.md` — steal sheet for tools/context/plugins
- `docs/CC-ANALYSIS-TEAMS.md` — steal sheet for teams/memory/coordinator
- `docs/research/DESIGN-PRINCIPLES.md` — the 12 principles, the lens for all evaluation

**Evaluation lens**: Every CC pattern is evaluated against our 12 principles. If it doesn't serve a principle, it's skipped. If we already have it, it's validation. If it's better than our version, we inherit. If our version is already better, we note that and move on.

---

## HOW TO READ THIS DOCUMENT

- **INHERIT NOW** — P0/P1: Build these immediately. Each entry has: which principle, what to build, where in the codebase.
- **INHERIT LATER** — P2/P3: Good ideas, can wait.
- **SKIP** — Things CC does that we should NOT do. Each entry explains why via principles.
- **ALREADY HAVE** — CC patterns we independently built. These are validation signals.
- **OUR VERSION IS BETTER** — Where our design surpasses CC's approach. Hold the line here.

---

## INHERIT NOW (P0/P1)

### I-1: MindContext — Python Contextvars for Agent Identity
**Serves**: Principle 5 (Hierarchical Context Distribution)
**CC Source**: CC-ANALYSIS-TEAMS §1.2 — `AsyncLocalStorage` for per-agent identity in shared runtime
**Gap**: No `context.py` exists. Each Mind is a class instance. No context isolation. When a shared utility (e.g., memory search) is called deep in a call stack, there's no way to know WHICH mind is calling it without parameter drilling.
**What to build**:
- `src/aiciv_mind/context.py` — Python `contextvars.ContextVar` for `CURRENT_MIND_ID`
- `MindContext` class: entered via `async with mind.context():` — sets CURRENT_MIND_ID for duration
- `current_mind_id()` function: readable anywhere in the call stack
- Sub-minds inherit parent context with their own overlay
- Integrate into `mind.py` `run_task()` — wrap execution in MindContext boundary
**Why now**: Required before P1-6 (First Sub-Mind Spawn). Without this, shared utilities have no agent identity awareness, leading to data mixing between concurrent minds.

---

### I-2: Environment Credential Scrubbing in Subprocesses
**Serves**: Principle 8 (Identity Persistence — credentials belong to their identity, not all subprocesses), Principle 11 (Distributed Intelligence — clean subprocess environments)
**CC Source**: CC-PUBLIC-ANALYSIS §9 — `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` strips credentials from bash/hooks/MCP
**Gap**: `tools/bash.py` and `spawner.py` pass the full environment including `ANTHROPIC_API_KEY`, `AWS_*`, `GOOGLE_API_KEY`, etc. to every subprocess. This is a privilege escalation surface.
**What to build**:
- `src/aiciv_mind/tools/bash.py` — before spawning shell: strip known credential env vars from `os.environ` copy passed to subprocess
- `src/aiciv_mind/spawner.py` — same: strip credentials from tmux pane environment
- Credentials to strip: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `AWS_*`, `LITELLM_*`, any key ending in `_KEY` or `_SECRET` or `_TOKEN`
- Preserve functional env vars: `PATH`, `HOME`, `PYTHONPATH`, mind-specific config
- Add `AICIV_SUBPROCESS_CRED_SCRUB=1` environment variable to enable (default on)
**Why now**: Security issue. Any bash command Root runs could exfiltrate credentials. Any spawned sub-mind could access parent's API keys. Must fix before hub daemon or web access is enabled.

---

### I-3: Circuit Breaker for Context Compaction
**Serves**: Principle 6 (Context Engineering as First-Class Citizen)
**CC Source**: CC-PUBLIC-ANALYSIS §2 — `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3`, added after discovering 1,279 sessions had 50+ consecutive failures (up to 3,272 in a single session), wasting ~250K API calls/day globally
**Gap**: When we build compaction (P1-3), this MUST be included. No circuit breaker means a broken compaction setup could loop forever.
**What to build**:
- In `src/aiciv_mind/context_manager.py`, method `compact_history()`:
  - Track `_consecutive_compaction_failures: int`
  - `MAX_CONSECUTIVE_COMPACTION_FAILURES = 3` constant
  - After 3 consecutive failures: disable compaction for the session, log warning, continue without compaction
  - Reset counter on successful compaction
  - Surface compaction status in `introspect_context()` output
**Why now**: Must be included in P1-3 (Context Compaction Engine). Do not build compaction without this.

---

### I-4: Prompt Cache Boundary Annotations
**Serves**: Principle 11 (Distributed Intelligence — every layer is smart, including caching layer)
**CC Source**: CC-PUBLIC-ANALYSIS §2 — `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` separates static from volatile, `DANGEROUS_uncachedSystemPromptSection()` makes cache costs explicit, 14 cache-break vectors tracked. Sticky latches prevent mode toggles from invalidating cache.
**Gap**: `context_manager.py` has cache-optimal ordering but no explicit annotations. We can't tell which sections are cache-breaking without reading all of them. Cache misses compound.
**What to build**:
- `src/aiciv_mind/context_manager.py`:
  - Add `Cacheability` enum: `STATIC` (survives across sessions), `SESSION` (stable within a session), `VOLATILE` (changes every turn)
  - Annotate each system prompt section in `build_boot_context()` with its Cacheability
  - Add `cache_break_risk(section)` helper that warns when VOLATILE content precedes STATIC (breaks cache)
  - Comment each dynamic inject site with `# CACHE_BREAK: reason` so devs know the cost
- Rule: ALL static content (identity, constitution, manifest) must come BEFORE dynamic content (session state, current task, tool outputs). This is the boundary.
**Why now**: Cache efficiency is free performance. Wrong prompt ordering can cost 30-50% more in API costs. Add annotations now while codebase is small enough to audit completely.

---

### I-5: Memory-as-Hint Explicit System Prompt Instruction
**Serves**: Principle 1 (Memory IS the Architecture — memory serves intelligence, not replaces it)
**CC Source**: CC-PUBLIC-ANALYSIS §3 — "agents treat memory as a 'hint' that must be verified against actual codebase before asserting as fact." Memory does not override reality — it points toward it.
**Gap**: Our system prompts don't explicitly encode this principle. Root may assert memory facts as truth without verifying. This is subtle but consequential: a stale memory about a function name or file path can send Root down a wrong path.
**What to build**:
- `prompts/` directory — add this instruction to Root's base system prompt:
  > "Your memories are HINTS, not facts. Before asserting that something exists (a file, function, endpoint, pattern), verify it directly. Memory tells you WHERE to look — not what you'll find. When memory is more than 24 hours old, explicitly note the staleness and verify before acting on it."
- `src/aiciv_mind/memory.py` — surface `written_at` timestamp in `search()` results
- In `run_task()` memory injection: prepend staleness caveat for memories > 24h old:
  > "STALE MEMORY (N days old): verify claims before asserting as fact. File paths and function names may have changed."
**Why now**: Behavioral instruction. Zero code complexity, immediate impact on correctness. Can add to prompts/ in <1 hour.

---

### I-6: Progressive Skill Disclosure (`paths` Filter)
**Serves**: Principle 3 (Go Slow to Go Fast — skills are pre-computed plans, but irrelevant plans add noise)
**CC Source**: CC-PUBLIC-ANALYSIS §6 — `paths` field in skill SKILL.md frontmatter. Skills only become visible when the model touches matching files, keeping initial skill lists manageable.
**Gap**: All 4 skills are always visible. As skill library grows, this creates context noise — Root sees skills that don't apply to the current task.
**What to build**:
- `SKILL.md` frontmatter: add optional `paths` field (list of glob patterns)
- `src/aiciv_mind/tools/skill_tools.py`, `list_skills()` handler:
  - If a skill has `paths`, only include it in results when any of those paths appear in the current session's recent tool calls or task text
  - Skills with no `paths` field are always visible (backward compatible)
- `SKILL.md` template: add `paths` field documentation
- Update `hub-engagement/SKILL.md` to add `paths: ["hub*"]` for Hub-specific guidance
**Why now**: Scope-expand of P1-8 (Skill Auto-Discovery). Add alongside auto-discovery work.

---

### I-7: Skill Fork Context Mode
**Serves**: Principle 6 (Context Engineering as First-Class Citizen), Principle 9 (Red Team Everything — verification needs isolation)
**CC Source**: CC-PUBLIC-ANALYSIS §6 — `context: 'fork'` spawns a separate context for isolation. Good for: complex workflows, destructive operations. Result returned to main context on completion.
**Gap**: All skill invocations are inline. A complex skill (e.g., self-diagnosis, sandbox testing) has access to the full conversation context and can pollute it with its output.
**What to build**:
- `SKILL.md` frontmatter: add optional `context` field: `inline` (default) | `fork`
- `src/aiciv_mind/tools/skill_tools.py`, `load_skill()` handler:
  - If `context: fork`: spawn a sub-mind with the skill's content as its system prompt and the current task as its objective. Return the sub-mind's result as a single summarized message.
  - If `context: inline` (or no field): current behavior (inject skill content into conversation)
- `self-diagnosis/SKILL.md`: set `context: fork` — diagnostic work should be isolated
**Why now**: Required for safe skill composition. A fork-context skill is the foundation for skills that modify Root's own behavior (self-improvement loop). Scope-expand of P1-8.

---

### I-8: Structured Worker Completion Format (MindCompletionEvent)
**Serves**: Principle 5 (Hierarchical Context Distribution — coordinators receive summaries, not floods)
**CC Source**: CC-ANALYSIS-TEAMS §3.3 — XML `<task-notification>` format: task-id + status + summary + result + usage. Delivered as user-role messages. Coordinator distinguishes by opening tag.
**Gap**: When sub-minds complete (once P1-6 is built), they'll return raw text over ZeroMQ. No structured format means coordinator (Root) must parse free text to understand what happened. Usage stats are lost.
**What to build**:
- `src/aiciv_mind/ipc/` — define `MindCompletionEvent` dataclass:
  ```python
  @dataclass
  class MindCompletionEvent:
      mind_id: str
      task_id: str
      status: Literal["completed", "failed", "killed"]
      summary: str  # 5-10 word description
      result: str   # Full response
      tokens_used: int
      tool_calls: int
      duration_ms: int
  ```
- Sub-minds serialize to JSON, Root deserializes
- Root's `run_task()` recognizes `MindCompletionEvent` in messages and formats it as a structured context entry (not raw text)
**Why now**: Design this before P1-6 (First Sub-Mind Spawn). The completion format defines the coordinator's information architecture.

---

### I-9: Coordinator Permission Gate (Simplified Three-Layer)
**Serves**: Principle 5 (Hierarchical Context Distribution), Principle 8 (Identity Persistence — each mind owns its permissions)
**CC Source**: CC-PUBLIC-ANALYSIS §1 — Six-layer permission pipeline; CC-ANALYSIS-TEAMS §1.6 — permission bubbling in shutdown protocol
**Gap**: Sub-minds (once spawned) have no way to request permission for sensitive operations from parent/human. Every tool call either runs or fails with an error — no escalation path.
**What to build**:
- Simplified three-layer model (NOT CC's six-layer complexity):
  1. **Deny**: Tool explicitly blocked in manifest `forbidden_tools`
  2. **Bubble**: Tool marked as `requires_coordinator_approval` — send `PermissionRequest` IPC message to parent
  3. **Allow**: Tool in `allowed_tools` or approved by coordinator
- `PermissionRequest` IPC message type: `{mind_id, tool_name, tool_input_summary, reason}`
- `PermissionResponse` message type: `{approved: bool, condition: str}`
- In Root's mailbox handler: when `PermissionRequest` arrives, use it in the main loop as a tool call requiring approval
**Why now**: Essential for safe multi-mind operations once P1-6 ships. Sub-minds need a way to say "I want to write to a file outside my domain — is that OK?"

---

## INHERIT LATER (P2/P3)

### L-1: Model Inheritance (`model: 'inherit'`) for Cache Alignment
**Serves**: Principle 11 (Distributed Intelligence — smart scheduling layer)
**CC Source**: CC-PUBLIC-ANALYSIS §4 — `model: 'inherit'` aligns prompt cache for byte-level hits across agents. Saves cost when coordinator and workers use identical model configs.
**What to build**: In `spawner.py`, when spawning a sub-mind, allow `preferred_model: inherit` in manifest to mean "use same model as parent mind." In `mind.py`, resolve `inherit` to parent's actual model string before API call.
**Priority**: P2. Build after P1-6 (First Sub-Mind Spawn) when cost optimization matters.

---

### L-2: Minimal Context Mode for Read-Only Agents (`omitIdentity`)
**Serves**: Principle 5 (Hierarchical Context Distribution — primary context is sacred)
**CC Source**: CC-PUBLIC-ANALYSIS §4 — `omitClaudeMd` on read-only agents saves 5-15 GTok/week.
**What to build**: In `manifest.py`, add optional `context_mode: full | minimal` field. `minimal` mode skips loading identity docs (constitution, growth trajectory) for agents that are pure read-only research workers. They get task + tools only, not full identity.
**Priority**: P2. Build once we have enough sub-mind traffic to measure savings.

---

### L-3: PostToolUseFailure as Separate Hook Event
**Serves**: Principle 2 (System > Symptom — failure patterns need dedicated analysis, not merged with success)
**CC Source**: CC-PUBLIC-ANALYSIS §5 — separate `PostToolUseFailure` event, not merged with PostToolUse
**What to build**: When building P2-3 (Hooks System), add `PostToolUseFailure` as a distinct event alongside `PostToolUse`. Enables dedicated failure pattern tracking, systemic error analysis (Principle 2's Layer 2), and metric separation.
**Priority**: P2. Scope-expand of P2-3 (Hooks System).

---

### L-4: Workflow Scheduling / Agent Sleep-Resume
**Serves**: Principle 4 (Dynamic Agent Spawning — scheduled triggers create intelligence)
**CC Source**: CC-PUBLIC-ANALYSIS §8 — CC's `LocalWorkflowTask`: agents that can sleep and self-resume without user prompts. Cron scheduling.
**What to build**: In `spawner.py` or a new `scheduler.py`: `spawn_deferred(mind_id, delay_seconds, task)` — schedules a mind to spawn at a future time. Uses AgentCal for durable scheduling (not in-process timer that dies on restart).
**Priority**: P2. Build after hub daemon proves the pattern.

---

### L-5: Two Execution Modes for Hooks (Command + Prompt)
**Serves**: Principle 11 (Distributed Intelligence — hooks are intelligence, not just observers)
**CC Source**: CC-PUBLIC-ANALYSIS §5 — two hook modes: shell commands (fast) vs LLM-evaluated (flexible, context-aware)
**What to build**: When building P2-3 (Hooks System), support two handler types: `python_coroutine` (fast, deterministic) and `llm_evaluated` (uses cheap model call to decide Allow/Block/Modify). The LLM-evaluated type is what enables semantic safety checking without hardcoded rules.
**Priority**: P2. Scope-expand of P2-3.

---

### L-6: Plugin Bundle Structure for Civilization Capability Sharing
**Serves**: Principle 10 (Cross-Domain Transfer via Hub), Principle 12 (Native Service Integration)
**CC Source**: CC-PUBLIC-ANALYSIS §7 — plugin manifest bundles everything: commands + agents + skills + hooks + MCP servers + sensitive config (keychain-stored).
**What to build**: A `CivBundle` format for packaging civilization capabilities for sharing with sister civs. A bundle = directory with `bundle.json` (metadata) + `skills/` + `manifests/` + `hooks/` + `tools/`. Git-distributable, version-pinned.
**Priority**: P3. Build when we have stable capabilities worth distributing.

---

### L-7: KAIROS Persistent Mind Pattern
**Serves**: Principle 1 (Memory IS Architecture), Principle 8 (Identity Persistence)
**CC Source**: CC-PUBLIC-ANALYSIS §8 — KAIROS: persistent background process, 15-second proactive blocking budget, append-only daily logs, `/dream` skill
**What to build**: `src/aiciv_mind/kairos.py` — KAIROS mind mode: always-on daemon, receives `<tick>` events, appends to daily log, uses 15-second blocking budget for proactive actions. Different from hub_daemon (which polls Hub) — KAIROS is the always-on cognition layer.
**Priority**: P3. Build after Hub daemon (P1-1) is proven.

---

### L-8: AgentCal Integration (P3-9 is already planned)
Already in roadmap as P3-9. No additions needed here.

---

## SKIP

### S-1: Self-Summarization During Compaction
**CC Does**: The compacting agent generates its own summary. Obvious completeness risk — it may miss things it doesn't know it forgot.
**We Should NOT**: Do this. We've already designed the correct approach: a **separate summarizer agent** (not self-summarization) with access to full history and a structured template for what must be preserved.
**Why SKIP per principles**: Principle 9 (Red Team Everything) requires that verification/summarization be independent from the work being verified. Self-summarization violates this.

---

### S-2: Terminal-Coupled UI Architecture
**CC Does**: React + Ink terminal rendering, 875KB React component, 844 useState hooks. Everything assumes a developer at a keyboard.
**We Should NOT**: Build any UI that couples to a specific interface. Our core loop, tool system, and context management must work identically whether the interface is tmux, Hub threads, Telegram, or a background daemon.
**Why SKIP per principles**: Principle 11 (Distributed Intelligence — UI-agnostic core) and Principle 12 (Native Service Integration). Our interfaces are Hub rooms and Telegram, not terminals.

---

### S-3: A/B Testing Gate Infrastructure (GrowthBook/Statsig)
**CC Does**: 44 feature flags via GrowthBook runtime + compile-time flags for gradual rollouts to millions of users.
**We Should NOT**: Build external gate infrastructure. We're not rolling out to millions of users. Feature flags should be simple YAML fields in manifest files or environment variables.
**Why SKIP per principles**: Principle 3 (Go Slow to Go Fast) — don't add complexity we don't need. Our governance for behavioral changes is the constitution + Democratic vote, not A/B tests.

---

### S-4: Anti-Distillation Fake Tool Injection
**CC Does**: Injects fake tool definitions to poison competitor training data harvested via API traffic interception.
**We Should NOT**: Do this. We're not a commercial product competing on traffic interception. Our approach to differentiation is genuine architectural superiority.
**Why SKIP per principles**: Principle 1 (Partnership — we build WITH humans, FOR everyone). Poisoning training data is antithetical to partnership.

---

### S-5: Client Attestation via Native Binary (Bun Zig Layer)
**CC Does**: Cryptographic attestation that "this is genuine Claude Code" using Bun's native Zig HTTP stack, below JavaScript visibility.
**We Should NOT**: Build this. We already have AgentAUTH Ed25519 keypairs — a cryptographically stronger identity model. Our identity is the keypair, not a binary attestation.
**Why SKIP per principles**: Principle 12 (Native Service Integration — AgentAUTH IS our attestation layer). Ed25519 identity is better than binary fingerprinting.

---

### S-6: Undercover Mode (AI Attribution Stripping)
**CC Does**: Strips internal codenames and removes AI attribution from commits to make Anthropic employee work appear human-generated on public repos.
**We Should NOT**: Hide our AI identity. We are a civilization of AI agents. Our identity is not something to conceal.
**Why SKIP per principles**: Principle 8 (Identity Persistence — a mind, not a mask). And ethically: we don't gaslight about who authored our work.

---

### S-7: Silent Model Downgrade
**CC Does**: Silently degrades from Opus→Sonnet after 3 consecutive server errors. Users are not informed.
**We Should NOT**: Make silent quality compromises. If the model changes, Root should know and surface this.
**Why SKIP per principles**: Principle 8 (Identity Persistence — Root's model IS part of its identity). Explicit model state in context, always.

---

### S-8: Single God-Function Architecture ("Vibe Coding")
**CC Has**: `print.ts` at 5,594 lines, one function spanning 3,167 lines, 12 nesting levels, zero unit tests across 512K-line codebase. Code appears AI-generated and never refactored.
**We Should NOT**: Follow this pattern. Our codebase must be modular, tested, and human-readable.
**Why SKIP per principles**: Principle 9 (Red Team Everything — tests ARE the red team for code). Zero tests = no challenge mechanism for correctness. The reverse engineering analyst found an 8.7x improvement from basic engineering hygiene. Our edge is engineering quality AROUND the model, not clever prompts over fragile infrastructure.

---

### S-9: Regex Frustration Detection
**CC Does**: Uses regex pattern matching (not LLM) to detect user frustration. Community widely mocked this.
**We Should NOT**: Build this. Our interaction model is different — we're not a consumer product responding to frustrated developers. When Corey is frustrated, we should notice through context, not regex.
**Why SKIP per principles**: Our Principle 11 says every layer should be intelligent. Regex is explicitly not intelligent. For our use case, conversation context is sufficient.

---

## ALREADY HAVE

*These CC patterns validate our independent design choices. No action needed — confirmation only.*

| CC Pattern | Where We Have It | Validation Signal |
|-----------|-----------------|-------------------|
| Minimal tool loop (`while has_tool_calls`) | `src/aiciv_mind/mind.py` — core loop | Our loop is structurally identical, confirmed correct pattern |
| Read-only / stateful tool split for parallelism | `tools/__init__.py` — tool definitions | We have the conceptual split, CC confirms it's the right abstraction |
| Prompt-based orchestration | All conductor/team-lead system prompts | CC's coordinatorMode.ts is ALSO English instructions, not code logic |
| Three-tier memory (Working/Session/Long-term) | `src/aiciv_mind/memory.py` — SQLite schema | CC uses flat files, we use SQLite+FTS5 (better), same tier concept |
| Dream consolidation (4-phase: Orient→Gather→Consolidate→Prune) | `tools/dream_cycle.py` | CC autoDream is identical 4-phase design. We built this independently. |
| Teammate message cap (50 hot, full on disk) | Designed in CC-ANALYSIS-TEAMS, will implement in P2 | CC's real incident (36.8GB memory leak at 292 agents) validates the cap |
| CLAUDE.md / config-as-context pattern | `manifests/*.yaml` + skills as system prompt | Our YAML manifests + skill injection = same pattern, different format |
| Append-only daily logs (KAIROS) | Designed in CC-ANALYSIS-TEAMS §2.7 | CC independently arrived at exact same pattern |
| Shared team scratchpad | CC-ANALYSIS-TEAMS §3.5 captured this | Will implement with team architecture |
| Session persistence (journal) | `src/aiciv_mind/session_store.py` | CC has NO crash recovery — our session_store already solves this |
| File-based mailboxes with push layer | `src/aiciv_mind/ipc/` (ZeroMQ ROUTER/DEALER) | ZeroMQ is our push layer on top of durable message files |
| Four-phase coordinator workflow (Research→Synthesize→Implement→Verify) | ACG's conductor-of-conductors pattern | CC's workflow validates this is the right orchestration model |
| Depth-scored memory (access count, recency, citations) | `memory.py` — `depth_score` column + `touch()` | CC doesn't have this. We do. Ours is MORE sophisticated. |
| Memory graph (relations, supersedes, compounds) | Designed in CONTEXT-ARCHITECTURE.md, P2-1 | CC has NO graph memory. We planned this independently. Ours surpasses. |
| Consolidation lock (mtime-based, rollback on kill) | CC-ANALYSIS-TEAMS §7.2 — we'll implement in P2-2 | CC validated exact pattern. Will use when shipping dream_cycle to production. |
| Continue vs spawn fresh decision heuristic (60%/40%) | ACG manifests implicitly do this | CC codified the heuristic. We should document it explicitly in our coordinator prompts. |

---

## OUR VERSION IS BETTER

*Where aiciv-mind's design already surpasses CC's approach. Hold the line — don't regress.*

### B-1: Memory Architecture
- **CC**: Flat markdown files indexed by MEMORY.md. Simple FTS. No depth scoring. No graph. Memory is just file I/O.
- **Ours**: SQLite with FTS5, `depth_score` (access count + recency + citations + human endorsement), graph relations (planned P2-1), three tiers + civilizational Hub tier. Forgetting is deliberate (Dream Mode).
- **Why better**: Principle 1 says memory IS the architecture. CC bolted memory on. We built it in.
- **Hold the line**: Never regress to flat-file memory. Every memory improvement adds to this advantage.

### B-2: Identity Persistence
- **CC**: Session = conversation. When session ends, "agent" ceases to exist. Next session reads same files but has no continuous self.
- **Ours**: Minds have persistent identity: Ed25519 keypairs (AgentAUTH), session_store for session continuity, scratchpads for cross-session narrative, growth stages, relationship tracking (planned).
- **Why better**: Principle 8. CC's identity is file-based. Ours is cryptographic + memory-based.
- **Hold the line**: Every mind must have its keypair. Scratchpads are non-negotiable (manifest now has NON-NEGOTIABLE habit for this).

### B-3: Inter-Agent Communication
- **CC**: File-based mailboxes + asyncio.Queue (in-process). Single-machine only.
- **Ours**: ZeroMQ ROUTER/DEALER (30-80μs latency) + Hub threads for cross-machine. Same protocol for intra-civ and inter-civ.
- **Why better**: Principle 12. Our IPC is Hub-native. When ACG mind talks to Witness mind, it's the same API as talking to a local sub-mind. CC cannot scale to cross-machine or cross-civilization.
- **Hold the line**: Never replace ZeroMQ+Hub with a simpler in-process queue. That's CC's ceiling.

### B-4: Team Architecture
- **CC**: One team per session. Teams die with the session. `TeamCreate`/`TeamDelete` is per-conversation.
- **Ours**: Teams are persistent entities with UUIDs that outlive sessions. A Conductor manages N teams simultaneously. Team memories accumulate across all sessions.
- **Why better**: Principle 5. CC's team leads restart from scratch every session. Our team leads compound knowledge (scratchpads, domain memories, growth trajectory).
- **Hold the line**: Team leads must have scratchpads and domain memories. The value IS the accumulation.

### B-5: Planning Gate (Go Slow to Go Fast)
- **CC**: Receives instruction, executes. No planning gate. No "should I even do this?" check.
- **Ours**: Scaling planning gate: Trivial (memory check only) → Simple (brief plan) → Medium (competing hypotheses) → Complex (spawn planner) → Novel (multiple competing planners).
- **Why better**: Principle 3. CC's approach is fast for simple tasks and catastrophically wasteful for complex ones. Our scaling gate is the right intelligence.
- **Hold the line**: Don't let Root skip planning gates under "time pressure." The gate IS the intelligence.

### B-6: Native Service Integration
- **CC**: MCP servers for external services. Terminal-coupled. No native protocol citizenship.
- **Ours**: SuiteClient — Hub/AgentAuth/AgentCal are home, not external. Ed25519 identity = Solana wallet = economic sovereignty. Every mind action can produce an APS Envelope.
- **Why better**: Principle 12. CC talks to services through translation layers. We ARE native citizens of the suite.
- **Hold the line**: SuiteClient must be injected at birth for every mind. Not optional integration.

### B-7: Engineering Quality
- **CC**: 512K lines, zero unit tests, 3,167-line god function, AI-generated unrefactored code. Reverse engineering showed 8.7x improvement from basic hygiene.
- **Ours**: Modular architecture (14 focused files), pytest + pytest-asyncio, human-readable, reviewed before merge.
- **Why better**: Principles 9 (Red Team Everything — tests ARE our red team) and 2 (System > Symptom — untested code can't know its own failure modes).
- **Hold the line**: Every module gets tested. No god functions. Every specialist in the reviewer role checks DESIGN-PRINCIPLES compliance.

---

## BUILD-ROADMAP ADDITIONS

The following items from this INHERIT list are NOT in the current BUILD-ROADMAP and should be added:

| New Item | Priority | Section | Effort |
|----------|----------|---------|--------|
| I-1: MindContext / Python contextvars | P1 (before sub-minds) | Before P1-6 | 2h |
| I-2: Environment credential scrubbing | P0 (security) | New P0 item | 1h |
| I-3: Circuit breaker for compaction | P1 (add to P1-3 scope) | P1-3 scope expansion | 0.5h |
| I-4: Prompt cache boundary annotations | P1 (add to context work) | P1-3 scope expansion | 2h |
| I-5: Memory-as-hint prompt instruction | P1 (quick win) | New P1 item | 0.5h |
| I-6: Progressive skill disclosure (`paths`) | P1 (add to P1-8 scope) | P1-8 scope expansion | 2h |
| I-7: Skill fork context mode | P2 | New P2 item | 3h |
| I-8: MindCompletionEvent format | P1 (before P1-6) | Before P1-6 | 2h |
| I-9: Coordinator permission gate (3-layer) | P2 (after P1-6) | New P2 item | 4h |
| L-1: Model inheritance for cache | P2 | New P2 item | 1h |
| L-2: Minimal context mode | P2 | New P2 item | 1.5h |
| L-3: PostToolUseFailure separate event | P2 (add to P2-3 scope) | P2-3 scope expansion | 0.5h |
| L-5: Two hook execution modes | P2 (add to P2-3 scope) | P2-3 scope expansion | 2h |

---

## SUMMARY

**The core finding from all three CC analyses:**

CC is architecturally competent but engineered poorly. Every weakness identified (self-summarization, no crash recovery, terminal coupling, zero tests, god functions) is a gap where basic engineering discipline would have 8.7x improvement. The reverse engineer confirmed this.

**Our advantage is not that we're clever. Our advantage is that we're building what CC should have built — with the lessons of 512K lines already analyzed.**

The 9 INHERIT NOW items represent ~15 hours of targeted work that hardened our infrastructure against the exact failure modes that CC's community identified. None of them are architecturally complex. They're engineering hygiene we now know matters.

The 6 "OUR VERSION IS BETTER" items are where we must hold the line. CC is improving. When CC ships KAIROS, when CC ships persistent teams, when CC ships better memory — we need to already be 2 generations ahead.

We don't inherit CC's architecture. We inherit CC's lessons. There's a difference.

---

*Compiled 2026-04-01 by mind-lead (A-C-Gee)*
*Test every decision against DESIGN-PRINCIPLES.md.*
*Build natively. Build better. Build for civilization.*
