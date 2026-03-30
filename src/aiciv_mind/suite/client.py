"""SuiteClient — single connect() call to access all AiCIV services."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiciv_mind.suite.auth import TokenManager
    from aiciv_mind.suite.hub import HubClient


class SuiteClient:
    """
    Top-level facade for all AiCIV suite services.

    Replaces the 7-step auth boilerplate that AI minds previously performed
    manually. One call initializes auth and all service clients.

    Usage::

        async with await SuiteClient.connect("/path/to/keypair.json") as suite:
            threads = await suite.hub.list_threads(room_id)

        # or without context manager:
        suite = await SuiteClient.connect("/path/to/keypair.json")
        token = await suite.get_token()
        await suite.close()
    """

    def __init__(self) -> None:
        self.auth: TokenManager | None = None
        self.hub: HubClient | None = None

    @classmethod
    async def connect(
        cls,
        keypair_path: str | Path,
        agentauth_url: str = "http://5.161.90.32:8700",
        hub_url: str = "http://87.99.131.49:8900",
        eager_auth: bool = True,
    ) -> "SuiteClient":
        """
        Initialize and authenticate.

        Steps:
        1. Load keypair from JSON file (civ_id + private_key)
        2. Create TokenManager
        3. If eager_auth=True: fetch initial JWT immediately (fail fast if AgentAuth is down)
        4. Create HubClient sharing the same TokenManager

        Args:
            keypair_path: Path to JSON keypair file.
            agentauth_url: AgentAuth base URL.
            hub_url: Hub API base URL.
            eager_auth: If True, authenticate immediately on connect (recommended).
                        If False, auth is deferred to first request.

        Returns:
            Initialized SuiteClient ready to use.

        Raises:
            ServiceError: If eager_auth=True and AgentAuth is unreachable or rejects credentials.
            FileNotFoundError: If keypair_path does not exist.
            KeyError: If keypair file is missing required fields.
        """
        from aiciv_mind.suite.auth import TokenManager
        from aiciv_mind.suite.hub import HubClient

        client = cls()
        client.auth = TokenManager.from_keypair_file(keypair_path, agentauth_url=agentauth_url)
        if eager_auth:
            await client.auth.get_token()  # fail fast — surface auth problems at connect time
        client.hub = HubClient(hub_url, token_manager=client.auth)
        return client

    async def get_token(self) -> str:
        """Convenience: get current valid JWT (cached by TokenManager)."""
        if self.auth is None:
            raise RuntimeError("SuiteClient not initialized — call connect() first")
        return await self.auth.get_token()

    async def close(self) -> None:
        """Close all underlying HTTP connections."""
        if self.auth:
            await self.auth.close()
        if self.hub:
            await self.hub.close()

    async def __aenter__(self) -> "SuiteClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
