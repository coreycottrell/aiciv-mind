"""
aiciv_mind.roles — Hard-coded role enforcement for fractal coordination.

Design Principle 5: "This is not a behavioral guideline — it is a structural
constraint."

Three roles, three tool sets, hard-coded:
  PRIMARY    → can ONLY spawn team leads, read/write coordination scratchpad, communicate
  TEAM_LEAD  → can ONLY spawn agents, read/write team scratchpad, read coordination, communicate
  AGENT      → full tool access (65+ tools)

The mind's role is declared in its manifest YAML.  ToolRegistry.for_role()
returns a filtered registry containing ONLY the tools for that role.  The LLM
never sees tools outside its whitelist — they don't exist at that level.
"""

from __future__ import annotations

import enum


class Role(enum.Enum):
    """Mind hierarchy level.  Determines available tools."""

    PRIMARY = "primary"
    TEAM_LEAD = "team_lead"
    AGENT = "agent"

    @classmethod
    def from_str(cls, value: str) -> "Role":
        """Parse role from manifest string (handles hyphens and underscores)."""
        normalized = value.strip().lower().replace("-", "_")
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(
            f"Unknown role '{value}'. Must be one of: "
            f"{', '.join(m.value for m in cls)}"
        )


# ---------------------------------------------------------------------------
# Tool whitelists — the structural constraints
# ---------------------------------------------------------------------------

# Primary: 7 tools.  Can ONLY orchestrate + inter-mind coordination.
PRIMARY_TOOLS: frozenset[str] = frozenset({
    "spawn_team_lead",
    "coordination_read",
    "coordination_write",
    "send_message",
    "shutdown_team_lead",
    "publish_surface",
    "read_surface",
})

# Team Lead: coordination + read-only memory + team scratchpad.
# Cannot execute tools, cannot write files, cannot call bash.
TEAM_LEAD_TOOLS: frozenset[str] = frozenset({
    "spawn_agent",
    "team_scratchpad_read",
    "team_scratchpad_write",
    "coordination_read",
    "send_message",
    "memory_search",
    "shutdown_agent",
})

# Agent: gets everything.  No whitelist — all registered tools are available.
# This is represented by None (no filter).
AGENT_TOOLS: None = None


# Mapping for programmatic access
ROLE_TOOL_WHITELIST: dict[Role, frozenset[str] | None] = {
    Role.PRIMARY: PRIMARY_TOOLS,
    Role.TEAM_LEAD: TEAM_LEAD_TOOLS,
    Role.AGENT: AGENT_TOOLS,  # None = all tools
}


def tools_for_role(role: Role) -> frozenset[str] | None:
    """
    Return the tool whitelist for a role.

    Returns frozenset of tool names for PRIMARY/TEAM_LEAD.
    Returns None for AGENT (meaning: all tools, no filter).
    """
    return ROLE_TOOL_WHITELIST[role]
