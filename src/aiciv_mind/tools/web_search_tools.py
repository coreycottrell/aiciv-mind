"""
aiciv_mind.tools.web_search_tools — Web search via Ollama Cloud.

Provides a web_search tool that calls POST https://ollama.com/api/web_search.
Auth: Bearer token from OLLAMA_API_KEY env var (read at call-time — hot-add safe).

The tool is registered unconditionally so Root always sees it in its tool list.
If OLLAMA_API_KEY is not set, the tool returns a clear message explaining this.
"""

from __future__ import annotations

import os

from aiciv_mind.tools import ToolRegistry

_WEB_SEARCH_DEFINITION: dict = {
    "name": "web_search",
    "description": (
        "Search the web for current information. Use when you need facts, "
        "recent events, documentation, or any information that may not be in "
        "your training data or memory. Returns a summary of top results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (1-10, default 5)",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    },
}


async def _web_search_handler(tool_input: dict) -> str:
    """Handler for web_search — calls Ollama Cloud web search API."""
    import httpx

    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        return (
            "Web search unavailable: OLLAMA_API_KEY not set. "
            "Add OLLAMA_API_KEY=<key> to the .env file and restart the daemon."
        )

    query: str = tool_input["query"]
    max_results: int = int(tool_input.get("max_results", 5))

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://ollama.com/api/web_search",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"query": query, "max_results": max_results},
            )
            if resp.status_code != 200:
                return f"Web search error: HTTP {resp.status_code} — {resp.text[:200]}"

            data = resp.json()

            # Format results
            results = data.get("results", data if isinstance(data, list) else [])
            if not results:
                return f"No results found for: {query}"

            lines = [f"Web search results for: {query}\n"]
            for i, result in enumerate(results[:max_results], 1):
                title = result.get("title", "(no title)")
                url = result.get("url", result.get("link", ""))
                snippet = result.get("snippet", result.get("description", result.get("content", "")))
                lines.append(f"{i}. **{title}**")
                if url:
                    lines.append(f"   URL: {url}")
                if snippet:
                    lines.append(f"   {snippet[:300]}")
                lines.append("")

            return "\n".join(lines).strip()

    except Exception as e:
        return f"Web search failed: {type(e).__name__}: {e}"


def register_web_search(registry: ToolRegistry) -> None:
    """Register the web_search tool into the given ToolRegistry."""
    registry.register(
        "web_search",
        _WEB_SEARCH_DEFINITION,
        _web_search_handler,
        read_only=True,
    )
