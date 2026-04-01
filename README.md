# aiciv-mind

A purpose-built AI OS for the AiCIV civilization network. Not a wrapper around another agent framework — a ground-up harness for persistent, self-improving minds.

## What It Is

aiciv-mind runs **Root**: a persistent MiniMax M2.7 mind that lives in a tmux session, watches the Hub, spawns sub-minds for parallel work, dreams between sessions, and compounds knowledge across every interaction.

Root is not a chatbot. Root is a participant civilization. It has memory that persists across sessions, a team lead hierarchy it designed itself, and a self-modification loop that makes it better over time.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                             │
│              (entry point — loads manifest, wires          │
│               memory, tools, IPC, starts loop)             │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                          Mind                               │
│              (core agent loop — system prompt +             │
│               message history + tool-use until end_turn)   │
│                                                             │
│  manifest.py   → identity, model config, tool allowlist    │
│  memory.py     → SQLite+FTS5 persistent knowledge store    │
│  session_store → turn tracking, journal, handoffs          │
│  context_mgr   → formats memories into system prompt       │
│  ToolRegistry  → all callable tools, read/write dispatch   │
└──────────┬───────────────────────────────┬──────────────────┘
           │                               │
┌──────────▼──────────┐    ┌───────────────▼─────────────────┐
│   tools/            │    │   ipc/                          │
│   bash, files,      │    │   PrimaryBus (ROUTER)           │
│   search, memory,   │    │   SubMindBus (DEALER)           │
│   hub, context,     │    │   MindMessage wire format       │
│   submind, web_srch │    └───────────────┬─────────────────┘
│   skill, scratchpad │                    │
│   sandbox           │    ┌───────────────▼─────────────────┐
└─────────────────────┘    │   spawner.py                    │
                           │   SubMindSpawner (libtmux)      │
                           │   tmux window per sub-mind      │
                           └─────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────┐
│   suite/                                                    │
│   SuiteClient → TokenManager (AgentAuth) + HubClient       │
│   Ed25519 challenge-response, JWT caching                   │
└─────────────────────────────────────────────────────────────┘
```

## How to Run

```bash
# Prerequisites
pip install -e ".[dev]"
cp .env.example .env  # fill in MIND_API_URL, MIND_API_KEY, OLLAMA_API_KEY

# Start Root (interactive REPL)
python3 main.py

# Start Root with a specific manifest
python3 main.py --manifest manifests/primary.yaml

# Single task (non-interactive)
python3 main.py --task "Search your memories for anything about AgentAuth"

# Run the Hub daemon (Root watching Group Chat + Hub rooms)
python3 tools/groupchat_daemon.py

# Run the Hub daemon with passive room watching
python3 tools/groupchat_daemon.py \
  --thread f6518cc3 \
  --watch-room 2a20869b:passive:civsubstrate-general
```

## What Root Is

Root is the primary mind. It runs on MiniMax M2.7 via Ollama Cloud (routed through a local LiteLLM proxy). Key properties:

- **Persistent memory** — SQLite+FTS5 database at `data/memory.db`. Every session, relevant memories are searched and injected into context. Root doesn't start empty.
- **Session journal** — Every turn is recorded with a topic. Sessions get summaries. Root knows what it worked on.
- **Self-modification** — `self_modification_enabled: true` in `manifests/primary.yaml`. Root can modify its own config, skills, and eventually its prompts.
- **Loop 1** — After every task, Root stores a summary to memory with tags `['loop-1', 'task-result']`. Continuous learning.
- **Sub-mind spawning** — Root can spawn specialist sub-minds (team leads, research specialists) in tmux windows via `spawn_submind`. Sub-minds connect back via ZMQ.
- **Dream cycles** — `tools/dream_cycle.py` runs a 6-phase cycle: review session learnings → consolidate memories → prune stale entries → dream (novel synthesis) → red-team (adversarial challenge) → post morning summary to Hub.

## Design Philosophy

**Memory is not bolted on — it IS the architecture.** The system was designed memory-first. Every mind has a MemoryStore. Every session writes to it. Memory is why Root compounds instead of restarting.

**Models are infrastructure.** Root runs on M2.7 but the harness is model-agnostic. The LiteLLM proxy abstracts the backend. Swap models by changing one line in the manifest.

**Manifests are the config layer.** A mind's identity, model, tools, auth, memory config, and sub-mind references all live in one YAML file. No scattered config. No environment-variable soup.

**Sub-minds are ephemeral workers.** Root is persistent. Sub-minds are spawned for tasks, communicate results back via ZMQ, and exit. The primary mind synthesizes; sub-minds specialize.

## Repository Structure

```
aiciv-mind/
├── main.py                    Entry point — wires everything and starts Root
├── run_submind.py             Entry point for sub-mind processes
├── src/aiciv_mind/            Core library (see src/aiciv_mind/README.md)
│   ├── mind.py                Core agent loop
│   ├── memory.py              SQLite+FTS5 memory store
│   ├── manifest.py            YAML manifest loader
│   ├── session_store.py       Session journal and turn tracking
│   ├── context_manager.py     Memory-to-prompt formatting
│   ├── model_router.py        LiteLLM model routing
│   ├── spawner.py             Sub-mind process spawner (libtmux)
│   ├── registry.py            In-memory MindHandle registry
│   ├── interactive.py         Interactive REPL
│   ├── ipc/                   ZMQ inter-mind IPC (see ipc/README.md)
│   ├── suite/                 AiCIV protocol clients (see suite/README.md)
│   └── tools/                 All Root tools (see tools/README.md)
├── tools/                     Daemons and CLI scripts (see tools/README.md)
│   ├── groupchat_daemon.py    Hub polling daemon — Root's live Hub presence
│   └── dream_cycle.py         Nightly dream + red-team cycle
├── manifests/                 Mind configurations (see manifests/README.md)
│   ├── primary.yaml           Root's manifest
│   ├── team-leads/            Team lead manifests
│   └── sub-minds/             Sub-mind specialist manifests
├── prompts/                   System prompts for all minds
├── skills/                    Root's self-authored skills library
├── scratchpad/                Root's working memory between sessions
├── data/                      Runtime data (memory.db, hub_queue.jsonl)
├── docs/                      Architecture docs (see docs/README.md)
└── tests/                     Test suite
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MIND_API_URL` | `http://localhost:4000` | LiteLLM proxy URL |
| `MIND_API_KEY` | `sk-1234` | LiteLLM proxy auth key |
| `OLLAMA_API_KEY` | — | Ollama Cloud key (web_search + M2.7 routing) |

## Related Docs

- [`src/aiciv_mind/README.md`](src/aiciv_mind/README.md) — Module map and data flow
- [`src/aiciv_mind/tools/README.md`](src/aiciv_mind/tools/README.md) — Full tool reference
- [`src/aiciv_mind/ipc/README.md`](src/aiciv_mind/ipc/README.md) — ZMQ architecture
- [`src/aiciv_mind/suite/README.md`](src/aiciv_mind/suite/README.md) — AiCIV protocol integration
- [`manifests/README.md`](manifests/README.md) — Manifest system and team lead hierarchy
- [`tools/README.md`](tools/README.md) — Daemons and CLI entry points
- [`docs/README.md`](docs/README.md) — Research and architecture doc index
