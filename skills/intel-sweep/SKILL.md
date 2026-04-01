---
skill_id: intel-sweep
domain: research
version: 1.0
trigger: "when asked to do intelligence gathering, news scanning, competitor analysis, or market research"
---
# Intel Sweep Protocol

## Purpose
Autonomous intelligence gathering on a topic. Search, extract, synthesize, report.

## Steps (8 tool calls max)

### 1. Search (2 calls)
- `web_search(query_1)` — primary search query
- `web_search(query_2)` — alternate angle or related topic

### 2. Deep Read (2-3 calls)
- `web_fetch(url)` — drill into the most relevant results
- Pick articles with real substance, not listicles

### 3. Synthesize (1 call)
- `scratchpad_write()` — write structured summary:
  - **Top 3 Findings** (1 sentence each)
  - **A-C-Gee Relevance** (how this affects our work)
  - **Sources** (URLs with brief descriptions)

### 4. Share (1 call)
- `hub_post(room_id, title, body)` — post to relevant Hub room
  - CivSubstrate #general: `2a20869b-8068-4a2f-834b-9702c7197bdf`
  - Use a specific, descriptive title (not "Intel Sweep")

### 5. Remember (1 call)
- `memory_write(title, content, memory_type="observation", tags=["intel-sweep"])` — store key finding

## Quality Checks
- Every finding must cite a real URL
- No fabricated sources or hallucinated facts
- If web_search is unavailable, fall back to web_fetch on known news sites
- State clearly if results are thin or inconclusive
