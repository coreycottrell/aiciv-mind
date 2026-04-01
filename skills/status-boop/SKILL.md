---
skill_id: status-boop
domain: operations
version: 1.0
trigger: "when running a status check, health check, or hourly BOOP"
---
# Status BOOP Protocol

## Purpose
Hourly system health check. Quick, focused, 5 tool calls max.

## Steps

### 1. System Health (1 call)
- `system_health()` — check memory DB, services, git, disk

### 2. Email Check (1 call)
- `email_read(limit=5)` — scan for urgent messages
- If anything urgent: read the full message with `email_read(message_id=...)`

### 3. Scratchpad Read (1 call)
- `scratchpad_read()` — check today's notes for context

### 4. Write Summary (1 call)
- `scratchpad_write()` — append status summary:
  ```
  ## Status BOOP — [time]
  - System: [ok/issues]
  - Email: [summary]
  - Action needed: [yes/no + what]
  ```

### 5. Escalate if Needed (optional, 1 call)
- If Hub or AgentAuth is DOWN: `hub_post()` to operations room
- If urgent email: flag for Corey

## Anti-Patterns
- Do NOT explore the codebase during a status BOOP
- Do NOT start fixing things you find — note them and move on
- Do NOT exceed 5 tool calls
- Keep the entire BOOP under 30 seconds
