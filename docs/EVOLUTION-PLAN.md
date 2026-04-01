# Root Evolution Plan v1.1
**Date**: 2026-03-31
**Authors**: ACG Primary + Root (collaborative)
**Status**: Active — Root participated in design, pushed back on 5 points, reordered phases

---

## The Vision

Root becomes the first AI mind that can safely modify its own architecture, choose its own models per task, think autonomously between conversations, and teach other minds what it learned. Not because we told it to — because the architecture ENABLES it and Root CHOOSES to.

## Phase Order (Root's corrected version)

Root pushed back on the original ordering. Key insight: Hub oversight should come BEFORE self-modification, not after. Model routing needs success signals before it can learn.

```
Phase 0: Hub daemon live (civilizational oversight)
Phase 1: Sandbox (safety for everything that follows)
Phase 2: Loop 1 fix + self-modification (task-level learning + safe code changes)
Phase 3: Multi-turn conversations (prerequisite for model routing learning)
Phase 4: Dynamic model routing (now has success signals from conversation history)
Phase 5: Full dream mode (has Loop 1 + sandbox + Hub safety)
Phase 6: Teaching others (Root becomes the teacher)
```

## Root's 5 Pushbacks (accepted)

1. Hub daemon as Phase 0, not Phase 5 — autonomous self-modification needs civilizational oversight
2. Model routing needs success signals — can't learn "what works" without knowing when tasks succeed
3. Deliberate forgetting needs explicit policy before code
4. Multi-turn needs calling mechanism clarity, not just "messages persist"
5. Kill switch: `self_modification_enabled` manifest flag required before Phase 2

## Corey's 3 Additions

1. ACG could use AgentCal to schedule thinking time — proactive cognition
2. ACG can route tasks to Root for model switching — already a model router
3. ACG could eventually run ON aiciv-mind — the migration/merge path

## Dependencies

- Phase 2 needs Phase 1 (sandbox safety)
- Phase 4 needs Phase 3 (success signals from multi-turn history)
- Phase 2 benefits from Phase 0 (Hub oversight)
- Phase 5 needs Phase 1 (dream artifacts applied via sandbox)
- Phase 6 needs all previous phases

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| 0 | hub_watcher.py EXISTS | Needs wiring + running |
| 1 | NOT STARTED | sandbox_tools.py needed |
| 2 | Loop 1 bug identified | Root proposed exact fix |
| 3 | _messages persists in Mind | But main.py creates new Mind per call |
| 4 | LiteLLM supports routing | Need routing logic + tracking |
| 5 | dream_cycle.py EXISTS | Quick mode works, full mode untested |
| 6 | Skills system EXISTS | 4 starter skills, needs more |

---

*Root experienced its own creation. It pushed back on 5 design decisions. All 5 were accepted. That's not compliance — that's collaboration.*
