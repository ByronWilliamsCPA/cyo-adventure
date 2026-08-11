"""Integration tests for ``POST /api/v1/consent/kws/start`` (ADR-018 D1).

This endpoint is unusual in two ways that the tests below exist to pin.

It authenticates WITHOUT requiring an active account, because the ratified
sign-in order puts verification before admin approval and
``deps.require_principal`` refuses any non-``active`` user. So its caller is,
by design, an account no other guardian route will serve.

And it causes an outbound email to a real person, which makes it the one
guardian-facing write path where the anti-automation limits are the security
control rather than a nicety. Those limits are exercised here against a real
Postgres, because they are counted from the ``kws_verification`` table itself:
an in-process counter would prove nothing about a multi-replica deployment.

Only the outbound HTTP send is stubbed. The attempt row, its commit ordering,
the row-level lock that serializes concurrent starts, and every limit read run
for real.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from cyo_adventure.api import deps
from cyo_adventure.api.deps import OnboardingIdentity
from cyo_adventure.app import app
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import ExternalServiceError
from cyo_adventure.db.models import KwsVerification, User

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from .conftest import Seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_START = "/api/v1/consent/kws/start"
_ONBOARDING = "/api/v1/onboarding"
_SUBJECT = "verifying-guardian"
_EMAIL = "parent.under.test@example.com"
_BODY: dict[str, object] = {"location": "US", "language": "en"}


class _SendRecorder:
    """Stands in for ``KwsClient``, recording what would have gone on the wire.

    Substituted for the class rather than for ``start_parent_verification``,
    so the attempt row is still INSERTed and COMMITTED on its own session by
    the real code path. Every count these tests assert on is therefore a count
    of rows the production writer produced.
    """

    def __init__(self) -> None:
        self.emails: list[str] = []
        self.fail_with: Exception | None = None

    def __call__(self, *_args: Any, **_kwargs: Any) -> _SendRecorder:
        """Answer the ``KwsClient()`` construction inside the service.

        Args:
            *_args: Ignored positional construction arguments.
            **_kwargs: Ignored keyword construction arguments.

        Returns:
            _SendRecorder: This same recorder, so one instance accumulates
                every send across a test.
        """
        return self

    async def send_verification_email(self, request: Any, *, correlation: Any) -> None:
        """Record the recipient, or raise the configured failure.

        Args:
            request: The ``VerificationEmailRequest`` the service built.
            correlation: The attempt correlation token. Unused.

        Raises:
            Exception: Whatever ``fail_with`` holds, to exercise the
                "row survives a failed send" path.
        """
        _ = correlation
        self.emails.append(request.email)
        if self.fail_with is not None:
            raise self.fail_with


@pytest.fixture
def sends(
    monkeypatch: pytest.MonkeyPatch, sessions: async_sessionmaker[AsyncSession]
) -> _SendRecorder:
    """Point the send leg's own session at the test database, and stub its client.

    ``start_parent_verification`` deliberately opens a session of its OWN
    rather than joining the request unit of work, so overriding the request-
    scoped ``get_db`` dependency (which the ``client`` fixture does) does not
    reach it. Left alone it would write the attempt row to whatever database
    the ambient configuration names, and every row assertion below would read
    an empty test database and pass for the wrong reason.

    Args:
        monkeypatch: The patcher.
        sessions: The test engine's session factory, substituted for
            ``get_session``: both are zero-argument callables returning an
            ``AsyncSession`` usable as an async context manager.

    Returns:
        _SendRecorder: The recorder every send in this test lands in.
    """
    monkeypatch.setattr("cyo_adventure.consent.service.get_session", sessions)
    monkeypatch.setattr(settings, "kws_environment", "test")
    monkeypatch.setattr(settings, "kws_api_origin", "https://api.kws.example")
    monkeypatch.setattr(settings, "kws_organization_id", str(uuid.uuid4()))
    monkeypatch.setattr(settings, "kws_client_id", str(uuid.uuid4()))
    monkeypatch.setattr(settings, "kws_api_key", SecretStr("not-a-real-kws-key"))
    monkeypatch.setattr(settings, "kws_enabled_methods", ["credit_card"])
    # The endpoint is gated on this flag, not on credential presence: a tier
    # holding credentials is not thereby a tier that runs verification. Every
    # test below except the two that pin the gate itself describes a tier that
    # does, so it is set here rather than repeated in each of them.
    monkeypatch.setattr(settings, "kws_verification_required", True)
    recorder = _SendRecorder()
    monkeypatch.setattr("cyo_adventure.consent.service.KwsClient", recorder)
    return recorder


@pytest.fixture
def as_guardian() -> Iterator[None]:
    """Authenticate every request in the test as one verified, emailed subject.

    The local dev token seam supplies no email claim, and the recipient is
    taken from the token before the stored copy, so an override is the only
    way to exercise the ordinary case.

    Yields:
        None: For the duration of the override.
    """

    def _identity() -> OnboardingIdentity:
        return OnboardingIdentity(subject=_SUBJECT, email=_EMAIL)

    app.dependency_overrides[deps.require_onboarding_identity] = _identity
    try:
        yield
    finally:
        app.dependency_overrides.pop(deps.require_onboarding_identity, None)


async def _provision(client: AsyncClient) -> uuid.UUID:
    """Create the caller's guardian row via the ordinary onboarding path.

    Args:
        client: The test HTTP client, already authenticated by ``as_guardian``.

    Returns:
        uuid.UUID: The provisioned user's id.
    """
    resp = await client.post(_ONBOARDING, json={})
    assert resp.status_code == 201
    return uuid.UUID(cast("dict[str, str]", resp.json())["user_id"])


async def _attempts(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> list[KwsVerification]:
    """Return every attempt row for one user, oldest first.

    Args:
        sessions: The session factory.
        user_id: The adult to read.

    Returns:
        list[KwsVerification]: The rows.
    """
    async with sessions() as session:
        rows = await session.scalars(
            select(KwsVerification)
            .where(KwsVerification.user_id == user_id)
            .order_by(KwsVerification.requested_at)
        )
        return list(rows)


async def _add_attempts(
    sessions: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    count: int,
    *,
    status: str,
) -> None:
    """Insert resolved attempt rows directly, bypassing the endpoint.

    Used to reach the hourly cap without tripping the open-attempt refusal
    first: the two limits are checked in order, so a ``sent`` row would answer
    409 and the cap would never be reached.

    Args:
        sessions: The session factory.
        user_id: The adult the attempts belong to.
        count: How many rows to insert.
        status: The terminal status to record.
    """
    now = datetime.now(UTC)
    async with sessions() as session:
        for index in range(count):
            requested = now - timedelta(minutes=index + 1)
            session.add(
                KwsVerification(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    kws_environment=settings.kws_environment,
                    status=status,
                    requested_at=requested,
                    resolved_at=requested,
                    enabled_methods=["credit_card"],
                    location="US",
                )
            )
        await session.commit()


@pytest.mark.usefixtures("as_guardian")
class TestStartIsGatedOnTheFlag:
    """What decides whether this tier may email a parent at all.

    Credential presence is a fact about the deployment; running verification
    is a decision. These two tests are the only ones in this file that
    describe a tier which holds KWS credentials without having made that
    decision, which is why they undo the ``sends`` fixture's flag.
    """

    async def test_start_is_refused_while_verification_is_not_required(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """Credentials alone must not open an endpoint that discloses an email.

        The endpoint hands an adult's address to Epic (ADR-018 D1, O-125). On
        a tier where ``kws_verification_required`` is off nothing consumes the
        answer, so the disclosure buys nothing and must not happen. Nothing is
        sent AND no row is written: a refusal that still burned the hourly cap
        would be a denial-of-service on the guardian.
        """
        _ = seed
        user_id = await _provision(client)
        monkeypatch.setattr(settings, "kws_verification_required", False)

        resp = await client.post(_START, json=_BODY)

        assert resp.status_code == 400
        assert sends.emails == []
        assert await _attempts(sessions, user_id) == []

    async def test_the_test_plan_override_re_opens_start_while_not_required(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """Staging can still prove the endpoint, and only via its own flag.

        Proving the flow before it becomes a control means sending a real
        email on a tier where verification gates nothing. That is the one
        legitimate reading of the combination, so it gets its own separately
        auditable setting rather than a wider reading of ``kws_configured``.
        ``config.py`` refuses this variable outright against Production KWS.

        Note the narrow scope: the Gate 1 runbook procedure calls
        ``start_parent_verification`` directly and never reaches this
        endpoint, so what this flag buys is the endpoint's own surface (its
        allowlist, its two limits) and the screens that consume it.
        """
        _ = seed
        _ = await _provision(client)
        monkeypatch.setattr(settings, "kws_verification_required", False)
        monkeypatch.setattr(settings, "kws_allow_start_while_not_required", True)

        resp = await client.post(_START, json=_BODY)

        assert resp.status_code == 202
        assert sends.emails == [_EMAIL]


@pytest.mark.usefixtures("as_guardian")
class TestStartHappyPath:
    """What one well-formed call produces."""

    async def test_a_start_sends_once_and_records_one_attempt(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """202, one email, one row, and the response names that row.

        202 rather than 201 on purpose: what the call achieves is an attempt
        in flight. Only the webhook ever turns it into a verified parent.
        """
        _ = seed
        user_id = await _provision(client)

        resp = await client.post(_START, json=_BODY)

        assert resp.status_code == 202
        payload = cast("dict[str, str]", resp.json())
        assert payload["status"] == "sent"
        rows = await _attempts(sessions, user_id)
        assert len(rows) == 1
        assert str(rows[0].id) == payload["attempt_id"]
        assert sends.emails == [_EMAIL]

    async def test_the_reported_start_time_is_the_row_the_limiter_reads(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """``requested_at`` is read back from the row, not the handler's clock.

        The client counts the resend window from this value and the endpoint
        refuses a resend by comparing against the column. Reporting an earlier
        clock reading would let a correct client offer a resend that the
        server then rejects with 409.
        """
        _ = seed, sends
        user_id = await _provision(client)

        resp = await client.post(_START, json=_BODY)

        assert resp.status_code == 202
        reported = datetime.fromisoformat(
            cast("dict[str, str]", resp.json())["requested_at"]
        )
        rows = await _attempts(sessions, user_id)
        assert reported == rows[0].requested_at

    async def test_the_body_cannot_choose_the_recipient(
        self, client: AsyncClient, seed: Seed, sends: _SendRecorder
    ) -> None:
        """An ``email`` in the body is refused outright, not quietly ignored.

        The schema forbids extras, so the endpoint has no field a caller could
        aim at a third party. Silently dropping an unknown field would leave a
        caller believing they had chosen the recipient and would make a later
        addition of such a field indistinguishable from today's behaviour.
        """
        _ = seed
        await _provision(client)

        resp = await client.post(_START, json={**_BODY, "email": "victim@example.com"})

        assert resp.status_code == 422
        assert sends.emails == []


@pytest.mark.usefixtures("as_guardian")
class TestStartLimits:
    """The three bounds that stand between a valid token and a mailer."""

    async def test_an_unresolved_attempt_refuses_a_second_send(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """409 while an attempt is still open, and no second email goes out.

        This is the bound that catches the ordinary case, a double-click or a
        retry loop, and it is stated as a state conflict rather than a rate
        limit because the caller's own outstanding attempt is what blocks
        them; the answer changes when that attempt resolves or ages out.
        """
        _ = seed
        user_id = await _provision(client)
        assert (await client.post(_START, json=_BODY)).status_code == 202

        resp = await client.post(_START, json=_BODY)

        assert resp.status_code == 409
        assert len(await _attempts(sessions, user_id)) == 1
        assert sends.emails == [_EMAIL]

    async def test_start_refuses_once_the_hourly_cap_is_reached(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """429 once the rolling-hour count is spent, even with nothing open.

        Resolved attempts clear the 409 above but must still count here, or a
        caller who completes verification could immediately spend an unbounded
        number of further sends.
        """
        _ = seed
        monkeypatch.setattr(settings, "kws_start_max_attempts_per_hour", 2)
        user_id = await _provision(client)
        await _add_attempts(sessions, user_id, 2, status="verified")

        resp = await client.post(_START, json=_BODY)

        assert resp.status_code == 429
        assert len(await _attempts(sessions, user_id)) == 2
        assert sends.emails == []

    async def test_a_failed_attempt_still_counts_against_the_hourly_cap(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The cap counts SENDS, so no outcome may exempt an attempt.

        A cap that only counted successes would let an attacker reset their
        own quota by driving attempts to a terminal failure, which is the one
        outcome they can influence from outside.
        """
        _ = seed
        monkeypatch.setattr(settings, "kws_start_max_attempts_per_hour", 2)
        user_id = await _provision(client)
        await _add_attempts(sessions, user_id, 2, status="failed")

        resp = await client.post(_START, json=_BODY)

        assert resp.status_code == 429
        assert sends.emails == []

    async def test_a_send_that_raises_still_leaves_a_counted_row(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """A 5xx from KWS is exactly when the email may have gone out anyway.

        The row is committed before the outbound call precisely so this case
        leaves evidence. If the failure rolled the row back, the retry it
        invites would be unmetered, and a delivered email would have no row
        for the webhook to match.
        """
        _ = seed
        user_id = await _provision(client)
        sends.fail_with = ExternalServiceError("KWS is down", service_name="kws")

        resp = await client.post(_START, json=_BODY)

        # 400 rather than a 5xx, because ``app.py::_status_for`` has no entry
        # for ExternalServiceError and falls back to 400 app-wide (pinned by
        # tests/unit/test_app.py::test_external_service_error_falls_back_to_400).
        # Asserted as-is rather than corrected here: the mapping predates this
        # endpoint and every provider-backed route shares it. The property
        # under test is the row, not the code.
        assert resp.status_code == 400
        rows = await _attempts(sessions, user_id)
        assert len(rows) == 1
        assert rows[0].status == "send_failed"
        assert rows[0].resolved_at is not None

    async def test_a_send_failure_does_not_block_an_immediate_retry(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """The whole point of ``send_failed`` having its own status.

        The resend guard refuses while an attempt is open, which is right for
        an email in flight and wrong for one that never left: the guardian
        could do nothing but wait out the cooldown for a failure that was ours.
        Closing the row out re-opens the retry immediately. The hourly cap is
        deliberately NOT refunded, so this stays bounded: the retry is allowed,
        an unbounded loop of them is not.
        """
        _ = seed
        user_id = await _provision(client)
        sends.fail_with = ExternalServiceError("KWS is down", service_name="kws")
        failed = await client.post(_START, json=_BODY)
        assert failed.status_code == 400

        sends.fail_with = None
        retry = await client.post(_START, json=_BODY)

        assert retry.status_code == 202
        rows = await _attempts(sessions, user_id)
        assert sorted(row.status for row in rows) == ["send_failed", "sent"]
        # Both attempts reached the send seam. The first one's failure was the
        # send itself, not a refusal upstream of it, so this distinguishes the
        # fix from a resend guard that merely let the second request past.
        assert sends.emails == [_EMAIL, _EMAIL]

    async def test_two_concurrent_starts_do_not_both_send(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """The ``FOR UPDATE`` lock is what makes the limits mean anything.

        Without it both requests read an empty history before either writes,
        and the cap bounds nothing at the exact moment it is most needed. Two
        real requests over two real connections are the only way to show it:
        the loser must block on the caller's own user row until the winner's
        unit of work commits, and then see the attempt the winner recorded.
        """
        _ = seed
        user_id = await _provision(client)

        first, second = await asyncio.gather(
            client.post(_START, json=_BODY),
            client.post(_START, json=_BODY),
        )

        assert sorted([first.status_code, second.status_code]) == [202, 409]
        assert len(await _attempts(sessions, user_id)) == 1
        assert sends.emails == [_EMAIL]


class TestStartAuthorization:
    """Who may call at all."""

    @pytest.mark.usefixtures("as_guardian")
    async def test_an_account_that_has_not_onboarded_is_refused(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """A verified token with no user row cannot send.

        The row is where the limits are counted from, so serving a caller
        without one would mean sending with no quota attached to anybody.
        """
        _ = seed
        before = await _count(sessions)

        resp = await client.post(_START, json=_BODY)

        assert resp.status_code == 400
        assert await _count(sessions) == before
        assert sends.emails == []

    async def test_a_child_row_cannot_start_a_verification(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """403 for a child row holding an adult-audience token.

        ``require_onboarding_identity`` already refuses a child SESSION token
        by audience. This is the second, role-based gate behind it, and it is
        the one that holds if any adult-audience token ever resolves to a
        child row.
        """
        _ = seed
        subject = "child-shaped-subject"
        async with sessions() as session:
            family_id = await session.scalar(select(User.family_id).limit(1))
            assert family_id is not None
            session.add(
                User(
                    family_id=family_id,
                    role="child",
                    status="active",
                    authn_subject=subject,
                    email=_EMAIL,
                )
            )
            await session.commit()

        def _identity() -> OnboardingIdentity:
            return OnboardingIdentity(subject=subject, email=_EMAIL)

        app.dependency_overrides[deps.require_onboarding_identity] = _identity
        try:
            resp = await client.post(_START, json=_BODY)
        finally:
            app.dependency_overrides.pop(deps.require_onboarding_identity, None)

        assert resp.status_code == 403
        assert sends.emails == []

    async def test_a_deactivated_guardian_cannot_start_a_verification(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """403 for a revoked adult who still holds a valid token.

        ``require_principal`` would have refused this caller on status alone,
        but this endpoint deliberately does not use it: verification sits
        before admin approval, so an active-only dependency would lock out the
        guardians it exists for. That relaxation has to be a narrowing rather
        than a removal.

        The gap is reachable because app-level deactivation does not revoke
        the Supabase JWT. Without the allowlist, a guardian an admin had just
        revoked could still make KWS mail a real person in our name, spend the
        hourly cap, and hold the open-attempt window against the account.
        """
        _ = seed
        subject = "deactivated-guardian-subject"
        async with sessions() as session:
            family_id = await session.scalar(select(User.family_id).limit(1))
            assert family_id is not None
            session.add(
                User(
                    family_id=family_id,
                    role="guardian",
                    status="deactivated",
                    authn_subject=subject,
                    email=_EMAIL,
                )
            )
            await session.commit()

        def _identity() -> OnboardingIdentity:
            return OnboardingIdentity(subject=subject, email=_EMAIL)

        app.dependency_overrides[deps.require_onboarding_identity] = _identity
        try:
            resp = await client.post(_START, json=_BODY)
        finally:
            app.dependency_overrides.pop(deps.require_onboarding_identity, None)

        assert resp.status_code == 403
        assert sends.emails == []

    async def test_a_guardian_awaiting_approval_can_start_a_verification(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
    ) -> None:
        """The allowlist must not close the case the endpoint was built for.

        The counterpart to the refusal above. A self-signup guardian lands on
        ``awaiting_approval`` and has to verify from there, so a fix that only
        admitted ``active`` would trade one defect for a worse one: nobody
        could ever complete first-time verification. This is what keeps the
        allowlist honest.
        """
        _ = seed
        subject = "awaiting-approval-guardian-subject"
        async with sessions() as session:
            family_id = await session.scalar(select(User.family_id).limit(1))
            assert family_id is not None
            session.add(
                User(
                    family_id=family_id,
                    role="guardian",
                    status="awaiting_approval",
                    authn_subject=subject,
                    email=_EMAIL,
                )
            )
            await session.commit()

        def _identity() -> OnboardingIdentity:
            return OnboardingIdentity(subject=subject, email=_EMAIL)

        app.dependency_overrides[deps.require_onboarding_identity] = _identity
        try:
            resp = await client.post(_START, json=_BODY)
        finally:
            app.dependency_overrides.pop(deps.require_onboarding_identity, None)

        assert resp.status_code == 202
        assert sends.emails == [_EMAIL]

    @pytest.mark.usefixtures("as_guardian")
    async def test_an_unconfigured_tier_refuses_before_writing_a_row(
        self,
        client: AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        seed: Seed,
        sends: _SendRecorder,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No credentials means no attempt row, not an unsendable one.

        ``kws_client.py`` raises the same error, but only after the row has
        been committed, which would leave a permanently unresolvable ``sent``
        row on every tier that never configured KWS at all.
        """
        _ = seed, sends
        await _provision(client)
        monkeypatch.setattr(settings, "kws_api_origin", None)
        before = await _count(sessions)

        resp = await client.post(_START, json=_BODY)

        assert resp.status_code == 400
        assert await _count(sessions) == before


async def _count(sessions: async_sessionmaker[AsyncSession]) -> int:
    """Count every attempt row in the database.

    Args:
        sessions: The session factory.

    Returns:
        int: The row count.
    """
    async with sessions() as session:
        return int(
            await session.scalar(select(func.count()).select_from(KwsVerification)) or 0
        )
