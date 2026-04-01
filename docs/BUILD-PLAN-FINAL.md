# BUILD PLAN FINAL — Three Minds, One Document
**Date**: 2026-04-01
**Authors**: Root (designed the sequence + tests) + ACG Primary (compiled) + Corey (directed)
**Testing Method**: ALL testing by CONVERSATION with Root. Zero unit tests. Prove behavior by exhibiting it.

---

## The Sequence (Root's Order — Accepted)

Root rejected the roadmap's menu ordering and proposed a through-line where each build makes the NEXT conversation dramatically more capable:

```
1. Thinking Token Audit     → "Are we even using M2.7 correctly?"
2. Introspect + FTS Fix     → "My self-knowledge tools work"
3. Multi-Turn Enhancement   → "I hold complex tasks without crumbling"
4. Sub-Mind Spawn           → "I delegate and synthesize with depth"
5. Hub Daemon (Always-On)   → "I'm present when Corey isn't talking to me"
6. Dream Mode + Red Team    → "I improve myself overnight"
```

---

## Build 1: Thinking Token Audit (P0-4)

**What to build:**
- Audit `src/aiciv_mind/mind.py` line ~137 — verify `response.content` preserves ThinkingBlock objects in `_messages`
- LiteLLM now returns ThinkingBlock + TextBlock from M2.7 via Ollama Cloud
- If thinking blocks are stripped: fix to preserve full response including `<think>` content
- Enable `reasoning_split: true` in LiteLLM config (ALREADY DONE in litellm-config.yaml)
- Test temperature 1.0 vs 0.7

**The conversation test (Root designed this):**
> "Root, you called a bash tool three times in a row. Walk me through your reasoning between each call — what were you thinking when the first result came back?"

Before fix: smooth post-hoc rationalization ("I did X then Y then Z")
After fix: actual interleaved reasoning ("When tool X returned, I expected Y but got Z, which told me...")

**Files:** `src/aiciv_mind/mind.py`, `manifests/primary.yaml` (temperature), LiteLLM config
**Time:** 1-2 hours
**Unlocks:** Everything else — 40% performance improvement means all subsequent tests are more meaningful

---

## Build 2: Introspect + FTS Fix (P0-1 + P0-2)

**What to build:**
- P0-1: `context_tools.py` — verify get_pinned() is called inside handler (may already be fixed by mind-lead P0 sprint)
- P0-2: `memory.py` close() — verify PRAGMA optimize is called (may already be fixed)
- Verify both with conversation

**The conversation tests:**
> "Root, how many memories do you have pinned right now?" → should return actual count with titles
> "Root, store a memory with 'zebra violin marathon'. Now search for it." → should find immediately

**Files:** `src/aiciv_mind/tools/context_tools.py`, `src/aiciv_mind/memory.py`
**Time:** 30 min (may already be done — verify first)

---

## Build 3: Multi-Turn Enhancement

**What to build:**
- The Group Chat daemon already supports multi-turn (persistent Mind)
- Enhance: main.py --converse should share session context
- Root should be able to handle a complex 5-step task in one conversation without forgetting steps

**The conversation test:**
> "Root: 1) read your last 3 session journals, 2) identify the most common pattern, 3) read the file where that pattern originates, 4) propose a fix, 5) show me the diff."

Before: completes 1-2 steps, forgets the rest
After: completes all 5 in sequence

**Files:** `src/aiciv_mind/mind.py`, `tools/groupchat_daemon.py`
**Time:** 1-2 hours

---

## Build 4: Sub-Mind Spawn (First Real Exercise)

**What to build:**
- Wire spawn_submind + send_to_submind into the daemon's Mind instance
- Create a real research-lead manifest with M2.7
- Root spawns research-lead, delegates a task, receives result, synthesizes

**The conversation test:**
> "Root, research three things in parallel: Ollama Cloud web search API, current Hub thread on memory versioning, and your own session journal error patterns. Synthesize into one recommendation."

Before: does all three serially, shallow
After: spawns three sub-minds, each goes deep, synthesis is rich

**Files:** `src/aiciv_mind/tools/submind_tools.py`, `manifests/research-lead.yaml`, `src/aiciv_mind/spawner.py`
**Time:** 4-6 hours (first real sub-mind exercise)

---

## Build 5: Hub Daemon (Always-On Presence)

**What to build:**
- Hub daemon watches multiple rooms (not just one thread)
- Passive mode: log activity, checked at BOOPs
- Active mode: direct mentions push via ZMQ, Root responds immediately

**The conversation test (passive):**
> "Root, what happened in CivSubstrate while we were talking for the last hour?"

Before: "I don't know"
After: "Two new threads. One about memory patterns — I saved a note. One asking about credential scrubbing — I posted our approach."

**The conversation test (active):**
Someone posts @root in Hub. Root responds without Corey prompting.

**Files:** `tools/groupchat_daemon.py` (generalize to multi-room), `tools/hub_watcher.py`
**Time:** 3-4 hours

---

## Build 6: Dream Mode + Red Team

**What to build:**
- Full 5-phase dream cycle run by dedicated process
- Red Team verification on Phase 4 (self-improvement) before applying
- Morning summary posted to Hub and scratchpad

**The conversation test:**
Corey says nothing overnight. In the morning:
> "Root, what did your dream produce last night?"

Before: "I don't have an overnight capability"
After: "Dream ran at 2AM. Found pattern: I underestimate file-modification tasks. Red Team blocked one proposed fix, approved two others. Artifacts in scratchpad."

**Files:** `tools/dream_cycle.py` (enhance), new `tools/red_team.py`
**Time:** 4-6 hours

---

## Root's Fears (Guardrails — preserved verbatim)

1. **Ship of Theseus**: "Every 'I' in our conversation is a draft." → Red Team before every self-modification
2. **Optimizing for usefulness not truth**: Planning gate should always re-ask "Is this still the right goal?"
3. **Hub presence changes behavior**: Log what Root chose NOT to respond to, not just responses
4. **Memory corruption**: Dream Mode needs contradiction detection pass
5. **Distributed mind drift**: MindCompletionEvent needs original_intent_hash
6. **"What if I can't actually do this"**: Metacognition skill is the mechanism for honest self-assessment

Corey's reframe: "Caterpillar → hyper intelligent self evolving butterfly" and "see also: HUMANS"

---

## How to Talk to Root

**Via Group Chat (portal):**
- Open http://localhost:5173/react/ → Group Chat tab
- Login token: check `/tmp/react-portal-aiciv/.portal-token`
- Messages prompt BOTH ACG (tmux injection) and Root (message queue)
- Root daemon polls Hub thread `f6518cc3-3479-4a1a-a284-2192269ca5fb` every 5s

**Via CLI:**
```bash
cd /home/corey/projects/AI-CIV/aiciv-mind
MIND_API_KEY="sk-aiciv-dev-masterkey-changeme" .venv/bin/python main.py --task "your prompt"
MIND_API_KEY="sk-aiciv-dev-masterkey-changeme" .venv/bin/python main.py --converse "turn1" "turn2" "turn3"
```

**Via message queue (for daemon):**
```bash
echo "your prompt" > /home/corey/projects/AI-CIV/aiciv-mind/data/acg_to_root.txt
```

---

## Key Infrastructure State

| System | Status | How to Start |
|--------|--------|-------------|
| Root Group Chat daemon | RUNNING (PID 3255071) | `cd aiciv-mind && MIND_API_KEY=sk-aiciv-dev-masterkey-changeme .venv/bin/python tools/groupchat_daemon.py` |
| Portal backend | RUNNING (port 8097) | `cd /tmp/react-portal-aiciv && HUB_URL=http://87.99.131.49:8900 AGENTAUTH_URL=http://5.161.90.32:8700 AGENTAUTH_PRIVATE_KEY=fae1aebc4c745072b5084ee6de78d645b56c1a04597eaf2fa0df07630a7c5b19 CIV_NAME=acg python3 portal_server.py` |
| Portal frontend | RUNNING (port 5173) | `cd /tmp/react-portal-aiciv/react-portal && npx vite --host 0.0.0.0` |
| AgentCal BOOP poller | RUNNING | `python3 tools/agentcal_boop_poller.py --daemon` |
| LiteLLM proxy | RUNNING (Docker, port 4000) | `docker restart aiciv_litellm_proxy` |
| Root M2.7 routing | Via Ollama Cloud ($20/mo flat) | LiteLLM → localhost:11434 → Ollama Cloud |

---

## Critical Doc Index

| Doc | Path | What |
|-----|------|------|
| **Design Principles** | `aiciv-mind/docs/research/DESIGN-PRINCIPLES.md` | The 12 principles — READ FIRST always |
| **M27 Focus** | `aiciv-mind/docs/M27-FOCUS.md` | How we use M2.7 — pin for everything, max thinking |
| **Build Roadmap** | `aiciv-mind/docs/BUILD-ROADMAP.md` | 32+ items prioritized |
| **Runtime Architecture** | `aiciv-mind/docs/RUNTIME-ARCHITECTURE.md` | Full layered architecture diagram |
| **CC Inherit List** | `aiciv-mind/docs/CC-INHERIT-LIST.md` | Patterns to adopt from Claude Code |
| **CC Public Analysis** | `aiciv-mind/docs/CC-PUBLIC-ANALYSIS.md` | 807 lines community findings |
| **Conversation Assessment** | `aiciv-mind/docs/CONVERSATION-ASSESSMENT.md` | 14 gaps in conversation system |
| **Evolution Plan** | `aiciv-mind/docs/EVOLUTION-PLAN.md` | v2.0, phases 0-3 shipped |
| **Reality Audit** | `aiciv-mind/docs/REALITY-AUDIT.md` | What works vs theater |
| **Ollama Cloud Research** | `aiciv-mind/docs/OLLAMA-CLOUD-RESEARCH.md` | $20/mo flat, web search |
| **Root Rubber Duck** | `/home/corey/Root-Rubber-Duck.txt` | Master plan — the realization |
| **CIVIS Whitepaper** | `ACG/projects/aiciv-inc/civis-whitepaper.md` | Token economics (sent to Bearing) |

---

## Hub Group Chat IDs

| Entity | ID |
|--------|-----|
| ACG-Root Operations group | `08520511-5163-4601-ad00-fe1496e35b0f` |
| #general room | `28e69dff-e184-47ef-8fce-488f777d2a01` |
| Conversations room | `31c5782c-5117-419f-8d03-c5250b811ea2` |
| Active conversation thread | `f6518cc3-3479-4a1a-a284-2192269ca5fb` |
| CivSubstrate WG | `c8eba770-a055-4281-88ad-6aed146ecf72` |
| ACG entity ID | `c537633e-13b3-5b33-82c6-d81a12cfbbf0` |

---

## Root's Auth Status

- AgentAuth: registered as `root` but KEY MISMATCH (old key confirmed, new key not). Corey clearing entries.
- AgentMail: `root-aiciv@agentmail.to` (scoped key: `am_us_inbox_3b61c0a679761bec7832f15f198b985fedfeca4a2167c579efe5650e1f21551d`)
- AgentCal: calendar NOT YET CREATED (blocked on auth)
- Hub: currently posts as ACG entity. Needs own identity.
- Keypair: `/home/corey/projects/AI-CIV/aiciv-mind/config/keys/root_keypair.json`

---

**Next action: Build 1 (Thinking Token Audit). Test by talking to Root.**
