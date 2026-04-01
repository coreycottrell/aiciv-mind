# src/aiciv_mind — Module Reference

The core library. Every component that makes Root work.

## Module Map

| Module | Role |
|--------|------|
| `mind.py` | Core agent loop |
| `memory.py` | SQLite+FTS5 memory store |
| `manifest.py` | YAML manifest loader and validator |
| `session_store.py` | Session journal and turn tracking |
| `context_manager.py` | Formats memories into system prompt |
| `model_router.py` | LiteLLM model routing and selection |
| `spawner.py` | Sub-mind process spawner via libtmux |
| `registry.py` | In-memory MindHandle registry |
| `interactive.py` | Interactive REPL for human↔Root |
| `ipc/` | ZMQ inter-mind communication |
| `suite/` | AiCIV protocol clients (Auth, Hub) |
| `tools/` | All callable tools |

---

## Data Flow: User Prompt → Response

```
1. main.py (or groupchat_daemon.py)
   └─ loads manifest, creates MemoryStore, wires ToolRegistry
   └─ creates Mind(manifest, memory, tools, bus, session_store)

2. Mind.run_task(task)
   a. Build system prompt:
      - STATIC:      base_prompt from manifest.resolved_system_prompt()
      - STABLE:      boot_context_str (handoff + pinned memories)
      - SEMI-STABLE: auto_search results appended last
      (ordering matters: static prefix → cache hit rate)
   b. record_turn() in session_store (topic extraction, 16 words)
   c. Append user message to self._messages
   d. Build tools list from manifest.enabled_tool_names()

3. Tool-use loop (max 30 iterations):
   a. _call_model(system_prompt, tools_list)
      → anthropic SDK → LiteLLM proxy → M2.7 / other model
   b. Extract text blocks → update final_text
   c. Extract tool_use blocks → _execute_tool_calls()
      - read_only tools: run concurrently (asyncio.gather)
      - write tools: run sequentially
   d. Append tool results as user message
   e. Loop until end_turn or no tool_use blocks

4. Loop 1 (if self_modification_enabled):
   Store 200-char summary of final_text to memory
   tags: ['loop-1', 'task-result']

5. Return final_text
```

---

## mind.py

The agent loop. Stateful: holds message history in `self._messages`. One `Mind` instance per running mind (primary or sub-mind).

Key methods:
- `run_task(task)` — Execute one task. Returns final text.
- `_call_model()` — Single API call with full message history
- `_execute_tool_calls()` — Dispatch read-only tools concurrently, write tools sequentially
- `_log_cache_stats()` — Log prompt cache hit/miss from response metadata
- `cache_stats` property — Accumulated cache stats for this session
- `stop()` — Signal the loop to exit

**Cache optimization note:** The system prompt is structured in cache-optimal order: STATIC (base prompt, always same) → STABLE (boot context, changes per session) → SEMI-STABLE (memory search results, changes per turn). LiteLLM caches the stable prefix. Never put dynamic content before static content.

---

## memory.py

The persistence layer. SQLite database with FTS5 virtual table for full-text search (BM25 ranking). Every mind shares the same `memory.db` but memories are tagged by `agent_id`.

**Schema tables:**
- `memories` — Main memory store. Columns: id, agent_id, domain, session_id, memory_type, title, content, source_path, created_at, confidence, tags, access_count, last_accessed_at, depth_score, is_pinned, human_endorsed
- `memories_fts` — FTS5 virtual table. Automatically synced via INSERT/UPDATE/DELETE triggers.
- `memory_tags` — Tag index. `(memory_id, tag)` pairs for efficient tag lookup.
- `session_journal` — Session lifecycle. start_time, end_time, turn_count, topics (JSON array), summary.
- `skills` — Skill registry. skill_id, file_path, usage_count, effectiveness.
- `agent_registry` — Agent registry. agent_id, manifest_path, spawn_count, last_active_at.

**Memory types:** `learning` | `decision` | `error` | `handoff` | `observation`

**Depth score formula:**
```
depth = (min(access_count,20)/20 * 0.3)
      + (recency_score * 0.25)     # 1.0=today, 0.5=this month, 0.1=older
      + (is_pinned * 0.2)
      + (human_endorsed * 0.15)
      + (confidence_score * 0.1)   # HIGH=1.0, MEDIUM=0.6, LOW=0.3
```

Key methods:
- `store(memory)` → Insert memory + tags
- `search(query, agent_id, limit)` → FTS5 BM25 ranked search
- `touch(memory_id)` → Increment access_count (triggers depth score update at session end)
- `pin(memory_id)` / `unpin()` → Always-in-context flag
- `get_pinned(agent_id)` → Retrieve pinned memories
- `start_session()` / `record_turn()` / `end_session()` → Session journal lifecycle
- `register_skill()` / `touch_skill()` → Skill usage tracking

---

## manifest.py

YAML → Pydantic validation → `MindManifest`. Single source of truth for what a mind is.

`MindManifest.from_yaml(path)` does three things:
1. Parse YAML
2. Expand environment variables (`$VAR` and `${VAR}`) recursively through the entire dict
3. Resolve relative paths (system_prompt_path, auth.keypair_path, memory.db_path, sub_minds[*].manifest_path) to absolute, anchored at the manifest file's directory

Fields:
- `mind_id` — Unique identifier (e.g., "primary", "research-lead")
- `role` — "conductor-of-conductors" | "team-lead" | "specialist"
- `model.preferred` — LiteLLM routing name (e.g., "minimax-m27", "gemini-flash-free")
- `tools[]` — Enabled tools with optional constraints
- `auth.keypair_path` — Ed25519 keypair JSON for AgentAuth
- `memory.db_path` — SQLite database path
- `memory.auto_search_before_task` — Whether to inject memory search results each turn
- `memory.max_context_memories` — How many search results to inject
- `sub_minds[]` — Sub-mind references (mind_id + manifest_path)

---

## session_store.py

Wraps `MemoryStore.session_journal` operations. Created fresh each run. Tracks the current session's turn count and topics.

The `record_turn(topic)` call in `Mind.run_task()` records up to 16 words of the task as a topic. This builds a readable session history for handoffs.

---

## context_manager.py

Formats memory search results into the system prompt's SEMI-STABLE section. Controls how much context memories consume and how they're presented to the model.

---

## spawner.py — SubMindSpawner

Launches sub-mind processes in tmux windows via libtmux.

```
spawner.ensure_session()    # get/create tmux session "aiciv-subminds"
spawner.spawn(mind_id, manifest_path)
    → new tmux window named mind_id
    → runs: python3 run_submind.py --manifest <path> --id <mind_id>
    → returns MindHandle(mind_id, pane_id, pid, zmq_identity)
spawner.terminate(handle)   # kill the tmux window
spawner.is_alive(handle)    # check process status
spawner.capture_output(handle, lines)  # read tmux pane output
```

**Architecture limitation:** Sub-minds spawned by `run_submind.py` do NOT receive a PrimaryBus or SubMindSpawner. They cannot spawn their own sub-minds. This is the Build 7 candidate.

---

## registry.py

In-memory `MindRegistry`. Tracks live sub-minds by `MindHandle`. Not persisted — rebuilt each session. The persistent agent registry lives in `MemoryStore.agent_registry`.

---

## interactive.py

Interactive REPL for direct human↔Root conversation. Used when running `main.py` without `--task`. Reads input from stdin, calls `Mind.run_task()`, prints response.
