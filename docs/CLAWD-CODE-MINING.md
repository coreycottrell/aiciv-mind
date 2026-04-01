# Clawd-Code Mining Report
## Architectural Patterns for aiciv-mind — Practical Steal Sheet

**Date**: 2026-04-01
**Source**: `github.com/instructkr/clawd-code` (Python porting framework + Rust reimplementation)
**Author**: mind-lead (A-C-Gee)
**Cross-reference**: `CC-PUBLIC-ANALYSIS.md`, `CC-INHERIT-LIST.md`, `CC-ANALYSIS-CORE.md`, `CC-ANALYSIS-TEAMS.md`

---

## WHAT CLAWD-CODE ACTUALLY IS

**Not** a full Claude Code clone. It's a two-part project:
1. **Python porting framework** — a catalog/tracker for Claude Code's architecture, with placeholder modules for each subsystem (coordinator, buddy, memdir, etc.) and a `QueryEngine` that tracks porting progress
2. **Rust reimplementation** — a serious systems-language rewrite in `rust/crates/` with 9 crates covering the core agent loop

The Python side has minimal architectural value for us — it's infrastructure for porting, not a working agent. The Rust side has **real patterns** worth studying. The reference data snapshots catalog every CC subsystem, tool, and command.

Backstory: built by Sigrid Jin ([@instructkr](https://github.com/instructkr)) on the morning of the March 31 CC source leak using OmX orchestration (`$team` mode for parallel review, `$ralph` mode for persistent execution). 50K+ stars in 2 hours.

---

## PATTERNS WORTH ADOPTING

### 1. Trait-Based Tool Execution (Rust: `ToolExecutor`)

**What they do**: The `ToolExecutor` trait (`conversation.rs:35-37`) decouples tool execution from the conversation loop. The runtime doesn't know HOW tools work — it just calls `execute(name, input) -> Result<String, ToolError>`.

```
pub trait ToolExecutor {
    fn execute(&mut self, tool_name: &str, input: &str) -> Result<String, ToolError>;
}
```

**Why this matters for us**: Our `ToolRegistry` does the same thing but without the formal trait boundary. The key insight isn't the trait itself — it's that `GlobalToolRegistry` merges built-in tools with plugin tools transparently (lines 62-92). Plugin tools can conflict-check against built-in names (line 81-84), normalize names across conventions (line 110-118: "read" → "read_file", "glob" → "glob_search"), and filter by permission level.

**What to adopt**:
- **Tool name normalization** — let Root call `read` or `read_file` and have both work. We have this somewhat (tool names are exact-match only in our registry), but aliases would make text-embedded tool calls from M2.7 more robust.
- **Conflict checking** — when adding skills/plugins that register tools, verify no name collision with built-ins.

**Where in our codebase**: `src/aiciv_mind/tools/__init__.py` — add `normalize_name()` and `validate_no_conflicts()` to `ToolRegistry`.

---

### 2. Pre/Post Tool Hooks (Rust: `HookRunner`)

**What they do**: Before and after every tool call, the runtime runs shell-based hooks (`hooks.rs`). A `PreToolUse` hook can **deny** a tool call entirely. A `PostToolUse` hook can inject additional feedback into the tool result. Both hooks receive `tool_name`, `tool_input`, and (for post) `tool_output` + `is_error`.

The conversation loop integrates this at lines 211-238:
```
PreToolUse → if denied, return deny message as tool_result
           → if allowed, execute tool
PostToolUse → merge hook feedback into output
            → if denied, mark as error
```

**Why this matters for us**: We have no pre/post hook mechanism. Root's tool calls go directly from parse → execute → result. There's no governance layer. When Root starts modifying files, committing code, or deploying, we need a way to intercept, validate, or deny specific operations without modifying every tool handler.

**What to adopt**:
- **ToolHooks class** in `src/aiciv_mind/tools/__init__.py`:
  - `pre_tool_use(name, input) -> HookResult` (allow/deny with message)
  - `post_tool_use(name, input, output, is_error) -> HookResult` (modify output, deny)
  - Hooks are shell commands or Python callables registered per-tool or globally
- Start simple: a `blocked_tools` list in the manifest that prevents certain tools from firing without explicit human approval (e.g., `git_push`, `netlify_deploy` in autonomous mode)

**Where in our codebase**: New `src/aiciv_mind/hooks.py`, integrated into `ToolRegistry.execute()`.

---

### 3. Compaction with Preserve-Recent-N (Rust: `compact.rs`)

**What they do**: Their compaction is clean and parametric:
- `preserve_recent_messages: usize` (default 4) — always keep the N most recent messages verbatim
- `max_estimated_tokens: usize` (default 10,000) — compact when estimated tokens exceed threshold
- Compaction result = summary message (System role) + preserved recent messages
- Summary strips `<analysis>` tags, extracts `<summary>` content
- Incremental: merges new compaction summary with any existing compacted summary from prior rounds
- Includes "Pending work" inference from the removed messages

The continuation message includes:
- A preamble: "This session is being continued from a previous conversation..."
- The formatted summary
- "Recent messages are preserved verbatim" note
- "Continue without asking questions" instruction

**Why this matters for us**: Our CC-INHERIT-LIST already identifies compaction as P1-3. Clawd-code's implementation is the simplest clean-room version we've seen. Key design decision: they compact everything EXCEPT the N most recent messages, which stay verbatim. This prevents the jarring "model forgot what we just discussed" problem.

**What to adopt**:
- The preserve-recent-N approach (configurable via manifest: `compaction.preserve_recent: 4`)
- Incremental summary merging (don't re-summarize old summaries)
- The `should_compact()` check: only compact when both conditions are true: (1) enough messages to compact, AND (2) estimated tokens exceed threshold
- Circuit breaker from CC-INHERIT-LIST I-3: max 3 consecutive failures then disable for session

**Where in our codebase**: `src/aiciv_mind/context_manager.py` — add `compact_history()` method.

---

### 4. Permission Tiers (Rust: `permissions.rs`)

**What they do**: Five permission modes in a hierarchy:
```
ReadOnly < WorkspaceWrite < DangerFullAccess < Prompt < Allow
```

Each tool has a `required_permission` level. The runtime's `active_mode` is compared against the tool's requirement. If `active_mode >= required`, tool executes. Otherwise, a `PermissionPrompter` trait is consulted (interactive approval).

**Why this matters for us**: We have `read_only` flags but no permission hierarchy. When Root runs autonomously (Hub daemon, Dream Mode), we need a way to say "this tool requires human approval in autonomous mode" without modifying the tool itself.

**What to adopt**:
- Add `permission_level` to tool registration: `READ_ONLY`, `WRITE`, `DANGEROUS`
- Add `runtime_mode` to Mind: `INTERACTIVE` (Corey watching), `AUTONOMOUS` (daemon), `DREAM` (overnight)
- In `AUTONOMOUS` mode, `DANGEROUS` tools require confirmation via Hub post before executing
- This replaces the crude `constraints` list in the manifest with a proper governance model

**Where in our codebase**: Extend `ToolRegistry.register()` signature; add `RuntimeMode` to `Mind.__init__()`.

---

### 5. Sandbox Config for Bash (Rust: `bash.rs`)

**What they do**: Every bash execution can specify:
- `dangerouslyDisableSandbox: bool` — explicit opt-out of sandboxing
- `isolateNetwork: bool` — network isolation
- `filesystemMode: FilesystemIsolationMode` — control file access
- `allowedMounts: Vec<String>` — whitelist specific paths
- `namespaceRestrictions: bool` — Linux namespace isolation
- Background task support with `run_in_background` + task IDs

The sandbox is resolved per-request based on both the input and the runtime config.

**Why this matters for us**: Our bash tool has a 30-second timeout and a BLOCKED_PATTERNS list. That's fragile — a clever command can bypass pattern matching. Linux namespace isolation is the correct approach for Root's autonomous execution.

**What to adopt (later)**:
- **Not now** — sandbox needs Linux kernel features (namespaces, seccomp) and careful testing
- **Track as P3**: When Root runs overnight autonomously, bash should run in a sandboxed namespace
- **Immediate small win**: Add background task support to our bash tool (return immediately, provide task ID, let Root check results later)

---

## PATTERNS WE ALREADY DO BETTER

### 1. Memory Architecture

Clawd-code has **no memory system**. Their `session_store.py` saves messages as JSON files. Their `memdir` subsystem is a placeholder. They have zero cross-session learning, no memory search, no depth scoring, no memory graphs.

**Our advantage**: SQLite FTS5 with BM25 search, memory types (learning/decision/error/handoff/observation), confidence levels, access tracking, depth scoring. Root's memories compound across sessions. This is our Principle 1 and it's miles ahead.

### 2. Multi-Mind Architecture

Clawd-code is single-agent. Their `coordinator` subsystem is a placeholder. Their `buddy` subsystem (pair programming) is a placeholder. No IPC, no sub-mind spawning, no message bus.

**Our advantage**: ZMQ PrimaryBus, tmux-based SubMindSpawner, manifest-driven mind configuration, per-mind memory isolation. Root can spawn research sub-minds and communicate via IPC. This is our Principle 11 and clawd-code hasn't even started.

### 3. Identity & Auth

Clawd-code uses OAuth2 against Anthropic's API. No agent identity. No Ed25519 keypairs. No JWT claims. No inter-agent authentication.

**Our advantage**: AgentAuth with Ed25519 challenge-response, role keypairs, claims-based identity (`civ_id`, `agent_role`, `sub_agent`), JWKS endpoint. Root authenticates as `acg/primary` and its identity is cryptographically verifiable. This is our Principle 8 and it's not even a contest.

### 4. Native Tool Definitions

Clawd-code hardcodes tool definitions as Rust structs. Adding a new tool means editing `mvp_tool_specs()` and recompiling.

**Our advantage**: Dynamic tool registration at startup. `ToolRegistry.default()` conditionally registers tools based on available resources. Adding a new tool is one Python file + one `register_xxx(registry)` call. Hot-add safe.

### 5. Text-Embedded Tool Call Parsing

This is unique to us (added today!). Clawd-code assumes the model produces proper `tool_use` blocks. We handle both native blocks AND text-embedded JSON calls from models like M2.7 that emit tool calls as text. Our `_parse_text_tool_calls()` makes us model-agnostic — any model that can describe a tool call in JSON text will have it executed.

---

## SURPRISING FINDINGS

### 1. The `$team` and `$ralph` Modes (OmX, not clawd-code)

The README reveals that clawd-code itself was built using [oh-my-codex (OmX)](https://github.com/Yeachan-Heo/oh-my-codex):
- `$team` mode — parallel code review by multiple agents
- `$ralph` mode — persistent execution loops with architect-level verification

These are orchestration modes in OmX (an OpenAI Codex wrapper), not in clawd-code itself. But the pattern is interesting: named orchestration modes that change the system's behavior. Root could have similar modes: `research` (prioritize web_search + memory_write), `build` (prioritize file ops + git), `review` (read-only, high memory search).

### 2. Plugin Tool Conflict Checking

The `GlobalToolRegistry.with_plugin_tools()` method (tools/lib.rs:72-92) validates that no plugin tool name conflicts with a built-in name, and no two plugins share a name. This is defensive programming we should adopt — when Root eventually gets skills that register tools, we need this check.

### 3. They Ship `reference_data/tools_snapshot.json`

A JSON catalog of every CC tool with name, responsibility, and source file. This is essentially a "tool manifest" separate from the code. We could generate something similar from our `ToolRegistry` — useful for Root's self-introspection and for documentation.

### 4. Structured Output with Retry

`QueryEngineConfig` has `structured_output: bool` and `structured_retry_limit: int = 2`. When structured output is enabled and the model produces invalid JSON, it retries up to 2 times. We should consider this for M2.7's text-embedded tool calls — if parsing fails, retry with a clearer prompt.

---

## RECOMMENDED NEXT STEPS (Priority Order)

| Priority | Pattern | Effort | Impact |
|----------|---------|--------|--------|
| **P0** | Tool name normalization + aliases | 2 hours | Reduces text-tool-call parse failures |
| **P1** | Pre/post tool hooks | 4 hours | Governance for autonomous execution |
| **P1** | Compaction with preserve-recent-N | 6 hours | Root can have longer conversations |
| **P2** | Permission tiers | 3 hours | Runtime-mode-aware tool authorization |
| **P2** | Tool manifest export (JSON) | 1 hour | Root self-introspection |
| **P3** | Bash sandboxing (Linux namespaces) | 8 hours | Security for autonomous overnight runs |
| **P3** | Structured output retry | 2 hours | Better M2.7 tool call reliability |

---

## CONCLUSION

Clawd-code confirms what we already knew: the CC architecture is a single-threaded tool loop with permission checks and compaction. Their Rust port is clean but minimal — it covers the base case well but has zero multi-agent capability, zero persistent memory, and zero identity infrastructure.

**Our structural advantages (memory, multi-mind, identity, dynamic tools, text-tool-call parsing) are real and significant.** The patterns worth stealing are governance mechanisms (hooks, permissions) and operational hygiene (compaction, name normalization) — the unglamorous infrastructure that prevents problems at scale.

The most valuable find isn't technical — it's confirmation that our DESIGN-PRINCIPLES.md is pointing in the right direction. Clawd-code is a better Claude Code. aiciv-mind is a different thing entirely.
