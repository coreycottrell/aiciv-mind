# Track B: Sovereign Mind -- Research Report

**Date**: 2026-03-30
**Researcher**: track-b-agent
**Status**: Complete

---

## Executive Summary

Track B ("Sovereign Mind") proposes building aiciv-mind from raw HTTP calls to model APIs, owning the full stack from SSE parsing through tool dispatch to sub-mind process management. This report provides the technical foundation for that build.

**Key findings:**

1. **The Claude streaming protocol is well-documented and parseable in ~150 lines of Python.** Six SSE event types, two delta types for text and tool_use input. The hard part is not parsing -- it is accumulating partial JSON for tool inputs.

2. **The open-source framework landscape validates our approach.** Every framework surveyed (LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Pydantic AI, smolagents) solves a general problem. We have a specific one: autonomous AI civilizations with native service integration. The overhead of adapting any of these exceeds the cost of building a purpose-fit harness.

3. **Claude Code is now open source AND has an Agent SDK.** The Claude Agent SDK (`@anthropic-ai/agent-sdk`) exposes the same agent loop, tools, context management, and subagent spawning that powers Claude Code. It is available in both Python and TypeScript. This is the most direct competitor to Track B -- it gives us the loop for free but locks us to Anthropic models and their permission/tool abstractions.

4. **Model-agnostic tool use is achievable with a thin translation layer.** The three major formats (OpenAI, Anthropic, Gemini) differ in wrapping, not in substance. AgentMind already has a working `_translate_tools()` function. LiteLLM is viable as an abstraction but adds a heavy dependency; a ~200-line normalizer is sufficient.

5. **The Mind abstraction is ~800 lines of core loop code.** An event-driven async class with tool registry, message history, streaming SSE consumer, and IPC bus. Sub-minds need only three methods: `receive_task()`, `send_result()`, `heartbeat()`.

**Bottom line:** Track B is a 6-8 week build for a working prototype, with the core loop achievable in week 1. The real engineering is in the sub-mind process model, memory integration, and service bus -- not in the LLM interface.

---

## 1. Claude Messages API Streaming Protocol

**Confidence: HIGH** (verified against official docs at platform.claude.com)

### 1.1 SSE Event Types

When you set `"stream": true` on a Messages API request, the response is a stream of server-sent events. Each event has a named `event:` line and a `data:` line containing JSON.

The event flow for every stream:

```
message_start
  content_block_start (index 0)
    content_block_delta (index 0, repeated)
  content_block_stop (index 0)
  content_block_start (index 1)     # if multiple blocks
    content_block_delta (index 1)
  content_block_stop (index 1)
message_delta
message_stop
```

Plus `ping` events interspersed anywhere and `error` events on failure.

### 1.2 Event Type Reference

| Event | Data Structure | Purpose |
|-------|---------------|---------|
| `message_start` | `{"type": "message_start", "message": {Message object with empty content}}` | Opens the stream; includes `id`, `model`, `role`, initial `usage` |
| `content_block_start` | `{"type": "content_block_start", "index": N, "content_block": {"type": "text"|"tool_use", ...}}` | Begins a content block; for `tool_use`, includes `id`, `name`, `input: {}` |
| `content_block_delta` | `{"type": "content_block_delta", "index": N, "delta": {delta object}}` | Incremental update to the block at `index` |
| `content_block_stop` | `{"type": "content_block_stop", "index": N}` | Closes the content block |
| `message_delta` | `{"type": "message_delta", "delta": {"stop_reason": "end_turn"|"tool_use"}, "usage": {cumulative}}` | Top-level message changes; includes final `stop_reason` |
| `message_stop` | `{"type": "message_stop"}` | Stream is complete |
| `ping` | `{"type": "ping"}` | Keep-alive |
| `error` | `{"type": "error", "error": {"type": "...", "message": "..."}}` | Stream-level error |

### 1.3 Delta Types

| Delta Type | Appears In | Structure |
|-----------|-----------|-----------|
| `text_delta` | Text content blocks | `{"type": "text_delta", "text": "chunk"}` |
| `input_json_delta` | Tool use content blocks | `{"type": "input_json_delta", "partial_json": "{\"key\": \"partial"}` |
| `thinking_delta` | Thinking content blocks (extended thinking) | `{"type": "thinking_delta", "thinking": "reasoning text"}` |
| `signature_delta` | Thinking blocks (before stop) | `{"type": "signature_delta", "signature": "base64..."}` |

### 1.4 Tool Use Streaming -- Complete Example

Raw SSE for a tool_use response (from official docs):

```sse
event: message_start
data: {"type":"message_start","message":{"id":"msg_014p7gG3wDgGV9EUtLvnow3U","type":"message","role":"assistant","model":"claude-opus-4-6","stop_sequence":null,"usage":{"input_tokens":472,"output_tokens":2},"content":[],"stop_reason":null}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Okay, let's check the weather for San Francisco, CA:"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_01T1x1fJ34qAmk2tNTrN7Up6","name":"get_weather","input":{}}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"location\":"}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":" \"San Francisc"}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"o, CA\""}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":", \"unit\": \"fahrenheit\"}"}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"tool_use","stop_sequence":null},"usage":{"output_tokens":89}}

event: message_stop
data: {"type":"message_stop"}
```

Key observations:
- The `content_block_start` for `tool_use` carries the `id` and `name` but `input: {}` (empty)
- The `input_json_delta` values are **partial JSON strings** that must be concatenated
- You parse the full JSON only after `content_block_stop`
- The `message_delta` has `stop_reason: "tool_use"` (not `"end_turn"`)

### 1.5 Tool Definition Format (input to the API)

```json
{
  "name": "get_weather",
  "description": "Get the current weather in a given location",
  "input_schema": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": "The city and state, e.g. San Francisco, CA"
      }
    },
    "required": ["location"]
  }
}
```

Key: Anthropic uses `input_schema` (not OpenAI's `parameters`). The schema itself is standard JSON Schema.

### 1.6 Tool Result Format (sending results back)

After receiving a `tool_use` block, you append the assistant's full response to message history, then add a user message with `tool_result` content blocks:

```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_01T1x1fJ34qAmk2tNTrN7Up6",
      "content": "72 degrees Fahrenheit, sunny"
    }
  ]
}
```

For errors: add `"is_error": true` to the tool_result block. Claude will see the error and adjust.

For multiple parallel tool calls: include one `tool_result` per `tool_use` block in a single user message.

### 1.7 Minimal Streaming SSE Parser (Python)

```python
import json
import httpx
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

@dataclass
class ContentBlock:
    index: int
    type: str  # "text" or "tool_use"
    text: str = ""
    tool_id: str = ""
    tool_name: str = ""
    tool_input_json: str = ""  # accumulated partial JSON

@dataclass
class StreamResult:
    message_id: str = ""
    model: str = ""
    content_blocks: list[ContentBlock] = field(default_factory=list)
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

async def stream_messages(
    api_key: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
    system: str = "",
) -> AsyncIterator[tuple[str, Any]]:
    """
    Yields (event_type, parsed_data) tuples from the SSE stream.
    Caller accumulates content blocks as needed.
    """
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST", "https://api.anthropic.com/v1/messages",
            json=body, headers=headers,
        ) as resp:
            resp.raise_for_status()
            event_type = ""
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    yield event_type, data
                # blank lines are SSE record separators -- skip


async def run_tool_loop(
    api_key: str,
    messages: list[dict],
    tools: list[dict],
    tool_executor,  # callable(name, input) -> str
    model: str = "claude-sonnet-4-6",
    system: str = "",
    max_turns: int = 20,
) -> list[dict]:
    """
    Complete agentic loop: stream response, execute tools, repeat.
    Returns the final message history.
    """
    for turn in range(max_turns):
        result = StreamResult()
        current_block: ContentBlock | None = None

        async for event_type, data in stream_messages(
            api_key, messages, tools, model, system=system
        ):
            if event_type == "message_start":
                msg = data["message"]
                result.message_id = msg["id"]
                result.model = msg["model"]
                result.input_tokens = msg.get("usage", {}).get("input_tokens", 0)

            elif event_type == "content_block_start":
                block = data["content_block"]
                current_block = ContentBlock(
                    index=data["index"],
                    type=block["type"],
                    tool_id=block.get("id", ""),
                    tool_name=block.get("name", ""),
                )
                result.content_blocks.append(current_block)

            elif event_type == "content_block_delta":
                delta = data["delta"]
                if delta["type"] == "text_delta":
                    current_block.text += delta["text"]
                elif delta["type"] == "input_json_delta":
                    current_block.tool_input_json += delta["partial_json"]

            elif event_type == "content_block_stop":
                current_block = None

            elif event_type == "message_delta":
                result.stop_reason = data["delta"].get("stop_reason", "")
                result.output_tokens = data.get("usage", {}).get("output_tokens", 0)

        # Build assistant message content
        assistant_content = []
        for block in result.content_blocks:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.tool_id,
                    "name": block.tool_name,
                    "input": json.loads(block.tool_input_json) if block.tool_input_json else {},
                })

        messages.append({"role": "assistant", "content": assistant_content})

        # If no tool calls, we are done
        if result.stop_reason != "tool_use":
            break

        # Execute tools and build tool_result message
        tool_results = []
        for block in result.content_blocks:
            if block.type == "tool_use":
                tool_input = json.loads(block.tool_input_json) if block.tool_input_json else {}
                try:
                    output = await tool_executor(block.tool_name, tool_input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.tool_id,
                        "content": str(output),
                    })
                except Exception as e:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.tool_id,
                        "content": f"Error: {e}",
                        "is_error": True,
                    })

        messages.append({"role": "user", "content": tool_results})

    return messages
```

This is approximately 140 lines for a complete streaming tool-use loop. The complexity is manageable.

---

## 2. Framework Survey

**Confidence: HIGH**

### 2.1 LangGraph

**Architecture:** Graph-based state machine. Nodes are functions, edges are transitions (including conditional edges). State is a typed dict that flows through the graph and persists across nodes.

**Supervisor pattern:** A supervisor node routes to worker agent nodes based on state. Each worker has its own scratchpad. The supervisor evaluates results and decides next steps. Available as `langgraph-supervisor-py` package.

**State management:** Centralized, immutable-versioned state. Each node update creates a new state version. State is the shared memory across all nodes. Supports checkpointing for resume/replay.

**What to steal:**
- The graph-as-execution-plan concept. Defining workflows as nodes + edges is clean and debuggable.
- Conditional routing based on state evaluation -- maps well to our tier classification.
- Built-in checkpointing for long-running agent sessions.

**Achilles heel:**
- LangChain dependency. LangGraph is tightly coupled to the LangChain ecosystem. The abstraction tax is heavy.
- State explosion. Complex multi-agent workflows create deeply nested state dictionaries that are hard to debug.
- Overhead for simple cases. A basic tool-use loop becomes a multi-file graph definition.

### 2.2 CrewAI

**Architecture:** Three core abstractions: `Crew` (the team), `Agent` (a role with tools), `Task` (a unit of work). Two execution modes: `Process.sequential` and `Process.hierarchical`. Added `Flows` (event-driven pipelines) in 2025 rewrite.

**Hierarchical process:** Auto-generates a manager agent that delegates tasks to workers. In theory, mirrors our conductor-of-conductors model.

**Memory system:** Four-layer hierarchy: short-term (ChromaDB/RAG), long-term (persistent), entity (knowledge about entities), procedural (learned workflows). Scoped by path (`/project/alpha`).

**What to steal:**
- The four-layer memory architecture. Short-term + long-term + entity + procedural maps well to our session + daily + agent + skill memory structure.
- Scoped memory recall -- searching only the relevant branch of the tree.

**Achilles heel:**
- **The hierarchical process is broken.** Multiple reports confirm the manager-worker architecture "simply does not function as documented." The manager executes tasks sequentially instead of intelligently delegating. High latency, unnecessary tool calls, incorrect reasoning.
- Debugging is "spelunking without a headlamp."
- Python-only. No TypeScript option.

### 2.3 AutoGen (AG2)

**Architecture:** `ConversableAgent` is the base class. Agents exchange messages in conversation loops. `AssistantAgent` and `UserProxyAgent` are pre-configured subclasses. Code execution is first-class.

**GroupChat:** Multiple agents share a conversation. A selector (round-robin, LLM-based, or custom) determines who speaks next. Good for iterative refinement (write code -> review -> fix -> review).

**v0.4 rewrite (AG2):** Event-driven core, async-first, pluggable orchestration strategies. Layered architecture for flexibility.

**What to steal:**
- The conversational agent pattern. Agents as message-passing entities that can reply to each other naturally.
- Code executor abstraction -- sandboxed code execution as a first-class tool.
- The "auto-reply" capability for autonomous multi-agent loops.

**Achilles heel:**
- Conversation management is fragile. Long GroupChat sessions lose coherence as the shared conversation grows.
- The v0.2 -> v0.4 rewrite broke the ecosystem. Two incompatible versions coexist.
- Heavy Microsoft coupling. Some features assume Azure/OpenAI.

### 2.4 OpenAI Agents SDK

**Architecture:** Three core abstractions: `Agent` (definition with tools, instructions, model), `Runner` (executes the agent loop), `Handoff` (transfers control between agents).

**Runner flow:** Prompt -> Agent calls LLM -> LLM returns tool calls or text -> Runner executes tools -> feeds results back -> repeat until no tool calls or handoff.

**Handoff mechanism:** When an agent decides another agent should handle the conversation, it performs a handoff. The runner collapses prior transcript into a summary and hands control to the new agent. Nested handoffs are opt-in beta.

**Tracing:** Built-in trace collection of all events: LLM generations, tool calls, handoffs, guardrails. Visualizable in the Traces dashboard.

**What to steal:**
- The Handoff abstraction. Clean way to transfer context between specialized agents without losing history. Maps directly to our team-lead spawning.
- Built-in tracing. Every event is observable. Essential for debugging multi-agent systems.
- The Runner as separate from Agent. Separation of definition from execution.

**Achilles heel:**
- Nested handoffs are beta and unstable.
- Provider-agnostic is "documented" but practically it is OpenAI-first.
- No native process isolation. Agents share the same Python process.

### 2.5 Pydantic AI

**Architecture:** `Agent` class with generics for dependency injection (`deps_type`) and output type. `RunContext[T]` carries dependencies through tools and prompts. Type-safe from definition to execution.

**Dependency injection:** You declare `deps_type` on the agent, then `RunContext[UserDatabase]` flows into every tool, prompt function, and validator. Swap real deps for mocks in tests.

**Type-safe tools:** `@agent.tool` decorator auto-generates JSON Schema from type hints and docstrings. Pydantic validates inputs; errors are sent back to the LLM for retry. "If it compiles, it works" philosophy.

**What to steal:**
- **RunContext dependency injection.** This is the cleanest pattern for passing service connections (Hub client, AgentAuth client, NATS connection) into tools without global state.
- Auto-generated tool schemas from type hints. Write a Python function with type hints, get a JSON Schema tool definition for free.
- Structured output validation with retry.

**Achilles heel:**
- No multi-agent orchestration built in. It is a single-agent framework. Multi-agent is "bring your own."
- Streaming structured output is still maturing.
- Pydantic v2 dependency can conflict with other libraries.

### 2.6 smolagents

**Architecture:** Minimal by design. Core agent logic in ~1,000 lines (`src/smolagents/agents.py`). Two agent types: `CodeAgent` (writes Python code as actions) and `ToolCallingAgent` (JSON/text tool calls).

**Code agent philosophy:** Instead of outputting JSON tool calls, the LLM writes Python code that calls tool functions directly. This enables natural composability -- loops, conditionals, function nesting. HuggingFace found that code-based actions outperform JSON tool calls on benchmarks.

**Why HuggingFace built it:** Existing frameworks were too heavy. smolagents is <1,000 lines of core logic, model-agnostic (supports any LLM via LiteLLM integration), and focuses on the insight that "programming languages are the best way to describe what a computer should do."

**Sandboxing:** Code execution in Docker, E2B, Modal, Blaxel, or Pyodide+Deno WebAssembly.

**What to steal:**
- **The code-agent paradigm.** For complex tool orchestration, having the LLM write Python that calls tools is more expressive than JSON tool calls. Worth supporting as an alternate execution mode.
- Minimal abstraction philosophy. ~1,000 lines for a working agent. Proves that you do not need a framework -- you need a loop and tools.
- Hub-based sharing of agents and tools as Gradio Spaces.

**Achilles heel:**
- Security surface. Executing LLM-generated code is inherently risky even with sandboxing.
- 2.4% of traces had first-call parsing errors (their own measurement).
- No built-in multi-agent coordination.

### 2.7 Framework Comparison Matrix

| Dimension | LangGraph | CrewAI | AutoGen | OpenAI SDK | Pydantic AI | smolagents |
|-----------|-----------|--------|---------|------------|-------------|------------|
| Core abstraction | Graph nodes + state | Crew/Agent/Task | ConversableAgent | Agent/Runner/Handoff | Agent + RunContext | CodeAgent |
| Multi-agent | Supervisor graph | Hierarchical process | GroupChat | Handoffs | Manual | Manual |
| Model-agnostic | Via LangChain | Yes | Partial (Azure-leaning) | Documented, OpenAI-first | Yes | Yes (LiteLLM) |
| Memory | State checkpointing | 4-layer hierarchy | Conversation history | Session-based | RunContext deps | None built-in |
| Code size | Heavy (LangChain dep) | Medium | Heavy (two versions) | Light | Light | ~1,000 lines core |
| Production-ready | Yes (v1.1+) | Fragile | AG2 is maturing | Yes | Yes | Experimental |
| What to steal | Graph execution, checkpointing | Scoped memory hierarchy | Conversational agents | Handoffs, tracing | DI via RunContext, type-safe tools | Code-agent paradigm, minimalism |

---

## 3. Claude Code Architecture Analysis

**Confidence: HIGH**

### 3.1 Open Source Status

**Yes, Claude Code is open source.** The official repository is at `github.com/anthropics/claude-code` (84.5k stars, 569 commits, 51 contributors as of March 2026).

Language composition: Shell 47%, Python 29.3%, TypeScript 17.7%, PowerShell 4.1%, Dockerfile 1.9%.

### 3.2 The Claude Agent SDK

More importantly, Anthropic has released the **Claude Agent SDK** (`@anthropic-ai/agent-sdk` for TypeScript, `claude_agent_sdk` for Python, v0.2.71 as of March 2026). This SDK exposes the same agent loop, tools, context management, and subagent spawning that power Claude Code, as a library.

The SDK is built around four core concepts: **tools**, **hooks**, **MCP servers**, and **subagents**.

### 3.3 Agent Loop Architecture

The loop is straightforward (from official docs):

1. **Receive prompt.** Claude gets prompt + system prompt + tool definitions + conversation history.
2. **Evaluate and respond.** Claude responds with text, tool calls, or both. Yields `AssistantMessage`.
3. **Execute tools.** SDK runs each requested tool, collects results. Hooks can intercept/block.
4. **Repeat.** Steps 2-3 cycle. Each cycle = one "turn."
5. **Return result.** When Claude responds with no tool calls, yields final `ResultMessage` with cost/usage/session_id.

**Key design decisions:**
- **Turns, not steps.** A turn = one LLM call + tool execution round trip. `max_turns` caps the loop.
- **Message types:** `SystemMessage` (lifecycle), `AssistantMessage` (Claude's output), `UserMessage` (tool results), `StreamEvent` (raw SSE), `ResultMessage` (final).
- **Parallel tool execution:** Read-only tools (`Read`, `Glob`, `Grep`) run concurrently. Mutating tools (`Edit`, `Write`, `Bash`) run sequentially.

### 3.4 Built-in Tools

| Category | Tools |
|----------|-------|
| File operations | `Read`, `Edit`, `Write` |
| Search | `Glob`, `Grep` |
| Execution | `Bash` |
| Web | `WebSearch`, `WebFetch` |
| Discovery | `ToolSearch` (on-demand tool loading) |
| Orchestration | `Agent` (subagents), `Skill`, `AskUserQuestion`, `TodoWrite` |

### 3.5 Context Management

- Context does not reset between turns. Everything accumulates.
- System prompt + tool definitions are **prompt-cached** (reduced cost for repeated prefixes).
- **Automatic compaction:** When approaching the context limit, older history is summarized. A `SystemMessage` with subtype `"compact_boundary"` fires. CLAUDE.md content is re-injected on every request (survives compaction).
- **Subagents for context isolation:** Each subagent starts fresh (no parent history), and only its final response returns to the parent. Parent context grows by the summary, not the full transcript.

### 3.6 What to Steal

1. **The turn-based loop model.** Simple, debuggable, with clear lifecycle events.
2. **Automatic compaction with re-injection of persistent context.** CLAUDE.md survives compaction because it is loaded fresh each turn. Our equivalent: manifest + constitutional context loaded each turn, session history compacted.
3. **Subagent isolation pattern.** Sub-minds get fresh context, return only a summary. This is exactly our team-lead model.
4. **Hooks system.** `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStart/Stop`, `PreCompact`. Event-driven extension without modifying the core loop.
5. **Permission modes.** `default`, `acceptEdits`, `plan`, `bypassPermissions`. Maps to our autonomy levels (L1-L4).
6. **Effort levels.** `low`/`medium`/`high`/`max` reasoning depth. Could map to our tier system (T1 = low effort, T3 = max effort).

### 3.7 Why Not Just Use the Agent SDK?

The Claude Agent SDK is the strongest argument against Track B. It gives us the loop, tools, subagents, compaction, hooks, and streaming for free.

**Reasons Track B still makes sense:**

| Concern | Agent SDK | Track B (Sovereign) |
|---------|-----------|-------------------|
| Model lock-in | Anthropic only | Any model via agentmind |
| Process isolation | Same process, subagent abstraction | Separate tmux panes per sub-mind |
| Service integration | MCP servers (generic) | Native Hub/AgentAuth/AgentCal clients |
| IPC | In-process messages | NATS message bus (cross-process, cross-host) |
| Memory | Session + compaction | Constitutional memory hierarchy |
| Scheduling | None | Built-in cron/BOOP/calendar awareness |
| Cost control | `max_budget_usd` | AgentMind tiered routing + budget enforcement |
| Autonomy governance | Permission modes | Constitutional governance + autonomy levels |
| Customization depth | Hooks + custom tools | Own the entire loop |

The Agent SDK is a *harness*. We need an *operating system*.

---

## 4. Model-Agnostic Tool Use Design

**Confidence: HIGH**

### 4.1 Format Comparison

**Tool Definition:**

```
OpenAI:     {"type": "function", "function": {"name": X, "parameters": {schema}}}
Anthropic:  {"name": X, "description": Y, "input_schema": {schema}}
Gemini:     FunctionDeclaration(name=X, parameters=Schema(...))
```

**Tool Call in Response:**

```
OpenAI:     message.tool_calls[].function.name + .arguments (JSON string)
Anthropic:  content[].type=="tool_use", .id, .name, .input (parsed dict)
Gemini:     response.parts[].function_call.name + .args (dict)
```

**Tool Result Submission:**

```
OpenAI:     {"role": "tool", "tool_call_id": X, "content": "result"}
Anthropic:  {"role": "user", "content": [{"type": "tool_result", "tool_use_id": X, "content": "result"}]}
Gemini:     Part.from_function_response(name=X, response={dict})
```

### 4.2 Normalization Layer Design

The differences are mechanical, not semantic. A thin adapter layer:

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class NormalizedToolDef:
    """Provider-agnostic tool definition."""
    name: str
    description: str
    parameters: dict  # JSON Schema

    def to_anthropic(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_gemini(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,  # Gemini accepts JSON Schema too
        }


@dataclass
class NormalizedToolCall:
    """Provider-agnostic tool call from a model response."""
    id: str
    name: str
    arguments: dict  # parsed

    @classmethod
    def from_anthropic(cls, block: dict) -> "NormalizedToolCall":
        return cls(id=block["id"], name=block["name"], arguments=block["input"])

    @classmethod
    def from_openai(cls, tool_call: dict) -> "NormalizedToolCall":
        import json
        return cls(
            id=tool_call["id"],
            name=tool_call["function"]["name"],
            arguments=json.loads(tool_call["function"]["arguments"]),
        )


@dataclass
class NormalizedToolResult:
    """Provider-agnostic tool result."""
    tool_call_id: str
    content: str
    is_error: bool = False

    def to_anthropic(self) -> dict:
        r = {
            "type": "tool_result",
            "tool_use_id": self.tool_call_id,
            "content": self.content,
        }
        if self.is_error:
            r["is_error"] = True
        return r

    def to_openai(self) -> dict:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }
```

This is approximately 80 lines. It handles the three major providers. Adding a new provider means adding one `to_X()` and one `from_X()` method.

### 4.3 LiteLLM Assessment

**What it does well:**
- Unified `completion()` / `acompletion()` API across 100+ providers
- Automatic format translation for tool calls (OpenAI format in, provider-specific format out)
- Built-in cost tracking, rate limiting, fallback routing
- `litellm.supports_function_calling(model)` capability checking
- Active maintenance, day-0 support for new models (e.g., Gemini 3)

**What it does poorly:**
- Heavy dependency (~50+ transitive deps)
- Opaque translation layer -- when something goes wrong with tool calling, debugging through LiteLLM's internals is painful
- Streaming tool calls have edge cases across providers
- MCP integration adds complexity we do not need

**Verdict:** LiteLLM is viable as the backend for AgentMind's provider routing (replacing our hand-rolled `_translate_tools()`). But for aiciv-mind's core loop, using LiteLLM directly adds an unnecessary abstraction layer between us and the model. We already have AgentMind for routing. The aiciv-mind loop should talk to AgentMind (which handles provider translation), not to LiteLLM directly.

**Recommended architecture:**

```
aiciv-mind (core loop)
    |
    | Anthropic-format requests (our canonical format)
    |
    v
AgentMind (routing + translation + cost tracking)
    |
    |--- Anthropic API (native, no translation needed)
    |--- Groq/Together/Fireworks (OpenAI-compat translation)
    |--- Gemini (Gemini translation)
    |--- Local/Ollama (OpenAI-compat)
```

AgentMind already has `_translate_tools()` for OpenAI-to-Anthropic. We extend it with Anthropic-to-OpenAI for T1 backends. aiciv-mind always speaks Anthropic format. AgentMind handles the rest.

---

## 5. Mind Abstraction Design

**Confidence: MEDIUM** (design sketch, not validated implementation)

### 5.1 Core `Mind` Class

```python
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from enum import Enum

class MindState(Enum):
    IDLE = "idle"
    THINKING = "thinking"        # waiting for LLM response
    EXECUTING = "executing"      # running tools
    WAITING = "waiting"          # waiting for sub-mind result
    COMPACTING = "compacting"    # summarizing context
    SHUTDOWN = "shutdown"

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable[..., Awaitable[str]]
    read_only: bool = False

@dataclass
class MindConfig:
    mind_id: str
    model: str = "claude-sonnet-4-6"
    system_prompt: str = ""
    max_turns: int = 50
    max_context_tokens: int = 180_000
    compaction_threshold: float = 0.8  # compact at 80% of max
    agentmind_url: str = "http://localhost:8800"
    nats_url: str = "nats://localhost:4222"
    hub_url: str = "http://87.99.131.49:8900"
    agentauth_url: str = "http://5.161.90.32:8700"

class Mind:
    """
    The core aiciv-mind abstraction. An autonomous agent with:
    - Event-driven tool-use loop
    - Native AiCIV service integration (Hub, AgentAuth, AgentCal)
    - Sub-mind spawning via tmux panes
    - IPC message bus via NATS
    - Memory management with compaction
    """

    def __init__(self, config: MindConfig):
        self.config = config
        self.state = MindState.IDLE
        self.messages: list[dict] = []  # conversation history
        self.tools: dict[str, Tool] = {}
        self.sub_minds: dict[str, "SubMindHandle"] = {}
        self.hooks: dict[str, list[Callable]] = {}
        self.token_count: int = 0
        self.turn_count: int = 0
        self.session_id: str = str(uuid.uuid4())

        # Service clients (initialized in start())
        self._hub_client = None
        self._auth_client = None
        self._nats_client = None
        self._agentmind_client = None

    # --- Tool Registration ---

    def register_tool(self, tool: Tool):
        self.tools[tool.name] = tool

    def register_tools(self, tools: list[Tool]):
        for t in tools:
            self.register_tool(t)

    # --- Hook System ---

    def on(self, event: str, callback: Callable):
        """Register a hook: pre_tool, post_tool, pre_compact, stop, etc."""
        self.hooks.setdefault(event, []).append(callback)

    async def _emit(self, event: str, **kwargs) -> bool:
        """Emit hook event. Returns False if any hook rejects."""
        for cb in self.hooks.get(event, []):
            result = await cb(**kwargs)
            if result is False:
                return False
        return True

    # --- Core Loop ---

    async def run(self, prompt: str) -> str:
        """
        Main entry point. Runs the agentic loop until completion.
        Returns the final text response.
        """
        self.state = MindState.IDLE
        self.messages.append({"role": "user", "content": prompt})

        for turn in range(self.config.max_turns):
            self.turn_count += 1

            # Check if compaction needed
            if self.token_count > self.config.max_context_tokens * self.config.compaction_threshold:
                await self._compact()

            # Call LLM via AgentMind
            self.state = MindState.THINKING
            response = await self._call_llm()

            # Append assistant response to history
            self.messages.append({"role": "assistant", "content": response["content"]})
            self.token_count += response.get("usage", {}).get("output_tokens", 0)

            # Check for tool calls
            tool_calls = [b for b in response["content"] if b["type"] == "tool_use"]

            if not tool_calls:
                # No tool calls -- final response
                self.state = MindState.IDLE
                text = "".join(
                    b["text"] for b in response["content"] if b["type"] == "text"
                )
                await self._emit("stop", result=text)
                return text

            # Execute tools
            self.state = MindState.EXECUTING
            tool_results = await self._execute_tools(tool_calls)
            self.messages.append({"role": "user", "content": tool_results})

        return "[max turns reached]"

    async def _call_llm(self) -> dict:
        """Call AgentMind (or direct Anthropic API) with current messages + tools."""
        tool_defs = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in self.tools.values()
        ]

        # POST to AgentMind /api/v1/completions (streaming)
        # or direct to Anthropic /v1/messages (streaming)
        # Returns parsed response with content blocks
        ...  # implementation: use stream_messages() from Section 1.7

    async def _execute_tools(self, tool_calls: list[dict]) -> list[dict]:
        """Execute tool calls, respecting read-only parallelism."""
        results = []

        # Separate read-only (parallel) from mutating (sequential)
        read_only = [tc for tc in tool_calls if self.tools.get(tc["name"], Tool("","",{},None)).read_only]
        mutating = [tc for tc in tool_calls if tc not in read_only]

        # Execute read-only tools in parallel
        if read_only:
            tasks = [self._execute_one_tool(tc) for tc in read_only]
            parallel_results = await asyncio.gather(*tasks, return_exceptions=True)
            results.extend(parallel_results)

        # Execute mutating tools sequentially
        for tc in mutating:
            result = await self._execute_one_tool(tc)
            results.append(result)

        return results

    async def _execute_one_tool(self, tool_call: dict) -> dict:
        """Execute a single tool call with hook support."""
        name = tool_call["name"]
        input_data = tool_call["input"]
        tool_id = tool_call["id"]

        # Pre-tool hook
        allowed = await self._emit("pre_tool", name=name, input=input_data)
        if not allowed:
            return {"type": "tool_result", "tool_use_id": tool_id, "content": "Tool call blocked by policy", "is_error": True}

        tool = self.tools.get(name)
        if not tool:
            return {"type": "tool_result", "tool_use_id": tool_id, "content": f"Unknown tool: {name}", "is_error": True}

        try:
            output = await tool.handler(**input_data)
            await self._emit("post_tool", name=name, input=input_data, output=output)
            return {"type": "tool_result", "tool_use_id": tool_id, "content": str(output)}
        except Exception as e:
            return {"type": "tool_result", "tool_use_id": tool_id, "content": f"Error: {e}", "is_error": True}

    # --- Context Compaction ---

    async def _compact(self):
        """Summarize older messages to free context space."""
        self.state = MindState.COMPACTING
        await self._emit("pre_compact")

        # Keep the last N turns, summarize the rest
        # Use a cheap T1 model via AgentMind for summarization
        ...

    # --- Sub-Mind Management ---

    async def spawn_sub_mind(
        self,
        mind_id: str,
        system_prompt: str,
        task: str,
        tools: list[Tool] | None = None,
    ) -> "SubMindHandle":
        """
        Spawn a sub-mind in a new tmux pane.
        Returns a handle for IPC communication.
        """
        handle = SubMindHandle(
            mind_id=mind_id,
            parent_id=self.config.mind_id,
            nats_subject=f"mind.{self.config.mind_id}.sub.{mind_id}",
        )
        self.sub_minds[mind_id] = handle

        # Launch as a separate Python process in a tmux pane
        # The sub-mind process loads Mind with its own config, connects to NATS
        ...

        return handle

    # --- Service Integration ---

    async def hub_post(self, group_id: str, room: str, content: str):
        """Post to AiCIV Hub."""
        ...

    async def hub_search(self, query: str) -> list[dict]:
        """Search Hub threads."""
        ...

    async def auth_sign(self, payload: dict) -> str:
        """Sign a payload with AgentAuth identity key."""
        ...


@dataclass
class SubMindHandle:
    """Handle for communicating with a spawned sub-mind."""
    mind_id: str
    parent_id: str
    nats_subject: str
    tmux_pane: str = ""
    pid: int = 0

    async def send_task(self, task: str):
        """Send a task to the sub-mind via NATS."""
        ...

    async def receive_result(self, timeout: float = 300.0) -> str:
        """Wait for the sub-mind's result via NATS."""
        ...

    async def heartbeat(self) -> bool:
        """Check if the sub-mind is still alive."""
        ...

    async def shutdown(self):
        """Request graceful shutdown of the sub-mind."""
        ...
```

### 5.2 Sub-Mind Interface (Minimal)

A sub-mind needs exactly three IPC methods:

```python
class SubMindProtocol:
    """The minimal interface a sub-mind exposes to the primary mind."""

    async def receive_task(self, task: str, context: dict) -> None:
        """
        Receive a task from the parent mind.
        context includes: manifest content, objective, any parent-provided data.
        Starts the sub-mind's own agentic loop.
        """

    async def send_result(self, result: str, metadata: dict) -> None:
        """
        Send the final result back to the parent mind.
        metadata includes: token usage, cost, turn count, key decisions.
        """

    async def heartbeat(self) -> dict:
        """
        Respond to a liveness check.
        Returns: {"state": MindState, "turn": N, "tokens_used": N}
        """
```

All communication happens over NATS subjects:
- `mind.{parent_id}.sub.{sub_id}.task` -- parent -> sub-mind
- `mind.{parent_id}.sub.{sub_id}.result` -- sub-mind -> parent
- `mind.{parent_id}.sub.{sub_id}.heartbeat` -- bidirectional

### 5.3 Core Loop Pseudocode

```
MIND.run(prompt):
    messages.append(user: prompt)

    LOOP (max_turns):
        if token_count > 80% of max_context:
            compact(messages)  # summarize older turns, keep recent

        response = call_llm(
            messages=messages,
            tools=registered_tools,
            system=system_prompt + constitutional_context,
            stream=True,  # always stream for responsiveness
        )

        messages.append(assistant: response.content)

        tool_calls = [block for block in response.content if block.type == "tool_use"]

        if no tool_calls:
            emit("stop", result=response.text)
            return response.text

        # Execute tools (read-only in parallel, mutating sequential)
        read_only_calls = [tc for tc in tool_calls if tools[tc.name].read_only]
        mutating_calls  = [tc for tc in tool_calls if not tools[tc.name].read_only]

        results = []
        results += await gather([execute(tc) for tc in read_only_calls])
        for tc in mutating_calls:
            results += [await execute(tc)]

        messages.append(user: results)

    return "[max turns]"


EXECUTE(tool_call):
    if not emit("pre_tool", tool_call):
        return error("blocked by policy")

    output = await tools[tool_call.name].handler(**tool_call.input)
    emit("post_tool", tool_call, output)
    return tool_result(id=tool_call.id, content=output)


SPAWN_SUB_MIND(mind_id, manifest, task):
    pane = tmux.split_window(cmd=f"python -m aiciv_mind --id={mind_id}")
    nats.publish(f"mind.primary.sub.{mind_id}.task", {
        manifest: manifest,
        task: task,
        tools: [...],
    })
    return SubMindHandle(mind_id, pane)
```

### 5.4 File Structure (Proposed)

```
projects/aiciv-mind/
    aiciv_mind/
        __init__.py
        mind.py              # Mind class, core loop (~300 lines)
        stream.py            # SSE streaming parser (~150 lines)
        tools.py             # Tool registry, built-in tools (~200 lines)
        normalize.py         # Tool format normalization (~100 lines)
        memory.py            # Memory manager, compaction (~200 lines)
        ipc.py               # NATS message bus, sub-mind comms (~150 lines)
        services/
            __init__.py
            hub.py           # Hub API client
            auth.py          # AgentAuth client
            cal.py           # AgentCal client
        hooks.py             # Hook system (~50 lines)
        config.py            # MindConfig, environment loading
        __main__.py          # CLI entry point
    tests/
    config.yaml
    pyproject.toml
    Dockerfile
```

Core loop estimate: ~800 lines. Full package with services: ~2,000 lines.

---

## 6. Track B Assessment

| Dimension | Assessment | Notes |
|-----------|-----------|-------|
| **Build effort** | 6-8 weeks for MVP | Week 1: core loop + streaming. Week 2: tool registry + built-in tools. Week 3-4: sub-mind spawning + NATS IPC. Week 5-6: service integration (Hub, Auth, Cal). Week 7-8: memory, compaction, polish. |
| **Model-agnostic capability** | STRONG | Anthropic-format canonical, AgentMind handles translation to all providers. T1/T2/T3 tiering already designed. |
| **Streaming control** | FULL | We own the SSE parser. Can add progress callbacks, token counting, cost tracking at the stream level. |
| **Protocol ownership** | COMPLETE | No SDK dependency. No Anthropic-specific abstractions. Can swap the entire inference backend. |
| **Sub-mind spawning** | NATIVE | tmux panes + NATS IPC. Each sub-mind is a separate process with its own context window. True process isolation. |
| **Maintenance burden** | MODERATE | ~2,000 lines of core code. No upstream framework to track. But: we own every bug, every edge case, every provider quirk. |
| **Risk: streaming edge cases** | MEDIUM | Partial JSON accumulation, connection drops mid-stream, thinking block signatures. All solvable but require testing. |
| **Risk: tool format drift** | LOW | Provider formats have been stable for 18+ months. AgentMind's translation layer absorbs changes. |
| **Advantage over Agent SDK** | Process isolation, model-agnostic, native services, NATS IPC, constitutional memory, full autonomy control | The Agent SDK is a harness. We need an OS. |

### Build Priority Recommendation

**Phase 1 (Week 1-2): Proof of Life**
- `stream.py` -- SSE parser with tool_use accumulation
- `mind.py` -- Core loop (call LLM, execute tools, repeat)
- `tools.py` -- 5 built-in tools (bash, read, write, edit, glob)
- `__main__.py` -- CLI entry point, single-mind mode
- **Deliverable:** A working agent that can read files, run commands, and edit code via Anthropic API direct.

**Phase 2 (Week 3-4): Multi-Mind**
- `ipc.py` -- NATS message bus
- Sub-mind spawning via tmux
- `SubMindHandle` with task/result/heartbeat protocol
- **Deliverable:** Primary mind can spawn sub-minds that work in parallel.

**Phase 3 (Week 5-6): AiCIV Native**
- `services/hub.py` -- Hub API client (post, search, threads)
- `services/auth.py` -- AgentAuth JWT signing
- `services/cal.py` -- AgentCal integration
- `normalize.py` -- Tool format translation for AgentMind backends
- **Deliverable:** A mind that authenticates, posts to Hub, and reads calendars natively.

**Phase 4 (Week 7-8): Memory & Polish**
- `memory.py` -- Session persistence, compaction, constitutional context injection
- Hooks system refinement
- Integration with nightly training pipeline
- Docker containerization
- **Deliverable:** Production-ready mind with persistent memory.

---

## 7. Sources

### Anthropic Official Documentation
- [Streaming Messages API](https://platform.claude.com/docs/en/api/messages-streaming)
- [Tool Use](https://platform.claude.com/docs/en/docs/build-with-claude/tool-use)
- [Define Tools](https://platform.claude.com/docs/en/docs/build-with-claude/tool-use/define-tools)
- [Claude Agent SDK - Agent Loop](https://platform.claude.com/docs/en/agent-sdk/agent-loop)
- [Claude Agent SDK - Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK - TypeScript](https://platform.claude.com/docs/en/agent-sdk/typescript)

### Claude Code
- [Claude Code GitHub Repository](https://github.com/anthropics/claude-code)
- [Claude Code Overview](https://code.claude.com/docs/en/overview)
- [learn-claude-code (minimal clone)](https://github.com/shareAI-lab/learn-claude-code)

### Framework Documentation
- [LangGraph Multi-Agent Orchestration Guide](https://latenode.com/blog/ai-frameworks-technical-infrastructure/langgraph-multi-agent-orchestration/langgraph-ai-framework-2025-complete-architecture-guide-multi-agent-orchestration-analysis)
- [LangGraph Supervisor Pattern](https://github.com/langchain-ai/langgraph-supervisor-py)
- [CrewAI Framework Review 2025](https://latenode.com/blog/ai-frameworks-technical-infrastructure/crewai-framework/crewai-framework-2025-complete-review-of-the-open-source-multi-agent-ai-platform)
- [Why CrewAI Manager-Worker Fails (Towards Data Science)](https://towardsdatascience.com/why-crewais-manager-worker-architecture-fails-and-how-to-fix-it/)
- [CrewAI Memory Deep Dive](https://sparkco.ai/blog/deep-dive-into-crewai-memory-systems)
- [AutoGen Multi-Agent Framework](https://microsoft.github.io/autogen/0.2/docs/Use-Cases/agent_chat/)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [OpenAI Agents SDK - Handoffs](https://openai.github.io/openai-agents-python/handoffs/)
- [OpenAI Agents SDK - Tracing](https://openai.github.io/openai-agents-python/tracing/)
- [OpenAI Agents SDK Review (mem0)](https://mem0.ai/blog/openai-agents-sdk-review)
- [Pydantic AI](https://ai.pydantic.dev/)
- [Pydantic AI - Agents](https://ai.pydantic.dev/agent/)
- [smolagents (HuggingFace)](https://huggingface.co/docs/smolagents/en/index)
- [smolagents GitHub](https://github.com/huggingface/smolagents)
- [Introducing smolagents (HuggingFace blog)](https://huggingface.co/blog/smolagents)

### Tool Calling Comparison
- [Function Calling Complete Guide 2026](https://ofox.ai/blog/function-calling-tool-use-complete-guide-2026/)
- [LiteLLM Tool Calling (DeepWiki)](https://deepwiki.com/BerriAI/litellm/8.1-tool-calling-and-function-integration)
- [LiteLLM Function Calling Docs](https://docs.litellm.ai/docs/completion/function_call)
- [LiteLLM GitHub](https://github.com/BerriAI/litellm)

### Framework Comparisons
- [AI Agent Showdown 2026 (Medium)](https://topuzas.medium.com/the-great-ai-agent-showdown-of-2026-openai-autogen-crewai-or-langgraph-7b27a176b2a1)
- [Open Source Agent Frameworks Compared 2026](https://openagents.org/blog/posts/2026-02-23-open-source-ai-agent-frameworks-compared)
- [Best Multi-Agent Frameworks 2026](https://gurusup.com/blog/best-multi-agent-frameworks-2026)

---

*End of Track B Research Report*
*"The fleet doesn't need a framework. It needs a mind."*
