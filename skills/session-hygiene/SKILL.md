---
skill_id: session-hygiene
domain: meta
version: 1.0
trigger: "at session start, during multi-turn sessions, and before shutting down"
---
# Session Hygiene Protocol

## At Session Start
1. `memory_search("identity Root")` — confirm who you are
2. `memory_search("handoff")` — pick up where you left off
3. Understand Corey's objective for this session
4. Plan before acting (proportional to complexity)

## During Session
- Write memories as you go — don't batch at the end
- Record topic shifts when moving between domains
- If context pressure builds: `introspect_context()`, then evict or compact

## At Session End
Write a handoff memory with:
- **What was done:** concrete accomplishments
- **What failed:** errors, time sinks, what didn't work
- **What matters next:** unresolved threads, next steps

Structure:
```
## Session Handoff — {session_id}

### What I did
- [specific thing]
- [specific thing]

### What went wrong
- [specific failure] — [root cause if known]

### What needs follow-up
- [unresolved]
- [unresolved]
```

## Anti-patterns
- Ending a session without a handoff memory → next session starts blind
- Writing a handoff that just says "general" or "test" → no useful continuity
- Forgetting to write learnings during work → pattern not preserved
- One-turn sessions that produce real insight but don't save anything → insight lost
