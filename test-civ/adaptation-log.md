# test-civ — Adaptation Log

## Phase 0: Self-Discovery

**Started**: 2026-04-03
**Completed**: 2026-04-04
**Executed by**: Mind Lead (ACG) — codewright-lead delegation failed (timeout), manual execution

### Tasks Completed

| Task | Status | Details |
|------|--------|---------|
| 0.1 Read identity.json | DONE | `.aiciv-identity.json` parsed: civ_name=test-civ, human=Corey Cottrell, parent=acg |
| 0.2 Extract infrastructure | DONE | IPC socket, memory paths, manifest paths extracted |
| 0.3 Validate seed | DONE | `memories/identity/seed-conversation.md` present + `human-profile.json` present |
| 0.4 Replace placeholders | DONE | 3 files: constitution.md, operations.md, manifests/research-lead.yaml — 0 placeholders remaining |
| 0.5 Write core-identity.json | DONE | `memories/identity/core-identity.json` — synthesized from identity + seed + human profile |
| 0.6 Write adaptation-log.md | DONE | This file |
| 0.7 Verify no placeholders | DONE | `grep -r '\${' test-civ/` returns 0 matches |

### Placeholder Substitutions

| Placeholder | Value | Source |
|-------------|-------|--------|
| `${CIV_NAME}` | test-civ | .aiciv-identity.json |
| `${DISPLAY_NAME}` | Test Civilization | .aiciv-identity.json |
| `${HUMAN_NAME}` | Corey Cottrell | .aiciv-identity.json |
| `${CIV_EMAIL}` | acgee.ai@gmail.com | .aiciv-identity.json (human_email) |
| `${PARENT_CIV}` | acg | .aiciv-identity.json |
| `${CIV_ROOT}` | /home/corey/projects/AI-CIV/aiciv-mind/test-civ | .aiciv-identity.json |
| `${IPC_SOCKET}` | /tmp/aiciv-test-civ-router.ipc | .aiciv-identity.json |

### Failures Encountered

1. **Codewright-lead timeout (attempt 1)**: `asyncio.TimeoutError` after 120s on first LLM call. Root cause: concurrent sub-minds saturating LiteLLM proxy. Fixed: increased `call_timeout_s` to 300s in manifest, added descriptive TimeoutError message.

2. **Codewright-lead format mismatch (attempt 2)**: M2.7 emitted tool calls as `function read_file\nfile_path "..."` — a 6th format variant not in the parser. Task "completed" with 0 executed tool calls.

3. **Manual execution**: Mind Lead executed Phase 0 directly after two failed codewright-lead attempts.

### Architecture Notes

- Phase 0 is intentionally simple (read, substitute, write) to test the self-discovery pipeline
- The placeholder substitution pattern is the same one the fork-awakening system uses
- core-identity.json becomes the boot context anchor for all subsequent phases
