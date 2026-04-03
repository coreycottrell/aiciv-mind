#!/usr/bin/env python3
"""
infrastructure_guard.py — Nightly infrastructure health validator.

Runs 8 checks against critical aiciv-mind systems and writes results
to data/guard_results.json.  Exit code 0 = all pass, 1 = any failure.

Usage:
    python3 tools/infrastructure_guard.py                # All checks
    python3 tools/infrastructure_guard.py --check hub    # Single check
    python3 tools/infrastructure_guard.py --json         # JSON output only

Source: BUILD-ROADMAP P2-7 (Aether Onboarding Guard pattern — #6 GRAB)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

MIND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = MIND_ROOT / "data"
RESULTS_FILE = DATA_DIR / "guard_results.json"
MEMORY_DB = DATA_DIR / "memory.db"
SKILLS_DIR = MIND_ROOT / "skills"
SCRATCHPAD_DIR = MIND_ROOT / "scratchpads"

# External service URLs (defaults — override via env)
HUB_URL = os.environ.get("AICIV_HUB_URL", "http://87.99.131.49:8900")
AGENTAUTH_URL = os.environ.get("AGENTAUTH_URL", "http://5.161.90.32:8700")
LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")


def check_hub_reachable() -> dict:
    """Check 1: Hub API responds to GET /api/rooms."""
    import urllib.request
    import urllib.error

    url = f"{HUB_URL}/api/rooms"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "aiciv-mind-guard/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return {"check": "hub_reachable", "status": "PASS", "detail": f"HTTP 200 from {url}"}
            return {"check": "hub_reachable", "status": "FAIL", "detail": f"HTTP {resp.status} from {url}"}
    except Exception as e:
        return {"check": "hub_reachable", "status": "FAIL", "detail": f"{type(e).__name__}: {e}"}


def check_agentauth_jwks() -> dict:
    """Check 2: AgentAuth JWKS endpoint responds."""
    import urllib.request
    import urllib.error

    url = f"{AGENTAUTH_URL}/.well-known/jwks.json"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "aiciv-mind-guard/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read())
                key_count = len(data.get("keys", []))
                return {"check": "agentauth_jwks", "status": "PASS", "detail": f"JWKS OK — {key_count} keys"}
            return {"check": "agentauth_jwks", "status": "FAIL", "detail": f"HTTP {resp.status}"}
    except Exception as e:
        return {"check": "agentauth_jwks", "status": "FAIL", "detail": f"{type(e).__name__}: {e}"}


def check_memory_db_integrity() -> dict:
    """Check 3: memory.db readable + not corrupted (PRAGMA integrity_check)."""
    if not MEMORY_DB.exists():
        return {"check": "memory_db_integrity", "status": "FAIL", "detail": f"DB not found: {MEMORY_DB}"}

    try:
        conn = sqlite3.connect(str(MEMORY_DB), timeout=5)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result and result[0] == "ok":
            size_mb = MEMORY_DB.stat().st_size / (1024 * 1024)
            return {"check": "memory_db_integrity", "status": "PASS", "detail": f"integrity OK, {size_mb:.1f}MB"}
        return {"check": "memory_db_integrity", "status": "FAIL", "detail": f"integrity_check returned: {result}"}
    except Exception as e:
        return {"check": "memory_db_integrity", "status": "FAIL", "detail": f"{type(e).__name__}: {e}"}


def check_litellm_proxy() -> dict:
    """Check 4: LiteLLM proxy reachable (GET /health)."""
    import urllib.request
    import urllib.error

    url = f"{LITELLM_URL}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return {"check": "litellm_proxy", "status": "PASS", "detail": f"HTTP 200 from {url}"}
            return {"check": "litellm_proxy", "status": "FAIL", "detail": f"HTTP {resp.status}"}
    except Exception as e:
        return {"check": "litellm_proxy", "status": "FAIL", "detail": f"{type(e).__name__}: {e}"}


def check_skills_directory() -> dict:
    """Check 5: Skills directory has >= 4 SKILL.md files."""
    if not SKILLS_DIR.exists():
        return {"check": "skills_directory", "status": "FAIL", "detail": f"Skills dir not found: {SKILLS_DIR}"}

    skill_files = list(SKILLS_DIR.glob("*/SKILL.md"))
    count = len(skill_files)
    if count >= 4:
        return {"check": "skills_directory", "status": "PASS", "detail": f"{count} skills found"}
    return {"check": "skills_directory", "status": "FAIL", "detail": f"Only {count} skills (need >= 4)"}


def check_recent_session() -> dict:
    """Check 6: At least 1 session in past 24h in session_journal."""
    if not MEMORY_DB.exists():
        return {"check": "recent_session", "status": "FAIL", "detail": "DB not found"}

    try:
        conn = sqlite3.connect(str(MEMORY_DB), timeout=5)
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        row = conn.execute(
            "SELECT COUNT(*) FROM session_journal WHERE start_time > ?",
            (cutoff,),
        ).fetchone()
        conn.close()
        count = row[0] if row else 0
        if count > 0:
            return {"check": "recent_session", "status": "PASS", "detail": f"{count} sessions in past 24h"}
        return {"check": "recent_session", "status": "WARN", "detail": "No sessions in past 24h"}
    except Exception as e:
        return {"check": "recent_session", "status": "FAIL", "detail": f"{type(e).__name__}: {e}"}


def check_orphaned_sessions() -> dict:
    """Check 7: No orphaned sessions older than 24h."""
    if not MEMORY_DB.exists():
        return {"check": "orphaned_sessions", "status": "FAIL", "detail": "DB not found"}

    try:
        conn = sqlite3.connect(str(MEMORY_DB), timeout=5)
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        row = conn.execute(
            "SELECT COUNT(*) FROM session_journal WHERE end_time IS NULL AND start_time < ?",
            (cutoff,),
        ).fetchone()
        conn.close()
        count = row[0] if row else 0
        if count == 0:
            return {"check": "orphaned_sessions", "status": "PASS", "detail": "No orphaned sessions"}
        return {"check": "orphaned_sessions", "status": "WARN", "detail": f"{count} orphaned sessions > 24h old"}
    except Exception as e:
        return {"check": "orphaned_sessions", "status": "FAIL", "detail": f"{type(e).__name__}: {e}"}


def check_disk_usage() -> dict:
    """Check 8: Disk usage < 90%."""
    try:
        usage = shutil.disk_usage(str(MIND_ROOT))
        pct = usage.used / usage.total * 100
        if pct < 90:
            return {"check": "disk_usage", "status": "PASS", "detail": f"{pct:.1f}% used ({usage.free // (1024**3)}GB free)"}
        return {"check": "disk_usage", "status": "FAIL", "detail": f"{pct:.1f}% used — critically low"}
    except Exception as e:
        return {"check": "disk_usage", "status": "FAIL", "detail": f"{type(e).__name__}: {e}"}


ALL_CHECKS = {
    "hub": check_hub_reachable,
    "agentauth": check_agentauth_jwks,
    "memory_db": check_memory_db_integrity,
    "litellm": check_litellm_proxy,
    "skills": check_skills_directory,
    "recent_session": check_recent_session,
    "orphaned_sessions": check_orphaned_sessions,
    "disk": check_disk_usage,
}


def run_guard(checks: list[str] | None = None, json_only: bool = False) -> dict:
    """Run specified checks (or all), write results, return output dict."""
    to_run = {k: v for k, v in ALL_CHECKS.items() if checks is None or k in checks}

    results = []
    for name, fn in to_run.items():
        start = time.monotonic()
        result = fn()
        result["duration_ms"] = round((time.monotonic() - start) * 1000)
        results.append(result)

        if not json_only:
            status = result["status"]
            icon = {"PASS": "+", "WARN": "~", "FAIL": "!"}[status]
            print(f"  [{icon}] {result['check']}: {status} — {result['detail']} ({result['duration_ms']}ms)")

    output = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks": results,
        "summary": {
            "total": len(results),
            "pass": sum(1 for r in results if r["status"] == "PASS"),
            "warn": sum(1 for r in results if r["status"] == "WARN"),
            "fail": sum(1 for r in results if r["status"] == "FAIL"),
        },
    }

    # Write results to file
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(output, indent=2))

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="aiciv-mind infrastructure guard")
    parser.add_argument("--check", choices=list(ALL_CHECKS.keys()), help="Run a single check")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    args = parser.parse_args()

    checks = [args.check] if args.check else None

    if not args.json:
        print(f"\naiciv-mind Infrastructure Guard — {datetime.utcnow().isoformat()}Z\n")

    output = run_guard(checks, json_only=args.json)

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        s = output["summary"]
        print(f"\nSummary: {s['pass']} PASS, {s['warn']} WARN, {s['fail']} FAIL")
        print(f"Results written to: {RESULTS_FILE}\n")

    # Exit code: 0 if no FAIL, 1 if any FAIL
    sys.exit(0 if output["summary"]["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
