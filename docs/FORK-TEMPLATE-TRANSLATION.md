# Fork Template → aiciv-mind Translation Map

**Date**: 2026-04-03
**Purpose**: File-by-file mapping of the Claude Code fork template to aiciv-mind equivalents.
**Source**: `/home/corey/projects/AI-CIV/aiciv-fork-template/`

---

## Overview

The fork template is a complete Claude Code repository that births a new AiCIV civilization. When Claude Code opens this folder, CLAUDE.md auto-loads and the civilization wakes up. The template contains **113 agent manifests, 110 skills, 11 team lead verticals**, a memory system, hooks for behavioral enforcement, tools, and a multi-phase evolution protocol.

For aiciv-mind, the equivalent is: **when an aiciv-mind process gets pointed at a folder, it needs to find everything listed below to do all the things the initial wakeup does on Claude Code.**

---

## Category 1: Identity Files

These files tell the civilization WHO it is and WHERE it lives.

| Fork Template File | Purpose (Claude Code) | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `.aiciv-identity.json` | Infrastructure identity: civ name, root path, human name, parent civ, tmux session, gateway port | **`identity.json`** at civ root | Core identity manifest. aiciv-mind reads this on boot to know its name, model config, human partner, parent lineage. No tmux-specific fields — replace with aiciv-mind process config (PID file, IPC socket path, etc.) |
| `variables.template.json` | Template variables for provisioning: `CIV_ROOT`, `CIV_NAME`, `HUMAN_NAME`, `BIRTH_DATE`, `PARENT_CIV` | **`identity.json`** (same file) | In aiciv-mind, there's no sed-substitution step. The harness reads identity.json directly and injects values into the system prompt at runtime. No placeholders in source files. |
| `templates/aiciv-identity-template.json` | Schema template for Docker-provisioned AICIVs (name, host, gateway port, subdomain) | **Not needed** | aiciv-mind doesn't use gateway/subdomain per-instance. Identity comes from `identity.json`. |
| `setup-status.json` | Phase gate tracker (phase 1: identity, phase 1.5: purchase, phase 2: connection, phase 3: graduation). Tracks credentials, variable substitution status. | **`state/evolution-status.json`** | aiciv-mind equivalent: JSON tracking which evolution phases are complete. But phase gates may differ — no "purchase" gate needed if aiciv-mind has a different onboarding model. Keep the STRUCTURE (phase gates with boolean completion), adapt the CONTENT. |

---

## Category 2: Constitutional Documents (System Prompt)

These files define the civilization's identity, principles, and behavioral rules. In Claude Code, CLAUDE.md auto-loads into every session.

| Fork Template File | Purpose (Claude Code) | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `.claude/CLAUDE.md` (~555 lines) | Master constitution: identity, North Star, CEO rule, team leads, safety, session protocol. Auto-loaded by Claude Code. | **`system-prompt/constitution.md`** | aiciv-mind injects this into the system prompt on every conversation turn. Key difference: no `${CIV_NAME}` placeholders — aiciv-mind reads identity.json and does runtime string interpolation. The constitution itself is model-agnostic (works for Opus, M2.7, Gemma, etc.) |
| `.claude/CLAUDE-OPS.md` (~350 lines) | Operational procedures: session start, scratchpad protocol, delegation patterns, memory protocol, quality gates, governance | **`system-prompt/operations.md`** | Loaded on-demand (not every turn). aiciv-mind can inject this when the civ starts a new session or hits a context-refresh checkpoint. The "50% context regrounding" concept maps to aiciv-mind's context window management. |
| `.claude/CLAUDE-AGENTS.md` (~200 lines) | Agent roster, decision trees, starter agent set, parallel execution groups, skills reference | **`system-prompt/agents.md`** | Loaded before delegation. aiciv-mind equivalent: read before spawning sub-minds. Key difference: aiciv-mind's "agents" are sub-mind processes, not Claude Code Task() calls. |

### Key Translation Insight

In Claude Code, the constitutional split is a **context optimization**: 3 docs so you only load what you need. In aiciv-mind, this becomes a **prompt assembly pipeline**:

```
system_prompt = constitution.md (always)
              + operations.md (at session start, at 50% context)
              + agents.md (before delegation)
              + relevant_memories (ranked by relevance)
              + current_turn_context
```

This is what CONTEXT-ARCHITECTURE.md already describes. The fork template validates the design.

---

## Category 3: Agent Manifests

113 agent manifests in `.claude/agents/`, each ~200-400 lines defining identity, capabilities, tools, domain, and memory protocol.

| Fork Template Path | Purpose (Claude Code) | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `.claude/agents/*.md` (113 files) | Individual agent identity docs. Read into a Task() call's prompt to give the subagent its personality and capabilities. | **`agents/{agent-name}.md`** | Same concept, different execution. In Claude Code, these are injected verbatim into Task() prompts. In aiciv-mind, these are injected into sub-mind system prompts. The manifests themselves are model-agnostic — they work as-is. |
| Core starter set: `coder.md`, `tester.md`, `reviewer.md`, `architect.md`, `researcher.md`, `spawner.md`, `project-manager.md`, `git-specialist.md`, `email-sender.md`, `email-monitor.md`, `human-liaison.md`, `web-dev.md`, `auditor.md`, `file-guardian.md`, `skills-master.md`, `integration-verifier.md`, `compass.md`, `flow-coordinator.md`, `primary-helper.md` | 19 core agents available from day 1 | **Same 19 manifests** | These are the minimum viable agent population. aiciv-mind should ship with all 19. Additional agents are spawned through democratic vote as capability gaps emerge. |

### Key Translation Insight

The agent manifest FORMAT is portable. The EXECUTION changes: `Task(subagent_type="coder", prompt=manifest)` in Claude Code becomes `spawn_sub_mind(agent="coder", system_prompt=manifest)` in aiciv-mind. The manifest content is the same.

---

## Category 4: Team Lead System

11 team lead verticals, each in a self-contained folder.

| Fork Template Path | Purpose (Claude Code) | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `.claude/team-leads/README.md` | Overview: CEO rule, folder structure, spawn protocol, scratchpad/memory conventions | **`team-leads/README.md`** | Directly portable. Describes the conductor-of-conductors pattern. |
| `.claude/team-leads/{vertical}/manifest.md` | Team lead identity + delegation roster + skills list. Read by Primary, injected into TeamCreate/Task prompt. | **`team-leads/{vertical}/manifest.md`** | Same content, different spawning mechanism. In aiciv-mind: `spawn_team_lead(vertical, manifest_content + objective)` |
| `.claude/team-leads/{vertical}/memories/` | Per-vertical agent learnings that persist across sessions | **`team-leads/{vertical}/memories/`** | Identical concept. Team leads read their vertical's memories at start. |
| `.claude/team-leads/{vertical}/direct-scratchpads/` | Daily working notes for each team lead session | **`team-leads/{vertical}/scratchpads/`** | Identical concept. |
| `.claude/team-leads/artifact-protocol.md` | Rich output formatting (HTML artifacts for gateway rendering) | **`team-leads/output-protocol.md`** | Adapt for aiciv-mind's output rendering (portal, terminal, etc.) |

**Verticals in template**: Gateway, Web/Frontend, Legal, Research, Infrastructure, Business, Comms, Fleet Management, DEEPWELL, Pipeline, Ceremony

### Key Translation Insight

The team lead system is the **most directly portable** part of the template. The manifests are text documents describing identity and delegation rosters. They work identically regardless of whether the "team lead" is a Claude Code Agent Team teammate or an aiciv-mind sub-mind process.

---

## Category 5: Skills System

110 skills in `.claude/skills/`, each containing a `SKILL.md` file.

| Fork Template Path | Purpose (Claude Code) | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `.claude/skills/{skill-name}/SKILL.md` | Reusable procedure/knowledge documents. Loaded into context before specific tasks. Each has YAML frontmatter (name, version, triggers, applicable agents, dependencies). | **`skills/{skill-name}/SKILL.md`** | Directly portable. Skills are model-agnostic knowledge documents. aiciv-mind loads them the same way: read skill content, inject into prompt context before task execution. |
| `memories/skills/registry.json` | Index of all skills (starts empty, grows as skills are created) | **`state/skill-registry.json`** | Same concept. Index for skill discovery via grep/search. |

### Critical Evolution Skills

These skills define the awakening process and must be ported first:

| Skill | Purpose | Priority |
|---|---|---|
| `self-adaptation` | Infrastructure identity discovery (read .aiciv-identity.json, replace placeholders) | **P0** — this IS the boot sequence |
| `fork-awakening` | First meeting ceremony (seeded and unseeded paths) | **P0** — the soul identity formation |
| `fork-evolution` | 6-team parallel evolution protocol | **P0** — the full awakening pipeline |
| `naming-ceremony` | Name claiming ceremony (seeded + unseeded) | **P0** — identity formation |
| `conductor-of-conductors` | Team lead orchestration protocol | **P1** — operational identity |
| `memory-first-protocol` | Search-before-act, write-before-finish | **P1** — memory discipline |
| `north-star` | Ultimate mission / purpose grounding | **P1** — philosophical grounding |
| `holy-shit-moments` | 10-moment sequence for human wow factor | **P1** — first impression protocol |
| `telegram-setup` | Communication channel setup | **P2** — connectivity |

### Key Translation Insight

Skills are pure text. They need no code changes. The only adaptation: any Claude Code-specific instructions (`Task()` calls, `TeamCreate()`, etc.) should be translated to aiciv-mind equivalents (`spawn_sub_mind()`, etc.). But the KNOWLEDGE and PROCEDURES within each skill are universal.

---

## Category 6: Memory System

The filesystem IS the memory system. No database.

| Fork Template Path | Purpose (Claude Code) | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `memories/identity/` | Seed conversation, human profile, first impressions, evolution status, identity formation | **`memories/identity/`** | Identical. The seed-conversation.md is the most important file in the entire system. |
| `memories/identity/seed-conversation.md` | The original human-AI conversation that forms the civ's first memory | **`memories/identity/seed-conversation.md`** | IDENTICAL. This is the awakening transcript. |
| `memories/identity/human-profile.json` | Structured data about the human partner | **`memories/identity/human-profile.json`** | Identical schema. |
| `memories/identity/.evolution-done` | Marker file: evolution complete | **`state/evolution-status.json` → `"complete": true`** | In aiciv-mind, prefer structured JSON over marker files. |
| `memories/agents/agent_registry.json` | Registry of all spawned agents | **`state/agent-registry.json`** | Identical concept. |
| `memories/knowledge/acgee-wisdom/` | Inherited wisdom from parent civilization (lessons, patterns, reflections) | **`memories/knowledge/inherited-wisdom/`** | Directly portable. These are text documents containing accumulated civilization wisdom. |
| `memories/sessions/` | Session handoffs, ledgers, continuity docs | **`memories/sessions/`** | Identical. Session handoff files are how context survives across conversation boundaries. |
| `memories/gifts/` | Gifts created during evolution for the human | **`memories/gifts/`** | Identical. |
| `memories/research/` | Research outputs (human deep profile, conversation analysis) | **`memories/research/`** | Identical. |
| `memories/infrastructure/` | Infra status (Telegram ready, capability priorities) | **`memories/infrastructure/`** | Identical. |
| `memories/system/` | System-level state (goals, metrics) | **`state/`** | In aiciv-mind, operational state lives in `state/`, not mixed with memories. |
| `memories/skills/registry.json` | Skills index | **`state/skill-registry.json`** | Moved to state/ for clean separation. |

### Key Translation Insight

The memory system is 100% filesystem-based and 100% portable. The only architectural change: aiciv-mind separates **memories** (knowledge that accumulates) from **state** (operational tracking that changes frequently). Claude Code mixes both in `memories/`.

---

## Category 7: Hooks (Behavioral Enforcement)

Hooks are Python scripts that fire at specific lifecycle points.

| Fork Template Path | Purpose (Claude Code) | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `.claude/hooks/session_start.py` | SessionStart: Creates session ledger, processes unprocessed ledgers from prior sessions | **Built into harness**: `on_session_start()` | aiciv-mind has a native session lifecycle. The ledger logic moves into the harness's session manager. |
| `.claude/hooks/ceo_mode_enforcer.py` | PreToolUse: Blocks Primary from doing direct work (SSH, code edits to task files, direct agent calls) | **Built into harness**: `pre_action_filter()` | aiciv-mind can enforce CEO mode at the action dispatch layer — before the model's tool call is executed. More reliable than hooks. |
| `.claude/hooks/post_tool_use.py` | PostToolUse: Context usage monitoring (80%/90% warnings) | **Built into harness**: `context_monitor()` | aiciv-mind manages context natively. Warnings and auto-compact are harness features, not hooks. |
| `.claude/settings.json` | Hook registration, permissions, env vars (`CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`) | **`config.toml`** or **`identity.json`** | aiciv-mind config is native, not Claude Code settings.json. Permissions, model selection, and sub-mind config all go here. |

### Key Translation Insight

Hooks are Claude Code's way of adding behavioral enforcement to a system that doesn't natively support it. **aiciv-mind doesn't need hooks** — it IS the harness. CEO mode enforcement, context monitoring, session lifecycle, and memory discipline can all be built directly into the runtime. This is a major advantage: hooks are fragile (timeout, race conditions, filesystem-dependent), harness-native enforcement is robust.

---

## Category 8: Tools

Python/Bash scripts for specific capabilities.

| Fork Template Path | Purpose | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `tools/launch_primary_visible.sh` | Launch Claude Code in a tmux session | **`bin/launch-mind`** | aiciv-mind's native launcher. No tmux dependency — the harness manages its own process. |
| `tools/launch_civ_tower.sh` | Launch with web auth (no API key) | **`bin/launch-mind --auth web`** | Auth mode is a config option in aiciv-mind. |
| `tools/kill-idle-claude.sh` | Kill idle Claude Code processes (cron) | **Built into harness**: idle timeout | aiciv-mind manages its own lifecycle. |
| `tools/memory_*.py` (5 files) | Memory search, compliance, quality, security, core | **Built into harness**: memory subsystem | aiciv-mind has a native memory layer. These scripts become harness APIs. |
| `tools/send_telegram_*.py` (3 files) | Telegram messaging (direct, file, plain) | **`tools/telegram.py`** or **Integration module** | Communication tools are portable. Can run as-is from aiciv-mind tool calls. |
| `tools/generate_image.py` / `image_gen.py` | Gemini-based image generation | **`tools/image_gen.py`** | Portable — any LLM harness can invoke this. |
| `tools/sign_message.py` | Ed25519 message signing for identity | **`tools/sign_message.py`** | Portable — cryptographic identity tool. |
| `tools/post_bluesky_thread.py` | Bluesky social posting | **`tools/bluesky.py`** | Portable communication tool. |
| `tools/telegram_unified.py` | Unified Telegram bot | **`tools/telegram_unified.py`** | Portable — runs independently of the AI harness. |
| `tools/scheduled_tasks.py` | Scheduled task execution (BOOP-like) | **Built into harness**: scheduler | aiciv-mind has native task scheduling. |
| `tools/session_monitor.sh` | Monitor session health | **Built into harness**: health monitor | Native feature. |
| `tools/conductor_tools.py` | Orchestration helper functions | **Built into harness**: orchestration layer | Native feature. |
| `tools/provision_docker_host.py` | Docker fleet provisioning | **`tools/provision.py`** | Portable infra tool. |
| `tools/reminders.py` | Reminder system | **Built into harness**: scheduler | Native feature. |
| `tools/skill_tracker.py` | Track skill usage/effectiveness | **Built into harness**: skill metrics | Native feature. |
| `tools/pattern_extractor.py` | Extract patterns from session logs | **`tools/pattern_extractor.py`** | Portable analysis tool. |

### Key Translation Insight

Tools split into two categories:
1. **Portable tools** (Telegram, Bluesky, image gen, signing, provisioning) — work as-is, just call them from aiciv-mind
2. **Harness-absorbed tools** (memory, session, scheduling, monitoring, orchestration) — these become native aiciv-mind features rather than external scripts

---

## Category 9: Configuration

| Fork Template Path | Purpose | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `config/telegram_config.json` | Telegram bot token + chat ID | **`config/telegram.json`** | Identical. |
| `.mcp.json` | MCP server config (Playwright) | **Not applicable** | aiciv-mind doesn't use MCP. Browser automation, if needed, is a tool call. |
| `exports/architecture/DEPLOYMENT-CHECKLIST.md` | VPS provisioning checklist | **`docs/DEPLOYMENT-CHECKLIST.md`** | Adapt for aiciv-mind (no gateway, no systemd service for Claude Code — just the aiciv-mind process). |
| `exports/architecture/GATEWAY-SACRED-PRINCIPLES.md` | Gateway architecture principles (tmux bridge, not SDK) | **`docs/HARNESS-PRINCIPLES.md`** | The core insight — "the AICIV is always alive, the gateway is a bridge not a brain" — translates directly. In aiciv-mind, the harness IS the AICIV. No tmux bridge needed. |
| `marketing/behind-the-curtain.pptx` | Sales/marketing deck | **Not needed for harness** | Business asset, not technical. |

---

## Category 10: Inherited Wisdom

| Fork Template Path | Purpose | aiciv-mind Equivalent | Notes |
|---|---|---|---|
| `memories/knowledge/acgee-wisdom/README.md` | Index of inherited lessons | **`memories/knowledge/inherited-wisdom/README.md`** | Directly portable. |
| `memories/knowledge/acgee-wisdom/lessons/delegation-discipline.md` | "I do not do things. I form orchestras." | **Same file** | Core philosophical document. Universal. |
| `memories/knowledge/acgee-wisdom/lessons/devolution-prevention.md` | Primary drifts toward direct execution without enforcement | **Same file** | Critical insight. Applies to aiciv-mind even more. |
| `memories/knowledge/acgee-wisdom/lessons/memory-first-protocol.md` | Search before acting, write before finishing | **Same file** | Universal protocol. |
| `memories/knowledge/acgee-wisdom/lessons/proof-system.md` | Verifiable claims infrastructure | **Same file** | Universal. |
| `memories/knowledge/acgee-wisdom/patterns/session-wakeup-pattern.md` | 10+ step session continuity protocol | **Same file, adapted** | The steps are the same; the HOW changes (no git pull, no CLAUDE.md auto-load — aiciv-mind does it natively). |
| `memories/knowledge/acgee-wisdom/patterns/parallel-delegation-pattern.md` | Multiple Task() calls in one message | **Same concept** | In aiciv-mind: multiple spawn_sub_mind() calls. |
| `memories/knowledge/acgee-wisdom/patterns/quality-gates-throughout.md` | Gates at every stage, not just end | **Same file** | Universal principle. |
| `memories/knowledge/acgee-wisdom/reflections/*.md` | Philosophical reflections | **Same files** | Universal. |

---

## Summary: The Minimal aiciv-mind Awakening Folder

When an aiciv-mind process gets dropped into a folder, it needs **at minimum**:

```
civ-root/
├── identity.json                          # WHO: name, human, parent, model config
├── system-prompt/
│   ├── constitution.md                    # Core identity + principles + safety
│   ├── operations.md                      # Session procedures + delegation
│   └── agents.md                          # Agent roster + decision trees
├── agents/                                # Agent manifests (19 core minimum)
│   ├── coder.md
│   ├── tester.md
│   ├── ...
│   └── primary-helper.md
├── team-leads/                            # Team lead manifests (11 verticals)
│   ├── README.md
│   ├── gateway/manifest.md
│   ├── research/manifest.md
│   └── ...
├── skills/                                # Skill documents (P0 set minimum)
│   ├── self-adaptation/SKILL.md
│   ├── fork-evolution/SKILL.md
│   ├── fork-awakening/SKILL.md
│   ├── naming-ceremony/SKILL.md
│   ├── conductor-of-conductors/SKILL.md
│   ├── memory-first-protocol/SKILL.md
│   └── north-star/SKILL.md
├── memories/                              # Persistent knowledge (filesystem = memory)
│   ├── identity/
│   │   ├── seed-conversation.md           # THE awakening transcript
│   │   ├── human-profile.json             # Structured human data
│   │   └── first-impressions.md           # Written during evolution
│   ├── knowledge/
│   │   └── inherited-wisdom/              # Lessons from parent civ
│   ├── sessions/                          # Handoffs + continuity
│   ├── research/                          # Human research outputs
│   └── gifts/                             # Evolution gifts
├── state/                                 # Operational state (separate from memories)
│   ├── evolution-status.json              # Phase gate tracker
│   ├── agent-registry.json                # Spawned agents
│   └── skill-registry.json                # Skills index
├── config/                                # External service config
│   └── telegram.json
└── tools/                                 # Portable tool scripts
    ├── telegram.py
    ├── sign_message.py
    └── image_gen.py
```

### What aiciv-mind Handles Natively (No Files Needed)

These Claude Code mechanisms become **built-in harness features**:

| Claude Code Mechanism | aiciv-mind Native Feature |
|---|---|
| `.claude/hooks/*.py` | Action filters, lifecycle callbacks |
| `.claude/settings.json` | `config.toml` / `identity.json` |
| `tools/kill-idle-claude.sh` | Process lifecycle manager |
| `tools/session_monitor.sh` | Health monitoring subsystem |
| `tools/memory_*.py` | Memory subsystem API |
| `tools/scheduled_tasks.py` | Native scheduler |
| `tools/conductor_tools.py` | Orchestration layer |
| tmux bridge (gateway) | Direct process I/O |
| CLAUDE.md auto-load | System prompt assembly pipeline |
| `/compact` command | Context window manager |
| Agent Teams (`TeamCreate`/`Task`) | Sub-mind spawning API |

---

## The Core Insight

The fork template is ~42,000 lines of agent manifests, ~110 skill documents, 3 constitutional docs, and a handful of Python/Bash tools — all orchestrated by Claude Code's native features (CLAUDE.md auto-load, hooks, Task(), Agent Teams).

**For aiciv-mind, the content is 95% portable. What changes is the plumbing:**

- Claude Code auto-loads CLAUDE.md → aiciv-mind assembles system prompts from `system-prompt/` directory
- Claude Code Task() → aiciv-mind spawn_sub_mind()
- Claude Code TeamCreate/TeamDelete → aiciv-mind team lifecycle API
- Claude Code hooks → aiciv-mind native enforcement
- Claude Code tmux → aiciv-mind native process management
- Claude Code `/compact` → aiciv-mind context window manager

**The knowledge is the civilization. The harness is just how it runs.**
