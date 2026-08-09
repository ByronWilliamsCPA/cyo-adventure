"""Seed the development database with a family, a child profile, and stories.

Run against a local Postgres so the reader app has content to serve::

    uv run python scripts/seed_dev_data.py

It creates the schema (if missing), one family with a guardian, an admin, and
a child profile; publishes the two hand-authored Phase 1 stories; leaves a
third story in review with a flagged moderation report so the admin review
queue has work to approve; and seeds a two-book, state-carrying series
("Ember Trail") assigned to the child profile so a continuation flow has
something real to walk. It is idempotent: re-running skips rows that already
exist. This is a development convenience, not a migration; production data
comes through the generation pipeline.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.core.database import Base, get_engine, get_session
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    ProviderModelAllowlist,
    Series,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    User,
)
from cyo_adventure.generation.allowlist import DEFAULT_ALLOWLIST
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.report import Severity

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_VALID = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "storybook" / "valid"
)
_STORIES = ["06_tier1_tide_pools.json", "07_tier2_clockwork_garden.json"]
_REVIEW_STORY = "08_tier2_bridge_builder.json"

_GUARDIAN_SUBJECT = "dev-guardian"
_CHILD_SUBJECT = "dev-child"
_ADMIN_SUBJECT = "dev-admin"
# A guardian who ALSO holds the admin capability (dual-role): use this token
# to exercise both the guardian console and the admin console as one adult.
_DUAL_SUBJECT = "dev-dual"

# Fixed id so naive-kid-misuse-real.spec.ts can request a known cross-family
# profile. Kept in sync with UNRELATED_PROFILE_ID in that spec.
_UNRELATED_PROFILE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

# Fixed id so docs/api/postman-collection.json can POST /admin/profiles into a
# family that is NOT the caller's and that HAS consent, without a dynamic
# lookup. Kept in sync with the `consented_family_id` collection variable.
_CONSENTED_TARGET_FAMILY_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_CONSENTED_TARGET_SUBJECT = "dev-consented-target-guardian"

# Fixed ids/titles so series-continue-real.spec.ts can locate the two books by
# title in the library and follow the reader flow through to book 2 without a
# dynamic lookup of story ids.
_SERIES_TITLE = "Ember Trail"
_SERIES_AGE_BAND = "10-13"
_SERIES_BOOKS = (
    ("s_dev_ember_1", "Ember Trail 1", 1),
    ("s_dev_ember_2", "Ember Trail 2", 2),
)

# Every _series_blob ending shares this title; a single constant avoids the
# repeated literal (SonarCloud S1192) across the 3-4 endings per book.
_ENDING_TITLE = "The End"


def _flagged_moderation_report(node_id: str) -> dict[str, object]:
    """A minimal soft-flag report so the review surface shows a flagged passage."""
    # #ASSUME: data-integrity: this dict must match ModerationReport.to_dict()
    # (src/cyo_adventure/moderation/report.py); approve() only checks non-null,
    # but the review surface reads findings[].node_id/verdict/message.
    # #VERIFY: test_seed_dev_data_seeds_admin_and_review_story.
    return {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "verdict": "flag",
                "message": "Dev seed: sample flag so the review queue has work.",
                "node_id": node_id,
                "score": 0.4,
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


def _assert_gate_clean(blob: Mapping[str, object]) -> None:
    """Raise if a story about to be seeded as published fails the validator gate.

    # #CRITICAL: data-integrity: a Storybook row inserted here with
    # ``status="published"`` is immediately readable by a child; unlike the
    # real generation pipeline (``generation/worker.py``), nothing else in
    # this script runs the deterministic ``validator.gate.run_gate`` two-layer
    # gate before that insert. This is the sole check standing between a
    # regression in this seed data (or in the validator rules themselves) and
    # a child reading a story the gate would have rejected.
    # #VERIFY: this task's manual verification run over every blob this
    # script seeds (see the commit message / PR discussion) proves zero
    # ERROR-severity findings; there is no repo test pinning this today.

    Args:
        blob: The raw story JSON mapping about to be inserted as a published
            ``StorybookVersion``.

    Raises:
        ValidationError: If ``run_gate`` reports any ERROR-severity finding,
            naming the story id and every failing rule id so the failure is
            actionable from the raised message alone.
    """
    story_id_raw = blob.get("id")
    story_id = story_id_raw if isinstance(story_id_raw, str) else "<unknown>"
    result = run_gate(dict(blob))
    errors = [f for f in result.report.findings if f.severity is Severity.ERROR]
    if not errors:
        return
    rule_summary = "; ".join(f"{f.rule_id}: {f.message}" for f in errors)
    message = (
        f"seed_dev_data: refusing to seed story '{story_id}' as published: "
        f"the validator gate reported {len(errors)} ERROR finding(s) "
        f"[{rule_summary}]"
    )
    raise ValidationError(message, field="status", value="published")


def _series_blob(
    story_id: str, title: str, book_index: int, series_id: str
) -> dict[str, object]:
    """Build an eleven-or-thirteen-node story blob for a series book.

    Shaped to pass the full validator gate (``validator.gate.run_gate``) for
    the "10-13" band, not just to parse: PL-25 requires the first decision to
    land at least 2 nodes in (an establishing ``start`` node with a single,
    unconditional choice precedes the first real fork), PL-17 requires at
    least 3 endings and 3 decision nodes, and PL-18's declared
    ``branch_and_bottleneck`` topology requires genuine reconvergence (two
    distinct fork nodes both targeting one ``hub``, which a networkx
    ``DiGraph`` only registers when the predecessors are actually distinct
    nodes; two choices on the same node aimed at the same target collapse to
    one edge and read as a linear spine).

    # #ASSUME: data-integrity: growing this blob to satisfy PL-25 means the
    # reader's first decision is no longer the very first node shown, which
    # is an observable behavior change for any consumer that clicked a choice
    # immediately after landing on a book. `frontend/e2e-real/
    # series-continue-real.spec.ts` does exactly that (it clicks
    # `choice-c_n_e1_brave` right after the reader becomes visible, and
    # asserts `choice-c_n_e2_carried` visible with zero intervening clicks
    # after following "Continue the series"); it will need updating to click
    # through the new prelude node first. This script owns only the seed
    # data, not the e2e spec, so the update is a separate, tracked follow-up.
    # #VERIFY: run the real-backend e2e suite after this change lands and
    # update series-continue-real.spec.ts's click sequence and node-id
    # references to match this shape.
    #
    # #ASSUME: data-integrity: book 2's courage-gated bonus choice (on
    # ``hub``, book_index >= 2 only) is now reachable two ways: a carried
    # courage >= 2 from book 1, or taking this book's own "brave" fork, which
    # also sets courage = 3. The single-book validator walk (Layer 2) has no
    # notion of carried state from a prior book, so a choice reachable ONLY
    # via carry is an unconditional L2-11 dead-branch finding in isolation;
    # giving book 2 its own in-story path to the same threshold is what makes
    # the gate pass while keeping the condition genuinely state-gated rather
    # than always-visible.
    # #VERIFY: test_seed_dev_data_seeds_series_chain covers structural
    # invariants (series id, book_index, entry node); the L2-11 reachability
    # claim itself is proven directly in this task's verification run of
    # ``run_gate`` over the built blob (see PR discussion / commit message),
    # not by a repo test, since scripts/ has no such gate-on-seed test today.

    Args:
        story_id: Fixed storybook id embedded in the blob (``blob["id"]``).
        title: Story title, also used as the passage-body prefix.
        book_index: 1-based position within the series.
        series_id: The just-flushed ``Series.id`` (as a string), embedded in
            ``metadata.series.series_id`` so the book links to a real row.

    Returns:
        A ``Storybook.model_validate``-clean, gate-clean blob whose
        ``metadata.series`` block declares the start node as the series entry
        node and marks the book as state-carrying.
    """
    prefix = f"n_e{book_index}"
    start = f"{prefix}_start"
    decision1 = f"{prefix}_decision1"
    fork_brave = f"{prefix}_fork_brave"
    fork_plain = f"{prefix}_fork_plain"
    hub = f"{prefix}_hub"
    path_explore = f"{prefix}_explore"
    path_rush = f"{prefix}_rush"
    decision3 = f"{prefix}_decision3"
    end_explore = f"{prefix}_end_explore"
    end_careful = f"{prefix}_end_careful"
    end_hasty = f"{prefix}_end_hasty"
    bonus = f"{prefix}_bonus"
    end_bonus = f"{prefix}_end_bonus"

    # hub is the PL-18 bottleneck: fork_brave and fork_plain are two distinct
    # predecessor nodes that both target it, so it has in-degree 2 (genuine
    # reconvergence), unlike two same-source choices aimed at one target.
    hub_choices: list[dict[str, object]] = [
        {
            "id": f"c_{prefix}_explore",
            "label": "Explore the ridge",
            "target": path_explore,
        },
        {
            "id": f"c_{prefix}_rush",
            "label": "Rush along the trail",
            "target": path_rush,
        },
    ]
    if book_index >= 2:
        hub_choices.append(
            {
                # Named "_carried", not "_courage": this id is the load-bearing
                # test id of the carries_state proof in
                # frontend/e2e-real/series-continue-real.spec.ts, whose negative
                # half asserts toHaveCount(0). Renaming it makes that assertion
                # pass vacuously (a missing id has count 0 too), so the id is
                # part of the contract and not free to change.
                "id": f"c_{prefix}_carried",
                "label": "Draw on your carried courage",
                "target": bonus,
                "condition": {">=": [{"var": "courage"}, 2]},
            }
        )

    nodes: list[dict[str, object]] = [
        {
            "id": start,
            "body": f"{title}: the trail begins.",
            "is_ending": False,
            "choices": [
                {"id": f"c_{prefix}_start_on", "label": "Set out", "target": decision1}
            ],
        },
        {
            "id": decision1,
            "body": f"{title}: a fork in the path demands a choice.",
            "is_ending": False,
            "choices": [
                {
                    "id": f"c_{prefix}_brave",
                    "label": "Face it with courage",
                    "target": fork_brave,
                    "effects": [{"op": "set", "var": "courage", "value": 3}],
                },
                {
                    "id": f"c_{prefix}_plain",
                    "label": "Walk on carefully",
                    "target": fork_plain,
                },
            ],
        },
        {
            "id": fork_brave,
            "body": f"{title}: courage steadies your steps.",
            "is_ending": False,
            "choices": [
                {"id": f"c_{prefix}_fork_brave_on", "label": "Onward", "target": hub}
            ],
        },
        {
            "id": fork_plain,
            "body": f"{title}: careful steps carry you onward.",
            "is_ending": False,
            "choices": [
                {"id": f"c_{prefix}_fork_plain_on", "label": "Onward", "target": hub}
            ],
        },
        {
            "id": hub,
            "body": f"{title}: the trail opens onto a ridge.",
            "is_ending": False,
            "choices": hub_choices,
        },
        {
            "id": path_explore,
            "body": f"{title}: the ridge reveals a hidden view.",
            "is_ending": False,
            "choices": [
                {
                    "id": f"c_{prefix}_explore_on",
                    "label": "Onward",
                    "target": end_explore,
                }
            ],
        },
        {
            "id": path_rush,
            "body": f"{title}: the trail narrows ahead.",
            "is_ending": False,
            "choices": [
                {"id": f"c_{prefix}_rush_on", "label": "Onward", "target": decision3}
            ],
        },
        {
            "id": decision3,
            "body": f"{title}: the last stretch offers one more choice.",
            "is_ending": False,
            "choices": [
                {
                    "id": f"c_{prefix}_careful",
                    "label": "Take the careful way",
                    "target": end_careful,
                },
                {
                    "id": f"c_{prefix}_hasty",
                    "label": "Take the hasty way",
                    "target": end_hasty,
                },
            ],
        },
        {
            "id": end_explore,
            "body": f"{title}: the view makes the whole journey worth it.",
            "is_ending": True,
            "ending": {
                "id": f"e_{prefix}_explore",
                "valence": "positive",
                "kind": "success",
                "title": _ENDING_TITLE,
            },
            "choices": [],
        },
        {
            "id": end_careful,
            "body": f"{title}: journey's end, safely reached.",
            "is_ending": True,
            "ending": {
                "id": f"e_{prefix}_careful",
                "valence": "positive",
                "kind": "completion",
                "title": _ENDING_TITLE,
            },
            "choices": [],
        },
        {
            "id": end_hasty,
            "body": f"{title}: haste costs you a scraped knee, but you make it.",
            "is_ending": True,
            "ending": {
                "id": f"e_{prefix}_hasty",
                "valence": "negative",
                "kind": "setback",
                "title": _ENDING_TITLE,
            },
            "choices": [],
        },
    ]
    if book_index >= 2:
        nodes.append(
            {
                "id": bonus,
                "body": f"{title}: your courage opens a hidden shortcut.",
                "is_ending": False,
                "choices": [
                    {
                        "id": f"c_{prefix}_bonus_on",
                        "label": "Take it",
                        "target": end_bonus,
                    }
                ],
            }
        )
        nodes.append(
            {
                "id": end_bonus,
                "body": f"{title}: the shortcut leads to a triumphant finish.",
                "is_ending": True,
                "ending": {
                    "id": f"e_{prefix}_bonus",
                    "valence": "positive",
                    "kind": "success",
                    "title": _ENDING_TITLE,
                },
                "choices": [],
            }
        )

    ending_count = 4 if book_index >= 2 else 3
    return {
        "schema_version": "2.0",
        "id": story_id,
        "version": 1,
        "title": title,
        "metadata": {
            "age_band": _SERIES_AGE_BAND,
            "reading_level": {"scheme": "flesch_kincaid", "target": 4.0},
            # Tier 2, not 1: the model forbids variables on tier 1 stories
            # (_check_tier_variables), and this blob declares "courage".
            "tier": 2,
            "estimated_minutes": 2,
            "ending_count": ending_count,
            "topology": "branch_and_bottleneck",
            "series": {
                "series_id": series_id,
                "book_index": book_index,
                "series_entry_node": start,
                "is_final": False,
                "carries_state": True,
            },
        },
        "variables": [
            {"name": "courage", "type": "int", "initial": 0, "min": 0, "max": 5}
        ],
        "start_node": start,
        "nodes": nodes,
    }


async def _seed_series_chain(session: AsyncSession) -> bool:
    """Idempotently seed the two-book, state-carrying series for the dev profile.

    Inserts one ``Series`` row plus two published ``Storybook``/
    ``StorybookVersion``/``StorybookAssignment`` rows (books 1 and 2), so
    ``series-continue-real.spec.ts`` can play book 1 to its ending, follow
    "Continue the series", and land on book 2. The ``Series`` row is flushed
    first so its real id can be embedded in each book's blob.

    Guarded on book 1's fixed storybook id (mirroring the fixed-profile-id
    guard in ``_seed_unrelated_family``) so a database seeded BEFORE this
    fixture existed still gains it on a re-run. The dev family, guardian, and
    child profile are resolved from the database: on a fresh seed the base
    rows were just added (autoflush makes them visible), and on an
    already-seeded database they are read back from their rows.

    Args:
        session: The active seed session.

    Returns:
        True when it inserted the series, False when it already existed or
        the base dev family is absent.
    """
    existing_book = await session.scalar(
        select(Storybook.id).where(Storybook.id == _SERIES_BOOKS[0][0])
    )
    if existing_book is not None:
        return False
    # #ASSUME: data integrity: the series hangs off the base dev family,
    # guardian, and child profile; if any is missing (a half-seeded database),
    # skip rather than insert orphan rows pointing at absent parents.
    # #VERIFY: test_seed_dev_data_backfills_series_chain_on_existing_db.
    guardian = await session.scalar(
        select(User).where(User.authn_subject == _GUARDIAN_SUBJECT)
    )
    child = await session.scalar(
        select(User).where(User.authn_subject == _CHILD_SUBJECT)
    )
    if guardian is None or child is None or child.child_profile_id is None:
        return False

    published_at = datetime.now(UTC)
    series = Series(
        family_id=guardian.family_id,
        title=_SERIES_TITLE,
        age_band=_SERIES_AGE_BAND,
        carries_state=True,
        created_by=guardian.id,
    )
    session.add(series)
    await session.flush()

    for story_id, title, book_index in _SERIES_BOOKS:
        blob = _series_blob(story_id, title, book_index, str(series.id))
        _assert_gate_clean(blob)
        session.add(
            Storybook(
                id=story_id,
                family_id=guardian.family_id,
                current_published_version=1,
                status="published",
                series_id=series.id,
                book_index=book_index,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob=blob,
                approved_by=guardian.id,
                published_at=published_at,
            )
        )
        # #ASSUME: concurrency: StorybookAssignment has a composite primary
        # key on (child_profile_id, storybook_id); the fixed-id existence
        # check at the top of this function (not seed_dev_data's early
        # return, which guards the base seed only) is what keeps a second
        # run from duplicating these rows.
        # #VERIFY: test_seed_dev_data_seeds_series_chain,
        # test_seed_dev_data_backfills_series_chain_on_existing_db.
        session.add(
            StorybookAssignment(
                child_profile_id=child.child_profile_id,
                storybook_id=story_id,
                assigned_by=guardian.id,
            )
        )
    return True


async def _seed_dual_role_user(session: AsyncSession) -> bool:
    """Idempotently seed the dual-role (guardian + admin capability) adult.

    A late-added fixture with its own existence check, so a database seeded
    before the dual-role model existed still gains the user on a re-run
    (the guardian early return in ``seed_dev_data`` guards the base seed
    only). Hangs off the base dev family; skips on a half-seeded database.

    Args:
        session: The active seed session.

    Returns:
        True when it inserted the user, False when it already existed or
        the base dev family is absent.
    """
    existing = await session.scalar(
        select(User).where(User.authn_subject == _DUAL_SUBJECT)
    )
    if existing is not None:
        return False
    guardian = await session.scalar(
        select(User).where(User.authn_subject == _GUARDIAN_SUBJECT)
    )
    if guardian is None:
        return False
    now = datetime.now(UTC)
    session.add(
        User(
            family_id=guardian.family_id,
            role="guardian",
            is_admin=True,
            authn_subject=_DUAL_SUBJECT,
            consent_accepted_at=now,
            consent_policy_version="dev-seed",
            consent_signer_name="Dev Dual-Role Guardian",
            consent_ip="127.0.0.1",
            # O-117/O-119: dev data mirrors production shape (consent_* is
            # always written alongside these two by api/onboarding.py::
            # _record_consent) and satisfies ck_user_residence_adulthood_pairing.
            residence_country="US",
            adulthood_attested_at=now,
        )
    )
    return True


async def _seed_unrelated_family(session: AsyncSession) -> bool:
    """Idempotently seed the cross-family fixture profile.

    Returns True when it inserted the fixture, False when it already existed.
    Guarded on the fixed profile id (not the guardian) so it self-heals on a
    database seeded before this fixture was added.
    """
    exists = await session.scalar(
        select(ChildProfile.id).where(ChildProfile.id == _UNRELATED_PROFILE_ID)
    )
    if exists is not None:
        return False
    unrelated_family = Family(name="Unrelated Family")
    session.add(unrelated_family)
    await session.flush()
    session.add(
        ChildProfile(
            id=_UNRELATED_PROFILE_ID,
            family_id=unrelated_family.id,
            display_name="Unrelated Reader",
            age_band="8-11",
        )
    )
    return True


async def _seed_consented_target_family(session: AsyncSession) -> bool:
    """Idempotently seed a consented family that is nobody's caller family.

    ``api/admin_profiles.py::_require_family_consent`` gates
    ``POST /api/v1/admin/profiles`` on the TARGET family holding consent, so
    the collection needs a family it can create into that satisfies the gate.
    The "Newman Ops Family" the collection builds at runtime cannot: it is
    created through ``POST /api/v1/admin/families`` and its only adult is a
    ``pending`` invite, which carries no ``consent_accepted_at``. That family
    is still used, as the negative case for the same gate.

    Deliberately seeded with no child profiles, so the collection's
    family-filtered listing sees exactly what the collection itself created.

    Returns:
        True when it inserted the family, False when it already existed.
    """
    exists = await session.scalar(
        select(Family.id).where(Family.id == _CONSENTED_TARGET_FAMILY_ID)
    )
    if exists is not None:
        return False
    session.add(Family(id=_CONSENTED_TARGET_FAMILY_ID, name="Consented Target Family"))
    await session.flush()
    now = datetime.now(UTC)
    session.add(
        User(
            family_id=_CONSENTED_TARGET_FAMILY_ID,
            role="guardian",
            authn_subject=_CONSENTED_TARGET_SUBJECT,
            consent_accepted_at=now,
            consent_policy_version="dev-seed",
            consent_signer_name="Consented Target Guardian",
            consent_ip="127.0.0.1",
            # O-117/O-119: both columns must be non-null together, and only
            # when consent_accepted_at is set (ck_user_residence_adulthood_pairing).
            residence_country="US",
            adulthood_attested_at=now,
        )
    )
    return True


async def _seed_provider_allowlist(session: AsyncSession) -> bool:
    """Idempotently seed the provider/model allowlist from ``DEFAULT_ALLOWLIST``.

    Restores the rows the retired Alembic migration inserted. ADR-012 moved the
    schema to a schema-only Supabase baseline, so a database provisioned from
    the migration chain alone (a fresh Supabase project, a CI compose db, a new
    local dev stack) has an empty ``provider_model_allowlist`` and rejects every
    generation request at the authoring-plan gate. Guarded per
    ``(provider, model_id)`` so it self-heals a database seeded before this was
    added and never duplicates on a re-run.

    Returns True when it inserted at least one row, False when every pair
    already existed.

    Args:
        session: Open async session bound to the seed target database.

    Returns:
        Whether any allowlist row was inserted.
    """
    # #CRITICAL: security: these rows gate which (provider, model_id) pairs may
    # bill against a generation backend; generation/allowlist.py::
    # is_enabled_allowlist_pair is the single read path the authoring-plan
    # endpoint trusts. Seeding exactly the enabled DEFAULT_ALLOWLIST pairs keeps
    # the code-side mirror and the database in sync, the invariant the retired
    # test_seed_matches_default_allowlist guarded.
    # #VERIFY: test_seed_dev_data_seeds_provider_allowlist.
    rows = await session.execute(
        select(ProviderModelAllowlist.provider, ProviderModelAllowlist.model_id)
    )
    existing = {(provider, model_id) for provider, model_id in rows.all()}
    inserted = False
    for seed in DEFAULT_ALLOWLIST:
        if (seed.provider, seed.model_id) in existing:
            continue
        session.add(
            ProviderModelAllowlist(
                provider=seed.provider,
                model_id=seed.model_id,
                enabled=True,
                display_name=seed.display_name,
            )
        )
        inserted = True
    return inserted


async def seed_dev_data(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> None:
    """Create the schema and insert the demo family, profile, and stories.

    Args:
        engine: Async engine to create the schema on. Defaults to the app's
            shared engine (``get_engine()``); tests inject a testcontainers
            engine here.
        session_factory: Callable returning a new ``AsyncSession``. When
            omitted it is derived from ``engine`` so schema creation and row
            inserts always target the same database; if ``engine`` is omitted
            too, it defaults to the app's ``get_session``.
    """
    active_engine = engine if engine is not None else get_engine()
    async with active_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # #ASSUME: data integrity: schema creation and row inserts must hit the same
    # database. When only ``engine`` is injected, bind the session factory to it
    # so a caller cannot create the schema on one engine while inserting through
    # the app's default ``get_session`` (a silent split-database footgun).
    # #VERIFY: seed_dev_data(engine=X) with no session_factory writes to X.
    if session_factory is not None:
        new_session = session_factory
    elif engine is not None:
        new_session = async_sessionmaker(active_engine, expire_on_commit=False)
    else:
        new_session = get_session

    async with new_session() as session:
        # #ASSUME: security: a second, wholly unrelated family exists solely so
        # naive-kid-misuse-real.spec.ts can prove authorize_profile rejects a
        # cross-family profile id, not just a cross-profile-same-family id.
        # No guardian/admin User rows are seeded for this family: the test only
        # needs the child profile to exist, not a full principal set. Seeded
        # here (before the guardian early return) with its own existence check
        # so a database seeded BEFORE this fixture was added still gains it on a
        # re-run; gating it on guardian-absence would skip it forever on any
        # already-seeded dev DB and break the real-backend cross-family spec.
        # #VERIFY: test_seed_dev_data_seeds_unrelated_family_profile.
        unrelated_profile_seeded = await _seed_unrelated_family(session)

        # Seeded here (before the guardian early return) with its own per-row
        # existence check so an already-seeded dev/CI database, or one built
        # from the schema-only Supabase baseline, still gains the allowlist rows
        # on a re-run; gating on guardian-absence would skip them forever.
        allowlist_seeded = await _seed_provider_allowlist(session)

        # Same placement rationale as the two above: its own existence check,
        # ahead of the guardian early return, so an already-seeded database
        # gains it on a re-run rather than skipping it forever.
        consented_target_seeded = await _seed_consented_target_family(session)

        existing = await session.scalar(
            select(User).where(User.authn_subject == _GUARDIAN_SUBJECT)
        )
        if existing is not None:
            # The early return below guards the BASE seed only. Seed groups
            # added after dev databases already existed (the cross-family
            # fixture above, the Ember Trail series here, the dual-role
            # adult) carry their own existence checks and run before it, so
            # an already-seeded database still gains them on a re-run;
            # gating them on guardian-absence would skip them forever.
            series_chain_seeded = await _seed_series_chain(session)
            dual_user_seeded = await _seed_dual_role_user(session)
            if (
                unrelated_profile_seeded
                or series_chain_seeded
                or allowlist_seeded
                or dual_user_seeded
                or consented_target_seeded
            ):
                await session.commit()
            print(
                "Dev data already seeded; refreshed late-added fixtures "
                "(cross-family profile, series chain, provider allowlist, "
                "dual-role adult, consented target family) if missing."
            )
            return

        family = Family(name="Dev Family")
        session.add(family)
        await session.flush()

        profile = ChildProfile(
            family_id=family.id, display_name="Dev Reader", age_band="10-13"
        )
        session.add(profile)
        await session.flush()

        # Phase 2 / ADR-018 D1 (VPC): api/profiles.py::_require_consent rejects
        # POST /api/v1/profiles for a guardian with no recorded consent, so
        # every seeded guardian must carry it -- otherwise the newman suite
        # (docs/api/postman-collection.json), which authenticates as
        # dev-guardian via this exact row, 400s on profile creation. Mirrors
        # tests/integration/conftest.py::_consented.
        consent_now = datetime.now(UTC)
        consent_kwargs = {
            "consent_accepted_at": consent_now,
            "consent_policy_version": "dev-seed",
            "consent_signer_name": "Dev Guardian",
            "consent_ip": "127.0.0.1",
            # O-117/O-119: dev data mirrors production shape and satisfies
            # ck_user_residence_adulthood_pairing (both new columns must be
            # non-null together, and only when consent_accepted_at is set).
            "residence_country": "US",
            "adulthood_attested_at": consent_now,
        }

        guardian = User(
            family_id=family.id,
            role="guardian",
            authn_subject=_GUARDIAN_SUBJECT,
            **consent_kwargs,
        )
        session.add(guardian)
        await session.flush()

        session.add(
            User(
                family_id=family.id,
                role="child",
                authn_subject=_CHILD_SUBJECT,
                child_profile_id=profile.id,
            )
        )
        session.add(
            User(
                family_id=family.id,
                role="admin",
                is_admin=True,
                authn_subject=_ADMIN_SUBJECT,
            )
        )
        session.add(
            User(
                family_id=family.id,
                role="guardian",
                is_admin=True,
                authn_subject=_DUAL_SUBJECT,
                **{**consent_kwargs, "consent_signer_name": "Dev Dual-Role Guardian"},
            )
        )

        # #ASSUME: data integrity: published_at must be timezone-aware to match
        # StorybookVersion.published_at, a TIMESTAMP WITH TIME ZONE column
        # (_TS = DateTime(timezone=True) in db/models.py). A naive datetime
        # would be ambiguous about which zone it represents.
        # #VERIFY: datetime.now(UTC) always returns a tz-aware value.
        published_at = datetime.now(UTC)

        for filename in _STORIES:
            blob = json.loads((_VALID / filename).read_text(encoding="utf-8"))
            story_id = str(blob["id"])
            version = int(blob["version"])
            _assert_gate_clean(blob)
            session.add(
                Storybook(
                    id=story_id,
                    family_id=family.id,
                    current_published_version=version,
                    status="published",
                )
            )
            session.add(
                StorybookVersion(
                    storybook_id=story_id,
                    version=version,
                    blob=blob,
                    approved_by=guardian.id,
                    published_at=published_at,
                )
            )
            # #ASSUME: concurrency: StorybookAssignment has a composite primary
            # key on (child_profile_id, storybook_id), so inserting one row per
            # seeded story here relies on this function never re-running for an
            # already-seeded family (the guardian-existence guard above returns
            # early before reaching this loop on a re-run).
            # #VERIFY: the early return at the top of this function is the only
            # idempotency guard; a caller that seeds without it would violate
            # the composite primary key on a second run.
            session.add(
                StorybookAssignment(
                    child_profile_id=profile.id,
                    storybook_id=story_id,
                    assigned_by=guardian.id,
                )
            )

        # #ASSUME: concurrency: the review-story Storybook/Version/Assignment
        # inserts share the composite-PK / no-rerun assumption tagged on the
        # published-story loop above; the function-level early return is the
        # sole guard against a second run duplicating these rows.
        # #VERIFY: test_seed_dev_data_seeds_admin_and_review_story.
        review_blob = json.loads((_VALID / _REVIEW_STORY).read_text(encoding="utf-8"))
        review_id = str(review_blob["id"])
        review_version = int(review_blob["version"])
        first_node_id = str(review_blob["nodes"][0]["id"])
        session.add(
            Storybook(
                id=review_id,
                family_id=family.id,
                current_published_version=None,
                status="in_review",
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=review_id,
                version=review_version,
                blob=review_blob,
                moderation_report=_flagged_moderation_report(first_node_id),
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=profile.id,
                storybook_id=review_id,
                assigned_by=guardian.id,
            )
        )

        # Fresh-database path: the series chain needs the base family,
        # guardian, and child profile just added above, so it cannot run at
        # the pre-early-return site the way _seed_unrelated_family does; its
        # internal existence check still makes this call idempotent.
        await _seed_series_chain(session)

        await session.commit()
        print(
            f"Seeded family {family.id}, profile {profile.id}, admin user, "
            f"{len(_STORIES)} published stories, 1 in-review story "
            f"({review_id}) awaiting approval, the 2-book '{_SERIES_TITLE}' "
            f"series, and {len(DEFAULT_ALLOWLIST)} provider-allowlist rows."
        )


def main() -> None:
    """Entry point for the dev seed script."""
    asyncio.run(seed_dev_data())


if __name__ == "__main__":
    main()
