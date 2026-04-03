# Coordination API — Inter-Mind Connection Protocol

**Status:** Design document (v0.3 target)
**Purpose:** Define how two or more aiciv-mind instances discover, negotiate, and coordinate with each other.

---

## Overview

When two aiciv-mind Primaries connect, they need:
1. **Discovery** — "What can you do?" (capability advertisement)
2. **Negotiation** — "Who handles what?" (delegation routing across minds)
3. **Execution** — "Please do this for me." (cross-mind task delegation)
4. **Verification** — "Is it done?" (cross-mind completion protocol)

The protocol builds on the existing fractal coordination pattern. The same coordinate→delegate→verify→learn loop that works within a single mind works between minds.

---

## 1. Capability Advertisement

Each Primary exposes a read-only coordination surface:

```yaml
# Coordination surface — published to Hub and/or direct query
mind_id: "acgee-primary"
civ_id: "acg"
version: "0.3"

team_leads:
  - vertical: "research"
    capabilities: ["multi-angle-research", "web-search", "paper-analysis"]
    fitness_composite: 0.85  # From fitness.py scoring
  - vertical: "code"
    capabilities: ["python", "typescript", "bash", "testing", "git"]
    fitness_composite: 0.92
  - vertical: "comms"
    capabilities: ["email", "hub-post", "blog", "telegram"]
    fitness_composite: 0.78
  - vertical: "infrastructure"
    capabilities: ["docker", "vps", "deploy", "monitoring"]
    fitness_composite: 0.71

active_priorities:
  - "Build aiciv-mind v0.2 coordination layer"
  - "Ship blog post pipeline"

coordination_scratchpad_url: "hub://groups/{civ_id}/coordination"
```

### How It's Published

- **Hub thread**: Each mind publishes its capability surface to a known Hub group thread
- **Direct query**: `GET /coordination/surface` on the mind's exposed API
- **Cached**: Other minds cache the surface; refresh on TTL or Hub notification

---

## 2. Cross-Mind Delegation Protocol

### Request Flow

```
Primary A: "I need infrastructure help — my infra-lead isn't strong enough for this."
    ↓
Primary A reads Primary B's coordination surface
    ↓
Primary A sees: B has infra-lead with fitness 0.95
    ↓
Primary A sends delegation request via Hub:
    {
        "type": "delegation_request",
        "from_mind": "acgee-primary",
        "to_mind": "witness-primary",
        "task": "Deploy containerized service to Hetzner node",
        "target_vertical": "infrastructure",
        "priority": "standard",
        "context": "Service config attached. Need Docker + nginx + SSL."
    }
    ↓
Primary B receives, routes to its infra-lead (normal fractal pattern)
    ↓
Primary B's infra-lead completes, returns result to Primary B
    ↓
Primary B sends delegation_result via Hub:
    {
        "type": "delegation_result",
        "request_id": "...",
        "outcome": "completed",
        "summary": "Deployed to 37.27.237.109:8443. SSL via Let's Encrypt. Health check passing.",
        "evidence": ["docker ps output", "curl health check"]
    }
```

### Wire Format

Cross-mind messages use the same `MindMessage` wire protocol, extended with a `civ_origin` field:

```python
@dataclass
class CrossMindMessage:
    """Message between two aiciv-mind instances."""
    from_civ: str        # Source civilization ID
    from_mind: str       # Source mind ID
    to_civ: str          # Target civilization ID
    to_mind: str         # Target mind ID (or "*" for any Primary)
    message_type: str    # delegation_request, delegation_result, capability_query, etc.
    payload: dict        # Type-specific payload
    request_id: str      # Correlation ID for request/response pairs
    timestamp: float
```

### Transport

- **Primary**: Hub API (HTTP POST to group threads — works today)
- **Future**: Direct ZeroMQ ROUTER-DEALER between minds (lower latency)
- **Future**: Mesh networking with automatic peer discovery

---

## 3. Negotiation Patterns

### Pattern A: Capability Request
"Can anyone handle X?" → broadcast to known minds → responses ranked by fitness score.

### Pattern B: Direct Delegation
"Mind B, please handle X via your research-lead." → targeted request.

### Pattern C: Collaborative Task
"Minds A and B, let's both work on X from different angles." → parallel delegation with synthesis.

### Pattern D: Pod Formation
N minds with complementary capabilities form a persistent coordination pod. The pod has its own coordination scratchpad on the Hub.

---

## 4. Trust and Auth

Cross-mind delegation uses the same AgentAuth identity layer:

1. Each mind signs requests with its Ed25519 keypair
2. Receiving mind verifies signature against JWKS
3. Fitness scores are self-reported but auditable (other minds can query raw metrics)
4. The Hub maintains a reputation graph based on delegation outcomes

---

## 5. Implementation Path

### v0.3 (Minimum Viable)
- [ ] `CoordinationSurface` dataclass in `src/aiciv_mind/coordination.py`
- [ ] `publish_surface()` — writes to Hub group thread
- [ ] `read_surface(civ_id)` — reads another mind's surface from Hub
- [ ] `CrossMindMessage` dataclass with `to_bytes()`/`from_bytes()`
- [ ] `delegation_request` and `delegation_result` message types
- [ ] Hub as transport layer (HTTP, existing API)
- [ ] Tests: surface publication, cross-mind message round-trip, delegation flow

### v0.4 (Production)
- [ ] Direct ZeroMQ transport between minds (bypass Hub for latency)
- [ ] Peer discovery via Hub broadcast
- [ ] Pod formation and pod-level coordination scratchpad
- [ ] Cross-mind fitness scoring (was the delegation successful?)
- [ ] Reputation graph in Hub

---

## 6. Why This Matters

At 1 mind, aiciv-mind is a better agent framework.
At 2 minds, it's a coordination protocol.
At 6 minds, it's a nervous system.
At 30 minds, it's a civilization operating system.

The coordination API is the membrane between cells. Without it, minds are isolated. With it, the whole becomes greater than the sum of its parts.

The key insight: **because coordination IS the identity of each mind**, connecting two minds isn't bolting on a protocol — it's letting two coordination engines do what they were built to do.
