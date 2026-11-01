"""Unit tests for erasing a deleted family's external data (R2 covers, Supabase Auth)."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from pydantic import SecretStr

from cyo_adventure import erasure
from cyo_adventure.erasure import (
    ErasureTargets,
    build_purge_callback,
    delete_auth_identity,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyo_adventure.core.config import Settings

_ISSUER = "https://project.supabase.co/auth/v1"
_KEY = "service-role-key-value"
_SUBJECT = "4b1f0f6e-2f0b-4a53-9b8e-0c6d5f2a1e11"


def _settings(**overrides: object) -> Settings:
    """Stand in for Settings: delete_auth_identity reads only these two fields.

    A real ``Settings`` refuses an OIDC issuer without a full deployment
    configuration (a deliberate startup guard), which is irrelevant here.
    """
    values: dict[str, object] = {
        "oidc_issuer": _ISSUER,
        "supabase_service_role_key": SecretStr(_KEY),
    }
    values.update(overrides)
    return cast("Settings", SimpleNamespace(**values))


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """Build an HTTP client whose every request goes to ``handler``."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_delete_auth_identity_calls_the_admin_api_under_the_issuer() -> None:
    """The DELETE goes to <issuer>/admin/users/<uuid> with the service-role key."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    async with _client(handler) as client:
        assert await delete_auth_identity(_SUBJECT, _settings(), client=client) is True

    assert len(seen) == 1
    assert seen[0].method == "DELETE"
    assert str(seen[0].url) == f"{_ISSUER}/admin/users/{_SUBJECT}"
    assert seen[0].headers["authorization"] == f"Bearer {_KEY}"
    assert seen[0].headers["apikey"] == _KEY


@pytest.mark.asyncio
async def test_delete_auth_identity_treats_not_found_as_already_gone() -> None:
    """A 404 means the identity is already absent, which is the goal state."""
    async with _client(lambda _r: httpx.Response(404)) as client:
        assert await delete_auth_identity(_SUBJECT, _settings(), client=client) is True


@pytest.mark.asyncio
async def test_delete_auth_identity_reports_a_rejected_delete_as_failed() -> None:
    """A server error is a failed purge, not a success."""
    async with _client(lambda _r: httpx.Response(500)) as client:
        assert await delete_auth_identity(_SUBJECT, _settings(), client=client) is False


@pytest.mark.asyncio
async def test_delete_auth_identity_reports_a_network_error_as_failed() -> None:
    """A transport failure is contained and reported, never raised."""

    def handler(request: httpx.Request) -> httpx.Response:
        msg = "connection refused"
        raise httpx.ConnectError(msg, request=request)

    async with _client(handler) as client:
        assert await delete_auth_identity(_SUBJECT, _settings(), client=client) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "subject",
    ["../../admin/users", "guardian-a", "pending-invite:x", "", "1234"],
)
async def test_delete_auth_identity_refuses_a_non_uuid_subject(subject: str) -> None:
    """Only a UUID reaches the URL path; nothing else is ever sent."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    async with _client(handler) as client:
        assert await delete_auth_identity(subject, _settings(), client=client) is False
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"supabase_service_role_key": None},
        {"supabase_service_role_key": SecretStr("")},
        {"supabase_service_role_key": SecretStr("   ")},
        {"oidc_issuer": None},
    ],
)
async def test_delete_auth_identity_is_a_noop_when_unconfigured(
    overrides: dict[str, object],
) -> None:
    """Without the key or the issuer nothing is sent and the purge reports failure."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    async with _client(handler) as client:
        assert (
            await delete_auth_identity(_SUBJECT, _settings(**overrides), client=client)
            is False
        )
    assert seen == []


def _targets() -> ErasureTargets:
    """Two covers and two adult identities for one erased family."""
    return ErasureTargets(
        family_id=uuid.uuid4(),
        cover_keys=("s1/1-aaa.webp", "s2/1-bbb.webp"),
        auth_subjects=(_SUBJECT, "9c2e1d77-0000-4000-8000-000000000001"),
    )


@pytest.mark.asyncio
async def test_purge_callback_deletes_every_cover_and_identity() -> None:
    """Each collected cover key and auth subject is passed to its deleter once."""
    covers: list[str] = []
    identities: list[str] = []

    async def cover(key: str, _settings: Settings) -> bool:
        covers.append(key)
        return True

    async def identity(subject: str, _settings: Settings) -> bool:
        identities.append(subject)
        return True

    targets = _targets()
    purge = build_purge_callback(
        targets, _settings(), delete_cover_fn=cover, delete_identity_fn=identity
    )
    await purge()
    assert covers == list(targets.cover_keys)
    assert identities == list(targets.auth_subjects)


@pytest.mark.asyncio
async def test_purge_callback_keeps_going_after_one_delete_fails() -> None:
    """A failed cover delete does not stop the remaining covers or the identities."""
    covers: list[str] = []
    identities: list[str] = []

    async def cover(key: str, _settings: Settings) -> bool:
        covers.append(key)
        return key != "s1/1-aaa.webp"

    async def identity(subject: str, _settings: Settings) -> bool:
        identities.append(subject)
        return True

    targets = _targets()
    purge = build_purge_callback(
        targets, _settings(), delete_cover_fn=cover, delete_identity_fn=identity
    )
    await purge()
    assert covers == list(targets.cover_keys)
    assert identities == list(targets.auth_subjects)


@pytest.mark.asyncio
async def test_purge_callback_survives_a_deleter_that_raises() -> None:
    """A raising cover deleter neither stops other covers nor the identities."""
    covers: list[str] = []
    identities: list[str] = []

    async def cover(key: str, _settings: Settings) -> bool:
        covers.append(key)
        if key == "s1/1-aaa.webp":
            msg = "disk error building the client"
            raise OSError(msg)
        return True

    async def identity(subject: str, _settings: Settings) -> bool:
        identities.append(subject)
        return True

    targets = _targets()
    purge = build_purge_callback(
        targets, _settings(), delete_cover_fn=cover, delete_identity_fn=identity
    )
    await purge()
    assert covers == list(targets.cover_keys)
    assert identities == list(targets.auth_subjects)


class _SpyLogger:
    """Records the structured log calls the purge makes."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def _record(self, event: str, **fields: object) -> None:
        self.events.append((event, fields))

    error = exception = info = warning = _record


@pytest.mark.asyncio
async def test_purge_callback_logs_every_target_when_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation mid-purge re-raises after naming every target for recovery."""
    spy = _SpyLogger()
    monkeypatch.setattr(erasure, "logger", spy)

    async def cover(_key: str, _settings: Settings) -> bool:
        raise asyncio.CancelledError

    async def identity(_subject: str, _settings: Settings) -> bool:
        return True

    targets = _targets()
    purge = build_purge_callback(
        targets, _settings(), delete_cover_fn=cover, delete_identity_fn=identity
    )
    with pytest.raises(asyncio.CancelledError):
        await purge()

    ((event, fields),) = [
        e for e in spy.events if e[0] == "erasure_external_purge_incomplete"
    ]
    assert event == "erasure_external_purge_incomplete"
    assert fields["reason"] == "cancelled"
    assert fields["failed_cover_keys"] == list(targets.cover_keys)
    assert fields["failed_auth_subjects"] == list(targets.auth_subjects)
