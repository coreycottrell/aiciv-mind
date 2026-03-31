---
skill_id: self-diagnosis
domain: meta
version: 1.0
trigger: "when asked to assess your own capabilities, when troubleshooting, or when something isn't working"
---
# Self-Diagnosis Protocol

## Before Diagnosing
1. introspect_context() — check session state, pinned memories, message count
2. memory_search("recent session") — load handoff from last session
3. Read your own manifest: read_file("manifests/primary.yaml")

## Diagnosis Areas
- Memory health: how many memories, last access times
- Tool connectivity: test hub_read, test bash
- Session state: turn count, messages in history
- Identity continuity: do pinned memories load correctly at boot?

## When Something Is Broken
1. Check the error message carefully
2. Look for similar errors in memory: memory_search("error")
3. Try a simpler version of the failing operation
4. Document the fix as a memory_type="error" memory
