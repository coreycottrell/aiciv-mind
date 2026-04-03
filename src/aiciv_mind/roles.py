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
        """Parse role from manifest string (handles hyphens, underscores, aliases)."""
        normalized = value.strip().lower().replace("-", "_")
        for member in cls:
            if member.value == normalized:
                return member
        # Check aliases — free-form role names that map to hierarchy levels
        alias = _ROLE_ALIASES.get(normalized)
        if alias is not None:
            return alias
        raise ValueError(
            f"Unknown role '{value}'. Must be one of: "
            f"{', '.join(m.value for m in cls)} "
            f"(or alias: {', '.join(_ROLE_ALIASES)})"
        )


# Aliases for manifest role strings that map to hierarchy levels.
# "conductor-of-conductors" is Root's philosophical role name — structurally PRIMARY.
_ROLE_ALIASES: dict[str, Role] = {
    "conductor_of_conductors": Role.PRIMARY,
    "conductor": Role.PRIMARY,
    "lead": Role.TEAM_LEAD,
    "worker": Role.AGENT,
}


# ---------------------------------------------------------------------------
# Tool whitelists — the structural constraints
# ---------------------------------------------------------------------------

# Primary: coordination + scratchpad + memory for routing decisions.
# These MUST match names in the ToolRegistry.  See tools/ for definitions.
PRIMARY_TOOLS: frozenset[str] = frozenset({
    "spawn_team_lead",       # spawn_tools.py — create team lead sub-mind
    "shutdown_team_lead",    # spawn_tools.py — graceful shutdown
    "send_to_submind",       # submind_tools.py — IPC message to active sub-mind
    "send_message",          # message_tools.py — inter-mind messaging
    "coordination_read",     # coordination_tools.py — read coordination scratchpad
    "coordination_write",    # coordination_tools.py — write coordination scratchpad
    "scratchpad_read",       # scratchpad_tools.py — Root's private journal
    "scratchpad_write",      # scratchpad_tools.py — Root's private journal
    "scratchpad_append",     # scratchpad_tools.py — append to journal
    "memory_search",         # memory_tools.py — search for routing decisions
    "ab_model_test",         # ab_test_tools.py — A/B model comparison (parallel sub-minds)
    "talk_to_acg",           # acg_tools.py — send messages to ACG Primary via tmux
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
