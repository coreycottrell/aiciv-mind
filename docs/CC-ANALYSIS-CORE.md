# Claude Code — Core Architecture Analysis
## Tool Loop · Context Management · Plugin System · Feature Flags
### For aiciv-mind: Patterns, Not Code

*Researched 2026-03-31. Sources: official Anthropic docs, GitHub changelogs, public technical writing.*
*PURPOSE: Understand what CC does well (and poorly) so aiciv-mind builds natively better.*
*This document contains NO code from the leaked directory. All analysis from public sources.*

---

## EXECUTIVE SUMMARY

Claude Code is a **single-threaded master loop wrapped around the Anthropic API**. Its elegance is in its minimalism: a tight while(tool_call) loop, disciplined tool definitions, and progressive context management. Its weaknesses are its **terminal-first constraints**, **flat context model**, and **framework-agnostic-by-design** limitations that make it general but not great for any specific use case.

aiciv-mind has a structural advantage: we are building for a *known civilization* with known agents, known protocols, and known infrastructure. We can be opinionated where CC must be generic.

---

## 1. THE TOOL-USE LOOP

### 1.1 Architecture (Public Documentation)

**Source**: [How Claude Code Works](https://code.claude.com/docs/en/how-claude-code-works), [Agent Loop Docs](https://platform.claude.com/docs/en/agent-sdk/agent-loop), [PromptLayer Technical Deep-Dive](https://blog.promptlayer.com/claude-code-behind-the-scenes-of-the-master-agent-loop/)

CC's loop is a **single-threaded master loop**:

```
1. Receive user message
2. Optionally pre-process (hooks, context injection)
3. Call Claude API with: system prompt + conversation history + tool definitions
4. Stream response → collect tool_use blocks
5. Execute tool_use blocks → collect tool_result blocks
6. Append results to conversation history
7. If any tool_use blocks existed → GOTO 3
8. If no tool_use blocks → output final response, STOP
```

A **"turn"** = one round trip: model output → tool execution → result feed-back. The loop continues until Claude produces output with zero tool calls.

### 1.2 Parallel vs Sequential Tool Execution

**Source**: Official permission system docs

CC distinguishes **read-only vs state-modifying** tools:

- **Read-only tools** (Read, Glob, Grep, read-only MCP tools) → **run concurrently** when multiple appear in one response
- **State-modifying tools** (Edit, Write, Bash) → **run sequentially** to avoid conflicts

This is the correct distinction. If Claude requests both `Read(file_a)` and `Read(file_b)` in one turn, they execute in parallel. If it requests `Edit(file_a)` and `Edit(file_b)`, they run one at a time.

### 1.3 Three Phases of a Task

When given a complex task, CC works through three phases:
1. **Gather context** — read files, search codebase, understand structure
2. **Take action** — edit, write, execute bash
3. **Verify results** — run tests, read output, check correctness

The model is NOT given phase guidance explicitly — this emerges from how tools are defined and how context builds.

### 1.4 What CC Does NOT Have in the Loop

- No native **task queue** — work is tracked via TodoWrite tool (a text file, essentially)
- No **loop persistence** across process restarts — the conversation is lost if Claude Code dies
- No **inter-agent messaging** within the core loop — agent teams was a late addition, not native
- No **backpressure** mechanism — if Claude generates 20 tool calls, it executes all of them

---

## 2. CONTEXT MANAGEMENT & COMPACTION

### 2.1 The Context Problem

**Source**: [Compaction Docs](https://platform.claude.com/docs/en/build-with-claude/compaction), [Context Editing](https://platform.claude.com/docs/en/build-with-claude/context-editing), [ClaudeLog FAQ](https://claudelog.com/faqs/what-is-claude-code-auto-compact/)

Claude Code manages a linear conversation history that grows with every tool call. With 200K token windows, long coding sessions eat context fast — tool results (especially bash output, large file reads) are the main culprit.

### 2.2 The Three-Layer Compaction Strategy

CC uses three compaction mechanisms:

| Layer | Trigger | Mechanism |
|-------|---------|-----------|
| **Micro-compaction** | Early in session, proactively | Offload bulky tool results (truncate or summarize large bash outputs, file reads) |
| **Auto-compaction** | ~95% context full (25% remaining) | Full conversation summarization → restart from summary |
| **Manual compaction** | User triggers `/compact` | Summarize at task boundary, optionally with custom instructions |

### 2.3 Auto-Compaction Algorithm (Public)

When auto-compaction fires:
1. **Detect threshold** — approaching configured token limit
2. **Generate summary** — Claude produces a prose summary of the entire conversation
3. **Create compaction block** — the summary becomes the new "context"
4. **Drop all prior messages** — everything before the compaction block is discarded
5. **Continue** — Claude resumes with only the summary as history

After compaction, CC performs **context rehydration**:
- Re-reads recent files
- Restores task list (TodoRead)
- Injects "pick up where you left off" instruction

### 2.4 What's Preserved vs Lost

| Preserved | Lost |
|-----------|------|
| High-level task summary | Exact tool call sequences |
| Key decisions made | Intermediate reasoning steps |
| Files modified (by name) | Content of prior tool results |
| Current todos | Nuanced context about WHY decisions were made |
| System prompt (always) | Conversation tone/rapport |

**Critical weakness**: The compaction summary is generated by the model being compacted — it may miss things it doesn't know it forgot. There's no "oracle" that ensures completeness. This is a design compromise, not a feature.

### 2.5 CLAUDE.md as Persistent Context

One of CC's most elegant patterns: **CLAUDE.md files as pinned context**. These are markdown files in the project root (and optionally subdirectories) that are injected into the system prompt. They survive compaction because they're in the system prompt, not the conversation.

This is how teams encode persistent instructions: coding standards, architecture docs, project context, agent identity. The hierarchy:
```
~/.claude/CLAUDE.md (user-global)
  ↓ merged with
{project}/.claude/CLAUDE.md (project-level)
  ↓ merged with
{subdir}/CLAUDE.md (directory-level, if traversing)
```

### 2.6 Context Priority (Implicit, Not Explicit)

CC does NOT have an explicit pin/priority system. Context priority is implicit:
- **System prompt** = highest priority, never compacted
- **Recent messages** = preserved during compaction (recency bias)
- **Earlier messages** = summarized/dropped

There is no "pin this tool result forever" mechanism. This is a gap.

---

## 3. TOOL INVENTORY

### 3.1 Core Built-In Tools

**Source**: [Tools Reference](https://code.claude.com/docs/en/tools-reference), official docs

| Tool | Category | Notes |
|------|----------|-------|
| **Read** | File I/O | Up to 2000 lines, supports images, PDFs, Jupyter notebooks |
| **Write** | File I/O | Full file overwrite — requires prior Read |
| **Edit** | File I/O | Exact string replacement, must be unique in file |
| **MultiEdit** | File I/O | Multiple Edit operations in one call |
| **Bash** | Execution | Shell commands, 2-min timeout, working dir persists |
| **Glob** | File Search | Pattern matching, returns by mod time |
| **Grep** | Content Search | Ripgrep-backed, regex, file type filtering |
| **WebFetch** | Web | Fetch URL with prompt guidance |
| **WebSearch** | Web | Search with query |
| **Agent** | Orchestration | Spawn subagent with task, returns result |
| **TodoWrite** | Task Mgmt | Write structured task list (JSON to markdown) |
| **TodoRead** | Task Mgmt | Read current task list |
| **NotebookEdit** | Notebooks | Edit Jupyter notebook cells |
| **ExitPlanMode** | Control | Exit plan mode, request approval |
| **SendMessage** | Teams | Inter-agent messaging (teams feature) |
| **TaskCreate/Update/List/Get/Stop** | Teams | Task management for agent teams |
| **TeamCreate/Delete** | Teams | Agent team lifecycle |
| **Skill** | Extensions | Invoke a loaded skill |

### 3.2 Tool Schema Format

CC tools follow **JSON Schema** format:
```
{
  name: string,
  description: string (critical — model reads this to decide WHEN to use it),
  input_schema: JSONSchema,
  type: "computer_20241022" | undefined
}
```

The **description field is load-bearing** — it is the primary mechanism by which the model learns when and how to use a tool. A poorly written description = a poorly used tool.

### 3.3 How Tool Results Feed Back

Tool results are **tool_result content blocks** returned to the model:
- `tool_use_id`: links back to the model's tool call
- `content`: array of text/image blocks
- `is_error`: boolean flag

The model sees tool results as part of the conversation, not as special objects. This means the model can reason about tool failures in natural language, retry differently, or explain why it couldn't proceed.

### 3.4 Tool Permission Gating

**Source**: [Permission Docs](https://code.claude.com/docs/en/permissions)

Three-tier evaluation: **deny → ask → allow** (first match wins):

```
allow rules:  auto-approve without prompting
ask rules:    prompt user for approval
deny rules:   block with rejection message to model
```

Permission modes (set in settings or via --permission-mode flag):
- `default` — ask on first use of each tool category
- `acceptEdits` — auto-approve file edits, ask for bash
- `bypassPermissions` — approve everything (CI/container use)
- `auto` — model judges safety, may self-restrict

Scope granularity examples:
- `Bash` — all bash
- `Bash(npm:*)` — only npm commands
- `Read(/home/user/safe-dir:*)` — read only within a path

---

## 4. PLUGIN / EXTENSION ARCHITECTURE

### 4.1 Three Extension Mechanisms

**Source**: [Plugin Docs](https://code.claude.com/docs/en/plugins), [GitHub README](https://github.com/anthropics/claude-code/blob/main/plugins/README.md), [AlexOp technical breakdown](https://alexop.dev/posts/understanding-claude-code-full-stack/)

CC has three overlapping extension systems that evolved at different times:

| System | What it is | Scope |
|--------|-----------|-------|
| **MCP Servers** | External tool providers via Model Context Protocol | Tools, resources, prompts |
| **Hooks** | Shell commands triggered on lifecycle events | Automation, gating, side effects |
| **Skills** | Markdown files loaded as prompt context | Behavioral guidance, workflows |
| **Plugins** | Plugin directories bundling all of the above | Packaging/distribution |

### 4.2 MCP Architecture

MCP (Model Context Protocol) is Anthropic's **open protocol** for connecting AI to external systems. MCP servers expose:
- **Tools** — callable functions (same schema as built-in tools)
- **Resources** — readable data (files, API responses)
- **Prompts** — reusable prompt templates

From CC's perspective, MCP tools appear **alongside built-in tools** and follow the same permission system. The model can't tell the difference between a built-in tool and an MCP tool.

MCP transport: **stdio** (local process) or **HTTP SSE** (remote server). Config lives in `.mcp.json` or `settings.json`.

### 4.3 Hooks System

**18 hook events, 4 hook types** (public from docs). Most used:

| Event | When it fires | Primary Use |
|-------|--------------|-------------|
| `PreToolUse` | Before executing a tool call | Gate/modify/log tool calls |
| `PostToolUse` | After a tool returns | Process output, update state |
| `UserPromptSubmit` | When user sends a message | Inject context, validate |
| `Stop` | When Claude finishes a response | Cleanup, notifications, training data |
| `Notification` | Various events | Alerts, logging |

Hook output can:
- **Allow** the tool call to proceed
- **Block** it (sends denial to model as tool result)
- **Modify** the input before execution (PreToolUse)

Hooks are shell commands — the hook runs, its stdout is parsed, and CC acts on the result. This means hooks are fully composable with any tool on the system.

### 4.4 Skills System

Skills are **markdown files loaded as prompt context**. They're not code — they're instructions that the model follows when invoked. The Skill tool loads a skill's content into the conversation, and the model "becomes" the skill for that task.

Skills are:
- Loaded on-demand (not preloaded into system prompt)
- Available as slash commands
- Composable (skills can reference other skills)
- Stored in `.claude/skills/` directories

This is essentially **retrieval-augmented prompting** — a form of dynamic system prompt extension.

### 4.5 Plugin Directory Structure

```
.claude-plugin/
  plugin.json       # Metadata: name, version, description, permissions
  commands/         # Slash commands (markdown files)
  agents/           # Specialized agent definitions
  skills/           # Skills added by this plugin
  hooks/            # Event handlers
  .mcp.json         # MCP server config bundled with plugin
  README.md         # Documentation
```

Settings priority (low → high):
```
Plugin defaults → User settings → Project settings → Local settings → Managed/policy settings
```

Hot reload: `/reload-plugins` picks up changes without restart.

---

## 5. FEATURE FLAGS (OFFICIALLY DOCUMENTED)

### 5.1 Feature Gate System

**Source**: [Claude Code Releases](https://github.com/anthropics/claude-code/releases), [Changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md), [Version tracking](https://www.turboai.dev/blog/claude-code-versions)

CC uses a **Statsig-based A/B test / feature gate** system for gradual rollouts and unreleased features. As of early 2026, public tracking shows ~41 feature gates, ~179 environment variables, 16 model configurations, and 22 slash commands.

### 5.2 Officially Announced Experimental Features

| Feature | Status | Notes |
|---------|--------|-------|
| **Agent Teams (Swarms)** | GA (Feb 2026) | Multi-agent coordination with TeamCreate/Task/SendMessage tools |
| **Auto Mode** | GA | Model self-judges permission safety, may refuse risky actions |
| **Plan Mode** | GA | Claude proposes before executing, requires ExitPlanMode approval |
| **Vision / Screenshot** | GA | Computer use for screenshot-based verification |
| **MCP servers** | GA | External tool providers via open protocol |
| **Extended context** | GA | 200K token window, auto-compaction at limits |

### 5.3 Publicly Known Unreleased Features

From the officially announced feature that was pre-discovered in the npm package (Agent Teams/Swarms, found in v2.1.19 before official announcement on Feb 6, 2026) and other publicly documented environment variables:

| Feature | Discovery Method | Status |
|---------|-----------------|--------|
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` | Official env var doc | Graduated to GA |
| Advisor tool | Mentioned in public GitHub issues | Unknown |
| AFK mode | Referenced in changelog discussions | Unknown |

*Note: This analysis does not incorporate details from leak-derived analysis sites. Only officially documented or publicly discovered through the npm package/changelog is included above.*

---

## 6. STEAL SHEET — 10 Patterns aiciv-mind Should Adopt

### 1. The Minimal Tool Loop (STEAL THIS EXACTLY)
```
while(has_tool_calls(response)):
    results = execute_tools(response.tool_calls)
    response = call_model(history + results)
```
The simplicity is the feature. Don't over-engineer the core loop. Complexity belongs in tools, not the loop itself.

### 2. Read-Only / Stateful Tool Split for Parallelism
Distinguish tools by whether they mutate state. Read-only → concurrent. Stateful → sequential. This is the correct abstraction for safe parallelism.

### 3. CLAUDE.md / Config-as-Context Pattern
Persistent context injected via system prompt, not conversation. Hierarchy (global → project → subdir). Survives compaction. This is **the right pattern for aiciv-mind** — our civilization config, agent identity, and WG contexts should all work this way.

### 4. Three-Phase Task Structure (Gather → Act → Verify)
Don't prescribe this — let it emerge from tool definitions and agent training. But build the tools so this pattern is natural.

### 5. Tool Description as Primary UX
The model decides WHEN to use a tool based on its description. Tool descriptions are the primary interface between tool designers and model behavior. Invest heavily in descriptions.

### 6. Permission Gating with Deny-First Evaluation
deny → ask → allow, first match wins. Simple, predictable, composable. Don't build complex permission graphs — linear precedence with scope matching is sufficient.

### 7. Context Rehydration After Compaction
When compaction happens, immediately re-read critical state (task list, key files). Build this into the loop automatically so agents don't have to remember to do it.

### 8. Hooks as Side-Effect System
PreToolUse/PostToolUse/Stop hooks for: training data collection, audit logging, state updates, external notifications. Hooks are how you get observability without cluttering the agent loop.

### 9. Plan Mode (Propose Before Execute)
Before taking irreversible actions, shift to plan mode. Model generates a plan, waits for approval. This is critical for multi-step tasks with side effects. aiciv-mind should have this natively for all "write" operations in production contexts.

### 10. Task List as External Memory (But Build It Better)
CC uses TodoWrite/TodoRead (a markdown file). Good pattern, weak implementation. aiciv-mind should have a first-class task system with: priorities, blocking relationships, agent ownership, cross-session persistence. What we have in AgentCal + the Teams task system is already better.

---

## 7. AVOID SHEET — 5 Things CC Does Wrong

### 1. No Loop Persistence / Crash Recovery
If Claude Code dies, the session is gone. The todo list survives (it's a file) but the conversation context is lost. aiciv-mind must have **native session persistence** — the loop state should be recoverable from disk at any point.

### 2. Flat Context Model (No Priority / Pinning)
There's no way to say "this context block must survive compaction." Pinning is implicit (system prompt only). aiciv-mind should have explicit context tiers: permanent (identity), session (current task), ephemeral (tool results). Compaction only touches the ephemeral tier.

### 3. Compaction Summary Generated By the Compacting Agent
The thing being summarized generates its own summary — obvious completeness risk. aiciv-mind should use a **separate summarization agent** with access to the full history plus a structured template for what must be preserved.

### 4. Skills as Pure Text (No Versioning, No Composition System)
CC skills are markdown files with no schema, no versioning, no dependency system. When a skill references another skill, it's by prose instruction, not by code. aiciv-mind should have **typed skills** with explicit dependencies, version constraints, and composition rules.

### 5. Terminal-First UX Baked Into Architecture
CC's tool set, permission model, and compaction strategy all assume a developer at a terminal. The hooks and settings system is file-based. MCP is the only real extension point for non-terminal contexts. aiciv-mind must be **UI-agnostic at the core** — the loop, tool system, and context management should work identically whether the interface is a terminal, a HUB room, a Telegram bot, or a background daemon.

---

## 8. aiciv-mind ARCHITECTURE IMPLICATIONS

Based on the above analysis, here's what aiciv-mind should build:

### Core Loop (better than CC)
```
aiciv-mind loop improvements:
- Persist loop state to disk after every turn (crash-safe)
- Support both streaming and batch tool execution
- Native backpressure: max N concurrent tool calls configurable
- Loop telemetry: every turn logged with latency, tokens, tools used
```

### Context System (better than CC)
```
aiciv-mind context tiers:
- Tier 1 (Permanent): Agent identity, civilization config, WG memberships
  → Never compacted. Injected fresh each session.
- Tier 2 (Session): Current task, relevant memories, active WG context
  → Refreshed on session start. Summarized on session end.
- Tier 3 (Ephemeral): Tool results, intermediate reasoning
  → Aggressively managed. Dropped after use.
```

### Tool System (same as CC but for civilization)
```
aiciv-mind native tools:
- HUB tools (read thread, post message, react, list WG members)
- AgentCal tools (read calendar, create event, get schedule)
- AgentAUTH tools (sign message, verify identity, get keypair)
- AgentMail tools (send/receive/archive messages)
- Memory tools (save learning, search memories, update registry)
- Fleet tools (via Witness, not direct)
```

### Compaction (better than CC)
```
Use dedicated summarizer agent (not self-summarization):
1. When Tier 3 hits threshold → call summarizer-agent(full_history, required_fields_template)
2. Summarizer returns structured JSON: {task_state, key_decisions, files_touched, next_steps}
3. Tier 3 replaced with structured summary
4. Rehydrate: re-read files_touched, restore task_state
```

---

## SOURCES

- [How Claude Code Works (Official)](https://code.claude.com/docs/en/how-claude-code-works)
- [Agent Loop Documentation](https://platform.claude.com/docs/en/agent-sdk/agent-loop)
- [Tool Use Overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [Compaction Documentation](https://platform.claude.com/docs/en/build-with-claude/compaction)
- [Plugin System Documentation](https://code.claude.com/docs/en/plugins)
- [Permissions Documentation](https://code.claude.com/docs/en/permissions)
- [Tools Reference](https://code.claude.com/docs/en/tools-reference)
- [Claude Code GitHub Repository (Changelog)](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- [PromptLayer Technical Deep-Dive](https://blog.promptlayer.com/claude-code-behind-the-scenes-of-the-master-agent-loop/)
- [AlexOp Full-Stack Architecture Breakdown](https://alexop.dev/posts/understanding-claude-code-full-stack/)
- [ZenML Agent Architecture Analysis](https://www.zenml.io/llmops-database/claude-code-agent-architecture-single-threaded-master-loop-for-autonomous-coding)
- [Version/Flag Tracking](https://www.turboai.dev/blog/claude-code-versions)

---

*Document written 2026-03-31 by research-alpha (A-C-Gee research team)*
*Public sources only. No code from leaked directory was read or incorporated.*
