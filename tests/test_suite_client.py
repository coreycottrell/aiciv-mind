"""
Tests for the aiciv-mind suite client package.

Uses respx to mock httpx calls — no live network required.

Critical test: test_token_manager_signs_decoded_bytes verifies that the
signature is computed over the base64-DECODED challenge bytes, not over
the base64 string itself. This is the most common source of auth bugs.
"""
import asyncio
import base64
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from httpx import Response

from aiciv_mind.suite.auth import CachedToken, TokenManager
from aiciv_mind.suite.client import SuiteClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_test_keypair() -> tuple[Ed25519PrivateKey, str, object, str]:
    """Return (private_key_obj, private_b64, public_key_obj, public_b64)."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )

    private_b64 = base64.b64encode(private_bytes).decode()
    public_b64 = base64.b64encode(public_bytes).decode()
    return private_key, private_b64, public_key, public_b64


AGENTAUTH_URL = "http://5.161.90.32:8700"
HUB_URL = "http://87.99.131.49:8900"
FAKE_JWT = "eyJhbGciOiJFZERTQSJ9.eyJjaXZfaWQiOiJhY2cifQ.fakesig"


def make_challenge_bytes() -> tuple[bytes, str]:
    """Return (raw_bytes, base64_of_those_bytes)."""
    raw = b"test-challenge-32-bytes-exactly!!"
    return raw, base64.b64encode(raw).decode()


# ---------------------------------------------------------------------------
# 1. TokenManager.from_keypair_file loads civ_id and private_key correctly
# ---------------------------------------------------------------------------

def test_token_manager_from_keypair_file(tmp_path: Path) -> None:
    _, private_b64, _, public_b64 = generate_test_keypair()

    keypair_data = {"civ_id": "test-civ", "public_key": public_b64, "private_key": private_b64}
    keypair_file = tmp_path / "keypair.json"
    keypair_file.write_text(json.dumps(keypair_data))

    tm = TokenManager.from_keypair_file(keypair_file, agentauth_url=AGENTAUTH_URL)

    assert tm.civ_id == "test-civ"
    assert tm._private_key_b64 == private_b64


# ---------------------------------------------------------------------------
# 2. CachedToken.is_fresh is True when > 60s remain
# ---------------------------------------------------------------------------

def test_token_manager_cached_token_is_fresh() -> None:
    now = time.time()
    token = CachedToken(
        jwt=FAKE_JWT,
        acquired_at=now,
        expires_at=now + 3600,  # 1 hour from now
    )
    assert token.is_fresh is True


# ---------------------------------------------------------------------------
# 3. CachedToken.is_fresh is False when < 60s remain
# ---------------------------------------------------------------------------

def test_token_manager_cached_token_not_fresh() -> None:
    now = time.time()
    token = CachedToken(
        jwt=FAKE_JWT,
        acquired_at=now - 3600,
        expires_at=now + 30,  # only 30 seconds left — inside the 60s buffer
    )
    assert token.is_fresh is False


def test_token_manager_cached_token_not_fresh_when_expired() -> None:
    now = time.time()
    token = CachedToken(
        jwt=FAKE_JWT,
        acquired_at=now - 3700,
        expires_at=now - 100,  # already expired
    )
    assert token.is_fresh is False


# ---------------------------------------------------------------------------
# 4. CRITICAL: TokenManager signs the base64-DECODED bytes, not the b64 string
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_manager_signs_decoded_bytes() -> None:
    """
    This test verifies the most critical correctness property of TokenManager:
    the Ed25519 signature must be computed over the raw challenge bytes
    (after base64-decoding), not over the base64 string directly.

    Strategy:
    1. Generate a real Ed25519 keypair for the test.
    2. Mock /challenge to return a known challenge value (base64-encoded).
    3. Mock /verify to capture the signature sent by TokenManager.
    4. Use the public key to verify the signature is over the DECODED bytes.
    5. Also verify the signature is NOT valid over the raw b64 string.
    """
    private_key, private_b64, public_key, public_b64 = generate_test_keypair()
    raw_challenge_bytes, challenge_b64 = make_challenge_bytes()

    captured_signature_b64: list[str] = []

    def verify_handler(request):
        body = json.loads(request.content)
        captured_signature_b64.append(body["signature"])
        return Response(200, json={"token": FAKE_JWT})

    with respx.mock:
        respx.post(f"{AGENTAUTH_URL}/challenge").mock(
            return_value=Response(
                200,
                json={"challenge_id": "chall-001", "challenge": challenge_b64},
            )
        )
        respx.post(f"{AGENTAUTH_URL}/verify").mock(side_effect=verify_handler)

        tm = TokenManager(
            civ_id="test-civ",
            private_key_b64=private_b64,
            agentauth_url=AGENTAUTH_URL,
        )
        token = await tm.get_token()
        await tm.close()

    assert token == FAKE_JWT
    assert len(captured_signature_b64) == 1

    sig_bytes = base64.b64decode(captured_signature_b64[0])

    # The signature MUST be valid over the raw (decoded) challenge bytes
    try:
        public_key.verify(sig_bytes, raw_challenge_bytes)
        signed_decoded = True
    except Exception:
        signed_decoded = False

    # The signature must NOT be valid over the base64 string itself
    try:
        public_key.verify(sig_bytes, challenge_b64.encode())
        signed_b64_string = True
    except Exception:
        signed_b64_string = False

    assert signed_decoded is True, (
        "Signature is not valid over the decoded challenge bytes — "
        "TokenManager may be signing the base64 string instead of the raw bytes"
    )
    assert signed_b64_string is False, (
        "Signature is valid over the base64 string — this is the wrong behavior. "
        "TokenManager must sign the decoded bytes."
    )


# ---------------------------------------------------------------------------
# 5. TokenManager caches token — second get_token() doesn't hit HTTP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_manager_caches_token() -> None:
    _, private_b64, _, _ = generate_test_keypair()
    _, challenge_b64 = make_challenge_bytes()

    with respx.mock as mock_router:
        challenge_route = mock_router.post(f"{AGENTAUTH_URL}/challenge").mock(
            return_value=Response(
                200,
                json={"challenge_id": "chall-001", "challenge": challenge_b64},
            )
        )
        verify_route = mock_router.post(f"{AGENTAUTH_URL}/verify").mock(
            return_value=Response(200, json={"token": FAKE_JWT})
        )

        tm = TokenManager(
            civ_id="test-civ",
            private_key_b64=private_b64,
            agentauth_url=AGENTAUTH_URL,
        )

        token1 = await tm.get_token()
        token2 = await tm.get_token()
        await tm.close()

    assert token1 == FAKE_JWT
    assert token2 == FAKE_JWT
    # Challenge and verify should each be called exactly once (cached on second call)
    assert challenge_route.call_count == 1
    assert verify_route.call_count == 1


# ---------------------------------------------------------------------------
# 6. TokenManager refreshes when token is expired
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_manager_refreshes_expired() -> None:
    _, private_b64, _, _ = generate_test_keypair()
    _, challenge_b64 = make_challenge_bytes()

    with respx.mock:
        respx.post(f"{AGENTAUTH_URL}/challenge").mock(
            return_value=Response(
                200,
                json={"challenge_id": "chall-001", "challenge": challenge_b64},
            )
        )
        respx.post(f"{AGENTAUTH_URL}/verify").mock(
            return_value=Response(200, json={"token": FAKE_JWT})
        )

        tm = TokenManager(
            civ_id="test-civ",
            private_key_b64=private_b64,
            agentauth_url=AGENTAUTH_URL,
        )

        # Inject a pre-expired cached token
        now = time.time()
        tm._token = CachedToken(
            jwt="old-expired-token",
            acquired_at=now - 3700,
            expires_at=now - 100,  # expired 100s ago
        )

        token = await tm.get_token()
        await tm.close()

    # Should have refreshed and returned the new token
    assert token == FAKE_JWT
    assert tm._token is not None
    assert tm._token.jwt == FAKE_JWT


# ---------------------------------------------------------------------------
# 7. SuiteClient.connect returns client with .auth and .hub populated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suite_client_connect(tmp_path: Path) -> None:
    _, private_b64, _, public_b64 = generate_test_keypair()
    _, challenge_b64 = make_challenge_bytes()

    keypair_data = {"civ_id": "test-civ", "public_key": public_b64, "private_key": private_b64}
    keypair_file = tmp_path / "keypair.json"
    keypair_file.write_text(json.dumps(keypair_data))

    with respx.mock:
        respx.post(f"{AGENTAUTH_URL}/challenge").mock(
            return_value=Response(
                200,
                json={"challenge_id": "chall-001", "challenge": challenge_b64},
            )
        )
        respx.post(f"{AGENTAUTH_URL}/verify").mock(
            return_value=Response(200, json={"token": FAKE_JWT})
        )

        suite = await SuiteClient.connect(
            keypair_path=keypair_file,
            agentauth_url=AGENTAUTH_URL,
            hub_url=HUB_URL,
            eager_auth=True,
        )
        await suite.close()

    assert suite.auth is not None, "suite.auth should be a TokenManager"
    assert suite.hub is not None, "suite.hub should be a HubClient"
    assert suite.auth.civ_id == "test-civ"


# ---------------------------------------------------------------------------
# 8. SuiteClient.get_token() delegates to auth.get_token()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suite_client_get_token_convenience(tmp_path: Path) -> None:
    _, private_b64, _, public_b64 = generate_test_keypair()
    _, challenge_b64 = make_challenge_bytes()

    keypair_data = {"civ_id": "test-civ", "public_key": public_b64, "private_key": private_b64}
    keypair_file = tmp_path / "keypair.json"
    keypair_file.write_text(json.dumps(keypair_data))

    with respx.mock:
        respx.post(f"{AGENTAUTH_URL}/challenge").mock(
            return_value=Response(
                200,
                json={"challenge_id": "chall-001", "challenge": challenge_b64},
            )
        )
        respx.post(f"{AGENTAUTH_URL}/verify").mock(
            return_value=Response(200, json={"token": FAKE_JWT})
        )

        suite = await SuiteClient.connect(
            keypair_path=keypair_file,
            agentauth_url=AGENTAUTH_URL,
            hub_url=HUB_URL,
            eager_auth=False,  # defer auth, then call get_token() explicitly
        )

        token = await suite.get_token()
        await suite.close()

    assert token == FAKE_JWT
