"""Negative-token suite for the real OIDC/Supabase JWT verification path.

ADR-009's testing strategy names this suite explicitly: expired, wrong issuer,
wrong audience, algorithm confusion, and tampered signature must all be
rejected. Every case here asserts AuthenticationError, never a silent
fallback to trusting the token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cyo_adventure.api import deps
from cyo_adventure.core.exceptions import AuthenticationError

_ISSUER = "https://example.supabase.co/auth/v1"
_AUDIENCE = "authenticated"
_SUBJECT = "9c6a6b1e-0000-4000-8000-000000000000"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class _FakeSigningKey:
    """Stand-in for jwt.PyJWK: only the .key attribute is read by jwt.decode."""

    key: object


class _FakeJwksClient:
    """Stand-in for jwt.PyJWKClient that always serves one fixed public key."""

    def __init__(self, key: object) -> None:
        """Store the public key this fake will serve for every lookup.

        Args:
            key: The public key returned to every caller.
        """
        self._key = key

    def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
        """Return the fixed signing key, ignoring the token's kid header.

        Args:
            _token: The JWT whose header would normally select a key; unused.

        Returns:
            _FakeSigningKey: The wrapper around the fixed public key.
        """
        return _FakeSigningKey(key=self._key)


@pytest.fixture(autouse=True)
def _configure_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point deps.settings at the test issuer/audience and reset the JWKS cache."""
    monkeypatch.setattr(deps.settings, "oidc_issuer", _ISSUER)
    monkeypatch.setattr(deps.settings, "oidc_audience", _AUDIENCE)
    monkeypatch.setattr(deps.settings, "oidc_jwks_url", "https://example.invalid/jwks")
    monkeypatch.setattr(
        deps,
        "_jwks_client",
        lambda: _FakeJwksClient(_PRIVATE_KEY.public_key()),
    )


def _claims(**overrides: object) -> dict[str, Any]:
    """Build a valid claim set, with keyword overrides applied on top.

    Args:
        **overrides: Claim values that replace (or extend) the valid base set.

    Returns:
        dict[str, Any]: The merged claims ready for :func:`_sign`.
    """
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "sub": _SUBJECT,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    base.update(overrides)
    return base


def _sign(
    claims: dict[str, Any], *, key: rsa.RSAPrivateKey = _PRIVATE_KEY, alg: str = "RS256"
) -> str:
    """Encode and sign the claims into a compact JWT.

    Args:
        claims: The claim set to encode.
        key: The signing key; defaults to the suite's primary RSA key.
        alg: The JWS algorithm name.

    Returns:
        str: The signed, compact-serialized token.
    """
    return jwt.encode(claims, key, algorithm=alg)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_token_returns_subject() -> None:
    """A correctly-signed, current, matching-issuer/audience token verifies."""
    token = _sign(_claims())
    assert await deps._verify_oidc_jwt(token) == _SUBJECT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expired_token_rejected() -> None:
    """A token whose exp claim is in the past fails verification."""
    now = datetime.now(UTC)
    token = _sign(_claims(iat=now - timedelta(hours=2), exp=now - timedelta(hours=1)))
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wrong_issuer_rejected() -> None:
    """A token issued by a different issuer than configured fails verification."""
    token = _sign(_claims(iss="https://attacker.example/auth/v1"))
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wrong_audience_rejected() -> None:
    """A token minted for a different audience fails verification."""
    token = _sign(_claims(aud="some-other-service"))
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tampered_signature_rejected() -> None:
    """Flipping a byte in the signature segment invalidates the token."""
    token = _sign(_claims())
    header_b64, payload_b64, signature_b64 = token.split(".")
    tampered_sig = ("A" if signature_b64[0] != "A" else "B") + signature_b64[1:]
    tampered_token = f"{header_b64}.{payload_b64}.{tampered_sig}"
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(tampered_token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wrong_signing_key_rejected() -> None:
    """A token signed by a key other than the one served by the JWKS fails."""
    token = _sign(_claims(), key=_OTHER_PRIVATE_KEY)
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_algorithm_none_rejected() -> None:
    """An unsigned alg=none token is rejected by the RS256/ES256 allowlist.

    PyJWT never falls back to a caller-supplied algorithm; the explicit
    algorithms=[...] allowlist in _verify_oidc_jwt is what defeats this
    classic JWT forgery, independent of any key material.
    """

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    claims = _claims()
    json_safe_claims = {
        key: value.timestamp() if isinstance(value, datetime) else value
        for key, value in claims.items()
    }
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps(json_safe_claims).encode())
    token = f"{header}.{payload}."
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_subject_claim_rejected() -> None:
    """A validly-signed token with no sub claim is rejected.

    With sub in the decode-time require list, this is now rejected by
    jwt.decode (MissingRequiredClaimError -> "token failed verification")
    before the manual subject check runs, so no message match is asserted.
    """
    claims = _claims()
    del claims["sub"]
    token = _sign(claims)
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_subject_claim_rejected() -> None:
    """A validly-signed token with an empty sub claim hits the manual check.

    An empty string is present, so the require list passes; the explicit
    subject check in _verify_oidc_jwt is what rejects it.
    """
    token = _sign(_claims(sub=""))
    with pytest.raises(AuthenticationError, match="subject"):
        await deps._verify_oidc_jwt(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_token_without_exp_rejected() -> None:
    """A validly-signed token missing the exp claim is rejected.

    The options={"require": [...]} allowlist in _verify_oidc_jwt forces exp to
    be present, so a non-expiring token cannot slip through verification.
    """
    claims = _claims()
    del claims["exp"]
    token = _sign(claims)
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hs256_confusion_rejected() -> None:
    """An HS256 token forged with the RSA public key as the HMAC secret fails.

    The RS256/ES256 allowlist defeats the classic algorithm-confusion attack:
    _verify_oidc_jwt never treats the asymmetric public key as an HMAC secret
    because HS256 is not accepted, so the forgery is rejected before any
    signature check. The token is hand-assembled here because PyJWT's own
    jwt.encode refuses to HMAC-sign with a PEM public key (its encode-side
    mitigation), so a real attacker's forged token must be built directly.
    """

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    public_pem = _PRIVATE_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    claims = _claims()
    json_safe_claims = {
        key: value.timestamp() if isinstance(value, datetime) else value
        for key, value in claims.items()
    }
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps(json_safe_claims).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = _b64url(hmac.new(public_pem, signing_input, hashlib.sha256).digest())
    forged = f"{header}.{payload}.{signature}"
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(forged)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jwks_fetch_failure_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A JWKS lookup failure (network, unknown kid) raises AuthenticationError."""

    class _FailingJwksClient:
        def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
            raise jwt.PyJWKClientError("no matching key found")

    def _failing_jwks_client() -> _FailingJwksClient:
        return _FailingJwksClient()

    monkeypatch.setattr(deps, "_jwks_client", _failing_jwks_client)
    token = _sign(_claims())
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_subject_trusts_token_in_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_subject bypasses verification entirely when environment=='local'."""
    monkeypatch.setattr(deps.settings, "environment", "local")
    assert await deps._resolve_subject("opaque-dev-token") == "opaque-dev-token"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resolve_subject_verifies_outside_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_subject routes to _verify_oidc_jwt when environment != 'local'."""
    monkeypatch.setattr(deps.settings, "environment", "staging")
    token = _sign(_claims())
    assert await deps._resolve_subject(token) == _SUBJECT
