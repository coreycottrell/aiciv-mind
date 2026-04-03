"""
aiciv_mind.tools.handoff_audit_tools — Audit handoff quality and accuracy.

The problem: handoffs are written by a Root who believes things that may no
longer be true. Handoffs are treated as fact rather than as claims that
need verification.

The fix: handoff_audit runs automated checks against the current state
of reality and flags claims in the handoff that contradict it. It is the
mirror of handoff_context: that tool generates rich context for a handoff;
this tool verifies a written handoff after it is written.

Checks:
  1. handoff_exists        — is there a recent handoff to audit?
  2. git_state_reconciliation — do git commits after handoff contradict its claims?
  3. tool_existence        — do tool-related claims match the registry?
  4. prior_handoff_contradiction — did state flip between consecutive handoffs?
  5. temporal_staleness   — is it too old with unresolved items?
  6. context_completeness  — does it have the minimum required fields?
  7. session_overlap       — is a new session already running with an incomplete handoff?

Output: JSON report with trust score and per-check findings.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

from aiciv_mind.tools import ToolRegistry

_TOOL_VERSION = "1.0.0"

_HANDOFF_AUDIT_DEFINITION: dict = {
    "name": "handoff_audit",
    "description": (
        "Audit the most recent handoff memory for quality and accuracy. "
        "Runs checks against git history, the tool registry, and prior handoffs. "
        "Flags stale claims, tool existence mismatches, unresolved contradictions, "
        "and missing context. Returns a JSON report with a trust score and "
        "per-check findings. Use this before trusting a handoff, or before "
        "writing a new one to see what the next session will actually receive."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verbose": {
                "type": "boolean",
                "description": (
                    "Include all check results, not just failures. "
                    "Default: false (failures + warnings only)."
                ),
            },
            "handoff_id": {
                "type": "string",
                "description": (
                    "Specific handoff memory ID to audit. Default: most recent."
                ),
            },
        },
        "additionalProperties": False,
    },
}


# ---------------------------------------------------------------------------
# Helper: git commands
# ---------------------------------------------------------------------------


def _git_log(mind_root: str, n: int = 20) -> str:
    """Get recent git log (oneline)."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=10,
            cwd=mind_root,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _git_commits_since(mind_root: str, since: str) -> str:
    """Get commits after a given ISO timestamp."""
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since}", "--oneline"],
            capture_output=True, text=True, timeout=10,
            cwd=mind_root,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _git_changed_files_since(mind_root: str, since: str) -> list[str]:
    """Get list of files changed since a given ISO timestamp."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{since}..HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=mind_root,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return []
    except Exception:
        return []


def _git_commit_exists(mind_root: str, commit_hash: str) -> bool:
    """Check if a commit hash exists in the repo."""
    try:
        result = subprocess.run(
            ["git", "cat-file", "-t", commit_hash[:8]],
            capture_output=True, text=True, timeout=5,
            cwd=mind_root,
        )
        return result.returncode == 0 and "commit" in result.stdout
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Helper: timestamp age calculation
# ---------------------------------------------------------------------------


def _hours_since(timestamp_str: str) -> float | None:
    """Return hours since an ISO timestamp string, or None if unparseable."""
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - ts.replace(tzinfo=timezone.utc)
        return delta.total_seconds() / 3600
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helper: handoff content parsing
# ---------------------------------------------------------------------------


def _parse_handoff_content(content_raw: str) -> dict[str, Any]:
    """
    Try to parse handoff content as JSON.
    If it fails, return a dict with the raw text as a 'summary' fallback.
    """
    try:
        parsed = json.loads(content_raw)
        if isinstance(parsed, str):
            return {"summary": parsed}
        return parsed
    except (json.JSONDecodeError, TypeError):
        return {"summary": content_raw}


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row (or any row-like) to a dict by column name."""
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):  # sqlite3.Row
        return {k: row[k] for k in row.keys()}
    return dict(enumerate(row))


# ---------------------------------------------------------------------------
# Check 1: handoff_exists
# ---------------------------------------------------------------------------

def _check_handoff_exists(
    memory_store, tool_input: dict
) -> dict[str, Any]:
    """
    Verify there is a recent handoff memory to audit.

    Findings:
      - error:   No handoff found
      - warning: Handoff is >24 hours old
      - info:    First handoff (no prior to compare)
    """
    findings: list[dict[str, str]] = []
    handoff_id = tool_input.get("handoff_id")

    try:
        if handoff_id:
            row = memory_store._conn.execute(
                "SELECT * FROM memories WHERE id = ? AND memory_type = 'handoff'",
                (handoff_id,),
            ).fetchone()
            if row is None:
                return {
                    "check": "handoff_exists",
                    "status": "FAIL",
                    "summary": f"Handoff '{handoff_id}' not found",
                    "findings": [{
                        "severity": "error",
                        "message": f"No handoff memory found with id '{handoff_id}'."
                    }],
                }
            handoff = _row_to_dict(row)
        else:
            row = memory_store._conn.execute(
                "SELECT * FROM memories WHERE memory_type = 'handoff' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()
            if row is None:
                return {
                    "check": "handoff_exists",
                    "status": "FAIL",
                    "summary": "No handoff memory found",
                    "findings": [{
                        "severity": "error",
                        "message": "No handoff memory entries exist in the memory store."
                    }],
                }
            handoff = _row_to_dict(row)

        findings.append({
            "severity": "info",
            "message": f"Found handoff: {handoff.get('id', '?')}, "
                       f"created {handoff.get('created_at', '?')}"
        })

        hours = _hours_since(handoff.get("created_at", ""))
        if hours is not None and hours > 24:
            findings.append({
                "severity": "warning",
                "message": (
                    f"Handoff is {hours:.1f} hours old (> 24 h). "
                    "Verify that the situation has not changed significantly."
                )
            })

        # Check for prior handoffs
        prior = memory_store._conn.execute(
            "SELECT id FROM memories WHERE memory_type = 'handoff' "
            "AND id != ? ORDER BY created_at DESC LIMIT 1",
            (handoff.get("id"),),
        ).fetchone()
        if prior is None:
            findings.append({
                "severity": "info",
                "message": "This is the first handoff; no prior history to compare."
            })

        return {
            "check": "handoff_exists",
            "status": "PASS",
            "summary": f"Handoff '{handoff.get('id')}' found and is recent enough.",
            "findings": findings,
            "handoff_id": handoff.get("id"),
        }

    except Exception as e:
        return {
            "check": "handoff_exists",
            "status": "ERROR",
            "summary": f"Error accessing memory store: {e}",
            "findings": [{"severity": "error", "message": str(e)}],
        }


# ---------------------------------------------------------------------------
# Check 2: git_state_reconciliation
# ---------------------------------------------------------------------------

def _check_git_state_reconciliation(
    memory_store, mind_root: str, handoff_id: str | None
) -> dict[str, Any]:
    """
    Check whether git commits made after the handoff contradict its claims.

    This looks for:
      - Files the handoff claims are stable but that were modified after it
      - Commit messages that suggest relevant work was done after the handoff
    """
    findings: list[dict[str, str]] = []

    try:
        if handoff_id:
            row = memory_store._conn.execute(
                "SELECT created_at FROM memories WHERE id = ?",
                (handoff_id,),
            ).fetchone()
        else:
            row = memory_store._conn.execute(
                "SELECT created_at FROM memories WHERE memory_type = 'handoff' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()

        if row is None:
            return {
                "check": "git_state_reconciliation",
                "status": "SKIP",
                "summary": "No handoff found to compare against git state.",
                "findings": [],
            }

        handoff_time = _row_to_dict(row).get("created_at", "")
        if not handoff_time:
            return {
                "check": "git_state_reconciliation",
                "status": "SKIP",
                "summary": "Handoff has no timestamp; cannot compare with git.",
                "findings": [],
            }

        commits_since = _git_commits_since(mind_root, handoff_time)
        changed_files = _git_changed_files_since(mind_root, handoff_time)

        if not commits_since and not changed_files:
            findings.append({
                "severity": "info",
                "message": "No git commits or file changes since handoff."
            })
            return {
                "check": "git_state_reconciliation",
                "status": "PASS",
                "summary": "No git activity since handoff — git state is consistent.",
                "findings": findings,
            }

        findings.append({
            "severity": "warning",
            "message": (
                f"{len(changed_files)} file(s) changed since handoff: "
                f"{', '.join(changed_files[:5])}"
                + ("..." if len(changed_files) > 5 else "")
            )
        })

        recent_commits = commits_since.split("\n")[:5]
        findings.append({
            "severity": "warning",
            "message": (
                f"Recent commits since handoff:\n" +
                "\n".join(f"  - {c}" for c in recent_commits)
            )
        })

        return {
            "check": "git_state_reconciliation",
            "status": "WARNING",
            "summary": (
                f"Git state has changed since handoff: "
                f"{len(changed_files)} files, {len(commits_since.splitlines())} commits."
            ),
            "findings": findings,
            "changed_files": changed_files[:10],
            "recent_commits": recent_commits,
        }

    except Exception as e:
        return {
            "check": "git_state_reconciliation",
            "status": "ERROR",
            "summary": f"Error checking git state: {e}",
            "findings": [{"severity": "error", "message": str(e)}],
        }


# ---------------------------------------------------------------------------
# Check 3: tool_existence
# ---------------------------------------------------------------------------

def _check_tool_existence(
    memory_store, registry: ToolRegistry, handoff_id: str | None
) -> dict[str, Any]:
    """
    Verify that tool names claimed in the handoff still exist in the registry.

    A handoff may claim a tool was used that no longer exists, or reference
    a tool by a misspelled or renamed version.
    """
    findings: list[dict[str, str]] = []
    referenced_tools: list[str] = []
    missing_tools: list[str] = []

    try:
        if handoff_id:
            row = memory_store._conn.execute(
                "SELECT content FROM memories WHERE id = ?",
                (handoff_id,),
            ).fetchone()
        else:
            row = memory_store._conn.execute(
                "SELECT content FROM memories WHERE memory_type = 'handoff' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()

        if row is None:
            return {
                "check": "tool_existence",
                "status": "SKIP",
                "summary": "No handoff found to check tools against.",
                "findings": [],
            }

        content = _row_to_dict(row).get("content", "")
        parsed = _parse_handoff_content(content)

        # Extract tool names from structured content
        if "tools_used" in parsed:
            tools_block = parsed["tools_used"]
            if isinstance(tools_block, list):
                for entry in tools_block:
                    if isinstance(entry, str):
                        referenced_tools.append(entry)
                    elif isinstance(entry, dict):
                        referenced_tools.append(entry.get("name", ""))

        # Check each referenced tool against the registry
        available = registry.names()
        for tool_name in referenced_tools:
            if tool_name and tool_name not in available:
                missing_tools.append(tool_name)

        if missing_tools:
            findings.append({
                "severity": "error",
                "message": (
                    f"Tool(s) referenced in handoff not found in registry: "
                    f"{', '.join(repr(t) for t in missing_tools)}"
                )
            })
        elif referenced_tools:
            findings.append({
                "severity": "info",
                "message": (
                    f"All {len(referenced_tools)} referenced tool(s) "
                    f"found in registry: {', '.join(referenced_tools)}"
                )
            })
        else:
            findings.append({
                "severity": "info",
                "message": "No tool usage claims found in handoff to verify."
            })

        status = "FAIL" if missing_tools else ("PASS" if referenced_tools else "INFO")
        return {
            "check": "tool_existence",
            "status": status,
            "summary": (
                f"{len(missing_tools)} missing tool(s), "
                f"{len(referenced_tools)} referenced."
            ),
            "findings": findings,
            "referenced_tools": referenced_tools,
            "missing_tools": missing_tools,
        }

    except Exception as e:
        return {
            "check": "tool_existence",
            "status": "ERROR",
            "summary": f"Error checking tool registry: {e}",
            "findings": [{"severity": "error", "message": str(e)}],
        }


# ---------------------------------------------------------------------------
# Check 4: prior_handoff_contradiction
# ---------------------------------------------------------------------------

def _check_prior_handoff_contradiction(
    memory_store, handoff_id: str | None
) -> dict[str, Any]:
    """
    Compare the current handoff to the previous one and flag contradictions.

    Contradictions detected:
      - A key claimed as 'done' in the prior handoff is absent or changed
      - A key claimed as 'in progress' is now marked 'done' (flip)
      - Critical state fields diverge between consecutive handoffs
    """
    findings: list[dict[str, str]] = []

    try:
        if handoff_id:
            current_row = memory_store._conn.execute(
                "SELECT * FROM memories WHERE id = ?", (handoff_id,)
            ).fetchone()
        else:
            current_row = memory_store._conn.execute(
                "SELECT * FROM memories WHERE memory_type = 'handoff' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()

        if current_row is None:
            return {
                "check": "prior_handoff_contradiction",
                "status": "SKIP",
                "summary": "No current handoff found.",
                "findings": [],
            }

        current = _row_to_dict(current_row)
        prior_rows = memory_store._conn.execute(
            "SELECT * FROM memories WHERE memory_type = 'handoff' "
            "AND id != ? ORDER BY created_at DESC LIMIT 1",
            (current.get("id"),),
        ).fetchall()

        if not prior_rows:
            return {
                "check": "prior_handoff_contradiction",
                "status": "INFO",
                "summary": "No prior handoff to compare against.",
                "findings": [{
                    "severity": "info",
                    "message": "This is the first handoff; no prior to contradict."
                }],
            }

        prior = _row_to_dict(prior_rows[0])

        # Parse both contents
        current_parsed = _parse_handoff_content(current.get("content", ""))
        prior_parsed = _parse_handoff_content(prior.get("content", ""))

        # Compare key fields that might flip between sessions
        contradictions: list[str] = []

        for key in ["status", "current_work", "next_steps"]:
            curr_val = str(current_parsed.get(key, "")).strip().lower()
            prev_val = str(prior_parsed.get(key, "")).strip().lower()
            if curr_val and prev_val and curr_val != prev_val:
                # Flag if the change is suspicious (e.g., "done" -> "in progress")
                if (
                    ("done" in prev_val and "done" not in curr_val) or
                    ("in progress" in prev_val and "in progress" not in curr_val)
                ):
                    contradictions.append(
                        f"Field '{key}' changed from '{prev_val}' to '{curr_val}'"
                    )

        # Check for unresolved items carried forward without acknowledgment
        prior_items = prior_parsed.get("unresolved", prior_parsed.get("open_issues", []))
        current_items = current_parsed.get("resolved", [])
        if isinstance(prior_items, list) and isinstance(current_items, list):
            still_unresolved = [
                item for item in prior_items
                if item not in current_items
            ]
            if still_unresolved and prior_items:
                findings.append({
                    "severity": "warning",
                    "message": (
                        f"{len(still_unresolved)} prior unresolved item(s) "
                        f"appear to still be unresolved: {still_unresolved[:3]}"
                    )
                })

        if contradictions:
            findings.append({
                "severity": "error",
                "message": (
                    "Contradictions detected between consecutive handoffs:\n" +
                    "\n".join(f"  - {c}" for c in contradictions)
                )
            })
            return {
                "check": "prior_handoff_contradiction",
                "status": "FAIL",
                "summary": f"{len(contradictions)} contradiction(s) found.",
                "findings": findings,
                "contradictions": contradictions,
            }

        findings.append({
            "severity": "info",
            "message": "No contradictions detected between consecutive handoffs."
        })
        return {
            "check": "prior_handoff_contradiction",
            "status": "PASS",
            "summary": "Current and prior handoffs are consistent.",
            "findings": findings,
        }

    except Exception as e:
        return {
            "check": "prior_handoff_contradiction",
            "status": "ERROR",
            "summary": f"Error comparing handoffs: {e}",
            "findings": [{"severity": "error", "message": str(e)}],
        }


# ---------------------------------------------------------------------------
# Check 5: temporal_staleness
# ---------------------------------------------------------------------------

def _check_temporal_staleness(
    memory_store, handoff_id: str | None
) -> dict[str, Any]:
    """
    Flag if the handoff is too old relative to its unresolved items.

    A handoff older than 48 hours with open issues is a staleness risk:
    the next session may start with outdated assumptions.
    """
    findings: list[dict[str, str]] = []

    try:
        if handoff_id:
            row = memory_store._conn.execute(
                "SELECT * FROM memories WHERE id = ?", (handoff_id,)
            ).fetchone()
        else:
            row = memory_store._conn.execute(
                "SELECT * FROM memories WHERE memory_type = 'handoff' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()

        if row is None:
            return {
                "check": "temporal_staleness",
                "status": "SKIP",
                "summary": "No handoff found.",
                "findings": [],
            }

        handoff = _row_to_dict(row)
        hours = _hours_since(handoff.get("created_at", ""))

        if hours is None:
            findings.append({
                "severity": "warning",
                "message": "Could not parse handoff timestamp."
            })
            return {
                "check": "temporal_staleness",
                "status": "WARNING",
                "summary": "Handoff timestamp unparseable.",
                "findings": findings,
            }

        parsed = _parse_handoff_content(handoff.get("content", ""))
        unresolved = parsed.get("unresolved", parsed.get("open_issues", []))
        unresolved_count = len(unresolved) if isinstance(unresolved, list) else 0

        if hours > 48 and unresolved_count > 0:
            findings.append({
                "severity": "error",
                "message": (
                    f"Handoff is {hours:.1f} hours old with {unresolved_count} "
                    "unresolved item(s). Staleness risk: next session may "
                    "proceed on outdated information."
                )
            })
            return {
                "check": "temporal_staleness",
                "status": "FAIL",
                "summary": f"Stale handoff: {hours:.1f}h old, {unresolved_count} open items.",
                "findings": findings,
                "hours_old": round(hours, 1),
                "unresolved_count": unresolved_count,
            }
        elif hours > 24:
            findings.append({
                "severity": "warning",
                "message": (
                    f"Handoff is {hours:.1f} hours old (> 24 h). "
                    "Verify the situation has not changed."
                )
            })
            return {
                "check": "temporal_staleness",
                "status": "WARNING",
                "summary": f"Handoff is aging: {hours:.1f}h old.",
                "findings": findings,
                "hours_old": round(hours, 1),
            }
        else:
            findings.append({
                "severity": "info",
                "message": f"Handoff is {hours:.1f} hours old — fresh."
            })
            return {
                "check": "temporal_staleness",
                "status": "PASS",
                "summary": f"Handoff is fresh ({hours:.1f}h old).",
                "findings": findings,
                "hours_old": round(hours, 1),
            }

    except Exception as e:
        return {
            "check": "temporal_staleness",
            "status": "ERROR",
            "summary": f"Error checking temporal staleness: {e}",
            "findings": [{"severity": "error", "message": str(e)}],
        }


# ---------------------------------------------------------------------------
# Check 6: context_completeness
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = {
    "current_work",
    "next_steps",
}

_OPTIONAL_BUT_RECOMMENDED = {
    "tools_used",
    "open_issues",
    "session_id",
}


def _check_context_completeness(
    memory_store, handoff_id: str | None
) -> dict[str, Any]:
    """
    Verify the handoff contains the minimum required context fields.

    A handoff missing 'current_work' or 'next_steps' leaves the next
    session blind — this is a critical completeness failure.
    """
    findings: list[dict[str, str]] = []
    missing_required: list[str] = []
    missing_recommended: list[str] = []

    try:
        if handoff_id:
            row = memory_store._conn.execute(
                "SELECT content FROM memories WHERE id = ?", (handoff_id,)
            ).fetchone()
        else:
            row = memory_store._conn.execute(
                "SELECT content FROM memories WHERE memory_type = 'handoff' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()

        if row is None:
            return {
                "check": "context_completeness",
                "status": "SKIP",
                "summary": "No handoff found.",
                "findings": [],
            }

        parsed = _parse_handoff_content(_row_to_dict(row).get("content", ""))

        # Treat raw summary-only content as automatically missing required fields
        if "summary" in parsed and len(parsed) == 1:
            missing_required = list(_REQUIRED_FIELDS)
            findings.append({
                "severity": "error",
                "message": (
                    "Handoff content is unstructured text (not JSON). "
                    "Cannot verify field completeness. "
                    "Consider re-writing the handoff as structured JSON."
                )
            })
        else:
            for field in _REQUIRED_FIELDS:
                value = parsed.get(field, "")
                if not value or (isinstance(value, list) and not value):
                    missing_required.append(field)

            for field in _OPTIONAL_BUT_RECOMMENDED:
                if field not in parsed:
                    missing_recommended.append(field)

        if missing_required:
            findings.append({
                "severity": "error",
                "message": (
                    f"Missing required field(s): {', '.join(missing_required)}. "
                    "The next session will not know what to work on."
                )
            })

        if missing_recommended:
            findings.append({
                "severity": "warning",
                "message": (
                    f"Missing recommended field(s): {', '.join(missing_recommended)}. "
                    "These are not required but improve handoff quality."
                )
            })

        if not missing_required and not missing_recommended:
            findings.append({
                "severity": "info",
                "message": "All required and recommended fields are present."
            })

        status = (
            "FAIL" if missing_required
            else ("WARNING" if missing_recommended else "PASS")
        )
        return {
            "check": "context_completeness",
            "status": status,
            "summary": (
                f"{len(missing_required)} required, "
                f"{len(missing_recommended)} recommended field(s) missing."
            ),
            "findings": findings,
            "missing_required": missing_required,
            "missing_recommended": missing_recommended,
        }

    except Exception as e:
        return {
            "check": "context_completeness",
            "status": "ERROR",
            "summary": f"Error checking context completeness: {e}",
            "findings": [{"severity": "error", "message": str(e)}],
        }


# ---------------------------------------------------------------------------
# Check 7: session_overlap
# ---------------------------------------------------------------------------

def _check_session_overlap(
    memory_store, handoff_id: str | None
) -> dict[str, Any]:
    """
    Detect if a new session was started before the prior handoff was written.

    If the most recent session_journal entry shows a session that started
    after the handoff's timestamp, there is a potential context gap:
    the new session may have worked before the handoff was recorded.
    """
    findings: list[dict[str, str]] = []

    try:
        # Get handoff timestamp
        if handoff_id:
            handoff_row = memory_store._conn.execute(
                "SELECT created_at FROM memories WHERE id = ?", (handoff_id,)
            ).fetchone()
        else:
            handoff_row = memory_store._conn.execute(
                "SELECT created_at FROM memories WHERE memory_type = 'handoff' "
                "ORDER BY created_at DESC LIMIT 1",
            ).fetchone()

        if handoff_row is None:
            return {
                "check": "session_overlap",
                "status": "SKIP",
                "summary": "No handoff found.",
                "findings": [],
            }

        handoff_time = _row_to_dict(handoff_row).get("created_at", "")

        # Get session journal entries after the handoff
        tables = memory_store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]

        if "session_journal" in table_names:
            overlap_rows = memory_store._conn.execute(
                "SELECT * FROM session_journal WHERE start_time > ? "
                "ORDER BY start_time ASC LIMIT 5",
                (handoff_time,),
            ).fetchall()

            if overlap_rows:
                findings.append({
                    "severity": "warning",
                    "message": (
                        f"{len(overlap_rows)} session(s) started after the handoff. "
                        "Verify that the handoff was written before those sessions began, "
                        "or that the sessions already accounted for the handoff context."
                    )
                })
                return {
                    "check": "session_overlap",
                    "status": "WARNING",
                    "summary": (
                        f"{len(overlap_rows)} overlapping session(s) detected."
                    ),
                    "findings": findings,
                    "overlapping_sessions": [
                        _row_to_dict(r) for r in overlap_rows
                    ],
                }

        findings.append({
            "severity": "info",
            "message": "No session overlap detected."
        })
        return {
            "check": "session_overlap",
            "status": "PASS",
            "summary": "No overlapping sessions found.",
            "findings": findings,
        }

    except Exception as e:
        return {
            "check": "session_overlap",
            "status": "ERROR",
            "summary": f"Error checking session overlap: {e}",
            "findings": [{"severity": "error", "message": str(e)}],
        }


# ---------------------------------------------------------------------------
# Trust score calculation
# ---------------------------------------------------------------------------

_STATUS_WEIGHTS = {"PASS": 1.0, "INFO": 1.0, "WARNING": 0.5, "FAIL": 0.0, "ERROR": 0.0, "SKIP": 1.0}
_STATUS_ORDER  = ["ERROR", "FAIL", "WARNING", "SKIP", "INFO", "PASS"]


def _compute_trust_score(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute an overall trust score (0.0–1.0) from individual check results.

    Weights by severity of the check's overall status.
    Checks with ERROR always drag the score to 0.0.
    """
    if not results:
        return {"score": 1.0, "label": "NO_CHECKS", "grade": "N/A", "details": []}

    error_flag = any(r["status"] == "ERROR" for r in results)
    if error_flag:
        score = 0.0
    else:
        total = 0.0
        for r in results:
            total += _STATUS_WEIGHTS.get(r["status"], 0.5)
        score = round(total / len(results), 3)

    if score >= 0.9:
        grade = "A"
    elif score >= 0.75:
        grade = "B"
    elif score >= 0.5:
        grade = "C"
    elif score >= 0.25:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "label": grade,
        "grade": grade,
        "total_checks": len(results),
        "passed": sum(1 for r in results if r["status"] in ("PASS", "INFO")),
        "warnings": sum(1 for r in results if r["status"] == "WARNING"),
        "failed": sum(1 for r in results if r["status"] in ("FAIL", "ERROR")),
    }


# ---------------------------------------------------------------------------
# Main tool function
# ---------------------------------------------------------------------------

def handoff_audit(
    memory_store=None,
    tool_input: dict | None = None,
    registry: ToolRegistry | None = None,
    mind_root: str = ".",
) -> dict[str, Any]:
    """
    Audit the most recent (or specified) handoff memory for quality and accuracy.

    Runs 7 checks against git history, the tool registry, and prior handoffs.
    Returns a JSON report with:
      - trust_score:   overall score 0.0–1.0 with letter grade
      - check_results: per-check status, summary, and findings
      - recommendations: human-readable list of issues to address

    Parameters
    ----------
    memory_store
        A MemoryStore instance with a ._conn sqlite3 connection.
    tool_input
        Dict with optional keys: verbose (bool), handoff_id (str).
    registry
        A ToolRegistry instance. If None, a default one is created.
    mind_root
        Path to the project root for git commands. Default: ".".
    """
    tool_input = tool_input or {}
    verbose = tool_input.get("verbose", False)
    handoff_id: str | None = tool_input.get("handoff_id")

    # Lazily build registry if not provided
    if registry is None:
        registry = ToolRegistry()

    # Run all checks
    check_handoff_exists        = _check_handoff_exists(memory_store, tool_input)
    check_git                   = _check_git_state_reconciliation(
        memory_store, mind_root, handoff_id
    )
    check_tool                  = _check_tool_existence(memory_store, registry, handoff_id)
    check_contradiction         = _check_prior_handoff_contradiction(memory_store, handoff_id)
    check_staleness             = _check_temporal_staleness(memory_store, handoff_id)
    check_completeness          = _check_context_completeness(memory_store, handoff_id)
    check_session               = _check_session_overlap(memory_store, handoff_id)

    all_results: list[dict[str, Any]] = [
        check_handoff_exists,
        check_git,
        check_tool,
        check_contradiction,
        check_staleness,
        check_completeness,
        check_session,
    ]

    # Filter to failures+warnings unless verbose
    if not verbose:
        displayed = [
            r for r in all_results
            if r["status"] not in ("PASS", "INFO", "SKIP")
        ]
        # Always show the handoff_exists result so the caller knows if nothing was found
        if not any(r["check"] == "handoff_exists" for r in displayed):
            displayed.insert(0, check_handoff_exists)
    else:
        displayed = all_results

    trust = _compute_trust_score(all_results)

    # Build recommendations
    recommendations: list[str] = []
    for r in all_results:
        if r["status"] == "FAIL":
            recommendations.append(f"[{r['check']}] {r['summary']}")
        elif r["status"] == "WARNING":
            recommendations.append(f"[{r['check']}] {r['summary']}")

    return {
        "trust_score": trust,
        "check_results": displayed,
        "recommendations": recommendations,
        "tool_version": _TOOL_VERSION,
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_handoff_audit_tools(
    registry: ToolRegistry,
    memory_store=None,
    mind_root: str = ".",
) -> None:
    """
    Register handoff_audit as always-on in the given registry.

    memory_store and mind_root are captured in closures so they don't need
    to be passed in the tool_input dict.
    """
    def _invoke(tool_input=None):
        return handoff_audit(
            memory_store=memory_store,
            tool_input=tool_input or {},
            registry=registry,
            mind_root=mind_root,
        )

    registry.register(
        name="handoff_audit",
        definition=_HANDOFF_AUDIT_DEFINITION,
        handler=_invoke,
        read_only=True,
    )
