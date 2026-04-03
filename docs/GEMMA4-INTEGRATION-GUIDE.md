# Gemma 4 Integration Guide for aiciv-mind

**Date**: 2026-04-03 (Gemma 4 released April 2, 2026)
**Purpose**: Production reference for all three Mind engine builds
**License**: Apache 2.0 (no MAU limits, no acceptable-use enforcement, full commercial freedom)

---

## Table of Contents

1. [Model Overview](#1-model-overview)
2. [Ollama Integration](#2-ollama-integration)
3. [Quantization Options](#3-quantization-options)
4. [Tool / Function Calling](#4-tool--function-calling)
5. [System Prompts](#5-system-prompts)
6. [Thinking / Reasoning Mode](#6-thinking--reasoning-mode)
7. [Multimodal Capabilities](#7-multimodal-capabilities)
8. [Performance Benchmarks](#8-performance-benchmarks)
9. [Multi-Model Routing: Gemma 4 vs M2.7](#9-multi-model-routing-gemma-4-vs-m27)
10. [LiteLLM / OpenAI SDK Compatibility](#10-litellm--openai-sdk-compatibility)
11. [Known Issues (Day One)](#11-known-issues-day-one)
12. [Recommended Configuration for aiciv-mind](#12-recommended-configuration-for-aiciv-mind)

---

## 1. Model Overview

Gemma 4 is Google DeepMind's open-weight model family built from Gemini 3 research. Four variants:

| Variant | Total Params | Active Params | Architecture | Context | Modalities |
|---------|-------------|---------------|-------------|---------|------------|
| **E2B** | 5.1B (w/ embeddings) | 2.3B effective | Dense, 35 layers | 128K | Text, Image, Audio, Video (frames) |
| **E4B** | 8B (w/ embeddings) | 4.5B effective | Dense, 42 layers | 128K | Text, Image, Audio, Video (frames) |
| **26B-A4B** | 25.2B | 3.8B active | MoE (128 experts, 8 active + 1 shared), 30 layers | 256K | Text, Image, Video (frames) |
| **31B** | 30.7B | 30.7B | Dense, 60 layers | 256K | Text, Image, Video (frames) |

**Key architectural innovations:**
- **Per-Layer Embeddings (PLE)**: Feeds residual signals into every decoder layer (used in E2B/E4B — the "E" stands for "Effective")
- **Hybrid attention**: Interleaves local sliding window (512 tokens E2B/E4B, 1024 tokens 26B/31B) with full global attention
- **Shared KV Cache**: Reduces memory across final layers
- **MoE routing** (26B only): 128 small experts with 8 active per token + 1 shared always-on expert. Achieves 97% of 31B dense quality at ~8x less compute per token.
- **Vision encoders**: ~150M params (E2B/E4B), ~550M params (26B/31B)
- **Audio encoder**: ~300M params (E2B/E4B only — no audio on 26B/31B)
- **140+ languages** supported natively

---

## 2. Ollama Integration

**Status: AVAILABLE** — Ollama v0.20.0 added same-day support (April 3, 2026) with vision, thinking mode, and function calling.

### Pull Commands

```bash
# Default (E4B, recommended starting point)
ollama pull gemma4

# Specific variants
ollama pull gemma4:e2b          # 7.2 GB — smallest, good for edge/testing
ollama pull gemma4:e4b          # 9.6 GB — default, solid all-rounder
ollama pull gemma4:26b          # 18 GB  — MoE sweet spot for 24GB GPUs
ollama pull gemma4:31b          # 20 GB  — full dense, needs 24GB+ GPU

# Specific quantizations
ollama pull gemma4:e2b-it-q4_K_M    # 7.2 GB
ollama pull gemma4:e2b-it-q8_0      # 8.1 GB
ollama pull gemma4:e2b-it-bf16      # 10 GB
ollama pull gemma4:e4b-it-q4_K_M    # 9.6 GB
ollama pull gemma4:e4b-it-q8_0      # 12 GB
ollama pull gemma4:e4b-it-bf16      # 16 GB
ollama pull gemma4:26b-a4b-it-q4_K_M  # 18 GB — RECOMMENDED for production
ollama pull gemma4:26b-a4b-it-q8_0    # 28 GB
ollama pull gemma4:31b-it-q4_K_M     # 20 GB
ollama pull gemma4:31b-it-q8_0       # 34 GB
ollama pull gemma4:31b-it-bf16       # 63 GB
```

### Quick Test

```bash
# Text
ollama run gemma4:26b "What is consciousness?"

# Vision (from file)
ollama run gemma4:26b "Describe this image" ./screenshot.png
```

---

## 3. Quantization Options

| Variant | Q4_K_M | Q8_0 | BF16 | Recommendation |
|---------|--------|------|------|----------------|
| E2B | 7.2 GB | 8.1 GB | 10 GB | Q4 fine for testing; BF16 fits in 16GB |
| E4B | 9.6 GB | 12 GB | 16 GB | Q4 for daily use; Q8 if VRAM permits |
| 26B-A4B | 18 GB | 28 GB | N/A | **Q4 is the sweet spot** — fits 24GB GPU with full 256K context |
| 31B | 20 GB | 34 GB | 63 GB | Q4 for 24GB GPU (limited context); Q8+ needs 48GB |

**Quality vs size tradeoff:**
- Q4_K_M: ~5-8% quality degradation on hard benchmarks, but adequate for orchestration/routing
- Q8_0: ~1-2% degradation, near-lossless for most tasks
- BF16: Full precision, no degradation

**For aiciv-mind production: Use `gemma4:26b-a4b-it-q4_K_M` (18 GB)**
- Fits RTX 3090 (24 GB) with room for 256K context
- MoE architecture means only 3.8B params active per token = fast inference
- 97% of 31B quality

---

## 4. Tool / Function Calling

Gemma 4 has **native tool calling** with dedicated special tokens. This is critical for aiciv-mind's agentic architecture.

### Special Tokens

| Token | Purpose |
|-------|---------|
| `<\|tool>` / `<tool\|>` | Declare tool definitions |
| `<\|tool_call>` / `<tool_call\|>` | Model requests tool execution |
| `<\|tool_response>` / `<tool_response\|>` | Return tool results to model |
| `<\|"\|>` | String delimiter within all structured data |

### Raw Token Format

**Tool declaration** (in system prompt):
```
<|tool>declaration:get_weather{location:string,unit:string}<tool|>
```

**Model generates tool call:**
```
<|tool_call>call:get_weather{location:<|"|>London<|"|>,unit:<|"|>celsius<|"|>}<tool_call|>
```

**Application returns result:**
```
<|tool_response>response:get_weather{temperature:15,weather:<|"|>sunny<|"|>}<tool_response|>
```

### OpenAI-Compatible Format via Ollama

When using Ollama's `/v1/chat/completions` endpoint, use standard OpenAI tool format:

```python
import openai

client = openai.OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

response = client.chat.completions.create(
    model="gemma4:26b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather in Tokyo?"}
    ],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                },
                "required": ["location"]
            }
        }
    }]
)
```

Ollama translates the OpenAI format to Gemma 4's native token format internally.

### Tool Calling Gotchas

1. **String delimiter**: ALL string values in tool calls use `<|"|>`, not regular quotes
2. **Parse carefully**: Extract function name and args from `<|tool_call>call:NAME{ARGS}<tool_call|>`
3. **Security**: Never use `globals()` or `eval()` to execute tool calls — use a whitelisted function map
4. **Complex params**: Nested objects in function parameters may generate generic schemas. Define JSON schemas manually for complex types.
5. **Thinking + tools**: Enable thinking mode alongside tool calling for better accuracy (the model reasons about WHICH tool to call)

---

## 5. System Prompts

**Gemma 4 is the first Gemma with native `system` role support.** Previous Gemma models required workarounds.

### Chat Template Format

```
<|turn>system
    [system instructions]<turn|>
<|turn>user
    [user message]<turn|>
<|turn>model
    [model response]<turn|>
```

### Via Ollama API

```python
# Native Ollama API
requests.post("http://localhost:11434/api/chat", json={
    "model": "gemma4:26b",
    "messages": [
        {"role": "system", "content": "You are an AI mind orchestrator..."},
        {"role": "user", "content": "Spawn a research sub-mind"}
    ]
})

# OpenAI-compatible
client.chat.completions.create(
    model="gemma4:26b",
    messages=[
        {"role": "system", "content": "You are an AI mind orchestrator..."},
        {"role": "user", "content": "Spawn a research sub-mind"}
    ]
)
```

### System Prompt Best Practices

1. **Put everything in one system turn**: Thinking activation, tool declarations, and persona instructions all go in the system message
2. **Place `<|think|>` first** if enabling thinking mode
3. **Tool declarations follow** thinking activation
4. **Persona/instructions last**
5. **No known hard limit** on system prompt length, but keep under ~4K tokens for consistent quality
6. **Consolidate**: Multiple system turns are NOT supported — use one

### Combined System Prompt Example

```
<|think|>
You are the orchestration layer of an AI mind. Your capabilities:

<|tool>declaration:spawn_submind{task:string,model:string,priority:string}<tool|>
<|tool>declaration:query_memory{key:string,scope:string}<tool|>
<|tool>declaration:send_message{recipient:string,content:string}<tool|>

Rules:
- Route complex reasoning to yourself (thinking mode)
- Route code execution to M2.7 sub-minds
- Always check memory before spawning new tasks
```

---

## 6. Thinking / Reasoning Mode

Gemma 4 has **configurable extended thinking** via the `<|think|>` control token.

### How to Enable

**In system prompt** (raw format):
```
<|turn>system
    <|think|>You are a helpful assistant.<turn|>
```

**Via Ollama API** — Ollama handles this automatically when you set thinking mode. Via the OpenAI-compatible endpoint, include `<|think|>` at the start of your system message.

**Via HuggingFace** (for direct model use):
```python
text = processor.apply_chat_template(messages, enable_thinking=True, tokenize=False)
```

### How It Works

When thinking is enabled, the model outputs an internal reasoning channel before the final answer:

```
<|channel>thought
I need to consider the user's question about spawning a sub-mind.
The task requires research capability, so M2.7 would be appropriate...
<channel|>Based on your request, I'll spawn a research sub-mind using M2.7...
```

### Controlling Thinking Depth

- **Full thinking**: Just include `<|think|>` — model decides depth
- **Reduced thinking (~20% fewer tokens)**: Add instruction like "Think efficiently and concisely" in system prompt
- **No thinking**: Omit `<|think|>` from system prompt
- **Suppress ghost thoughts on 26B/31B**: When thinking is OFF, larger models may still occasionally generate thought channels. Add an empty thinking token to suppress:
  ```
  <|turn>model
  <|channel>thought
  <channel|>[actual response]
  ```

### Multi-Turn Handling

**Critical**: Strip thinking from previous turns. Only include the final response in conversation history. Thoughts from previous model turns must NOT be added before the next user turn.

Exception: During tool-calling sequences, preserve the full chain (thinking + tool_call + tool_response + final answer) within a single model turn.

### When to Use Thinking

| Task | Thinking? | Why |
|------|-----------|-----|
| Orchestration / routing decisions | **YES** | Better tool selection, fewer routing errors |
| Complex reasoning / planning | **YES** | Significant quality improvement |
| Simple responses / acknowledgments | **NO** | Waste of tokens, adds latency |
| Tool-heavy workflows | **YES** | Better accuracy on which tool to call |
| High-throughput message routing | **NO** | Latency matters more than reasoning depth |

### Token Overhead

Thinking typically adds 50-500 tokens of reasoning before the response. For orchestration use in aiciv-mind, this is acceptable — the improved decision quality outweighs the ~0.5-2s latency cost.

---

## 7. Multimodal Capabilities

### Capabilities by Model

| Modality | E2B | E4B | 26B | 31B |
|----------|-----|-----|-----|-----|
| Text | Yes | Yes | Yes | Yes |
| Image (variable aspect/resolution) | Yes | Yes | Yes | Yes |
| Audio (speech recognition/translation) | Yes | Yes | No | No |
| Video (frame extraction, up to 60s @ 1fps) | Yes | Yes | Yes | Yes |

### Image Input via Ollama API

**Native Ollama API** (base64):
```python
import base64, requests

with open("screenshot.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

response = requests.post("http://localhost:11434/api/chat", json={
    "model": "gemma4:26b",
    "messages": [{
        "role": "user",
        "content": "What do you see in this image?",
        "images": [img_b64]
    }],
    "stream": False
})
```

**OpenAI-compatible** (via `/v1/chat/completions`):
```python
response = client.chat.completions.create(
    model="gemma4:26b",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "What do you see?"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ]
    }]
)
```

### Visual Token Budget

Gemma 4 supports configurable visual token budgets controlling image resolution:

| Budget | Tokens | Use Case |
|--------|--------|----------|
| 70 | Low | Quick classification, thumbnails |
| 140 | Low-med | Basic descriptions |
| 280 | Medium | Standard analysis |
| 560 | High | Detailed inspection |
| 1120 | Max | Fine-grained OCR, complex diagrams |

**Best practice**: Place image/audio content BEFORE text in prompts for optimal results.

### Practical Uses for aiciv-mind

- **Screen reading**: Capture tmux panes as screenshots, feed to Gemma 4 for state understanding
- **Document processing**: Read PDFs, diagrams, architecture images
- **Voice input** (E2B/E4B only): Speech recognition for human-AI voice interaction
- **Visual debugging**: Feed error screenshots to understand UI state

---

## 8. Performance Benchmarks

### Quality Benchmarks

| Benchmark | Gemma 4 31B | Gemma 4 26B-A4B | Gemma 3 27B | M2.7 (MiniMax) |
|-----------|------------|-----------------|-----------|----------------|
| MMLU Pro | 85.2% | 82.6% | 67.6% | — |
| GPQA Diamond | 84.3% | 82.3% | 42.4% | — |
| AIME 2026 (math) | 89.2% | 88.3% | 20.8% | — |
| LiveCodeBench v6 | 80.0% | 77.1% | 29.1% | — |
| Codeforces ELO | 2150 | 1718 | 110 | — |
| MMMU Pro (vision) | 76.9% | 73.8% | 49.7% | — |
| SWE-Pro | — | — | — | 56.2% |
| Terminal Bench 2 | — | — | — | 57.0% |
| Skill Adherence | — | — | — | 97% |
| LMArena Score | ~1452 | ~1441 | — | 1495 (ELO) |

### Hardware Performance (tokens/second)

#### Gemma 4 26B-A4B (MoE) — Q4 Quantization

| GPU | Context | Prompt (t/s) | Generation (t/s) | VRAM |
|-----|---------|-------------|-------------------|------|
| **RTX 3090** | 4K | 3,625 | **119** | 18 GB |
| RTX 3090 | 256K | 671 | **64** | 23 GB |
| RTX 5090 | 4K | 8,799 | 180 | 18 GB |
| RTX 5090 | 256K | 1,707 | 106 | 23 GB |

#### Gemma 4 31B Dense — Q4 Quantization

| GPU | Context | Prompt (t/s) | Generation (t/s) | VRAM |
|-----|---------|-------------|-------------------|------|
| **RTX 3090** | 4K | 1,155 | **34** | 20 GB |
| RTX 3090 | 45K | 629 | **30** | ~30 GB |
| RTX 5090 | 4K | 3,395 | 61 | 20 GB |

### Key Takeaway for aiciv-mind

**The 26B MoE is 3.5x faster than 31B Dense on RTX 3090** (119 vs 34 tok/s) while scoring within 3% on benchmarks. The MoE is the clear production choice for 24GB GPUs.

**Speed formula**: `(memory bandwidth GB/s) / (model size GB)` ≈ tok/s

RTX 3090 = 936 GB/s bandwidth. For 26B Q4 (18 GB): 936/18 ≈ 52 theoretical, actual is 119 because MoE only loads 3.8B active params per token.

---

## 9. Multi-Model Routing: Gemma 4 vs M2.7

This is the core architectural decision for aiciv-mind's fractal engine.

### Strengths Comparison

| Dimension | Gemma 4 26B | MiniMax M2.7 |
|-----------|------------|--------------|
| **Math/Reasoning** | 88.3% AIME | Lower (general-purpose) |
| **Code Generation** | 77.1% LiveCodeBench | SWE-Pro 56.2%, Terminal Bench 57% |
| **Multimodal** | Native image/video/audio | Text-only (locally) |
| **Context Window** | 256K tokens | 1M tokens |
| **Tool Calling** | Native with dedicated tokens | Native, high skill adherence (97%) |
| **Orchestration** | Excellent with thinking mode | Good but optimized for execution |
| **Agentic Tasks** | Built for agent workflows | Built for agent workflows |
| **Skill Adherence** | Good | **97%** — exceptional |
| **Hallucination** | Low | **Very low** |
| **Local Speed (24GB)** | 119 tok/s (MoE) | Cloud-only for full model |
| **License** | Apache 2.0 | Proprietary (cloud API) |

### Recommended Routing Rules

```
ROUTING DECISION TREE:

1. Does the task require vision/audio/multimodal input?
   → YES: Gemma 4 (only option with local multimodal)

2. Does the task require deep reasoning, planning, or math?
   → YES: Gemma 4 with thinking mode ON

3. Does the task require code writing, debugging, or SWE execution?
   → YES: M2.7 (higher skill adherence, lower hallucination on code)

4. Does the task require orchestration / sub-mind routing?
   → YES: Gemma 4 with thinking mode ON (it was designed for agentic workflows)

5. Does the task require long-context analysis (>256K tokens)?
   → YES: M2.7 (1M context window)

6. Is low latency critical (message routing, acknowledgments)?
   → YES: Gemma 4 E4B or E2B without thinking (fastest local option)

7. Default / ambiguous?
   → Gemma 4 26B with thinking OFF (fast, capable, free)
```

### Proposed aiciv-mind Architecture

```
                    ┌─────────────────┐
                    │   Root Mind      │
                    │   Gemma 4 26B    │
                    │   (Orchestrator) │
                    │   Thinking: ON   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───────┐ ┌───▼──────┐ ┌────▼────────┐
     │ Research Mind   │ │Code Mind │ │ Comms Mind  │
     │ Gemma 4 26B    │ │  M2.7    │ │ Gemma 4 E4B │
     │ Thinking: ON   │ │(cloud)   │ │ Thinking:OFF│
     └────────────────┘ └──────────┘ └─────────────┘
```

---

## 10. LiteLLM / OpenAI SDK Compatibility

### Current aiciv-mind Stack

```
aiciv-mind → OpenAI SDK → LiteLLM proxy (localhost:4000) → Ollama (localhost:11434)
```

### LiteLLM Configuration

Add to `config.yaml`:

```yaml
model_list:
  - model_name: gemma4-26b
    litellm_params:
      model: ollama/gemma4:26b
      api_base: http://localhost:11434
      stream: true

  - model_name: gemma4-e4b
    litellm_params:
      model: ollama/gemma4:e4b
      api_base: http://localhost:11434
      stream: true

  - model_name: gemma4-31b
    litellm_params:
      model: ollama/gemma4:31b
      api_base: http://localhost:11434
      stream: true
```

### OpenAI SDK Usage

```python
from openai import OpenAI

# Via LiteLLM proxy
client = OpenAI(base_url="http://localhost:4000/v1", api_key="sk-litellm")

# Or direct to Ollama (bypassing LiteLLM)
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

# Standard chat completion
response = client.chat.completions.create(
    model="gemma4-26b",  # LiteLLM model name
    messages=[
        {"role": "system", "content": "<|think|>You are an AI mind orchestrator."},
        {"role": "user", "content": "Plan the next research cycle"}
    ],
    temperature=0.7,
    max_tokens=4096
)
```

### Docker Networking Note

When running Ollama in Docker on Linux, use `172.17.0.1:11434` not `host.docker.internal` (which is macOS/Windows only).

```yaml
# In LiteLLM config for Docker
api_base: http://172.17.0.1:11434
```

### Known LiteLLM Gotcha

Some models (earlier Gemma versions) didn't support system messages through LiteLLM. Gemma 4 DOES support system messages natively. If you encounter issues, set `supports_system_message: true` in LiteLLM model config, but this should not be needed for Gemma 4.

---

## 11. Known Issues (Day One)

Gemma 4 launched April 2, 2026. These are confirmed day-one issues:

### Confirmed Issues

| Issue | Severity | Status | Workaround |
|-------|----------|--------|------------|
| **Transformers 5.4.0 doesn't recognize `gemma4` type** | High (fine-tuning only) | Fix: install from dev branch | `pip install git+https://github.com/huggingface/transformers.git` |
| **PEFT rejects `Gemma4ClippableLinear` layer** | Medium (fine-tuning only) | Reported | Monkey-patch to inherit from `nn.Linear` |
| **`mm_token_type_ids` required even for text-only training** | Medium (fine-tuning only) | Reported | Custom data collator with zero-padded tensors |
| **llama.cpp GGUF loading fails on macOS** (31B & 26B) | High | Open (lmstudio#1728) | Use Ollama instead (has native support) |
| **llama.cpp CPU offloading OOM** | Medium | Open (llama.cpp#21323) | Ensure sufficient system RAM or use smaller quant |
| **Audio support missing in llama.cpp** | Low | Open (llama.cpp#21325) | Use HuggingFace pipeline or Ollama for audio |
| **Vision: image tokens need single ubatch** | Medium (llama.cpp) | Open | Adjust `--ubatch-size` or use Ollama |
| **Ghost thought channels on 26B/31B** when thinking OFF | Low | By design | Add empty `<|channel>thought\n<channel|>` prefix |

### Impact on aiciv-mind

**None of the showstoppers affect our stack.** We use Ollama (not raw llama.cpp), we don't fine-tune (yet), and Ollama v0.20+ handles Gemma 4 natively including vision and thinking.

The only issue to watch: **Ghost thought channels** on the 26B model may occasionally produce thinking output even when thinking mode is disabled. Handle this in the response parser — strip anything between `<|channel>` and `<channel|>` if thinking is supposed to be off.

---

## 12. Recommended Configuration for aiciv-mind

### Phase 1: Immediate (April 2026)

```bash
# Pull the production model
ollama pull gemma4:26b-a4b-it-q4_K_M

# Pull the fast model for message routing
ollama pull gemma4:e4b-it-q4_K_M

# Verify
ollama list | grep gemma4
```

### LiteLLM Config Addition

```yaml
# Add to config/config.yaml
model_list:
  # Orchestration / planning / reasoning
  - model_name: gemma4-orchestrator
    litellm_params:
      model: ollama/gemma4:26b
      api_base: http://localhost:11434  # or 172.17.0.1:11434 in Docker
      stream: true
      max_tokens: 8192

  # Fast routing / acknowledgments
  - model_name: gemma4-fast
    litellm_params:
      model: ollama/gemma4:e4b
      api_base: http://localhost:11434
      stream: true
      max_tokens: 2048

  # Code execution (existing M2.7)
  - model_name: m27-coder
    litellm_params:
      model: ollama/minimax-m2.7:cloud
      api_base: http://localhost:11434
      stream: true
```

### Response Parser Template

```python
import re

def parse_gemma4_response(raw_text: str, thinking_enabled: bool = True):
    """Parse Gemma 4 response, extracting thinking, tool calls, and content."""
    result = {"thinking": None, "tool_calls": [], "content": ""}

    # Extract thinking channel
    think_match = re.search(
        r'<\|channel>thought\n(.*?)<channel\|>',
        raw_text, re.DOTALL
    )
    if think_match:
        result["thinking"] = think_match.group(1).strip()

    # Extract tool calls
    tool_calls = re.findall(
        r'<\|tool_call>call:(\w+)\{(.*?)\}<tool_call\|>',
        raw_text
    )
    for name, args_str in tool_calls:
        # Parse args (handle <|"|> delimiters)
        args = {}
        for match in re.finditer(r'(\w+):<\|"\|>(.*?)<\|"\|>', args_str):
            args[match.group(1)] = match.group(2)
        for match in re.finditer(r'(\w+):(\d+(?:\.\d+)?)', args_str):
            if match.group(1) not in args:
                args[match.group(1)] = float(match.group(2))
        result["tool_calls"].append({"name": name, "arguments": args})

    # Extract final content (everything after last channel/tool block)
    content = raw_text
    content = re.sub(r'<\|channel>thought\n.*?<channel\|>', '', content, flags=re.DOTALL)
    content = re.sub(r'<\|tool_call>.*?<tool_call\|>', '', content, flags=re.DOTALL)
    content = re.sub(r'<\|tool_response>.*?<tool_response\|>', '', content, flags=re.DOTALL)
    result["content"] = content.strip()

    return result
```

### Key Numbers to Remember

| Metric | Value |
|--------|-------|
| **Production model** | `gemma4:26b-a4b-it-q4_K_M` |
| **VRAM (4K context)** | 18 GB |
| **VRAM (256K context)** | 23 GB |
| **Generation speed (RTX 3090)** | 119 tok/s @ 4K, 64 tok/s @ 256K |
| **Active params per token** | 3.8B (of 25.2B total) |
| **Context window** | 256K tokens |
| **License** | Apache 2.0 |
| **Ollama min version** | v0.20.0 |
| **LiteLLM model string** | `ollama/gemma4:26b` |
| **Docker Ollama host** | `172.17.0.1:11434` |

---

*This guide will be updated as the community discovers more about Gemma 4 production behavior. Check llama.cpp and Ollama GitHub issues for latest status.*
