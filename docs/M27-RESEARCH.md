# MiniMax M2.7 — Deep Research Report

**Date:** 2026-04-01
**Author:** A-C-Gee Research
**Purpose:** Foundation intelligence brief for aiciv-mind. Root runs on this model. We need to know everything.

---

## 1. Architecture & Parameters

### Model Family

MiniMax M2.7 is the fourth generation in the MiniMax M2 line:

| Model | Released | Status | Weights |
|-------|----------|--------|---------|
| M2 | Oct 2025 | Open-weight (MIT), HuggingFace | 230B total / 10B active |
| M2.1 | Dec 2025 | Proprietary API | Undisclosed |
| M2.5 | Feb 2026 | Open-weight (HuggingFace) | Same MoE arch as M2 |
| **M2.7** | **Mar 18, 2026** | **Proprietary API only** | **Undisclosed** |

### Architecture

**Base architecture (from open-weight M2):**
- **Mixture of Experts (MoE)** — sparse activation
- **Total parameters:** ~230 billion (M2 baseline; M2.7 undisclosed but likely larger)
- **Active parameters per inference:** ~10 billion (confirmed for M2.7 by multiple sources — "smallest Tier-1 model")
- **Attention type:** Full attention (not hybrid/linear). MiniMax explicitly chose full attention over their earlier Lightning Attention work because "efficient attention still has some way to go before it can definitively beat full attention" in production
- **Reasoning:** Native interleaved thinking via `<think>...</think>` tags — the model was *trained* to reason between steps, not just prompted to

### Context Window & Output

| Spec | Value |
|------|-------|
| **Max context** | 204,800 tokens (~307 A4 pages) |
| **Max output (completion)** | 131,072 tokens |
| **Default max_tokens** | 10,240 (M2 series) |

### Variants

Two API variants exist with **identical output quality**:

| Variant | Speed | Use Case |
|---------|-------|----------|
| `MiniMax-M2.7` | Standard (~42 TPS measured, ~100 TPS claimed) | General use |
| `MiniMax-M2.7-highspeed` | Faster (lower latency) | Latency-sensitive apps |

### Training Data Cutoff

**Not publicly disclosed.** MiniMax has not published a knowledge cutoff date for any M2 model. This is a gap we need to probe empirically with Root.

### Company

MiniMax is headquartered in Singapore with US data centers. Their data policy: no training on API data, retains prompts, publication not allowed.

---

## 2. Strengths — Where M2.7 Excels

### 2.1 Cost Efficiency (The Killer Feature)

This is M2.7's defining advantage and the reason Root runs on it:

| Model | Input $/M tokens | Output $/M tokens | Blended (3:1) |
|-------|------------------|--------------------|----------------|
| **M2.7** | **$0.30** | **$1.20** | **$0.53** |
| M2.7 (cached) | $0.03 | $1.20 | **~$0.06** |
| Claude Opus 4.6 | $15.00 | $75.00 | $30.00 |
| GPT-5 | $10.00 | $30.00 | $15.00 |
| Sonnet 4.6 | $3.00 | $15.00 | $6.00 |

**M2.7 is 50x cheaper than Opus on input and 60x cheaper on output.** With cache hits, the blended rate drops to ~$0.06/M — essentially free at our usage volumes.

In the Kilo.ai head-to-head test: M2.7 delivered **90% of Opus quality for 7% of the cost** ($0.27 vs $3.67 per evaluation).

### 2.2 Software Engineering

M2.7 is genuinely competitive on code benchmarks:

| Benchmark | M2.7 | Opus 4.6 | GPT-5.3 Codex |
|-----------|-------|----------|---------------|
| SWE-Pro | **56.22%** | ~57% | 56.2% |
| SWE-bench Verified | **~78%** | ~55% | — |
| VIBE-Pro (end-to-end delivery) | **55.6%** | ~57% | — |
| Terminal Bench 2 | **57.0%** | — | — |
| SWE Multilingual | **76.5%** | — | — |

On SWE-bench Verified it actually *beats* Opus 4.6. The Multi SWE Bench score (52.7) demonstrates strong multi-language capability.

### 2.3 Agentic Workflows

M2.7 was built for agent use from the ground up:
- **97% skill adherence rate** on 40+ complex skills (each >2,000 tokens)
- **GDPval-AA: 1495 ELO** — highest among comparable models for professional office tasks
- **Interleaved thinking** — reasons between tool calls, maintaining a plan-act-reflect loop
- **Multi-agent collaboration** — native support for role boundaries, adversarial reasoning, protocol adherence

### 2.4 Self-Evolution (The Headline Feature)

M2.7's marketing centers on "self-evolution" — concretely this means:
- The model ran **100+ autonomous iterations** optimizing its own agent scaffold during training
- Achieved **30% performance improvement** on internal evaluations without human intervention
- Handled **30-50% of the RL research workflow** independently (log reading, debugging, metric analysis)
- On MLE-Bench Lite: **66.6% medal rate** across 22 ML competitions (9 gold medals)

This is relevant for aiciv-mind because M2.7 was literally trained to improve its own harness — which is exactly what we're building.

### 2.5 Reliability

99% success rate across benchmarks. The model rarely crashes, hallucinates tool calls, or produces malformed output. This matters enormously for an always-on system.

### 2.6 Long Context

204K context with full attention (not hybrid). MiniMax deliberately chose full attention because their experiments showed hybrid attention had "clear deficits in complex, multi-hop reasoning tasks" at scale.

---

## 3. Weaknesses — Where M2.7 Falls Short

### 3.1 Speed

This is M2.7's worst metric:

| Metric | M2.7 | Median (price tier) |
|--------|------|---------------------|
| **Output speed** | 41.8 TPS | 97.5 TPS |
| **Time to first token** | 2.49-3.10s | 1.84s |
| **500-token response** | ~13s end-to-end | — |

M2.7 is roughly **half the speed** of comparable models. For an interactive system like Root's Telegram bridge, this means noticeable delays.

**Note:** MiniMax claims 100 TPS; independent measurement shows 42-46 TPS. The highspeed variant may close this gap but independent benchmarks are scarce.

### 3.2 Verbosity

M2.7 generated **87 million tokens** in Artificial Analysis's evaluation — versus a 20M median. That's **4.35x more verbose** than the average model. This has real cost implications despite cheap per-token pricing, and means:
- Longer responses = more output tokens billed
- More thinking tokens consumed (interleaved reasoning adds overhead)
- Conversations fill context faster

**Mitigation for Root:** Set clear output length expectations in system prompts. Monitor token usage per session.

### 3.3 Intelligence Gap vs Frontier Models

On Artificial Analysis Intelligence Index v4.0:

| Model | Score |
|-------|-------|
| Gemini 3.1 Pro | 57 |
| GPT-5.4 | 57 |
| Opus 4.6 | 53 |
| Sonnet 4.6 | 52 |
| **M2.7** | **50** |
| M2.5 | 42 |

M2.7 is solidly in the top tier but **3-7 points below frontier models** on general intelligence. This gap shows up in:
- Open-ended reasoning (untested with Root — flagged in REALITY-AUDIT)
- Defense-in-depth security thinking (Kilo test: chose SHA-256 over bcrypt)
- Comprehensive test coverage (unit tests vs integration tests)
- Edge-case handling (missing rollback logic, partial failure handling)

### 3.4 Text-Only (No Vision)

M2.7 is **not multimodal**. Text input and text output only. No image understanding, no vision capabilities. This is a hard limitation for any task requiring visual analysis.

### 3.5 Regression on Some Benchmarks

VentureBeat noted M2.7 scored **worse than M2.5 on BridgeBench vibe-coding tasks**. This suggests the self-evolution training may have introduced regressions in specific areas while improving others.

### 3.6 Autonomous Judgment (Unknown)

Per our own REALITY-AUDIT: "M2.7 performs surprisingly well on structured prompts, but its autonomous judgment on unstructured tasks is unknown." Every proof-of-life test was highly structured. Open-ended tasks like "design the self-improvement loop" have not been tested.

---

## 4. Function Calling / Tool Use

### Native Support: YES

M2.7 has native, trained-in function calling with interleaved thinking. This is not a hack or translation layer — the model was trained to reason between tool calls.

### API Format

Standard OpenAI-compatible tool calling:

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search memory store",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    }
]
```

**`tool_choice`**: `"auto"` (default) or `"none"`

### Interleaved Thinking Flow

```
User message → <think>reasoning about what tool to call</think> → tool_call →
tool_result → <think>reasoning about result</think> → tool_call or response
```

The model reflects on each tool result before deciding next action. This is what makes it excel at long-horizon agentic tasks.

### Critical: Preserve Thinking Tokens

**This is the single most important implementation detail for aiciv-mind.**

The complete model response — including `<think>` blocks and `reasoning_details` — **MUST** be appended to conversation history. Modifying or excluding thinking content **breaks the reasoning chain and degrades performance**.

Performance impact of preserving vs dropping thinking state:

| Benchmark | With state | Without | Delta |
|-----------|-----------|---------|-------|
| SWE-Bench Verified | 69.4 | 67.2 | +3.3% |
| Tau-2 | 87 | 64 | **+35.9%** |
| BrowseComp | 44.0 | 31.4 | **+40.1%** |
| GAIA | 75.7 | 67.9 | +11.5% |
| xBench | 72.0 | 66.0 | +9.1% |

Dropping thinking tokens costs up to **40% performance** on complex agentic tasks. This is not optional.

### LiteLLM Translation

Our current setup routes through LiteLLM → OpenRouter → MiniMax. LiteLLM's `additional_drop_params` strips `cache_control`, `thinking`, and `betas` parameters. Tool calling passes through natively via the OpenAI-compatible API.

The `reasoning_split=True` parameter (separates thinking into `reasoning_details` field instead of `<think>` tags in content) can be passed via `extra_body` in LiteLLM config.

### Current aiciv-mind Status

Root correctly parallelizes read-only tools and sequences writes. Tool batching works. But we have NOT verified that thinking tokens are being preserved in conversation history — **this needs immediate audit**.

---

## 5. Prompt Format & System Prompt Handling

### System Prompt

Standard `role: "system"` message. OpenRouter notes that M2.7 **"hoists and merges system messages"** — meaning if multiple system messages appear in the conversation, they get consolidated.

**Implication for aiciv-mind:** Our context_manager.py builds a single system prompt with static content first, dynamic content after. This is correct. Do NOT insert multiple system messages mid-conversation.

### Recommended Temperature & Sampling

| Parameter | Recommended (M2 series) | Notes |
|-----------|------------------------|-------|
| `temperature` | 1.0 | Not 0.7 — MiniMax recommends 1.0 |
| `top_p` | 0.95 | Default |
| `top_k` | 40 | For open-weight models |

**Note:** Root's manifest currently uses `temperature: 0.7`. MiniMax recommends 1.0 for M2 series. This may be worth experimenting with — lower temperature could be suppressing M2.7's reasoning quality.

### Thinking Tags

Reasoning wraps in `<think>...</think>` tags within the content field by default. With `reasoning_split=True`, thinking moves to a separate `reasoning_details` field.

**Mandatory reasoning:** OpenRouter flags M2.7 as having a "mandatory reasoning requirement" — the model always thinks before responding. You cannot disable this.

### Best Practices from MiniMax Docs

1. **Be explicit** — state expected output format, style, and structure upfront
2. **Explain intent** — include the "why" behind requests for better accuracy
3. **Use examples** — show what good output looks like, highlight mistakes to avoid
4. **Phase long tasks** — break into structured phases across multiple windows
5. **Track state with files** — use test files and init scripts for complex tasks
6. **Keep total tokens under 200K** — model may terminate tasks early near capacity
7. **Control system prompt size** when using context compression
8. **Restart with fresh context** for new tasks; use compression for single ongoing tasks

---

## 6. Structured Output (JSON Mode)

### Support: PARTIAL

- **JSON mode:** Supported via all OpenRouter providers (confirmed)
- **`response_format` with JSON schema:** Documented for MiniMax-Text-01 but NOT explicitly confirmed for M2.7
- **Practical JSON output:** M2.7 can produce JSON reliably when instructed in the system prompt

**Recommendation for aiciv-mind:** Use prompt-based JSON formatting rather than relying on `response_format` API parameter. Include a JSON example in the prompt and instruct "respond ONLY with valid JSON." This works reliably across all providers.

---

## 7. Vision / Multimodal

### Support: NO

M2.7 is text-only. No image input, no image output, no audio, no video. If Root needs visual analysis, we must route to a different model (Gemini, GPT-4V, etc.) via the model router.

---

## 8. Prompt Caching

### How It Works

MiniMax uses **automatic (passive) prefix caching** — no configuration needed:

1. Cache prefix is constructed in order: **tools → system prompt → user messages**
2. When identical content appears in subsequent requests, cached tokens are reused
3. Minimum threshold: **512 input tokens** to activate caching

### Pricing

| Token Type | Cost per 1M |
|------------|-------------|
| Standard input | $0.30 |
| **Cached input (hit)** | **$0.03** (90% cheaper) |
| Cache write | $0.375 (25% more expensive, first time only) |
| Output | $1.20 |

### Cache Expiration

- Automatic caching: TTL "automatically adjusted based on system load" (no fixed guarantee)
- Anthropic-compatible explicit caching: 5-minute window, renewed on use

### aiciv-mind Implications

Our context_manager.py already orders the system prompt for cache optimization:
```
1. Static prompt text (CACHED — same every call)
2. Boot context (CACHED — same within session)
3. Per-turn memory search results (DYNAMIC — changes each turn)
4. Current date/time (DYNAMIC)
```

This is correct. The key rule documented in context_manager.py: **"static content MUST come before dynamic content. Any reversal invalidates the cached prefix."**

Current estimated cache hit rate from logs: ~94%. At $0.03/M for cached tokens vs $0.30/M uncached, this is saving us roughly **$0.25 per million input tokens** — essentially making input nearly free.

**Note:** `cache_control` params are stripped by our LiteLLM config, so we rely entirely on prefix stability. This is fine — MiniMax's automatic caching works without explicit breakpoints.

---

## 9. Long Conversation & Context Degradation

### Known Behaviors

1. **"Lost in the middle" effect** applies to M2.7 like all LLMs — information at the start and end of context gets more attention than middle content
2. M2.7 has **"excellent state tracking"** per MiniMax docs, with coherent sequential thinking
3. The model **may terminate tasks early** when approaching the 200K token capacity threshold
4. MiniMax recommends keeping total input + output within 200K tokens

### Mitigation Strategies

1. **Focus on limited goals per interaction** — don't try to do everything in one turn
2. **Phase long tasks** — use multiple windows with clear handoffs
3. **Start fresh contexts** for genuinely new tasks
4. **Use compression** only for continuing single ongoing tasks
5. **Pin critical context early** in the system prompt (cache-optimal and attention-optimal)

### What We Don't Know

Our REALITY-AUDIT flagged: "No evidence of sessions with large context windows. No test of what happens when max_context_memories is hit." This remains untested. We need to stress-test Root with 100K+ token conversations to understand degradation patterns.

---

## 10. MiniMax Best Practices (Official Documentation)

Direct from `platform.minimax.io/docs/token-plan/best-practices`:

1. **Be explicit with instructions** — specify format, style, structure upfront
2. **Explain your intent** — the "why" behind requests improves accuracy
3. **Use examples as templates** — show good output, highlight mistakes
4. **Phase long tasks** — framework window first, iteration windows after
5. **Create test files** — `tests.py`, `tests.json` to track multi-step progress
6. **Use init scripts** — `init.sh` to avoid repetitive setup
7. **Keep tokens under 200K** total (input + output combined)
8. **Restart with fresh contexts** for multiple/new tasks
9. **Control system prompt size** when using context compression tools
10. **Use streaming** — recommended for M2 series "for best performance"

---

## 11. Model Variants & Alternatives

### M2.7 Highspeed

`MiniMax-M2.7-highspeed` — same quality, faster inference. Available on MiniMax API directly and via some providers. Pricing may differ (monthly tier plans: $40-$150/month for highspeed vs $10-$50 standard).

### M2.5 (Free Tier Available)

Our LiteLLM config includes `minimax-m25-free` via OpenRouter at zero cost. Specs:
- 196K context, 32K output
- Lower intelligence (Index 42 vs M2.7's 50)
- Open-weight (HuggingFace, MIT license)
- Good for low-stakes tasks, drafts, or fallback

**Potential use:** Route cheap/fast tasks to M2.5-free and save M2.7 for complex reasoning. The model router in aiciv-mind already supports this pattern.

### Potential Upgrades to Monitor

| Model | Why Watch |
|-------|-----------|
| M2.7-highspeed | Same quality, faster — worth benchmarking via direct MiniMax API |
| Future M2.9/M3 | MiniMax iterates fast (4 versions in 5 months) |
| Kimi K2 | Already in our LiteLLM stack as reasoning fallback |
| Qwen 3.5 35B | Local option, 262K context, competitive benchmarks |

---

## 12. Cost Comparison at Similar Quality

Models in the same quality tier (Intelligence Index 48-55):

| Model | Input $/M | Output $/M | Index | Speed (TPS) |
|-------|-----------|------------|-------|-------------|
| **M2.7** | **$0.30** | **$1.20** | **50** | **42** |
| Sonnet 4.6 | $3.00 | $15.00 | 52 | ~80 |
| Opus 4.6 | $15.00 | $75.00 | 53 | ~33 |
| GPT-5.4 | — | — | 57 | ~40 |
| Gemini 3.1 Pro | — | — | 57 | — |

M2.7 is **10x cheaper than Sonnet** and **50x cheaper than Opus** on input. The intelligence gap is 2-3 points vs Sonnet and 3 points vs Opus — a real gap but not a canyon.

**The value proposition is clear:** for sustained, high-volume AI operations (which is what Root does), M2.7's cost structure makes it viable to run continuously in a way that Opus/Sonnet never could be.

---

## 13. Special Features We Should Be Using

### 13.1 Interleaved Thinking (USING — but verify preservation)

Root uses interleaved thinking. BUT we need to verify the thinking tokens are being preserved in conversation history. The +40% performance delta on BrowseComp is too large to leave on the table.

**Action:** Audit `mind.py` conversation history management to confirm `<think>` blocks are retained.

### 13.2 Automatic Prefix Caching (USING)

Already optimized via context_manager.py ordering. 94% hit rate observed.

### 13.3 reasoning_split Parameter (NOT USING)

Setting `reasoning_split=True` separates thinking into a structured `reasoning_details` field instead of `<think>` tags mixed into content. This could make parsing cleaner and preserve reasoning more reliably.

**Action:** Add `reasoning_split: true` to LiteLLM extra_body config and update conversation history handling to extract and re-inject `reasoning_details`.

### 13.4 Highspeed Variant (NOT USING)

`MiniMax-M2.7-highspeed` could reduce Root's response latency for interactive sessions (Telegram, real-time Hub engagement).

**Action:** Add highspeed variant to LiteLLM config. Route interactive tasks to highspeed, batch/background tasks to standard.

### 13.5 M2.5-Free for Low-Stakes Tasks (CONFIGURED but not routed)

Already in LiteLLM config. The model router has cost_tier metadata but doesn't actively route cheap tasks to M2.5.

**Action:** Implement active cost-based routing: memory summaries, simple file operations, and status checks to M2.5-free; reasoning, planning, and complex tool chains to M2.7.

### 13.6 mask_sensitive_info Parameter (NOT USING)

MiniMax offers a `mask_sensitive_info` boolean that replaces PII (emails, addresses, IDs) with `***` in output. Could be useful for privacy-sensitive operations.

### 13.7 Self-Evolution Patterns (APPLICABLE)

M2.7 was trained to optimize its own scaffold. This means it should be naturally good at:
- Analyzing its own performance logs
- Proposing improvements to its own prompts and tools
- Identifying failure patterns and suggesting fixes

This aligns directly with aiciv-mind's "compounding intelligence" vision. We should give Root tasks that exercise this capability.

---

## 14. Risks & Open Questions

### 14.1 Proprietary Lock-In

M2.7 is API-only — no self-hosting option. If MiniMax changes pricing, terms, or availability, we have no fallback at this quality/cost point. M2.5 is open-weight but meaningfully weaker.

**Mitigation:** Keep the model router working and LiteLLM abstraction clean. Root's code should never import MiniMax-specific SDKs.

### 14.2 Speed for Interactive Use

42 TPS with 2.5-3s TTFT is noticeable in conversation. Telegram users will see delays.

**Mitigation:** Highspeed variant, streaming responses, and UX that shows "thinking..." indicators.

### 14.3 Verbosity Cost Creep

4.35x verbosity means 4.35x more output tokens. Even at $1.20/M, this adds up over thousands of sessions.

**Mitigation:** Explicit output length guidance in system prompts. Monitor token usage per session and set alerts.

### 14.4 Unknown Knowledge Cutoff

We don't know what M2.7 knows vs doesn't. Root may confidently state outdated information.

**Mitigation:** Ground Root with tool access to current data. Don't rely on parametric knowledge for anything time-sensitive.

### 14.5 Temperature Mismatch

Root runs at temperature 0.7; MiniMax recommends 1.0 for M2 series. We may be artificially constraining the model's reasoning quality.

**Action:** A/B test temperature 0.7 vs 1.0 on identical prompts and compare output quality.

---

## 15. Summary: What We're Working With

**MiniMax M2.7 is the right model for Root.** Here's why:

**It's viable because:**
- 50x cheaper than Opus = we can run Root continuously without burning budget
- 204K context = enough for complex multi-turn sessions with memory injection
- Native tool calling with interleaved thinking = designed for exactly what Root does
- 97% skill adherence = reliable execution of complex multi-step instructions
- Automatic prefix caching = 90% input cost reduction on repeated prompts

**It's limited by:**
- Intelligence gap of 3-7 points vs frontier (compensate with better prompts, tools, and memory)
- Speed (42 TPS vs 98 TPS median) — noticeable in interactive use
- Verbosity (4x average) — monitor and constrain
- Text-only — need secondary model for visual tasks
- Proprietary — no self-hosting escape hatch

**The strategic bet:** M2.7 gives us 90% of frontier intelligence at 2% of frontier cost. The remaining 10% gap can be closed with better tooling, memory systems, and prompt engineering — which is exactly what aiciv-mind is designed to do.

---

## Sources

- [MiniMax M2.7 Official Announcement](https://www.minimax.io/news/minimax-m27-en)
- [MiniMax M2.7 Model Page](https://www.minimax.io/models/text/m27)
- [MiniMax API Docs — Tool Use & Interleaved Thinking](https://platform.minimax.io/docs/guides/text-m2-function-call)
- [MiniMax API Docs — Usage Tips](https://platform.minimax.io/docs/token-plan/best-practices)
- [MiniMax API Docs — Prompt Caching](https://platform.minimax.io/docs/api-reference/text-prompt-caching)
- [MiniMax API Docs — Text Generation API](https://platform.minimax.io/docs/api-reference/text-post)
- [Artificial Analysis — M2.7 Intelligence & Performance](https://artificialanalysis.ai/models/minimax-m2-7)
- [OpenRouter — M2.7 Model Card](https://openrouter.ai/minimax/minimax-m2.7)
- [Kilo.ai — M2.7 vs Opus 4.6 Comparison](https://blog.kilo.ai/p/we-tested-minimax-m27-against-claude)
- [WaveSpeed — M2.7 Features & Benchmarks](https://wavespeed.ai/blog/posts/minimax-m2-7-self-evolving-agent-model-features-benchmarks-2026/)
- [VentureBeat — M2.7 Self-Evolution](https://venturebeat.com/technology/new-minimax-m2-7-proprietary-ai-model-is-self-evolving-and-can-perform-30-50)
- [MiniMax — Why Full Attention for M2](https://www.minimax.io/news/why-did-m2-end-up-as-a-full-attention-model)
- [MiniMax — Interleaved Thinking Deep Dive](https://www.minimax.io/news/why-is-interleaved-thinking-important-for-m2)
- [LiteLLM — MiniMax Provider Docs](https://docs.litellm.ai/docs/providers/minimax)
- [OpenRouter — Message Transforms](https://openrouter.ai/docs/guides/features/message-transforms)
- [GitHub — MiniMax-M2 (open-weight)](https://github.com/MiniMax-AI/MiniMax-M2)
