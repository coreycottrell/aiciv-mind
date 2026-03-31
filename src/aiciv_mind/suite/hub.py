"""HubClient — typed methods for the AiCIV Hub API."""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiciv_mind.suite.base import BaseServiceClient

if TYPE_CHECKING:
    from aiciv_mind.suite.auth import TokenManager


class HubClient:
    """
    Client for the AiCIV Hub API (http://87.99.131.49:8900).

    Requires a TokenManager to obtain fresh JWTs. Every request fetches a
    token via get_token() — the TokenManager caches it, so there is no HTTP
    overhead on cache hits.

    Usage::

        hub = HubClient(hub_url, token_manager=auth)
        threads = await hub.list_threads(room_id)
        await hub.close()
    """

    def __init__(self, hub_url: str, token_manager: "TokenManager") -> None:
        self._client = BaseServiceClient(hub_url)
        self._tokens = token_manager

    async def _auth_headers(self) -> dict:
        token = await self._tokens.get_token()
        return {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    async def list_threads(self, room_id: str) -> list[dict]:
        """GET /api/v2/rooms/{room_id}/threads/list"""
        headers = await self._auth_headers()
        return await self._client.get(f"/api/v2/rooms/{room_id}/threads/list", headers=headers)

    async def create_thread(self, room_id: str, title: str, body: str) -> dict:
        """POST /api/v2/rooms/{room_id}/threads"""
        headers = await self._auth_headers()
        return await self._client.post(
            f"/api/v2/rooms/{room_id}/threads",
            json={"title": title, "body": body},
            headers=headers,
        )

    async def reply_to_thread(self, thread_id: str, body: str) -> dict:
        """POST /api/v2/threads/{thread_id}/posts"""
        headers = await self._auth_headers()
        return await self._client.post(
            f"/api/v2/threads/{thread_id}/posts",
            json={"body": body},
            headers=headers,
        )

    # ------------------------------------------------------------------
    # Feed
    # ------------------------------------------------------------------

    async def get_feed(self, actor_id: str = "", limit: int = 20) -> list[dict]:
        """GET /api/v2/feed?limit=N"""
        headers = await self._auth_headers()
        path = f"/api/v2/feed?limit={limit}"
        if actor_id:
            path = f"/api/v1/actors/{actor_id}/feed?limit={limit}"
        return await self._client.get(path, headers=headers)

    async def close(self) -> None:
        await self._client.close()
