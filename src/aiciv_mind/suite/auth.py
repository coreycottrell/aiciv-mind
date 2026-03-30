"""
TokenManager — Ed25519 challenge-response auth with JWT caching.

Async version of the AgentAuthClient.login() pattern from aiciv-suite-sdk.

CRITICAL auth flow:
    POST /challenge {"civ_id": "acg"}
    -> {"challenge_id": "...", "challenge": "<base64-encoded bytes>"}

    # Decode the base64 FIRST, sign the RAW bytes
    raw_bytes = base64.b64decode(challenge["challenge"])
    signature = private_key.sign(raw_bytes)        # raw bytes, not the b64 string
    signature_b64 = base64.b64encode(signature).decode()

    POST /verify {"civ_id": "acg", "signature": "<signature_b64>"}
    -> {"token": "<JWT>"}
"""
import asyncio
import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aiciv_mind.suite.base import BaseServiceClient, ServiceError


@dataclass
class CachedToken:
    jwt: str
    acquired_at: float  # time.time() at acquisition
    expires_at: float   # acquired_at + 3600 (1-hour TTL)

    @property
    def is_fresh(self) -> bool:
        """True if more than 60 seconds remain before expiry."""
        return time.time() < (self.expires_at - 60)


class TokenManager:
    """
    Manages JWT lifecycle for AgentAuth.

    Thread-safe via asyncio.Lock. Caches token in memory. Auto-refreshes
    before expiry (60-second buffer).

    Usage::

        tm = TokenManager.from_keypair_file("/path/to/keypair.json")
        token = await tm.get_token()   # cached on subsequent calls
        await tm.close()
    """

    def __init__(
        self,
        civ_id: str,
        private_key_b64: str,
        agentauth_url: str = "http://5.161.90.32:8700",
    ) -> None:
        self.civ_id = civ_id
        self._private_key_b64 = private_key_b64
        self._client = BaseServiceClient(agentauth_url)
        self._token: CachedToken | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def from_keypair_file(
        cls,
        keypair_path: str | Path,
        agentauth_url: str = "http://5.161.90.32:8700",
    ) -> "TokenManager":
        """
        Load keypair from JSON file and construct TokenManager.

        Expected file format::

            {"civ_id": "acg", "public_key": "<base64>", "private_key": "<base64>"}
        """
        data = json.loads(Path(keypair_path).read_text())
        return cls(
            civ_id=data["civ_id"],
            private_key_b64=data["private_key"],
            agentauth_url=agentauth_url,
        )

    async def get_token(self) -> str:
        """
        Return cached JWT if still fresh, else perform a full refresh.

        Concurrent-safe: multiple coroutines calling get_token() simultaneously
        will serialize through the lock — only one refresh occurs.
        """
        async with self._lock:
            if self._token is None or not self._token.is_fresh:
                self._token = await self._refresh()
            return self._token.jwt

    async def _refresh(self) -> CachedToken:
        """
        Full challenge-response cycle. Returns a new CachedToken.

        CRITICAL: The /challenge endpoint returns a base64-encoded bytes value.
        We must base64-DECODE it before signing. Signing the raw base64 string
        would produce a signature the server cannot verify.
        """
        # Step 1: request challenge
        challenge_data = await self._client.post(
            "/challenge",
            json={"civ_id": self.civ_id},
        )
        challenge_b64: str = challenge_data["challenge"]

        # Step 2: decode base64 -> raw bytes, then sign
        challenge_bytes = base64.b64decode(challenge_b64)  # CRITICAL: decode first
        private_bytes = base64.b64decode(self._private_key_b64)
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        signature_bytes = private_key.sign(challenge_bytes)
        signature_b64 = base64.b64encode(signature_bytes).decode()

        # Step 3: verify and receive JWT
        verify_data = await self._client.post(
            "/verify",
            json={
                "civ_id": self.civ_id,
                "signature": signature_b64,
            },
        )

        now = time.time()
        return CachedToken(
            jwt=verify_data["token"],
            acquired_at=now,
            expires_at=now + 3600,
        )

    async def close(self) -> None:
        await self._client.close()
