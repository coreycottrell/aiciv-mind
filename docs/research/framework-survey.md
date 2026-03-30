# Agent Framework Survey — Research Report

**Date**: 2026-03-30
**Researcher**: framework-agent (Opus 4.6)
**Purpose**: Inform the architecture of **aiciv-mind** — a purpose-built AI harness/OS
**Method**: 20+ web searches, framework docs, GitHub repos, blog posts, reverse-engineering analyses

---

## Executive Summary

The agent framework landscape in early 2026 has consolidated around a few clear winners, with LangGraph dominating production deployments, CrewAI leading rapid prototyping, Pydantic AI emerging as the type-safety champion, and AutoGen entering maintenance mode as Microsoft pivots to its unified Agent Framework. Meanwhile, Claude Code — while not a "framework" in the traditional sense — represents the most battle-tested agent harness in production, with architectural decisions that are deeply relevant to aiciv-mind.

**The standout pattern across all frameworks**: Context engineering (managing what's in the LLM's window at any given moment) is the single most important architectural challenge. Every framework that succeeds in production has invested heavily in this; every one that struggles has treated context as infinite.

**The common trap**: Over-abstracting agent coordination. Every framework adds layers of orchestration that become their own source of bugs, latency, and debugging pain. The most successful agents use simple loops with good tools, not complex graph engines.

---

## 1. LangGraph

**Confidence**: HIGH (most extensively documented framework)

### Core Abstraction

LangGraph models agent workflows as **directed graphs** with three primitives:

- **State**: A shared, typed data structure (typically a TypedDict or Pydantic model) that acts as the single source of truth. State flows between nodes like a baton. Each node reads state, computes, and returns an updated state. State updates use **reducer functions** — e.g., `operator.add` to append to lists rather than overwrite.
- **Nodes**: Python functions that receive current state and return updated state. Nodes are where logic lives — an LLM call, a tool invocation, a branching decision.
- **Edges**: Define transitions between nodes. **Standard edges** are fixed A→B transitions. **Conditional edges** evaluate state and route dynamically (the LLM decides the path). This is where the "intelligence" of routing lives.

The execution model is **message-passing**: when a node completes, it sends messages along edges to successor nodes. Multiple successors = parallel execution.

### Supervisor Pattern

LangGraph has a first-party supervisor pattern (`langgraph-supervisor-py`), though LangChain now recommends implementing supervisors via tool-calling rather than the dedicated library. The pattern:

1. A **supervisor node** (LLM-powered) receives the task
2. Supervisor decides which **worker subgraph** to invoke via tool calls
3. Workers execute and return results to supervisor
4. Supervisor synthesizes or routes to next worker

For deeper hierarchies, **subgraphs** compose into larger graphs. A top-level supervisor delegates to mid-level supervisors, each managing their own worker subgraphs. Subgraphs can have separate state schemas — input/output transformations handle cross-boundary communication.

**Known issue**: The supervisor can exhibit pathological behavior — repeatedly sending an agent's output back to itself, burning tokens and time. This is an LLM reliability problem, not a framework bug.

### State Persistence (Checkpointing)

LangGraph's persistence is its strongest architectural feature:

- **InMemorySaver**: Development/testing
- **SqliteSaver / AsyncSqliteSaver**: Local workflows, prototyping
- **PostgresSaver / AsyncPostgresSaver**: Production (used by LangSmith)
- **Custom backends**: Pluggable via `BaseCheckpointSaver` interface

Checkpoints capture the **complete graph state** at every node boundary. This enables:
- Resume from any checkpoint (crash recovery)
- Time-travel debugging (inspect state at any point)
- Human-in-the-loop (pause, review, modify state, resume)
- Branching (fork from a checkpoint into alternative paths)

Serialization uses `JsonPlusSerializer` which handles LangChain primitives, datetimes, enums, and custom types.

### Streaming

LangGraph supports 5 streaming modes:
1. **Values**: Full state after each node
2. **Updates**: Delta state changes per node
3. **Messages**: Token-by-token from LLM calls
4. **Events**: Custom events from tools/code
5. **Debug**: Full internal execution trace

This is the most granular streaming system of any framework surveyed.

### Multi-Process Support

LangGraph does **not** natively support multiple agents in separate OS processes. It's single-process, event-loop-based. For multi-process, you'd need to wrap graphs in services (e.g., FastAPI endpoints) and orchestrate externally. LangGraph Platform (their hosted offering) does handle this, but it's a paid service.

### What to Steal

**Checkpoint-based state persistence with time-travel.** The idea that every state transition is checkpointed, and you can resume, fork, or rollback from any checkpoint, is the single most powerful idea for aiciv-mind. For long-running autonomous minds that restart across sessions, this is essential.

### What to Avoid

**The graph abstraction itself.** The learning curve is steep, the debugging is painful when conditional edges misbehave, and for autonomous agents (vs. user-facing workflows), the graph metaphor adds complexity without proportional value. Users consistently report that LangGraph feels "heavier than the problem requires" for anything that isn't a complex branching workflow. Version compatibility issues with LangChain ecosystem are a persistent pain point — updates break things, migration docs are inadequate.

---

## 2. CrewAI

**Confidence**: HIGH

### Core Abstraction

CrewAI uses a **role-playing team metaphor**:

- **Agent**: An LLM configured with a `role`, `goal`, and `backstory`. The role shapes the agent's behavior and decision-making. Agents can have tools, delegation authority, and memory.
- **Task**: A unit of work assigned to an agent. Has a `description`, `expected_output`, assigned agent, and optionally required tools. Task output from one task becomes context for the next.
- **Crew**: A collection of agents working on a collection of tasks under a defined process.
- **Process**: The execution strategy — sequential, hierarchical, or consensual.

### Hierarchical Process

In **hierarchical mode**, CrewAI auto-generates a **manager agent** that:
1. Reads the overall goal
2. Breaks it into subtasks
3. Dispatches subtasks to worker agents based on capabilities
4. Reviews outputs and validates completion
5. Synthesizes final result

The manager uses a dedicated LLM (configurable, can be different from workers). Senior agents can override junior agents' decisions and redistribute resources.

**Critical failure mode** (documented by multiple users): The hierarchical process **does not function as documented** in many real workflows. The manager doesn't effectively coordinate; instead, CrewAI falls back to sequential execution with incorrect reasoning, unnecessary tool calls, and extreme latency. A generic manager prompt produces erroneous results — significant prompt engineering is required to make it work.

### Memory System

CrewAI has the most sophisticated memory system of any framework surveyed (as of v1.x, 2025-2026):

- **Short-Term Memory**: ChromaDB-backed RAG for current session context. Stores task interactions and intermediate results.
- **Long-Term Memory**: SQLite3-based storage of task results and knowledge that persists across sessions.
- **Entity Memory**: RAG-based capture of details about people, places, concepts — entities encountered during execution.
- **Contextual Memory**: Combines all three above to provide agents with relevant background.

In the latest unified API, a single `Memory` class replaces the separate types. On **save**, an LLM analyzes content to infer scope, categories, and importance. On **recall**, the LLM analyzes queries to guide retrieval with composite scoring (semantic similarity + recency + importance).

### Parallel Execution

Tasks can run in parallel via `async_execution=True`. CrewAI uses `asyncio.gather()` under the hood. Multiple crews can also run concurrently. Dynamic branching via `@listen` decorators triggers tasks based on completion of others.

Production recommendation: 16-32GB RAM for 5-10 concurrent agents.

### Tool Sharing

Tools are Python functions decorated with `@tool`. Multiple agents can share the same tool definitions. Tools are defined at the agent level — assign any tool to any agent.

### What to Steal

**The unified memory system with LLM-analyzed importance scoring.** The idea that memory entries have automatically inferred scope, categories, and importance — and that recall uses composite scoring blending semantic similarity, recency, and importance — is exactly what aiciv-mind needs for long-running knowledge compounding. The weight configurability (tuning the blend of recency vs. relevance vs. importance) is elegant.

### What to Avoid

**The hierarchical manager pattern.** Multiple independent analyses confirm it doesn't work reliably. The manager agent lacks sufficient context to make good delegation decisions, and the framework's internal plumbing doesn't support the dynamic routing the docs promise. Also avoid the debugging experience — debugging CrewAI crews is widely described as painful, with no ability to write meaningful unit tests for agent interactions.

---

## 3. AutoGen (Microsoft)

**Confidence**: MEDIUM (framework is in maintenance mode; information may be stale)

### Core Abstraction (v0.2)

AutoGen's v0.2 architecture centered on **conversational agents**:

- **ConversableAgent**: Base class for all agents. Can send/receive messages, maintain conversation history, and invoke functions.
- **AssistantAgent**: Extends ConversableAgent with LLM integration. No human input required, no code execution by default.
- **UserProxyAgent**: Acts as a human gateway. Can execute code, request human input, and auto-reply.

### Multi-Agent Conversation

AutoGen's core insight: **multi-agent dialogue as the coordination primitive.** Agents communicate by exchanging messages in a conversation. Turn-taking can be:
- **Two-agent chat**: Simple back-and-forth
- **Sequential chat**: Chain of two-agent conversations
- **Group chat**: Multiple agents with a manager selecting who speaks next

### GroupChat

GroupChat provides:
- A list of participating agents
- A **GroupChatManager** that coordinates turn-taking
- Speaker selection strategies: round-robin, random, LLM-decided, or custom function
- Maximum rounds to prevent infinite loops
- Message broadcasting (all agents see all messages)

### Code Execution

AutoGen has the best sandboxed code execution:

- **CommandLineCodeExecutor**: Saves code blocks to files, executes them as separate processes
- **DockerCommandLineCodeExecutor**: Runs code inside Docker containers (default image: `python:3-slim`)
- **JupyterCodeExecutor**: Executes in Jupyter kernels (persistent state across cells)
- Docker containers can be customized, kept running, or auto-removed
- Supports Python and shell scripts

### New AutoGen (v0.4+, January 2025)

Complete rewrite with a layered architecture:

- **Core Layer**: Event-driven actor framework. Agents communicate via **asynchronous messages** (not conversations). Supports both event-driven and request/response patterns.
- **AgentChat Layer**: Built on Core. Provides the familiar high-level API (AssistantAgent, SelectorGroupChat, RoundRobinGroupChat). Migration path from v0.2.
- **Extensions Layer**: Pluggable components, third-party integrations.

Key additions: streaming messages, improved observability, save/restore task progress, resume paused actions.

### What to Steal

**The actor-model core with async message passing.** AutoGen v0.4's insight — that agents should be actors communicating via typed async messages, not participants in a "conversation" — is the right abstraction for aiciv-mind. Also worth stealing: **declarative agent specification** — AutoGen is the only framework supporting full JSON serialization of agents, teams, and termination conditions, which matters for spawning minds dynamically.

### What to Avoid

**The entire framework.** AutoGen is in maintenance mode as of late 2025. Microsoft has stopped feature development and is consolidating into the Microsoft Agent Framework (combining AutoGen + Semantic Kernel). Building on a deprecated foundation is a mistake. Also avoid GroupChat's centralized orchestration — having a single GroupChatManager as bottleneck creates scaling problems and doesn't match aiciv-mind's supervisor→worker hierarchy.

---

## 4. OpenAI Agents SDK

**Confidence**: HIGH

### Core Abstraction

The Agents SDK (launched March 2025, production-ready evolution of Swarm) has an intentionally minimal surface area:

- **Agent**: An LLM configured with `instructions`, `tools`, and optional `handoffs`, `guardrails`, and `output_type`. Agents are lightweight — just configuration, not complex objects.
- **Runner**: Executes the agent loop. Calls the LLM, executes tool calls, handles handoffs, repeats until completion. The Runner manages the entire lifecycle.
- **Handoff**: A mechanism for one agent to delegate to another. Handoffs are represented as **tools** to the LLM — e.g., a handoff to "Refund Agent" becomes a tool called `transfer_to_refund_agent`.
- **Tool**: A function the agent can call. Standard Python functions with type hints.

### Handoff Mechanism

Handoffs are the SDK's coordination primitive:

1. Agent A decides (via LLM reasoning) to hand off to Agent B
2. The handoff appears as a tool call in Agent A's output
3. The Runner catches it, switches the active agent to Agent B
4. Agent B receives the conversation history and continues
5. Process repeats until an agent produces final output (no handoff)

**Nested handoffs** (opt-in beta): When enabled, the Runner collapses prior transcript into a single summary message wrapped in a `CONVERSATION HISTORY` block, preventing context window bloat from accumulated handoff chains.

### Tracing

Built-in tracing captures:
- LLM generations (full request/response)
- Tool calls and results
- Handoffs
- Guardrail evaluations
- Custom events

Traces are viewable in the OpenAI dashboard for debugging, visualization, and monitoring. This is tightly integrated with OpenAI's platform.

### Guardrails

Three types:
- **Input guardrails**: Run on the first agent's input only
- **Output guardrails**: Run on the final agent's output only
- **Tool guardrails**: Run before/after every tool invocation

Guardrails are validation functions that can block, modify, or log. They run in parallel with the agent (for input guardrails), providing fast feedback.

**Limitation**: Input guardrails only run for the first agent in a chain — a significant gap for multi-agent systems where each agent might receive adversarial input.

### What to Steal

**Handoffs-as-tools.** Representing agent delegation as tool calls that the LLM can reason about is elegant and simple. The LLM doesn't need a special "delegation protocol" — it just calls a function. This is the cleanest multi-agent coordination primitive surveyed. Also steal: **the Runner loop pattern** — a simple while loop that executes tools and handoffs until done, with no graph engine or state machine overhead.

### What to Avoid

**Platform coupling.** While the SDK technically supports non-OpenAI models, it's optimized for and tested against OpenAI's APIs. The tracing system feeds into OpenAI's dashboard. You're building on their infrastructure's assumptions. Also avoid the guardrail limitation — input guardrails only running on the first agent is a real gap for supervisor→worker architectures where each worker needs input validation.

---

## 5. Pydantic AI

**Confidence**: HIGH

### Core Abstraction

Pydantic AI treats agents as **typed Python functions with LLM backends**:

- **Agent[DepsT, OutputT]**: Generic over dependencies and output type. An agent is defined once with its tools, system prompts, and output schema, then run multiple times with different inputs and dependencies.
- **deps_type**: The type of runtime dependencies the agent needs (database connections, API clients, config objects). Declared at agent creation, injected at `agent.run(deps=...)`.
- **RunContext[DepsT]**: Passed as the first parameter to tool functions and system prompt functions. Provides access to `ctx.deps` (injected dependencies), `ctx.model` (current model), `ctx.usage` (token counts), etc.
- **result_type**: The expected output type. Can be a Pydantic model, a primitive, or `str`. The framework validates the LLM's output against this schema.

### Type-Safe Tools

Tools are defined as decorated Python functions with full type annotations:

```python
@agent.tool
async def get_weather(ctx: RunContext[MyDeps], city: str) -> str:
    """Get weather for a city."""
    return await ctx.deps.weather_client.get(city)
```

The framework automatically:
- Generates JSON schema from type hints for the LLM
- Validates LLM-provided arguments against the schema
- Provides autocomplete and type checking in IDEs
- Returns typed results

Compared to writing raw tool schemas (JSON blobs), this is dramatically better DX. The tool's docstring becomes the tool description. Parameter types become the schema. No manual schema maintenance.

### Streaming

Pydantic AI supports streaming structured output using Pydantic's experimental **partial validation**. As tokens stream in, the framework attempts to validate the incomplete output against the target schema, providing real-time access to partially formed structured data. This is unique — most frameworks only stream text, not validated structured objects.

### Dependency Injection

The deps pattern is Pydantic AI's most distinctive feature:

1. Define your dependency type (e.g., `@dataclass class MyDeps: db: Database; api: ApiClient`)
2. Create agent with `Agent[MyDeps, OutputType]`
3. Tools receive deps via `RunContext[MyDeps]`
4. At runtime: `agent.run("prompt", deps=MyDeps(db=real_db, api=real_api))`
5. For testing: `agent.run("prompt", deps=MyDeps(db=mock_db, api=mock_api))`

This separates agent definition from runtime context — the same agent definition works in production and testing with different deps.

### Testing

Pydantic AI has the best testing story of any framework:

- **TestModel**: A mock model that calls all tools and returns deterministic results based on schemas. No LLM calls, no cost, no latency, no nondeterminism.
- **FunctionModel**: Custom model that executes a Python function instead of calling an LLM. Full control over responses.
- **Agent.override()**: Replace model, deps, or tools at any point without modifying call sites.
- **ALLOW_MODEL_REQUESTS=False**: Global safety net that blocks real LLM calls in test environments.
- **capture_run_messages()**: Inspect the full message exchange for assertion.
- **Pydantic Evals**: Dataset-based evaluation framework for systematic agent testing.

### What to Steal

**Three things**: (1) The **dependency injection pattern** — separating agent definition from runtime context is exactly right for aiciv-mind, where minds need different tools/connections depending on their role. (2) **Type-safe tool definitions** from decorated Python functions — zero schema maintenance, full IDE support. (3) **TestModel for deterministic testing** — the ability to test agent logic without LLM calls is critical for a system that needs to be reliable.

### What to Avoid

**The lack of built-in multi-agent orchestration.** Pydantic AI supports multi-agent via agent-calls-agent, but there's no supervisor pattern, no team abstraction, no built-in message passing between agents. You'd build all of that yourself. For aiciv-mind's primary→sub-mind architecture, this is a gap. Also: Pydantic AI is fundamentally **single-process, single-agent-at-a-time** in its design — parallel sub-minds would need external orchestration.

---

## 6. smolagents (HuggingFace)

**Confidence**: MEDIUM

### Core Abstraction

smolagents takes a radically different approach: **code-as-action**.

- **MultiStepAgent**: The base class. Runs a think-act-observe loop.
- **CodeAgent**: The default agent type. Instead of emitting tool calls as JSON, the agent **writes Python code** that calls tools as functions.
- **ToolCallingAgent**: A more traditional agent that uses JSON tool calls (available but not the default).

The entire framework fits in ~1,000 lines of code. This is intentional minimalism.

### Code-as-Action Paradigm

The core insight: LLMs are better at writing code than at filling out JSON schemas.

Instead of:
```json
{"tool": "search", "args": {"query": "weather NYC"}}
{"tool": "format", "args": {"data": "$PREV_RESULT", "style": "table"}}
```

The agent writes:
```python
results = search("weather NYC")
formatted = format(results, style="table")
print(formatted)
```

Benefits:
- **Composability**: The agent can chain operations, use variables, write loops, add conditionals — anything Python can do
- **Expressiveness**: Complex multi-step logic in one code block vs. multiple sequential tool calls
- **Efficiency**: Research shows LLMs produce more accurate tool use when writing code vs. JSON
- **Fewer tokens**: Code is more token-efficient than JSON for complex operations

### Tool Definitions

Tools are Python functions or classes exposed to the agent. There's a tool registry for sharing tools on/from HuggingFace Hub. Tools become callable functions in the agent's execution environment.

### Execution Security

This is where smolagents struggles. Code execution requires sandboxing:

- **LocalPythonExecutor**: Built-in restricted executor (default). Has had **critical security vulnerabilities** — CVE-2025-5120 was a sandbox escape allowing remote code execution. Patched in v1.17.0.
- **Docker sandbox**: Recommended for production
- **E2B, Modal, Blaxel, Pyodide+Deno**: Alternative sandboxed environments

The fundamental tension: code-as-action is powerful but inherently more dangerous than JSON tool calls. Every `additional_authorized_imports` widens the attack surface.

### What to Steal

**The core insight that LLMs are better at writing code than filling schemas.** For aiciv-mind, this suggests that tool orchestration should lean toward "write a script" rather than "emit a sequence of tool calls" when the task is complex. The ~1,000-line framework size is also instructive — it proves you don't need a massive framework to build capable agents.

### What to Avoid

**Code execution as the primary action mode for autonomous agents.** For aiciv-mind running autonomously with no human in the loop, having the LLM generate and execute arbitrary Python is a security nightmare. The sandbox escape CVE proves this isn't theoretical. Use code generation for specific, bounded tasks — not as the universal action primitive. Also avoid the documentation quality — consistently cited as poor.

---

## 7. Comparative Analysis

### Category Winners (for aiciv-mind's requirements)

| Requirement | Best Framework | Why |
|-------------|---------------|-----|
| **Supervisor → Worker pattern** | **OpenAI Agents SDK** | Handoffs-as-tools is the cleanest delegation primitive. LangGraph's subgraph approach is more powerful but more complex. |
| **Long-running agent state** | **LangGraph** | Checkpoint-based persistence with time-travel, branching, and resume is unmatched. |
| **Tool definition DX** | **Pydantic AI** | Type-safe tools from decorated functions with auto-schema generation and full IDE support. |
| **Autonomous looping (no human)** | **Claude Code** (architecture) | The TAOR loop with auto-compaction at 50% context, sub-agent isolation, and filesystem offloading is purpose-built for autonomous operation. |
| **Tracing / Observability** | **OpenAI Agents SDK** | Built-in tracing of LLM calls, tools, handoffs, guardrails, and custom events — but tied to OpenAI's platform. **Pydantic AI + Logfire** is the open alternative. |
| **Memory across sessions** | **CrewAI** | Unified memory with LLM-analyzed importance, composite recall scoring, and configurable weights. |
| **Testing** | **Pydantic AI** | TestModel, FunctionModel, Agent.override(), ALLOW_MODEL_REQUESTS, capture_run_messages. No contest. |
| **Multi-process agents** | **None** | No framework surveyed natively supports multiple agents in separate OS processes with IPC. Claude Code's Agent Teams come closest (separate tmux panes with shared task list). |

### Anti-Patterns to Avoid (Universal)

These mistakes appear across ALL frameworks:

1. **Over-abstracting coordination.** Every framework wraps LLM-to-LLM communication in its own DSL (graphs, crews, conversations, handoffs). The actual coordination is just "send a message, get a response." The abstraction layers become the primary source of bugs.

2. **Treating context as infinite.** Most frameworks don't have built-in context management. LangGraph has checkpoints but no compaction. CrewAI has memory but no context windowing. Only Claude Code's architecture treats context as a finite, managed resource with auto-compaction — and it's not a framework.

3. **Using LLMs for deterministic tasks.** Every framework encourages routing ALL decisions through the LLM. But input validation, output formatting, API call construction, error handling — these should be deterministic code, not LLM calls. The frameworks that succeed in production use "LLM for ambiguous decisions, code for everything else."

4. **Monolithic context.** Running everything in one context window means every tool result, every intermediate step, every error message competes for tokens. The solution — which only Claude Code and AutoGen v0.4 properly implement — is context isolation via sub-agents with independent windows.

5. **Framework lock-in masquerading as features.** Every framework has a "Platform" or "Cloud" offering that captures your agent definitions in their proprietary runtime. The framework is open source; the production deployment isn't.

### Where They All Over-Engineer

- **Agent "personalities"** (CrewAI's backstory, role definitions): Adds tokens to every prompt for marginal behavioral shaping. System prompts are enough.
- **Complex routing logic** (LangGraph conditional edges, CrewAI consensual process): The LLM can decide where to route with a simple tool call. You don't need a graph engine for this.
- **Memory hierarchies** (CrewAI's 4 memory types): In practice, "recent context + searchable long-term store" covers 95% of needs. The taxonomy adds complexity without proportional value.

---

## 8. The Steal List

| Framework | What to Steal for aiciv-mind |
|-----------|------------------------------|
| **LangGraph** | **Checkpoint-based state persistence.** Every mind state transition gets checkpointed. Resume from any point. Fork into alternative paths. Time-travel for debugging. Use SQLite for development, Postgres for production. |
| **CrewAI** | **Composite memory recall scoring.** When a mind searches its memory, score results by blending semantic similarity, recency, and importance with configurable weights. LLM-analyzed importance tagging on memory write. |
| **AutoGen** | **Actor model with typed async messages.** Minds are actors. They communicate via typed, async messages — not conversations, not function calls. This naturally supports multi-process deployment and scales to distributed systems. Also: **declarative mind specification** in JSON for dynamic spawning. |
| **OpenAI Agents SDK** | **Handoffs-as-tools for delegation.** When Primary wants to delegate to a sub-mind, it calls a tool (e.g., `delegate_to_research_lead(task="...")`). The sub-mind is just a tool call that happens to spawn an agent. Simple, composable, LLM-native. |
| **Pydantic AI** | **Three things**: (1) Dependency injection via typed RunContext for separating mind definition from runtime. (2) Type-safe tool definitions from decorated functions. (3) TestModel for deterministic testing without LLM calls. |
| **smolagents** | **Minimalism as a design principle.** The entire agent loop in ~1,000 lines. Prove that aiciv-mind's core can be comparably lean. Also: the insight that LLMs are better at writing code than filling schemas — offer a "code action" mode for complex tool orchestration. |
| **Claude Code** | **The motherlode.** (1) TAOR loop as the core execution model. (2) Auto-compaction at ~50% context capacity. (3) Sub-agent isolation with independent context windows returning only summaries. (4) Six-layer memory system loaded at session start. (5) Filesystem as extended memory (write intermediate results to disk, not context). (6) Permission spectrum (plan → default → acceptEdits → dontAsk → bypass). (7) Hooks at every lifecycle event for deterministic guardrails. (8) Worktree isolation for parallel execution. (9) Declarative extensibility via .md and .json — not code. (10) "Delete code on model upgrade" — architecture should get thinner as models improve. |

---

## 9. Claude Code Architecture

**Confidence**: HIGH (open-source repo + extensive reverse engineering + Pragmatic Engineer interview with Boris Cherny)

### Is Claude Code Open Source?

Yes. The official repository is at [github.com/anthropics/claude-code](https://github.com/anthropics/claude-code). As of March 2026 it has ~81.6K GitHub stars. Built with TypeScript, React (Ink for terminal UI), Yoga (layout), and Bun (build/package).

### The Agent Loop (TAOR)

Claude Code's core is a **single-threaded master loop** internally codenamed "nO":

```
Think → Act → Observe → Repeat
```

The orchestrator is ~50 lines of logic. All intelligence resides in the model and prompt. The loop continues until the model signals completion, with a configurable `maxTurns` cap preventing runaway execution.

This is the most important architectural insight: **the loop is dumb; the model is smart.** The framework's job is to manage context and execute tools, not to make decisions.

### Tool System (4 Primitives)

Rather than 100 specialized tools, Claude Code provides 4 capability primitives:
- **Read**: File and directory access
- **Write/Edit**: File modification
- **Execute**: Bash shell access ("the universal adapter")
- **Connect**: MCP for external services

In practice, Claude Code ships ~14 built-in tools. The key insight: **bash is the universal tool.** Any CLI tool, any script, any API call via curl — all accessible through one primitive.

### Context Management

Claude Code treats tokens as a **scarce resource**:

- **Auto-Compaction**: At ~50% context capacity (some sources say 92%), the LLM summarizes prior transcript into decision summaries, preserving reasoning while freeing space.
- **Sub-Agent Isolation**: Heavy tasks delegate to isolated TAOR loops with independent context windows. Sub-agents return only summaries — preventing "context pollution."
- **Semantic Tool Search**: For MCP servers with 100+ tools, semantic search injects only relevant tool definitions.
- **Filesystem Offloading**: Long-running agents write intermediate results to files rather than keeping them in context. The filesystem is extended memory.

### Six-Layer Memory

Loaded at session start (agent never starts from zero):
1. Organization policies
2. Project configuration (CLAUDE.md)
3. User preferences
4. Auto-learned patterns
5. Local state
6. Automatic memory (MEMORY.md)

### Sub-Agent Architecture

Three built-in variants:
- **Explore**: Fast, read-only (Haiku-class model)
- **Plan**: Research-focused
- **General-purpose**: Full tools

Custom sub-agents defined via `.md` files with YAML frontmatter specifying:
- Available tools (whitelist/blacklist)
- Model selection
- Permission mode
- Memory scope
- Max turns
- Skill preloading

Sub-agents can run in **foreground** (blocking, user sees permission prompts) or **background** (concurrent, permissions pre-approved).

### Agent Teams

Experimental feature for peer coordination:
- Separate Claude Code instances coordinate via **shared task list** (`~/.claude/tasks/`)
- Self-claim unassigned, unblocked tasks
- Bidirectional message/broadcast IPC
- Independent context windows and compaction
- Quality-gate hooks: `TeammateIdle` and `TaskCompleted`

### Permission System (Trust Spectrum)

| Mode | Behavior |
|------|----------|
| `plan` | Read-only |
| `default` | Ask before edits/shell |
| `acceptEdits` | Auto-approve file changes |
| `dontAsk` | Auto-approve whitelisted tools |
| `bypassPermissions` | Skip all checks |

Glob patterns and tool-level allow/deny rules. Static analysis validates every tool call.

### Hooks (Lifecycle Events)

Deterministic scripts (not LLM-powered) firing at:
- `SessionStart`, `SessionEnd`
- `UserPromptSubmit` (can transform input)
- `PreToolUse`, `PostToolUse`, `PostToolUseFailure`
- `PermissionRequest` (auto-approve/deny)
- `PreCompact` (inject context into summary)

### Key Design Principles

1. **Model-agnosticism**: Swap the brain without rebuilding the body
2. **Co-evolution**: "Delete code on model upgrade" — architecture gets thinner as models improve
3. **Composability over coverage**: Generic primitives outperform bespoke tools
4. **Context as product**: Every architectural decision manages a single bounded budget
5. **90% self-written**: Claude Code writes 90% of its own code

### Claude Agent SDK

The Agent SDK extracts Claude Code's core into a reusable Python/TypeScript library:
- Same agent loop, tools, and context management
- Session persistence (write to disk, resume by ID)
- Built-in tools available as string names (`["Read", "Glob", "Bash"]`)
- Hooks for safety/observability
- Subagent spawning with independent contexts
- Streaming event system

### What to Steal for aiciv-mind

Nearly everything. Claude Code is the closest existing system to what aiciv-mind needs:
- The TAOR loop is the right execution model
- Context management (compaction + isolation + filesystem offloading) is essential
- The sub-agent architecture matches primary→sub-mind
- Agent Teams' shared task list is a proven IPC mechanism
- The hook system provides deterministic safety without LLM overhead
- Declarative extensibility via markdown files matches aiciv-mind's skill/manifest system

**The gap**: Claude Code is designed as a coding assistant with a human in the loop (permission prompts). aiciv-mind needs to run fully autonomously. The `bypassPermissions` mode exists but isn't the default workflow. aiciv-mind needs autonomous operation as the primary mode with safety constraints built into the mind's constitution, not the permission system.

---

## 10. Architectural Recommendations for aiciv-mind

Based on this survey, here is what aiciv-mind should look like:

### Core Loop
Adopt Claude Code's **TAOR pattern**: Think → Act → Observe → Repeat. Keep the orchestrator minimal (~100 lines). All intelligence in the model and prompt. Configurable `maxTurns` as a safety cap.

### Context Management
- Auto-compaction at configurable threshold (50-80% capacity)
- Sub-mind isolation with independent context windows
- Filesystem as extended memory (write scratchpads, read on demand)
- Semantic search for tool/skill injection (don't load everything upfront)

### State Persistence
Steal LangGraph's checkpoint model: every state transition checkpointed to SQLite (dev) / Postgres (prod). Support resume, fork, and time-travel.

### Mind Spawning
Use OpenAI SDK's handoffs-as-tools: Primary calls `spawn_research_lead(task=...)` as a tool call. The framework handles the actual spawning (process creation, tmux pane, context setup). The LLM doesn't need to know about the spawning machinery — it just calls a function.

### Tool System
Pydantic AI's type-safe tool definitions + Claude Code's "bash as universal adapter":
- Tools defined as decorated Python functions with type hints
- Auto-generated schemas from type annotations
- Bash/shell as the escape hatch for anything without a dedicated tool
- Dependency injection via typed context for runtime flexibility

### Memory
CrewAI's composite scoring for recall + Claude Code's layered loading:
- Constitutional principles loaded first (always in context)
- Session memory loaded at start
- Long-term memory searched on demand with composite scoring (similarity + recency + importance)
- Learning capture at session end

### Inter-Mind Communication
AutoGen v0.4's actor model: minds are actors communicating via typed async messages. This supports:
- Same-process (for development)
- Cross-process via IPC (for production)
- Cross-machine via network (for future distributed deployment)

### Testing
Pydantic AI's TestModel pattern: deterministic mock models that exercise tool logic without LLM calls. Essential for CI/CD.

### Safety
Claude Code's hook system: deterministic scripts at lifecycle events for guardrails, logging, and governance — outside the LLM, zero AI, pure code.

---

## 11. Sources

### LangGraph
- [LangGraph Architecture and Design (Medium)](https://medium.com/@shuv.sdr/langgraph-architecture-and-design-280c365aaf2c)
- [LangGraph Explained 2026 Edition (Medium)](https://medium.com/@dewasheesh.rana/langgraph-explained-2026-edition-ea8f725abff3)
- [LangGraph GitHub](https://github.com/langchain-ai/langgraph)
- [LangGraph Persistence Docs](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Streaming Docs](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangGraph Supervisor GitHub](https://github.com/langchain-ai/langgraph-supervisor-py)
- [Hierarchical Agent Teams Tutorial](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/hierarchical_agent_teams/)
- [LangGraph Limitations 2025 (Latenode Community)](https://community.latenode.com/t/current-limitations-of-langchain-and-langgraph-frameworks-in-2025/30994)
- [LangGraph Alternatives 2026](https://www.ema.ai/additional-blogs/addition-blogs/langgraph-alternatives-to-consider)

### CrewAI
- [CrewAI Memory Docs](https://docs.crewai.com/en/concepts/memory)
- [CrewAI Tasks Docs](https://docs.crewai.com/en/concepts/tasks)
- [CrewAI Framework 2025 Review (Latenode)](https://latenode.com/blog/ai-frameworks-technical-infrastructure/crewai-framework/crewai-framework-2025-complete-review-of-the-open-source-multi-agent-ai-platform)
- [CrewAI Hierarchical Teams Blueprint (SparkCo)](https://sparkco.ai/blog/implementing-crewai-in-hierarchical-teams-a-2025-blueprint)
- [Why CrewAI Manager-Worker Fails (Towards Data Science)](https://towardsdatascience.com/why-crewais-manager-worker-architecture-fails-and-how-to-fix-it/)
- [CrewAI Practical Lessons (Medium)](https://ondrej-popelka.medium.com/crewai-practical-lessons-learned-b696baa67242)
- [CrewAI GitHub](https://github.com/crewAIInc/crewAI)

### AutoGen
- [AutoGen 0.4 Launch Blog (Microsoft)](https://devblogs.microsoft.com/autogen/autogen-reimagined-launching-autogen-0-4/)
- [AutoGen v0.4 Research Blog (Microsoft)](https://www.microsoft.com/en-us/research/blog/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/)
- [AutoGen Migration Guide](https://microsoft.github.io/autogen/stable//user-guide/agentchat-user-guide/migration-guide.html)
- [AutoGen Docker Code Executor](https://microsoft.github.io/autogen/stable//user-guide/core-user-guide/components/command-line-code-executors.html)
- [AutoGen Maintenance Mode (DEV Community)](https://dev.to/clickit_devops/choosing-the-right-agent-framework-in-2026-is-autogen-enough-3332)
- [Microsoft AutoGen Has Split (DEV Community)](https://dev.to/maximsaplin/microsoft-autogen-has-split-in-2-wait-3-no-4-parts-2p58)

### OpenAI Agents SDK
- [OpenAI Agents SDK Docs](https://openai.github.io/openai-agents-python/)
- [Handoffs Documentation](https://openai.github.io/openai-agents-python/handoffs/)
- [Tracing Documentation](https://openai.github.io/openai-agents-python/tracing/)
- [Guardrails Documentation](https://openai.github.io/openai-agents-python/guardrails/)
- [OpenAI Agents SDK Review (Mem0, Dec 2025)](https://mem0.ai/blog/openai-agents-sdk-review)
- [OpenAI Vendor Lock-In Analysis (ModelsLab)](https://modelslab.com/blog/api/openai-vendor-lock-in-multi-provider-api-2026)

### Pydantic AI
- [Pydantic AI Docs](https://ai.pydantic.dev/)
- [Dependencies Documentation](https://ai.pydantic.dev/dependencies/)
- [Testing Documentation](https://ai.pydantic.dev/testing/)
- [Function Tools Documentation](https://ai.pydantic.dev/tools/)
- [Multi-Agent Patterns](https://ai.pydantic.dev/multi-agent-applications/)
- [Pydantic AI GitHub](https://github.com/pydantic/pydantic-ai)
- [2026 Framework Decision Guide (DEV Community)](https://dev.to/linou518/the-2026-ai-agent-framework-decision-guide-langgraph-vs-crewai-vs-pydantic-ai-b2h)

### smolagents
- [smolagents Docs (HuggingFace)](https://huggingface.co/docs/smolagents/en/index)
- [smolagents Blog Post (HuggingFace)](https://huggingface.co/blog/smolagents)
- [smolagents GitHub](https://github.com/huggingface/smolagents)
- [CVE-2025-5120 Sandbox Escape](https://github.com/advisories/GHSA-6v92-r5mx-h5fx)
- [NCC Group Security Analysis](https://www.nccgroup.com/research/autonomous-ai-agents-a-hidden-risk-in-insecure-smolagents-codeagent-usage/)
- [Secure Code Execution Docs](https://huggingface.co/docs/smolagents/en/tutorials/secure_code_execution)

### Claude Code
- [Claude Code GitHub (anthropics/claude-code)](https://github.com/anthropics/claude-code)
- [Claude Code Architecture Reverse Engineered (Substack)](https://vrungta.substack.com/p/claude-code-architecture-reverse)
- [How Claude Code is Built (Pragmatic Engineer)](https://newsletter.pragmaticengineer.com/p/how-claude-code-is-built)
- [Claude Code Agent Loop (Docs)](https://platform.claude.com/docs/en/agent-sdk/agent-loop)
- [Claude Code Overview (Docs)](https://code.claude.com/docs/en/overview)
- [Agent Teams (Docs)](https://code.claude.com/docs/en/agent-teams)
- [Claude Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Sessions Documentation](https://platform.claude.com/docs/en/agent-sdk/sessions)
- [Claude Code Behind the Scenes (PromptLayer)](https://blog.promptlayer.com/claude-code-behind-the-scenes-of-the-master-agent-loop/)
- [ZenML Analysis: Single-Threaded Master Loop](https://www.zenml.io/llmops-database/claude-code-agent-architecture-single-threaded-master-loop-for-autonomous-coding)

### Comparative / Meta
- [Agent Design Patterns (Lance Martin, LangChain)](https://rlancemartin.github.io/2026/01/09/agent_design/)
- [Best Agent Frameworks Comparison (LangWatch)](https://langwatch.ai/blog/best-ai-agent-frameworks-in-2025-comparing-langgraph-dspy-crewai-agno-and-more)
- [AutoGen vs CrewAI vs LangGraph vs PydanticAI (Victor Dibia)](https://newsletter.victordibia.com/p/autogen-vs-crewai-vs-langgraph-vs)
- [AI Agent Frameworks Compared 2026 (SparkCo)](https://sparkco.ai/blog/ai-agent-frameworks-compared-langchain-autogen-crewai-and-openclaw-in-2026)
- [Top 9 Frameworks March 2026 (Shakudo)](https://www.shakudo.io/blog/top-9-ai-agent-frameworks)
- [Agentic Design Patterns 2026 (Sitepoint)](https://www.sitepoint.com/the-definitive-guide-to-agentic-design-patterns-in-2026/)
- [Agentic Frameworks in Production 2026 (Zircon Tech)](https://zircon.tech/blog/agentic-frameworks-in-2026-what-actually-works-in-production/)
