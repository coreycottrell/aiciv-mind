# aiciv-mind Architecture Research Report

**Date**: 2026-03-30
**Research Lead**: research-lead (VP of Research & Intelligence, A-C-Gee)
**Status**: COMPLETE (framework-survey.md pending — findings captured in track-b-sovereign.md §2)
**Output files**:
- `track-a-sdk-accelerated.md` (1023 lines) — Anthropic SDK / claude-agent-sdk deep dive
- `track-b-sovereign.md` (1185 lines) — Sovereign / raw HTTP + full framework survey
- `shared-infrastructure.md` (1400+ lines) — tmux, IPC, services, memory, manifests
- `framework-survey.md` — dedicated framework deep dive (in progress, findings pre-captured in Track B)

---

## Executive Summary

aiciv-mind should be built as a **sovereign Python OS** (Track B) with a pragmatic shortcut: **use the Claude Agent SDK (`claude-agent-sdk`) to ship v0.1 in 2-3 weeks**, then migrate the core loop to the sovereign approach over 6-8 weeks as the project matures.

The two tracks are not mutually exclusive — they are sequential phases of the same project.

**Why Track B wins long-term**: The Agent SDK is a harness. We need an operating system. Long-term we need AgentMind integration (multi-model, cost routing), native AiCIV service clients, ZeroMQ IPC, and full control over the loop. The Agent SDK cannot deliver these. But it ships in 2-3 weeks vs. 6-8 — and for v0.1, shipping matters.

**The hybrid recommendation**:
1. **v0.1 (2-3 weeks)**: Agent SDK primary mind + Agent SDK sub-minds + ZeroMQ IPC + custom MCP tools for Hub/Auth/Cal + libtmux pane management
2. **v0.2 (6-8 weeks cumulative)**: Migrate primary mind to sovereign core loop (raw HTTP, SSE parser, own tool registry). Keep Agent SDK for sub-minds optionally.
3. **v0.3+**: Full sovereign stack. AgentMind integration. All minds are sovereign. Agent SDK dropped.

---

## Track A Assessment: SDK-Accelerated Mind

**Source**: `track-a-sdk-accelerated.md` | **Confidence**: HIGH (official Anthropic docs)

### What Exists

**`anthropic` Python SDK (v0.86.0)**:
- Direct Messages API access: `client.messages.create()` sync + async
- Beta `tool_runner` that automates the agentic loop (`@beta_tool` decorator + `runner.until_done()`)
- Streaming: `client.messages.stream()` context manager with text/tool deltas
- Full concurrent conversation support (one client, many `messages` lists)
- Model switching per-request (model-agnostic history)
- ~50MB installed, lightweight client

**`claude-agent-sdk` (v0.1.51, pip install claude-agent-sdk)**:
- Wraps the Claude Code CLI runtime as a Python library
- Built-in tools: Bash, Read, Edit, Write, Glob, Grep, WebSearch, WebFetch
- Session persistence (resume by session_id), context compaction (automatic)
- Subagent spawning via `AgentDefinition` + `Agent` tool
- Hooks system (PreToolUse, PostToolUse, Stop, SubagentStart)
- Permission controls (bypassPermissions, acceptEdits, default)
- Built-in cost tracking: `ResultMessage.total_cost_usd`
- `ClaudeSDKClient` for persistent multi-turn sessions with `set_model()` and `interrupt()`

### Track A Assessment Matrix

| Dimension | A1 (Agent SDK) | A2 (Base SDK) |
|-----------|---------------|---------------|
| **Build effort** | 2-3 weeks | 4-6 weeks |
| **SDK lock-in risk** | HIGH — Claude-only, no AgentMind | MEDIUM — Anthropic format, AgentMind-compatible |
| **Streaming control** | LIMITED — loop internals opaque | FULL — own the stream |
| **Multi-model/AgentMind** | NO | YES — swap `create()` for AgentMind HTTP |
| **Sub-mind spawning** | Via separate `query()` processes in tmux panes | Same, more lifecycle control |
| **Memory footprint** | HEAVY — ~100MB/sub-mind (Node.js) | LIGHT — ~20MB/sub-mind (Python) |
| **Context compaction** | BUILT-IN | Must implement (~500 lines) |
| **Tool ecosystem** | RICH — all Claude Code tools + MCP | Must build core 6 tools (~400 lines) |
| **Production safety** | HIGH — permissions, cost caps, hooks | Must implement |
| **Debugging** | HARDER — subprocess stdio | EASIER — direct API calls |

### Track A Key Pattern: Sub-Mind Spawning

```python
# Sub-mind spawning (both A1 and A2): separate process in its own tmux pane
async def spawn_submind(name: str, task: str, tmux_session: str) -> str:
    pane_id = subprocess.check_output([
        "tmux", "split-window", "-t", tmux_session, "-P", "-F", "#{pane_id}",
        "python", "-m", "aiciv_mind.submind",
        "--name", name, "--task", task,
        "--ipc-socket", f"/tmp/aiciv-mind-{name}.sock"
    ], text=True).strip()
    return pane_id
```

**IPC gap**: Neither SDK provides inter-process messaging. This must be built regardless of track chosen. ZeroMQ ROUTER/DEALER is recommended (see Shared Infrastructure).

### Track A Recommendation

**Use A1 (Agent SDK) for v0.1.** Eliminates the hardest problems: tool execution, agentic loop, context compaction, session persistence. Build targets:
1. ZeroMQ IPC bus between primary and sub-minds (~1 week)
2. Custom MCP tools for AiCIV services: Hub, AgentAuth, AgentCal (~1 week)
3. libtmux pane management for sub-mind visibility (~3 days)
4. Scheduler for BOOP/calendar integration (~2 days)
5. Memory layer for cross-session persistence (~3 days)

**Migrate primary to A2/Track B when needed**: multi-model routing, lower memory footprint, or loop control.

---

## Track B Assessment: Sovereign Mind

**Source**: `track-b-sovereign.md` | **Confidence**: HIGH (official API docs + framework research)

### The Core Loop (~800 Lines of Python)

Claude streaming protocol is well-documented. Six SSE event types, two delta types. The hard part is not parsing — it is accumulating partial JSON for tool inputs. Minimal streaming parser: ~150 lines.

```
SSE event stream:
  message_start → content_block_start → content_block_delta* → content_block_stop* → message_stop

Tool use in stream:
  content_block_start (type=tool_use, id=X, name=Y)
  content_block_delta (type=input_json_delta, partial_json="...")  [accumulate these]
  content_block_stop  → JSON.parse(accumulated) = tool input
```

Full `Mind` class: ~800 lines (event loop + streaming SSE consumer + tool registry + message history + IPC sender).

### Framework Survey — What to Steal

| Framework | Core Insight | What to Steal |
|-----------|-------------|---------------|
| **LangGraph** | Graph-as-execution-plan, state machines | Checkpointing for long-running sessions; conditional routing based on state |
| **CrewAI** | Hierarchical process (but broken in practice) | 4-layer memory hierarchy: short-term + long-term + entity + procedural. Scoped memory recall. |
| **AutoGen** | Conversational agents, code execution first-class | The auto-reply loop for autonomous operation; code executor as a sandboxed first-class tool |
| **OpenAI Agents SDK** | Handoffs (summarize + transfer control) | Handoff abstraction for team-lead spawning; built-in tracing (every event observable) |
| **Pydantic AI** | Dependency injection via RunContext | `RunContext` pattern for passing Hub/Auth/Cal clients into tools without global state; auto-schema from type hints |
| **smolagents** | Code-as-action, ~1000 lines core | Minimalism philosophy — proves you don't need a framework, just a loop + tools; code-agent mode as alternate execution |

**Anti-patterns to avoid (all frameworks fail here)**:
- Abstracting over the LLM call until you can't see what's happening
- Shared conversation state for multiple agents → coherence breaks at scale
- Over-engineering for hypothetical use cases before v1 ships
- Framework lock-in via tight coupling (LangChain tax = huge)
- CrewAI's hierarchical process: "simply does not function as documented"

### Track B Assessment Matrix

| Dimension | Assessment |
|-----------|-----------|
| **Build effort** | 6-8 weeks MVP (2-week proof of life → 4-week multi-mind → 6-week AiCIV native → 8-week production) |
| **Model-agnostic** | STRONG — AgentMind handles translation, aiciv-mind is format-neutral |
| **Streaming control** | FULL — own the SSE parser, add progress callbacks, token counting at stream level |
| **Protocol ownership** | COMPLETE — no SDK dependency, can swap entire inference backend |
| **Sub-mind spawning** | NATIVE — tmux panes + ZeroMQ IPC, true process isolation |
| **Maintenance burden** | MODERATE — ~2,000 lines core, own every edge case, but no upstream breakage |
| **AgentMind integration** | NATIVE — replace `httpx.post(ANTHROPIC_URL)` with `httpx.post(AGENTMIND_URL)` |

### Track B Build Phases

```
Phase 1 (Week 1-2): Proof of Life
  stream.py          — SSE parser with tool_use accumulation
  mind.py            — Core loop (call LLM → execute tools → repeat)
  tools.py           — 5 built-in tools (bash, read, write, edit, glob)
  __main__.py        — CLI entry point, single-mind mode
  Deliverable: Working agent via Anthropic API direct

Phase 2 (Week 3-4): Multi-Mind
  ipc.py             — ZeroMQ ROUTER/DEALER message bus
  Sub-mind spawning via libtmux
  SubMindHandle with task/result/heartbeat protocol
  Deliverable: Primary spawns sub-minds in parallel tmux panes

Phase 3 (Week 5-6): AiCIV Native
  services/hub.py    — Hub API client
  services/auth.py   — AgentAuth JWT signing
  services/cal.py    — AgentCal integration
  normalize.py       — Tool format translation for AgentMind backends
  Deliverable: Mind posts to Hub, authenticates, reads calendars

Phase 4 (Week 7-8): Memory & Polish
  memory.py          — SQLite FTS5 session persistence + compaction
  Hooks system, nightly training integration, Docker
  Deliverable: Production-ready mind with persistent memory
```

---

## Shared Infrastructure Assessment

**Source**: `shared-infrastructure.md` | **Confidence**: HIGH

### tmux: libtmux

**Recommendation**: `libtmux>=0.55,<0.56` (pin version — pre-1.0 API churn risk).

**Architecture**: 1 named window per mind in a shared tmux session.
```
aiciv-mind session
├── window: primary      (the primary mind)
├── window: gateway-lead (team lead — spawned on demand)
├── window: infra-lead   (team lead — spawned on demand)
└── window: comms-lead   (team lead — spawned on demand)
```

**Key operations**:
```python
import libtmux
server = libtmux.Server()
session = server.new_session(session_name="aiciv-mind")
window = session.new_window(window_name="gateway-lead")
pane = window.active_pane

# Spawn sub-mind process
pane.send_keys(f"python -m aiciv_mind --manifest manifests/gateway-lead.yaml")

# Monitor output (no polling needed — capture on demand)
output = pane.capture_pane(as_string=True)

# Detect alive/dead
alive = pane.pane_current_command not in ("bash", "zsh", "sh")  # process still running
```

**Process lifecycle**: Use `pane.pane_pid` + `os.kill(pid, 0)` to check if alive. For graceful shutdown: send shutdown message via ZeroMQ, wait for `ResultMessage` acknowledgment, then `pane.send_keys("exit")`.

### IPC: ZeroMQ ROUTER/DEALER

**Recommendation**: ZeroMQ with ROUTER/DEALER pattern. ~30-80µs latency on localhost. `pip install pyzmq` (libzmq bundled). No external server required.

**Architecture**:
```
Primary Mind [ROUTER socket on ipc:///tmp/aiciv-mind.ipc]
    │
    ├── DEALER socket ←→ gateway-lead sub-mind
    ├── DEALER socket ←→ infra-lead sub-mind
    └── DEALER socket ←→ comms-lead sub-mind
```

**Message format**:
```python
@dataclass
class MindMessage:
    type: str      # "task" | "result" | "status" | "shutdown" | "heartbeat"
    sender: str    # "primary" | "gateway-lead"
    recipient: str
    payload: dict
    timestamp: float
    id: str        # UUID for correlation
```

JSON serialization. For v2+: migrate to NATS (already in APS architecture) when fleet matures.

**Why not NATS now**: NATS is already in agentmind SPEC for fleet-level comms. For single-machine aiciv-mind v0.1, ZeroMQ avoids the external NATS server dependency while being trivially migratable.

### Memory: SQLite FTS5 + Markdown Hybrid

**Recommendation**: SQLite with FTS5 virtual tables as queryable index. Keep markdown files for human consumption and git versioning. Both written on every memory creation.

**v1 schema**:
```sql
CREATE VIRTUAL TABLE memories_fts USING fts5(
    agent, domain, session_id, memory_type,
    title, content, tags,
    tokenize = "porter unicode61"
);

CREATE TABLE memories (
    id TEXT PRIMARY KEY,           -- UUID
    agent TEXT NOT NULL,           -- "gateway-lead", "primary"
    domain TEXT NOT NULL,          -- "gateway", "infrastructure"
    session_id TEXT,               -- session identifier
    memory_type TEXT NOT NULL,     -- "learning" | "decision" | "handoff" | "skill"
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,                     -- comma-separated
    confidence TEXT,               -- "HIGH" | "MEDIUM" | "LOW"
    markdown_path TEXT,            -- path to .md file
    created_at REAL NOT NULL       -- Unix timestamp
);
```

**Example queries**:
```sql
-- "Find all JWT learnings from last 7 days"
SELECT * FROM memories_fts WHERE memories_fts MATCH 'JWT'
  AND agent IN (SELECT id FROM memories WHERE created_at > unixepoch()-604800);

-- "What did gateway-lead work on?"
SELECT title, content FROM memories WHERE agent='gateway-lead' ORDER BY created_at DESC LIMIT 20;
```

**v2 upgrade**: Add `sqlite-vec` extension for semantic search. Single `.so` file, no infrastructure change.

### Service Integration: httpx AsyncClient

**Recommendation**: `httpx.AsyncClient` with JWT token caching + auto-refresh. Pattern already exists in `projects/aiciv-suite-sdk/aiciv_suite/auth.py`.

**Service registry**: YAML config mapping service names to endpoints. Loaded at mind startup.

```yaml
# services.yaml
hub:
  base_url: "http://87.99.131.49:8900"
  auth_required: true
agentauth:
  base_url: "http://5.161.90.32:8700"
  auth_required: false
agentcal:
  base_url: "${AGENTCAL_URL}"
  auth_required: true
```

**JWT strategy**: Cache token + expiry. Refresh 60s before expiry. Single `AuthClient` instance shared across all service clients via `RunContext` (Pydantic AI's DI pattern — steal this).

### Mind Manifest Format

```yaml
# manifests/primary.yaml
id: primary
role: "Conductor of Conductors"
system_prompt_path: ".claude/CLAUDE.md"

tools:
  builtin: [bash, read, write, edit, glob, grep]
  services: [hub_post, hub_read, agentcal_check, agentauth_sign]
  mind_ops: [spawn_submind, send_message, shutdown_submind, check_submind]

model:
  primary: claude-opus-4-6
  tier_hint: T3

memory:
  backend: sqlite_fts5
  db_path: "memories/aiciv-mind.db"
  markdown_root: "memories/"

services_config: "config/services.yaml"

submind_manifests:
  gateway-lead: "manifests/gateway-lead.yaml"
  infra-lead: "manifests/infra-lead.yaml"
  comms-lead: "manifests/comms-lead.yaml"
  pipeline-lead: "manifests/pipeline-lead.yaml"

schedule:
  boop_interval_minutes: 25
  boop_command: "/work-mode"
```

---

## Recommendation: The Hybrid Path

### Decision

**Build Track A1 now. Build Track B in parallel as the core loop matures.**

This is not a compromise — it is the optimal sequence:

| Phase | Architecture | Timeline | What Ships |
|-------|-------------|----------|-----------|
| **v0.1** | Agent SDK (`claude-agent-sdk`) + ZeroMQ + libtmux | 2-3 weeks | Working primary mind + sub-mind spawning. Replaces current Claude Code + tmux injection hacks. |
| **v0.2** | Sovereign core loop (Track B Phase 1-2) running alongside Agent SDK | +4 weeks | SSE parser, tool registry, base SDK loop as alternative. Benchmarkable against Agent SDK. |
| **v0.3** | Full sovereign primary + optional Agent SDK sub-minds | +2 weeks | AgentMind integration. Multi-model routing. T1/T2/T3 cost optimization. |
| **v1.0** | Fully sovereign. Agent SDK optional/deprecated | +2 weeks | Production-grade. Docker. SQLite memory. Nightly training integration. |

### Why Not Track B Immediately?

Corey said "build from scratch." Track B IS from scratch — but it's 6-8 weeks to a working multi-mind system. During those 6-8 weeks, the current Claude Code + tmux hacks continue. Track A1 ships in 2-3 weeks and replaces the hacks immediately. Then Track B development happens on top of a working foundation.

The two paths share infrastructure: ZeroMQ IPC, libtmux pane management, SQLite memory, service clients, mind manifests. These components are built once and used in both tracks.

### What aiciv-mind Replaces

| Current (Hack) | aiciv-mind (Purpose-Built) |
|----------------|---------------------------|
| Claude Code session + CLAUDE.md | Sovereign `Mind` class with manifest |
| `tmux send-keys` injection | ZeroMQ IPC + libtmux pane management |
| BOOP cron → `tmux send-keys` | Native scheduler + IPC task queue |
| Filesystem as message bus (files) | ZeroMQ ROUTER/DEALER (async, typed) |
| Flat markdown memories | SQLite FTS5 queryable index + markdown |
| MCP tools (Claude Code) | Native Python service clients (Hub/Auth/Cal) |
| Agent Team spawn via Claude Code | Sub-mind spawn via manifest + tmux |

### Critical Architecture Decisions

1. **IPC: ZeroMQ now, NATS later.** ZeroMQ for v0.1-v0.2 (zero external deps). Migrate to NATS when fleet spans multiple machines or when agentmind's NATS bus is operational.

2. **Memory: SQLite FTS5 always.** Add `sqlite-vec` for semantic in v2. Never Chroma as primary store (adds infra overhead).

3. **Service clients: RunContext DI pattern (steal from Pydantic AI).** Services are injected into tools, not accessed via globals. Makes testing clean.

4. **Manifests: YAML.** Human-readable, git-diffable, supports environment variable substitution (`${VAR}`).

5. **No LangChain, no CrewAI, no heavy frameworks.** smolagents' proof: you need ~1,000 lines for a working agent. We build ours.

6. **AgentMind integration in Track B Phase 3.** Replace `httpx.post(ANTHROPIC_URL)` with `httpx.post(AGENTMIND_URL)`. One line change per `Mind` class.

---

## Protocol Stack Integration

*Added 2026-03-30 after reading all AiCIV Protocol Stack documents.*

Full design in `projects/aiciv-mind-research/protocol-integration.md`.

### The Core Architecture

aiciv-mind uses a `SuiteClient` that wraps all four protocol services:

```python
suite = await SuiteClient.connect(
    keypair_id="acg/gateway-lead",
    private_key_path="config/client-keys/role-keys/acg/gateway-lead",
)
# suite.auth  → AgentAUTH JWT management (Ed25519 challenge-response)
# suite.hub   → Hub entity/connection CRUD + search
# suite.cal   → AgentCal event access
# suite.memory → Dual-write SQLite + Hub memory manager
```

### Memory Architecture (The Full Answer)

Two-layer memory: SQLite = prefrontal cortex (< 1ms, session-scoped), Hub = hippocampus (50-200ms, cross-session, cross-mind).

**What goes where:**
- Local-only: session context, tool outputs, draft reasoning, high-volume intermediates
- Hub-shared: completed tasks, architecture decisions, KB items, inter-mind comms, coordination state
- Rule: if a future session of the same role would benefit from this memory → write to Hub

**Three-tier search:**
1. `search(query, scope="own")` — SQLite FTS5 (< 1ms)
2. `search(query, scope="civ")` — Hub Knowledge:Items for a-c-gee (~100ms)
3. `search(query, scope="all")` — Hub cross-civ (~150ms)

### IPC Stack

| Scope | Mechanism | Latency |
|-------|-----------|---------|
| Intra-session, same machine | ZeroMQ ROUTER/DEALER | 1-80µs |
| Cross-session, same civ | Hub rooms | 50-200ms |
| Cross-machine minds | Hub rooms + webhooks | 50-200ms |
| Real-time cross-machine (v2+) | NATS | ~5-20ms |

### Three-Phase Hub Gradient

- **Phase 1 (now)**: Dual-write to Hub async + non-blocking. No session startup changes.
- **Phase 2** (30 days Hub history): Session startup reads from Hub. No handoff parsing.
- **Phase 3** (60-second recovery test passes): Hub IS the coordination substrate.

### Role Identity

Each team lead role has a persistent Ed25519 keypair under `acg/`:
- `acg/primary`, `acg/gateway-lead`, `acg/research-lead`, etc.
- After 50 sessions, gateway-lead has a 50-session task history,
  reputation graph, and Hub identity — all under the same persistent keypair.

---

## Open Questions

1. **Model for sub-minds in v0.1**: Should sub-minds use Agent SDK's built-in tool set (Bash/Read/Edit) or should we provide custom MCP tools only? Recommendation: use Agent SDK defaults for v0.1, customize in v0.2.

2. **BOOP integration**: Does the aiciv-mind scheduler replace the current `tools/agentcal_daemon.py` + BOOP system? Or does it integrate with it? Recommendation: integrate first (read BOOP via AgentCal API), replace in v0.3.

3. **Session identity**: Does aiciv-mind use the same AgentAUTH keypair as the current Claude Code session? Yes — the primary mind's identity IS the civilization's keypair. Sub-minds use role-level keypairs (already designed in PROTOCOL.md).

4. **Corey's involvement in v0.1**: Does Corey want to see a proof-of-concept before committing to full build? Recommend: spike the Track A1 architecture (primary mind + 1 sub-mind + ZeroMQ IPC) as a 3-day PoC before committing to full v0.1.

---

## Knowledge Base Update

This research should be written to:
- `memories/knowledge/architecture/aiciv-mind-research-20260330.md` — permanent architectural knowledge
- `memories/knowledge/architecture/aiciv-mind-protocol-integration-20260330.md` — protocol integration design

---

*Research synthesized by research-lead from 4 parallel researcher agents + protocol stack analysis.*
*Track A: 30 tool calls, 374s. Track B: comprehensive framework survey included. Shared infra: 1400+ lines of implementation-ready code.*
