"""
aiciv_mind.tools.graph_tools — Memory graph tools for linking memories.

Memories are not flat files. They are nodes in a graph. These tools let Root
create and traverse links between memories: supersedes, references, conflicts,
compounds.
"""

from __future__ import annotations

import json

from aiciv_mind.tools import ToolRegistry


# ---------------------------------------------------------------------------
# memory_link
# ---------------------------------------------------------------------------

_LINK_DEFINITION: dict = {
    "name": "memory_link",
    "description": (
        "Create a directed link between two memories. Link types: "
        "'supersedes' (source replaces target), 'references' (source cites target), "
        "'conflicts' (source contradicts target), 'compounds' (together they reveal a pattern)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "source_id": {"type": "string", "description": "ID of the source memory"},
            "target_id": {"type": "string", "description": "ID of the target memory"},
            "link_type": {
                "type": "string",
                "description": "One of: supersedes, references, conflicts, compounds",
            },
            "reason": {
                "type": "string",
                "description": "Why this link exists (optional)",
                "default": "",
            },
        },
        "required": ["source_id", "target_id", "link_type"],
    },
}


def _make_link_handler(memory_store):
    def memory_link_handler(tool_input: dict) -> str:
        source_id = tool_input.get("source_id", "").strip()
        target_id = tool_input.get("target_id", "").strip()
        link_type = tool_input.get("link_type", "").strip()
        reason = tool_input.get("reason", "").strip() or None

        if not source_id or not target_id:
            return "ERROR: source_id and target_id are both required"
        if not link_type:
            return "ERROR: link_type is required"

        valid_types = ("supersedes", "references", "conflicts", "compounds")
        if link_type not in valid_types:
            return f"ERROR: link_type must be one of {valid_types}, got: {link_type}"

        lid = memory_store.link_memories(source_id, target_id, link_type, reason)
        return f"Link created: {lid} [{link_type}] {source_id} -> {target_id}"

    return memory_link_handler


# ---------------------------------------------------------------------------
# memory_graph
# ---------------------------------------------------------------------------

_GRAPH_DEFINITION: dict = {
    "name": "memory_graph",
    "description": (
        "See a memory's graph neighborhood — what it links to and what links to it. "
        "Shows the memory itself plus all incoming and outgoing connections."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "ID of the memory to inspect"},
        },
        "required": ["memory_id"],
    },
}


def _make_graph_handler(memory_store):
    def memory_graph_handler(tool_input: dict) -> str:
        memory_id = tool_input.get("memory_id", "").strip()
        if not memory_id:
            return "ERROR: memory_id is required"

        graph = memory_store.get_memory_graph(memory_id)

        lines = [f"## Memory Graph: {memory_id}\n"]

        # The memory itself
        mem = graph.get("memory")
        if mem:
            lines.append(f"**Title**: {mem.get('title', '(untitled)')}")
            lines.append(f"**Domain**: {mem.get('domain', 'general')} | **Type**: {mem.get('memory_type', '?')}")
            lines.append(f"**Created**: {mem.get('created_at', '?')}\n")
        else:
            lines.append("*(memory not found — may have been archived)*\n")

        # Outgoing links
        out = graph.get("links_from", [])
        if out:
            lines.append(f"### Links FROM this memory ({len(out)})")
            for link in out:
                target_title = link.get("target_title") or link.get("target_id", "?")
                reason = f" — {link['reason']}" if link.get("reason") else ""
                lines.append(f"- **{link['link_type']}** -> {target_title} (`{link['target_id']}`){reason}")
            lines.append("")
        else:
            lines.append("### Links FROM this memory: none\n")

        # Incoming links
        inc = graph.get("links_to", [])
        if inc:
            lines.append(f"### Links TO this memory ({len(inc)})")
            for link in inc:
                source_title = link.get("source_title") or link.get("source_id", "?")
                reason = f" — {link['reason']}" if link.get("reason") else ""
                lines.append(f"- **{link['link_type']}** <- {source_title} (`{link['source_id']}`){reason}")
            lines.append("")
        else:
            lines.append("### Links TO this memory: none\n")

        return "\n".join(lines)

    return memory_graph_handler


# ---------------------------------------------------------------------------
# memory_conflicts
# ---------------------------------------------------------------------------

_CONFLICTS_DEFINITION: dict = {
    "name": "memory_conflicts",
    "description": (
        "List all unresolved conflict links between memories. "
        "Shows both sides of each contradiction so you can resolve them."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "Filter by agent (empty = all agents)",
                "default": "",
            },
        },
    },
}


def _make_conflicts_handler(memory_store):
    def memory_conflicts_handler(tool_input: dict) -> str:
        agent_id = tool_input.get("agent_id", "").strip() or None

        conflicts = memory_store.get_conflicts(agent_id=agent_id)
        if not conflicts:
            return "No unresolved memory conflicts found."

        lines = [f"## Memory Conflicts ({len(conflicts)} unresolved)\n"]
        for c in conflicts:
            source_title = c.get("source_title") or c.get("source_id", "?")
            target_title = c.get("target_title") or c.get("target_id", "?")
            reason = c.get("reason") or "(no reason given)"
            lines.append(
                f"### Conflict: {source_title} vs {target_title}\n"
                f"- **Source** (`{c['source_id']}`): {source_title}\n"
                f"- **Target** (`{c['target_id']}`): {target_title}\n"
                f"- **Reason**: {reason}\n"
                f"- **Created**: {c.get('created_at', '?')}\n"
            )
        return "\n".join(lines)

    return memory_conflicts_handler


# ---------------------------------------------------------------------------
# memory_superseded
# ---------------------------------------------------------------------------

_SUPERSEDED_DEFINITION: dict = {
    "name": "memory_superseded",
    "description": (
        "List memories that have been superseded (replaced) by newer ones. "
        "Useful for pruning stale knowledge."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "Filter by agent (empty = all agents)",
                "default": "",
            },
        },
    },
}


def _make_superseded_handler(memory_store):
    def memory_superseded_handler(tool_input: dict) -> str:
        agent_id = tool_input.get("agent_id", "").strip() or None

        superseded = memory_store.get_superseded(agent_id=agent_id)
        if not superseded:
            return "No superseded memories found."

        lines = [f"## Superseded Memories ({len(superseded)})\n"]
        for m in superseded:
            lines.append(
                f"- **{m.get('title', '(untitled)')}** (`{m['id']}`)\n"
                f"  Replaced by: `{m.get('superseded_by', '?')}`\n"
                f"  Created: {m.get('created_at', '?')}"
            )
        return "\n".join(lines)

    return memory_superseded_handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_graph_tools(
    registry: ToolRegistry,
    memory_store,
) -> None:
    """Register memory_link, memory_graph, memory_conflicts, memory_superseded."""
    registry.register(
        "memory_link",
        _LINK_DEFINITION,
        _make_link_handler(memory_store),
        read_only=False,
    )
    registry.register(
        "memory_graph",
        _GRAPH_DEFINITION,
        _make_graph_handler(memory_store),
        read_only=True,
    )
    registry.register(
        "memory_conflicts",
        _CONFLICTS_DEFINITION,
        _make_conflicts_handler(memory_store),
        read_only=True,
    )
    registry.register(
        "memory_superseded",
        _SUPERSEDED_DEFINITION,
        _make_superseded_handler(memory_store),
        read_only=True,
    )
