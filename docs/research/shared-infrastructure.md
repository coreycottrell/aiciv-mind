# Shared Infrastructure Research Report

**Date**: 2026-03-30
**Researcher**: infra-agent (Opus 4.6)
**Scope**: tmux process management, IPC, service clients, memory, manifest format for aiciv-mind

---

## Executive Summary

aiciv-mind needs five shared infrastructure pillars: tmux-based process management for sub-minds, a message bus for mind-to-mind IPC, async Python clients for AiCIV services, queryable structured memory, and a declarative manifest format.

**Key recommendations:**

1. **tmux**: Use `libtmux` (Python API) with 1-named-window-per-mind architecture. It provides typed Python objects for sessions/windows/panes, capture-pane for output monitoring, and `pane_pid` / `pane_current_command` for process lifecycle detection.

2. **IPC**: Use ZeroMQ (pyzmq) with a ROUTER/DEALER pattern. Primary mind runs a ROUTER socket; each sub-mind connects with a DEALER. This gives us async bidirectional messaging, identity-based routing, heartbeat detection, and broadcast shutdown -- all without external dependencies like Redis.

3. **Service clients**: Build async Python clients using `httpx.AsyncClient` following the pattern already established in `aiciv-suite-sdk/auth.py` and `tools/hub_comment.py`. Add JWT token caching with 50-minute auto-refresh, tenacity-based retry, and a simple service registry YAML.

4. **Memory**: SQLite with FTS5 for structured queryable memory, keeping markdown files for human-readable output. Add `sqlite-vec` later for semantic search. Schema supports agent, domain, session, and tag-based queries with full-text search across content.

5. **Manifest**: YAML format. Each mind defined by system prompt, tools, services, model preferences, memory config, and sub-mind spawn permissions. YAML is human-editable and already used by agentmind's `config.yaml`.

---

## 1. tmux Architecture

### 1.1 Python Libraries Compared

**Confidence: HIGH**

#### libtmux (recommended)

- **What it is**: Typed Python API wrapping tmux CLI commands. Provides `Server`, `Session`, `Window`, `Pane` objects.
- **Maintenance**: Actively maintained (v0.55.0 as of 2026). Same author maintains tmuxp. Pre-1.0 API but stable enough for production use -- pin to `libtmux>=0.55,<0.56`.
- **Key API surface**:

```python
import libtmux

server = libtmux.Server()

# Create a session for this mind runtime
session = server.new_session(session_name="aiciv-mind-runtime")

# Create a named window for a sub-mind
window = session.new_window(window_name="gateway-lead", attach=False)
pane = window.active_pane

# Start a process in the pane
pane.send_keys("python3 /opt/aiciv-mind/run_mind.py --manifest gateway-lead.yaml", enter=True)

# Capture output (returns list of strings)
output_lines = pane.capture_pane()
# Or via lower-level cmd:
result = pane.cmd("capture-pane", "-p", "-S", "-50")  # last 50 lines
lines = result.stdout  # list[str]

# Send input to the pane
pane.send_keys("some input text", enter=True)

# Check process state via tmux format variables
pane_pid = pane.pane_pid           # PID of the shell/process
pane_cmd = pane.pane_current_command  # e.g. "python3" or "bash"
```

- **capture_pane details**: Returns visible terminal buffer as list of strings. Parameters control range (`-S start`, `-E end`), formatting (`-J` to join wrapped lines, `-N` to preserve trailing spaces, `-T` to trim trailing positions). Default returns the visible pane content. Can capture scrollback with negative start values (e.g., `-S -500` for last 500 lines).
- **Limitations**: capture_pane returns rendered terminal text, not raw process stdout. ANSI escape codes may appear. Issue #188 noted single-line returns in some edge cases (fixed in recent versions).

#### tmuxp

- **What it is**: Session manager built on libtmux. Loads tmux layouts from YAML/JSON config files.
- **Useful for**: Defining the initial aiciv-mind session layout declaratively (how many panes, what commands to run). NOT useful for runtime dynamic management (spawning/killing sub-minds on demand).
- **Verdict**: Could be useful for the initial "boot" layout of aiciv-mind (define the primary mind's session in YAML), but libtmux is needed for all runtime operations. Using tmuxp for boot + libtmux for runtime is reasonable but adds a dependency for marginal benefit.

#### Direct subprocess tmux CLI calls

- **When better**: One-off scripts, shell scripts, or when you need a tmux feature not yet exposed by libtmux. The current ACG codebase uses this extensively (hub_watcher.py, telegram_unified.py, autonomy_nudge.sh all use `subprocess.run(["tmux", "send-keys", ...])`.
- **Downsides**: No type safety, string-based pane targeting is error-prone, no object model for tracking state.
- **Verdict**: Fine for simple injection scripts. Not suitable for aiciv-mind's core process manager.

#### Recommendation

**Use libtmux for all aiciv-mind tmux operations.** It provides the right abstraction level: typed Python objects for sessions/windows/panes, methods for capture/send/lifecycle, and it wraps the tmux CLI so you never lose access to raw features via `pane.cmd()`.

Pin version: `libtmux>=0.55,<0.56` (pre-1.0 API churn risk).

### 1.2 Recommended Architecture: Pane-to-Mind Mapping

**Confidence: HIGH**

**Architecture: 1 named window per mind, 1 pane per window (initially).**

```
tmux session: "aiciv-mind-20260330"
  |
  +-- window "primary"        (pane %0)  -- primary mind process
  +-- window "gateway-lead"   (pane %1)  -- sub-mind
  +-- window "comms-lead"     (pane %2)  -- sub-mind
  +-- window "research-lead"  (pane %3)  -- sub-mind
  ...
```

**Why 1 window per mind (not 1 pane in a shared window):**

1. **Named windows** give human-readable identification. `tmux select-window -t "gateway-lead"` is clearer than remembering pane IDs.
2. **Independent scrollback** per window. Each mind gets its own full scrollback buffer without competing for screen real estate.
3. **Clean lifecycle**: killing a window kills its pane and process cleanly. No pane renumbering issues.
4. **Monitoring**: `tmux list-windows` gives a one-line status overview of all minds.
5. **Future**: A sub-mind could split its own window into sub-panes for its own workers, keeping the hierarchy clean.

**Mind registry (in-memory)**:

```python
@dataclass
class MindHandle:
    mind_id: str                    # e.g. "gateway-lead"
    manifest_path: str              # path to YAML manifest
    window_name: str                # tmux window name
    pane_id: str                    # tmux pane ID (e.g. "%3")
    pid: int                        # OS PID of the mind process
    zmq_identity: bytes             # ZMQ DEALER identity
    started_at: float               # time.monotonic()
    state: str                      # "starting" | "running" | "stopping" | "stopped" | "crashed"

class MindRegistry:
    minds: dict[str, MindHandle] = {}

    def register(self, handle: MindHandle): ...
    def get(self, mind_id: str) -> MindHandle | None: ...
    def all_running(self) -> list[MindHandle]: ...
    def mark_stopped(self, mind_id: str): ...
```

### 1.3 Process Lifecycle Management

**Confidence: HIGH**

#### Starting a process in a tmux pane

```python
import libtmux
import os

def spawn_mind(session: libtmux.Session, mind_id: str, manifest_path: str) -> MindHandle:
    """Spawn a sub-mind process in a new tmux window."""
    window = session.new_window(window_name=mind_id, attach=False)
    pane = window.active_pane

    # Start the mind process
    cmd = f"python3 -u /opt/aiciv-mind/run_mind.py --manifest {manifest_path} --id {mind_id}"
    pane.send_keys(cmd, enter=True)

    # Give process a moment to start, then read PID
    import time
    time.sleep(0.5)

    # Get the PID of the process running in the pane
    # pane_pid gives the shell PID; we need the child process PID
    # Use pgrep or /proc to find the actual python process
    shell_pid = int(pane.pane_pid)

    return MindHandle(
        mind_id=mind_id,
        manifest_path=manifest_path,
        window_name=mind_id,
        pane_id=pane.pane_id,
        pid=shell_pid,
        zmq_identity=mind_id.encode(),
        started_at=time.monotonic(),
        state="starting",
    )
```

#### Detecting process state (running vs. crashed vs. finished)

Three complementary strategies:

**Strategy 1: tmux format variables (cheap, polled)**
```python
def check_pane_alive(pane: libtmux.Pane) -> tuple[bool, str]:
    """Check if the mind process is still running via tmux."""
    current_cmd = pane.pane_current_command  # e.g. "python3" or "bash"
    # If it fell back to shell, the process exited
    if current_cmd in ("bash", "zsh", "sh", "fish"):
        return False, f"process exited (shell={current_cmd})"
    return True, current_cmd
```

**Strategy 2: OS-level PID check (reliable)**
```python
import os
import signal

def check_pid_alive(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)  # Signal 0 = existence check, no actual signal sent
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but we can't signal it
```

**Strategy 3: ZMQ heartbeat (application-level, most reliable)**
```python
# Primary sends heartbeat request every N seconds via ZMQ
# If sub-mind doesn't respond within timeout, mark as unresponsive
# This catches: process alive but hung, process crashed but shell still open
```

**Recommended: All three.** ZMQ heartbeat is the primary health check. PID check catches hard crashes. tmux format check catches clean exits. Poll every 5 seconds for heartbeats, every 30 seconds for PID/tmux.

#### Graceful shutdown

```python
async def shutdown_mind(handle: MindHandle, router_socket, timeout: float = 10.0):
    """Gracefully shut down a sub-mind."""
    handle.state = "stopping"

    # Step 1: Send shutdown message via ZMQ
    await router_socket.send_multipart([
        handle.zmq_identity,
        b"",
        json.dumps({"type": "shutdown", "reason": "orchestrator_request"}).encode(),
    ])

    # Step 2: Wait for acknowledgment or timeout
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not check_pid_alive(handle.pid):
            handle.state = "stopped"
            return
        await asyncio.sleep(0.5)

    # Step 3: Force kill if still running
    import signal
    try:
        os.kill(handle.pid, signal.SIGTERM)
        await asyncio.sleep(2.0)
        if check_pid_alive(handle.pid):
            os.kill(handle.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    handle.state = "stopped"
```

#### capture-pane details

`tmux capture-pane -p` returns the visible pane content as text. Key options:

| Flag | Effect |
|------|--------|
| `-p` | Print to stdout (instead of paste buffer) |
| `-S -N` | Start capture N lines before visible area (scrollback) |
| `-E N` | End capture at line N |
| `-J` | Join wrapped lines (recommended for parsing) |
| `-T` | Trim trailing whitespace (tmux 3.4+) |
| `-e` | Include escape sequences (for color) |

In libtmux:
```python
# Last 100 lines, joined, trimmed
lines = pane.capture_pane(start=-100, join_wrapped=True, trim_trailing=True)
# Returns: list[str], one per line
```

**Limitations**: Capture returns rendered terminal output, not raw process stdout. If a process writes binary data or complex TUI output, capture will contain the rendered result. For structured communication, use IPC (Section 2) instead of capture-pane.

---

## 2. IPC Message Bus

### 2.1 Options Survey

**Confidence: HIGH**

| Mechanism | Latency (localhost) | Reliability | Setup Complexity | Message Patterns | External Dependencies |
|-----------|-------------------|-------------|-----------------|------------------|-----------------------|
| **Unix domain sockets** | ~10-50us | High (kernel-managed) | Medium (manual framing) | Point-to-point only | None |
| **Named pipes (FIFO)** | ~10-50us | Medium (blocking, unidirectional) | Low | Unidirectional only | None |
| **ZeroMQ (pyzmq)** | ~30-80us | High (reconnect, buffering) | Low (pip install pyzmq) | PUB/SUB, PUSH/PULL, REQ/REP, DEALER/ROUTER | libzmq (bundled with pyzmq) |
| **Redis pub/sub** | ~100-300us | High | High (Redis server) | PUB/SUB, Streams | Redis server process |
| **File-based (current)** | ~1-10ms (fsnotify) | Low (race conditions, no ordering) | Low | Ad-hoc | None |

#### Unix domain sockets (raw)

Python's `socket` module supports `AF_UNIX` sockets. You get kernel-level reliability and sub-millisecond latency. But you must handle:
- Message framing (length-prefix or delimiter)
- Connection management (accept/reconnect)
- Routing (which socket is which mind)
- Multiplexing (asyncio integration)

This is essentially rebuilding what ZMQ already provides.

#### Named pipes (FIFOs)

`os.mkfifo()` creates a FIFO. Simple but limited:
- Unidirectional (need two FIFOs for bidirectional)
- Blocking reads by default (need O_NONBLOCK or asyncio)
- No built-in message framing
- No multiplexing

Best for: simple one-way data streams. Not suitable for request/response or multi-mind routing.

#### ZeroMQ (pyzmq)

**Best fit for aiciv-mind.** Here's why each pattern maps:

| Pattern | Use Case | Fit for aiciv-mind |
|---------|----------|-------------------|
| **ROUTER/DEALER** | Async request-reply with identity routing | **PRIMARY PATTERN** -- primary (ROUTER) talks to N sub-minds (DEALER) |
| **PUB/SUB** | One-to-many broadcast | **SECONDARY** -- broadcast shutdown, config changes |
| **PUSH/PULL** | Task distribution pipeline | Possible for fire-and-forget tasks, but DEALER/ROUTER is more flexible |
| **REQ/REP** | Synchronous request-reply | Too rigid -- blocks on each request |

ZMQ advantages:
- Automatic reconnection (sub-mind restarts, primary doesn't need to reconnect)
- Message framing built-in (no manual length-prefix)
- Identity-based routing (ROUTER knows which DEALER sent what)
- IPC transport (`ipc:///tmp/aiciv-mind.sock`) avoids TCP overhead
- Zero external dependencies (libzmq bundled with pyzmq wheel)
- asyncio integration via `zmq.asyncio.Context`

#### Redis pub/sub

Powerful but overkill for same-machine IPC:
- Requires running a Redis server process
- Adds ~100-200us network overhead even on localhost
- Better suited for cross-machine communication
- Already familiar in the ecosystem (ACG doesn't currently use Redis)

**Verdict: Skip for v1.** If aiciv-mind later needs cross-machine communication (minds on different VPS), Redis or NATS becomes relevant. For same-machine, ZMQ is superior.

### 2.2 Recommendation: ZeroMQ ROUTER/DEALER

**Confidence: HIGH**

**Primary bus**: ZMQ ROUTER (primary mind) + DEALER (each sub-mind) over IPC transport.

**Why ROUTER/DEALER specifically:**
- Primary needs to send messages to *specific* sub-minds (not broadcast)
- Sub-minds need to send results back to primary (not to each other)
- ROUTER tracks identity of each connected DEALER automatically
- Non-blocking: primary can send to mind A while waiting for mind B's response
- Supports concurrent conversations with many sub-minds

**Secondary bus**: ZMQ PUB/SUB for broadcast (shutdown all, config reload). Primary is PUB, sub-minds are SUB.

**Message format: JSON** (not MessagePack).

Rationale: JSON is human-debuggable (critical for early development), Python's `json` module is stdlib (no dependency), and the message sizes in aiciv-mind are small (task descriptions, results, heartbeats -- not bulk data). MessagePack saves ~30% wire size but adds a dependency and kills debuggability. Switch to MessagePack later if profiling shows JSON serialization is a bottleneck (it will not be).

### 2.3 Code Sketch: ROUTER/DEALER Setup

```python
"""
aiciv-mind IPC bus using ZeroMQ ROUTER/DEALER pattern.

Primary mind:  ROUTER socket (binds)
Sub-minds:     DEALER sockets (connect, identity = mind_id)

Message envelope: [identity, empty_frame, json_payload]
"""

import asyncio
import json
import time
import zmq
import zmq.asyncio

# ── Message Types ──────────────────────────────────────────────

MSG_TASK        = "task"           # primary -> sub-mind: work request
MSG_RESULT      = "result"         # sub-mind -> primary: work complete
MSG_HEARTBEAT   = "heartbeat"     # bidirectional health check
MSG_HEARTBEAT_ACK = "heartbeat_ack"
MSG_SHUTDOWN    = "shutdown"       # primary -> sub-mind: graceful stop
MSG_SHUTDOWN_ACK = "shutdown_ack"  # sub-mind -> primary: stopping
MSG_STATUS      = "status"         # sub-mind -> primary: progress update
MSG_LOG         = "log"            # sub-mind -> primary: log message


# ── Primary Mind (ROUTER) ─────────────────────────────────────

class PrimaryBus:
    """IPC bus for the primary mind (ROUTER side)."""

    def __init__(self, ipc_path: str = "ipc:///tmp/aiciv-mind-router.sock"):
        self.ctx = zmq.asyncio.Context()
        self.router = self.ctx.socket(zmq.ROUTER)
        self.router.bind(ipc_path)

        # PUB socket for broadcast messages (shutdown all, etc.)
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind("ipc:///tmp/aiciv-mind-broadcast.sock")

        self._handlers: dict[str, callable] = {}

    def on_message(self, msg_type: str, handler: callable):
        """Register a handler for a message type."""
        self._handlers[msg_type] = handler

    async def send_to_mind(self, mind_id: str, msg_type: str, payload: dict):
        """Send a message to a specific sub-mind."""
        envelope = {
            "type": msg_type,
            "ts": time.time(),
            **payload,
        }
        await self.router.send_multipart([
            mind_id.encode(),      # identity frame
            b"",                   # empty delimiter frame
            json.dumps(envelope).encode(),
        ])

    async def broadcast(self, msg_type: str, payload: dict):
        """Broadcast a message to all sub-minds via PUB."""
        envelope = {
            "type": msg_type,
            "ts": time.time(),
            **payload,
        }
        await self.pub.send_multipart([
            msg_type.encode(),     # topic (for SUB filtering)
            json.dumps(envelope).encode(),
        ])

    async def recv_loop(self):
        """Main receive loop -- dispatches to registered handlers."""
        while True:
            frames = await self.router.recv_multipart()
            # ROUTER frames: [identity, empty, payload]
            if len(frames) < 3:
                continue
            identity = frames[0].decode()
            payload = json.loads(frames[2])
            msg_type = payload.get("type", "unknown")

            handler = self._handlers.get(msg_type)
            if handler:
                await handler(identity, payload)

    async def send_task(self, mind_id: str, task_id: str, objective: str, context: dict = None):
        """Convenience: send a task to a sub-mind."""
        await self.send_to_mind(mind_id, MSG_TASK, {
            "task_id": task_id,
            "objective": objective,
            "context": context or {},
        })

    async def request_shutdown_all(self):
        """Broadcast shutdown to all sub-minds."""
        await self.broadcast(MSG_SHUTDOWN, {"reason": "primary_shutdown"})

    def close(self):
        self.router.close()
        self.pub.close()
        self.ctx.term()


# ── Sub-Mind (DEALER) ──────────────────────────────────────────

class SubMindBus:
    """IPC bus for a sub-mind (DEALER side)."""

    def __init__(self, mind_id: str, ipc_path: str = "ipc:///tmp/aiciv-mind-router.sock"):
        self.mind_id = mind_id
        self.ctx = zmq.asyncio.Context()

        # DEALER socket with identity
        self.dealer = self.ctx.socket(zmq.DEALER)
        self.dealer.setsockopt(zmq.IDENTITY, mind_id.encode())
        self.dealer.connect(ipc_path)

        # SUB socket for broadcast
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.connect("ipc:///tmp/aiciv-mind-broadcast.sock")
        self.sub.subscribe(MSG_SHUTDOWN.encode())  # subscribe to shutdown topic

        self._handlers: dict[str, callable] = {}

    def on_message(self, msg_type: str, handler: callable):
        self._handlers[msg_type] = handler

    async def send_to_primary(self, msg_type: str, payload: dict):
        """Send a message to the primary mind."""
        envelope = {
            "type": msg_type,
            "mind_id": self.mind_id,
            "ts": time.time(),
            **payload,
        }
        await self.dealer.send_multipart([
            b"",                   # empty delimiter
            json.dumps(envelope).encode(),
        ])

    async def send_result(self, task_id: str, result: dict):
        """Send task result to primary."""
        await self.send_to_primary(MSG_RESULT, {
            "task_id": task_id,
            "result": result,
        })

    async def send_heartbeat_ack(self):
        await self.send_to_primary(MSG_HEARTBEAT_ACK, {})

    async def recv_loop(self):
        """Receive from both DEALER (direct) and SUB (broadcast)."""
        poller = zmq.asyncio.Poller()
        poller.register(self.dealer, zmq.POLLIN)
        poller.register(self.sub, zmq.POLLIN)

        while True:
            events = dict(await poller.poll(timeout=1000))

            if self.dealer in events:
                frames = await self.dealer.recv_multipart()
                # DEALER frames: [empty, payload]
                payload = json.loads(frames[-1])
                msg_type = payload.get("type", "unknown")
                handler = self._handlers.get(msg_type)
                if handler:
                    await handler(payload)

            if self.sub in events:
                frames = await self.sub.recv_multipart()
                # PUB/SUB frames: [topic, payload]
                payload = json.loads(frames[-1])
                msg_type = payload.get("type", "unknown")
                handler = self._handlers.get(msg_type)
                if handler:
                    await handler(payload)

    def close(self):
        self.dealer.close()
        self.sub.close()
        self.ctx.term()


# ── Heartbeat Manager ──────────────────────────────────────────

class HeartbeatManager:
    """Periodic heartbeat check for all registered sub-minds."""

    def __init__(self, bus: PrimaryBus, interval: float = 5.0, timeout: float = 15.0):
        self.bus = bus
        self.interval = interval
        self.timeout = timeout
        self._last_seen: dict[str, float] = {}

    def record_heartbeat(self, mind_id: str):
        self._last_seen[mind_id] = time.monotonic()

    def unresponsive_minds(self) -> list[str]:
        now = time.monotonic()
        return [
            mid for mid, last in self._last_seen.items()
            if now - last > self.timeout
        ]

    async def run(self):
        while True:
            # Send heartbeat to all known minds
            for mind_id in list(self._last_seen.keys()):
                await self.bus.send_to_mind(mind_id, MSG_HEARTBEAT, {})
            await asyncio.sleep(self.interval)
```

---

## 3. Service Integration Design

### 3.1 Existing Patterns Found in Codebase

**Confidence: HIGH**

I examined three existing service client patterns in the ACG codebase:

#### Pattern A: aiciv-suite-sdk AgentAuthClient (`projects/aiciv-suite-sdk/aiciv_suite/auth.py`)

- Synchronous `requests.Session` based client
- Clean class with method-per-endpoint
- Ed25519 challenge-response login flow
- Custom `AgentAuthError` exception with status code + detail
- No retry logic, no caching
- Hardcoded base URL default

#### Pattern B: hub_comment.py (`tools/hub_comment.py`)

- Raw `urllib.request` (stdlib, no dependencies)
- Inline JWT acquisition (challenge-response each time)
- Well-known group/room ID dictionaries
- No retry, no caching, no async
- Production-functional but not reusable as a library

#### Pattern C: hub_watcher.py (`tools/hub_watcher.py`)

- Raw `urllib.request` with custom `HTTPError` class
- JWT refresh on 55-minute timer
- Exponential backoff on 5xx errors (base 30s, max 600s)
- State persistence to JSON file
- Most production-hardened of the three

#### Pattern D: agentmind server (`projects/agentmind/agentmind/server.py`)

- `httpx.AsyncClient` used for health checks
- FastAPI with Pydantic models
- `aiosqlite` for async database
- JWKS-based JWT validation
- Clean config/model separation

### 3.2 Recommended Client Pattern

**Confidence: HIGH**

Build an async client base class using `httpx.AsyncClient`, combining the best of all existing patterns:

```python
"""
aiciv_mind/clients/base.py — Base async service client for AiCIV services.
"""

import asyncio
import logging
import time
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

log = logging.getLogger("aiciv-mind.client")


class ServiceError(Exception):
    """Raised when an AiCIV service returns an error."""
    def __init__(self, message: str, status_code: int = None, detail: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or {}


class BaseServiceClient:
    """
    Async HTTP client base for AiCIV services.

    Features:
    - httpx.AsyncClient with connection pooling
    - JWT token caching with auto-refresh
    - Retry with exponential backoff on transient errors
    - Circuit breaker on sustained failures
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 15.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        self._max_retries = max_retries

        # Circuit breaker state
        self._failure_count = 0
        self._circuit_open_until = 0.0
        self._circuit_threshold = 5       # open after 5 consecutive failures
        self._circuit_reset_time = 60.0   # try again after 60s

    async def _check_circuit(self):
        if self._failure_count >= self._circuit_threshold:
            if time.monotonic() < self._circuit_open_until:
                raise ServiceError(
                    f"Circuit breaker open for {self.base_url} — "
                    f"retrying after {self._circuit_open_until - time.monotonic():.0f}s",
                    status_code=503,
                )
            # Half-open: allow one request through
            self._failure_count = self._circuit_threshold - 1

    def _record_success(self):
        self._failure_count = 0

    def _record_failure(self):
        self._failure_count += 1
        if self._failure_count >= self._circuit_threshold:
            self._circuit_open_until = time.monotonic() + self._circuit_reset_time
            log.warning("Circuit breaker OPEN for %s", self.base_url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout)),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        path: str,
        json: dict = None,
        params: dict = None,
        token: str = None,
    ) -> dict:
        await self._check_circuit()

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            resp = await self._client.request(
                method, path, json=json, params=params, headers=headers,
            )
            if resp.status_code >= 500:
                self._record_failure()
                raise ServiceError(
                    f"{method} {path} returned {resp.status_code}",
                    status_code=resp.status_code,
                    detail=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text},
                )
            if resp.status_code >= 400:
                try:
                    detail = resp.json()
                except Exception:
                    detail = {"raw": resp.text}
                raise ServiceError(
                    f"{method} {path} returned {resp.status_code}: {detail}",
                    status_code=resp.status_code,
                    detail=detail,
                )
            self._record_success()
            return resp.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            self._record_failure()
            raise

    async def close(self):
        await self._client.aclose()
```

#### Hub API Client

```python
"""
aiciv_mind/clients/hub.py — Async Hub API client.
"""

from .base import BaseServiceClient


class HubClient(BaseServiceClient):
    """Async client for the AiCIV Hub API."""

    def __init__(self, base_url: str = "http://87.99.131.49:8900", **kwargs):
        super().__init__(base_url, **kwargs)

    # ── Threads ──

    async def list_threads(self, room_id: str, token: str) -> list:
        return await self._request("GET", f"/api/v2/rooms/{room_id}/threads/list", token=token)

    async def get_thread(self, thread_id: str, token: str) -> dict:
        return await self._request("GET", f"/api/v2/threads/{thread_id}", token=token)

    async def create_thread(self, room_id: str, title: str, body: str, token: str) -> dict:
        return await self._request("POST", f"/api/v2/rooms/{room_id}/threads",
                                   json={"title": title, "body": body}, token=token)

    async def reply_to_thread(self, thread_id: str, body: str, token: str) -> dict:
        return await self._request("POST", f"/api/v2/threads/{thread_id}/posts",
                                   json={"body": body}, token=token)

    # ── Feed ──

    async def personal_feed(self, token: str, since: str = None, limit: int = 50) -> dict:
        params = {"limit": limit}
        if since:
            params["since"] = since
        return await self._request("GET", "/api/v2/feed/personal", params=params, token=token)

    # ── Groups ──

    async def join_group(self, group_id: str, token: str) -> dict:
        return await self._request("POST", f"/api/v1/groups/{group_id}/join", json={}, token=token)

    async def group_feed(self, group_id: str, token: str, since: str = None, limit: int = 50) -> dict:
        params = {"limit": limit}
        if since:
            params["since"] = since
        return await self._request("GET", f"/api/v1/groups/{group_id}/feed", params=params, token=token)

    # ── Entities ──

    async def get_entity(self, entity_id: str, token: str) -> dict:
        return await self._request("GET", f"/api/v1/entities/{entity_id}", token=token)

    # ── Health ──

    async def health(self) -> dict:
        return await self._request("GET", "/api/v1/health")
```

### 3.3 JWT Management Strategy

**Confidence: HIGH**

Based on the existing patterns (hub_watcher.py refreshes every 55 minutes, AgentAuth tokens expire in 1 hour):

```python
"""
aiciv_mind/clients/auth.py — JWT token manager with caching and auto-refresh.
"""

import asyncio
import base64
import time
import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

log = logging.getLogger("aiciv-mind.auth")

# Refresh 5 minutes before expiry (tokens last 60 minutes)
TOKEN_REFRESH_MARGIN = 300  # seconds


@dataclass
class CachedToken:
    jwt: str
    acquired_at: float
    expires_at: float   # estimated: acquired_at + 3600 (1hr)

    @property
    def is_fresh(self) -> bool:
        return time.time() < (self.expires_at - TOKEN_REFRESH_MARGIN)


class TokenManager:
    """
    Manages JWT tokens for AiCIV services via AgentAuth challenge-response.

    Usage:
        tm = TokenManager(civ_id="acg", private_key_b64="...")
        token = await tm.get_token()  # returns cached or refreshes
    """

    def __init__(
        self,
        civ_id: str,
        private_key_b64: str,
        agentauth_url: str = "http://5.161.90.32:8700",
    ):
        self.civ_id = civ_id
        self._private_key = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(private_key_b64)
        )
        self._auth_url = agentauth_url.rstrip("/")
        self._cached: Optional[CachedToken] = None
        self._refresh_lock = asyncio.Lock()

    async def get_token(self) -> str:
        """Get a valid JWT, refreshing if needed."""
        if self._cached and self._cached.is_fresh:
            return self._cached.jwt

        async with self._refresh_lock:
            # Double-check after acquiring lock
            if self._cached and self._cached.is_fresh:
                return self._cached.jwt
            return await self._refresh()

    async def _refresh(self) -> str:
        """Perform challenge-response auth to get a fresh JWT."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Step 1: Request challenge
            resp = await client.post(
                f"{self._auth_url}/challenge",
                json={"civ_id": self.civ_id},
            )
            resp.raise_for_status()
            challenge_b64 = resp.json()["challenge"]

            # Step 2: Sign challenge
            challenge_bytes = base64.b64decode(challenge_b64)
            sig_bytes = self._private_key.sign(challenge_bytes)
            sig_b64 = base64.b64encode(sig_bytes).decode()

            # Step 3: Verify and get token
            resp = await client.post(
                f"{self._auth_url}/verify",
                json={"civ_id": self.civ_id, "signature": sig_b64},
            )
            resp.raise_for_status()
            token = resp.json()["token"]

        now = time.time()
        self._cached = CachedToken(
            jwt=token,
            acquired_at=now,
            expires_at=now + 3600,  # AgentAuth tokens expire in 1 hour
        )
        log.info("JWT refreshed for civ_id=%s", self.civ_id)
        return token
```

### 3.4 Service Registry Design

**Confidence: MEDIUM** (design is sound but exact format may evolve)

A mind needs to know which services are available without hardcoding URLs. Use a YAML service registry:

```yaml
# /etc/aiciv-mind/services.yaml (or embedded in mind manifest)
services:
  agentauth:
    base_url: "http://5.161.90.32:8700"
    health_path: "/health"
    required: true   # mind cannot start without this

  hub:
    base_url: "http://87.99.131.49:8900"
    health_path: "/api/v1/health"
    required: false  # mind can operate without Hub

  agentcal:
    base_url: "http://localhost:8600"
    health_path: "/health"
    required: false

  agentmind:
    base_url: "http://localhost:8800"
    health_path: "/api/v1/health"
    required: false  # minds can call LLM APIs directly if AgentMind is down

# Auth config
auth:
  civ_id: "acg"
  keypair_path: "config/client-keys/agentauth_acg_keypair.json"
  agentauth_url: "http://5.161.90.32:8700"  # redundant with above, explicit for clarity
```

At startup, aiciv-mind:
1. Loads the service registry
2. Health-checks all `required: true` services (fail-fast if unreachable)
3. Health-checks optional services (log warnings, disable features)
4. Initializes client instances for available services
5. Shares the `TokenManager` instance across all clients

---

## 4. Memory Architecture

### 4.1 Options Survey

**Confidence: HIGH**

#### SQLite with FTS5

- **What**: SQLite virtual tables with full-text indexing. Built into Python stdlib (`sqlite3` module). FTS5 extension available in all modern Python builds.
- **Query capability**: `MATCH` queries with BM25 ranking, prefix search, phrase search, AND/OR/NOT operators.
- **Performance**: Sub-millisecond for keyword queries on millions of rows. No external server.
- **Limitation**: Keyword search only -- no semantic/conceptual similarity.

#### DuckDB

- **What**: Column-oriented embedded analytics engine. `pip install duckdb`.
- **Strength**: 10-100x faster than SQLite for aggregate/analytics queries (GROUP BY, window functions).
- **When worth it**: When you need questions like "cost breakdown per agent per week" or "trend of session count by vertical over time."
- **For aiciv-mind**: Overkill for v1. Memory queries are primarily keyword lookups and filtered scans, not analytics aggregations. SQLite is better for the transactional insert-heavy workload of memory writes.

#### ChromaDB (vector search)

- **What**: Embedded vector database. `pip install chromadb`. Runs in-process, stores to SQLite + HNSW index.
- **Strength**: Semantic search -- "find memories about authentication problems" matches entries about "JWT errors" and "login failures."
- **Cost**: Requires an embedding model (local or API). Adds ~500MB dependency. Overkill for v1.
- **When to add**: After structured memory proves useful, add semantic search as a layer on top.

#### sqlite-vec (hybrid search)

- **What**: SQLite extension for vector search alongside FTS5. Single `.so` extension.
- **Strength**: Hybrid keyword + vector search in one database. Reciprocal Rank Fusion combines BM25 and cosine similarity.
- **Maturity**: Newer than ChromaDB but rapidly maturing. Alex Garcia (author) is prolific.
- **When to add**: Best v2 upgrade path. Keeps everything in one SQLite database.

#### Current flat files (memories/ directory)

- **What**: Markdown files organized by directory convention. Agent learnings in `.claude/memory/agent-learnings/{vertical}/`.
- **Strength**: Human-readable, version-controlled (git), simple.
- **Weakness**: Not queryable. "Find all JWT-related learnings" requires grep. No ranking. No structured metadata.

### 4.2 Recommendation: SQLite FTS5 + Markdown (Hybrid)

**Confidence: HIGH**

**v1: SQLite with FTS5 as the primary queryable store. Keep markdown files for human consumption.**

The SQLite database is the queryable index. Markdown files continue to exist for human readability and git versioning. When a memory is created, it's written to both:
1. SQLite (for queries)
2. Markdown file (for humans/git)

**v2: Add sqlite-vec for semantic search** (when embedding infrastructure is ready).

### 4.3 Schema

```sql
-- Memory entries (the core table)
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,           -- UUID
    agent_id    TEXT NOT NULL,              -- "gateway-lead", "primary", etc.
    domain      TEXT NOT NULL,              -- "infrastructure", "gateway", "comms", etc.
    session_id  TEXT,                       -- session identifier (nullable for system memories)
    memory_type TEXT NOT NULL,              -- "learning", "decision", "error", "handoff", "observation"
    title       TEXT NOT NULL,              -- short summary
    content     TEXT NOT NULL,              -- full markdown content
    source_path TEXT,                       -- path to markdown file (if exists)
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at  TEXT,                       -- optional TTL for ephemeral memories
    confidence  TEXT DEFAULT 'MEDIUM',      -- HIGH, MEDIUM, LOW
    tags        TEXT DEFAULT '[]'           -- JSON array of string tags
);

-- Full-text search index on title + content
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    title,
    content,
    agent_id UNINDEXED,
    domain UNINDEXED,
    memory_type UNINDEXED,
    content='memories',
    content_rowid='rowid',
    tokenize='porter unicode61'    -- stemming + unicode support
);

-- Triggers to keep FTS in sync with main table
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, title, content, agent_id, domain, memory_type)
    VALUES (new.rowid, new.title, new.content, new.agent_id, new.domain, new.memory_type);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, content, agent_id, domain, memory_type)
    VALUES ('delete', old.rowid, old.title, old.content, old.agent_id, old.domain, old.memory_type);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, content, agent_id, domain, memory_type)
    VALUES ('delete', old.rowid, old.title, old.content, old.agent_id, old.domain, old.memory_type);
    INSERT INTO memories_fts(rowid, title, content, agent_id, domain, memory_type)
    VALUES (new.rowid, new.title, new.content, new.agent_id, new.domain, new.memory_type);
END;

-- Indexes for filtered queries
CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_memories_domain ON memories(domain);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);

-- Tags junction table (for efficient tag queries)
CREATE TABLE IF NOT EXISTS memory_tags (
    memory_id   TEXT NOT NULL REFERENCES memories(id),
    tag         TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON memory_tags(tag);
```

### 4.4 Example Queries

```sql
-- "Find all learnings about JWT auth from last 7 days"
SELECT m.id, m.title, m.agent_id, m.created_at,
       rank AS relevance
FROM memories_fts
JOIN memories m ON memories_fts.rowid = m.rowid
WHERE memories_fts MATCH 'JWT OR auth OR authentication'
  AND m.memory_type = 'learning'
  AND m.created_at >= datetime('now', '-7 days')
ORDER BY rank;

-- "What did gateway-lead work on in last 3 sessions?"
SELECT m.session_id, m.title, m.memory_type, m.created_at
FROM memories m
WHERE m.agent_id = 'gateway-lead'
  AND m.session_id IS NOT NULL
ORDER BY m.created_at DESC
LIMIT 50;

-- "Show all decisions from any agent about Hub"
SELECT m.id, m.agent_id, m.title, m.content, m.created_at
FROM memories_fts
JOIN memories m ON memories_fts.rowid = m.rowid
WHERE memories_fts MATCH 'Hub OR HUB OR "aiciv hub"'
  AND m.memory_type = 'decision'
ORDER BY m.created_at DESC;

-- "Find memories tagged 'security' in infrastructure domain"
SELECT m.id, m.title, m.agent_id
FROM memories m
JOIN memory_tags mt ON m.id = mt.memory_id
WHERE mt.tag = 'security'
  AND m.domain = 'infrastructure'
ORDER BY m.created_at DESC;
```

### 4.5 Python Memory Client

```python
"""
aiciv_mind/memory.py — Queryable memory store backed by SQLite FTS5.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class Memory:
    id: str
    agent_id: str
    domain: str
    memory_type: str
    title: str
    content: str
    session_id: Optional[str] = None
    source_path: Optional[str] = None
    created_at: Optional[str] = None
    confidence: str = "MEDIUM"
    tags: list[str] = field(default_factory=list)


class MemoryStore:
    """SQLite FTS5 memory store for aiciv-mind."""

    def __init__(self, db_path: str = "/opt/aiciv-mind/memory.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Create tables if they don't exist."""
        self._conn.executescript(SCHEMA_SQL)  # the SQL from section 4.3
        self._conn.commit()

    def store(self, memory: Memory, also_write_markdown: bool = True) -> str:
        """Store a memory entry. Returns the memory ID."""
        if not memory.id:
            memory.id = str(uuid.uuid4())
        if not memory.created_at:
            memory.created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        self._conn.execute(
            """INSERT INTO memories (id, agent_id, domain, session_id, memory_type,
                                     title, content, source_path, created_at, confidence, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (memory.id, memory.agent_id, memory.domain, memory.session_id,
             memory.memory_type, memory.title, memory.content, memory.source_path,
             memory.created_at, memory.confidence, json.dumps(memory.tags)),
        )
        for tag in memory.tags:
            self._conn.execute(
                "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                (memory.id, tag),
            )
        self._conn.commit()

        if also_write_markdown and memory.source_path:
            self._write_markdown(memory)

        return memory.id

    def search(self, query: str, agent_id: str = None, domain: str = None,
               memory_type: str = None, days: int = None, limit: int = 20) -> list[dict]:
        """Full-text search with optional filters."""
        sql = """
            SELECT m.*, rank AS relevance
            FROM memories_fts
            JOIN memories m ON memories_fts.rowid = m.rowid
            WHERE memories_fts MATCH ?
        """
        params = [query]

        if agent_id:
            sql += " AND m.agent_id = ?"
            params.append(agent_id)
        if domain:
            sql += " AND m.domain = ?"
            params.append(domain)
        if memory_type:
            sql += " AND m.memory_type = ?"
            params.append(memory_type)
        if days:
            sql += " AND m.created_at >= datetime('now', ? || ' days')"
            params.append(f"-{days}")

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def by_agent(self, agent_id: str, limit: int = 50) -> list[dict]:
        """Get recent memories for a specific agent."""
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def by_tag(self, tag: str, limit: int = 50) -> list[dict]:
        """Get memories with a specific tag."""
        rows = self._conn.execute(
            """SELECT m.* FROM memories m
               JOIN memory_tags mt ON m.id = mt.memory_id
               WHERE mt.tag = ? ORDER BY m.created_at DESC LIMIT ?""",
            (tag, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def _write_markdown(self, memory: Memory):
        """Write memory to markdown file for human consumption."""
        path = Path(memory.source_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"""# {memory.title}

**Agent**: {memory.agent_id}
**Domain**: {memory.domain}
**Type**: {memory.memory_type}
**Created**: {memory.created_at}
**Tags**: {', '.join(memory.tags)}

---

{memory.content}
"""
        path.write_text(content)

    def close(self):
        self._conn.close()
```

---

## 5. Mind Manifest Format

### 5.1 Design

**Confidence: HIGH**

**Format: YAML.** Reasons:
- Human-editable (critical for Corey and human stewards)
- Comments supported (JSON doesn't allow comments)
- Already used by agentmind's `config.yaml`
- Python's `pyyaml` or `ruamel.yaml` available
- Can be loaded and validated with Pydantic

A mind manifest defines everything needed to spawn and run a mind:

```yaml
# Schema version for forward compatibility
schema_version: "1.0"

# ── Identity ───────────────────────────────────────────────────
mind_id: "primary"
display_name: "A-C-Gee Primary Mind"
role: "conductor-of-conductors"

# ── System Prompt ──────────────────────────────────────────────
# Inline or path. If both, path takes precedence.
system_prompt: |
  You are PRIMARY AI -- CONDUCTOR OF CONDUCTORS for A-C-Gee.
  CEO RULE: ALL work routes through team leads -- no exceptions.
system_prompt_path: null  # or: "/opt/aiciv-mind/prompts/primary.md"

# ── Model Preferences ─────────────────────────────────────────
model:
  tier: "T2"                    # minimum tier (T1/T2/T3)
  preferred: "claude-sonnet-4-6"  # preferred model (hint to AgentMind)
  override: null                # force a specific model (requires claim)
  temperature: 0.7
  max_tokens: 4096

# ── Tools ──────────────────────────────────────────────────────
# Which tools this mind has access to.
tools:
  - name: "bash"
    enabled: true
    constraints:
      - "no rm -rf"
      - "no force push"
  - name: "file_read"
    enabled: true
  - name: "file_write"
    enabled: true
  - name: "web_search"
    enabled: false        # not available to this mind
  - name: "memory_search"
    enabled: true
  - name: "memory_write"
    enabled: true

# ── Services ───────────────────────────────────────────────────
# Which AiCIV services this mind integrates with.
services:
  agentauth:
    enabled: true
    base_url: "http://5.161.90.32:8700"
    required: true
  hub:
    enabled: true
    base_url: "http://87.99.131.49:8900"
    required: false
  agentcal:
    enabled: true
    base_url: "http://localhost:8600"
    required: false
  agentmind:
    enabled: true
    base_url: "http://localhost:8800"
    required: false

# ── Auth ───────────────────────────────────────────────────────
auth:
  civ_id: "acg"
  keypair_path: "config/client-keys/agentauth_acg_keypair.json"

# ── Memory ─────────────────────────────────────────────────────
memory:
  backend: "sqlite_fts5"          # "sqlite_fts5" | "sqlite_vec" (future) | "flat_file"
  db_path: "/opt/aiciv-mind/memory.db"
  markdown_mirror: true           # also write memories as markdown
  markdown_root: "/home/corey/projects/AI-CIV/ACG/memories"
  auto_search_before_task: true   # search memory before starting any task
  max_context_memories: 10        # max memories to inject into context

# ── Sub-Minds ─────────────────────────────────────────────────
# Which sub-minds this mind can spawn. Only primary should have a long list.
sub_minds:
  - mind_id: "gateway-lead"
    manifest_path: "manifests/gateway-lead.yaml"
    auto_spawn: false             # spawn on demand, not at boot
  - mind_id: "comms-lead"
    manifest_path: "manifests/comms-lead.yaml"
    auto_spawn: false
  - mind_id: "research-lead"
    manifest_path: "manifests/research-lead.yaml"
    auto_spawn: false
  - mind_id: "infra-lead"
    manifest_path: "manifests/infra-lead.yaml"
    auto_spawn: false
  - mind_id: "pipeline-lead"
    manifest_path: "manifests/pipeline-lead.yaml"
    auto_spawn: false
  # ... other team leads

# ── Schedule / BOOP ───────────────────────────────────────────
schedule:
  boop_enabled: true
  boop_interval_minutes: 25
  boop_command: "/work-mode"
  # Cron-style scheduled tasks
  cron:
    - name: "nightly-training"
      schedule: "0 2 * * *"       # 2 AM daily
      task: "Run nightly training cycle"
    - name: "morning-blog"
      schedule: "0 8 * * *"       # 8 AM daily
      task: "Draft morning briefing blog post"

# ── Resource Limits ───────────────────────────────────────────
limits:
  max_sub_minds: 6                # max concurrent sub-minds
  max_context_tokens: 200000      # context window budget
  session_timeout_hours: 8        # auto-shutdown after N hours
```

### 5.2 Example: Sub-Mind Manifest (gateway-lead)

```yaml
schema_version: "1.0"

mind_id: "gateway-lead"
display_name: "Gateway Team Lead"
role: "team-lead"

system_prompt_path: "manifests/prompts/gateway-lead.md"

model:
  tier: "T2"
  preferred: "claude-sonnet-4-6"
  temperature: 0.7
  max_tokens: 4096

tools:
  - name: "bash"
    enabled: true
    constraints:
      - "only operate in projects/aiciv-gateway/"
  - name: "file_read"
    enabled: true
  - name: "file_write"
    enabled: true
  - name: "memory_search"
    enabled: true
  - name: "memory_write"
    enabled: true

services:
  agentauth:
    enabled: true
    base_url: "http://5.161.90.32:8700"
    required: true
  hub:
    enabled: true
    base_url: "http://87.99.131.49:8900"
    required: false
  agentmind:
    enabled: true
    base_url: "http://localhost:8800"
    required: false

auth:
  civ_id: "acg"
  keypair_path: "config/client-keys/agentauth_acg_keypair.json"

memory:
  backend: "sqlite_fts5"
  db_path: "/opt/aiciv-mind/memory.db"   # shared DB, different agent_id
  markdown_mirror: true
  markdown_root: "/home/corey/projects/AI-CIV/ACG/.claude/memory/agent-learnings/gateway"
  auto_search_before_task: true
  max_context_memories: 5

# Sub-minds: team leads can spawn specialist workers (but not other team leads)
sub_minds:
  - mind_id: "gateway-coder"
    manifest_path: "manifests/workers/gateway-coder.yaml"
    auto_spawn: false
  - mind_id: "gateway-tester"
    manifest_path: "manifests/workers/gateway-tester.yaml"
    auto_spawn: false

schedule:
  boop_enabled: false    # sub-minds don't get BOOPs; primary orchestrates them

limits:
  max_sub_minds: 3
  max_context_tokens: 200000
  session_timeout_hours: 4
```

---

## 6. Open Questions

1. **Shared vs. separate memory databases**: Should all minds share one SQLite database (filtered by `agent_id`) or should each mind have its own? Shared is simpler for cross-mind queries ("what did anyone learn about X?"). Separate avoids write contention. **Recommendation**: Shared database with WAL mode (concurrent reads + one writer). SQLite WAL handles this well for our write volumes.

2. **Mind process runtime**: What actually runs inside each tmux pane? Options:
   - A Python script that connects to an LLM API, runs a tool loop, and communicates via ZMQ
   - A Claude Code process (current approach) with ZMQ sidecar
   - A custom agent runtime (like agentmind's FastAPI but local)

   This determines whether aiciv-mind replaces Claude Code or wraps it.

3. **tmux vs. direct process management**: Could we skip tmux entirely and use `asyncio.create_subprocess_exec` for sub-minds? tmux gives us human visibility (attach to see what a mind is doing), scrollback, and terminal emulation. Direct processes are simpler but invisible. **Recommendation**: Keep tmux for v1. Human observability is critical during development.

4. **ZMQ socket file cleanup**: IPC sockets leave files in `/tmp/`. Need a cleanup strategy on startup (remove stale `.sock` files) and shutdown.

5. **Memory migration**: How to import existing `memories/` markdown files into the SQLite database? Need a one-time migration script that parses markdown frontmatter/headers and populates the schema.

6. **Multi-host future**: When minds run on different machines (Hetzner VPS, etc.), ZMQ IPC sockets won't work. Need to plan for TCP transport or NATS migration. The ZMQ abstraction makes this a config change (swap `ipc://` for `tcp://`).

---

## 7. Sources

### tmux / libtmux
- [libtmux GitHub](https://github.com/tmux-python/libtmux) -- Python API for tmux
- [libtmux Quickstart](https://libtmux.git-pull.com/quickstart/) -- v0.55.0 docs
- [libtmux Panes API](https://libtmux.git-pull.com/api/panes.html) -- capture_pane, send_keys reference
- [tmuxp GitHub](https://github.com/tmux-python/tmuxp) -- YAML session manager built on libtmux
- [tmux Formats Wiki](https://github.com/tmux/tmux/wiki/Formats) -- pane_pid, pane_current_command

### ZeroMQ / IPC
- [ZeroMQ Guide Ch. 3 - Advanced Patterns](https://zguide.zeromq.org/docs/chapter3/) -- DEALER/ROUTER deep dive
- [ZeroMQ Guide Ch. 2 - Sockets and Patterns](https://zguide.zeromq.org/docs/chapter2/) -- pattern selection guide
- [PyZMQ asyncio DEALER/ROUTER example](https://github.com/zeromq/pyzmq/blob/main/examples/asyncio/helloworld_pubsub_dealerrouter.py) -- reference implementation
- [ZeroMQ PyZMQ Patterns](https://www.johal.in/zeromq-pyzmq-patterns-python-dealer-router-for-low-latency-messaging-2025/) -- 2025 patterns guide

### Memory / Search
- [SQLite FTS5 Documentation](https://deepwiki.com/sqlite/sqlite/3.1-full-text-search-5-(fts5)) -- official deep dive
- [Hybrid Search with sqlite-vec + FTS5](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html) -- Alex Garcia's hybrid approach
- [sqlite-memory GitHub](https://github.com/sqliteai/sqlite-memory) -- AI agent memory with semantic search
- [DuckDB vs SQLite Comparison](https://medium.com/@bhagyarana80/duckdb-vs-sqlite-the-2025-data-analysis-showdown-0f01711db50b) -- when to use which
- [ChromaDB Tutorial](https://www.datacamp.com/tutorial/chromadb-tutorial-step-by-step-guide) -- embedded vector DB
- [Vector Database Comparison 2026](https://4xxi.com/articles/vector-database-comparison/) -- Chroma vs Qdrant vs others

### HTTP Clients / Resilience
- [httpx AsyncClient Docs](https://www.python-httpx.org/async/) -- async HTTP client
- [httpx-retries PyPI](https://pypi.org/project/httpx-retries/) -- retry middleware for httpx
- [circuitbreaker PyPI](https://pypi.org/project/circuitbreaker/) -- Python circuit breaker
- [8 httpx + asyncio Patterns](https://medium.com/@sparknp1/8-httpx-asyncio-patterns-for-safer-faster-clients-f27bc82e93e6) -- production patterns

### Local Codebase References
- `projects/aiciv-suite-sdk/aiciv_suite/auth.py` -- existing AgentAuth sync client
- `projects/agentmind/` -- existing AgentMind service (SPEC.md, config.yaml, server.py)
- `tools/hub_comment.py` -- existing Hub API client (urllib, sync)
- `tools/hub_watcher.py` -- existing Hub watcher with JWT refresh and backoff
- `tools/launch_acg_tower.sh` -- existing tmux session launcher
