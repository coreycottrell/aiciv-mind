# Root Bug Analysis — Post Proof-of-Life

**Date:** 2026-03-31 ~02:00 UTC
**Source:** Root's self-diagnosis during 50-behavior proof-of-life

## Bug 1: introspect_context shows stale pinned count

**Root's diagnosis:** Closure captures pinned count at construction time.
**ACG's review:** Root was WRONG about the cause. The code at context_tools.py:132 correctly calls `memory_store.get_pinned()` INSIDE the inner handler function — it queries fresh every time. The issue is likely SQLite WAL mode read isolation — the write from `pin()` may not be visible within the same API turn if both operations happen on the same connection without an explicit checkpoint.

**Actual fix:** Either force WAL checkpoint after pin/unpin writes, or accept eventual consistency within the same turn (pin takes effect on next introspection).

## Bug 2: FTS5 indexing lag

**Root's diagnosis:** Ghost-row accumulation, needs PRAGMA optimize.
**Assessment:** Likely correct. FTS5 virtual tables in WAL mode can lag behind the main table. Adding `PRAGMA optimize` or `INSERT INTO memories_fts(memories_fts) VALUES('optimize')` after batch writes would help.

## Bug 3: Hub room IDs return 404

**Assessment:** The Hub API at 87.99.131.49:8900 is live (verified earlier today) but the room IDs in the manifest/prompt may be wrong, or the Hub API path for thread listing is different from what hub_tools.py expects. Needs investigation of the actual Hub endpoint paths vs what the client sends.

## Key Insight

Root diagnosed real bugs but got one root cause wrong. This is EXACTLY why Red Team (Principle 9) matters — self-diagnosis is valuable but not authoritative. The mind should propose fixes AND have them reviewed before applying.
