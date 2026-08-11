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
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from cyo_adventure.consent import KwsClient
from cyo_adventure.consent.service import (
    ParentVerifiedOutcome,
    VerificationStartRequest,
    attempts_since,
    has_usable_verification,
    open_attempt_started_at,
    record_parent_verified,
    reportable_verification_status,
    start_parent_verification,
    verification_delivery_health,
    verification_status,
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


class TestOpenAttemptAndAttemptCounts:
    """The two readers the anti-automation limits on ``POST /consent/kws/start``
    are built from.

    Both are deliberately laxer than ``has_usable_verification``: that one
    answers "may this evidence gate a child profile", these answer "has this
    account already caused an email to be sent". An attempt that will never
    count as evidence still consumed a real send.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_an_open_attempt_is_reported_even_when_test_evidence_is_refused(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Test-evidence refusal must NOT be copied onto this reader.

        ``has_usable_verification`` refuses a Test row because a Test
        verification is not proof of anything. That reasoning does not carry:
        an unresolved Test attempt still put a real message in a real mailbox,
        so it must still suppress a second send. Copying the refusal here
        would turn staging into an unmetered mailer.
        """
        monkeypatch.setattr(settings, "kws_environment", "test")
        monkeypatch.setattr(settings, "kws_accept_test_evidence", False)
        started = datetime.now(UTC)
        mock_async_session.scalar.return_value = started

        assert await open_attempt_started_at(mock_async_session, _USER_ID) == started
        assert mock_async_session.scalar.await_count == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_open_attempt_query_is_scoped_to_this_environment_and_sent(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only an UNRESOLVED attempt in THIS environment blocks a fresh send.

        A resolved attempt is finished business, and an attempt belonging to
        the other KWS environment can never be resolved by this process's
        webhook, so treating either as open would wedge the caller out of the
        flow for the whole window with no way to clear it.
        """
        monkeypatch.setattr(settings, "kws_environment", "production")
        mock_async_session.scalar.return_value = None

        await open_attempt_started_at(mock_async_session, _USER_ID)

        bound = mock_async_session.scalar.await_args.args[0].compile().params.values()
        assert "production" in bound
        assert "sent" in bound
        assert _USER_ID in bound

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_attempts_since_counts_every_status_and_every_environment(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The hourly cap counts SENDS, so no outcome may exempt an attempt.

        Filtering to ``sent`` would let an attacker reset their own quota by
        resolving each attempt, and filtering by environment would hand them a
        second quota after a cutover. Asserted on the compiled parameters
        because the property is the ABSENCE of those filters: only the user
        and the window may be bound.
        """
        monkeypatch.setattr(settings, "kws_environment", "production")
        mock_async_session.scalar.return_value = 4
        since = datetime.now(UTC)

        assert await attempts_since(mock_async_session, _USER_ID, since) == 4

        bound = list(
            mock_async_session.scalar.await_args.args[0].compile().params.values()
        )
        assert _USER_ID in bound
        assert since in bound
        assert "production" not in bound
        assert "sent" not in bound

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_rows_counts_as_zero_rather_than_none(
        self, mock_async_session: AsyncMock
    ) -> None:
        """``COUNT`` cannot return NULL, but a mocked or future reader can.

        The caller compares this against a cap, and ``None >= cap`` raises
        rather than refusing, so the coercion is load-bearing at the call
        site even though SQL will not exercise it.
        """
        mock_async_session.scalar.return_value = None

        assert (
            await attempts_since(mock_async_session, _USER_ID, datetime.now(UTC)) == 0
        )


class TestReportedVerificationStatus:
    """The three-valued display fact, and the flag that suppresses it."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_verified_outranks_an_open_attempt(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An adult who verified and then started another attempt is verified.

        Reporting them as pending would route a client that trusts this field
        to a wait screen that nothing will ever move them off, since the
        verification they are waiting for already happened.
        """
        monkeypatch.setattr(settings, "kws_environment", "production")
        monkeypatch.setattr(settings, "kws_verification_required", True)
        mock_async_session.scalar.return_value = uuid.uuid4()

        assert await verification_status(mock_async_session, _USER_ID) == "verified"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_flag_being_off_suppresses_the_state_entirely(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tier that ran verification and switched it off stops advertising it.

        The rows survive the flag, so the underlying fact would still read
        "verified"; a surface that reported it would point clients at a flow
        that no longer gates anything. Asserted on the query count as well,
        because the short-circuit is what keeps the flag-off tiers paying
        nothing for a feature they do not run.
        """
        monkeypatch.setattr(settings, "kws_verification_required", False)
        mock_async_session.scalar.return_value = uuid.uuid4()

        state = await reportable_verification_status(mock_async_session, _USER_ID)

        assert state == "none"
        assert mock_async_session.scalar.await_count == 0


def _delivery_row(
    session: AsyncMock,
    *,
    stuck: int,
    oldest: datetime | None = None,
    newest: datetime | None = None,
    last_resolved: datetime | None = None,
) -> None:
    """Point the session's single aggregate round trip at one result row.

    ``verification_delivery_health`` reads the count and all three timestamps
    from one aggregate row, so the double is one ``execute()`` whose result
    yields one namespace, mirroring
    ``tests/unit/test_health.py::_fake_session_with_queue_counts``.
    """
    result = MagicMock()
    result.one.return_value = SimpleNamespace(
        stuck=stuck,
        oldest=oldest,
        newest=newest,
        last_resolved=last_resolved,
    )
    session.execute.return_value = result


class TestVerificationDeliveryHealth:
    """The only signal a blocked inbound leg produces at all.

    On 2026-08-09 a Cloudflare custom rule blocked four KWS webhook retries at
    the edge. The origin logged zero POSTs, so every log-derived view of that
    outage was byte-identical to "the vendor never sent anything": there was no
    line to alert on, and no absence a log-based rule could name. The one trace
    such an outage does leave is rows that never leave ``sent``, which is why
    the alarm is a query over the table rather than a rule over the logs.

    The verdict is an ordering of two timestamps: has anything come back since
    the most recent attempt that is still waiting. The tests below pin what
    that ordering buys (an outage on a quiet tier, and a fresh outage sitting
    behind an ancient abandoned row) and what it deliberately costs (a lone
    abandoned attempt on a tier with no other traffic keeps alarming).
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_resolution_after_the_newest_waiting_attempt_is_not_an_alarm(
        self, mock_async_session: AsyncMock
    ) -> None:
        """The steady state: parents are mid-flow and the leg demonstrably works.

        At any moment some parents have an open attempt they have not acted
        on. What makes that benign is not their number but the delivery that
        landed after the most recent of them was sent.
        """
        now = datetime.now(UTC)
        _delivery_row(
            mock_async_session,
            stuck=3,
            oldest=now - timedelta(days=9),
            newest=now - timedelta(days=2),
            last_resolved=now - timedelta(hours=3),
        )

        health = await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        assert health.deliveries_have_stopped is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nothing_coming_back_since_the_newest_attempt_is_the_alarm(
        self, mock_async_session: AsyncMock
    ) -> None:
        """The Cloudflare-shaped outage: outbound fine, inbound eaten.

        Attempts are piling up unresolved and the last delivery predates all
        of them. The leg has had a chance to answer and has not.
        """
        now = datetime.now(UTC)
        _delivery_row(
            mock_async_session,
            stuck=4,
            oldest=now - timedelta(days=4),
            newest=now - timedelta(days=2),
            last_resolved=now - timedelta(days=6),
        )

        health = await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        assert health.deliveries_have_stopped is True
        assert health.stuck == 4
        assert health.oldest_stuck_requested_at is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_an_outage_on_a_quiet_tier_still_alarms(
        self, mock_async_session: AsyncMock
    ) -> None:
        """The false negative this rule exists to remove.

        The predecessor also required fresh sends inside a window, on the
        theory that stuckness without traffic is abandonment. The theory
        fails on the case that matters: a blocked inbound leg suppresses
        nothing about sends, but a tier with few parents may simply not have
        sent anything in the last day, and then the outage was silent for
        exactly as long as it was quiet. One waiting attempt older than the
        threshold, with the last delivery before it, is enough.
        """
        now = datetime.now(UTC)
        _delivery_row(
            mock_async_session,
            stuck=1,
            oldest=now - timedelta(days=3),
            newest=now - timedelta(days=3),
            last_resolved=now - timedelta(days=30),
        )

        health = await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        assert health.deliveries_have_stopped is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_an_old_abandoned_row_does_not_mask_a_fresh_outage(
        self, mock_async_session: AsyncMock
    ) -> None:
        """Why the anchor is the NEWEST waiting attempt rather than the oldest.

        An attempt abandoned months ago stays the oldest stuck row forever.
        Anchoring the comparison on it would let every resolution since then
        answer for the leg, so an outage that started yesterday would be
        cleared by evidence from months ago. Here the ancient row and a fresh
        one are both stuck, and deliveries landed in between: it is the fresh
        one the leg has to answer for.
        """
        now = datetime.now(UTC)
        _delivery_row(
            mock_async_session,
            stuck=2,
            oldest=now - timedelta(days=120),
            newest=now - timedelta(days=2),
            last_resolved=now - timedelta(days=30),
        )

        health = await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        assert health.deliveries_have_stopped is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_leg_that_has_never_delivered_is_the_alarm(
        self, mock_async_session: AsyncMock
    ) -> None:
        """No resolution has ever landed, and something is waiting.

        This is the shape a never-reachable webhook URL takes on a freshly
        wired tier: sends leave, nothing returns, and there is no earlier
        success to compare against. ``None`` must read as "the leg has not
        answered", never as "no evidence against it".
        """
        now = datetime.now(UTC)
        _delivery_row(
            mock_async_session,
            stuck=2,
            oldest=now - timedelta(days=5),
            newest=now - timedelta(days=2),
            last_resolved=None,
        )

        health = await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        assert health.deliveries_have_stopped is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_lone_abandoned_attempt_keeps_alarming_by_design(
        self, mock_async_session: AsyncMock
    ) -> None:
        """The accepted cost, pinned so a later change cannot make it silently.

        One parent who never opened their email, on a tier where nothing has
        resolved since, is indistinguishable from a broken leg on the evidence
        available: in both cases an attempt has been waiting and nothing has
        come back. The rule says so rather than guessing, and the remedy is to
        resolve the row. A change that makes this case quiet is re-introducing
        the false negative ``test_an_outage_on_a_quiet_tier_still_alarms``
        covers, and should fail that test too.
        """
        now = datetime.now(UTC)
        _delivery_row(
            mock_async_session,
            stuck=1,
            oldest=now - timedelta(days=90),
            newest=now - timedelta(days=90),
            last_resolved=None,
        )

        health = await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        assert health.deliveries_have_stopped is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nothing_waiting_is_not_an_alarm(
        self, mock_async_session: AsyncMock
    ) -> None:
        """No attempt has been outstanding long enough to be evidence.

        A tier nobody used, or one where every attempt resolved, offers the
        check nothing to speak about. Silence must read as "no evidence",
        never as "broken", however long ago the last delivery was.
        """
        _delivery_row(
            mock_async_session,
            stuck=0,
            last_resolved=datetime.now(UTC) - timedelta(days=400),
        )

        health = await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        assert health.deliveries_have_stopped is False
        assert health.oldest_stuck_requested_at is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_failed_resolution_still_counts_as_the_leg_working(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resolutions are read from ``resolved_at``, with no status filter.

        A KWS delivery reporting a REFUSED verification is still a delivery
        that reached us, so it is evidence the inbound leg works and must
        clear the alarm exactly as a success does. Asserted on the compiled
        parameters because the property is the ABSENCE of a status filter on
        that term: only ``sent`` (from the stuck filter) and the environment
        may be bound.
        """
        monkeypatch.setattr(settings, "kws_environment", "production")
        _delivery_row(mock_async_session, stuck=0)

        await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        bound = list(
            mock_async_session.execute.await_args.args[0].compile().params.values()
        )
        assert "verified" not in bound
        assert "failed" not in bound

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_the_query_is_scoped_to_this_kws_environment(
        self, mock_async_session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Staging's Test rows must not mask or manufacture a production alarm.

        The two environments have separate credentials and separate webhook
        deliveries, so a Test resolution is no evidence at all that
        production's inbound leg works. Scoping matches
        ``open_attempt_started_at``.
        """
        monkeypatch.setattr(settings, "kws_environment", "production")
        _delivery_row(mock_async_session, stuck=0)

        await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        bound = list(
            mock_async_session.execute.await_args.args[0].compile().params.values()
        )
        assert "production" in bound

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_a_null_count_coerces_to_zero(
        self, mock_async_session: AsyncMock
    ) -> None:
        """``COUNT`` cannot return NULL, but the report must not raise if it does.

        The verdict no longer reads ``stuck`` at all, so a NULL here can only
        reach an operator through the reported count. ``int(None)`` raises,
        which would turn a surprising row into an exception inside a health
        check whose whole job is to report rather than to fail.
        """
        _delivery_row(
            mock_async_session,
            stuck=None,  # pyright: ignore[reportArgumentType]
        )

        health = await verification_delivery_health(
            mock_async_session, stuck_after=timedelta(hours=24)
        )

        assert health.stuck == 0
        assert health.deliveries_have_stopped is False
