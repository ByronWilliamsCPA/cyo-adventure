"""Reset real-backend e2e fixture state to a clean, idempotent starting point.

Run before ``frontend/e2e-real`` specs so a second consecutive
``npm run test:e2e:real`` is green with no manual DB surgery (Phase 4.2,
docs/planning/handoff-test-coverage-robustness-2026-07-22.md)::

    uv run python scripts/reset_e2e_real_state.py

``scripts/seed_dev_data.py`` is intentionally idempotent by early-returning
once its base fixtures exist; it never undoes what a *test run* mutated. Two
classes of cross-run mutation accumulate as a result, each producing a false
failure on the second consecutive real-backend run:

1. ``approval-flow.spec.ts`` approves the seeded review story
   (``s_bridge_builder``, ``scripts/seed_dev_data.py`` ``_REVIEW_STORY``)
   through the real API. A second run finds it already ``published`` (not
   ``in_review``), so the "admin sees the seeded in-review story" assertion
   fails. This script reverts the exact fields ``approve()``
   (``publishing/service.py``) set: ``storybook.status``,
   ``storybook.current_published_version``, ``storybook.visibility``, and
   the version row's ``approved_by``/``published_at``.
2. ``kid-reads.spec.ts``, ``series-continue-real.spec.ts``, and
   ``offline-conflict-real.spec.ts`` leave ``reading_state`` rows pinned at
   an ending (or mid-conflict revision) for the seeded "Dev Reader" profile.
   A second run resumes the reader from that persisted node instead of the
   story's start node, so ``getByTestId('reader')`` and choice-button
   assertions time out waiting for elements that never render (the ending
   screen renders in their place). This script truncates ``reading_state``
   entirely: no spec relies on it surviving between runs, and each spec's
   ``beforeEach``/first navigation recreates it via ``ReaderPage``'s
   mount-time save.
3. ``authored-request.spec.ts`` submits and auto-approves two real story
   requests for the seeded dev-guardian's family every run.
   ``story_requests/service.py::enforce_family_quota`` (ADR-015 G7) counts
   ``story_request`` rows with ``status = 'approved'`` and ``approved_at`` in
   the current UTC calendar month against ``Family.monthly_story_quota``
   (unset for the seed family, so ``settings.default_monthly_story_quota`` =
   10 applies); ``scripts/seed_dev_data.py`` never inserts a ``story_request``
   row itself, so every row for that family is test-created. A few runs
   exhaust the quota and every subsequent ``authored-request.spec.ts`` attempt
   gets the real 409 ("monthly story budget reached") instead of the success
   notice, for the rest of the calendar month. This script deletes every
   ``story_request`` row owned by the seeded dev-guardian's family: nothing
   references ``story_request.id`` as a foreign key (it is a leaf table), so
   this is a plain, unconditional ``DELETE``.

All three operations are no-ops (well-defined, not errors) against a database
that was never touched by these specs, e.g. right after
``docker-compose up -d && uv run python scripts/seed_dev_data.py``: the review
story is already ``in_review``, ``reading_state`` is already empty, and no
``story_request`` row exists yet for the seed family.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from sqlalchemy import text

from cyo_adventure.core.config import settings
from cyo_adventure.core.database import get_engine
from cyo_adventure.core.exceptions import ConfigurationError

# scripts/seed_dev_data.py `_REVIEW_STORY` ("08_tier2_bridge_builder.json"),
# the sole story approval-flow.spec.ts drives through the real approve API.
_REVIEW_STORY_ID = "s_bridge_builder"

# scripts/seed_dev_data.py `_GUARDIAN_SUBJECT`; the family whose monthly
# story-request quota authored-request.spec.ts spends against.
_GUARDIAN_AUTHN_SUBJECT = "dev-guardian"

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _require_local_database() -> None:
    """Refuse to run unless this is unmistakably a disposable local database.

    #CRITICAL: data-integrity: this script issues a raw ``TRUNCATE`` and a
    lifecycle-bypassing ``UPDATE`` against ``storybook``/``storybook_version``
    outside the ``publishing/service.py`` state machine; running either
    against a shared or production database would silently destroy real
    reading progress or unpublish a real book, with no undo.
    #VERIFY: test_reset_e2e_real_state_refuses_non_local_environment,
    test_reset_e2e_real_state_refuses_non_local_host.

    Raises:
        ConfigurationError: If ``settings.environment`` is not ``"local"``,
            or the configured database host is not localhost/127.0.0.1.
    """
    if settings.environment != "local":
        msg = (
            "refusing to reset e2e-real fixture state: environment is "
            f"{settings.environment!r}, not 'local'"
        )
        raise ConfigurationError(msg)
    host = urlsplit(settings.database_url).hostname
    if host not in _LOCAL_HOSTS:
        msg = (
            "refusing to reset e2e-real fixture state: database host "
            f"{host!r} is not local"
        )
        raise ConfigurationError(msg)


async def reset_e2e_real_state() -> None:
    """Revert the seeded review story and clear reading_state for a clean run."""
    _require_local_database()
    engine = get_engine()
    async with engine.begin() as conn:
        # #ASSUME: data-integrity: TRUNCATE (not a scoped DELETE) is safe here
        # because reading_state has no dependent rows: nothing in db/models.py
        # declares a foreign key onto it (completion and rating key off
        # child_profile_id/storybook_id independently, not off this table).
        # #VERIFY: test_reset_e2e_real_state_truncates_reading_state.
        await conn.execute(text("TRUNCATE TABLE reading_state"))
        await conn.execute(
            text(
                "UPDATE storybook_version "
                "SET approved_by = NULL, published_at = NULL "
                "WHERE storybook_id = :story_id"
            ),
            {"story_id": _REVIEW_STORY_ID},
        )
        result = await conn.execute(
            text(
                "UPDATE storybook "
                "SET status = 'in_review', current_published_version = NULL, "
                "visibility = 'family' "
                "WHERE id = :story_id"
            ),
            {"story_id": _REVIEW_STORY_ID},
        )
        # #ASSUME: data-integrity: a plain, unconditional DELETE is safe here
        # because story_request is a leaf table (no other table declares a
        # foreign key onto story_request.id) and seed_dev_data.py never
        # inserts a row into it, so every row owned by this family was
        # created by a prior e2e-real run.
        # #VERIFY: test_reset_e2e_real_state_deletes_story_requests_for_seed_family.
        requests_deleted = await conn.execute(
            text(
                "DELETE FROM story_request "
                'WHERE family_id = (SELECT family_id FROM "user" '
                "WHERE authn_subject = :subject)"
            ),
            {"subject": _GUARDIAN_AUTHN_SUBJECT},
        )
    print(
        "Reset e2e-real fixture state: truncated reading_state; reverted "
        f"{_REVIEW_STORY_ID} to in_review ({result.rowcount} storybook row(s) "
        f"touched); deleted {requests_deleted.rowcount} story_request row(s) "
        "for the seed family (resets the monthly quota)."
    )


def main() -> None:
    """Entry point for the real-backend e2e reset script."""
    asyncio.run(reset_e2e_real_state())


if __name__ == "__main__":
    main()
