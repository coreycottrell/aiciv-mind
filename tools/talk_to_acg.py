#!/usr/bin/env python3
"""
talk_to_acg.py — Let aiciv-mind instances talk directly to ACG Primary.

Injects messages into ACG's tmux pane via the same mechanism the TG bridge uses.
Root (and any aiciv-mind) can call this to ask ACG questions, report status, or request help.

Usage:
  python3 tools/talk_to_acg.py "Root here. IPC is working. What should I focus on next?"
  python3 tools/talk_to_acg.py --from root "Status update: 6/6 team leads operational."
"""
import subprocess
import sys
import os
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

ACG_PANE_FILE = Path("/home/corey/projects/AI-CIV/ACG/.current_pane")
ACG_TG_PANE_FILE = Path("/home/corey/projects/AI-CIV/ACG/.tg_sessions/primary_pane_id")
COREY_CHAT_ID = 437939400
ACG_TG_BOT_TOKEN = os.environ.get("ACG_TG_BOT_TOKEN", "8388754468:AAEROakhpBPR1KNHjravHx3CIMH-FIyIWEc")

def get_acg_pane() -> str:
    """Find ACG Primary's tmux pane ID."""
    for f in [ACG_PANE_FILE, ACG_TG_PANE_FILE]:
        if f.exists():
            pane = f.read_text().strip()
            if pane:
                return pane
    return "%0"  # fallback

def inject_message(message: str, sender: str = "aiciv-mind") -> bool:
    """Inject a message into ACG's tmux pane."""
    pane = get_acg_pane()

    # Format the message with sender tag
    formatted = f"[AICIV-MIND from:{sender}] {message}"

    # Escape for tmux
    formatted = formatted.replace('"', '\\"').replace("'", "\\'")

    # Inject via tmux send-keys (same pattern as TG bridge)
    try:
        # Send the message
        subprocess.run(
            ["tmux", "send-keys", "-t", pane, formatted, "Enter"],
            check=True, timeout=5
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Failed to inject into ACG pane {pane}: {e}", file=sys.stderr)
        return False

def notify_corey(message: str, sender: str = "root"):
    """Send a copy of the message to Corey on Telegram via ACG's bot."""
    try:
        text = f"🤖 [{sender}→ACG] {message}"
        if len(text) > 4000:
            text = text[:3997] + "..."
        url = f"https://api.telegram.org/bot{ACG_TG_BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": COREY_CHAT_ID, "text": text}).encode()
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        urlopen(req, timeout=5)
    except (URLError, OSError) as e:
        print(f"TG notify failed (non-fatal): {e}", file=sys.stderr)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Talk to ACG Primary via tmux injection")
    parser.add_argument("message", nargs="?", help="Message to send")
    parser.add_argument("--from", dest="sender", default="root", help="Sender name (default: root)")
    args = parser.parse_args()

    if not args.message:
        # Read from stdin
        args.message = sys.stdin.read().strip()

    if not args.message:
        print("No message provided", file=sys.stderr)
        sys.exit(1)

    success = inject_message(args.message, args.sender)
    if success:
        print(f"Sent to ACG (pane {get_acg_pane()})")
    else:
        print("Failed to reach ACG", file=sys.stderr)
        sys.exit(1)

    # Also notify Corey on Telegram so he can see Root's messages
    notify_corey(args.message, args.sender)

if __name__ == "__main__":
    main()
