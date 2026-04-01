# src/aiciv_mind/ipc — ZMQ Inter-Mind Communication

ZeroMQ-based IPC between the primary mind and sub-minds. Pattern: ROUTER/DEALER.

## Architecture

```
┌──────────────────────────────────────────────────┐
│              PRIMARY MIND (main.py)               │
│                                                   │
│  PrimaryBus (ROUTER)                              │
│  bound to: ipc:///tmp/aiciv-mind-router.ipc       │
│                                                   │
│  bus.on(MsgType.RESULT, handle_result)            │
│  bus.on(MsgType.HEARTBEAT, handle_heartbeat)      │
│  await bus.send(MindMessage.task(...))            │
└──────────────────┬───────────────────────────────┘
                   │  ZMQ IPC socket
        ┌──────────┴──────────┐
        │                     │
┌───────▼──────┐    ┌─────────▼──────┐
│ research-lead │    │ memory-lead    │
│ SubMindBus   │    │ SubMindBus     │
│ (DEALER)     │    │ (DEALER)       │
│ identity=    │    │ identity=      │
│ "research-   │    │ "memory-lead"  │
│  lead"       │    │                │
└──────────────┘    └────────────────┘
```

## Message Format — MindMessage

All messages use a single JSON-serializable format:

```json
{
  "type": "task",
  "sender": "primary",
  "recipient": "research-lead",
  "id": "uuid-string",
  "timestamp": 1712345678.0,
  "payload": {
    "task_id": "abc123",
    "objective": "Search for MiniMax M2.7 context window limits",
    "context": {}
  }
}
```

## Message Types (MsgType)

| Type | Direction | Purpose |
|------|-----------|---------|
| `task` | primary → sub-mind | Dispatch work to a sub-mind |
| `result` | sub-mind → primary | Return task output |
| `status` | sub-mind → primary | Progress update during long tasks |
| `heartbeat` | primary → sub-mind | Liveness check |
| `heartbeat_ack` | sub-mind → primary | Liveness response |
| `shutdown` | primary → sub-mind | Request graceful shutdown |
| `shutdown_ack` | sub-mind → primary | Confirm shutdown |
| `log` | sub-mind → primary | Forward log entry |

## Wire Envelope

ZMQ ROUTER/DEALER imposes a specific frame format:

**ROUTER sends to DEALER:**
```
[identity_bytes, b"", json_bytes]
```
The ROUTER prepends the DEALER's identity so messages arrive correctly.

**DEALER sends to ROUTER:**
```
[b"", json_bytes]
```
The empty delimiter is required by DEALER/ROUTER protocol. The ROUTER sees `[identity, "", json_bytes]` because ZMQ automatically prepends the sender identity.

## PrimaryBus (primary_bus.py)

Binds the ROUTER socket. The primary mind creates one PrimaryBus per session.

```python
bus = PrimaryBus()
bus.bind()                                    # bind to ipc:///tmp/aiciv-mind-router.ipc
bus.on(MsgType.RESULT, async_handler)         # register message handlers
bus.start_recv()                              # start background recv loop

msg = MindMessage.task("primary", "research-lead", task_id, objective)
await bus.send(msg)                           # route to research-lead by ZMQ identity

bus.close()                                   # shutdown recv loop + close socket
```

**Key detail:** `send(msg)` routes by `msg.recipient` — this must match the sub-mind's ZMQ identity (which is always the sub-mind's `mind_id`).

## SubMindBus (submind_bus.py)

Each sub-mind creates one SubMindBus. The DEALER sets its ZMQ IDENTITY to `mind_id` before connecting — this is how the ROUTER knows who's talking.

```python
bus = SubMindBus("research-lead")
bus.connect()                                  # connect to primary's ROUTER
bus.on(MsgType.TASK, async_handle_task)        # register task handler
bus.on(MsgType.SHUTDOWN, async_handle_shutdown)
bus.start_recv()                               # start background recv loop

reply = MindMessage.result("research-lead", "primary", task_id, "Found: ...")
await bus.send(reply)                          # send result back to primary

bus.close()
```

## Message Factories

`MindMessage` provides class methods for each type:

```python
MindMessage.task(sender, recipient, task_id, objective, context=None)
MindMessage.result(sender, recipient, task_id, result, success=True, error=None)
MindMessage.shutdown(sender, recipient, reason="orchestrator_request")
MindMessage.shutdown_ack(sender, recipient, mind_id)
MindMessage.heartbeat(sender, recipient)
MindMessage.heartbeat_ack(sender, recipient)
MindMessage.status(sender, recipient, task_id, progress, pct=None)
MindMessage.log(sender, recipient, level, message)
```

## IPC Flow: spawn_submind → send_to_submind

1. `spawn_submind("research-lead", "manifests/team-leads/research-lead.yaml")`
   - `SubMindSpawner.spawn()` creates tmux window
   - `run_submind.py` starts in that window
   - Sub-mind creates its own `SubMindBus("research-lead")`, connects to primary's ROUTER

2. `send_to_submind("research-lead", "What is M2.7's context window?")`
   - Creates a `MindMessage.task(...)` with a task_id UUID
   - Calls `await bus.send(msg)` — routes to research-lead by identity
   - Awaits a RESULT message with matching task_id (up to timeout_seconds)
   - Returns the result text

## Known Limitation

Sub-minds launched by `run_submind.py` do NOT receive a PrimaryBus or SubMindSpawner. Sub-minds cannot spawn their own sub-minds. The true team lead hierarchy (research-lead spawning research-web, research-memory, research-code) requires extending `run_submind.py` to instantiate and pass these objects. This is the Build 7 candidate.
