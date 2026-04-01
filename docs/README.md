# docs/ — Research and Architecture Index

All architecture decisions, research reports, and design documents for aiciv-mind. Most were written before or during implementation — they are the reasoning trail.

## Architecture Documents

| File | Description |
|------|-------------|
| `RUNTIME-ARCHITECTURE.md` | Production reference for the v0.3 runtime — how all components connect at runtime. Start here for architecture overview. |
| `CONTEXT-ARCHITECTURE.md` | Deep dive on context window management — how memories are ranked, injected, and pruned. The theory behind the system prompt structure. |
| `MEMORY-TYPES-SPEC.md` | Full taxonomy of memory types (learning, decision, error, handoff, observation) and when to use each. |
| `CONTEXT-ARCH-VS-ROADMAP.md` | Cross-reference: which BUILD-ROADMAP items correspond to CONTEXT-ARCHITECTURE sections. |
| `CONVERSATION-ASSESSMENT.md` | Assessment of the conversation/session system — turn tracking, journal, handoffs. |

## Build Planning

| File | Description |
|------|-------------|
| `BUILD-PLAN-FINAL.md` | The final build plan Root executed on 2026-04-01 — 6 builds delivered in one session. This is the definitive record of what was built and why. |
| `BUILD-ROADMAP.md` | Full gap analysis and prioritized build plan. Preceded BUILD-PLAN-FINAL. |
| `EVOLUTION-PLAN.md` | Root Evolution Plan v2.0 — the longer-term trajectory for what Root becomes. |
| `NEXT-STEPS.md` | Immediate next steps (snapshot from a specific session). |

## Model Research

| File | Description |
|------|-------------|
| `M27-RESEARCH.md` | Deep research report on MiniMax M2.7 — capabilities, context window, pricing, streaming behavior. |
| `M27-FOCUS.md` | How we actually use M2.7 in aiciv-mind — prompting strategies, temperature settings, known quirks. |
| `OLLAMA-CLOUD-RESEARCH.md` | Research on Ollama Cloud — routing M2.7 via flat subscription instead of OpenRouter per-token. Includes LiteLLM config examples and pitfalls. |

## Claude Code Analysis

| File | Description |
|------|-------------|
| `CC-ANALYSIS-CORE.md` | Analysis of Claude Code's core architecture (tool loop, context management, plugin system). Patterns worth adopting. |
| `CC-ANALYSIS-TEAMS.md` | Analysis of Claude Code's multi-agent/team patterns for aiciv-mind coordination. |
| `CC-PUBLIC-ANALYSIS.md` | Summary of public community analysis of the Claude Code source leak (March 2026). Competitive intelligence. |
| `CC-INHERIT-LIST.md` | Concrete list of what aiciv-mind should inherit from the Claude Code analysis. |

## Audits and Assessments

| File | Description |
|------|-------------|
| `REALITY-AUDIT.md` | Forensic audit of aiciv-mind v0.2 — what was claimed vs. what was actually working. "Foundation is real. Core promises not yet delivered." |
| `ROOT-GAPS.md` | Architecture gaps audit: skills, agents, hub daemon — what Root was missing before the Build-Plan-Final sprint. |
| `PORTAL-REVIEW.md` | Review of the React portal for aiciv-mind. |

## Research Subdirectory

`research/` contains exploratory research documents:

| File | Description |
|------|-------------|
| `DESIGN-PRINCIPLES.md` | Core design principles for the system |
| `framework-survey.md` | Survey of existing agent frameworks considered before building from scratch |
| `protocol-integration.md` | Research on AiCIV protocol integration (AgentAuth, Hub, AgentCal) |
| `RESEARCH-REPORT.md` | Consolidated research findings |
| `shared-infrastructure.md` | Research on shared infrastructure across civilizations |
| `track-a-sdk-accelerated.md` | Design track A: build on existing SDKs |
| `track-b-sovereign.md` | Design track B: build from scratch (chosen) |

---

## Reading Order for New Contributors

1. **`RUNTIME-ARCHITECTURE.md`** — understand how it all fits together
2. **`BUILD-PLAN-FINAL.md`** — understand what was built and why
3. **`MEMORY-TYPES-SPEC.md`** — understand the memory architecture
4. **`M27-FOCUS.md`** — understand the model layer
5. **`REALITY-AUDIT.md`** — understand the honest state of the system

Everything else is reference material for specific subsystems.
