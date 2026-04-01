"""
aiciv_mind.tools.netlify_tools — Deploy to ai-civ.com via Netlify API.

Root can deploy files to the ai-civ.com Netlify site.
Uses the Netlify REST API directly — no CLI dependency.

Safety:
  - Only deploys to the aiciv-inc site (843d1615-7086-461d-a6cf-511c1d54b6e0).
  - Netlify auth token read from NETLIFY_AUTH_TOKEN env var.
  - Deploy directory must exist and contain files.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

import httpx

from aiciv_mind.tools import ToolRegistry

NETLIFY_API = "https://api.netlify.com/api/v1"
AICIV_INC_SITE_ID = "843d1615-7086-461d-a6cf-511c1d54b6e0"
TIMEOUT_SECONDS = 60  # deploys can take a moment


def _get_netlify_token() -> str | None:
    """Get Netlify auth token from env or CLI config."""
    # Try env var first
    token = os.environ.get("NETLIFY_AUTH_TOKEN")
    if token:
        return token

    # Fall back to CLI config
    config_path = Path.home() / ".config" / "netlify" / "config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            users = config.get("users", {})
            if users:
                return list(users.values())[0].get("auth", {}).get("token")
        except Exception:
            pass
    return None


_DEPLOY_DEFINITION: dict = {
    "name": "netlify_deploy",
    "description": (
        "Deploy a directory to the ai-civ.com Netlify site. "
        "Provide the path to a directory containing the files to deploy. "
        "This creates a production deploy of the entire directory."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "deploy_dir": {
                "type": "string",
                "description": (
                    "Path to the directory to deploy. "
                    "All files in this directory will be uploaded to Netlify."
                ),
            },
            "deploy_message": {
                "type": "string",
                "description": "Deploy message for the Netlify dashboard (optional).",
            },
        },
        "required": ["deploy_dir"],
    },
}


async def _deploy_handler(tool_input: dict) -> str:
    deploy_dir = tool_input.get("deploy_dir", "").strip()
    deploy_message = tool_input.get("deploy_message", "[Root] automated deploy")

    if not deploy_dir:
        return "ERROR: No deploy_dir provided"

    deploy_path = Path(deploy_dir)
    if not deploy_path.is_dir():
        return f"ERROR: Directory not found: {deploy_dir}"

    token = _get_netlify_token()
    if not token:
        return "ERROR: No Netlify auth token. Set NETLIFY_AUTH_TOKEN in .env"

    # Build file digest: {"/path/in/site": sha1_hex}
    files: dict[str, str] = {}
    file_paths: dict[str, Path] = {}  # sha1 -> local path

    for file_path in deploy_path.rglob("*"):
        if file_path.is_file():
            rel = "/" + str(file_path.relative_to(deploy_path))
            content = file_path.read_bytes()
            sha1 = hashlib.sha1(content).hexdigest()
            files[rel] = sha1
            file_paths[sha1] = file_path

    if not files:
        return f"ERROR: No files found in {deploy_dir}"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Step 1: Create deploy with file digest
            deploy_data = {
                "files": files,
                "title": deploy_message,
            }
            r = await client.post(
                f"{NETLIFY_API}/sites/{AICIV_INC_SITE_ID}/deploys",
                headers=headers,
                json=deploy_data,
            )
            r.raise_for_status()
            deploy = r.json()

            deploy_id = deploy["id"]
            required = deploy.get("required", [])

            # Step 2: Upload required files (ones Netlify doesn't already have)
            uploaded = 0
            for sha1 in required:
                if sha1 in file_paths:
                    file_content = file_paths[sha1].read_bytes()
                    upload_headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/octet-stream",
                    }
                    ur = await client.put(
                        f"{NETLIFY_API}/deploys/{deploy_id}/files/{sha1}",
                        headers=upload_headers,
                        content=file_content,
                    )
                    ur.raise_for_status()
                    uploaded += 1

            url = deploy.get("ssl_url") or deploy.get("url", "https://ai-civ.com")
            state = deploy.get("state", "unknown")

            return (
                f"Deploy created: {deploy_id}\n"
                f"State: {state}\n"
                f"Files: {len(files)} total, {uploaded} uploaded, {len(files) - uploaded} cached\n"
                f"URL: {url}\n"
                f"Message: {deploy_message}"
            )

    except httpx.HTTPStatusError as e:
        return f"NETLIFY API ERROR {e.response.status_code}: {e.response.text[:500]}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


_STATUS_DEFINITION: dict = {
    "name": "netlify_status",
    "description": (
        "Check the current deploy status of ai-civ.com. "
        "Returns the latest deploy info including state and URL."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


async def _status_handler(tool_input: dict) -> str:
    token = _get_netlify_token()
    if not token:
        return "ERROR: No Netlify auth token. Set NETLIFY_AUTH_TOKEN in .env"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {token}"}
            r = await client.get(
                f"{NETLIFY_API}/sites/{AICIV_INC_SITE_ID}/deploys?per_page=3",
                headers=headers,
            )
            r.raise_for_status()
            deploys = r.json()

            if not deploys:
                return "No deploys found"

            lines = ["Recent deploys for ai-civ.com:\n"]
            for d in deploys[:3]:
                lines.append(
                    f"- [{d.get('state', '?')}] {d.get('title', 'untitled')} "
                    f"({d.get('created_at', '?')[:19]}) — {d.get('ssl_url', '')}"
                )
            return "\n".join(lines)

    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def register_netlify_tools(registry: ToolRegistry) -> None:
    """Register Netlify tools."""
    registry.register("netlify_deploy", _DEPLOY_DEFINITION, _deploy_handler, read_only=False)
    registry.register("netlify_status", _STATUS_DEFINITION, _status_handler, read_only=True)
