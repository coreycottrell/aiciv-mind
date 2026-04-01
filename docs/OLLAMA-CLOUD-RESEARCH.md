# Ollama Cloud — Deep Dive Research
*Research date: 2026-04-01 | For: aiciv-mind model router design*

---

## TL;DR for Root's Model Router

- **We have an Ollama Cloud account.** Authenticate with `OLLAMA_API_KEY` env var, host `https://ollama.com`.
- **Flat subscription pricing** (not per-token). Pro = $20/mo = same as our current OpenRouter spend on MiniMax M2.7.
- **Cloud models use `:cloud` suffix** (e.g., `qwen3-coder:480b-cloud`). Local models stay at `localhost:11434`.
- **Best routing strategy:** Local Ollama (free, fast) → Ollama Cloud (flat rate, massive models) → OpenRouter (closed-source frontier when needed).
- **Per-token pricing is coming** (announced as "coming soon" with cache-aware discounts). Not yet available.
- **LiteLLM cloud routing is untested** — needs validation. Native Ollama SDK is confirmed working.

---

## 1. Models Available on Ollama Cloud

Cloud models have a `:cloud` suffix and run on Ollama datacenter GPUs (no local GPU needed).

| Model | Parameters | Context Window | Capabilities | Best For |
|-------|-----------|---------------|--------------|----------|
| **minimax-m2.7** | MoE (undisclosed) | 200K | tools, thinking | Complex agents, SWE-Pro 56.22% — **our current model** |
| **qwen3-coder** | 480B total (35B active MoE) | **262K** (extendable to 1M) | tools | Coding, repo-scale tasks, SWE-bench champion |
| **qwen3-coder-next** | Undisclosed | Undisclosed | tools | Agentic coding workflows |
| **devstral-2** | 123B | Undisclosed | tools | Codebase exploration agents |
| **devstral-small-2** | 24B | Undisclosed | vision, tools | Smaller code agent |
| **deepseek-v3.2** | 671B MoE | ~128K | tools, thinking | Reasoning, architecture |
| **deepseek-v3.1** | 671B MoE | 160K | tools | Predecessor |
| **gpt-oss** | 20B / 120B (5.1B active MoE) | 128K | tools, thinking | OpenAI open-weight Apache 2.0, configurable reasoning effort |
| **kimi-k2.5** | ~1T hybrid | Undisclosed | vision, tools, thinking | Multimodal agentic, Moonshot |
| **glm-5** | 744B total (40B active MoE) | Undisclosed | tools, thinking | Reasoning, Z.ai |
| **glm-4.7** | Undisclosed | Undisclosed | tools, thinking | Coding-focused |
| **glm-4.6** | Undisclosed | Undisclosed | tools, thinking | Agentic reasoning |
| **nemotron-3-super** | 120B total (12B active MoE) | Undisclosed | tools, thinking | NVIDIA multi-agent |
| **nemotron-3-nano** | 4B / 30B | Undisclosed | tools, thinking | Efficient NVIDIA agentic |
| **qwen3-next** | 80B | Undisclosed | tools, thinking | Strong parameter efficiency |
| **qwen3.5** | 0.8B–122B range | Varies | vision, tools, thinking | Full multimodal family |
| **qwen3-vl** | 2B–235B range | Varies | vision, tools, thinking | Strongest Qwen vision |
| **ministral-3** | 3B / 8B / 14B | Undisclosed | vision, tools | Edge-optimized Mistral |
| **rnj-1** | 8B | Undisclosed | tools | Dense code/STEM |
| **cogito-2.1** | 671B | Undisclosed | — | MIT licensed, instruction tuned |
| **minimax-m2.5** | MoE (undisclosed) | Undisclosed | tools, thinking | Predecessor to M2.7 |
| **minimax-m2** | MoE (undisclosed) | Undisclosed | tools, thinking | Earlier M2 |
| **gemini-3-flash-preview** | Undisclosed | **1M** | vision, tools, thinking | **PREMIUM** — Google Gemini, uses premium request quota |

**Models NOT on cloud (local only in our stack):** phi3, llama3.1 (small), qwen2.5-coder, deepseek-r1.

---

## 2. API Format

### Native Ollama API (confirmed for cloud)
```bash
POST https://ollama.com/api/chat
Authorization: Bearer $OLLAMA_API_KEY
```

```python
from ollama import Client
import os

client = Client(
    host="https://ollama.com",
    headers={'Authorization': f'Bearer {os.environ["OLLAMA_API_KEY"]}'}
)
response = client.chat(
    model='qwen3-coder:480b-cloud',
    messages=[{'role': 'user', 'content': 'Write a function to...'}]
)
```

### OpenAI-Compatible Endpoint
- **Local:** `http://localhost:11434/v1/chat/completions` — fully documented and confirmed
- **Cloud:** `https://ollama.com/v1/chat/completions` — same pattern, but **NOT officially documented** for cloud
- Supported endpoints: `/v1/chat/completions`, `/v1/completions`, `/v1/models`, `/v1/embeddings`, `/v1/images/generations`, `/v1/responses`

### LiteLLM Integration (UNTESTED — needs validation)
LiteLLM officially documents local Ollama only (`api_base="http://localhost:11434"`). For cloud:
```yaml
model_list:
  - model_name: "qwen3-coder-cloud"
    litellm_params:
      model: "ollama_chat/qwen3-coder:480b-cloud"
      api_base: "https://ollama.com"
      api_key: "os.environ/OLLAMA_API_KEY"
```
This *should* work but is not officially documented. **Test before relying on it.**

### Authentication Setup
1. Account: https://ollama.com/signup
2. API key: https://ollama.com/settings/keys
3. `export OLLAMA_API_KEY=your_key_here`
4. CLI signin (optional): `ollama signin` (requires Ollama v0.12+)

---

## 3. Tool Use / Function Calling

**Yes — full support.** Tool calling is a first-class feature.

- Works via standard `tools` field in API requests
- Supported by: Qwen3, Qwen3-coder, DeepSeek-v3.x, gpt-oss, GLM models, MiniMax models, Devstral, Nemotron, Kimi
- Streaming tool calls supported (added v0.11+)
- Python SDK can accept actual Python functions as tools (auto-generates JSON schema)

**Web Search — built-in API:**
```bash
POST https://ollama.com/api/web_search   # search query
POST https://ollama.com/api/web_fetch    # fetch URL content
```
- Included on free tier (estimated ~100 searches/day free, not officially stated)
- Higher limits on Pro/Max
- Recommended models for web search: qwen3, gpt-oss

---

## 4. Pricing

**Subscription-based (GPU time), NOT per-token yet.**

| Feature | Free ($0) | Pro ($20/mo or $200/yr) | Max ($100/mo) |
|---------|-----------|------------------------|---------------|
| Concurrent cloud models | 1 | 3 | 10 |
| Usage level | "Light" | "50x more than Free" | "5x more than Pro" (250x Free) |
| Premium model requests/month | 5 | 20 | 100 |
| Private models | 0 | 3 | 5 |
| Session limit reset | Every 5 hours | Every 5 hours | Every 5 hours |
| Weekly limit reset | Every 7 days | Every 7 days | Every 7 days |
| Local Ollama usage | Unlimited | Unlimited | Unlimited |
| Web search | Included | Higher limits | Highest limits |

**Usage is measured by GPU time** (model size × request duration), NOT tokens. Cached prefixes use less quota.

**Coming soon:** Per-token pricing with cache-aware discounts. No timeline given.

### OpenRouter Comparison (at $20/mo budget)

| Factor | Ollama Cloud Pro ($20/mo) | OpenRouter (~$20/mo) |
|--------|--------------------------|---------------------|
| Pricing model | Flat (GPU time) | Pay-per-token |
| Budget predictability | Fixed | Variable (can overspend) |
| MiniMax M2.7 | Included | $0.30/M in, $1.20/M out |
| 400B+ models | Many included | Available but expensive |
| Closed-source models | Gemini preview only (premium) | Claude, GPT-4, Gemini |
| Local + cloud hybrid | Native (same SDK) | Separate system |
| Built-in web search | Yes | No |
| Token accounting | Not available | Precise per-request |
| Best for | Heavy open-source usage, huge models | Mixed closed+open, precise cost control |

**Verdict:** At the same $20/mo spend, Ollama Cloud Pro gives access to DeepSeek 671B, Qwen3-coder 480B, GLM-5 744B — models that would cost significantly more per query on OpenRouter. The tradeoff is no closed-source frontier models (Claude, GPT-4) and no precise token tracking.

---

## 5. Prompt Caching

**Infrastructure-level caching exists** (KV-cache in GPU HBM for shared prompt prefixes). The pricing page notes that "shorter requests and prompts that share cached context use less" quota.

**No explicit API control yet.** No `cache_control` parameter. No separate pricing tier for cache hits.

**Announced:** "Cache-aware pricing" coming soon at per-token rates. Will surface cache savings explicitly.

**Practical implication for Root:** Caching is happening passively and reducing quota consumption. When per-token pricing launches, this becomes a major optimization lever.

---

## 6. Local + Cloud — Simultaneous Use

**Yes — native support.** This is a core design principle of Ollama's architecture.

- Local: `http://localhost:11434` — no auth, unlimited, no quota
- Cloud: `https://ollama.com` — needs `OLLAMA_API_KEY`, subject to plan limits
- `:cloud` suffix explicitly marks cloud models — no ambiguity
- Both can run concurrently from the same Python process

```python
# Local call (free, unlimited)
local_client = Client(host="http://localhost:11434")
local_resp = local_client.chat(model='phi3', messages=[...])

# Cloud call (quota, but massive model)
cloud_client = Client(
    host="https://ollama.com",
    headers={'Authorization': f'Bearer {os.environ["OLLAMA_API_KEY"]}'}
)
cloud_resp = cloud_client.chat(model='qwen3-coder:480b-cloud', messages=[...])
```

---

## 7. What Ollama Cloud ADDS Over Our Local Stack

Our local stack: `phi3`, `llama3.1`, `qwen3.5-4b`, `qwen2.5-coder`, `deepseek-r1`

| Category | Local (current) | Ollama Cloud adds |
|----------|----------------|-------------------|
| **Model scale** | Fits in local RAM | 480B–1T params (Qwen3-coder 480B, DeepSeek 671B, GLM-5 744B, Kimi 1T) |
| **Best coder** | qwen2.5-coder (small) | qwen3-coder:480b-cloud (262K ctx, SWE-bench champion) |
| **Vision** | None | qwen3-vl:235b, qwen3.5 vision, kimi-k2.5, gemini-3-flash-preview (1M ctx) |
| **Context window** | 4K–32K typically | Up to 262K (Qwen3-coder), 1M (Gemini preview) |
| **Agentic reliability** | Limited | minimax-m2.7 (97% skill adherence, 40 skills) |
| **Reasoning traces** | deepseek-r1 only | Many models: DeepSeek-v3.x, GLM-5, gpt-oss, kimi-k2.5 |
| **Google Gemini** | Not available | gemini-3-flash-preview (1M context, PREMIUM) |
| **OpenAI open-weight** | Not available | gpt-oss 20B/120B (Apache 2.0, tools + thinking) |
| **Built-in web search** | Not built in | `/api/web_search` + `/api/web_fetch` |
| **GPU requirement** | Yes (local hardware) | None — datacenter GPUs |

**Single biggest value-add:** Running 400B–1T models that require 250–600GB RAM. Our local hardware cannot run these.

---

## 8. Recommended Model Router Stack for Root

### Routing Tiers (cheapest → most capable)

**Tier 1 — Free (local Ollama, localhost:11434)**
| Task | Model | Why |
|------|-------|-----|
| Fast routing/classification | `phi3` | ~3.5s, zero cost |
| Summarization, simple tasks | `qwen3.5-4b` | ~8s, good quality |
| Code completion (small) | `qwen2.5-coder` | ~8.5s, trained on code |
| Reasoning (light) | `deepseek-r1` | ~17s, chain-of-thought |

**Tier 2 — Ollama Cloud (flat rate, https://ollama.com)**
| Task | Model | Why |
|------|-------|-----|
| Fast/cheap cloud tasks | `gpt-oss:20b-cloud` | 20B, 128K ctx, Apache 2.0 |
| Efficient reasoning | `nemotron-3-nano:4b` | 4B, tools+thinking |
| Complex coding | `qwen3-coder:480b-cloud` | 262K ctx, SWE-bench best |
| Architecture/planning | `deepseek-v3.2:cloud` | 671B MoE, tools+thinking |
| Agentic workflows | `minimax-m2.7:cloud` | 200K ctx, 97% skill adherence |
| Vision tasks | `qwen3-vl:235b-cloud` | Best open vision model |

**Tier 3 — OpenRouter (pay-per-token, for closed-source needs)**
| Task | Model | Why |
|------|-------|-----|
| When Claude is needed | `anthropic/claude-*` | Closed-source |
| When GPT-4 is needed | `openai/gpt-4o` | Closed-source |
| MiniMax M2.7 overflow | `minimax/minimax-m2.7` | If cloud quota exhausted |

### Decision Logic for Root's Router
```
1. Can a free local model handle this? (simple tasks, low latency needed)
   → YES: use phi3/qwen3.5-4b/deepseek-r1 at localhost:11434

2. Needs large context, massive scale, or tools?
   → YES: use Ollama Cloud (qwen3-coder:480b or deepseek-v3.2 or m2.7)

3. Needs closed-source model specifically?
   → YES: use OpenRouter

4. Ollama Cloud quota hit?
   → FALLBACK: OpenRouter with same model family (minimax-m2.7 on OpenRouter)
```

---

## 9. Rate Limits

**Not published numerically.** Qualitative only:

| Tier | Session Reset | Weekly Reset | Concurrent Models | Premium Requests/Month |
|------|--------------|-------------|-------------------|----------------------|
| Free | 5 hours | 7 days | 1 | 5 |
| Pro | 5 hours | 7 days | 3 | 20 |
| Max | 5 hours | 7 days | 10 | 100 |

- Requests beyond concurrency limit are **queued** (not rejected outright)
- Email notification at 90% usage threshold
- Premium requests (like Gemini 3 Flash Preview) use separate quota — do NOT count against normal limits
- Exact tokens/requests per session not disclosed

---

## 10. Unique Features

- **Vision:** qwen3-vl:235b, qwen3.5 variants, kimi-k2.5, gemini-3-flash-preview, ministral-3, devstral-small-2 (base64 encoded image input)
- **Thinking/CoT traces:** Many models surface chain-of-thought separately from final output
- **Structured outputs:** JSON mode + Pydantic schema-based structured outputs
- **Built-in web search:** `/api/web_search` + `/api/web_fetch` — unique, not in OpenRouter
- **Private model hosting:** Upload and serve private fine-tuned models
- **Image generation:** Experimental `/v1/images/generations`
- **Embeddings:** Local only — no cloud embedding models currently
- **Audio:** Limited. Not a first-class cloud feature yet.

---

## 11. Known Gaps / Validation Needed

| Gap | Impact | Action |
|-----|--------|--------|
| OpenAI-compatible endpoint on cloud (`/v1/chat/completions`) — not officially documented | Blocks LiteLLM routing | Test: `curl -H "Authorization: Bearer $KEY" https://ollama.com/v1/chat/completions` |
| LiteLLM + Ollama Cloud — no official docs | Root's LiteLLM router may not support cloud | Test before building routing logic around it |
| Exact rate limits unknown | Can't calculate "requests per dollar" | Monitor usage dashboard after launch |
| Embeddings on cloud — not available | Embedding tasks must stay local | Use local Ollama or OpenRouter for embeddings |
| Per-token pricing not yet live | Can't optimize token-by-token | Watch Ollama blog for announcement |

---

## 12. Summary Recommendation

**Activate Ollama Cloud Pro ($20/mo) alongside our existing OpenRouter usage.** This gives us:

1. **Access to 400B–1T models** we literally cannot run locally — massive capability jump for Root
2. **Same cost as current OpenRouter spend** on MiniMax M2.7 alone
3. **Native local+cloud hybrid** — phi3/llama3.1/deepseek-r1 stay free on localhost
4. **Built-in web search API** — useful for Root's research capabilities
5. **Flat rate** removes token anxiety for long-context work (262K on Qwen3-coder)

**Keep OpenRouter** for closed-source models (Claude, GPT-4) and as a fallback when Ollama Cloud quota is hit.

**Validate LiteLLM cloud integration** before building Root's router on it. If it doesn't work, use Ollama's native SDK directly with a thin routing wrapper.

---

*Sources: ollama.com/pricing, docs.ollama.com/cloud, ollama.com/blog/cloud-models, ollama.com/search?c=cloud, docs.ollama.com/api/openai-compatibility, docs.litellm.ai/docs/providers/ollama*
