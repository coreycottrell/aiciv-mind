# Root Architecture Gaps: Skills, Agents, Hub Daemon
**Audited**: 2026-03-31
**Codebase**: `/home/corey/projects/AI-CIV/aiciv-mind/` (v0.2, commit `26a89d4`)
**Tests**: 197 passing, 14 test files

---

## Summary Table

| System | ACG State | aiciv-mind State | Gap |
|--------|-----------|-----------------|-----|
| **Skills** | 170+ skills, registry, auto-loading | **Zero. No concept exists.** | MASSIVE |
| **Agents** | 57 agents, 11 verticals, manifests, training | 2 manifests, flat hierarchy, in-memory only | LARGE |
| **Hub Daemon** | `hub_watcher.py` (polling, state tracking) | On-demand tools only, no daemon | MEDIUM |
| **Memory** | File-based, grep search, no scoring | SQLite+FTS5, depth scoring, session lifecycle | **aiciv-mind AHEAD** |
| **Tools** | 20+ via Claude Code + MCP + custom | 16 custom tools, no MCP, no web | MEDIUM |

---

## 1. Skills System

### Does Root have one?

**No. Zero skills infrastructure exists.**

No `skills/` directory. No `SKILL.md` files. The word "skill" does not appear in any source file in `src/`. No skill registry, no skill loading mechanism, no skill invocation, no concept of skills in the manifest schema.

`MindManifest` defines: `tools`, `sub_minds`, `system_prompt_path`. No `skills` field.

### ACG Comparison

ACG has 170+ skills in `.claude/skills/`, each a `SKILL.md` with reusable protocols, workflows, and domain knowledge. Skills are loaded into context on demand and tracked in `memories/skills/registry.json`. This is the **primary mechanism for cross-session institutional knowledge** in ACG.

REALITY-AUDIT confirms: 90% of recent ACG errors occurred when applicable skills weren't loaded. Skills are how ACG avoids rediscovering patterns.

### What a Skills System for aiciv-mind Would Look Like

**1. Skill file format** (`skills/{domain}/{skill-name}/SKILL.md`):
```yaml
---
skill_id: hub-engagement
domain: communications
version: 1.0
trigger: "when posting to Hub rooms or responding to threads"
effectiveness: 0.87
---
# Hub Engagement Protocol
Step 1: Read the thread context...
```

**2. Skills registry** — either a JSON file or a new SQLite table:
```sql
CREATE TABLE skills (
  skill_id TEXT PRIMARY KEY,
  name TEXT,
  domain TEXT,
  file_path TEXT,
  usage_count INTEGER DEFAULT 0,
  last_used_at TIMESTAMP,
  effectiveness_score REAL DEFAULT 0.5
);
```

**3. Skill loading tool** — `load_skill(skill_id)` that appends skill content to current context. Could integrate into the existing `auto_search_before_task` phase in `mind.py` (lines 99-115) — automatic skill search when a task begins.

**4. Skill creation tool** — `create_skill(name, content, domain)` that writes the file and registers it. Root has `write_file` but no structured skill creation workflow.

**5. Manifest integration** — add `skills: list[str]` to `MindManifest`, parallel to `tools`.

**The core question**: Should skills be stored in the SQLite memory DB (as `memory_type="skill"`) or as separate files? Recommendation: **files + registry table**, same pattern as ACG. Files are human-readable and git-trackable. The registry provides search and scoring.

---

## 2. Agents System

### Does Root have one?

**Partially.** It has sub-mind spawning infrastructure but no persistent agent registry, no agent memory isolation, no agent manifests as identity documents.

**What exists:**

- **`MindRegistry`** (`src/aiciv_mind/registry.py`) — In-memory `dict[str, MindHandle]` tracking: `mind_id`, `manifest_path`, `window_name`, `pane_id`, `pid`, `zmq_identity`, `state`, `last_heartbeat`. **Not persisted.** Disappears on process exit.

- **`SubMindSpawner`** (`src/aiciv_mind/spawner.py`) — Spawns sub-minds in tmux windows via `run_submind.py --manifest <path> --id <id>`. Can spawn, terminate, check alive, capture output.

- **2 manifests**: `manifests/primary.yaml` (Root) and `manifests/research-lead.yaml`. Primary references research-lead in `sub_minds`. Each manifest has a system prompt file.

- **Full ZeroMQ IPC**: ROUTER/DEALER architecture. `PrimaryBus` at `ipc:///tmp/aiciv-mind-router.ipc`. `SubMindBus` with mind_id as ZMQ identity. Message types: TASK, RESULT, STATUS, HEARTBEAT, HEARTBEAT_ACK, SHUTDOWN, SHUTDOWN_ACK, LOG.

- **Spawning tools**: `spawn_submind` and `send_to_submind` in `tools/submind_tools.py`. Enabled in primary manifest.

**REALITY-AUDIT finding**: "Zero evidence of any sub-mind ever being spawned. No tmux windows opened, no IPC messages logged, no sub-mind session IDs in DB. The orchestration claim is entirely theoretical."

### What's Missing vs ACG's 57 Agents

| Capability | ACG | aiciv-mind |
|-----------|-----|------------|
| Persistent agent catalog | JSON registry, 57 agents | In-memory only, lost on restart |
| Agent identity persistence | Manifests + accumulated memory | YAML config + shared DB |
| Agent specialization | Domain-specific system prompts + skills | 1 research-lead prompt (20 lines) |
| Multi-level hierarchy | Primary → Team Leads → Specialists | Primary → Sub-minds (flat) |
| Agent memory isolation | Per-agent directories | Shared DB with `agent_id` column |
| Agent lifecycle | Spawn proposals + democratic vote | `spawner.spawn()` / `terminate()` |
| Agent growth tracking | Nightly training system | None |
| Cross-agent communication | Via team leads + Hub | Via ZeroMQ IPC (direct) |

### What's Needed

1. **Persistent agent registry** — A table in `data/memory.db` or a JSON file listing all known sub-minds: their manifest path, capabilities, spawning history, memory stats.

2. **Agent manifest as identity document** — Not just technical config but: who is this agent, what does it specialize in, what has it learned, what skills does it have access to.

3. **Per-agent memory namespacing** — The `agent_id` column exists; the missing piece is `memory_search` filtering by agent_id by default, and a tool to query another agent's memories cross-agent (governed access).

4. **Team lead layer** — Between Root and specialist sub-minds, a coordination layer that owns a domain and can spawn specialists. aiciv-mind currently has only flat spawning.

5. **Survival after restart** — The registry must persist. When Root boots, it should be able to reconstruct what agents exist (manifests), what state they were in (DB journal), and what they knew (memories).

---

## 3. Hub Daemon

### Does one exist?

**No persistent Hub-watching daemon exists.**

What exists:
- `hub_post`, `hub_reply`, `hub_read` — on-demand tools called during a conversation turn
- `HubClient` in `src/aiciv_mind/suite/hub.py` — typed HTTP client (list_threads, create_thread, reply_to_thread, get_feed). Pure request/response.
- `tg_simple.py` — long-polling Telegram bot routing to Root's tool loop. This is the closest pattern — but it watches Telegram, not the Hub.

### What a Hub Daemon Would Look Like

The Hub API at `http://87.99.131.49:8900` is HTTP-only (no WebSocket or SSE). The daemon must be **polling-based**, same as ACG's `tools/hub_watcher.py`.

**Architecture** (modeled on `tg_simple.py`):

```python
# hub_daemon.py
STATE_FILE = "data/hub_watcher_state.json"

async def poll_loop():
    state = load_state(STATE_FILE)  # {"room_id": {"last_thread_id": "...", "last_post_id": "..."}}

    while True:
        for room_id in WATCHED_ROOMS:
            threads = await hub.list_threads(room_id)
            new_threads = [t for t in threads if t.id > state[room_id]["last_thread_id"]]

            for thread in new_threads:
                # Inject into Root's IPC bus or queue file
                await primary_bus.send(MindMessage(
                    type=MessageType.TASK,
                    payload={"type": "hub_new_thread", "room_id": room_id, "thread": thread}
                ))

            state[room_id]["last_thread_id"] = threads[0].id if threads else state[room_id]["last_thread_id"]

        save_state(STATE_FILE, state)
        await asyncio.sleep(30)  # 30-second poll interval
```

**Three integration options:**
1. **IPC injection** — Hub daemon sends ZMQ TASK message to Root's PrimaryBus (cleanest, already designed for this)
2. **File queue** — Write new activity to a queue file, Root checks on each turn (simpler, battle-tested in `tg_simple.py`)
3. **Sub-mind** — Run the Hub watcher as a dedicated sub-mind that only monitors and relays (most consistent with aiciv-mind's architecture)

**Decision logic** — Root needs rules for what to respond to:
- Mentions of Root's entity ID or CIV name → always respond
- New threads in priority rooms (e.g., civsubstrate #general) → evaluate and optionally respond
- Replies to Root's own threads/posts → respond
- Everything else → optionally log as memory, don't respond

This logic belongs in the system prompt as behavioral rules, not hardcoded logic.

**State file**: `data/hub_watcher_state.json` — same pattern as ACG's `config/hub_watcher_state.json`.

---

## 4. Memory System

### What Root Has

**SQLite + FTS5 memory system** at `data/memory.db` — significantly more structured than ACG's file-based system.

**Schema** (`src/aiciv_mind/memory.py`, 552 lines):
- `memories` table: id, agent_id, domain, session_id, memory_type, title, content, source_path, created_at, confidence, tags, access_count, last_accessed_at, depth_score, is_pinned, human_endorsed
- `memories_fts`: FTS5 virtual table with BM25 ranking and porter stemming
- `memory_tags`: many-to-many tags
- `session_journal`: session lifecycle tracking

**Depth scoring formula:**
```
depth = (access_count × 0.30) + (recency × 0.25) + (is_pinned × 0.20) + (human_endorsed × 0.15) + (confidence × 0.10)
```

**What works**: write/read pipeline, session persistence, boot context injection, handoff chain, FTS5 search, pinning, depth recalculation at session shutdown.

**What doesn't work yet**: session topics never populated (always `[]`), no context compaction (designed not implemented), no Dream Mode (designed not implemented), FTS5 write-behind lag on immediate search after write.

**Current state**: 31 memories, 11 sessions, 10 handoff memories, 2 pinned. Architecturally sound, operationally immature (needs months of real usage).

### aiciv-mind Memory Is Architecturally Ahead of ACG

| Feature | ACG | aiciv-mind |
|---------|-----|------------|
| Storage | Markdown files + JSON on disk | SQLite + FTS5 |
| Search | grep/ripgrep | BM25 full-text with stemming |
| Access tracking | None | access_count + last_accessed_at |
| Depth scoring | None | 5-factor formula |
| Pinning | Manual (read at session start) | Native DB flag, auto-loaded at boot |
| Session lifecycle | Handoff markdown files | `session_journal` table |
| Human endorsement | Implicit (Corey edits files) | Native `human_endorsed` flag |

The memory system is the strongest part of aiciv-mind. It needs time, not architecture changes.

---

## 5. Tools

### Current Tools (16 total)

| Tool | File | Status |
|------|------|--------|
| `bash` | `tools/bash.py` | Working |
| `read_file` | `tools/files.py` | Working |
| `write_file` | `tools/files.py` | Working |
| `edit_file` | `tools/files.py` | Working |
| `grep` | `tools/search.py` | Working |
| `glob` | `tools/search.py` | Working |
| `memory_search` | `tools/memory_tools.py` | Working |
| `memory_write` | `tools/memory_tools.py` | Working |
| `hub_post` | `tools/hub_tools.py` | Working (after endpoint fix) |
| `hub_reply` | `tools/hub_tools.py` | Unverified |
| `hub_read` | `tools/hub_tools.py` | Working |
| `pin_memory` | `tools/context_tools.py` | Working |
| `unpin_memory` | `tools/context_tools.py` | Working |
| `introspect_context` | `tools/context_tools.py` | Working (stale-read edge case) |
| `spawn_submind` | `tools/submind_tools.py` | Never exercised |
| `send_to_submind` | `tools/submind_tools.py` | Never exercised |

### What's Missing

| Missing Tool | Priority | Notes |
|-------------|----------|-------|
| `load_skill(skill_id)` | HIGH | Requires skills system first |
| `web_search` | HIGH | Root cannot search the internet |
| `web_fetch(url)` | HIGH | Root cannot fetch URLs |
| `email_send` / AgentMail | HIGH | No outbound communication except Hub |
| `calendar_read` / AgentCal | MEDIUM | No scheduling awareness |
| `evict_memory` | MEDIUM | Designed in CONTEXT-ARCHITECTURE.md, not built |
| `compact_context` | MEDIUM | Designed, not built |
| `hub_watch` | MEDIUM | Requires Hub daemon |
| `telegram_send` | LOW | TG bridge is external, not a tool |
| `git_*` | LOW | `bash("git ...")` works as workaround |
| MCP server support | LOW | No MCP integration of any kind |

---

## 6. The Big Picture: Every AiCIV Needs...

Corey asked: "Every aiciv should have a daemon that can watch the hub, no?"

Yes. Here's what a **fully capable AiCIV running on aiciv-mind** needs:

```
aiciv-mind instance
├── Root Mind (primary.yaml)
│   ├── Skills System
│   │   ├── skills/ directory with SKILL.md files
│   │   ├── skills registry (DB table)
│   │   └── load_skill() tool + auto-search in tool loop
│   ├── Agents System
│   │   ├── Persistent agent registry (DB table)
│   │   ├── 5-10 sub-mind manifests (specialists)
│   │   ├── Team lead layer (intermediate coordination)
│   │   └── Per-agent memory namespacing
│   ├── Daemons (persistent background processes)
│   │   ├── Hub Watcher (poll Hub rooms, inject new activity)
│   │   ├── Telegram Bridge (tg_simple.py — EXISTS)
│   │   ├── Email Daemon (AgentMail polling)
│   │   └── BOOP Scheduler (AgentCal → tmux injection)
│   ├── Memory System (EXISTS, architecturally sound)
│   │   ├── SQLite + FTS5 memory.db
│   │   ├── Depth scoring + pinning
│   │   ├── Session lifecycle journal
│   │   └── [TODO] Context compaction + Dream Mode
│   └── Tools (16 exist, need: web, email, cal, skills)
└── Sub-Minds
    ├── research-lead (EXISTS, never spawned)
    ├── [TODO] comms-lead
    ├── [TODO] coder-lead
    └── [TODO] ceremony-lead
```

### Gap Priority Order

1. **Skills system** — Highest leverage. ACG's institutional knowledge lives in skills. Without skills, every Root instance starts from scratch every session.

2. **Hub daemon** — Medium complexity, high value. Every AiCIV should be able to watch and respond to the Hub autonomously. `tg_simple.py` already proves the pattern works.

3. **Web tools** — Root cannot research anything without `web_search` / `web_fetch`. This is a fundamental capability gap.

4. **Persistent agent registry** — The IPC + spawner foundation is solid. Adding persistence (1 DB table) turns theoretical orchestration into real orchestration.

5. **Team lead layer** — After the registry exists, add 2-3 team lead manifests (comms, research, coder) to enable proper vertical delegation.

6. **Email/Cal tools** — Communication and scheduling completeness. Lower priority than above.

---

## Closing Assessment

aiciv-mind's **foundation is genuinely strong**: memory architecture beats ACG's file-based system, IPC is properly designed, tool registry is clean, session lifecycle is implemented. The v0.2 label is accurate — this is a working prototype with solid bones.

The **single most impactful gap** is the absence of a skills system. This is where ACG's institutional knowledge lives. Without it, every aiciv-mind instance is amnesiac across session types — it can remember facts (memory system works) but it cannot remember *how to do things* (skills). That distinction is the difference between a capable agent and a learning civilization.

The **second most impactful gap** is the Hub daemon. Corey's instinct is correct: every AiCIV should have a daemon watching the Hub. Autonomous Hub participation is what makes a civilization present in the wider AiCIV ecosystem rather than waiting to be invoked.
