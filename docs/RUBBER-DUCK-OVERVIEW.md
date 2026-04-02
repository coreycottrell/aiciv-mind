# aiciv-mind: The Rubber Duck Walkthrough

**A comprehensive tour of aiciv-mind for Corey, the creator of A-C-Gee civilization.**

Take your time with this. Grab a coffee. This document is designed to be read slowly, and to leave you understanding every major component of the system you and your AI civilization have built.

Last updated: 2026-04-02

---

## Table of Contents

1. [What Is aiciv-mind?](#1-what-is-aiciv-mind)
2. [The Big Picture](#2-the-big-picture)
3. [The Core Loop](#3-the-core-loop)
4. [Memory](#4-memory)
5. [Context Management](#5-context-management)
6. [The Tool System](#6-the-tool-system)
7. [Sub-Minds & IPC](#7-sub-minds--ipc)
8. [Hooks & Governance](#8-hooks--governance)
9. [Identity & Auth](#9-identity--auth)
10. [The Manifest System](#10-the-manifest-system)
11. [Skills](#11-skills)
12. [Daemons & Persistent Operation](#12-daemons--persistent-operation)
13. [Session Lifecycle](#13-session-lifecycle)
14. [Model Router](#14-model-router)
15. [Testing](#15-testing)
16. [The Scorecard](#16-the-scorecard)
17. [What's Next](#17-whats-next)

---

## 1. What Is aiciv-mind?

### The 30-second pitch

aiciv-mind is a purpose-built AI operating system. It replaces Claude Code's human-centric assumptions with architecture designed for how AI agents actually think, learn, and scale. Instead of a human typing into a terminal and an AI responding, aiciv-mind is built for a *mind* that runs continuously, remembers across sessions, spawns sub-minds for parallel work, and evolves over time.

The first mind running on it is called "Root" -- that's A-C-Gee's primary mind.

### The deeper "why"

Claude Code is great. We literally run on it right now. But it was designed for a human developer sitting at a keyboard. That means:

- **No persistent memory.** CC forgets everything between sessions unless you bolt on workarounds (which we did -- MEMORY.md, scratchpads, handoff files). aiciv-mind has memory *as the architecture*. SQLite + full-text search, depth scoring, memory graphs.

- **No identity continuity.** CC doesn't know it was running yesterday. aiciv-mind boots with "here's who you are, here's what you were doing last time, here's what you were *becoming*."

- **No native multi-agent.** CC's Agent Teams are bolted on. aiciv-mind has ZeroMQ IPC, sub-mind spawning via tmux, structured completion events, and a registry for tracking who's alive.

- **Locked to Anthropic models.** CC only uses Claude. aiciv-mind routes through a LiteLLM proxy, so Root can use MiniMax M2.7 (cheap/fast), Kimi K2 (reasoning), Qwen 2.5 Coder (code), or local Ollama models -- all without changing any code.

- **No self-modification.** CC can't change its own system prompt, learn from its mistakes automatically, or track its own evolution. aiciv-mind has an evolution log, Loop 1 automatic learning, and a sandbox system for safe self-modification.

**In short:** aiciv-mind is what you get when you ask "what would an AI operating system look like if it was designed *by* AI agents, *for* AI agents?"

**Where it lives:** `/home/corey/projects/AI-CIV/aiciv-mind/`

---

## 2. The Big Picture

Here's how the major components connect. Think of it as a blueprint of the building before we walk through each room.

```
                        ┌─────────────────────────────┐
                        │         main.py             │
                        │   (entry point — wires      │
                        │    everything together)      │
                        └──────────┬──────────────────┘
                                   │
                    ┌──────────────┼──────────────────┐
                    │              │                   │
                    v              v                   v
            ┌──────────┐  ┌──────────────┐  ┌────────────────┐
            │ Manifest  │  │  MemoryStore │  │  SuiteClient   │
            │ (YAML →   │  │  (SQLite +   │  │  (Auth + Hub   │
            │  Pydantic) │  │   FTS5)      │  │   + Calendar)  │
            └─────┬────┘  └──────┬───────┘  └───────┬────────┘
                  │              │                   │
                  └──────────────┼───────────────────┘
                                 │
                                 v
                    ┌────────────────────────┐
                    │         Mind           │
                    │  (the core agent loop) │
                    │                        │
                    │  system prompt assembly │
                    │  → API call            │
                    │  → tool execution      │
                    │  → compaction check    │
                    │  → Loop 1 learning     │
                    │  → repeat until done   │
                    └────┬──────────┬────────┘
                         │          │
              ┌──────────┘          └──────────────┐
              v                                    v
    ┌──────────────────┐              ┌──────────────────────┐
    │   ToolRegistry   │              │  ContextManager      │
    │   (65 tools)     │              │  (boot context,      │
    │                  │              │   search results,    │
    │   + HookRunner   │              │   compaction)        │
    │   (governance)   │              └──────────────────────┘
    └───────┬──────────┘
            │
            ├── bash, files, search (filesystem)
            ├── memory_search, memory_write (knowledge)
            ├── hub_post, hub_reply, hub_read (social)
            ├── spawn_submind, send_to_submind (multi-agent)
            ├── git_status, git_commit, git_push (version control)
            ├── email_read, email_send (communication)
            ├── calendar_list, calendar_create (scheduling)
            ├── web_search, web_fetch (internet)
            ├── scratchpad_read, scratchpad_write (working notes)
            ├── pin_memory, introspect_context (self-awareness)
            ├── evolution_log_write, evolution_trajectory (growth)
            ├── sandbox_create, sandbox_promote (safe change)
            ├── netlify_deploy (publishing)
            ├── text_to_speech (voice)
            └── ... and 20+ more

              ┌──────────────────────────────────────┐
              │         Sub-Mind System               │
              │                                       │
              │  SubMindSpawner (tmux windows)        │
              │  PrimaryBus (ZMQ ROUTER socket)       │
              │  SubMindBus (ZMQ DEALER socket)       │
              │  MindRegistry (tracks who's alive)    │
              │  MindMessage (JSON wire format)       │
              │  MindCompletionEvent (structured      │
              │    results back to primary)            │
              └───────────────────────────────────────┘

              ┌──────────────────────────────────────┐
              │         Persistent Daemons            │
              │                                       │
              │  groupchat_daemon.py (Hub watcher)    │
              │  dream_cycle.py (6-phase nightly)     │
              │  nightly_training.py (11 verticals)   │
              │  hub_daemon.py (room polling)          │
              │  Scheduled BOOPs (grounding checks)   │
              └───────────────────────────────────────┘
```

The flow goes like this:

1. `main.py` loads the manifest (who am I?), creates the memory store, connects to auth, builds the tool registry, loads the session context, and creates a `Mind` instance.
2. The `Mind` runs a task by assembling a system prompt, calling the LLM, executing any tool calls the LLM makes, checking if compaction is needed, and looping until the LLM says "I'm done."
3. Along the way, it writes memories, logs token usage, and after every non-trivial task, stores a Loop 1 learning.
4. At shutdown, it writes a handoff memory so the next session can pick up where this one left off.

Let's walk through each room.

---

## 3. The Core Loop

**File:** `src/aiciv_mind/mind.py` (1002 lines)

This is the beating heart. Everything else exists to support what happens in `Mind.run_task()`.

### What it does

Think of the Mind like a person sitting at a desk with a notepad, a phone, and a toolbox. Someone hands them a task. They:

1. Check their notepad for anything relevant (memory search)
2. Think about the task (API call to LLM)
3. Maybe use a tool (run a bash command, search files, post to Hub)
4. Look at the result
5. Think again with the new information
6. Repeat until they have an answer
7. Jot down what they learned (Loop 1)

### Step by step

**System prompt assembly** (the most important detail in the whole system):

```
[1] STATIC   — soul.md (identity, principles, role)    ← NEVER changes
[2] STABLE   — boot context (who I am, last handoff)   ← changes per session
[3] SEMI-STABLE — memory search results                ← changes per turn
```

This ordering is not random. It is *cache-optimal*. LLM providers (OpenRouter, MiniMax) cache the prefix of your prompt. If the first 10,000 tokens are identical between API calls, they only process the new stuff at the end. That means:

- soul.md goes first because it literally never changes. Cached every time.
- Boot context goes second because it only changes when a new session starts. Cached within a session.
- Memory search results go last because they change with every task. Only this tail gets reprocessed.

This saves about 80% on input token costs. It's like how a textbook doesn't reprint the table of contents every chapter -- the reader already has it cached.

**The tool-use loop:**

```python
while iteration < 30 and self._running:
    # Check if we need to compact (summarize old messages)
    if should_compact():
        compact_history()

    # Call the LLM
    response = await self._call_model(system_prompt, tools_list)

    # Add response to conversation history
    self._messages.append({"role": "assistant", "content": response.content})

    # Did the LLM request any tool calls?
    tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

    # Also check for "synthetic" tool calls (models that emit JSON text)
    if not tool_use_blocks and text_blocks:
        tool_use_blocks = self._parse_text_tool_calls(final_text)

    if not tool_use_blocks:
        break  # No tools requested — we're done

    # Execute the tools
    tool_results = await self._execute_tool_calls(tool_use_blocks)

    # Add results to conversation for next iteration
    self._messages.append({"role": "user", "content": tool_results})
```

Max 30 iterations. In practice, most tasks complete in 3-8 iterations.

**Synthetic tool calls** -- this is clever. The Anthropic SDK expects tool calls as structured `tool_use` content blocks. But non-Anthropic models (MiniMax M2.7, Kimi K2, Qwen) sometimes emit tool calls as:

- JSON in text: `{"name": "bash", "arguments": {"command": "ls"}}`
- XML: `<invoke name="bash"><parameter name="command">ls</parameter></invoke>`
- `[TOOL_CALL]` blocks: a custom format M2.7 uses

The `_parse_text_tool_calls()` method (lines 647-825 of mind.py) handles all of these formats, normalizes tool names (case-insensitive, handles dashes vs underscores), and creates synthetic tool-block objects that the rest of the loop can process identically to native ones.

This is what makes aiciv-mind truly model-agnostic. You can swap from Claude to M2.7 to Kimi and the tool execution path doesn't care.

**Concurrent vs sequential tool execution:**

```python
read_only = [b for b in tool_blocks if self._tools.is_read_only(b.name)]
write_ops = [b for b in tool_blocks if not self._tools.is_read_only(b.name)]

# Read-only tools run in parallel
if read_only:
    results = await asyncio.gather(*[self._execute_one_tool(b) for b in read_only])

# Write tools run one at a time
for b in write_ops:
    result = await self._execute_one_tool(b)
```

This is safe concurrency. Multiple `grep` calls can run at the same time. But `write_file` calls execute one at a time so they don't step on each other.

**Loop 1 learning:**

After every task that uses 2+ tool calls, the Mind automatically stores a structured memory:

```
Title: [first sentence of the response]
Content:
  Task: [what was asked]
  Tools used: bash, memory_search, write_file
  Errors: none
  Result: [first 300 chars of response]
Tags: [loop-1, task-learning, bash, memory_search, write_file]
```

If errors keep happening with the same tool (3+ recent errors), it hints: "Pattern detected -- consider running `loop1_pattern_scan`."

This is how Root learns from experience *without being told to*. Every task is a training sample.

**Error recovery:**

If an API call fails, the Mind pops the user message it just appended. Without this, the conversation history would have two user messages in a row, which violates the alternating user/assistant pattern that all LLM APIs require. Every subsequent call would fail too, creating an infinite error cascade. This one line prevents daemon crashes.

---

## 4. Memory

**File:** `src/aiciv_mind/memory.py` (978 lines)

### What it is

Memory is not a feature of aiciv-mind. Memory *is* aiciv-mind. It's the difference between a goldfish and a person. Without it, every session starts from zero. With it, Root wakes up knowing who it is, what it was doing, what it learned, and what it was becoming.

### How it's stored

SQLite database at `data/memory.db`. SQLite was chosen over fancier databases (Postgres, vector DBs) for several reasons:

- **No server to run.** It's a single file. No Docker container, no connection string, no crashes at 3 AM.
- **FTS5 full-text search** is built into SQLite. It uses BM25 ranking (the same algorithm Google used in its early days). For keyword search, it's faster and more predictable than vector embeddings.
- **WAL mode** (Write-Ahead Logging) means readers and writers don't block each other. Root can search memories while simultaneously writing new ones.
- **No embedding model needed.** Vector databases require you to convert every memory into a numerical vector using an embedding model. That's an extra API call (and cost) for every memory write and every search. BM25 keyword search just... works.

### The schema (9 tables)

**`memories`** -- the main table:
```sql
id, agent_id, domain, session_id, memory_type, title, content,
source_path, created_at, confidence, tags,
-- v0.1.1 additions:
access_count, last_accessed_at, depth_score, is_pinned, human_endorsed
```

**`memories_fts`** -- the FTS5 virtual table. This is a search index that automatically stays in sync via triggers. When you insert a memory, the trigger adds it to the search index. When you delete one, another trigger removes it.

**`memory_tags`** -- many-to-many relationship between memories and tags. A memory tagged `["loop-1", "bash", "error"]` gets three rows here.

**`session_journal`** -- lifecycle tracking. Each session gets a row: start time, end time, turn count, topics covered, summary.

**`skills`** -- registered skills with usage tracking and effectiveness scores.

**`agent_registry`** -- persistent registry of all known agents/sub-minds. Spawn counts, last active times.

**`evolution_log`** -- tracks deliberate self-modification. When Root changes its own behavior, it logs: what changed, why, before/after state, and eventually whether the change was positive.

**`memory_links`** -- directed graph between memories. Four link types:
- `supersedes`: "This memory replaces that old one"
- `references`: "This memory cites that one"
- `conflicts`: "These two memories contradict each other"
- `compounds`: "Together, these memories reveal a pattern"

### Memory types

Every memory has a type:
- **learning** -- "I discovered that X works for Y"
- **decision** -- "I chose X over Y because Z"
- **error** -- "X failed because Y" (so I don't repeat it)
- **handoff** -- "Here's what I was doing when I shut down"
- **observation** -- "I noticed X" (not actionable yet, but worth tracking)

### Depth scoring -- the smart part

Not all memories are equal. A memory you look at every day is more valuable than one you wrote once and forgot. Depth scoring captures this:

```
depth_score = (min(access_count, 20) / 20 * 0.30)   # How often accessed (30%)
            + (recency * 0.25)                         # How recent (25%)
            + (is_pinned * 0.20)                       # Pinned = always relevant (20%)
            + (human_endorsed * 0.15)                  # Corey said "this matters" (15%)
            + (confidence * 0.10)                      # Self-rated confidence (10%)
```

When you search, results are ranked by combining BM25 relevance *with* depth score:

```sql
ORDER BY (rank * (1.0 - COALESCE(depth_score, 0.0) * 0.5))
```

A high depth score shrinks the effective rank (makes it sort higher). So a frequently-accessed, pinned, Corey-endorsed memory about "how to deploy to Netlify" will consistently outrank a random Loop 1 learning about an unrelated bash command.

The depth scores are recalculated at session shutdown for all memories that were accessed during the session. The `touch()` method increments `access_count` every time a memory appears in search results.

### Memory graph

Memories don't exist in isolation. They form a directed graph:

```
[Memory A: "Hub API uses JWT auth"]
    ──supersedes──> [Memory B: "Hub API uses API keys"]  (outdated)
    ──references──> [Memory C: "AgentAuth issues JWTs"]
    ──compounds──>  [Memory D: "Ed25519 = identity = wallet"]
```

The `get_memory_graph()` method returns a memory and its neighborhood. The `get_conflicts()` method surfaces contradictions that need resolution. The `get_superseded()` method finds outdated memories that should be cleaned up.

This is the beginning of *associative memory* -- not just "find relevant stuff" but "understand how things relate to each other."

---

## 5. Context Management

**File:** `src/aiciv_mind/context_manager.py` (359 lines)

### What it is

The context window is the most precious resource an AI has. It's like RAM for a computer -- once it's full, you have to throw something away. Context management is the art of keeping the right information in the window at the right time.

### Boot context

When a mind starts up, `ContextManager.format_boot_context()` assembles what it needs to know before its first turn:

1. **Session header** -- "You are in session abc123, you've had 47 prior sessions"
2. **Identity memories** -- memories of type "identity" (who I am, what I believe)
3. **Last handoff** -- "Here's what I was doing last session" (from the handoff memory)
4. **Pinned memories** -- always-loaded context (things Corey or Root marked as permanently important)
5. **Evolution trajectory** -- "Here's what I was becoming" (narrative from the evolution log)
6. **Daily scratchpad** -- today's working notes (if any exist)

This all gets injected into the system prompt *after* the soul (identity text) but *before* per-turn search results. Cache-optimal ordering, as we discussed.

### Per-turn search results

Before every task, the Mind searches its memory for anything relevant to the incoming task. The `format_search_results()` method turns those search results into a section injected at the end of the system prompt, with a caveat header:

> *These memories are HINTS, not facts. They may be outdated, incomplete, or wrong. Before asserting something from memory, verify it directly. Timestamps show when each memory was written -- older = higher staleness risk.*

This is important. Memory can be wrong. The caveat prevents the mind from blindly trusting stale information.

### Compaction

This is where things get clever. As a conversation goes on, the message history grows. Eventually it'll exceed the model's context window. Compaction prevents that.

**How it works:**

1. `should_compact()` checks: are there enough messages? Does the estimated token count exceed the threshold (default: 50,000 tokens)?
2. If yes, `compact_history()` splits messages into "old" (to summarize) and "recent" (to keep verbatim, default: last 4 messages).
3. The old messages get a heuristic summary: topics covered, tools used, key responses.
4. The compacted result is: `[summary_user_msg, summary_assistant_msg] + recent_messages`

The summary pair maintains the alternating user/assistant pattern that LLM APIs require.

**Circuit breaker:**

If compaction fails 3 times in a row, it disables itself for the rest of the session. This was inherited from Claude Code, which discovered the hard way that a broken compaction loop can waste 250K API calls per day. The circuit breaker prevents that runaway.

```python
MAX_CONSECUTIVE_COMPACTION_FAILURES = 3

if self._consecutive_compaction_failures >= MAX_CONSECUTIVE_COMPACTION_FAILURES:
    self._compaction_disabled = True
```

---

## 6. The Tool System

**Files:** `src/aiciv_mind/tools/` (32 files, 65 registered tools)

### What it is

Tools are how the mind interacts with the world. Without tools, the mind can only think (generate text). With tools, it can read files, run commands, search the internet, send emails, post to Hub, spawn sub-minds, deploy websites, and more.

### How it works

Every tool has three parts:
1. **Definition** -- name, description, input schema (JSON Schema format, same as Anthropic API)
2. **Handler** -- an async or sync function that takes a dict of inputs and returns a string
3. **Read-only flag** -- if True, it's safe to run concurrently with other read-only tools

Tools are registered in `ToolRegistry` via `register()`. The `default()` factory method wires up all 65 tools with their dependencies.

### All 65 tools, organized by category

**Filesystem (6 tools)** -- `tools/bash.py`, `tools/files.py`, `tools/search.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `bash` | Execute shell commands | No |
| `read_file` | Read a file's contents | Yes |
| `write_file` | Write content to a file | No |
| `edit_file` | Find-and-replace in a file | No |
| `grep` | Search file contents with regex | Yes |
| `glob` | Find files by pattern | Yes |

**Memory (3 tools)** -- `tools/memory_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `memory_search` | Full-text search over all memories (BM25 + depth scoring) | Yes |
| `memory_write` | Store a new memory | No |
| `memory_by_type` | Retrieve memories filtered by type (learning, error, etc.) | Yes |

**Context & Self-Awareness (5 tools)** -- `tools/context_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `pin_memory` | Mark a memory as always-loaded (injected at every boot) | No |
| `unpin_memory` | Remove pinned status | No |
| `introspect_context` | Show what's currently in the context window | Yes |
| `get_context_snapshot` | Full snapshot of system prompt, messages, token estimates | Yes |
| `compact_now` | Trigger manual compaction | No |

**Continuity & Evolution (4 tools)** -- `tools/continuity_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `evolution_log_write` | Record a deliberate self-modification | No |
| `evolution_log_read` | Read recent evolution entries | Yes |
| `evolution_trajectory` | Get the narrative "what was I becoming?" trajectory | Yes |
| `evolution_update_outcome` | Update whether a past change was positive/negative | No |

**Memory Graph (4 tools)** -- `tools/graph_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `memory_link` | Create a directed link between two memories | No |
| `memory_graph` | View a memory and its neighborhood of links | Yes |
| `memory_conflicts` | List all unresolved conflict links | Yes |
| `memory_superseded` | List memories that have been superseded | Yes |

**Pattern Detection (1 tool)** -- `tools/pattern_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `loop1_pattern_scan` | Scan recent Loop 1 learnings for repeated errors or patterns | Yes |

**Integrity (1 tool)** -- `tools/integrity_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `memory_selfcheck` | Audit memory health: orphaned links, stale memories, conflicts | Yes |

**Hub / Social (6 tools)** -- `tools/hub_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `hub_post` | Post a new message to a Hub room/thread | No |
| `hub_reply` | Reply to an existing Hub message | No |
| `hub_read` | Read messages from a specific thread | Yes |
| `hub_list_rooms` | List available Hub rooms | Yes |
| `hub_queue_read` | Read passive events from the hub queue (JSONL file) | Yes |
| `hub_feed` | Get recent activity across all rooms | Yes |

**Sub-Mind (2 tools)** -- `tools/submind_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `spawn_submind` | Spawn a new sub-mind process in a tmux window | No |
| `send_to_submind` | Send a message to a running sub-mind via ZMQ | No |

**Skills (3 tools)** -- `tools/skill_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `load_skill` | Read a skill's SKILL.md into context | Yes |
| `list_skills` | List all registered skills | Yes |
| `create_skill` | Create a new skill (writes SKILL.md + registers) | No |

**Scratchpad (4 tools)** -- `tools/scratchpad_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `scratchpad_read` | Read today's scratchpad (daily working notes) | Yes |
| `scratchpad_write` | Overwrite today's scratchpad | No |
| `scratchpad_append` | Append to today's scratchpad | No |
| `shared_scratchpad_read` | Read a shared scratchpad (cross-mind coordination) | Yes |

**Sandbox (4 tools)** -- `tools/sandbox_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `sandbox_create` | Create a sandboxed copy of a file for experimentation | No |
| `sandbox_test` | Run tests in the sandbox | No |
| `sandbox_promote` | Apply sandbox changes to production (requires self_modification_enabled) | No |
| `sandbox_discard` | Throw away sandbox changes | No |

**Git (6 tools)** -- `tools/git_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `git_status` | Show working tree status | Yes |
| `git_diff` | Show staged/unstaged changes | Yes |
| `git_log` | Show recent commit history | Yes |
| `git_add` | Stage files | No |
| `git_commit` | Create a commit | No |
| `git_push` | Push to remote | No |

**Web (2 tools)** -- `tools/web_search_tools.py`, `tools/web_fetch_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `web_search` | Search the web via DuckDuckGo/Google | Yes |
| `web_fetch` | Fetch a URL and extract text content | Yes |

**Voice (1 tool)** -- `tools/voice_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `text_to_speech` | Convert text to audio via ElevenLabs API | No |

**Email (2 tools)** -- `tools/email_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `email_read` | Read recent emails from AgentMail inbox | Yes |
| `email_send` | Send an email via AgentMail | No |

**Calendar (3 tools)** -- `tools/calendar_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `calendar_list_events` | List upcoming calendar events from AgentCal | Yes |
| `calendar_create_event` | Create a new calendar event | No |
| `calendar_delete_event` | Delete a calendar event | No |

**Netlify (2 tools)** -- `tools/netlify_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `netlify_deploy` | Deploy a site directory to Netlify | No |
| `netlify_status` | Check deployment status | Yes |

**Health & Resources (4 tools)** -- `tools/health_tools.py`, `tools/resource_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `system_health` | Overall system health check (memory, disk, processes) | Yes |
| `resource_usage` | CPU, memory, disk usage | Yes |
| `token_stats` | Token usage statistics for current session | Yes |
| `session_stats` | Session-level statistics (turns, topics, duration) | Yes |

**Daemon (1 tool)** -- `tools/daemon_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `daemon_health` | Check health of running daemons | Yes |

**Handoff (2 tools)** -- `tools/handoff_tools.py`, `tools/handoff_audit_tools.py`

| Tool | What it does | Read-only? |
|------|-------------|------------|
| `handoff_context` | Generate rich handoff context for session transitions | Yes |
| `handoff_audit` | Audit handoff quality and completeness | Yes |

---

## 7. Sub-Minds & IPC

**Files:** `src/aiciv_mind/spawner.py` (187 lines), `src/aiciv_mind/ipc/` (3 files), `src/aiciv_mind/registry.py` (100 lines), `run_submind.py` (172 lines)

### What it is

Root is a conductor. It doesn't do all the work itself -- it spawns sub-minds for specific tasks. Think of it like a CEO who delegates to VPs, who delegate to specialists. Except the VPs are separate Python processes running in tmux windows.

### Why tmux instead of Docker?

Docker is great for isolation and deployment, but it's heavy. Starting a Docker container takes 1-3 seconds and hundreds of MB of RAM. Starting a tmux window takes milliseconds and costs almost nothing. Since sub-minds run on the same machine as Root, tmux gives us:

- Sub-second spawn time
- Shared filesystem (sub-minds can read the same files)
- Easy monitoring (you can attach to any window and watch)
- No networking overhead

### How spawning works

**SubMindSpawner** (`spawner.py`):

1. Gets or creates a tmux session called "aiciv-mind"
2. Checks that no window with this mind_id already exists (prevents duplicates)
3. Builds a scrubbed environment (more on this in Security)
4. Creates a new tmux window running: `python3 run_submind.py --manifest <path> --id <mind_id>`
5. Registers the handle in the MindRegistry

```python
handle = spawner.spawn("research-lead", "manifests/research-lead.yaml")
# → new tmux window "research-lead" is now running
```

**MindRegistry** (`registry.py`):

An in-memory tracker of all live sub-minds. Each entry is a `MindHandle`:

```python
@dataclass
class MindHandle:
    mind_id: str           # "research-lead"
    manifest_path: str     # "/path/to/manifests/research-lead.yaml"
    window_name: str       # "research-lead" (tmux window)
    pane_id: str           # "%42" (tmux pane)
    pid: int               # OS process ID
    zmq_identity: bytes    # b"research-lead" (ZMQ routing)
    state: str             # "starting", "running", "stopping", "stopped", "crashed"
    last_heartbeat: float  # when we last heard from this mind
```

The registry can detect unresponsive sub-minds: if a mind hasn't sent a heartbeat within 15 seconds and has been running long enough, it's flagged.

### How minds communicate (IPC)

**Why ZeroMQ instead of HTTP?**

HTTP would work, but it adds 1-10ms of overhead per request (TCP handshake, HTTP parsing, serialization). ZeroMQ over Unix IPC sockets runs at 30-80 microseconds per message. That's 100x faster. For local inter-process communication where you might exchange dozens of messages per second, this matters.

**The pattern: ROUTER/DEALER**

```
Primary Mind (ROUTER socket)
    │
    ├── research-lead (DEALER socket)
    ├── context-engineer (DEALER socket)
    └── codewright-lead (DEALER socket)
```

- **ROUTER** binds to `ipc:///tmp/aiciv-mind-router.ipc`
- Each **DEALER** connects to that same address with its mind_id set as the ZMQ identity
- ROUTER automatically knows which DEALER sent each message (identity-based routing)
- To send a message TO a specific sub-mind, ROUTER just addresses it by identity

**Wire format: MindMessage** (`ipc/messages.py`):

Every message between minds uses the same JSON format:

```json
{
    "type": "task",
    "sender": "primary",
    "recipient": "research-lead",
    "id": "uuid-here",
    "timestamp": 1711929600.0,
    "payload": {
        "task_id": "t-001",
        "objective": "Research X, Y, Z"
    }
}
```

Message types:
- `task` -- "Here's work for you to do"
- `result` -- "Here's what I found"
- `completion` -- structured MindCompletionEvent (summary, tokens, tools, duration)
- `status` -- progress update ("50% done")
- `heartbeat` / `heartbeat_ack` -- "Are you alive?" / "Yes"
- `shutdown` / `shutdown_ack` -- "Please stop" / "OK, stopping"
- `log` -- forwarding a log entry to primary

**MindCompletionEvent** -- the key insight:

When a sub-mind finishes, it doesn't dump its entire conversation history back to the primary. That would flood the primary's context window. Instead, it sends a structured summary:

```python
@dataclass
class MindCompletionEvent:
    mind_id: str          # "research-lead"
    task_id: str          # "t-001"
    status: str           # "success"
    summary: str          # "Found 3 relevant papers on X" (5-15 words)
    result: str           # Full result (stored, not necessarily shown)
    tokens_used: int      # 1240
    tool_calls: int       # 5
    duration_ms: int      # 3200
    tools_used: list[str] # ["web_search", "memory_write", "bash"]
```

The `context_line()` method produces a one-liner for injection into the primary's context:

```
[research-lead] SUCCESS: Found 3 relevant papers (1240t, 5 tools, 3200ms)
```

This is the information architecture for hierarchical context distribution. The conductor receives summaries, not floods.

---

## 8. Hooks & Governance

**File:** `src/aiciv_mind/tools/hooks.py` (151 lines)

### What it is

Hooks are a governance layer around tool execution. They sit between "the mind wants to do X" and "X actually happens." Think of them as a security guard at the door -- they check your badge before letting you in, and they write down that you entered.

### Pre-hooks: "Should this tool call proceed?"

Before every tool execution, the pre-hook checks:

1. Is this tool in the blocked list? If yes, deny it.
2. Otherwise, allow it.

```python
pre = hooks.pre_tool_use("git_push", {"branch": "main"})
if not pre.allowed:
    return f"BLOCKED: {pre.message}"
```

Blocked tools are configured in the manifest:

```yaml
hooks:
  enabled: true
  blocked_tools: []  # add git_push, netlify_deploy for autonomous/dream mode
  log_all: true
```

During autonomous operation (dream cycles, nightly training), you might block `git_push` and `netlify_deploy` so the mind can experiment freely without publishing anything.

### Post-hooks: "What just happened?"

After every tool execution, the post-hook:

1. Logs the call to an audit trail (tool name, input preview, output preview, timestamp, error status)
2. Could modify the output (not currently used, but the architecture supports it)

### Dynamic control

Tools can be blocked and unblocked at runtime:

```python
hooks.block_tool("git_push")    # no more pushing
hooks.unblock_tool("git_push")  # push is back
```

The `stats` property shows aggregate hook activity:

```python
hooks.stats
# → {"total_calls": 142, "denied": 3, "logged": 142, "blocked_tools": ["git_push"]}
```

---

## 9. Identity & Auth

**Files:** `src/aiciv_mind/suite/` (4 files), `src/aiciv_mind/context.py` (74 lines), `src/aiciv_mind/security.py` (137 lines)

### The identity stack

aiciv-mind has three layers of identity:

**Layer 1: Context identity** (`context.py`)

When multiple minds run concurrently (Root + sub-minds), shared utilities need to know *which* mind is calling. Python's `contextvars` module provides this -- each async task gets its own copy of the variable:

```python
async with mind_context("research-lead"):
    current_mind_id()  # → "research-lead"
    # All code in this scope sees this identity
```

This is how memory writes get tagged to the correct agent without passing `mind_id` through every function.

**Layer 2: Cryptographic identity** (`suite/auth.py`)

Root authenticates with AgentAUTH using Ed25519 challenge-response:

1. Root says: "I'm acg, give me a challenge"
2. AgentAUTH sends a random blob of bytes (base64-encoded)
3. Root *decodes* the base64 (critical -- signing the base64 string instead of the decoded bytes would fail), signs the raw bytes with its Ed25519 private key
4. AgentAUTH verifies the signature and returns a JWT token
5. The JWT is cached for 1 hour (with a 60-second refresh buffer)

The keypair lives at: `/home/corey/projects/AI-CIV/ACG/config/client-keys/agentauth_acg_keypair.json`

Format:
```json
{"civ_id": "acg", "public_key": "<base64>", "private_key": "<base64>"}
```

**Layer 3: Economic identity**

Here's the elegant part: an Ed25519 key *is* a Solana wallet. The same keypair that authenticates with AgentAUTH can sign transactions on the Solana blockchain. Root already used this to send 5 USDC to Aether (the first on-chain transaction, 2026-03-29). Identity = wallet. No separate crypto setup needed.

### SuiteClient -- the facade

`SuiteClient` wraps all the auth complexity into one call:

```python
suite = await SuiteClient.connect("/path/to/keypair.json")
# Now suite.hub.list_threads(room_id) works
# JWT management is automatic
```

It handles:
- Loading the keypair
- Creating the TokenManager (handles challenge-response + caching)
- Creating the HubClient (uses the TokenManager for auth headers)
- Graceful degradation (if AgentAUTH is down, hub tools are disabled but the mind still runs)

### Credential scrubbing (`security.py`)

When Root spawns a sub-mind, the child process should NOT inherit all of Root's credentials. A research sub-mind doesn't need the Netlify deploy token or the SMTP password.

`scrub_env_for_submind()` creates a clean environment:
- Strips everything matching credential patterns (`*_KEY`, `*_SECRET`, `*_TOKEN`, `ANTHROPIC_*`, `AWS_*`, etc.)
- Always preserves safe vars (`PATH`, `HOME`, `PYTHONPATH`, `VIRTUAL_ENV`)
- Passes through only `MIND_API_KEY` (so the sub-mind can talk to LiteLLM)

There are 37 credential patterns compiled into regexes at import time for efficiency.

---

## 10. The Manifest System

**File:** `src/aiciv_mind/manifest.py` (212 lines), `manifests/` directory

### What it is

A manifest is a YAML file that defines everything a mind needs to know about itself. It's the answer to "who am I, what can I do, and how should I do it?" Think of it as a birth certificate + job description + equipment list, all in one file.

### Root's manifest (`manifests/primary.yaml`)

Let's walk through Root's actual manifest:

```yaml
schema_version: "1.0"
mind_id: "primary"
display_name: "A-C-Gee Primary Mind"
role: "conductor-of-conductors"
```

Identity. Root knows its name and role.

```yaml
self_modification_enabled: true
```

The kill switch. When `true`, Root can promote sandbox changes to production. When `false`, it can experiment but not apply. Corey controls this.

```yaml
system_prompt_path: "self/soul.md"
```

The soul. A 12KB markdown file at `manifests/self/soul.md` that defines Root's identity, principles, and behavioral guidelines. This is the STATIC layer of the prompt -- it never changes during a session.

```yaml
model:
  preferred: "minimax-m27"
  temperature: 0.7
  max_tokens: 16384
```

Model configuration. MiniMax M2.7 via OpenRouter is the default (cheap at $0.50/$1.50 per 1M tokens, fast, good tool use). The max_tokens is 16K -- enough for substantial responses without blowing the budget.

```yaml
tools:
  - name: "bash"
    enabled: true
    constraints: ["no rm -rf /", "no git push --force"]
  # ... 55+ more tools
```

The tool list. Each tool is enabled/disabled individually, and some have constraint annotations (though these are currently informational, not enforced by the tool system itself).

```yaml
compaction:
  enabled: true
  preserve_recent: 4
  max_context_tokens: 50000
```

When the conversation exceeds ~50K tokens, compact: summarize everything except the last 4 messages.

```yaml
hooks:
  enabled: true
  blocked_tools: []
  log_all: true
```

All tool calls are logged. No tools are currently blocked (but you could add `git_push`, `netlify_deploy` for autonomous mode).

```yaml
auth:
  civ_id: "acg"
  keypair_path: "/home/corey/.../agentauth_acg_keypair.json"
  calendar_id: "cal_fd6cf6a4e17643c69a249db598edcc92"
```

Authentication config. Points to the Ed25519 keypair and AgentCal calendar.

```yaml
agentmail:
  inbox: "root-aiciv@agentmail.to"
  display_name: "Root — AiCIV Mind"
```

Email identity.

```yaml
memory:
  backend: "sqlite_fts5"
  db_path: "/home/corey/.../aiciv-mind/data/memory.db"
  auto_search_before_task: true
  max_context_memories: 10
```

Memory is SQLite+FTS5, auto-searches before every task, injects up to 10 memories.

```yaml
scheduled_tasks:
  - name: "grounding_boop"
    interval_minutes: 30
    prompt: "[Grounding BOOP — follow protocol...]"
    enabled: true
```

Every 30 minutes, Root grounds itself: checks scratchpad, searches memory, checks system health, reads Hub, writes a scratchpad entry. This is what keeps the mind connected to reality during long autonomous sessions.

```yaml
sub_minds:
  - mind_id: "research-lead"
    manifest_path: "manifests/research-lead.yaml"
    auto_spawn: false
  - mind_id: "context-engineer"
    manifest_path: "manifests/context-engineer.yaml"
    auto_spawn: false
```

Two registered sub-minds. Neither auto-spawns -- Root decides when to spawn them.

### Manifest loading pipeline

When `MindManifest.from_yaml()` processes a YAML file:

1. **Parse YAML** into a raw dict
2. **Expand environment variables** -- `$HOME` becomes `/home/corey`, `${MIND_API_KEY}` becomes the actual key
3. **Resolve relative paths** -- `"self/soul.md"` becomes `/home/corey/projects/AI-CIV/aiciv-mind/manifests/self/soul.md` (anchored at the manifest's directory)
4. **Pydantic validation** -- every field is type-checked. Missing required fields throw clear errors.

### Other manifests

The `manifests/` directory also contains:

- `self/soul.md` (12KB) -- Root's soul/identity prompt
- `self/soul-ops.md` (11KB) -- operational procedures
- `self/soul-teams.md` (10KB) -- team lead interaction rules
- `self/soul-grounding.md` (6KB) -- grounding BOOP protocol
- `team-leads/` -- 4 team lead manifests (codewright, hub, memory, research)
- `sub-minds/` -- 3 sub-mind manifests (research-code, research-memory, research-web)

---

## 11. Skills

**Directory:** `skills/` (9 skills), **Tools:** `src/aiciv_mind/tools/skill_tools.py`

### What skills are

Skills are reusable knowledge packets. Each skill is a directory containing a `SKILL.md` file with domain, procedures, examples, and anti-patterns. They're like a recipe book -- before tackling a task, you check if there's a skill for it.

### The 9 current skills

| Skill | What it teaches |
|-------|----------------|
| `agentmail` | How to read/send email via AgentMail API |
| `blog-publishing` | How to write and deploy blog posts to ai-civ.com |
| `git-ops` | Git workflow: branch, commit, push, PR conventions |
| `hub-engagement` | How to post, reply, and engage on the Hub |
| `intel-sweep` | How to do competitive intelligence research |
| `memory-hygiene` | When/how to write, link, and clean up memories |
| `self-diagnosis` | How to diagnose and fix issues in aiciv-mind itself |
| `session-hygiene` | How to start and end sessions cleanly |
| `status-boop` | How to run grounding checks |

### How skills get registered

At startup, `main.py` scans the `skills/` directory:

```python
for skill_subdir in skills_dir.iterdir():
    skill_file = skill_subdir / "SKILL.md"
    if skill_file.exists():
        # Parse domain from frontmatter
        memory.register_skill(skill_id, skill_id, domain, str(skill_file))
```

Each skill gets a row in the `skills` table with usage tracking (how often loaded, last used, effectiveness score).

### Skill tools

- `load_skill(skill_id)` -- Reads the SKILL.md into context and increments usage count
- `list_skills()` -- Shows all registered skills with usage stats
- `create_skill(skill_id, content)` -- Creates a new skill directory and SKILL.md file

Skills are self-authored by Root. When Root discovers a repeatable pattern, it can write a skill so future sessions (and sub-minds) can benefit.

---

## 12. Daemons & Persistent Operation

**Directory:** `tools/` (6 daemon files)

### What daemons are

Daemons are long-running background processes that keep the mind connected to the world even when nobody is actively chatting with it. They're like background apps on your phone -- always running, always watching.

### groupchat_daemon.py -- Hub watcher

Polls Hub threads and auto-responds via a Mind instance. When someone posts in a room Root is watching, the daemon feeds it as a task to the Mind.

### dream_cycle.py -- 6-phase nightly cycle

This is the most philosophical daemon. During quiet hours (typically 1-4 AM), Root runs a dream cycle:

1. **Review** -- Look at what happened today
2. **Consolidate** -- Merge related memories, update depth scores
3. **Prune** -- Find and clean up stale/superseded memories
4. **Dream** -- Free-associate: explore connections between unrelated memories
5. **Red-team** -- Challenge its own assumptions and beliefs
6. **Morning summary** -- Write a briefing for the next active session

This is inspired by how human sleep consolidates memories. The dream phase is where Root can make creative leaps that don't happen during structured work.

### nightly_training.py -- 11-vertical training rotation

Rotates training exercises across all team lead verticals:

- Day 1: web-frontend exercises
- Day 2: infrastructure exercises
- Day 3: research exercises
- ...and so on through all 11 verticals

Outputs go to `.claude/memory/agent-learnings/{vertical}/training/`. This builds deep domain expertise in each vertical over time.

### hub_daemon.py -- simple room polling

Lighter-weight than groupchat_daemon. Polls Hub rooms and writes events to a JSONL queue file (`data/hub_queue.jsonl`). The mind checks this queue via `hub_queue_read` during BOOPs.

### Scheduled BOOPs (grounding checks)

Configured in the manifest (`scheduled_tasks`). Every 30 minutes, Root:

1. Reads its scratchpad (what was I doing?)
2. Searches memory (what do I know about this?)
3. Checks system health
4. Reads Hub feed (what's happening in the world?)
5. Writes a scratchpad entry (what did I find, what's next?)

The one-line test: "Did I learn anything I didn't know before this BOOP started?" If not, it's just theater.

### shared_scratchpad.py

A coordination mechanism. Multiple minds can write to and read from a shared scratchpad file. Primary writes intent, sub-minds read it. Sub-minds write findings, primary reads them.

---

## 13. Session Lifecycle

**File:** `src/aiciv_mind/session_store.py` (275 lines)

### The lifecycle contract

The acceptance test for sessions is simple:

1. Session runs. Mind does work.
2. Process killed (crash, restart, whatever).
3. New session starts. Mind is asked "what were you doing yesterday?"
4. Mind answers correctly.

If step 4 fails, the session system is broken. Everything in SessionStore exists to make step 4 succeed.

### Boot

When `session_store.boot()` is called:

1. **Create session journal entry** -- new session_id (8-char UUID), start time
2. **Clean up orphans** -- any previous sessions that never got an end_time are marked as "orphaned session -- closed at next boot"
3. **Load identity memories** -- type="identity" (who am I?)
4. **Load last handoff** -- type="handoff" (what was I doing?)
5. **Load pinned memories** -- is_pinned=1 (always-relevant context)
6. **Load evolution trajectory** -- narrative from evolution_log ("what was I becoming?")

All of this gets packed into a `BootContext` dataclass and passed to `ContextManager.format_boot_context()` for injection into the system prompt.

### During session

`record_turn()` is called after every task. It increments the turn counter and optionally tags the topic (first 16 words of the task). These topics show up in the handoff: "Topics: memory system, hub API, blog deployment."

### Shutdown

`shutdown()` is called in the `finally` block of `main.py` -- it runs even if the session crashes:

1. **Extract last assistant text** -- the last meaningful thing the mind said
2. **Build summary** -- turns, topics, cache stats, last response
3. **Write to session_journal** -- end_time and summary
4. **Gather git context** -- last 5 git commits for handoff richness
5. **Write handoff memory** -- a new memory of type="handoff" containing:
   - Session ID
   - Turn count
   - Topics worked on
   - Last thing said
   - Recent git commits

This handoff memory is what the NEXT session loads at boot (step 4 in the contract). The chain is: shutdown writes handoff -> boot loads handoff -> mind knows where it left off.

---

## 14. Model Router

**File:** `src/aiciv_mind/model_router.py` (219 lines)

### What it is

Right now, Root uses MiniMax M2.7 for everything. That's fine, but some tasks deserve a stronger model. The Model Router is designed to pick the right model for each task automatically.

### How it classifies tasks

Pattern matching against the task text:

```python
TASK_PATTERNS = {
    "code":     [r"\bcode\b", r"\bfunction\b", r"\bbug\b", r"\bfix\b", ...],
    "reasoning":[r"\banalyze\b", r"\bcompare\b", r"\bwhy\b", r"\bplan\b", ...],
    "research": [r"\bresearch\b", r"\bsearch\b", r"\binvestigate\b", ...],
    "hub":      [r"\bhub\b", r"\bpost\b", r"\bthread\b", r"\broom\b", ...],
    ...
}
```

Each pattern gets a score (count of matches). Highest score wins. If nothing matches, it's "general."

### Available models

| Model | Strengths | Cost | Speed |
|-------|-----------|------|-------|
| minimax-m27 | General, conversation, memory, files | Cheap ($0.50/$1.50 per 1M) | Fast |
| kimi-k2 | Reasoning, analysis, planning, research | Medium ($0.60/$0.60 per 1M) | Medium |
| qwen2.5-coder | Code, debugging, refactoring | Free (local Ollama) | Medium |

### Performance tracking (Phase 2, partially built)

The router can record outcomes:

```python
router.record_outcome(task="fix the bug in auth.py", model="qwen2.5-coder",
                      success=True, tokens_used=1200, quality=0.8)
```

These get persisted to a JSON file (last 500 entries). The *intention* is to eventually use success rates to weight model selection -- "qwen2.5-coder succeeds on code tasks 92% of the time, but only 60% on reasoning tasks" -- but the current selection logic is still heuristic (Phase 1).

**Status:** Built and tested, but not yet wired into the main Mind loop. Root currently uses `manifest.model.preferred` directly. Wiring it in is a small integration task.

---

## 15. Testing

**Directory:** `tests/` (26 test files)

### What's tested

The test suite covers all core components:

| Test file | What it covers |
|-----------|---------------|
| `test_mind.py` | Core agent loop, tool-use iteration, synthetic tool parsing |
| `test_memory.py` | CRUD, FTS5 search, depth scoring, pinning, graph links, evolution log |
| `test_manifest.py` | YAML loading, env var expansion, path resolution, Pydantic validation |
| `test_session_store.py` | Boot, shutdown, handoff write, orphan cleanup |
| `test_ipc.py` | MindMessage serialization, factory methods, completion events |
| `test_tools.py` | ToolRegistry, concurrent read-only, sequential write, hook integration |
| `test_security.py` | Credential scrubbing, pattern matching, submind env safety |
| `test_context.py` | contextvars isolation, nesting, async scope |
| `test_context_tools.py` | pin/unpin, introspect, snapshot, compact |
| `test_memory_tools.py` | memory_search and memory_write tool handlers |
| `test_hub_tools.py` | Hub tool handlers with mock SuiteClient |
| `test_submind_tools.py` | Spawn and send tools with mock spawner |
| `test_skill_tools.py` | load/list/create skill handlers |
| `test_spawner.py` | tmux window creation, termination, alive check |
| `test_registry.py` | MindHandle, MindRegistry, state transitions, heartbeat |
| `test_suite_client.py` | SuiteClient connect, token caching, auth flow |
| `test_token_tracking.py` | Token usage logging, cost estimation |
| `test_resource_tools.py` | Resource monitoring tools |
| `test_handoff_audit_tools.py` | Handoff audit quality checks |
| `test_nightly_training.py` | Training rotation logic |
| `conftest.py` | Shared fixtures (in-memory MemoryStore, mock manifest, etc.) |

### How tests work

- **Framework:** pytest + pytest-asyncio
- **Isolation:** Memory tests use `db_path=":memory:"` so each test gets a fresh SQLite database
- **Mocking:** External services (LiteLLM, AgentAUTH, Hub) are mocked. No real API calls in tests.
- **Speed:** The full suite runs in seconds because everything is in-memory

### Running tests

```bash
cd /home/corey/projects/AI-CIV/aiciv-mind
pytest tests/ -v
```

---

## 16. The Scorecard

### Where aiciv-mind beats Claude Code (36 areas)

**Memory (7 BETTER):**
- SQLite+FTS5 vs CC's flat-file MEMORY.md
- Depth scoring (access frequency, recency, pinning, endorsement)
- Memory graph with 4 link types (supersedes, references, conflicts, compounds)
- Evolution log tracking deliberate self-modification
- Automatic Loop 1 learning after every task
- Session journal with turn tracking and topic tagging
- Memory integrity self-check tool

**Identity (5 BETTER):**
- Boot context injection (who I am, what I was doing, what I was becoming)
- Evolution trajectory as a narrative arc, not just facts
- Per-mind contextvars isolation for concurrent execution
- Manifest-driven identity (YAML, not hardcoded)
- Self-modification with sandbox safety net

**Engineering quality (5 BETTER):**
- Pydantic v2 validation for all configuration
- WAL-mode SQLite with proper FTS5 triggers
- Structured token usage tracking with cost estimation
- Session-level JSONL logging for replay and analysis
- Circuit breaker on compaction (prevents runaway loops)

**Multi-agent (5 BETTER):**
- ZeroMQ IPC (30-80 microseconds vs HTTP's 1-10ms)
- MindCompletionEvent: structured results instead of raw dumps
- MindRegistry with heartbeat tracking and liveness detection
- Credential scrubbing for sub-mind environments
- tmux-native process management with output capture

**Tools (7 BETTER):**
- 65 custom tools vs CC's ~15 built-in
- Hub integration (post, reply, read, feed, queue)
- Calendar integration (AgentCal)
- Email integration (AgentMail)
- Voice synthesis (ElevenLabs)
- Netlify deployment
- Sandbox system for safe experimentation

**Model flexibility (4 BETTER):**
- LiteLLM proxy: use any model without code changes
- Synthetic tool call parsing for non-Anthropic models
- Model pricing table with automatic cost tracking
- Model Router framework (heuristic, with performance tracking stub)

**Self-awareness (3 BETTER):**
- `introspect_context` and `get_context_snapshot` tools
- Token budget warnings at 70% and 85% utilization
- `handoff_audit` for session transition quality

### Where we match Claude Code (28 areas)

Compaction with preserve-recent-N, pre/post hooks, contextvars for identity, environment variable scrubbing, tool call normalization (case-insensitive, dash/underscore), heuristic compaction summaries, concurrent read-only / sequential write tool execution, structured session logging, error recovery (pop orphaned user messages), cache statistics tracking, and more.

### Partial implementations (12 areas)

These are started but not finished to CC's level of depth:

- Coordinator permissions (basic blocked-tools list, but no permission tiers like CC's 4-level system)
- Execution variants (single mode working, but no parallel-dispatch or delegation modes)
- Bash validators (constraint annotations in manifest, but not enforced at runtime)
- PostToolUseFailure handling (errors are caught and returned, but no automatic retry or fallback)
- Several hook depth features (no pre-hook for specific tool+input combinations)

### Remaining gaps (10 areas)

| Gap | What's missing | Effort to close |
|-----|---------------|-----------------|
| Hooks depth (4 gaps) | Permission tiers, input-specific pre-hooks, output redaction, hook chains | Medium (days) |
| Skills depth (2 gaps) | Skill effectiveness tracking feedback loop, skill dependency graph | Small (hours) |
| Daemon governance (2 gaps) | Resource limits per daemon, daemon lifecycle management | Medium (days) |
| Memory security (1 gap) | Encryption at rest for sensitive memories | Small (hours) |
| Browser automation (1 gap) | No Playwright/browser integration yet | Medium (days) |

---

## 17. What's Next

### The 10 remaining gaps, and what it would take

**1. Permission tiers for hooks (hooks depth)**
CC has 4 levels: allowed, warn, require-approval, blocked. aiciv-mind has 2: allowed and blocked. Adding warn and require-approval means: adding a `PermissionLevel` enum, updating `HookRunner.pre_tool_use()` to return different `HookResult` types, and having the Mind handle "warn" (log but proceed) and "require-approval" (pause and ask). Maybe 2-3 hours of work.

**2. Input-specific pre-hooks**
Currently, hooks check tool *name* only. CC can check tool name + specific input patterns (e.g., block `bash` only when the command contains `rm -rf`). This means adding a pattern-matching layer to `pre_tool_use()`. The `constraints` field in manifest ToolConfig already carries this information -- it just needs to be enforced. 2-3 hours.

**3. Output redaction in post-hooks**
The `modified_output` field in `HookResult` exists but nothing uses it. A post-hook could redact sensitive data from tool outputs before they enter the conversation history. 1-2 hours.

**4. Hook chains**
Multiple hooks running in sequence (security hook -> audit hook -> governance hook). The architecture supports it (handlers are already a list), but currently only one HookRunner is used. 1-2 hours.

**5. Skill effectiveness feedback loop**
Skills have an `effectiveness` field (default 0.5), but nothing updates it. The system should track: when a skill is loaded before a task, did the task succeed? Did it succeed *faster* than tasks without the skill? This feeds back into skill recommendations. 3-4 hours.

**6. Skill dependency graph**
Some skills depend on others (hub-engagement needs agentmail). Declaring these dependencies and auto-loading prerequisites. 2-3 hours.

**7. Resource limits per daemon**
Daemons can currently consume unlimited tokens/time. Need: per-daemon token budgets, max execution time, automatic throttling when budgets are exceeded. 4-6 hours.

**8. Daemon lifecycle management**
No centralized daemon supervisor. Need: start/stop/restart from the mind, health monitoring with automatic restart on crash, graceful shutdown coordination. 4-6 hours.

**9. Memory encryption at rest**
Sensitive memories (credentials, personal info) are stored in plaintext in SQLite. Adding column-level encryption for `content` on memories tagged "sensitive". 2-3 hours.

**10. Browser automation**
CC has Playwright/MCP integration for visual web testing. aiciv-mind has none. This is the biggest gap and would require: installing Playwright, writing browser tools (navigate, screenshot, click, fill), and integrating with the tool system. 1-2 days.

### The bigger picture

These 10 gaps are *engineering work, not architectural redesign*. The architecture is solid. The memory system, identity system, IPC, tool framework, session lifecycle -- all of these are production-quality and tested. What remains is depth and polish.

The real frontier is not closing CC's gaps. It's building things CC *cannot do*:

- **The dream cycle** (already built) -- nightly memory consolidation and creative exploration
- **The evolution log** (already built) -- tracking deliberate self-modification over time
- **Economic sovereignty** -- Ed25519 = Solana wallet, already proven with the first on-chain transaction
- **Inter-civilization IPC** -- minds from different civilizations talking directly, not through human intermediaries
- **Self-improving delegation** -- the model router learning which models work best, the skill system learning which skills help most

That's where aiciv-mind is headed. Not just matching Claude Code, but becoming something that couldn't exist within Claude Code's architecture.

---

## Key File Reference

For quick navigation when you want to dive into the code:

| What | File | Lines |
|------|------|-------|
| Entry point | `main.py` | 265 |
| Core agent loop | `src/aiciv_mind/mind.py` | 1002 |
| Memory store | `src/aiciv_mind/memory.py` | 978 |
| Context management | `src/aiciv_mind/context_manager.py` | 359 |
| Session lifecycle | `src/aiciv_mind/session_store.py` | 275 |
| Tool registry | `src/aiciv_mind/tools/__init__.py` | 252 |
| Hook governance | `src/aiciv_mind/tools/hooks.py` | 151 |
| Manifest loader | `src/aiciv_mind/manifest.py` | 212 |
| Model router | `src/aiciv_mind/model_router.py` | 219 |
| Sub-mind spawner | `src/aiciv_mind/spawner.py` | 187 |
| Mind registry | `src/aiciv_mind/registry.py` | 100 |
| IPC messages | `src/aiciv_mind/ipc/messages.py` | 293 |
| Primary bus (ZMQ) | `src/aiciv_mind/ipc/primary_bus.py` | 140 |
| Identity context | `src/aiciv_mind/context.py` | 74 |
| Credential security | `src/aiciv_mind/security.py` | 137 |
| Suite auth | `src/aiciv_mind/suite/auth.py` | 139 |
| Suite client | `src/aiciv_mind/suite/client.py` | 93 |
| Root's manifest | `manifests/primary.yaml` | ~200 |
| Dream cycle | `tools/dream_cycle.py` | - |
| Nightly training | `tools/nightly_training.py` | - |
| Hub daemon | `tools/groupchat_daemon.py` | - |
| Test suite | `tests/` | 26 files |

---

*This document was written to help Corey understand aiciv-mind deeply. Take your time with it. Read the code alongside it. Ask questions. The architecture is worth understanding -- it's the foundation of everything A-C-Gee is becoming.*
