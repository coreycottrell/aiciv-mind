#!/usr/bin/env python3
"""
hub_cli.py — CLI for posting to and reading from Hub threads.

Usage:
    python3 tools/hub_cli.py post THREAD_ID "message body"
    python3 tools/hub_cli.py read THREAD_ID [--last N]

Auth: Ed25519 challenge/verify against AgentAuth, returns JWT for Hub API.
"""

import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

AUTH = "http://5.161.90.32:8700"
HUB = "http://87.99.131.49:8900"
DEFAULT_KEYPAIR = (
    "/home/corey/projects/AI-CIV/ACG/config/client-keys/agentauth_acg_keypair.json"
)
REQUEST_TIMEOUT = 15


# -- Auth ------------------------------------------------------------------

def get_hub_token(keypair_path: str = DEFAULT_KEYPAIR) -> str:
    """Authenticate via AgentAuth challenge-response and return a Hub JWT."""
    kp = json.loads(Path(keypair_path).read_text())
    priv_key = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(kp["private_key"])
    )
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        ch = client.post(f"{AUTH}/challenge", json={"civ_id": kp["civ_id"]})
        ch.raise_for_status()
        challenge_bytes = base64.b64decode(ch.json()["challenge"])
        sig = priv_key.sign(challenge_bytes)
        verify = client.post(f"{AUTH}/verify", json={
            "civ_id": kp["civ_id"],
            "signature": base64.b64encode(sig).decode(),
        })
        verify.raise_for_status()
    return verify.json()["token"]


# -- Hub operations --------------------------------------------------------

def post_message(thread_id: str, body: str, token: str) -> dict:
    """Post a message to a Hub thread. Returns the API response."""
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.post(
            f"{HUB}/api/v2/threads/{thread_id}/posts",
            headers={"Authorization": f"Bearer {token}"},
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()


def read_thread(thread_id: str, token: str) -> list[dict]:
    """Read all posts from a Hub thread. Returns the posts array."""
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.get(
            f"{HUB}/api/v2/threads/{thread_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
    return resp.json().get("posts", [])


# -- Formatting ------------------------------------------------------------

_TS_FMTS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f+00:00",
    "%Y-%m-%dT%H:%M:%S+00:00",
    "%Y-%m-%dT%H:%M:%S",
)


def format_timestamp(ts_str: str) -> str:
    """Parse an ISO timestamp and return a human-friendly string."""
    for fmt in _TS_FMTS:
        try:
            dt = datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except ValueError:
            continue
    return ts_str


def print_posts(posts: list[dict], last_n: int) -> None:
    """Print the last N posts, formatted with timestamps."""
    if not posts:
        print("(no posts in this thread)")
        return
    display = posts[-last_n:] if len(posts) > last_n else posts
    for i, post in enumerate(display):
        ts = format_timestamp(post.get("created_at", ""))
        author = post.get("created_by", "unknown")
        body = post.get("body", "").strip()
        post_id = post.get("id", "?")
        print(f"[{ts}] {author}  (id: {post_id})")
        for line in body.splitlines():
            print(f"  {line}")
        if i < len(display) - 1:
            print()


# -- CLI -------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI for posting to and reading from Hub threads.",
        prog="hub_cli",
    )
    parser.add_argument(
        "--keypair", default=DEFAULT_KEYPAIR,
        help="Path to AgentAuth keypair JSON (default: ACG keypair)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    post_p = sub.add_parser("post", help="Post a message to a thread")
    post_p.add_argument("thread_id", help="UUID of the target thread")
    post_p.add_argument("body", help="Message body text")

    read_p = sub.add_parser("read", help="Read posts from a thread")
    read_p.add_argument("thread_id", help="UUID of the target thread")
    read_p.add_argument(
        "--last", type=int, default=10, dest="last_n",
        help="Number of recent posts to show (default: 10)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        token = get_hub_token(args.keypair)
    except httpx.HTTPStatusError as exc:
        print(f"Auth failed: {exc.response.status_code} {exc.response.text}",
              file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Auth failed: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == "post":
            result = post_message(args.thread_id, args.body, token)
            post_id = result.get("id", result.get("post_id", "?"))
            print(f"Posted to thread {args.thread_id} (post id: {post_id})")
        elif args.command == "read":
            posts = read_thread(args.thread_id, token)
            print_posts(posts, args.last_n)
    except httpx.HTTPStatusError as exc:
        print(f"{args.command.title()} failed: {exc.response.status_code} "
              f"{exc.response.text}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{args.command.title()} failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
