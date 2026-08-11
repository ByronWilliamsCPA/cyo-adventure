"""Integration tests for JIT guardian onboarding (P6-03).

Exercises ``POST /api/v1/onboarding`` end-to-end against a real Postgres:
first-login provisioning, idempotent retry, admin non-provisioning, email
capture, and the auth boundary (missing bearer, child session token).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import func, select

from cyo_adventure.api import deps, onboarding
from cyo_adventure.api.deps import OnboardingIdentity
from cyo_adventure.app import app
from cyo_adventure.core.child_session import mint_child_session_token
from cyo_adventure.core.config import settings
from cyo_adventure.db.models import Family, KwsVerification, User

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_ONBOARDING = "/api/v1/onboarding"


async def _count(sessions: async_sessionmaker[AsyncSession], model: type) -> int:
    async with sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_first_login_creates_family_and_guardian(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A verified subject with no user row provisions a family + guardian (201).

    The row starts 'awaiting_approval', not 'active' (the self-signup
    approval track): an admin must approve it before anything else
    authenticates for this subject.
    """
    _ = seed  # seed builds the schema/rows the app queries against
    families_before = await _count(sessions, Family)

    resp = await client.post(_ONBOARDING, headers=auth("brand-new-guardian"), json={})

    assert resp.status_code == 201
    payload = cast("dict[str, object]", resp.json())
    assert payload["created"] is True
    assert payload["role"] == "guardian"
    assert payload["status"] == "awaiting_approval"
    assert payload["family_id"]
    assert payload["user_id"]
    assert await _count(sessions, Family) == families_before + 1

    async with sessions() as session:
        user = await session.scalar(
            select(User).where(User.authn_subject == "brand-new-guardian")
        )
    assert user is not None
    assert user.role == "guardian"
    assert user.status == "awaiting_approval"
    # Local dev seam supplies no email claim, so the contact column is null.
    assert user.email is None


async def test_self_signup_guardian_cannot_authenticate_until_approved(
    client: AsyncClient, seed: Seed
) -> None:
    """A freshly self-signed-up guardian's GET /v1/me fails until admin approval.

    require_principal rejects any non-'active' status with the same
    "unknown subject" message as a nonexistent one (api/deps.py); this pins
    that the self-signup track actually blocks access, not just that the
    row is tagged correctly.
    """
    _ = seed
    onboard_resp = await client.post(
        _ONBOARDING, headers=auth("unapproved-guardian"), json={}
    )
    assert onboard_resp.status_code == 201

    me_resp = await client.get("/api/v1/me", headers=auth("unapproved-guardian"))
    assert me_resp.status_code == 401


async def test_admin_approves_self_signup_guardian(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin approving a self-signed-up guardian lets them authenticate.

    End-to-end: self-signup (awaiting_approval) -> PATCH .../approve
    (active) -> GET /v1/me succeeds.
    """
    onboard_resp = await client.post(
        _ONBOARDING, headers=auth("soon-approved-guardian"), json={}
    )
    assert onboard_resp.status_code == 201
    user_id = onboard_resp.json()["user_id"]

    approve_resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"status": "active"},
        headers=auth(seed.admin_token),
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["status"] == "active"

    me_resp = await client.get("/api/v1/me", headers=auth("soon-approved-guardian"))
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "guardian"


async def test_admin_denies_self_signup_guardian(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin denying a self-signed-up guardian keeps them locked out."""
    onboard_resp = await client.post(
        _ONBOARDING, headers=auth("denied-guardian"), json={}
    )
    assert onboard_resp.status_code == 201
    user_id = onboard_resp.json()["user_id"]

    deny_resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"status": "deactivated"},
        headers=auth(seed.admin_token),
    )
    assert deny_resp.status_code == 200, deny_resp.text
    assert deny_resp.json()["status"] == "deactivated"

    me_resp = await client.get("/api/v1/me", headers=auth("denied-guardian"))
    assert me_resp.status_code == 401


async def test_retry_is_idempotent_same_ids(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A second onboarding for the same subject returns 200 with identical ids."""
    _ = seed
    first = await client.post(_ONBOARDING, headers=auth("retry-guardian"), json={})
    assert first.status_code == 201
    first_body = cast("dict[str, object]", first.json())

    second = await client.post(_ONBOARDING, headers=auth("retry-guardian"), json={})
    assert second.status_code == 200
    second_body = cast("dict[str, object]", second.json())

    assert second_body["created"] is False
    assert second_body["family_id"] == first_body["family_id"]
    assert second_body["user_id"] == first_body["user_id"]
    # Exactly one guardian row and one family exist for the retried subject.
    async with sessions() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.authn_subject == "retry-guardian")
        )
    assert count == 1


async def test_admin_token_does_not_create_family(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """An admin already has a row: onboarding returns it and creates no family."""
    families_before = await _count(sessions, Family)

    resp = await client.post(_ONBOARDING, headers=auth(seed.admin_token), json={})

    assert resp.status_code == 200
    payload = cast("dict[str, object]", resp.json())
    assert payload["created"] is False
    assert payload["role"] == "admin"
    assert payload["user_id"] == str(seed.admin_user_id)
    # No family was minted for the admin (admin is not a provisioned member).
    assert await _count(sessions, Family) == families_before


async def test_existing_guardian_is_idempotent(client: AsyncClient, seed: Seed) -> None:
    """A seeded guardian onboarding again returns its own row with 200."""
    resp = await client.post(_ONBOARDING, headers=auth(seed.guardian_token), json={})
    assert resp.status_code == 200
    payload = cast("dict[str, object]", resp.json())
    assert payload["created"] is False
    assert payload["role"] == "guardian"
    assert payload["family_id"] == str(seed.family_id)


async def test_missing_bearer_is_unauthorized(client: AsyncClient, seed: Seed) -> None:
    """Onboarding without a bearer token is rejected 401, never anonymous."""
    _ = seed
    resp = await client.post(_ONBOARDING, json={})
    assert resp.status_code == 401


async def test_child_session_token_cannot_onboard(
    client: AsyncClient, seed: Seed
) -> None:
    """A child session token is refused (403); it cannot provision a guardian."""
    token, _expires = mint_child_session_token(
        profile_id=seed.child_profile_id,
        family_id=seed.family_id,
        user_id=seed.admin_user_id,
    )
    resp = await client.post(_ONBOARDING, headers=auth(token), json={})
    assert resp.status_code == 403


async def test_empty_body_is_accepted(client: AsyncClient, seed: Seed) -> None:
    """Onboarding accepts a request with no body at all (identity is the token)."""
    _ = seed
    resp = await client.post(_ONBOARDING, headers=auth("bodyless-guardian"))
    assert resp.status_code == 201
    assert resp.json()["created"] is True


async def test_onboarding_without_consent_still_provisions(
    client: AsyncClient, seed: Seed
) -> None:
    """Omitting consent entirely still provisions the guardian; nothing is gated here.

    Phase 2 / ADR-018 D1's gate lives at POST /api/v1/profiles
    (api/profiles.py::_require_consent), not at onboarding itself: a
    guardian may finish sign-in and look around before completing consent,
    they simply cannot create a child profile until they do.
    """
    _ = seed
    resp = await client.post(_ONBOARDING, headers=auth("no-consent-guardian"), json={})
    assert resp.status_code == 201
    assert resp.json()["created"] is True


async def test_consent_requires_policy_version_and_signer_name(
    client: AsyncClient, seed: Seed
) -> None:
    """accepted=True with no signer_name is rejected (422), not silently dropped."""
    _ = seed
    resp = await client.post(
        _ONBOARDING,
        headers=auth("half-consenting-guardian"),
        json={"consent": {"accepted": True, "policy_version": "2026-07"}},
    )
    assert resp.status_code == 422


async def test_consent_requires_residence_country_and_adulthood_attested(
    client: AsyncClient, seed: Seed
) -> None:
    """accepted=True with policy_version/signer_name but no O-117/O-119 is rejected.

    The pre-existing consent_* quartet being complete is not enough: O-117
    (residence_country) and O-119 (adulthood_attested) are new independently
    required fields on the same consent submission.
    """
    _ = seed
    resp = await client.post(
        _ONBOARDING,
        headers=auth("no-country-guardian"),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Jane A. Guardian",
            }
        },
    )
    assert resp.status_code == 422


async def test_consent_rejects_malformed_country_code(
    client: AsyncClient, seed: Seed
) -> None:
    """A non-alpha-2 residence_country is rejected at the Pydantic boundary (422)."""
    _ = seed
    resp = await client.post(
        _ONBOARDING,
        headers=auth("bad-country-guardian"),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Jane A. Guardian",
                "residence_country": "USA",
                "adulthood_attested": True,
            }
        },
    )
    assert resp.status_code == 422


async def test_consent_rejects_false_adulthood_attested(
    client: AsyncClient, seed: Seed
) -> None:
    """adulthood_attested=false alongside accepted=true is rejected (422).

    Mirrors test_consent_requires_residence_country_and_adulthood_attested,
    but for an explicit False rather than an omitted field: _record_consent
    treats anything other than an explicit True as "not attested" (never
    coerced from truthiness).
    """
    _ = seed
    resp = await client.post(
        _ONBOARDING,
        headers=auth("not-adult-guardian"),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Jane A. Guardian",
                "residence_country": "US",
                "adulthood_attested": False,
            }
        },
    )
    assert resp.status_code == 422


async def test_consent_rejects_empty_country_code(
    client: AsyncClient, seed: Seed
) -> None:
    """An empty residence_country string is rejected at the Pydantic boundary (422)."""
    _ = seed
    resp = await client.post(
        _ONBOARDING,
        headers=auth("empty-country-guardian"),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Jane A. Guardian",
                "residence_country": "",
                "adulthood_attested": True,
            }
        },
    )
    assert resp.status_code == 422


async def test_consent_rejects_unassigned_country_code(
    client: AsyncClient, seed: Seed
) -> None:
    """A syntactically valid but unassigned alpha-2 code is rejected (422).

    "ZZ" passes the two-letter format regex but names no real ISO 3166-1
    country; ResidenceCountry's normalizer must reject it against
    ASSIGNED_RESIDENCE_COUNTRY_CODES, not just the format check (the
    ck_user_residence_country_format CHECK at rest would let it through).
    """
    _ = seed
    resp = await client.post(
        _ONBOARDING,
        headers=auth("unassigned-country-guardian"),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Jane A. Guardian",
                "residence_country": "ZZ",
                "adulthood_attested": True,
            }
        },
    )
    assert resp.status_code == 422


async def test_consent_normalizes_whitespace_padded_lowercase_country_code(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A whitespace-padded, lowercase country code is trimmed and uppercased.

    Positive counterpart to the rejection tests above: " us " is a valid
    submission, not a malformed one, once _normalize_residence_country strips
    and uppercases it.
    """
    _ = seed
    subject = "padded-lowercase-country-guardian"
    resp = await client.post(
        _ONBOARDING,
        headers=auth(subject),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Jane A. Guardian",
                "residence_country": " us ",
                "adulthood_attested": True,
            }
        },
    )
    assert resp.status_code == 201

    async with sessions() as session:
        user = await session.scalar(select(User).where(User.authn_subject == subject))
    assert user is not None
    assert user.residence_country == "US"


async def test_onboarding_records_consent_once_and_is_idempotent(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A valid consent payload is persisted onto the guardian's own User row.

    A second onboarding call with a DIFFERENT consent payload does not
    overwrite the first: consent is written once, matching
    api/onboarding.py::_record_consent's idempotency contract. Covers
    O-117/O-119 (residence_country / adulthood_attested_at) alongside the
    pre-existing consent_* quartet, since all five are written together.
    """
    _ = seed
    subject = "consenting-guardian"
    first = await client.post(
        _ONBOARDING,
        headers=auth(subject),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Jane A. Guardian",
                "residence_country": "us",
                "adulthood_attested": True,
            }
        },
    )
    assert first.status_code == 201

    async with sessions() as session:
        user = await session.scalar(select(User).where(User.authn_subject == subject))
    assert user is not None
    assert user.consent_accepted_at is not None
    assert user.consent_policy_version == "2026-07"
    assert user.consent_signer_name == "Jane A. Guardian"
    assert user.consent_ip is not None
    # Lowercase input is uppercased by the schema's normalizer before it
    # ever reaches the CHECK constraint or the database.
    assert user.residence_country == "US"
    assert user.adulthood_attested_at is not None
    first_recorded_at = user.consent_accepted_at
    first_attested_at = user.adulthood_attested_at

    second = await client.post(
        _ONBOARDING,
        headers=auth(subject),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2027-01",
                "signer_name": "Someone Else",
                "residence_country": "CA",
                "adulthood_attested": True,
            }
        },
    )
    assert second.status_code == 200

    async with sessions() as session:
        user = await session.scalar(select(User).where(User.authn_subject == subject))
    assert user is not None
    assert user.consent_accepted_at == first_recorded_at
    assert user.consent_policy_version == "2026-07"
    assert user.consent_signer_name == "Jane A. Guardian"
    assert user.residence_country == "US"
    assert user.adulthood_attested_at == first_attested_at


async def test_onboarding_links_the_consent_record_to_its_verification(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A consent recorded after a verification names the verification (ADR-018 D1).

    Follows the real order of events: the empty first call provisions the
    account, the parent then verifies, and only the consent written afterward
    can carry the link. The column is evidence, not a gate, so nothing here
    asserts that the consent was allowed or refused because of it.
    """
    _ = seed
    monkeypatch.setattr(settings, "kws_environment", "test")
    monkeypatch.setattr(settings, "kws_accept_test_evidence", True)
    subject = "verified-then-consenting-guardian"
    provisioned = await client.post(_ONBOARDING, headers=auth(subject))
    assert provisioned.status_code == 201

    attempt_id = uuid.uuid4()
    async with sessions() as session:
        user_id = await session.scalar(
            select(User.id).where(User.authn_subject == subject)
        )
        assert user_id is not None
        session.add(
            KwsVerification(
                id=attempt_id,
                user_id=user_id,
                kws_environment="test",
                status="verified",
                requested_at=datetime.now(UTC),
                resolved_at=datetime.now(UTC),
                enabled_methods=["credit_card"],
                location="US",
            )
        )
        await session.commit()

    consented = await client.post(
        _ONBOARDING,
        headers=auth(subject),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Verified A. Guardian",
                "residence_country": "US",
                "adulthood_attested": True,
            }
        },
    )
    assert consented.status_code == 200

    async with sessions() as session:
        user = await session.scalar(select(User).where(User.authn_subject == subject))
    assert user is not None
    assert user.consent_verification_id == attempt_id


async def test_onboarding_reports_the_verification_state_the_guardian_must_act_on(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This response, not GET /v1/me, is where an unapproved guardian learns to verify.

    ADR-018 D1 orders verification BEFORE admin approval, and
    ``require_principal`` refuses any user whose status is not 'active', so
    the guardian who most needs this answer cannot reach /v1/me to ask for
    it. Both readings are asserted in one test on purpose: a 'none' assertion
    alone would pass just as well against a field hard-coded to 'none', which
    is exactly the regression this pins.
    """
    _ = seed
    monkeypatch.setattr(settings, "kws_verification_required", True)
    monkeypatch.setattr(settings, "kws_environment", "test")
    monkeypatch.setattr(settings, "kws_accept_test_evidence", True)
    subject = "guardian-awaiting-verification"

    provisioned = await client.post(_ONBOARDING, headers=auth(subject))

    assert provisioned.status_code == 201
    body = cast("dict[str, object]", provisioned.json())
    assert body["status"] == "awaiting_approval"
    assert body["verification_status"] == "none"

    async with sessions() as session:
        user_id = await session.scalar(
            select(User.id).where(User.authn_subject == subject)
        )
        assert user_id is not None
        session.add(
            KwsVerification(
                id=uuid.uuid4(),
                user_id=user_id,
                kws_environment="test",
                status="verified",
                requested_at=datetime.now(UTC),
                resolved_at=datetime.now(UTC),
                enabled_methods=["credit_card"],
                location="US",
            )
        )
        await session.commit()

    retried = await client.post(_ONBOARDING, headers=auth(subject))

    assert retried.status_code == 200
    assert (
        cast("dict[str, object]", retried.json())["verification_status"] == "verified"
    )


async def test_onboarding_consent_without_a_verification_links_nothing(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """NULL is the legitimate answer for a typed-name-only consent record.

    The paired negative for the test above, and the reason the column is
    deliberately absent from ``ck_user_consent_pairing``: every consent
    recorded before ADR-018 D1's verification leg existed looks exactly like
    this, and a pairing constraint would make all of them illegal at rest.
    """
    _ = seed
    subject = "unverified-consenting-guardian"

    resp = await client.post(
        _ONBOARDING,
        headers=auth(subject),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Unverified A. Guardian",
                "residence_country": "US",
                "adulthood_attested": True,
            }
        },
    )
    assert resp.status_code == 201

    async with sessions() as session:
        user = await session.scalar(select(User).where(User.authn_subject == subject))
    assert user is not None
    assert user.consent_accepted_at is not None
    assert user.consent_verification_id is None


async def test_onboarding_race_recovers_winner(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The first-login race recovers via a real unique-index conflict.

    Simulates the loser's timeline: its pre-insert SELECT saw no row (so the
    handler proceeded to provision), but the winner's row is already committed
    when the loser's INSERT hits the unique ``ix_user_authn_subject`` index.
    The real ``IntegrityError`` unwinds the savepoint (undoing the loser's
    Family insert too) and the loser returns the winner's row, leaving exactly
    one user and one family for the subject.
    """
    _ = seed
    subject = "raced-first-login"
    families_before = await _count(sessions, Family)

    # The "winner": another device's committed first login.
    async with sessions() as session:
        family = Family(name="Winner Family")
        session.add(family)
        await session.flush()
        winner = User(family_id=family.id, role="guardian", authn_subject=subject)
        session.add(winner)
        await session.commit()
        winner_id = winner.id
        winner_family_id = family.id

    # The "loser": drive the savepoint provisioning step directly (its
    # pre-read already returned None before the winner committed) against the
    # real index. The conflicting writes run INSIDE begin_nested, so only the
    # savepoint unwinds and the outer transaction stays usable for the
    # recovery re-read.
    async with sessions() as session:
        user, created = await onboarding._provision_guardian(
            session, OnboardingIdentity(subject=subject, email=None)
        )
        assert created is False
        assert user.id == winner_id
        assert user.family_id == winner_family_id
        await session.commit()

    # Exactly one user row for the subject, and only the winner's family was
    # created: the loser's partial Family insert was unwound with the savepoint.
    async with sessions() as session:
        count = await session.scalar(
            select(func.count()).select_from(User).where(User.authn_subject == subject)
        )
    assert count == 1
    assert await _count(sessions, Family) == families_before + 1


async def test_email_claim_persisted_when_present(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The email contact claim is stored on the created user when the token has one.

    The local dev seam carries no email, so the verified-identity dependency is
    overridden here to inject one (as a real Supabase token would), proving the
    endpoint persists it. The child-session-secret autouse fixture and the DB
    override from the ``client`` fixture remain in force.
    """
    _ = seed
    relay = "abc123@privaterelay.appleid.com"

    def _identity_with_email() -> OnboardingIdentity:
        return OnboardingIdentity(subject="apple-guardian", email=relay)

    app.dependency_overrides[deps.require_onboarding_identity] = _identity_with_email
    try:
        resp = await client.post(_ONBOARDING, json={})
    finally:
        del app.dependency_overrides[deps.require_onboarding_identity]

    assert resp.status_code == 201
    async with sessions() as session:
        user = await session.scalar(
            select(User).where(User.authn_subject == "apple-guardian")
        )
    assert user is not None
    # Contact data only: stored, but authn_subject remains the sole key.
    assert user.email == relay
