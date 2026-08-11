"""Tests for ``scripts/kws_send_test_verification.py``.

``scripts/`` is not an importable package (no ``__init__.py``, by design), so
the module under test is loaded from its file path via importlib, mirroring
``tests/unit/test_backup_database.py``.

The refusals are the point of this file. This script sends real mail to a real
inbox against a rate-limited vendor, so every guard that stops it short is a
guard worth a test; the happy path is thin by comparison because the work it
delegates to is covered in ``test_kws_verification_service.py``.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cyo_adventure.core.exceptions import ExternalServiceError

if TYPE_CHECKING:
    from collections.abc import Iterator

_SPEC = importlib.util.spec_from_file_location(
    "kws_send_test_verification",
    Path(__file__).resolve().parents[2] / "scripts" / "kws_send_test_verification.py",
)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - import plumbing
    msg = "could not load scripts/kws_send_test_verification.py"
    raise RuntimeError(msg)
script = importlib.util.module_from_spec(_SPEC)
sys.modules["kws_send_test_verification"] = script
_SPEC.loader.exec_module(script)


_GUARDIAN_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _args(*, dry_run: bool = False) -> argparse.Namespace:
    """Build a parsed-command-line stand-in.

    Args:
        dry_run: Whether the run should be a dry run.

    Returns:
        argparse.Namespace: The arguments a real invocation would produce.
    """
    return argparse.Namespace(
        user_id=_GUARDIAN_ID,
        email="parent@example.com",
        location="US",
        language="en",
        dry_run=dry_run,
    )


@pytest.fixture
def test_environment() -> Iterator[None]:
    """Configure a fully-credentialed Test environment."""
    with (
        patch.object(script.settings, "kws_environment", "test"),
        patch.object(type(script.settings), "kws_configured", new=True),
    ):
        yield


@pytest.fixture
def guardian(mock_async_session: AsyncMock) -> Iterator[MagicMock]:
    """Resolve ``--user-id`` to an adult guardian row."""
    user = MagicMock()
    user.role = "guardian"
    mock_async_session.get = AsyncMock(return_value=user)
    mock_async_session.__aenter__.return_value = mock_async_session
    mock_async_session.__aexit__.return_value = False
    with patch.object(script, "get_session", return_value=mock_async_session):
        yield user


@pytest.fixture
def sender() -> Iterator[AsyncMock]:
    """Patch the service seam so no send ever leaves the test."""
    correlation = MagicMock()
    correlation.attempt_id = uuid.uuid4()
    with patch.object(
        script,
        "start_parent_verification",
        new_callable=AsyncMock,
        return_value=correlation,
    ) as started:
        yield started


class TestMaskEmail:
    """The address must never reach terminal output intact."""

    def test_an_ordinary_address_keeps_only_its_first_character(self) -> None:
        assert script._mask_email("parent@example.com") == "p***@example.com"

    def test_an_address_without_an_at_sign_is_fully_masked(self) -> None:
        # A naive slice would print the whole unparseable string, which is
        # exactly the input most likely to be a typo of a real address.
        assert script._mask_email("not-an-address") == "***"

    def test_an_address_with_an_empty_local_part_is_fully_masked(self) -> None:
        assert script._mask_email("@example.com") == "***"


class TestEnvironmentRefusal:
    """Production is refused with no override, by design."""

    def test_the_production_environment_is_refused(self) -> None:
        with (
            patch.object(script.settings, "kws_environment", "production"),
            pytest.raises(SystemExit) as excinfo,
        ):
            script._require_test_environment()
        assert excinfo.value.code == 1

    def test_the_test_environment_is_allowed(self) -> None:
        with patch.object(script.settings, "kws_environment", "test"):
            script._require_test_environment()

    def test_an_unconfigured_integration_is_refused(self) -> None:
        with (
            patch.object(type(script.settings), "kws_configured", new=False),
            pytest.raises(SystemExit) as excinfo,
        ):
            script._require_configured()
        assert excinfo.value.code == 1


@pytest.mark.asyncio
class TestResolveAdult:
    """The attempt must attribute to an existing adult."""

    async def test_an_unknown_user_is_refused(
        self, mock_async_session: AsyncMock
    ) -> None:
        mock_async_session.get = AsyncMock(return_value=None)
        mock_async_session.__aenter__.return_value = mock_async_session
        mock_async_session.__aexit__.return_value = False
        with (
            patch.object(script, "get_session", return_value=mock_async_session),
            pytest.raises(SystemExit) as excinfo,
        ):
            await script._resolve_adult(_GUARDIAN_ID)
        assert excinfo.value.code == 1

    async def test_a_child_user_is_refused(self, mock_async_session: AsyncMock) -> None:
        child = MagicMock()
        child.role = "child"
        mock_async_session.get = AsyncMock(return_value=child)
        mock_async_session.__aenter__.return_value = mock_async_session
        mock_async_session.__aexit__.return_value = False
        with (
            patch.object(script, "get_session", return_value=mock_async_session),
            pytest.raises(SystemExit) as excinfo,
        ):
            await script._resolve_adult(_GUARDIAN_ID)
        assert excinfo.value.code == 1

    async def test_a_guardian_resolves_to_its_role(self, guardian: MagicMock) -> None:
        assert await script._resolve_adult(_GUARDIAN_ID) == guardian.role


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_environment", "guardian")
class TestRun:
    """End-to-end behaviour of the script's body."""

    async def test_a_dry_run_sends_nothing(self, sender: AsyncMock) -> None:
        assert await script._run(_args(dry_run=True)) == 0
        sender.assert_not_awaited()

    async def test_a_live_run_sends_once(self, sender: AsyncMock) -> None:
        assert await script._run(_args()) == 0
        sender.assert_awaited_once()

    async def test_the_live_run_passes_the_typed_arguments_through(
        self, sender: AsyncMock
    ) -> None:
        await script._run(_args())
        request = sender.await_args.args[0]
        assert request.user_id == _GUARDIAN_ID
        assert request.email == "parent@example.com"
        assert request.location == "US"

    async def test_a_vendor_failure_exits_non_zero(self, sender: AsyncMock) -> None:
        sender.side_effect = ExternalServiceError("KWS said no")
        assert await script._run(_args()) == 1

    async def test_a_production_environment_never_reaches_the_send(
        self, sender: AsyncMock
    ) -> None:
        # The refusal has to happen before the send, not alongside it: this is
        # the assertion that would fail if the guard were ever moved below the
        # call it exists to prevent.
        args = _args()
        with (
            patch.object(script.settings, "kws_environment", "production"),
            pytest.raises(SystemExit),
        ):
            await script._run(args)
        sender.assert_not_awaited()
