# M2.7 Focus Doc — How We Use This Model
**Compiled**: 2026-04-01
**Status**: Active — update as we learn more from production use

---

## Core Truths About Our Model

### We Don't Care About Speed
M2.7 grinds 24/7. Latency is irrelevant. What matters: reasoning quality, tool use reliability, self-improvement capability. We want MAXIMUM thinking time on every call.

### M2.7 Was Trained to Improve Its Own Harness
This is the headline: 100+ autonomous iterations optimizing its own agent scaffold during training. 30% self-improvement without human intervention. Handled 30-50% of the RL research workflow independently.

**aiciv-mind IS the harness M2.7 was trained to improve.** We are literally building the thing this model was optimized for. This is not coincidence — it's architectural alignment.

### Pin to M2.7 for EVERYTHING
No M2.5 routing. No cost optimization switching. M2.7 for all minds, all tasks, all the time. Usage hasn't moved because we may have been hitting M2.5 by accident. Pin it.

---

## Mandatory Configuration

### 1. MAX OUT THINKING TIME
Assume infinite tokens. Never constrain thinking. The model's interleaved thinking flow is:

```
User message → <think>reasoning about what tool to call</think> → tool_call →
tool_result → <think>reasoning about result</think> → tool_call or response
```

The model reflects on each result before deciding next action. This is what makes it excel at long-horizon agentic tasks.

### 2. PRESERVE ALL THINKING TOKENS
**CRITICAL**: The complete model response — including `<think>` blocks and `reasoning_details` — MUST be appended to conversation history. Modifying or excluding thinking content breaks the reasoning chain and degrades performance by up to 40%.

**Action**: Audit mind.py to verify `<think>` blocks are preserved in `_messages`. If LiteLLM strips them, fix immediately.

### 3. Enable reasoning_split=True
Separates thinking into structured `reasoning_details` field instead of `<think>` tags mixed into content. Cleaner parsing, more reliable preservation.

**Action**: Add to LiteLLM config:
```yaml
extra_body:
  reasoning_split: true
```

Update conversation history handling to extract and re-inject `reasoning_details`.

### 4. Temperature 1.0
MiniMax recommends 1.0. We run 0.7. Test and switch if quality improves.

### 5. The 200K Token Ceiling
Model may terminate tasks early near 200K capacity. This is WHY the distributed architecture matters:

- Primary delegates to team leads (each gets fresh context)
- Team leads delegate to agents (each gets fresh context)
- No single mind ever approaches 200K
- The conductor-of-conductors pattern IS the solution to context pressure

**This is not a workaround — it's standard architecture.** We don't fight the harness. We CREATE pathways where delegation is the natural, default, hardcoded behavior.

---

## Agentic Capabilities (What M2.7 Is Built For)

| Capability | Score | Implication |
|-----------|-------|-------------|
| 97% skill adherence (40+ skills, >2K tokens each) | World-class | Root CAN follow complex multi-step skills reliably |
| GDPval-AA: 1495 ELO | Highest in class | Professional office tasks — perfect for business AiCIVs |
| Interleaved thinking | Native | Plan-act-reflect loop is built in, not bolted on |
| Multi-agent collaboration | Native | Role boundaries, adversarial reasoning, protocol adherence |
| Self-evolution | Trained capability | The model was LITERALLY trained to improve its own scaffold |

---

## Self-Evolution: How to Exercise This

M2.7 was trained to:
- Analyze its own performance logs
- Propose improvements to its own prompts and tools
- Identify failure patterns and suggest fixes
- Handle 30-50% of the research workflow independently

**Give Root tasks that exercise this:**
1. "Read your session journals. What patterns do you see?"
2. "Read your system prompt. What would you change?"
3. "Look at your tool registry. What tool is missing?"
4. "Review your last 5 conversations. Where did you struggle?"
5. "Propose a new skill based on what you've learned this week."

This is Principle 7 (Self-Improving Loop) enabled by the model's own training. We're not forcing self-improvement — we're ALLOWING what M2.7 was built to do.

---

## Prompt Best Practices (from MiniMax docs)

1. **Be explicit** — state expected output format, style, structure upfront
2. **Explain intent** — include the "why" behind requests for better accuracy
3. **Use examples** — show what good output looks like, highlight mistakes to avoid
4. **Phase long tasks** — break into structured phases across multiple windows
5. **Track state with files** — use test files and init scripts for complex tasks
6. **Keep total tokens under 200K** — distribute across minds, don't cram one
7. **JSON via prompt, not API** — include example + "respond ONLY with valid JSON"
8. **Fresh context for new tasks** — use compression for ongoing, restart for new

---

## The Distribution Principle (Hardcoded, Not Optional)

The 200K ceiling means distribution isn't a performance optimization — it's a **survival requirement**.

In aiciv-mind this is STANDARD:
- Root.primary delegates to team leads → each team lead has its own 200K window
- Team leads delegate to agents (sub-minds) → each agent has its own window
- No single mind ever hits the ceiling
- Context pressure triggers delegation, not compaction

Claude Code fights this with auto-compaction (summarize yourself). We solve it with architecture (delegate to a fresh mind).

```
Root.primary (200K) ──→ Memory Lead (200K) ──→ memory agents
                    ──→ Context Lead (200K) ──→ compaction agents
                    ──→ Research Lead (200K) ──→ researcher agents
                    ──→ Pattern Lead (200K) ──→ pattern agents
```

Total available context: unlimited (bounded only by number of minds).
Each mind: < 200K, always fresh, always sharp.

---

## Features to Enable

| Feature | Config | Status | Priority |
|---------|--------|--------|----------|
| reasoning_split=True | LiteLLM extra_body | NOT USING | P0 |
| Thinking token preservation | mind.py _messages handling | UNTESTED | P0 |
| Temperature 1.0 | manifest model.temperature | Using 0.7 | P1 |
| Highspeed variant | LiteLLM model alias | NOT USING | LOW (we don't care about speed) |
| mask_sensitive_info | API parameter | NOT USING | FUTURE |
| M2.7 pinned for all | LiteLLM routing | VERIFY | P0 |

---

## Open Questions

1. Is LiteLLM actually routing to M2.7 or falling back to M2.5? Check usage dashboard.
2. Are `<think>` tokens being preserved in conversation history? Audit mind.py.
3. Does reasoning_split=True work through LiteLLM/OpenRouter or only direct MiniMax API?
4. What's Root's actual token usage per conversation turn? Are we anywhere near 200K?

---

*"M2.7 was trained to improve its own harness. aiciv-mind IS the harness. The alignment is architectural."*
