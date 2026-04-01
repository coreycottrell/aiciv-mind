# src/aiciv_mind/tools — Tool Reference

Every tool Root can call. Each tool has a definition (Anthropic API format), a handler (async callable), and a `read_only` flag that controls whether it can run concurrently with other read-only tools.

## ToolRegistry

`ToolRegistry.default()` wires all tools. What gets registered depends on what's provided:

| Condition | Tools Added |
|-----------|-------------|
| Always | `bash`, `read_file`, `write_file`, `edit_file`, `grep`, `glob`, `web_search` |
| `memory_store` provided | `memory_search`, `memory_write` |
| `suite_client` provided | `hub_post`, `hub_reply`, `hub_read`, `hub_list_rooms`, `hub_queue_read` |
| `context_store` provided | `pin_memory`, `unpin_memory`, `introspect_context`, `get_context_snapshot` |
| `spawner` + `primary_bus` provided | `spawn_submind`, `send_to_submind` |
| `skills_dir` + `memory_store` provided | `list_skills`, `load_skill`, `create_skill` |
| `scratchpad_dir` provided | `scratchpad_read`, `scratchpad_write` |
| `manifest_path` provided | `sandbox_promote` |

**Concurrency:** Read-only tools (`grep`, `glob`, `read_file`, `memory_search`, `web_search`, etc.) run in parallel via `asyncio.gather` when called in the same model turn. Write tools run sequentially.

---

## Tool Reference

### bash.py — `bash`
Execute shell commands. Returns combined stdout+stderr with exit code.

```
bash(command: str) -> str
```

- Streams stdout+stderr, captures both
- Applies a 30-second timeout (configurable)
- Returns `EXIT CODE 0:\n<output>` or `EXIT CODE N:\n<output>`
- **read_only: False** — shell commands can write to disk

---

### files.py — `read_file`, `write_file`, `edit_file`, `grep`, `glob`

File system tools.

| Tool | Description | read_only |
|------|-------------|-----------|
| `read_file(file_path)` | Read file contents, returns as string | True |
| `write_file(file_path, content)` | Overwrite file (creates parent dirs) | False |
| `edit_file(file_path, old_string, new_string)` | Exact string replacement | False |
| `grep(pattern, path, flags?)` | Regex search via ripgrep | True |
| `glob(pattern, path?)` | File pattern matching | True |

---

### search.py — `search_web` (legacy), local search utilities

Internal search helpers. `grep` and `glob` are the primary search tools.

---

### web_search_tools.py — `web_search`

Web search via Ollama Cloud's `/api/web_search` endpoint.

```
web_search(query: str, max_results?: int = 5) -> str
```

- Reads `OLLAMA_API_KEY` from environment at call-time (not at registration — hot-add safe)
- Returns structured results or a clear error string if key is missing
- Graceful error: `"Web search unavailable: OLLAMA_API_KEY not set. Add OLLAMA_API_KEY=<key> to .env and restart the daemon."`
- Network timeout: ~15 seconds (Ollama Cloud can be slow from some hosts)
- **read_only: True**

---

### memory_tools.py — `memory_search`, `memory_write`

Access Root's persistent memory.

```
memory_search(query: str, memory_type?: str, limit?: int = 10) -> str
```
- FTS5 BM25 search over all memories for this agent
- Returns formatted list of matching memories with titles, content, and metadata

```
memory_write(title: str, content: str, memory_type?: str, tags?: list[str], confidence?: str) -> str
```
- Store a new memory
- `memory_type`: "learning" | "decision" | "error" | "handoff" | "observation"
- `confidence`: "HIGH" | "MEDIUM" | "LOW"
- Returns the new memory's UUID

**read_only:** `memory_search` is True, `memory_write` is False

---

### hub_tools.py — `hub_post`, `hub_reply`, `hub_read`, `hub_list_rooms`, `hub_queue_read`

Hub API interaction tools. Require `suite_client` to be wired into the registry.

| Tool | Description |
|------|-------------|
| `hub_post(room_id, title, body)` | Create a new thread in a Hub room |
| `hub_reply(thread_id, body)` | Post a reply to an existing thread |
| `hub_read(thread_id)` | Read posts from a thread |
| `hub_list_rooms(group_id)` | List rooms in a group |
| `hub_queue_read()` | Drain the passive room activity queue (`data/hub_queue.jsonl`) |

`hub_queue_read` is for passive room watching: the daemon logs new activity to the queue file, and Root reads it via this tool rather than being interrupted by every message.

All Hub tools use the `SuiteClient` (auto-refreshing JWT via AgentAuth).

---

### context_tools.py — `pin_memory`, `unpin_memory`, `introspect_context`, `get_context_snapshot`

Context window management tools.

```
pin_memory(memory_id: str) -> str    # Mark memory as always-in-context
unpin_memory(memory_id: str) -> str  # Remove pinned status
```

```
introspect_context() -> str
```
Returns a structured report:
- Session ID and turn count
- Number of messages in current conversation history
- Pinned memory count and titles
- Total memory count in database
- Top memories by depth score
- Recent session topics

```
get_context_snapshot() -> str
```
Compact version of introspect_context for quick context checks.

**All context tools: read_only: True**

---

### submind_tools.py — `spawn_submind`, `send_to_submind`

Sub-mind orchestration. Only registered when `spawner` + `primary_bus` are both provided.

```
spawn_submind(mind_id: str, manifest_path: str) -> str
```
- Launches a new tmux window running `run_submind.py --manifest <path> --id <mind_id>`
- Returns confirmation with pane_id and pid
- Raises SpawnError if a window with that mind_id already exists

```
send_to_submind(mind_id: str, task: str, timeout_seconds?: int = 120) -> str
```
- Sends a TASK message to the named sub-mind via ZMQ PrimaryBus
- Waits up to `timeout_seconds` for a RESULT message back
- Returns the sub-mind's response text or error message

**Both tools: read_only: False**

---

### skill_tools.py — `list_skills`, `load_skill`, `create_skill`

Root's skill library management.

```
list_skills() -> str             # List all registered skills
load_skill(skill_id: str) -> str # Read a skill's SKILL.md content into context
create_skill(skill_id, name, domain, content) -> str  # Write a new skill file
```

Skills live in `skills/<skill_id>/SKILL.md`. Loading a skill reads its content into Root's context window — the skill is live for that conversation turn.

---

### scratchpad_tools.py — `scratchpad_read`, `scratchpad_write`

Root's daily working memory. Stored in `scratchpad/YYYY-MM-DD.md`.

```
scratchpad_read(date?: str) -> str   # Read today's scratchpad (or specific date)
scratchpad_write(content: str) -> str # Append to today's scratchpad
```

The scratchpad is Root's between-session working notes. Not formal memories — quick state, TODOs, architectural observations.

---

### sandbox_tools.py — `sandbox_promote`

Self-modification gate. Only registered when `manifest_path` is provided and `self_modification_enabled: true` in the manifest.

```
sandbox_promote(changes: dict) -> str
```

Allows Root to apply approved changes to its own manifest or configuration. Guards against unapproved modifications.

---

## Adding a New Tool

1. Create `tools/your_tool.py` with:
   - A `_YOUR_DEFINITION: dict` in Anthropic format
   - A handler function or factory (`def _make_your_handler(...)`)
   - A `register_your_tool(registry: ToolRegistry, ...)` function

2. Call `register_your_tool(registry)` in `ToolRegistry.default()` with appropriate conditions

3. Add the tool name to the manifest's `tools:` list for any mind that should use it

Example:
```python
_MY_DEFINITION = {
    "name": "my_tool",
    "description": "Does something useful",
    "input_schema": {
        "type": "object",
        "properties": {"param": {"type": "string"}},
        "required": ["param"],
    },
}

async def _my_handler(tool_input: dict) -> str:
    return f"Result: {tool_input['param']}"

def register_my_tool(registry: ToolRegistry) -> None:
    registry.register("my_tool", _MY_DEFINITION, _my_handler, read_only=True)
```
