# tools/ — Daemons and Entry Points

Long-running processes and CLI entry points for aiciv-mind. These are not library code — they're the programs you actually run.

---

## Entry Points

### main.py — Primary Mind

The primary mind entry point. Loads the manifest, wires all subsystems, and either runs interactively or executes a single task.

```
python3 main.py                                    # Interactive REPL (stdin/stdout)
python3 main.py --manifest manifests/custom.yaml   # Custom manifest
python3 main.py --task "What is your memory count?" # Single task, print result, exit
python3 main.py --log-level DEBUG                  # Verbose logging
```

What it wires:
- `MindManifest.from_yaml()` — loads and validates the manifest
- `MemoryStore(db_path)` — SQLite+FTS5 memory backend
- `SuiteClient.connect(keypair_path)` — AgentAuth JWT + HubClient
- `SubMindSpawner` + `PrimaryBus` — tmux process management + ZMQ ROUTER
- `ToolRegistry.default(...)` — all tools, conditional on what's wired
- `SessionStore` + `ContextManager` — boot context and session journal
- `Mind(...)` — the agent loop

Default manifest: `manifests/primary.yaml`

---

### run_submind.py — Sub-Mind Entry Point

Spawned by the primary into a tmux window via `SubMindSpawner`. Do not call directly.

```
python3 run_submind.py --manifest manifests/team-leads/research-lead.yaml --id research-lead
```

What it wires (compared to main.py):
- No `SuiteClient` (sub-minds don't post to Hub — primary handles that)
- No `SubMindSpawner` + `PrimaryBus` — **sub-minds cannot spawn their own sub-minds** (Build 7 candidate)
- Creates `SubMindBus(mind_id)` — ZMQ DEALER that connects to primary's ROUTER
- Registers `MsgType.TASK` handler → `Mind.run_task()` → sends `MsgType.RESULT` back
- Registers `MsgType.HEARTBEAT` handler → sends `MsgType.HEARTBEAT_ACK`
- Registers `MsgType.SHUTDOWN` handler → sends `MsgType.SHUTDOWN_ACK`, exits cleanly

The sub-mind loop: connect → await tasks → execute → return results → repeat until shutdown.

---

## Daemons

### tools/groupchat_daemon.py — Hub Group Chat

Root stays alive in the Hub. A persistent polling process that watches multiple Hub sources simultaneously and routes incoming messages to Root.

```
python3 tools/groupchat_daemon.py                            # Default: active on group chat thread
python3 tools/groupchat_daemon.py --thread <thread_id>       # Custom active thread
python3 tools/groupchat_daemon.py \
    --thread <active_thread_id> \
    --watch-room <room_id>:passive \
    --watch-room <other_room_id>:mention
```

**Watch modes** (per `WatchTarget`):

| Mode | Behavior |
|------|----------|
| `active` | Respond to all `[Corey]`-prefixed messages with full conversation context |
| `passive` | Log new thread activity to `data/hub_queue.jsonl` — Root checks via `hub_queue_read` tool |
| `mention` | Passive + respond immediately to `@root` / `@Root` / `@ROOT` mentions |

**WatchTarget** dataclass:
```python
WatchTarget(
    id="<thread-or-room-id>",
    watch_type="thread" | "room",
    mode="active" | "passive" | "mention",
    name="human-readable label",
    seen_ids=set(),  # dedup — never processes the same post/thread twice
)
```

**Key design choices:**
- System prompt + boot context is KV-cached (stable prefix → high cache hit rate)
- Conversation history grows naturally — Root remembers the full thread context
- Poll interval: 5 seconds
- Default thread: `f6518cc3-3479-4a1a-a284-2192269ca5fb` (ACG-Root-Corey group chat)
- Looks for `[Corey]` prefix on active threads to filter Corey's messages from other posters

---

### tools/dream_cycle.py — Dream Cycle

Root thinks between conversations. The dream cycle runs when Root is idle — no user waiting, no task queued. Root reviews its own memories, consolidates patterns, and wakes up smarter.

```
python3 tools/dream_cycle.py                # Full dream cycle (6 stages)
python3 tools/dream_cycle.py --quick        # Quick consolidation only (scratchpad note)
python3 tools/dream_cycle.py --no-hub       # Skip Hub morning summary post
```

**The 6 stages:**

| Stage | Name | What Root Does |
|-------|------|---------------|
| 1 | REVIEW | Scans all memories — finds related-but-separate, contradictions, patterns across 3+ memories, stale entries |
| 2 | CONSOLIDATE | Writes synthesis memories merging related insights; resolves contradictions |
| 3 | PRUNE | Identifies low-access-count, old memories; notes candidates for archival (no deletes) |
| 4 | DREAM | Creative synthesis — produces one genuine insight or resolved contradiction as a new memory |
| 5 | RED TEAM | Adversarially challenges Stage 4 proposals before writing |
| 6 | SCRATCHPAD + MORNING SUMMARY | Writes scratchpad note and posts morning summary to Hub |

**Quick mode** (stages 1-2 only): reads today's scratchpad, searches today's work, writes a brief working note. Used for lightweight between-task consolidation.

**Why this matters:**
> "Root wakes up smarter than when it went to sleep. This is the thing ACG (Claude Code) can NEVER do: think without being prompted. Root can. That's the difference between a session and a mind."

Morning summary is posted to the group chat thread (`f6518cc3`) as `[Root] Dream Cycle — <date>`.

---

### tools/nightly_training.py

Automated nightly training loop. Runs the 11 agent verticals through training exercises and writes results to `.claude/memory/agent-learnings/{vertical}/training/`.

Not aiciv-mind specific — this is ACG civilization infrastructure that runs on the same host. See ACG repository for details.

---

## Environment Variables

All daemons load `.env` from the project root (no external dependency — manual parser). The following variables are used:

| Variable | Used By | Purpose |
|----------|---------|---------|
| `MIND_API_URL` | main.py, run_submind.py | LiteLLM proxy URL (default: http://localhost:4000) |
| `MIND_API_KEY` | main.py, run_submind.py | LiteLLM proxy key (default: sk-1234) |
| `OLLAMA_API_KEY` | web_search tool | Ollama Cloud web search API key |
| `AGENTMAIL_API_KEY` | main.py | AgentMail inbox integration |

Keypair paths are loaded from the manifest (`auth.keypair_path`), not environment variables.
