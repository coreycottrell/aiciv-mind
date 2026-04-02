"""
aiciv_mind.tools.memory_tools — Agent memory search and write tools.

These tools are only registered when a MemoryStore is provided to ToolRegistry.default().
They are read_only=True (search) and read_only=False (write).

The agent_id for memory_write is captured at registration time via closure,
so each mind instance writes memories tagged to its own identity.
"""

from __future__ import annotations

from aiciv_mind.context import current_mind_id
from aiciv_mind.tools import ToolRegistry

# ---------------------------------------------------------------------------
# memory_search
# ---------------------------------------------------------------------------

_SEARCH_DEFINITION: dict = {
    "name": "memory_search",
    "description": (
        "Search stored memories using depth-weighted full-text search. "
        "Results combine BM25 text relevance with each memory's depth_score "
        "(a 0-1 signal reflecting access frequency, recency, pinning, and "
        "human endorsement). High-depth memories rank higher by default. "
        "Set use_depth=false for pure BM25 ranking. "
        "With graph=true, results include 1-hop linked memories (references, "
        "compounds, conflicts, supersedes) for richer context. "
        "Use before starting any significant task to surface prior learnings."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query — keywords or phrases to find in stored memories",
            },
            "agent_id": {
                "type": "string",
                "description": "Filter by agent ID (optional — omit to search all agents)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5)",
            },
            "use_depth": {
                "type": "boolean",
                "description": (
                    "When true (default), rank results by BM25 relevance weighted "
                    "by depth_score. When false, use pure BM25 text relevance."
                ),
            },
            "graph": {
                "type": "boolean",
                "description": (
                    "When true (default), include 1-hop graph neighbors — memories "
                    "linked to each result via references, compounds, conflicts, or "
                    "supersedes. Set false for flat search."
                ),
            },
        },
        "required": ["query"],
    },
}


def _make_search_handler(memory_store):
    """Return a memory_search handler closed over the given MemoryStore."""

    def memory_search_handler(tool_input: dict) -> str:
        query: str = tool_input.get("query", "").strip()
        # If the agent didn't specify an agent_id, auto-detect from contextvar.
        # This means concurrent sub-minds automatically scope their searches
        # to their own identity without the LLM needing to know its own ID.
        agent_id: str | None = tool_input.get("agent_id") or current_mind_id()
        limit: int = int(tool_input.get("limit", 5))
        use_depth: bool = tool_input.get("use_depth", True)
        use_graph: bool = tool_input.get("graph", True)

        if not query:
            return "ERROR: No query provided"

        try:
            if use_graph and hasattr(memory_store, "search_with_graph"):
                results = memory_store.search_with_graph(
                    query=query, agent_id=agent_id, limit=limit, use_depth=use_depth,
                )
            else:
                results = memory_store.search(
                    query=query, agent_id=agent_id, limit=limit, use_depth=use_depth,
                )
        except Exception as e:
            return f"ERROR: Memory search failed: {type(e).__name__}: {e}"

        if not results:
            return f"No memories found for query: {query}"

        sections: list[str] = []
        for mem in results:
            # Support both dict (real MemoryStore) and Memory dataclass (stub).
            if isinstance(mem, dict):
                title = mem.get("title", "(untitled)")
                content = mem.get("content", "")
                mem_id = mem.get("id", "?")
                agent = mem.get("agent_id", "?")
                domain = mem.get("domain", "general")
                linked = mem.get("_linked", [])
                links_from = mem.get("_links_from", [])
                links_to = mem.get("_links_to", [])
            else:
                title = getattr(mem, "title", "(untitled)")
                content = getattr(mem, "content", "")
                mem_id = getattr(mem, "id", "?")
                agent = getattr(mem, "agent_id", "?")
                domain = getattr(mem, "domain", "general")
                linked = []
                links_from = []
                links_to = []

            # Update depth scoring — this is the mechanism by which frequently-accessed
            # memories rise in depth_score over time (compounding intelligence).
            if mem_id != "?":
                try:
                    memory_store.touch(mem_id)
                except Exception:
                    pass  # Never let touch() failure suppress search results

            section = (
                f"## {title}\n"
                f"*id: {mem_id} | agent: {agent} | domain: {domain}*\n\n"
                f"{content}"
            )

            # P1: append graph context if links exist
            link_count = len(links_from) + len(links_to)
            if link_count > 0:
                section += f"\n\n*Graph: {link_count} link(s)*"
                for lf in links_from:
                    target_title = lf.get("target_title") or lf.get("target_id", "?")[:8]
                    section += f"\n  → {lf.get('link_type', '?')}: {target_title}"
                for lt in links_to:
                    source_title = lt.get("source_title") or lt.get("source_id", "?")[:8]
                    section += f"\n  ← {lt.get('link_type', '?')}: {source_title}"

            if linked:
                section += f"\n\n### Linked Memories ({len(linked)})"
                for lm in linked[:3]:  # Cap at 3 linked per result
                    ltitle = lm.get("title", "(untitled)")
                    lid = lm.get("id", "?")
                    section += f"\n- **{ltitle}** (`{lid}`)"

            section += "\n\n---"
            sections.append(section)

        return "\n\n".join(sections)

    return memory_search_handler


# ---------------------------------------------------------------------------
# memory_write
# ---------------------------------------------------------------------------

_WRITE_DEFINITION: dict = {
    "name": "memory_write",
    "description": (
        "Store a new memory for future retrieval. "
        "Use to record important learnings, decisions, patterns, or observations. "
        "Good memories have a clear title, specific content, and relevant tags."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short descriptive title for the memory",
            },
            "content": {
                "type": "string",
                "description": "The memory content — what was learned, decided, or observed",
            },
            "memory_type": {
                "type": "string",
                "description": (
                    "Type of memory: 'learning', 'decision', 'error', 'handoff', 'observation', or 'identity' "
                    "(default: 'learning'). Use 'identity' for foundational facts about yourself "
                    "that should persist indefinitely — your name, role, core principles, civilization membership."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of searchable tags (optional)",
            },
        },
        "required": ["title", "content"],
    },
}


def _make_write_handler(memory_store, agent_id: str):
    """Return a memory_write handler closed over the MemoryStore and agent_id."""

    def memory_write_handler(tool_input: dict) -> str:
        title: str = tool_input.get("title", "").strip()
        content: str = tool_input.get("content", "").strip()
        memory_type: str = tool_input.get("memory_type", "learning")
        tags: list[str] = tool_input.get("tags") or []

        if not title:
            return "ERROR: No title provided"
        if not content:
            return "ERROR: No content provided"

        # Resolve effective agent_id: prefer contextvar (accurate for concurrent
        # sub-minds) over the closure-bound default.
        effective_agent_id = current_mind_id() or agent_id

        # Support both the real MemoryStore (uses Memory dataclass) and a simple
        # callable store (for testing or lighter implementations).
        try:
            # Try real MemoryStore API first.
            from aiciv_mind.memory import Memory
            memory = Memory(
                agent_id=effective_agent_id,
                title=title,
                content=content,
                memory_type=memory_type,
                tags=tags,
            )
            mem_id = memory_store.store(memory)
        except ImportError:
            # Fallback for lighter store implementations.
            try:
                result = memory_store.store(
                    title=title,
                    content=content,
                    agent_id=effective_agent_id,
                    memory_type=memory_type,
                    tags=tags,
                )
                mem_id = getattr(result, "id", str(result))
            except Exception as e:
                return f"ERROR: Failed to store memory: {type(e).__name__}: {e}"
        except Exception as e:
            return f"ERROR: Failed to store memory: {type(e).__name__}: {e}"

        return f"Memory stored: {title} (id: {mem_id})"

    return memory_write_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_memory_tools(
    registry: ToolRegistry,
    memory_store,
    agent_id: str = "primary",
) -> None:
    """
    Register memory_search and memory_write tools into the given ToolRegistry.

    Both tools close over memory_store. memory_write also closes over agent_id
    so all writes are tagged to the correct agent.
    """
    registry.register(
        "memory_search",
        _SEARCH_DEFINITION,
        _make_search_handler(memory_store),
        read_only=True,
    )
    registry.register(
        "memory_write",
        _WRITE_DEFINITION,
        _make_write_handler(memory_store, agent_id),
        read_only=False,
    )
