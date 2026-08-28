"""Integration tests: every lifecycle transition writes exactly one pipeline_event."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, create_autospec

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.core.config import Settings
from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    GenerationJob,
    ProviderModelAllowlist,
    Storybook,
    StorybookVersion,
    User,
)
from cyo_adventure.events.models import Actor
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import (
    _CANNED_STORY,
    _CANNED_STORY_JSON,
    MockProvider,
)
from cyo_adventure.generation.worker import run_generation_job
from cyo_adventure.moderation import pipeline as pipeline_mod
from cyo_adventure.moderation.classifiers import run_classifiers as _real_classifiers
from cyo_adventure.moderation.report import Finding, Source, Verdict
from cyo_adventure.moderation.stages import (
    run_coherence_stage as _real_coherence,
)
from cyo_adventure.moderation.stages import (
    run_engagement_stage as _real_engagement,
)
from cyo_adventure.moderation.stages import (
    run_safety_stage as _real_safety,
)
from cyo_adventure.publishing import service as publishing_service
from tests.conftest import make_clean_moderation_report
from tests.integration._event_assertions import assert_single_event, fetch_events
from tests.integration.conftest import Seed, Stranger, auth
from tests.integration.test_generation_worker import (
    _make_session_factory,
    gen_seed,  # noqa: F401 -- imported for pytest fixture discovery
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_CREATE = "/api/v1/story-requests"


def _moderation_settings() -> Settings:
    """Return minimal Settings driving the moderation pipeline's mock backend."""
    return Settings(review_provider="mock")


def _with_mock_stamp(**counts: int) -> dict[str, int]:
    """Return ``counts`` plus the mock reviewer's own row, as one exact expectation.

    Every moderation test in this module runs ``_moderation_settings()``, i.e.
    ``review_provider="mock"``, and ``pipeline._stamp_mock_reviewer`` adds one
    ADVISORY, ``structural=True`` finding to every such report in every
    environment (the gap-G1 stamp). It therefore contributes exactly one
    ``advisory`` and one ``structural`` to each ``moderation_completed``
    ``counts`` payload, on top of whatever the test's own findings produce.

    Folding it in here rather than relaxing the assertions keeps every call
    site an exact-equality check that ASSERTS the stamp: deleting the stamp,
    or gating it back on ``environment``, fails these tests instead of
    silently passing them.

    Args:
        counts: The verdict-name counts the test's own findings produce,
            excluding the stamp.

    Returns:
        The full expected ``counts`` payload, stamp included.
    """
    stamped = {"advisory": 1, "structural": 1}
    for name, value in counts.items():
        stamped[name] = stamped.get(name, 0) + value
    return stamped


def _pii() -> PiiContext:
    """Return an empty PiiContext with no real-child identifiers to guard against."""
    return PiiContext(child_names=frozenset())


@pytest.fixture
def stub_stages(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Factory stubbing the moderation pipeline's stage seams with autospecs.

    The settings-level mock review backend cannot drive these event tests: its
    fixed ``"{}"`` bodies fail-safe every safety finding to FLAG and would
    spuriously trigger repair on every run. The stage functions are therefore
    stubbed at the pipeline module's import sites; each stub is built with
    ``create_autospec`` against the real stage function (testing standard
    §4.2) so a signature drift in the pipeline's calls fails loudly here
    instead of passing silently. Plain ``AsyncMock(spec=...)`` would NOT give
    that: a function passed as ``spec=`` constrains attribute access only,
    never call signatures; only ``create_autospec`` captures and enforces the
    signature.

    Returns:
        An installer accepting ``classifiers`` (Stage-0 findings, default
        clean) and ``safety`` (a pre-built async mock for tests needing
        per-call side effects; build it with ``create_autospec`` to keep the
        signature check, default clean); all other stages are stubbed clean.
    """

    def _install(
        *,
        classifiers: list[Finding] | None = None,
        safety: AsyncMock | None = None,
    ) -> None:
        monkeypatch.setattr(
            pipeline_mod,
            "run_classifiers",
            create_autospec(_real_classifiers, return_value=classifiers or []),
        )
        for name, real in (
            ("run_coherence_stage", _real_coherence),
            ("run_engagement_stage", _real_engagement),
        ):
            monkeypatch.setattr(
                pipeline_mod, name, create_autospec(real, return_value=[])
            )
        monkeypatch.setattr(
            pipeline_mod,
            "run_safety_stage",
            safety
            if safety is not None
            else create_autospec(_real_safety, return_value=[]),
        )

    return _install


async def _seed_draft_storybook(
    sessions: async_sessionmaker[AsyncSession], story_id: str
) -> None:
    """Persist a minimal Family + draft Storybook + StorybookVersion row.

    Reuses the canned, schema-valid story blob (``_CANNED_STORY``) that the
    unit-level moderation-pipeline tests
    (tests/unit/test_moderation_pipeline.py) also validate against, so the
    same story passes ``StoryModel.model_validate`` inside the pipeline.
    """
    async with sessions() as session:
        fam = Family(name="Moderation Event Test Family")
        session.add(fam)
        await session.flush()
        session.add(Storybook(id=story_id, family_id=fam.id, status="draft"))
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob=dict(_CANNED_STORY),
                model="gen-model",
            )
        )
        await session.commit()


async def _seed_in_review_storybook(
    sessions: async_sessionmaker[AsyncSession], story_id: str
) -> None:
    """Seed Family + admin user + an in-review, moderation-screened single-version story.

    Mirrors tests/integration/test_approval_api.py::_seed_in_review (a clean
    moderation_report is required: approve() and send_back() both operate on
    an already-screened in_review version).
    """
    async with sessions() as session:
        fam = Family(name="Publishing Event Test Family")
        session.add(fam)
        await session.flush()
        session.add(
            User(family_id=fam.id, role="admin", authn_subject="admin-a", is_admin=True)
        )
        session.add(Storybook(id=story_id, family_id=fam.id, status="in_review"))
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={"id": story_id},
                moderation_report=make_clean_moderation_report(),
            )
        )
        await session.commit()


async def _seed_screened_storybook(
    sessions: async_sessionmaker[AsyncSession], story_id: str, *, status: str
) -> None:
    """Seed a story whose latest version already carries a moderation report.

    ``submit`` refuses any version moderation has never screened, so the
    submit-path tests cannot reuse ``_seed_draft_storybook`` (whose version row
    has no report). Both submit entry points seed from here: ``draft`` is where
    the moderation pipeline's own submit starts, ``needs_revision`` is the state
    a story rests in between a send-back and a human resubmission.

    Args:
        sessions: Session factory for the test database.
        story_id: Storybook id to create.
        status: Lifecycle status to rest at (``draft`` or ``needs_revision``).
    """
    async with sessions() as session:
        fam = Family(name="Submit Event Test Family")
        session.add(fam)
        await session.flush()
        session.add(
            User(family_id=fam.id, role="admin", authn_subject="admin-a", is_admin=True)
        )
        session.add(Storybook(id=story_id, family_id=fam.id, status=status))
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={"id": story_id},
                moderation_report=make_clean_moderation_report(),
            )
        )
        await session.commit()


async def _seed_screened_storybook_for_family(
    sessions: async_sessionmaker[AsyncSession],
    story_id: str,
    family_id: uuid.UUID,
    *,
    status: str,
) -> None:
    """Seed a screened Storybook owned by a caller-supplied family.

    The sibling ``_seed_screened_storybook`` mints its own family and an admin
    whose base ``role`` is already ``admin``, which makes it useless for
    exercising ``Principal.acting_role``: both of that method's branches return
    ``"admin"`` for such a user, so an inverted family comparison would still
    satisfy the assertion. This variant attaches the story to an existing family
    (``seed.family_id`` or ``stranger.family_id``) so the own-family and
    foreign-family branches produce DIFFERENT stamps and the assertion can tell
    them apart.

    Args:
        sessions: Session factory for the test database.
        story_id: Storybook id to create.
        family_id: Family that owns the story.
        status: Lifecycle status to rest at (``draft`` or ``needs_revision``).
    """
    async with sessions() as session:
        session.add(Storybook(id=story_id, family_id=family_id, status=status))
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={"id": story_id},
                moderation_report=make_clean_moderation_report(),
            )
        )
        await session.commit()


async def _seed_in_review_storybook_for_family(
    sessions: async_sessionmaker[AsyncSession],
    story_id: str,
    family_id: uuid.UUID,
) -> None:
    """Seed a clean in-review Storybook owned by a caller-supplied family.

    The sibling ``_seed_in_review_storybook`` mints its own family and admin
    user; this variant instead attaches the story to an existing family (e.g.
    ``seed.family_id`` or ``stranger.family_id``) so a dual-role adult's
    own-family versus foreign-family review can be exercised against the same
    fixture identities that mint the tokens. A clean moderation_report is
    required: ``approve()`` and ``send_back()`` both operate on an
    already-screened in_review version.
    """
    async with sessions() as session:
        session.add(Storybook(id=story_id, family_id=family_id, status="in_review"))
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={"id": story_id},
                moderation_report=make_clean_moderation_report(),
            )
        )
        await session.commit()


async def _seed_published_storybook(
    sessions: async_sessionmaker[AsyncSession], story_id: str
) -> None:
    """Seed Family + admin user + a published single-version story.

    Mirrors ``_seed_in_review_storybook`` above (own-family, own-admin); used
    by the ``archive()``/``STORYBOOK_ARCHIVED`` (A5) tests, which need a
    story already in ``published`` rather than ``in_review``.
    """
    async with sessions() as session:
        fam = Family(name="Archive Event Test Family")
        session.add(fam)
        await session.flush()
        session.add(
            User(family_id=fam.id, role="admin", authn_subject="admin-a", is_admin=True)
        )
        session.add(
            Storybook(
                id=story_id,
                family_id=fam.id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(storybook_id=story_id, version=1, blob={"id": story_id})
        )
        await session.commit()


async def _seed_published_storybook_for_family(
    sessions: async_sessionmaker[AsyncSession],
    story_id: str,
    family_id: uuid.UUID,
) -> None:
    """Seed a published Storybook owned by a caller-supplied family.

    Mirrors ``_seed_in_review_storybook_for_family`` above; used by the
    dual-role archive tests so a dual-role adult's own-family versus
    foreign-family archive can be exercised against the same fixture
    identities that mint the tokens.
    """
    async with sessions() as session:
        session.add(
            Storybook(
                id=story_id,
                family_id=family_id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(storybook_id=story_id, version=1, blob={"id": story_id})
        )
        await session.commit()


async def test_approve_writes_released_event(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Admin approve on an in-review story writes exactly one released event."""
    story_id = "s_release_event"
    await _seed_in_review_storybook(sessions, story_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("admin-a")
    )
    assert resp.status_code == 200, resp.text

    event = await assert_single_event(
        sessions,
        event_type="released",
        entity_type="storybook",
        to_state="published",
        actor_role="admin",
    )
    assert event.payload == {"visibility": "family"}


async def test_approve_with_catalog_visibility_stamps_event_payload(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Approving with visibility=catalog records it on the released event."""
    story_id = "s_catalog_visibility_event"
    await _seed_in_review_storybook(sessions, story_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve",
        headers=auth("admin-a"),
        json={"visibility": "catalog"},
    )
    assert resp.status_code == 200, resp.text

    event = await assert_single_event(
        sessions,
        event_type="released",
        entity_type="storybook",
        to_state="published",
        actor_role="admin",
    )
    assert event.payload == {"visibility": "catalog"}


async def test_send_back_writes_sent_back_event(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Admin send-back on an in-review story writes exactly one sent_back event."""
    story_id = "s_send_back_event"
    await _seed_in_review_storybook(sessions, story_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/send-back",
        headers=auth("admin-a"),
        json={"reason": "too scary for 6yo", "reason_code": "safety_concern"},
    )
    assert resp.status_code == 200, resp.text

    event = await assert_single_event(
        sessions,
        event_type="sent_back",
        entity_type="storybook",
        to_state="needs_revision",
        actor_role="admin",
    )
    assert event.payload == {"reason_code": "safety_concern"}


async def test_resubmit_after_send_back_writes_submitted_event(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A human resubmitting a sent-back story marks its RE-ENTRY to the gate.

    Without this event the second review round has no start timestamp.
    ``POST /submit`` does not re-run moderation, so no ``moderation_completed``
    follows it, and the only other gate-entry marker is the one the moderation
    pipeline writes on the FIRST pass. Approval duration past round one is
    therefore unmeasurable without this row (R-11).
    """
    story_id = "s_resubmit_event"
    await _seed_screened_storybook(sessions, story_id, status="needs_revision")

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/submit", headers=auth("admin-a")
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="submitted",
        entity_type="storybook",
        to_state="in_review",
        actor_role="admin",
    )


async def test_moderation_submit_stamps_the_system_actor(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The automated first entry to the gate is stamped system, not a person.

    Gate entry is logged uniformly, so a duration measurement never has to
    special-case where the entry came from; the ACTOR is what separates the
    pipeline's own submit from a human resubmission. This mirrors how
    ``needs_revision`` cannot distinguish auto-reject from a human send-back
    while the ``sent_back`` event can (see publishing/state_machine.py).
    """
    story_id = "s_pipeline_submit_event"
    await _seed_screened_storybook(sessions, story_id, status="draft")

    async with sessions() as session:
        book = await session.get(Storybook, story_id)
        assert book is not None
        await publishing_service.submit(session, book, actor=Actor.system())
        await session.commit()

    event = await assert_single_event(
        sessions,
        event_type="submitted",
        entity_type="storybook",
        to_state="in_review",
        actor_role="system",
    )
    assert event.payload == {}


async def test_dual_role_same_family_submit_stamps_guardian(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A dual-role adult resubmitting their own family's story acts as guardian.

    Submit is admin-gated at the route, but the audit stamp follows the same
    own-family rule as send-back and publish: the owner's guardian base persona,
    not admin. Paired with its foreign-family sibling below, this is what makes
    ``Principal.acting_role``'s two branches distinguishable for the submit path;
    neither of the other two submit tests can tell them apart, because the admin
    they seed returns ``"admin"`` from either branch.
    """
    story_id = "s_submit_dual_same_family"
    await _seed_screened_storybook_for_family(
        sessions, story_id, seed.family_id, status="needs_revision"
    )

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/submit", headers=auth(seed.dual_token)
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="submitted",
        entity_type="storybook",
        to_state="in_review",
        actor_role="guardian",
    )


async def test_dual_role_foreign_family_submit_stamps_admin(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    stranger: Stranger,
) -> None:
    """A dual-role adult resubmitting a foreign family's story acts as admin."""
    story_id = "s_submit_dual_foreign_family"
    await _seed_screened_storybook_for_family(
        sessions, story_id, stranger.family_id, status="needs_revision"
    )

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/submit", headers=auth(seed.dual_token)
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="submitted",
        entity_type="storybook",
        to_state="in_review",
        actor_role="admin",
    )


async def test_kid_create_writes_request_created(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    resp = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    await assert_single_event(
        sessions,
        event_type="request_created",
        entity_type="story_request",
        actor_role="child",
    )


async def test_decline_writes_request_declined(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/decline",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_declined",
        entity_type="story_request",
        to_state="declined",
        actor_role="guardian",
    )


async def test_approve_writes_request_approved(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.guardian_token),
        # WS-B: approve requires a confirmation body; band matches the
        # seeded profile's own band (conftest.Seed's profile_a, "10-13").
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_approved",
        entity_type="story_request",
        to_state="approved",
        actor_role="guardian",
    )


async def test_dual_role_same_family_decline_stamps_guardian(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A dual-role adult declining their own family's request acts as guardian.

    ``acting_role()`` only escalates to admin for a cross-family action; a
    dual-role adult (guardian base role + is_admin) declining within their
    own family is stamped with the base role, exactly like a plain guardian.
    """
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/decline",
        headers=auth(seed.dual_token),
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_declined",
        entity_type="story_request",
        to_state="declined",
        actor_role="guardian",
    )


async def test_dual_role_foreign_family_decline_stamps_admin(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    stranger: Stranger,
) -> None:
    """A dual-role adult declining a foreign family's request acts as admin.

    Only the admin capability authorizes the cross-family decline, so the
    audit stamp records admin, not the guardian base persona (mirrors
    test_dual_role_foreign_family_is_stamped_admin in
    test_story_requests_authored.py for the create path).
    """
    create = await client.post(
        _CREATE,
        headers=auth(stranger.guardian_token),
        json={
            "profile_id": str(stranger.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/decline",
        headers=auth(seed.dual_token),
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_declined",
        entity_type="story_request",
        to_state="declined",
        actor_role="admin",
    )


async def test_dual_role_same_family_approve_stamps_guardian(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A dual-role adult approving their own family's request acts as guardian."""
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.dual_token),
        # WS-B: approve requires a confirmation body; band matches the
        # seeded profile's own band (conftest.Seed's profile_a, "10-13").
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_approved",
        entity_type="story_request",
        to_state="approved",
        actor_role="guardian",
    )


async def test_dual_role_foreign_family_approve_stamps_admin(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    stranger: Stranger,
) -> None:
    """A dual-role adult approving a foreign family's request acts as admin.

    Only the admin capability authorizes the cross-family approval, so the
    audit stamp records admin, not the guardian base persona.
    """
    create = await client.post(
        _CREATE,
        headers=auth(stranger.guardian_token),
        json={
            "profile_id": str(stranger.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.dual_token),
        # Matches the stranger family's own seeded profile band ("10-13"),
        # per conftest.stranger's profile_c.
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_approved",
        entity_type="story_request",
        to_state="approved",
        actor_role="admin",
    )


async def test_dual_role_same_family_publish_stamps_guardian(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A dual-role adult publishing their own family's story acts as guardian.

    The RELEASED audit stamp must record the guardian base persona, not the
    admin capability, so an owner reviewing their own family's content is
    distinguishable in the event log from a genuine cross-family admin
    approval (Decision 2, persona-expectation audit 2026-07-27).
    """
    story_id = "s_release_dual_same_family"
    await _seed_in_review_storybook_for_family(sessions, story_id, seed.family_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve",
        headers=auth(seed.dual_token),
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="released",
        entity_type="storybook",
        to_state="published",
        actor_role="guardian",
    )


async def test_dual_role_foreign_family_publish_stamps_admin(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    stranger: Stranger,
) -> None:
    """A dual-role adult publishing a foreign family's story acts as admin.

    Only the admin capability authorizes the cross-family publish, so the
    RELEASED audit stamp records admin, not the guardian base persona.
    """
    story_id = "s_release_dual_foreign_family"
    await _seed_in_review_storybook_for_family(sessions, story_id, stranger.family_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve",
        headers=auth(seed.dual_token),
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="released",
        entity_type="storybook",
        to_state="published",
        actor_role="admin",
    )


async def test_dual_role_same_family_send_back_stamps_guardian(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A dual-role adult sending back their own family's story acts as guardian.

    Send-back is a review action too, so its audit stamp follows the same
    own-family rule as publish: the owner's guardian base persona, not admin.
    """
    story_id = "s_send_back_dual_same_family"
    await _seed_in_review_storybook_for_family(sessions, story_id, seed.family_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/send-back",
        headers=auth(seed.dual_token),
        json={"reason": "let's soften the storm scene", "reason_code": "prose_quality"},
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="sent_back",
        entity_type="storybook",
        to_state="needs_revision",
        actor_role="guardian",
    )


async def test_dual_role_foreign_family_send_back_stamps_admin(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    stranger: Stranger,
) -> None:
    """A dual-role adult sending back a foreign family's story acts as admin."""
    story_id = "s_send_back_dual_foreign_family"
    await _seed_in_review_storybook_for_family(sessions, story_id, stranger.family_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/send-back",
        headers=auth(seed.dual_token),
        json={"reason": "cross-family policy check", "reason_code": "other"},
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="sent_back",
        entity_type="storybook",
        to_state="needs_revision",
        actor_role="admin",
    )


async def test_archive_writes_storybook_archived_event(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Admin archive on a published story writes exactly one storybook_archived event.

    A5's incident/pull-everywhere path (docs/planning/capability-register.md):
    this is the event notifications/registry.py's composer turns into an
    alert-severity guardian notification.
    """
    story_id = "s_archive_event"
    await _seed_published_storybook(sessions, story_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/archive", headers=auth("admin-a")
    )
    assert resp.status_code == 200, resp.text

    event = await assert_single_event(
        sessions,
        event_type="storybook_archived",
        entity_type="storybook",
        to_state="archived",
        actor_role="admin",
    )
    assert event.payload == {}


async def test_dual_role_same_family_archive_stamps_guardian(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A dual-role adult archiving their own family's story acts as guardian."""
    story_id = "s_archive_dual_same_family"
    await _seed_published_storybook_for_family(sessions, story_id, seed.family_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/archive", headers=auth(seed.dual_token)
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="storybook_archived",
        entity_type="storybook",
        to_state="archived",
        actor_role="guardian",
    )


async def test_dual_role_foreign_family_archive_stamps_admin(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    stranger: Stranger,
) -> None:
    """A dual-role adult archiving a foreign family's story acts as admin."""
    story_id = "s_archive_dual_foreign_family"
    await _seed_published_storybook_for_family(sessions, story_id, stranger.family_id)

    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/archive", headers=auth(seed.dual_token)
    )
    assert resp.status_code == 200, resp.text

    await assert_single_event(
        sessions,
        event_type="storybook_archived",
        entity_type="storybook",
        to_state="archived",
        actor_role="admin",
    )


async def test_authoring_plan_writes_plan_assigned(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    approved = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.guardian_token),
        # WS-B: approve requires a confirmation body; band matches the
        # seeded profile's own band (conftest.Seed's profile_a, "10-13").
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert approved.status_code == 200, approved.text
    # WS-C PR1: automated_provider now requires a provider/model pair validated
    # against the enabled allowlist. The integration schema is built via
    # create_all, which does not run the migration's seed rows, so insert one
    # enabled pair here (mirrors tests/integration/test_authoring_plan_api.py).
    # openrouter, not the direct anthropic leg this used to name: since D1
    # (`UW-C346`, `UW-C350`) an authoring plan is a family-lane question, the
    # read path refuses a provider that lane forbids, and an ENABLED row for
    # one no longer satisfies the table's own CHECK either. This test is about
    # the plan_assigned event, so it wants a pair that is simply accepted.
    async with sessions() as session:
        session.add(
            ProviderModelAllowlist(
                provider="openrouter",
                model_id="deepseek/deepseek-v4-pro",
                enabled=True,
            )
        )
        await session.commit()
    resp = await client.post(
        f"{_CREATE}/{request_id}/authoring-plan",
        headers=auth(seed.admin_token),
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "prep_model": "openrouter/some-model",
            # Use the seeded-enabled pair so the plan is accepted and the
            # plan_assigned event is written.
            "provider": "openrouter",
            "model": "deepseek/deepseek-v4-pro",
        },
    )
    assert resp.status_code == 201, resp.text
    await assert_single_event(
        sessions,
        event_type="plan_assigned",
        entity_type="generation_job",
        actor_role="admin",
    )


async def test_generation_run_writes_started_and_finished_system_events(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],  # noqa: F811 -- pytest fixture, not the import
) -> None:
    """A full worker run writes exactly one generation_started and one
    generation_finished event, both attributed to the system actor.

    Reuses the ``gen_seed`` fixture and session-factory helper from
    test_generation_worker.py (seeded queued job + injected MockProvider)
    rather than building a new worker-test arrangement.
    """
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    provider = MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "passed", f"Expected passed, got {job.status}"

    await assert_single_event(
        sessions,
        event_type="generation_started",
        entity_type="generation_job",
        to_state="running",
        actor_is_system=True,
    )
    await assert_single_event(
        sessions,
        event_type="generation_finished",
        entity_type="generation_job",
        to_state="passed",
        actor_is_system=True,
    )


async def test_generation_finished_event_precedes_failure_commit(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],  # noqa: F811 -- pytest fixture, not the import
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pipeline failure's generation_finished event is committed atomically
    with the job's "failed" status write, never separately (worker.py
    ``_record_failure``'s #CRITICAL marker).

    ``record_event`` (events/writer.py) only flushes; the durable write comes
    from the SAME ``session.commit()`` that ``_record_failure`` calls right
    after it. Asserting "the event lands before the commit" cannot be done by
    polling from a second session/connection: Postgres's transaction
    isolation means a separate session can never observe an intermediate
    state inside another session's still-open transaction, so there is
    nothing to poll for. Two observations together establish the atomicity
    claim instead of one impossible one:

    1. Here: once the worker's failure path has fully run, the failed job row
       and its generation_finished/failed event are BOTH visible from a fresh
       session. If the event write happened in a transaction separate from
       the status write, a crash between the two could leave one committed
       without the other; this pins that they always arrive together.
    2. In the companion test
       (test_generation_finished_event_and_failed_status_share_one_commit):
       forcing the shared commit itself to fail leaves NEITHER row durable,
       proving the converse: nothing here becomes visible without that one
       commit succeeding. 1 and 2 together pin the "same transaction" claim.
    """
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    async def _boom_generate(*_args: object, **_kwargs: object) -> None:
        msg = "pipeline exploded"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        "cyo_adventure.generation.worker.generate_story", _boom_generate
    )

    provider = MockProvider(responses=[])
    session_factory = _make_session_factory(sessions)
    with pytest.raises(RuntimeError, match="pipeline exploded"):
        await run_generation_job(
            job_id,
            provider=provider,
            session_factory=session_factory,
        )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error == "pipeline exploded"

    event = await assert_single_event(
        sessions,
        event_type="generation_finished",
        entity_type="generation_job",
        to_state="failed",
        actor_is_system=True,
    )
    assert event.entity_id == str(job_id)
    assert event.actor_id is None
    assert event.actor_role == "system"
    assert event.payload == {"outcome": "failed"}


async def test_generation_finished_event_and_failed_status_share_one_commit(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],  # noqa: F811 -- pytest fixture, not the import
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the worker's terminal commit fails, neither the failed status nor
    its generation_finished event becomes durable.

    Companion to test_generation_finished_event_precedes_failure_commit:
    forces ``AsyncSession.commit`` to raise, simulating a crash landing right
    at the commit boundary ``_record_failure`` relies on. ``record_event``'s
    INSERT was already flushed (sent to Postgres over the same still-open
    transaction) before this failing commit call; since that row still does
    not survive, the event write was never durable on its own, only the
    shared commit makes it (and the status write) durable together.
    """
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    async def _boom_generate(*_args: object, **_kwargs: object) -> None:
        msg = "pipeline exploded"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        "cyo_adventure.generation.worker.generate_story", _boom_generate
    )

    async def _boom_commit(_self: AsyncSession) -> None:
        msg = "commit interrupted"
        raise RuntimeError(msg)

    monkeypatch.setattr(AsyncSession, "commit", _boom_commit)

    provider = MockProvider(responses=[])
    session_factory = _make_session_factory(sessions)
    with pytest.raises(RuntimeError, match="commit interrupted"):
        await run_generation_job(
            job_id,
            provider=provider,
            session_factory=session_factory,
        )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        # Neither the "running" nor the "failed" transition was ever
        # committed: the job row is still at its original queued state.
        assert job.status == "queued"

    assert await fetch_events(sessions, "generation_finished") == []


async def test_clean_moderation_writes_moderation_completed(
    sessions: async_sessionmaker[AsyncSession],
    stub_stages: Callable[..., None],
) -> None:
    """A clean moderation run (no soft flags, no hard block) writes exactly one
    moderation_completed event, attributed to the system actor, with
    to_state="in_review" and a PII-free payload showing repaired=False.

    Drives ``run_moderation_pipeline`` directly against a real session with
    classifiers and all four LLM stages stubbed clean (see the ``stub_stages``
    fixture for why the mock review backend cannot be used here).
    """
    story_id = "s_mod_clean"
    await _seed_draft_storybook(sessions, story_id)

    stub_stages()

    async with sessions() as session:
        await pipeline_mod.run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=1,
            settings=_moderation_settings(),
            generation_provider=MockProvider(responses=[]),
            pii=_pii(),
        )
        await session.commit()

    event = await assert_single_event(
        sessions,
        event_type="moderation_completed",
        entity_type="storybook_version",
        to_state="in_review",
        actor_is_system=True,
    )
    assert event.payload["overall_verdict"] == "pass"
    assert event.payload["repaired"] is False
    # "Clean" means the stages contributed nothing, so the mock reviewer's own
    # stamp is the ONLY row: the run's counts are exactly the stamp and no
    # more. The overall verdict stays "pass" because ADVISORY never gates.
    assert event.payload["counts"] == _with_mock_stamp()

    assert await fetch_events(sessions, "repair_applied") == []


async def test_repaired_moderation_writes_repair_applied_then_completed(
    sessions: async_sessionmaker[AsyncSession],
    stub_stages: Callable[..., None],
) -> None:
    """A soft-flagged run that triggers repair writes exactly one repair_applied
    event followed by exactly one moderation_completed event with
    payload["repaired"] is True.

    Safety FLAGs on the first pass, then reports clean after the repair,
    exercised against a real session so both events land in the durable
    pipeline_event table. The repair itself runs the REAL ``attempt_repair``
    against a MockProvider queued with the revised, schema-valid blob.
    """
    story_id = "s_mod_repair"
    await _seed_draft_storybook(sessions, story_id)

    flag_finding = Finding(
        stage=1,
        source=Source.LLM_SAFETY,
        category="safety",
        node_id="n1",
        verdict=Verdict.FLAG,
        message="too hard",
    )
    # First call (initial moderation) returns the FLAG; second call (post-repair
    # re-moderation) returns clean.
    stub_stages(safety=create_autospec(_real_safety, side_effect=[[flag_finding], []]))
    revised_blob: dict[str, object] = {
        **dict(_CANNED_STORY),
        "title": "The Forest Path (revised)",
    }
    generation_provider = MockProvider(responses=[json.dumps(revised_blob)])

    async with sessions() as session:
        await pipeline_mod.run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=1,
            settings=_moderation_settings(),
            generation_provider=generation_provider,
            pii=_pii(),
        )
        await session.commit()

    repair_event = await assert_single_event(
        sessions,
        event_type="repair_applied",
        entity_type="storybook_version",
        actor_is_system=True,
    )
    assert repair_event.payload == {"stage": "moderation"}

    completed_event = await assert_single_event(
        sessions,
        event_type="moderation_completed",
        entity_type="storybook_version",
        to_state="in_review",
        actor_is_system=True,
    )
    assert completed_event.payload["repaired"] is True

    # repair_applied precedes moderation_completed for this version (WS-D task
    # brief order requirement): the adoption point fires before the report's
    # outcome is persisted and the completion event is recorded.
    assert repair_event.occurred_at <= completed_event.occurred_at


async def test_structural_finding_adds_structural_key_to_moderation_completed_counts(
    sessions: async_sessionmaker[AsyncSession],
    stub_stages: Callable[..., None],
) -> None:
    """A structural finding (a pipeline fail-safe, not a genuine content
    judgment) is counted separately in the ``moderation_completed`` event's
    ``counts`` payload under a ``"structural"`` key, on top of its normal
    verdict-name key (design doc section 2.5, item (a)).

    Stubs Stage 0 with one ADVISORY-verdict structural finding (never gates,
    per report.py's Verdict docstring, so the run stays clean and routes to
    submit): this isolates the ``_verdict_counts`` payload-shaping behavior
    from the Stage-1 collapse mechanics already covered directly against the
    real stage function in tests/unit/test_moderation_stages.py.
    """
    story_id = "s_mod_structural"
    await _seed_draft_storybook(sessions, story_id)

    stub_stages(
        classifiers=[
            Finding(
                stage=0,
                source=Source.PIPELINE,
                category="pipeline",
                node_id=None,
                verdict=Verdict.ADVISORY,
                message="synthetic structural finding for event-payload assertion",
                structural=True,
                # "other" rather than a made-up slug: concern is validated
                # against CONCERN_TAXONOMY at construction, and this test is
                # about the structural key in the event payload, not the
                # concern value.
                concern="other",
            )
        ]
    )

    async with sessions() as session:
        await pipeline_mod.run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=1,
            settings=_moderation_settings(),
            generation_provider=MockProvider(responses=[]),
            pii=_pii(),
        )
        await session.commit()

    event = await assert_single_event(
        sessions,
        event_type="moderation_completed",
        entity_type="storybook_version",
        to_state="in_review",
        actor_is_system=True,
    )
    # The test's own synthetic finding is ADVISORY + structural, and so is the
    # mock reviewer's stamp, so both keys land on 2. Expressing it as the
    # test's contribution PLUS the stamp keeps the two sources distinguishable.
    assert event.payload["counts"] == _with_mock_stamp(advisory=1, structural=1)


async def test_hard_block_moderation_writes_moderation_completed_needs_revision(
    sessions: async_sessionmaker[AsyncSession],
    stub_stages: Callable[..., None],
) -> None:
    """A hard-blocked run (auto_reject, not submit) writes exactly one
    moderation_completed event with to_state="needs_revision" and a payload
    holding only enum verdicts, a bool, and int counts, never the blocking
    finding's message text or category (spec D3 PII-free contract).

    Seeds a classifier BLOCK finding (all four LLM stages stubbed clean)
    against a real session, and asserts the storybook's real routed state
    (``publishing.service.auto_reject`` actually runs here).
    """
    story_id = "s_mod_block"
    await _seed_draft_storybook(sessions, story_id)

    stub_stages(
        classifiers=[
            Finding(
                stage=0,
                source=Source.OPENAI,
                category="sexual/minors",
                node_id="n1",
                verdict=Verdict.BLOCK,
                message="this finding's prose must never reach the event log",
            )
        ]
    )

    async with sessions() as session:
        await pipeline_mod.run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=1,
            settings=_moderation_settings(),
            generation_provider=MockProvider(responses=[]),
            pii=_pii(),
        )
        await session.commit()

    async with sessions() as session:
        story = await session.get(Storybook, story_id)
        assert story is not None
        assert story.status == "needs_revision"

    event = await assert_single_event(
        sessions,
        event_type="moderation_completed",
        entity_type="storybook_version",
        to_state="needs_revision",
        actor_is_system=True,
    )
    # Exact equality (not just key presence) pins that "counts" holds a plain
    # verdict-name -> int mapping: any stray string/float value, or an extra
    # key such as "message"/"category" carrying the finding's own prose,
    # would break this comparison.
    assert event.payload == {
        "overall_verdict": "block",
        "repaired": False,
        "counts": _with_mock_stamp(block=1),
    }


_THRESHOLD_URL = "/api/v1/admin/moderation-thresholds"
_NOISE_FLOOR_URL = "/api/v1/admin/moderation/noise-floor"


async def test_threshold_upsert_emits_threshold_changed_event(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """PUT on a threshold override writes exactly one threshold_changed event,
    attributed to the admin, with a payload carrying action="upsert" plus
    the age_band/category/min_verdict/min_score that were written.
    """
    res = await client.put(
        f"{_THRESHOLD_URL}/3-5",
        params={"category": "violence"},
        json={"min_verdict": "advisory", "min_score": 0.3},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200

    event = await assert_single_event(
        sessions,
        event_type="threshold_changed",
        entity_type="moderation_threshold",
        actor_role="admin",
    )
    assert event.entity_id == "3-5"
    assert event.payload == {
        "age_band": "3-5",
        "category": "violence",
        "action": "upsert",
        "min_verdict": "advisory",
        "min_score": 0.3,
    }


async def test_threshold_delete_emits_threshold_changed_event(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """DELETE on a threshold override writes exactly one threshold_changed
    event with action="delete" and only the keys known at delete time (no
    min_verdict/min_score, since the value no longer exists).
    """
    put_res = await client.put(
        f"{_THRESHOLD_URL}/3-5",
        params={"category": "violence"},
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.admin_token),
    )
    assert put_res.status_code == 200

    res = await client.delete(
        f"{_THRESHOLD_URL}/3-5",
        params={"category": "violence"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200

    events = await fetch_events(sessions, "threshold_changed")
    assert [e.payload["action"] for e in events] == ["upsert", "delete"]
    delete_event = events[-1]
    assert delete_event.entity_type == "moderation_threshold"
    assert delete_event.actor_role == "admin"
    assert delete_event.payload == {
        "age_band": "3-5",
        "category": "violence",
        "action": "delete",
    }


async def test_noise_floor_update_emits_noise_floor_changed_event(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """PUT on the global noise floor writes exactly one noise_floor_changed
    event, attributed to the admin, with a payload carrying only the new
    value.
    """
    res = await client.put(
        _NOISE_FLOOR_URL, json={"value": 0.2}, headers=auth(seed.admin_token)
    )
    assert res.status_code == 200

    event = await assert_single_event(
        sessions,
        event_type="noise_floor_changed",
        entity_type="moderation_setting",
        actor_role="admin",
    )
    assert event.entity_id == "admin_noise_floor"
    assert event.payload == {"value": 0.2}


async def test_assign_writes_book_assigned_event_per_new_assignment(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Assigning a published book to a NEW profile writes exactly one
    book_assigned event, attributed to the guardian.

    The ``seed`` fixture already assigns ``seed.storybook_id`` to
    ``seed.child_profile_id`` (profile_a), so this test adds a second Family A
    child profile and assigns the same book to that new profile instead. This
    keeps the new-event count at exactly one and, together with the assertion
    below, pins that the idempotent skip branch (an already-assigned profile)
    does not also emit an event.
    """
    async with sessions() as session:
        # age_band matches the seed story's "10-13" band (H1): this test
        # assigns the seed story to the sibling and needs the assignment
        # itself to succeed, so the sibling's band must not trip the new
        # age-band ceiling check.
        sibling = ChildProfile(
            family_id=seed.family_id, display_name="Reader A2", age_band="10-13"
        )
        session.add(sibling)
        await session.commit()
        sibling_id = sibling.id

    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.child_profile_id), str(sibling_id)]},
    )
    assert resp.status_code == 200, resp.text

    event = await assert_single_event(
        sessions,
        event_type="book_assigned",
        entity_type="storybook_assignment",
        actor_role="guardian",
    )
    assert event.entity_id == f"{sibling_id}:{seed.storybook_id}"
    assert event.payload == {"child_profile_id": str(sibling_id)}


async def test_unassign_writes_book_unassigned_event(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Unassigning the seeded book from its profile writes exactly one
    book_unassigned event, attributed to the guardian; a second no-op unassign
    writes none.

    The ``seed`` fixture assigns ``seed.storybook_id`` to
    ``seed.child_profile_id``, so the first DELETE removes that row and emits.
    The second finds nothing to remove and must not emit, pinning the count at
    exactly one (the idempotent-no-op arm of the emit-once-per-removed-row
    discipline that mirrors ``assign_storybook``).
    """
    url = f"/api/v1/storybooks/{seed.storybook_id}/assignments/{seed.child_profile_id}"
    first = await client.delete(url, headers=auth(seed.guardian_token))
    assert first.status_code == 200, first.text
    second = await client.delete(url, headers=auth(seed.guardian_token))
    assert second.status_code == 200, second.text

    event = await assert_single_event(
        sessions,
        event_type="book_unassigned",
        entity_type="storybook_assignment",
        actor_role="guardian",
    )
    assert event.entity_id == f"{seed.child_profile_id}:{seed.storybook_id}"
    assert event.payload == {"child_profile_id": str(seed.child_profile_id)}


async def test_rating_writes_rated_event_with_is_update_transition(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Rating the same book twice writes two rated events: the first with
    is_update False (new row), the second with is_update True (overwrite).
    """
    first = await client.post(
        "/api/v1/ratings",
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 3,
        },
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        "/api/v1/ratings",
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 5,
        },
    )
    assert second.status_code == 200, second.text

    events = await fetch_events(sessions, "rated")
    assert len(events) == 2
    assert [e.payload["is_update"] for e in events] == [False, True]
    assert [e.payload["value"] for e in events] == [3, 5]
    for event in events:
        assert event.entity_type == "rating"
        assert event.entity_id == f"{seed.child_profile_id}:{seed.storybook_id}"
        assert event.actor_role == "child"
