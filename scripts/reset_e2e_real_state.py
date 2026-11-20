"""Reset real-backend e2e fixture state to a clean, idempotent starting point.

Run before ``frontend/e2e-real`` specs so a second consecutive
``npm run test:e2e:real`` is green with no manual DB surgery (Phase 4.2,
docs/planning/handoff-test-coverage-robustness-2026-07-22.md)::

    uv run python scripts/reset_e2e_real_state.py

``scripts/seed_dev_data.py`` is intentionally idempotent by early-returning
once its base fixtures exist; it never undoes what a *test run* mutated. Four
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
4. ``full-pipeline-real.spec.ts`` (Phase 7.1, G1) drives a real ``Concept`` ->
   ``GenerationJob`` -> ``Storybook`` through the real RQ worker every run, and
   ``authored-request.spec.ts``'s auto-approved requests do the same under the
   hood (``story_requests/service.py::_build_concept``) whenever a real worker
   is live. Each run leaves a fresh ``storybook`` row whose id is
   ``s_<job-uuid>`` (``generation/worker.py`` persists it under
   ``f"s_{job.id}"``), plus the ``storybook_version``, ``concept``, and
   ``generation_job`` rows behind it. ``scripts/seed_dev_data.py`` never
   creates a ``concept`` row at all (there is no "seeded concept"; see its
   imports), so *every* ``concept`` row in this database was created by a
   prior e2e-real run and is safe to delete unconditionally, independent of
   whether its job ever reached a storybook. This matters beyond the
   happy path: a job whose worker never picks it up (or one abandoned by a
   failed test run) stays ``queued`` forever with no storybook row to key
   off of, so scoping the cleanup to "concepts behind a matched storybook"
   would leak exactly those stuck rows. Left alone, they permanently count
   against ``MAX_ACTIVE_JOBS_PER_FAMILY`` (api/generation.py) until every
   subsequent ``/concepts/{id}/generate`` call 409s for the rest of the
   family's lifetime; this was observed directly while validating this
   script (a run that failed before enqueuing still leaked a ``concept`` row,
   and a dead-worker run left ``queued`` jobs that both exhausted the cap).
   This script deletes every ``storybook`` row whose id matches the
   worker-assigned shape (``s_`` followed by a UUID4, e.g.
   ``s_3f2a1c9e-...``), which never collides with a hand-authored fixture id
   (``s_bridge_builder``, ``s_tide_pools``, ``s_clockwork_garden``,
   ``s_dev_ember_1``/``_2``, any ``sk_*`` skeleton import): those are all
   underscore-slug ids, not UUIDs. ``storybook`` CASCADEs to
   ``storybook_version``, the composite-FK ``reading_state``/``completion``
   rows, ``rating``, ``storybook_assignment``, and ``kid_flag`` (all declared
   ``ondelete="CASCADE"`` in ``db/models.py``), so deleting the matched
   ``storybook`` rows alone clears every one of those dependents. Separately,
   and unconditionally, this script deletes every ``concept`` row outright;
   ``concept_id`` CASCADEs from ``concept`` onto ``generation_job``
   (``ondelete="CASCADE"``, ``NOT NULL``), so this also clears every
   ``generation_job`` row, matched-storybook-linked or stuck-``queued``
   alike, without a separate statement. ``Storybook`` carries no foreign key
   back onto ``concept``, so this never touches a seeded storybook row.
5. ``kid-flag-real.spec.ts`` POSTs a real, structured flag through
   ``POST /api/v1/flags`` (``api/flags.py::create_flag``) every run, which
   both inserts a ``kid_flag`` row AND records a real ``KID_FLAGGED``
   ``pipeline_event`` (``entity_type='kid_flag'``); that spec's own
   ``afterEach`` resolves the flag through the real admin endpoint (so
   ``MAX_OPEN_FLAGS_PER_PROFILE`` never trips), but a *resolved* flag row is
   still a row, and ``notifications/service.py``'s guardian feed composes a
   "Dev Reader flagged a story..." item for EVERY such event regardless of
   resolution status. Across a full-suite invocation this accumulates one
   toast per prior run's flag, and ``reading-history-real.spec.ts``'s
   ``getByText('Dev Reader')`` assertion (matching any of those toasts,
   worded "Dev Reader flagged a story. ...") goes strict-mode-ambiguous once
   more than one is on screen. ``pipeline_event`` is enforced append-only by
   a DB trigger (``trg_pipeline_event_append_only``,
   ``supabase/migrations/20260710000000_baseline.sql``) that raises on any
   ``UPDATE``/``DELETE``, so those event rows can never be purged directly;
   this script does not attempt it. Instead it deletes every ``kid_flag`` row
   for the seed family: ``notifications/service.py::_resolve_kid_flag``
   looks the event's ``entity_id`` up in the ``kid_flag`` table, and
   ``list_guardian_notifications`` drops any candidate event whose entity
   fails to resolve (the sole family-scoping gate; see that function's
   docstring), so a ``kid_flagged`` event whose ``kid_flag`` row no longer
   exists silently stops surfacing as a notification without needing the
   append-only event row itself to be touched. ``kid_flag`` is an ordinary
   (non-append-only) table with ``ondelete="CASCADE"`` on its
   family/profile/storybook-version foreign keys (``db/models.py``), so a
   plain, unconditional ``DELETE`` scoped to the seed family is safe: nothing
   references ``kid_flag.id`` as a foreign key (it is a leaf table), and
   ``scripts/seed_dev_data.py`` never inserts a ``kid_flag`` row itself (kid
   flags are only ever created by a real flag submission), so every row for
   this family was created by a prior e2e-real run.
   #VERIFY: test_reset_e2e_real_state_deletes_kid_flags_for_seed_family,
   test_reset_e2e_real_state_kid_flag_delete_is_noop_on_fresh_seed.

A second, opt-in mode stamps a worker-generated story for approval::

    uv run python scripts/reset_e2e_real_state.py --stamp-fixture-moderation s_<uuid>

The real-backend pipeline tier generates its story with the MOCK reviewer
(``CYO_ADVENTURE_MOCK_REVIEW_JUDGES_SAFE``), and ``moderation/pipeline.py``
stamps every mock-reviewed report ``reviewer_independent=False`` precisely so
that it can never be approved (``publishing/service.py`` refuses it with
``approve_with_unusable_moderation``, and the admin review surface disables
Approve). That is the intended product posture, and it made the approve,
publish, assign, and read steps of ``full-pipeline-real.spec.ts`` and
``connections-enforcement-real.spec.ts`` unreachable on every nightly run.
The specs now assert that refusal first, then call this mode to replace the
mock report with an explicitly labelled fixture judgment (reviewer provider
``e2e-fixture``), standing in for the real reviewer a production deployment
would run, the same way ``scripts/seed_dev_data.py`` hand-writes the seeded
review story's report. Guarded far more narrowly than the reset: local
database only, worker-generated story ids only, ``in_review`` only, and only
over a report that carries the mock-reviewer stamp, so it can never
overwrite a genuine judgment.

All five operations are no-ops (well-defined, not errors) against a database
that was never touched by these specs, e.g. right after
``docker-compose up -d && uv run python scripts/seed_dev_data.py``: the review
story is already ``in_review``, ``reading_state`` is already empty, no
``story_request`` row exists yet for the seed family, no ``storybook`` id
matches the worker-generated UUID shape, and no ``kid_flag`` row exists for
the seed family.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import cast
from urllib.parse import urlsplit

from sqlalchemy import text

from cyo_adventure.core.config import settings
from cyo_adventure.core.database import get_engine
from cyo_adventure.core.exceptions import BusinessLogicError, ConfigurationError
from cyo_adventure.moderation.report import (
    ModerationReport,
    moderation_coverage_incomplete,
    moderation_report_unusable,
)

# scripts/seed_dev_data.py `_REVIEW_STORY` ("08_tier2_bridge_builder.json"),
# the sole story approval-flow.spec.ts drives through the real approve API.
_REVIEW_STORY_ID = "s_bridge_builder"

# scripts/seed_dev_data.py `_GUARDIAN_SUBJECT`; the family whose monthly
# story-request quota authored-request.spec.ts spends against.
_GUARDIAN_AUTHN_SUBJECT = "dev-guardian"

# Tables truncated together in the single statement below. Every table with a
# foreign key onto "reading_state" (or onto another member of this set) MUST
# be listed here: Postgres refuses to TRUNCATE a table referenced by a
# foreign key from a table not named in the same statement
# (FeatureNotSupportedError), and TRUNCATE does not honor ondelete="CASCADE"
# the way DELETE does. This set is not asserted by hand; it is checked
# against live SQLAlchemy metadata (every ForeignKeyConstraint whose
# referenced table lands here must have its own table land here too) by
# test_truncated_tables_cover_every_dependent_foreign_key
# (tests/unit/test_reset_e2e_real_state.py), so a future FK onto
# "reading_state" fails that unit test instead of only this job at e2e time.
_TRUNCATED_TABLES = ("reading_state", "character_book_completion")

# Matches generation/worker.py's f"s_{job.id}" storybook id shape (job.id is a
# GenerationJob UUID primary key, so this is always a lowercase UUID4). Every
# hand-authored/seeded storybook id (s_bridge_builder, s_tide_pools,
# s_clockwork_garden, s_dev_ember_1/_2, any sk_* skeleton import) is an
# underscore slug, never a UUID, so this pattern only ever matches a
# worker-generated storybook.
# #VERIFY: test_reset_e2e_real_state_deletes_worker_generated_storybooks,
# test_reset_e2e_real_state_preserves_seeded_storybooks.
_GENERATED_STORYBOOK_ID_PATTERN = (
    r"^s_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})

# Substrings that unmistakably identify a hosted (staging/production) Supabase
# database host, e.g. ``db.<ref>.supabase.co`` or
# ``aws-0-<region>.pooler.supabase.com``. The localhost allowlist below already
# default-denies these, so this denylist is redundant defense-in-depth: it
# fails louder and, unlike the allowlist, keeps rejecting a real Supabase DSN
# even if ``_LOCAL_HOSTS`` is ever accidentally widened. It does not (and
# cannot) catch a localhost port-forward tunnel to a remote database, whose
# host is literally ``localhost``; that vector stays gated by the
# ``environment == "local"`` check alone.
_REMOTE_HOST_MARKERS = ("supabase.co", "supabase.com")


def _require_local_database(action: str = "reset e2e-real fixture state") -> None:
    """Refuse to run unless this is unmistakably a disposable local database.

    #CRITICAL: data-integrity: this script issues a raw ``TRUNCATE`` and a
    lifecycle-bypassing ``UPDATE`` against ``storybook``/``storybook_version``
    outside the ``publishing/service.py`` state machine; running either
    against a shared or production database would silently destroy real
    reading progress or unpublish a real book, with no undo.
    #VERIFY: test_require_local_database_refuses_non_local_environment,
    test_require_local_database_refuses_non_local_host,
    test_require_local_database_refuses_hosted_supabase_host,
    test_require_local_database_accepts_local (tests/unit/test_reset_e2e_real_state.py).

    Args:
        action: What the caller is about to do, named in the refusal message.

    Raises:
        ConfigurationError: If ``settings.environment`` is not ``"local"``, if
            the configured database host looks like a hosted Supabase project,
            or if the host is not localhost/127.0.0.1.
    """
    if settings.environment != "local":
        msg = (
            f"refusing to {action}: environment is "
            f"{settings.environment!r}, not 'local'"
        )
        raise ConfigurationError(msg)
    host = urlsplit(settings.database_url).hostname
    if host is not None and any(m in host for m in _REMOTE_HOST_MARKERS):
        msg = (
            f"refusing to {action}: database host "
            f"{host!r} looks like a hosted Supabase (staging/production) "
            "database, not a disposable local one"
        )
        raise ConfigurationError(msg)
    if host not in _LOCAL_HOSTS:
        msg = f"refusing to {action}: database host {host!r} is not local"
        raise ConfigurationError(msg)


async def reset_e2e_real_state() -> None:
    """Revert seeded/worker-mutated fixture state for a clean e2e-real run.

    Raises:
        ConfigurationError: Propagated from :func:`_require_local_database` when
            the configured database is not an unmistakably local one (guards
            against running the destructive statements below against a shared
            or production database).
    """
    _require_local_database()
    engine = get_engine()
    async with engine.begin() as conn:
        # #CRITICAL: data-integrity: TRUNCATE (not a scoped DELETE) is safe
        # here only because every table with a foreign key onto reading_state
        # is named in the SAME statement (_TRUNCATED_TABLES). Postgres
        # refuses a TRUNCATE that omits a referencing table
        # (FeatureNotSupportedError) rather than silently truncating past it,
        # so the failure mode of forgetting one here is loud, not silent; the
        # unit test below is what catches it before CI does.
        # CharacterBookCompletion rows are truncated deliberately, not just
        # for the FK: they key off the exact reading_state rows being wiped
        # (composite FK onto reading_state.child_profile_id/storybook_id,
        # ondelete="CASCADE"), and a DELETE would have cascaded them away
        # anyway, so a TRUNCATE that also clears them is semantically
        # equivalent, not a data-loss shortcut.
        # #VERIFY: test_truncated_tables_cover_every_dependent_foreign_key.
        await conn.execute(text(f"TRUNCATE TABLE {', '.join(_TRUNCATED_TABLES)}"))
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
        # #CRITICAL: data-integrity: this DELETE is unconditional (every row,
        # not scoped to a matched storybook or to the seed family), because
        # scripts/seed_dev_data.py never inserts a `concept` row: there is no
        # such thing as a "seeded concept" to protect. Scoping this to
        # concepts reachable from a matched worker-generated storybook (the
        # prior version of this script) leaked any job that never reached a
        # storybook, e.g. one abandoned by a failed test run, or one a dead
        # RQ worker never picked up off the queue; those stuck `queued` rows
        # then permanently count against MAX_ACTIVE_JOBS_PER_FAMILY
        # (api/generation.py) for the rest of the family's lifetime. concept_id
        # CASCADEs (ondelete="CASCADE", NOT NULL) from concept onto
        # generation_job, so this single DELETE also removes every
        # generation_job row, whether or not it ever produced a storybook.
        # #VERIFY: test_reset_e2e_real_state_deletes_concepts_for_generated_storybooks,
        # test_reset_e2e_real_state_deletes_stuck_queued_concepts_without_a_storybook.
        concepts_deleted = await conn.execute(text("DELETE FROM concept"))
        # #CRITICAL: data-integrity: this DELETE relies entirely on
        # `storybook` CASCADEing to storybook_version, reading_state,
        # completion, rating, storybook_assignment, and kid_flag (all
        # ondelete="CASCADE" in db/models.py); a future migration that
        # weakens any of those FKs would turn this into an orphan-row leak
        # rather than a loud failure, since none of those tables are
        # re-checked here.
        # #VERIFY: the companion test
        # test_reset_e2e_real_state_deletes_worker_generated_storybooks
        # confirms the storybook_version/reading_state/storybook_assignment
        # rows for a matched storybook are gone after this statement runs.
        storybooks_deleted = await conn.execute(
            text("DELETE FROM storybook WHERE id ~ :pattern"),
            {"pattern": _GENERATED_STORYBOOK_ID_PATTERN},
        )
        # #ASSUME: data-integrity: a plain, unconditional-per-family DELETE is
        # safe here because kid_flag is a leaf table (no other table declares
        # a foreign key onto kid_flag.id) and seed_dev_data.py never inserts a
        # row into it (a kid flag only ever comes from a real flag
        # submission), so every row for this family was created by a prior
        # e2e-real run. This does NOT touch pipeline_event (append-only,
        # DB-trigger-enforced); it relies entirely on
        # notifications/service.py::_resolve_kid_flag dropping any
        # kid_flagged event whose kid_flag row is gone, so old flag toasts
        # stop accumulating without ever deleting an event row.
        # #VERIFY: test_reset_e2e_real_state_deletes_kid_flags_for_seed_family,
        # test_reset_e2e_real_state_kid_flag_delete_is_noop_on_fresh_seed.
        kid_flags_deleted = await conn.execute(
            text(
                "DELETE FROM kid_flag "
                'WHERE family_id = (SELECT family_id FROM "user" '
                "WHERE authn_subject = :subject)"
            ),
            {"subject": _GUARDIAN_AUTHN_SUBJECT},
        )
    print(
        "Reset e2e-real fixture state: truncated reading_state; reverted "
        f"{_REVIEW_STORY_ID} to in_review ({result.rowcount} storybook row(s) "
        f"touched); deleted {requests_deleted.rowcount} story_request row(s) "
        "for the seed family (resets the monthly quota); deleted "
        f"{concepts_deleted.rowcount} concept row(s) and "
        f"{storybooks_deleted.rowcount} worker-generated storybook row(s) "
        "(cascades their versions/reading-state/assignments); deleted "
        f"{kid_flags_deleted.rowcount} kid_flag row(s) for the seed family "
        "(stops old flag notifications from resurfacing as toasts)."
    )


# Recorded as the report's reviewer provenance so the stamped row names its
# own origin: anyone reading the stored report sees a harness fixture, never
# what looks like a real reviewer run.
_FIXTURE_REVIEWER_PROVIDER = "e2e-fixture"

_STAMP_ACTION = "stamp an e2e-real fixture moderation report"


def build_fixture_moderation_report(
    storybook_id: str, mock_report: object
) -> dict[str, object]:
    """Return a clean, approvable fixture report to replace a mock-reviewed one.

    Pure (no I/O) so its refusals and its output's approvability are unit
    testable without a database.

    Args:
        storybook_id: The story the report belongs to; must be a
            worker-generated ``s_<uuid>`` id.
        mock_report: The currently stored ``moderation_report`` payload.

    Returns:
        dict[str, object]: A ``ModerationReport.to_dict()`` payload with no
        findings, ``reviewer_independent=True``, full coverage, and reviewer
        provenance naming :data:`_FIXTURE_REVIEWER_PROVIDER`.

    Raises:
        BusinessLogicError: If the id is not worker-generated, or the stored
            report is not a mock-reviewer-stamped one.
    """
    # #CRITICAL: security: this writes a report the approval gate accepts, so
    # it must only ever replace a report the gate would refuse BECAUSE the mock
    # reviewer produced it, on a story the worker produced. Seeded and imported
    # ids are slugs, never s_<uuid>, so they cannot reach the write.
    # #VERIFY: tests/unit/test_reset_e2e_real_state.py::
    # test_fixture_report_refuses_a_non_generated_story_id,
    # ::test_fixture_report_refuses_a_report_without_the_mock_stamp.
    if re.fullmatch(_GENERATED_STORYBOOK_ID_PATTERN, storybook_id) is None:
        msg = f"refusing to {_STAMP_ACTION}: {storybook_id!r} is not a worker-generated story id"
        raise BusinessLogicError(msg, rule="e2e_fixture_stamp_scope")
    if not _is_mock_stamped(mock_report):
        msg = (
            f"refusing to {_STAMP_ACTION}: the stored report for {storybook_id!r} "
            "does not carry the mock-reviewer stamp, so it may be a genuine judgment"
        )
        raise BusinessLogicError(msg, rule="e2e_fixture_stamp_scope")
    nodes_reviewed = 0
    aggregate = cast("dict[str, object]", mock_report).get("aggregate")
    if isinstance(aggregate, dict):
        count = cast("dict[str, object]", aggregate).get("nodes_reviewed")
        if isinstance(count, int):
            nodes_reviewed = count
    report = ModerationReport(
        reviewer_independent=True,
        nodes_reviewed=nodes_reviewed,
        reviewer={
            "provider": _FIXTURE_REVIEWER_PROVIDER,
            "model": None,
            "endpoint": [],
            "temperature": None,
            "batch_size": 0,
        },
    ).to_dict()
    # #ASSUME: data-integrity: the fixture exists to be approvable; if a future
    # gate predicate starts refusing it, fail here with a named cause rather
    # than as an opaque 400 inside a Playwright spec.
    # #VERIFY: test_fixture_report_passes_the_approval_predicates.
    if moderation_report_unusable(report) or moderation_coverage_incomplete(report):
        msg = f"refusing to {_STAMP_ACTION}: the fixture report no longer clears the approval gate"
        raise BusinessLogicError(msg, rule="e2e_fixture_stamp_unapprovable")
    return report


def _is_mock_stamped(report: object) -> bool:
    """True when ``report`` is a stored mock-reviewer report.

    Both marks ``moderation/pipeline.py::_stamp_mock_reviewer`` writes must be
    present: ``summary.reviewer_independent is False`` and a
    ``mock_reviewer_active`` finding.

    Args:
        report: The stored ``moderation_report`` payload.

    Returns:
        bool: Whether both mock-reviewer marks are present.
    """
    if not isinstance(report, dict):
        return False
    payload = cast("dict[str, object]", report)
    summary = payload.get("summary")
    if not (
        isinstance(summary, dict)
        and cast("dict[str, object]", summary).get("reviewer_independent") is False
    ):
        return False
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return False
    return any(
        isinstance(finding, dict)
        and cast("dict[str, object]", finding).get("concern") == "mock_reviewer_active"
        for finding in cast("list[object]", findings)
    )


async def stamp_fixture_moderation(storybook_id: str) -> None:
    """Replace a worker-generated story's mock report with a fixture judgment.

    Args:
        storybook_id: The worker-generated ``s_<uuid>`` story to stamp.

    Raises:
        BusinessLogicError: If the story is not ``in_review``, has no version,
            or :func:`build_fixture_moderation_report` refuses it.
    """
    _require_local_database(_STAMP_ACTION)
    engine = get_engine()
    async with engine.begin() as conn:
        # #ASSUME: concurrency: the row is read and written in one transaction
        # with FOR UPDATE, and the pipeline tier runs one Playwright worker, so
        # nothing re-moderates this version between the read and the write.
        # #VERIFY: the e2e-real pipeline specs call this once per story.
        row = (
            await conn.execute(
                text(
                    "SELECT v.version, v.moderation_report, s.status "
                    "FROM storybook s JOIN storybook_version v "
                    "ON v.storybook_id = s.id "
                    "WHERE s.id = :story_id "
                    "ORDER BY v.version DESC LIMIT 1 FOR UPDATE"
                ),
                {"story_id": storybook_id},
            )
        ).first()
        if row is None:
            msg = f"refusing to {_STAMP_ACTION}: no version found for {storybook_id!r}"
            raise BusinessLogicError(msg, rule="e2e_fixture_stamp_scope")
        version = cast("int", row[0])
        stored = cast("object", row[1])
        status = cast("str", row[2])
        if status != "in_review":
            msg = (
                f"refusing to {_STAMP_ACTION}: {storybook_id!r} is {status!r}, "
                "not 'in_review'"
            )
            raise BusinessLogicError(msg, rule="e2e_fixture_stamp_scope")
        report = build_fixture_moderation_report(storybook_id, stored)
        await conn.execute(
            text(
                "UPDATE storybook_version "
                "SET moderation_report = CAST(:report AS jsonb) "
                "WHERE storybook_id = :story_id AND version = :version"
            ),
            {
                "report": json.dumps(report),
                "story_id": storybook_id,
                "version": version,
            },
        )
    print(
        f"Stamped an e2e-fixture moderation report on version {version} of "
        f"{storybook_id} (replacing its mock-reviewer report)."
    )


def main() -> None:
    """Entry point for the real-backend e2e reset script."""
    parser = argparse.ArgumentParser(
        description="Reset real-backend e2e fixture state to a clean starting point."
    )
    parser.add_argument(
        "--stamp-fixture-moderation",
        metavar="STORYBOOK_ID",
        help=(
            "instead of resetting, replace this worker-generated story's "
            "mock-reviewer report with an approvable e2e-fixture report"
        ),
    )
    args = parser.parse_args()
    target = cast("str | None", args.stamp_fixture_moderation)
    if target is not None:
        asyncio.run(stamp_fixture_moderation(target))
        return
    asyncio.run(reset_e2e_real_state())


if __name__ == "__main__":
    main()
