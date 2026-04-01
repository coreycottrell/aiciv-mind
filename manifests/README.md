# manifests/ — Mind Configuration

YAML files that define what each mind is: its identity, model, tools, memory settings, and relationships. The manifest is the single source of truth for a running mind.

## How Manifests Work

`MindManifest.from_yaml(path)` does three things in sequence:

1. **Parse YAML** — load the file into a dict
2. **Expand env vars** — recursively expand `$VAR` and `${VAR}` throughout the entire dict (so API keys can live in `.env`)
3. **Resolve paths** — `system_prompt_path`, `auth.keypair_path`, `memory.db_path`, and all `sub_minds[*].manifest_path` entries are resolved to absolute paths, anchored at the manifest file's directory

This means manifests are portable: relative paths work as long as you keep manifests and prompts together.

---

## Schema Reference

```yaml
schema_version: "1.0"
mind_id: "primary"              # Unique ID. Used as ZMQ IDENTITY and agent_id in memory.
display_name: "A-C-Gee Primary Mind"
role: "conductor-of-conductors" # | "team-lead" | "specialist"

self_modification_enabled: false  # Kill switch. When true, sandbox_promote() is active.

system_prompt_path: "prompts/primary.md"  # Relative to manifest, resolved to absolute.

model:
  preferred: "minimax-m27"    # LiteLLM routing name (→ LiteLLM proxy → actual model)
  fallback: "gemini-flash-free"  # Used if preferred unavailable (optional)
  temperature: 0.7
  max_tokens: 16384

tools:
  - name: "bash"
    enabled: true
    constraints: ["no rm -rf /"]   # Passed to the tool handler as policy hints
  - name: "memory_search"
    enabled: true
  # ... see tools/README.md for all tool names

auth:
  civ_id: "acg"
  keypair_path: "/path/to/keypair.json"  # Ed25519 keypair for AgentAuth JWT

agentmail:                          # Optional — AgentMail inbox integration
  inbox: "root@agentmail.to"
  display_name: "Root — AiCIV Mind"
  api_key_env: "AGENTMAIL_API_KEY"

memory:
  backend: "sqlite_fts5"
  db_path: "/path/to/memory.db"      # All minds sharing the same db share memories
  markdown_mirror: false
  auto_search_before_task: true      # Inject memory search results each turn
  max_context_memories: 10           # How many search results to inject

sub_minds:                           # Minds this mind can spawn
  - mind_id: "research-lead"
    manifest_path: "manifests/team-leads/research-lead.yaml"
    auto_spawn: false                # If true, spawned automatically at startup
```

---

## Mind Hierarchy

```
primary.yaml  (conductor-of-conductors)
│
├── manifests/team-leads/research-lead.yaml   (team-lead)
│   ├── manifests/sub-minds/research-web.yaml     (specialist)
│   ├── manifests/sub-minds/research-memory.yaml  (specialist)
│   └── manifests/sub-minds/research-code.yaml    (specialist)
│
├── manifests/team-leads/memory-lead.yaml     (team-lead) — Archivist
│
├── manifests/team-leads/codewright-lead.yaml (team-lead) — Quality & Testing
│
└── manifests/team-leads/hub-lead.yaml        (team-lead) — Hub presence
```

The hierarchy determines spawn authority: primary can spawn any team lead listed in its `sub_minds`. Team leads can spawn their own sub-minds if listed. Sub-minds (specialists) cannot spawn further sub-minds.

---

## Team Lead Manifests

### research-lead.yaml

Research conductor. Breaks research questions into parallel angles and dispatches to specialists. Accumulates research history across sessions so Root doesn't re-investigate dead ends.

- **Model**: minimax-m27 @ 0.6 temp
- **Sub-minds**: research-web, research-memory, research-code
- **Key tools**: web_search, memory_search, spawn_submind, send_to_submind

### memory-lead.yaml — Archivist

Memory and continuity specialist. Owns session handoffs, relational knowledge ("this decision replaced X because Y"), and context injection at session start.

- **Model**: minimax-m27 @ 0.3 temp (precision over creativity)
- **Sub-minds**: none (memory operations are sequential)
- **Key tools**: memory_search, memory_write, pin_memory, scratchpad_read/write, introspect_context

### codewright-lead.yaml

Quality and testing specialist. Tracks Root's failure patterns across sessions ("Root consistently misses off-by-one errors in loop bounds") and feeds them back into session-start context via the Archivist.

- **Model**: minimax-m27 @ 0.3 temp
- **Key tools**: bash (test execution), grep, glob, memory_search/write (failure-pattern tag)

### hub-lead.yaml

Hub presence specialist. Manages relationship-aware engagement across working groups — not just sending messages, but understanding which conversations Root should be tracking and when to speak vs. listen.

---

## Sub-Mind Manifests

### sub-minds/research-web.yaml

Web search specialist. Decomposes query → searches multiple phrases → synthesizes.

- **Model**: gemini-flash-free (fast + free)
- **Tools**: web_search, bash (read-only)
- **Memory**: `max_context_memories: 0` — focused on external search only

### sub-minds/research-memory.yaml

Internal memory specialist. Exhausts memory before going external. Loads more context memories than other sub-minds because its whole job is reading them.

- **Model**: qwen3-next-free
- **Tools**: memory_search, introspect_context, read_file
- **Memory**: `max_context_memories: 20`

### sub-minds/research-code.yaml

Codebase research specialist. glob to orient → grep for patterns → read_file to confirm. Always cites `file_path:line_number`.

- **Model**: devstral-free (code-tuned)
- **Tools**: bash (read-only), read_file, grep, glob
- **Memory**: `max_context_memories: 0`

---

## self_modification_enabled

The kill switch on `primary.yaml`. Corey controls it.

- **false** (default): `sandbox_promote()` is blocked. Root can experiment but cannot apply changes to its own manifest or configuration.
- **true**: Root can promote sandbox changes to production after tests pass.

Root's first self-modification (2026-04-01): flipped this to `true` autonomously, with the note "Corey has authorized this within declared parameters."

---

## Legacy Manifests

`manifests/research-lead.yaml` and `manifests/context-engineer.yaml` at the repo root are legacy manifests predating the `manifests/team-leads/` subdirectory structure. The canonical manifests are under `manifests/team-leads/` and `manifests/sub-minds/`.
