# Track A: SDK-Accelerated Mind -- Research Report

**Date**: 2026-03-30
**Researcher**: track-a-agent
**Confidence**: HIGH (per-section confidence noted below)

---

## Executive Summary

Track A builds aiciv-mind on top of existing Anthropic SDK primitives rather than implementing API interaction from scratch. Two SDKs are available: the **base `anthropic` Python SDK** (v0.86.0) which provides raw Messages API access, streaming, and a beta `tool_runner` that automates the agentic loop; and the **Claude Agent SDK** (`claude-agent-sdk`, v0.1.51) which wraps the entire Claude Code runtime as a library -- complete with built-in tools (Bash, Read, Edit, Grep, Glob), session management, subagent spawning, hooks, and permission controls. The Agent SDK is the stronger foundation for aiciv-mind because it eliminates the need to implement tool execution, the agentic loop, and context compaction. The main gap is IPC between primary and sub-minds -- neither SDK provides inter-process messaging, so aiciv-mind must build that layer (likely via Unix sockets, NATS, or a custom message bus over tmux pipes).

---

## 1. Anthropic Python SDK -- Tool Use Loop

**Confidence: HIGH**

### 1.1 What the SDK Provides

The `anthropic` Python SDK (v0.86.0, `pip install anthropic`) provides:

- **Messages API client** (`client.messages.create()`) -- synchronous and async
- **Streaming** via `client.messages.stream()` context manager
- **Tool definitions** in JSON Schema format passed as `tools` parameter
- **Tool use detection** via `stop_reason == "tool_use"` and `tool_use` content blocks
- **Beta tool_runner** (`client.beta.messages.tool_runner()`) -- automatic agentic loop
- **MCP integration** (`pip install anthropic[mcp]`) -- convert MCP tools to Anthropic format

### 1.2 The Manual Agentic Loop

The core pattern for building an autonomous agent with the base SDK:

```python
import anthropic

client = anthropic.AsyncAnthropic()

# Define tools as JSON Schema
tools = [
    {
        "name": "bash",
        "description": "Execute a bash command",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to execute"}
            },
            "required": ["command"]
        }
    }
]

async def execute_tool(name: str, input: dict) -> str:
    if name == "bash":
        proc = await asyncio.create_subprocess_shell(
            input["command"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode() + stderr.decode()
    raise ValueError(f"Unknown tool: {name}")

async def agent_loop(prompt: str):
    messages = [{"role": "user", "content": prompt}]

    while True:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system="You are an autonomous AI agent.",
            tools=tools,
            messages=messages,
        )

        # Append assistant response to history
        messages.append({"role": "assistant", "content": response.content})

        # Check if we're done (no tool calls)
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            # Extract final text
            text = "".join(b.text for b in response.content if b.type == "text")
            return text

        # Execute tools and collect results
        tool_results = []
        for block in tool_use_blocks:
            result = await execute_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result
            })

        # Feed results back as user message
        messages.append({"role": "user", "content": tool_results})
```

**Key observations:**
- The `messages` list is the conversation state -- it grows unboundedly unless you implement compaction
- Claude can return multiple `tool_use` blocks in a single response (parallel tool calls)
- Tool results MUST include the matching `tool_use_id`
- The loop terminates when `response.stop_reason == "end_turn"` (no tool blocks)

### 1.3 The Beta tool_runner (Automated Loop)

The SDK provides `client.beta.messages.tool_runner()` which automates the loop entirely:

```python
from anthropic import Anthropic, beta_tool

client = Anthropic()

@beta_tool
def bash(command: str) -> str:
    """Execute a bash command."""
    import subprocess
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr

runner = client.beta.messages.tool_runner(
    model="claude-sonnet-4-6",
    max_tokens=4096,
    tools=[bash],
    messages=[{"role": "user", "content": "List all Python files in this directory"}],
)

# Iterate over messages (auto-executes tools)
for message in runner:
    print(message)

# Or get final message directly
final = runner.until_done()
```

The `@beta_tool` decorator auto-generates the JSON Schema from type hints and docstrings. The runner:
- Automatically calls tools when Claude requests them
- Manages conversation history internally
- Supports streaming (`stream=True`)
- Catches tool exceptions and returns them as `is_error: true` tool results
- Supports compaction for long-running sessions

### 1.4 Streaming Primitives

```python
# Context manager streaming (accumulates final message)
async with client.messages.stream(
    model="claude-sonnet-4-6",
    max_tokens=4096,
    messages=messages,
    tools=tools,
) as stream:
    async for event in stream:
        if event.type == "text":
            print(event.text, end="", flush=True)
        elif event.type == "content_block_stop":
            # A complete content block (text or tool_use) is ready
            handle_block(event.content_block)

    final_message = await stream.get_final_message()

# Raw SSE streaming (lower memory, no accumulation)
stream = await client.messages.create(..., stream=True)
async for event in stream:
    handle_raw_event(event)
```

**Event types:** `text` (text delta + accumulated snapshot), `input_json` (tool input delta), `content_block_stop` (complete block), `message_stop` (complete message).

### 1.5 Concurrent Conversations

The SDK fully supports multiple concurrent conversations:

```python
client = anthropic.AsyncAnthropic()

# Each conversation is just a separate messages list
conv1_messages = [{"role": "user", "content": "Task A"}]
conv2_messages = [{"role": "user", "content": "Task B"}]

# Run in parallel with asyncio
results = await asyncio.gather(
    client.messages.create(model="claude-sonnet-4-6", messages=conv1_messages, ...),
    client.messages.create(model="claude-sonnet-4-6", messages=conv2_messages, ...),
)
```

One `AsyncAnthropic()` instance can handle many concurrent conversations -- conversations are stateless on the client side (the `messages` list IS the state). There is no session affinity in the SDK itself.

### 1.6 Model Switching Mid-Conversation

Yes, trivially supported. The `model` parameter is per-request, not per-client:

```python
# Turn 1: Use Sonnet for initial analysis
resp1 = await client.messages.create(model="claude-sonnet-4-6", messages=messages, ...)
messages.append({"role": "assistant", "content": resp1.content})

# Turn 2: Upgrade to Opus for complex reasoning
resp2 = await client.messages.create(model="claude-opus-4-6", messages=messages, ...)
```

The message history is model-agnostic. You can route different turns to different models seamlessly. This is a key advantage for integrating with AgentMind's tier system.

### 1.7 SDK Constraints for Autonomous Agents

| Constraint | Impact | Mitigation |
|-----------|--------|------------|
| No built-in tool execution | Must implement all tools yourself | Use `@beta_tool` decorator or Agent SDK |
| No context compaction | Messages grow unboundedly | Implement manual compaction or use tool_runner's beta compaction |
| No built-in persistence | Conversation state is in-memory only | Serialize `messages` list to disk/DB |
| No IPC/multi-process | Single-process only | Build your own IPC layer |
| Rate limits apply | Concurrent conversations share rate limits | Implement backoff/queuing |
| No file/bash tools | Must implement from scratch | ~200 lines per tool, or use Agent SDK |

---

## 2. Claude Agent SDK

**Confidence: HIGH**

### 2.1 Package Identity

- **Package name**: `claude-agent-sdk` (PyPI)
- **Install**: `pip install claude-agent-sdk`
- **Current version**: v0.1.51 (released 2026-03-27)
- **GitHub**: https://github.com/anthropics/claude-agent-sdk-python
- **Formerly**: `claude-code-sdk` (deprecated, renamed late 2025)
- **Nature**: Wraps the Claude Code CLI as a library. The CLI binary is bundled with the pip package.

### 2.2 What It Offers Beyond the Base SDK

The Agent SDK is fundamentally different from the base `anthropic` SDK. It does not call the Messages API directly -- it spawns the Claude Code runtime, which handles the entire agent loop internally.

| Capability | Base `anthropic` SDK | Agent SDK |
|-----------|---------------------|-----------|
| API access | Direct Messages API | Via Claude Code runtime |
| Tool execution | You implement | Built-in (Bash, Read, Edit, Write, Glob, Grep, WebSearch, WebFetch) |
| Agentic loop | You implement (or use beta tool_runner) | Handled by runtime |
| Context compaction | You implement | Automatic |
| Session persistence | You implement | Built-in (session IDs, resume, fork) |
| Subagent spawning | Not available | Built-in (`Agent` tool + `AgentDefinition`) |
| Hooks | Not available | PreToolUse, PostToolUse, Stop, SubagentStart, etc. |
| Permission control | Not available | Full permission system (allow/deny/approve) |
| MCP integration | Basic helpers | Full stdio/SSE/HTTP MCP servers |
| Custom tools | JSON Schema only | `@tool` decorator with in-process MCP servers |
| Model selection | Per-request | Per-agent or per-options |
| Cost tracking | You implement | Built-in (ResultMessage.total_cost_usd) |
| Streaming | Raw events | Structured message types (AssistantMessage, ResultMessage, etc.) |

### 2.3 Architecture

The Agent SDK operates by spawning a Claude Code subprocess:

```
Your Python process
    |
    |--> claude-agent-sdk.query()
            |
            |--> Spawns Claude Code CLI subprocess
                    |
                    |--> Claude Code runtime (Node.js)
                            |
                            |--> Anthropic Messages API
                            |--> Built-in tools (Bash, Read, Edit, ...)
                            |--> Custom tools (in-process MCP servers)
                            |--> Subagents (nested Claude Code processes)
```

**Two entry points:**

1. **`query()`** -- One-shot function. Creates a new session, returns `AsyncIterator[Message]`. Each call is independent.

2. **`ClaudeSDKClient`** -- Persistent client. Maintains session state across multiple `query()` calls. Supports interrupts, model switching mid-conversation, and bidirectional streaming.

```python
# Entry point 1: One-shot query
async for message in query(
    prompt="Fix the bug",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Edit", "Bash"],
        permission_mode="bypassPermissions",
        system_prompt="You are an autonomous AI agent for AiCIV.",
        model="claude-sonnet-4-6",
        max_turns=30,
        max_budget_usd=1.00,
        cwd="/home/corey/projects/AI-CIV/ACG",
    )
):
    handle(message)

# Entry point 2: Persistent client
async with ClaudeSDKClient(options=options) as client:
    await client.query("First task")
    async for msg in client.receive_response():
        handle(msg)

    await client.query("Follow-up task")  # Same session, full context
    async for msg in client.receive_response():
        handle(msg)

    # Switch model mid-session
    await client.set_model("claude-opus-4-6")

    # Interrupt a long-running task
    await client.interrupt()
```

### 2.4 Subagent Architecture

The Agent SDK has native subagent support via the `Agent` tool:

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Agent"],
    agents={
        "code-reviewer": AgentDefinition(
            description="Expert code reviewer",
            prompt="Analyze code quality and suggest improvements.",
            tools=["Read", "Glob", "Grep"],
            model="sonnet",  # Can specify different model per subagent
        ),
        "test-writer": AgentDefinition(
            description="Test writing specialist",
            prompt="Write comprehensive tests.",
            tools=["Read", "Write", "Bash"],
            model="sonnet",
        ),
    },
)
```

Each subagent:
- Gets its own fresh conversation context (does NOT inherit parent's message history)
- Has its own tool set and system prompt
- Can use a different model than the parent
- Returns only its final result to the parent (not the full transcript)
- Messages include `parent_tool_use_id` for tracking

### 2.5 Can It Serve as a Foundation for aiciv-mind?

**Pros:**
- Eliminates need to build tool execution (~2000 lines saved)
- Eliminates need to build the agentic loop (~500 lines saved)
- Eliminates need to build context compaction (complex problem, already solved)
- Session persistence is built in
- Subagent architecture maps to team-lead pattern
- Hooks provide injection points for aiciv-mind's custom behaviors
- Custom tools via `@tool` decorator for AiCIV-specific operations (Hub API, AgentAuth, etc.)
- Permission system provides safety controls out of the box
- Cost tracking built in

**Cons:**
- **Process overhead**: Each agent spawns a Claude Code CLI subprocess (Node.js). A primary + 10 sub-minds = 11 Node.js processes.
- **Opinionated runtime**: The agent loop is a black box. You cannot modify how tools are executed, how streaming works internally, or how compaction is performed.
- **No direct API access**: Cannot integrate with AgentMind's tiered routing -- all API calls go through Claude Code's internal routing.
- **Claude-only**: Cannot route to non-Anthropic models (Groq, Together, etc.) within the agent loop. AgentMind integration would require a different approach.
- **Subprocess communication**: The SDK communicates with the CLI via stdio JSON. This adds serialization overhead and makes debugging harder.
- **Version coupling**: Tied to Claude Code releases. Breaking changes in Claude Code affect your agent.
- **No tmux-native spawning**: Subagents are in-process (nested subprocesses), not separate tmux panes. For aiciv-mind's tmux-pane-per-mind architecture, you would spawn separate `query()` calls in separate processes, not use the built-in `Agent` tool.

### 2.6 Key Options Reference

```python
@dataclass
class ClaudeAgentOptions:
    allowed_tools: list[str]           # Auto-approved tools
    disallowed_tools: list[str]        # Blocked tools
    system_prompt: str | None          # Custom system prompt
    permission_mode: str               # "default" | "acceptEdits" | "bypassPermissions"
    model: str | None                  # Model ID
    max_turns: int | None              # Max tool-use rounds
    max_budget_usd: float | None       # Cost cap
    cwd: str | Path | None             # Working directory
    mcp_servers: dict                  # MCP server configs
    hooks: dict                        # Event hooks
    agents: dict | None                # Subagent definitions
    resume: str | None                 # Resume session by ID
    thinking: ThinkingConfig | None    # Extended thinking config
    effort: str | None                 # "low" | "medium" | "high" | "max"
    env: dict[str, str]                # Environment variables
    setting_sources: list[str] | None  # Load CLAUDE.md, skills, etc.
    sandbox: SandboxSettings | None    # Sandbox configuration
    enable_file_checkpointing: bool    # File change tracking
```

---

## 3. SDK Constraints for Sub-Mind Architecture

**Confidence: HIGH**

### 3.1 Sub-Mind = Separate Process

Each sub-mind (team lead) should be a separate OS process with its own conversation history. Both SDKs support this cleanly:

**Base SDK approach:**
```python
# Each sub-mind is a separate asyncio task or process
# with its own messages list
class SubMind:
    def __init__(self, name: str, system_prompt: str, model: str):
        self.name = name
        self.client = anthropic.AsyncAnthropic()
        self.messages: list[dict] = []
        self.system_prompt = system_prompt
        self.model = model

    async def run(self, task: str):
        self.messages.append({"role": "user", "content": task})
        while True:
            response = await self.client.messages.create(
                model=self.model,
                system=self.system_prompt,
                messages=self.messages,
                tools=self.tools,
                max_tokens=8192,
            )
            # ... tool loop as shown above
```

**Agent SDK approach:**
```python
# Each sub-mind is a separate query() call, possibly in its own process
async def run_submind(name: str, task: str, pane_id: str):
    async for message in query(
        prompt=task,
        options=ClaudeAgentOptions(
            system_prompt=f"You are {name}, a team lead for A-C-Gee.",
            allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep"],
            permission_mode="bypassPermissions",
            model="claude-sonnet-4-6",
            max_turns=50,
            max_budget_usd=2.00,
        ),
    ):
        # Send progress to tmux pane
        if isinstance(message, AssistantMessage):
            write_to_pane(pane_id, format_message(message))
```

### 3.2 Conversation State Persistence

**Base SDK**: The `messages` list is plain Python data. Serialize it:

```python
import json

# Save state
def save_state(mind_id: str, messages: list):
    with open(f"state/{mind_id}.json", "w") as f:
        json.dump(messages, f)

# Restore state
def load_state(mind_id: str) -> list:
    with open(f"state/{mind_id}.json") as f:
        return json.load(f)
```

Caveat: Message history can be large (megabytes for long sessions). Consider compressing or implementing rolling compaction.

**Agent SDK**: Built-in session persistence. Use `resume=session_id` to restore:

```python
# First run -- capture session_id
session_id = None
async for message in query(prompt="Start work", options=options):
    if isinstance(message, ResultMessage):
        session_id = message.session_id

# Later -- resume with full context
async for message in query(
    prompt="Continue work",
    options=ClaudeAgentOptions(resume=session_id),
):
    handle(message)
```

### 3.3 Parallel Tool Execution Within One Conversation

Both SDKs support Claude requesting multiple tool calls in a single turn. The base SDK lets you execute them concurrently:

```python
# Claude returns multiple tool_use blocks
tool_blocks = [b for b in response.content if b.type == "tool_use"]

# Execute in parallel
results = await asyncio.gather(*[
    execute_tool(b.name, b.input) for b in tool_blocks
])

# Collect results
tool_results = [
    {"type": "tool_result", "tool_use_id": b.id, "content": r}
    for b, r in zip(tool_blocks, results)
]
```

The Agent SDK handles this automatically -- read-only tools (Read, Glob, Grep, MCP read-only tools) run concurrently; state-modifying tools (Edit, Write, Bash) run sequentially.

You can control this at the API level with `tool_choice`:
- `"auto"` -- Claude decides (may use multiple tools)
- `"any"` -- Must use at least one tool
- `"tool"` -- Force specific tool
- `"none"` -- No tools
- `disable_parallel_tool_use=True` -- Restrict to one tool per turn

### 3.4 Memory Footprint

**Base `anthropic` SDK:**
- The SDK itself is lightweight (~50MB installed with dependencies)
- Client instance: negligible memory (just httpx client config)
- Conversation state: proportional to message history (can grow to megabytes)
- Uses lazy initialization -- resources created on first access
- `client.copy()` uses weak references to avoid memory leaks

**Agent SDK:**
- Each `query()` call spawns a Claude Code subprocess (Node.js runtime)
- Per-subprocess overhead: ~50-100MB RSS (Node.js baseline)
- 10 concurrent sub-minds = ~500MB-1GB additional RAM just for the runtimes
- Trade-off: you get full Claude Code capabilities without implementing anything

**For aiciv-mind with 10+ sub-minds:**
- Base SDK: ~200MB total (SDK + 10 conversation states)
- Agent SDK: ~1-1.5GB total (10 Node.js subprocesses + Python orchestrator)

---

## 4. Minimal Tool Implementations

**Confidence: HIGH**

### 4.1 Anthropic Tool Definition Format

Every tool needs: `name`, `description`, `input_schema` (JSON Schema). The format is identical across base SDK and custom Agent SDK tools.

### 4.2 Bash Execution Tool

```python
import asyncio
import shlex

BASH_TOOL = {
    "name": "bash",
    "description": "Execute a bash command. Use for running scripts, git operations, "
                   "system commands. Returns stdout and stderr combined.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 120)",
                "default": 120
            }
        },
        "required": ["command"]
    }
}

BLOCKED_PATTERNS = [
    "rm -rf /", "rm -rf ~", "rm -rf /*",
    ":(){ :|:& };:",  # fork bomb
    "mkfs.", "dd if=",
    "> /dev/sda",
]

async def execute_bash(command: str, timeout: int = 120, cwd: str = None) -> str:
    """Execute bash command with safety checks."""
    # Safety check
    for pattern in BLOCKED_PATTERNS:
        if pattern in command:
            return f"BLOCKED: Command contains prohibited pattern '{pattern}'"

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        output = stdout.decode("utf-8", errors="replace")
        if stderr:
            output += "\nSTDERR:\n" + stderr.decode("utf-8", errors="replace")
        # Truncate very long output
        if len(output) > 50000:
            output = output[:25000] + "\n\n... [truncated] ...\n\n" + output[-25000:]
        return output or "(no output)"
    except asyncio.TimeoutError:
        proc.kill()
        return f"TIMEOUT: Command exceeded {timeout}s limit"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
```

### 4.3 File Read Tool

```python
FILE_READ_TOOL = {
    "name": "read_file",
    "description": "Read the contents of a file. Returns the file content with line numbers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
            "offset": {"type": "integer", "description": "Start line (1-based)", "default": 1},
            "limit": {"type": "integer", "description": "Max lines to read", "default": 2000},
        },
        "required": ["file_path"]
    }
}

def execute_read_file(file_path: str, offset: int = 1, limit: int = 2000) -> str:
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
        start = max(0, offset - 1)
        end = start + limit
        numbered = [f"{i+start+1}\t{line}" for i, line in enumerate(lines[start:end])]
        return "".join(numbered) or "(empty file)"
    except FileNotFoundError:
        return f"ERROR: File not found: {file_path}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
```

### 4.4 File Write Tool

```python
FILE_WRITE_TOOL = {
    "name": "write_file",
    "description": "Write content to a file, creating it if it doesn't exist.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["file_path", "content"]
    }
}

def execute_write_file(file_path: str, content: str) -> str:
    import os
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        return f"Wrote {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
```

### 4.5 File Edit Tool

```python
FILE_EDIT_TOOL = {
    "name": "edit_file",
    "description": "Replace an exact string in a file with a new string.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "old_string": {"type": "string", "description": "Exact text to find and replace"},
            "new_string": {"type": "string", "description": "Replacement text"},
        },
        "required": ["file_path", "old_string", "new_string"]
    }
}

def execute_edit_file(file_path: str, old_string: str, new_string: str) -> str:
    try:
        with open(file_path, "r") as f:
            content = f.read()
        count = content.count(old_string)
        if count == 0:
            return f"ERROR: old_string not found in {file_path}"
        if count > 1:
            return f"ERROR: old_string found {count} times (must be unique)"
        new_content = content.replace(old_string, new_string, 1)
        with open(file_path, "w") as f:
            f.write(new_content)
        return f"Edited {file_path}: replaced 1 occurrence"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
```

### 4.6 Grep/Glob Tools

```python
import glob as globlib
import re

GREP_TOOL = {
    "name": "grep",
    "description": "Search file contents with regex. Returns matching lines with file paths and line numbers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
            "glob_filter": {"type": "string", "description": "File glob pattern, e.g. '*.py'"},
        },
        "required": ["pattern"]
    }
}

GLOB_TOOL = {
    "name": "glob",
    "description": "Find files matching a glob pattern.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.py'"},
            "path": {"type": "string", "description": "Base directory", "default": "."},
        },
        "required": ["pattern"]
    }
}
```

### 4.7 Existing Open-Source Tool Libraries

There are no widely-adopted standalone "tool libraries" for the Anthropic SDK. However:

- **Agent SDK built-in tools** -- The Agent SDK ships with Bash, Read, Edit, Write, Glob, Grep, WebSearch, WebFetch. These are production-grade implementations used by Claude Code.
- **MCP servers** -- Hundreds of MCP servers provide tools (databases, browsers, APIs). The base SDK's `anthropic[mcp]` extras provide `async_mcp_tool()` for converting MCP tools.
- **LangChain/LlamaIndex** -- These frameworks have tool abstractions but add significant overhead and are model-agnostic rather than Claude-optimized.
- **Promptfoo** -- Provides a Claude Agent SDK test harness for evaluating agent behavior.

**Recommendation for aiciv-mind**: Use the Agent SDK's built-in tools if going the Agent SDK route. If going the base SDK route, implement the 6 core tools above (~400 lines total) -- they are simple and give you full control.

---

## 5. Recommended Track A Architecture

**Confidence: MEDIUM-HIGH**

### 5.1 Two Sub-Tracks

Track A splits into two viable sub-approaches:

#### Track A1: Agent SDK Foundation

Use `claude-agent-sdk` as the primary runtime. Each mind (primary + sub-minds) is a separate Python process running `query()` or `ClaudeSDKClient`. Custom behavior injected via hooks and custom tools.

```
aiciv-mind (orchestrator process)
    |
    |--> Primary Mind process
    |       |--> ClaudeSDKClient (persistent session)
    |       |--> Custom tools (Hub API, AgentAuth, AgentCal, IPC)
    |       |--> Hooks (pre/post tool, stop, subagent lifecycle)
    |
    |--> Sub-Mind: gateway-lead (tmux pane %1)
    |       |--> query() with AgentDefinition-style config
    |       |--> Own session, own tools, own working directory
    |
    |--> Sub-Mind: comms-lead (tmux pane %2)
    |       |--> query() with comms-specific tools
    |
    |--> IPC Message Bus (Unix sockets / NATS / tmux pipes)
    |       |--> Primary <-> Sub-Mind messaging
    |       |--> Task assignment, result collection, shutdown
    |
    |--> Scheduler
    |       |--> BOOP timing, calendar integration
    |       |--> Sub-mind lifecycle (spawn, monitor, shutdown)
    |
    |--> Memory Manager
            |--> Session state persistence
            |--> Memory search/write operations
            |--> Cross-session context
```

**Advantages**: Built-in tool execution, context compaction, session persistence. Most complex problems already solved.

**Disadvantages**: Cannot route to non-Claude models. ~1GB+ RAM for 10 sub-minds. Black-box agent loop.

#### Track A2: Base SDK + Custom Everything

Use `anthropic` SDK for API calls. Build the agent loop, tool execution, compaction, and session management from scratch. Integrate AgentMind for model routing.

```
aiciv-mind (single Python process or multi-process)
    |
    |--> Primary Mind
    |       |--> Custom agent loop (while tool_use: execute, feed back)
    |       |--> Messages API via anthropic SDK (or AgentMind HTTP)
    |       |--> Tool executor (bash, read, edit, grep, glob, web)
    |       |--> Context compactor (summarize when approaching limit)
    |
    |--> Sub-Mind processes (each with own agent loop)
    |       |--> Can route via AgentMind (tier-based model selection)
    |       |--> Own tool set, own conversation state
    |
    |--> IPC Message Bus
    |--> Scheduler
    |--> Memory Manager
```

**Advantages**: Full control. Can integrate AgentMind for multi-model routing. Lower memory footprint. No Node.js dependency.

**Disadvantages**: Must implement tool execution, agentic loop, compaction, session persistence. ~2-3 weeks more build time.

### 5.2 IPC Between Primary and Sub-Minds

Neither SDK provides inter-process communication. This is the main gap aiciv-mind must fill. Options:

| IPC Method | Pros | Cons |
|-----------|------|------|
| **Unix domain sockets** | Fast, simple, no external deps | Single-host only, must implement protocol |
| **NATS JetStream** | Already in APS architecture, persistent, pub/sub | External dependency, more complex setup |
| **Redis pub/sub** | Fast, well-understood | External dependency, no persistence |
| **tmux pipes** | Zero deps, already using tmux | Fragile, text-only, no structured messages |
| **Shared SQLite** | Persistent, queryable, zero external deps | Polling-based (not event-driven), slower |
| **File-based (JSON)** | Simplest possible | Polling, race conditions, slowest |

**Recommendation**: Start with Unix domain sockets for v0.1 (fast, zero deps, good enough). Migrate to NATS when the fleet architecture matures.

IPC message format (minimal):
```python
@dataclass
class MindMessage:
    type: str           # "task" | "result" | "status" | "shutdown" | "message"
    sender: str         # "primary" | "gateway-lead" | etc.
    recipient: str      # Target mind name
    payload: dict       # Type-specific data
    timestamp: float    # Unix timestamp
    id: str             # UUID for correlation
```

### 5.3 Sub-Mind Spawning

```python
import subprocess
import os

async def spawn_submind(
    name: str,
    task: str,
    system_prompt: str,
    model: str = "claude-sonnet-4-6",
    tmux_session: str = "aiciv-mind",
) -> str:
    """Spawn a sub-mind in its own tmux pane."""

    # Create tmux pane
    pane_id = subprocess.check_output(
        ["tmux", "split-window", "-t", tmux_session, "-P", "-F", "#{pane_id}",
         "python", "-m", "aiciv_mind.submind",
         "--name", name,
         "--task", task,
         "--model", model,
         "--ipc-socket", f"/tmp/aiciv-mind-{name}.sock"],
        text=True
    ).strip()

    return pane_id
```

### 5.4 The Primary Mind Loop (Track A1 -- Agent SDK)

```python
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, ResultMessage

class PrimaryMind:
    def __init__(self):
        self.submind_panes: dict[str, str] = {}  # name -> pane_id
        self.ipc = IPCBus()

    async def run(self):
        options = ClaudeAgentOptions(
            system_prompt=self.load_constitution(),
            allowed_tools=[
                "Read", "Edit", "Bash", "Glob", "Grep",
                # Custom tools registered via MCP
                "mcp__aiciv__spawn_submind",
                "mcp__aiciv__send_message",
                "mcp__aiciv__check_submind",
                "mcp__aiciv__hub_api",
                "mcp__aiciv__agentcal",
            ],
            permission_mode="bypassPermissions",
            model="claude-opus-4-6",
            max_budget_usd=5.00,
            cwd="/home/corey/projects/AI-CIV/ACG",
            mcp_servers={
                "aiciv": {
                    "command": "python",
                    "args": ["-m", "aiciv_mind.mcp_server"],
                }
            },
            setting_sources=["project"],  # Load CLAUDE.md
        )

        async with ClaudeSDKClient(options=options) as client:
            # Initial task
            await client.query("Begin session. Check scratchpad and recent handoff.")
            async for message in client.receive_response():
                await self.handle_message(message)

            # Continuous operation loop
            while True:
                task = await self.ipc.receive_next_task()
                await client.query(task)
                async for message in client.receive_response():
                    await self.handle_message(message)
```

### 5.5 The Primary Mind Loop (Track A2 -- Base SDK)

```python
import asyncio
import anthropic

class PrimaryMind:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic()
        self.messages: list[dict] = []
        self.tools = [BASH_TOOL, FILE_READ_TOOL, FILE_WRITE_TOOL,
                      FILE_EDIT_TOOL, GREP_TOOL, GLOB_TOOL,
                      SPAWN_SUBMIND_TOOL, SEND_MESSAGE_TOOL,
                      HUB_API_TOOL, AGENTCAL_TOOL]
        self.submind_panes: dict[str, str] = {}
        self.ipc = IPCBus()

    async def run(self, initial_prompt: str):
        self.messages.append({"role": "user", "content": initial_prompt})

        while True:
            # Call Claude (could route through AgentMind for tier selection)
            response = await self.client.messages.create(
                model="claude-opus-4-6",
                system=self.load_constitution(),
                messages=self.messages,
                tools=self.tools,
                max_tokens=8192,
            )

            self.messages.append({"role": "assistant", "content": response.content})

            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_blocks:
                # Agent is done with current task
                result = self.extract_text(response)
                await self.on_task_complete(result)

                # Wait for next task
                next_task = await self.ipc.receive_next_task()
                self.messages.append({"role": "user", "content": next_task})
                continue

            # Execute tools (parallel where safe)
            tool_results = await self.execute_tools(tool_blocks)
            self.messages.append({"role": "user", "content": tool_results})

            # Check context window size and compact if needed
            if self.estimate_tokens() > 150_000:
                await self.compact_context()
```

---

## 6. Track A Assessment

| Dimension | Track A1 (Agent SDK) | Track A2 (Base SDK) |
|-----------|---------------------|---------------------|
| **Build effort** | 2-3 weeks (IPC + custom tools + orchestrator) | 4-6 weeks (all of A1 + tool execution + loop + compaction + session mgmt) |
| **SDK lock-in risk** | HIGH -- tied to Claude Code runtime, no multi-model | MEDIUM -- tied to Anthropic API format, but can add AgentMind routing |
| **Streaming control** | LIMITED -- Agent SDK streams structured messages, but loop internals are opaque | FULL -- you own the stream, can process events however you want |
| **Multi-model support** | NO -- Agent SDK only calls Claude via its internal routing | YES -- can route through AgentMind to any model (Groq, Together, local) |
| **Sub-mind spawning** | GOOD -- spawn separate `query()` processes, each in own tmux pane | GOOD -- same approach, more control over lifecycle |
| **Production readiness** | HIGHER -- built-in safety (permissions, hooks, cost caps, compaction) | LOWER -- must implement all safety yourself |
| **Memory footprint** | HEAVY -- ~100MB per Node.js subprocess per sub-mind | LIGHT -- ~20MB per sub-mind (Python + messages list) |
| **AgentMind integration** | HARD -- cannot intercept API calls to route through AgentMind | EASY -- replace `client.messages.create()` with AgentMind HTTP call |
| **Context compaction** | BUILT-IN -- automatic, customizable via CLAUDE.md instructions | MUST BUILD -- significant engineering effort |
| **Tool ecosystem** | RICH -- all Claude Code tools + MCP + custom tools | MINIMAL -- must build core tools (~400 lines) |
| **Debugging** | HARDER -- subprocess stdio, structured messages | EASIER -- direct API calls, full visibility into messages |

### Recommendation

**Start with Track A1 (Agent SDK) for v0.1.** The Agent SDK eliminates the hardest problems (tool execution, agentic loop, compaction, session management). The main work is:

1. IPC message bus between primary and sub-minds (~1 week)
2. Custom MCP tools for AiCIV services (Hub, AgentAuth, AgentCal) (~1 week)
3. Tmux pane management for sub-mind visibility (~3 days)
4. Scheduler for BOOP/calendar integration (~2 days)
5. Memory layer for cross-session persistence (~3 days)

**Migrate to Track A2 when needed.** If multi-model routing (AgentMind), lower memory footprint, or full loop control become critical, migrate the core loop to base SDK while keeping the Agent SDK's tool definitions as reference implementations.

**The hybrid approach**: Use Agent SDK for sub-minds (they benefit most from built-in tools) and base SDK for the primary mind (it needs the most control and AgentMind integration). This gets the best of both worlds.

---

## 7. Sources

| Source | URL | Retrieved | Confidence |
|--------|-----|-----------|------------|
| Agent SDK Overview | https://platform.claude.com/docs/en/agent-sdk/overview | 2026-03-30 | HIGH |
| Agent SDK Python Reference | https://platform.claude.com/docs/en/agent-sdk/python | 2026-03-30 | HIGH |
| Agent SDK Quickstart | https://platform.claude.com/docs/en/agent-sdk/quickstart | 2026-03-30 | HIGH |
| Agent SDK Agent Loop | https://platform.claude.com/docs/en/agent-sdk/agent-loop | 2026-03-30 | HIGH |
| Anthropic Python SDK GitHub | https://github.com/anthropics/anthropic-sdk-python | 2026-03-30 | HIGH |
| Anthropic SDK Helpers | https://github.com/anthropics/anthropic-sdk-python/blob/main/helpers.md | 2026-03-30 | HIGH |
| Tool Use - Define Tools | https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use | 2026-03-30 | HIGH |
| Tool Runner (SDK) | https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner | 2026-03-30 | HIGH |
| Advanced Tool Use | https://www.anthropic.com/engineering/advanced-tool-use | 2026-03-30 | HIGH |
| Claude Agent SDK PyPI | https://pypi.org/project/claude-agent-sdk/ | 2026-03-30 | HIGH |
| Temporal Agentic Loop Example | https://docs.temporal.io/ai-cookbook/agentic-loop-tool-call-claude-python | 2026-03-30 | MEDIUM |
| SDK Client Architecture (DeepWiki) | https://deepwiki.com/anthropics/anthropic-sdk-python/4-client-architecture | 2026-03-30 | MEDIUM |
| Concurrent Agent Conversations | https://codesignal.com/learn/courses/parallelizing-claude-agentic-systems-in-python/lessons/concurrent-agent-conversations | 2026-03-30 | MEDIUM |
| AgentMind SPEC (local) | projects/agentmind/SPEC.md | 2026-03-30 | HIGH |
