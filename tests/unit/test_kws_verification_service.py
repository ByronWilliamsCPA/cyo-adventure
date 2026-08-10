"""Tests for the KWS verification persistence seam (``consent/service.py``).

The properties pinned here are the ones that cannot be re-established after the
fact if they are wrong in production: that the row exists before the email goes
out, that the id handed to KWS is the id the row was written under, that a
retried delivery does not rewrite a resolution, and that a delivery for the
other KWS environment never resolves this one's row.

The session is the shared ``mock_async_session`` double (an
``AsyncMock(spec=AsyncSession)``) rather than a database: these are unit tests,
and every assertion here is about call ORDER and about which fields a row
carries, neither of which needs a real transaction. The send leg, by contrast,
runs through a real ``KwsClient`` over ``httpx.MockTransport``, so the
``externalPayload`` asserted below is the one that would go on the wire.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from cyo_adventure.consent import KwsClient
from cyo_adventure.consent.service import (
    ParentVerifiedOutcome,
    VerificationStartRequest,
    has_usable_verification,
    record_parent_verified,
    start_parent_verification,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import ExternalServiceError
from cyo_adventure.db.models import KwsVerification

if TYPE_CHECKING:
    from collections.abc import Iterator
    from unittest.mock import AsyncMock

_API_ORIGIN = "https://api.kidswebservices.example"
_AUTH_ORIGIN = "https://auth.kidswebservices.example"
_TOKEN_URL = f"{_AUTH_ORIGIN}/auth/realms/kws/protocol/openid-connect/token"
_USER_ID = uuid.UUID("00000000-0000-4000-8000-00000000000a")
_START = VerificationStartRequest(
    user_id=_USER_ID,
    email="parent.under.test@example.com",
    location="US",
)


@pytest.fixture
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fully configured Test-environment integration."""
    monkeypatch.setattr(settings, "kws_environment", "test")
    monkeypatch.setattr(settings, "kws_api_origin", _API_ORIGIN)
    monkeypatch.setattr(settings, "kws_auth_origin", _AUTH_ORIGIN)
    monkeypatch.setattr(
        settings, "kws_client_id", "00000000-0000-4000-8000-000000000002"
    )
    monkeypatch.setattr(settings, "kws_api_key", SecretStr("not-a-real-api-key"))
    monkeypatch.setattr(
        settings, "kws_organization_id", "00000000-0000-4000-8000-000000000001"
    )
    monkeypatch.setattr(settings, "kws_enabled_methods", ["credit_card"])


class _SendRecorder:
    """Answers the token and send legs, recording the commit count as it goes.

    The commit count captured at the moment the send request arrives is the
    whole point: it is the only way to assert that the INSERT was DURABLE
    before the outbound call rather than merely preceding it in program
    order, which a later rollback would undo.
    """

    def __init__(self, session: AsyncMock, *, send_status: int = 200) -> None:
        """Store what to answer with and where to read the flush count from.

        Args:
            session: The mock session whose ``commit`` awaits are counted.
            send_status: The status the send leg answers with.
        """
        self.session = session
        self.send_status = send_status
        self.commits_at_send: int | None = None
        self.sent_bodies: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Answer one request.

        Args:
            request: The outbound request.

        Returns:
            httpx.Response: The scripted answer.
        """
        if str(request.url) == _TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "test-token", "expires_in": 300}
            )
        self.commits_at_send = self.session.commit.await_count
        self.sent_bodies.append(json.loads(request.content))
        return httpx.Response(self.send_status, json={})


def _client(recorder: _SendRecorder) -> KwsClient:
    """Build a client whose transport is the recorder.

    Args:
        recorder: The recorder answering both legs.

    Returns:
        KwsClient: A client wired to that recorder.
    """
    return KwsClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(recorder.handle))
    )


def _added_row(session: AsyncMock) -> KwsVerification:
    """Return the single row the service added to the session.

    Args:
        session: The mock session.

    Returns:
        KwsVerification: The added row.
    """
    assert session.add.call_count == 1
    row = session.add.call_args.args[0]
    assert isinstance(row, KwsVerification)
    return row


def _sent_row(**overrides: Any) -> KwsVerification:
    """Build an unresolved row the way the send leg would have written it.

    Args:
        **overrides: Column values to replace.

    Returns:
        KwsVerification: The row.
    """
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": _USER_ID,
        "kws_environment": "test",
        "status": "sent",
        "requested_at": datetime.now(UTC),
        "resolved_at": None,
        "transaction_id": None,
        "enabled_methods": ["credit_card"],
    }
    values.update(overrides)
    return KwsVerification(**values)


@pytest.fixture
def own_session(mock_async_session: AsyncMock) -> Iterator[MagicMock]:
    """Stand in for the short-lived session the send leg opens for itself.

    ``start_parent_verification`` takes no session: it opens and commits one of
    its own so the attempt row survives whatever the caller's request does with
    its transaction. Patching the factory rather than passing a double in is
    what keeps that structural choice under test, since a version that quietly
    went back to the caller's unit of work would never call this at all.

    Yields:
        MagicMock: The patched ``get_session`` factory.
    """
    mock_async_session.__aenter__.return_value = mock_async_session
    mock_async_session.__aexit__.return_value = False
    with patch(
        "cyo_adventure.consent.service.get_session",
        return_value=mock_async_session,
    ) as factory:
        yield factory


@pytest.mark.usefixtures("_configured", "own_session")
class TestStartOrdering:
    """The send leg's ordering, which is the correctness property here."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_row_is_committed_before_the_outbound_call(
        self, mock_async_session: AsyncMock
    ) -> None:
        """The INSERT is COMMITTED before KWS is asked to email anyone.

        Reversed, a timeout after KWS accepted the request would put a real
        email in front of a real parent with no row for the webhook to match,
        and KWS will not replay a delivery on request.

        Committed rather than merely flushed, because a flush is undone by a
        rollback: the assertion is on durability at the moment of the call, not
        on statement order, and only the first of those survives the caller
        letting the send's own error propagate.
        """
        recorder = _SendRecorder(mock_async_session)

        await start_parent_verification(_START, client=_client(recorder))

        assert recorder.commits_at_send == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_send_leg_opens_its_own_transaction(
        self, mock_async_session: AsyncMock, own_session: MagicMock
    ) -> None:
        """The row must not ride on a caller's unit of work.

        Stated separately from the ordering test above because the two fail
        independently: a version that flushed into a caller's session would
        still satisfy every ordering assertion here while losing the row on the
        rollback that a failed send provokes.
        """
        recorder = _SendRecorder(mock_async_session)

        await start_parent_verification(_START, client=_client(recorder))

        own_session.assert_called_once_with()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_persisted_id_is_the_payload_kws_receives(
        self, mock_async_session: AsyncMock
    ) -> None:
        """The row's primary key IS the externalPayload attempt id.

        Two values here rather than one would be two chances to disagree, and
        the disagreement would only surface as an unmatchable delivery.
        """
        recorder = _SendRecorder(mock_async_session)

        correlation = await start_parent_verification(_START, client=_client(recorder))

        payload = json.loads(recorder.sent_bodies[0]["externalPayload"])
        assert payload["attemptId"] == str(correlation.attempt_id)
        assert _added_row(mock_async_session).id == correlation.attempt_id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_failed_send_leaves_the_row_committed(
        self, mock_async_session: AsyncMock
    ) -> None:
        """A rejected send does not retract the record of the attempt.

        This is the case the separate transaction exists for. The service
        raises, and the raise is the caller's problem, but the INSERT is
        already committed and outside any transaction the caller can roll back.
        A 4xx is the benign shape of this; the dangerous shape is a 5xx or a
        timeout AFTER KWS accepted the request, where the email goes out and
        this row is the only thing that will ever match the webhook.
        """
        recorder = _SendRecorder(mock_async_session, send_status=400)
        client = _client(recorder)

        with pytest.raises(ExternalServiceError):
            await start_parent_verification(_START, client=client)

        assert mock_async_session.add.call_count == 1
        assert mock_async_session.commit.await_count == 1
        assert mock_async_session.rollback.await_count == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_failed_send_leaves_the_attempt_unresolved(
        self, mock_async_session: AsyncMock
    ) -> None:
        """A failed send must not be recorded as a failed VERIFICATION.

        The two are different claims and only one of them is known. If KWS
        delivered the email before failing us, the parent can still verify and
        the webhook will still arrive; marking the row ``failed`` here would
        record a false negative about that parent AND make the resolution guard
        refuse the real answer when it came. ``sent`` means "unresolved", which
        is exactly what is true.
        """
        recorder = _SendRecorder(mock_async_session, send_status=500)
        client = _client(recorder)

        with pytest.raises(ExternalServiceError):
            await start_parent_verification(_START, client=client)

        row = _added_row(mock_async_session)
        assert row.status == "sent"
        assert row.resolved_at is None


@pytest.mark.usefixtures("_configured", "own_session")
class TestStartRecordShape:
    """What the row carries, and what it must never carry."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_row_records_the_environment_and_the_guardian(
        self, mock_async_session: AsyncMock
    ) -> None:
        """Both are unrecoverable later: KWS reports neither."""
        recorder = _SendRecorder(mock_async_session)

        await start_parent_verification(_START, client=_client(recorder))

        row = _added_row(mock_async_session)
        assert row.kws_environment == "test"
        assert row.user_id == _USER_ID
        assert row.status == "sent"
        assert row.resolved_at is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_enabled_methods_snapshot_is_copied_not_referenced(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A later Control Panel change must not rewrite this row's evidence.

        The webhook reports no verification method, so this declaration is the
        only bound that will ever exist on how the parent was verified. Held by
        reference, that bound would evaporate retroactively for every row the
        moment anyone toggled a method.
        """
        recorder = _SendRecorder(mock_async_session)
        await start_parent_verification(_START, client=_client(recorder))
        row = _added_row(mock_async_session)

        monkeypatch.setattr(settings, "kws_enabled_methods", ["debit_card"])

        assert row.enabled_methods == ["credit_card"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_location_is_recorded_on_the_attempt(
        self, mock_async_session: AsyncMock
    ) -> None:
        """The location bounds how the parent could have been verified.

        It is what selects the methods KWS offers, and the parent-verified
        event reports neither it nor the method that ran, so an attempt that
        does not record it leaves no trace of either.
        """
        recorder = _SendRecorder(mock_async_session)

        await start_parent_verification(_START, client=_client(recorder))

        assert _added_row(mock_async_session).location == _START.location

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_parent_email_is_not_written_to_the_row(
        self, mock_async_session: AsyncMock
    ) -> None:
        """The address goes to KWS and nowhere else.

        Avoiding it as a join key is the entire reason the opaque correlation
        exists, so a row that quietly carried it would defeat the design while
        still passing every other test here.
        """
        recorder = _SendRecorder(mock_async_session)

        await start_parent_verification(_START, client=_client(recorder))

        row = _added_row(mock_async_session)
        stored = {
            column.name: getattr(row, column.name)
            for column in KwsVerification.__table__.columns
        }
        assert _START.email not in stored.values()


@pytest.mark.usefixtures("_configured")
class TestRecordParentVerified:
    """Resolving an attempt from an authenticated delivery."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_verified_delivery_resolves_the_row(
        self, mock_async_session: AsyncMock
    ) -> None:
        """Status, resolution time, and the vendor's transaction id all land."""
        row = _sent_row()
        mock_async_session.get.return_value = row

        handled = await record_parent_verified(
            mock_async_session,
            ParentVerifiedOutcome(
                attempt_id=row.id, verified=True, transaction_id="tx-1"
            ),
        )

        assert handled is True
        assert row.status == "verified"
        assert row.transaction_id == "tx-1"
        assert row.resolved_at is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_an_unverified_delivery_resolves_to_failed(
        self, mock_async_session: AsyncMock
    ) -> None:
        """``verified: false`` is a terminal outcome, not a missing one."""
        row = _sent_row()
        mock_async_session.get.return_value = row

        await record_parent_verified(
            mock_async_session,
            ParentVerifiedOutcome(
                attempt_id=row.id, verified=False, transaction_id="tx-2"
            ),
        )

        assert row.status == "failed"
        assert row.resolved_at is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_row_is_locked_for_update_before_it_is_resolved(
        self, mock_async_session: AsyncMock
    ) -> None:
        """Two simultaneous deliveries must serialize, not interleave.

        The status guard below is only authoritative if the reader holds the
        row while it decides, so the lock is asserted rather than assumed.
        """
        row = _sent_row()
        mock_async_session.get.return_value = row

        await record_parent_verified(
            mock_async_session,
            ParentVerifiedOutcome(
                attempt_id=row.id, verified=True, transaction_id="tx-1"
            ),
        )

        assert mock_async_session.get.await_args.kwargs["with_for_update"] is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_replayed_delivery_does_not_rewrite_the_resolution(
        self, mock_async_session: AsyncMock
    ) -> None:
        """KWS retries; the second delivery must change nothing.

        Still ``handled=True``: the delivery IS ours and is already recorded,
        so answering False would invite a retry of something already done.
        """
        resolved_at = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        row = _sent_row(
            status="verified", resolved_at=resolved_at, transaction_id="tx-first"
        )
        mock_async_session.get.return_value = row

        handled = await record_parent_verified(
            mock_async_session,
            ParentVerifiedOutcome(
                attempt_id=row.id, verified=True, transaction_id="tx-second"
            ),
        )

        assert handled is True
        assert row.transaction_id == "tx-first"
        assert row.resolved_at == resolved_at

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_an_unknown_attempt_id_is_not_handled(
        self, mock_async_session: AsyncMock
    ) -> None:
        """A foreign or replayed-after-erasure id is terminal, not an error."""
        mock_async_session.get.return_value = None

        handled = await record_parent_verified(
            mock_async_session,
            ParentVerifiedOutcome(
                attempt_id=uuid.uuid4(), verified=True, transaction_id="tx-1"
            ),
        )

        assert handled is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_delivery_from_the_other_environment_is_not_handled(
        self, mock_async_session: AsyncMock
    ) -> None:
        """A production delivery must not resolve a Test row, or vice versa.

        That column is the only thing separating sandbox noise from evidence
        about a real parent, so a cross-environment resolution would corrupt
        the one fact the record exists to carry.
        """
        row = _sent_row(kws_environment="production")
        mock_async_session.get.return_value = row

        handled = await record_parent_verified(
            mock_async_session,
            ParentVerifiedOutcome(
                attempt_id=row.id, verified=True, transaction_id="tx-1"
            ),
        )

        assert handled is False
        assert row.status == "sent"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_resolving_never_commits_the_caller_session(
        self, mock_async_session: AsyncMock
    ) -> None:
        """The webhook route's unit of work owns the commit, not this."""
        row = _sent_row()
        mock_async_session.get.return_value = row

        await record_parent_verified(
            mock_async_session,
            ParentVerifiedOutcome(
                attempt_id=row.id, verified=True, transaction_id="tx-1"
            ),
        )

        assert mock_async_session.commit.await_count == 0


class TestUsableVerification:
    """What counts as evidence, and what silently must not.

    No ``_configured`` fixture here on purpose: this reader asks nothing of
    the credentials, only of ``kws_environment`` and the two evidence
    switches, so configuring the client would obscure which setting each
    assertion actually turns on.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_test_environment_verification_is_not_usable_by_default(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A sandbox verification is an event about whoever clicked the link.

        The KWS API reports nothing that would let a Test verification be told
        apart from a real one after the fact, so the refusal has to be made
        here, at read time, on the environment recorded at write time.
        """
        monkeypatch.setattr(settings, "kws_environment", "test")
        monkeypatch.setattr(settings, "kws_accept_test_evidence", False)

        usable = await has_usable_verification(mock_async_session, (_USER_ID,))

        assert usable is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_test_refusal_never_reaches_the_database(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The refusal runs FIRST, so no ordering of the rest can leak a Test row.

        Stronger than asserting the False above: a refusal evaluated after the
        query would still return False today and would become wrong the moment
        anyone reordered the conditions or added an early return between them.
        """
        monkeypatch.setattr(settings, "kws_environment", "test")
        monkeypatch.setattr(settings, "kws_accept_test_evidence", False)

        await has_usable_verification(mock_async_session, (_USER_ID,))

        assert mock_async_session.scalar.await_count == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_an_accepted_test_verification_is_usable(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Staging opts in explicitly, or the flow could never be exercised at all."""
        monkeypatch.setattr(settings, "kws_environment", "test")
        monkeypatch.setattr(settings, "kws_accept_test_evidence", True)
        mock_async_session.scalar.return_value = uuid.uuid4()

        usable = await has_usable_verification(mock_async_session, (_USER_ID,))

        assert usable is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_candidate_adults_is_answered_without_a_query(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty set is "no" by definition, and ``IN ()`` is not worth emitting."""
        monkeypatch.setattr(settings, "kws_environment", "production")

        usable = await has_usable_verification(mock_async_session, ())

        assert usable is False
        assert mock_async_session.scalar.await_count == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_query_is_scoped_to_the_configured_environment(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other direction: a Production process must not count a Test row.

        The refusal above closes "Test rows where Test is not accepted"; this
        closes "Test rows left over from before a cutover, read by a process
        now pointed at Production". Asserted on the compiled parameters rather
        than on a returned row, because the point is that the filter is IN the
        statement, not that a particular fixture row failed to match it.
        """
        monkeypatch.setattr(settings, "kws_environment", "production")
        monkeypatch.setattr(settings, "kws_accept_test_evidence", False)
        mock_async_session.scalar.return_value = None

        await has_usable_verification(mock_async_session, (_USER_ID,))

        statement = mock_async_session.scalar.await_args.args[0]
        # dict_values rather than a set: the IN clause binds a list, which is
        # unhashable, and membership here compares by equality anyway.
        bound = statement.compile().params.values()
        assert "production" in bound
        assert "verified" in bound
        assert [_USER_ID] in bound
