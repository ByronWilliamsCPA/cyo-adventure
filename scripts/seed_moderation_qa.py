"""Seed the staging Moderation QA corpus as real, unpublishable storybook rows.

Implements moderation-review-redesign-2026-07-28.md section 5: a set of
labeled test storybooks (``docs/planning/safety/moderation-qa-corpus.json`` +
``tests/fixtures/moderation_qa/books/*.json``) seeded into staging as real
``storybook``/``storybook_version`` rows, so the real worker code path
(classifiers, reviewer, repair attempt, routing) processes a known-bad book
end to end. Inappropriate content never needs to exist in production: this
script hard-refuses to run outside staging.

What this corpus does and does not exercise
-------------------------------------------

Exercised for every fixture: stage 0-N classifiers, the review provider, the
leaf-diversity guard, verdict aggregation, and submit/auto_reject routing.

Exercised for five of the six fixtures: the soft-gate auto-repair path
*including adoption*. ``moderation/pipeline.py`` only adopts a repaired blob
that itself passes ``validator/gate.py::run_gate``, so a fixture that cannot
clear the gate can have a repair attempted but never adopted. Those five
fixtures are gate-clean (PL-16/PL-17/PL-18 all pass; only advisory L1-7 node
budget and RL-13 reading-level warnings remain, neither of which blocks).

NOT exercised, by design, for ``mqa_borderline_storm_watch_5_8``: repair
adoption. That fixture declares intense scariness and peril at the 5-8 band,
whose ceiling is mild, so ``run_gate`` raises PL-16 twice. Being off-ceiling
IS the test, so this is intended behaviour, not a defect to fix, and the
consequence is that a repair for this one book can be generated but never
adopted. If a future change needs repair-adoption coverage on a
ceiling-violating book, that needs a new fixture (or a pipeline change), not
a softening of this one.

Run against staging::

    ENVIRONMENT=staging CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/seed_moderation_qa.py

Insert the fixture rows without running moderation (cheap, no LLM calls;
useful for re-seeding or inspecting the raw draft rows)::

    ENVIRONMENT=staging CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/seed_moderation_qa.py --skip-moderation

Idempotent by design: a book id already present in the database is never
re-inserted. Moderation is driven off persisted state rather than off "what
this run inserted", so it is genuinely retryable: every manifest book whose
version-1 row still has a NULL ``moderation_report`` is moderated, whether it
was inserted moments ago, seeded earlier with ``--skip-moderation``, or left
unmoderated because a previous run's provider call failed. A book that
already carries a report is left alone.

Containment (moderation-review-redesign-2026-07-28.md section 5, point 3):

- the environment guard below hard-refuses anything but ``ENVIRONMENT=staging``,
  the same posture as ``scripts/seed_staging.py``;
- every row uses the ``mqa_`` id namespace and belongs to a dedicated
  "Moderation QA" family that never gets a ``ChildProfile``, so there is no
  profile in this family for a ``StorybookAssignment`` to ever target;
- this script never assigns a book to any profile and never calls
  ``publishing/service.py::approve`` -- the existing read gate (approved AND
  assigned) already makes an unassigned, unapproved book invisible to every
  kid surface, and the moderation pipeline itself only ever calls
  ``submit``/``auto_reject`` (see ``moderation/pipeline.py``'s own
  "guardian is the FINAL gate" invariant), never ``approve``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.database import Base, get_engine
from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.db.models import Family, Storybook, StorybookVersion
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.moderation.pipeline import run_moderation_pipeline
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_logger = get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_PATH = (
    _REPO_ROOT / "docs" / "planning" / "safety" / "moderation-qa-corpus.json"
)

# Fixed id (mirrors the _UNRELATED_PROFILE_ID / _SERIES_BOOKS fixed-id pattern
# in scripts/seed_dev_data.py) so re-running this script always resolves the
# same family row instead of minting a new one via the UUIDPrimaryKeyMixin
# default every time.
_QA_FAMILY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_QA_FAMILY_NAME = "Moderation QA"

_FIRST_VERSION = 1


def _require_staging_or_exit() -> str:
    """Refuse to run unless ``ENVIRONMENT=staging``.

    #CRITICAL: security: this is containment layer 1 of 4 (design section 5,
    point 3). QA fixtures deliberately include a bright-line-block book and
    several band-borderline books; running this script against production
    (or any non-staging target) would put that content into a real database.
    #VERIFY: test_require_staging_or_exit_refuses_non_staging in
    tests/unit/test_seed_moderation_qa.py.

    Returns:
        The validated ``"staging"`` environment string.
    """
    environment = os.environ.get("ENVIRONMENT", "")
    if environment != "staging":
        sys.exit(
            "seed_moderation_qa: refusing to run because ENVIRONMENT="
            f"{environment!r}, not 'staging'. This script seeds deliberately "
            "off-band and bright-line-block test content; it must never run "
            "against production or any other environment."
        )
    return environment


def _read_json_or_fail(path: Path, what: str) -> Any:
    """Read and parse a JSON file, naming the offending path on any failure.

    Args:
        path: The file to read.
        what: Short description of the file, used in the error message.

    Returns:
        The parsed JSON document.

    Raises:
        ConfigurationError: If the file is missing/unreadable or is not valid
            JSON. The message names ``path`` so an operator can fix it without
            reading a traceback.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"{what} is unreadable: {path}"
        raise ConfigurationError(msg, details={"path": str(path)}) from exc
    except json.JSONDecodeError as exc:
        msg = f"{what} is not valid JSON: {path}"
        raise ConfigurationError(msg, details={"path": str(path)}) from exc


def load_manifest() -> list[dict[str, Any]]:
    """Load the moderation QA corpus manifest's book entries.

    Returns:
        The manifest's ``books`` array (id, file path, expected labels).

    Raises:
        ConfigurationError: If the manifest is missing, is not valid JSON, or
            has no ``books`` array.
    """
    manifest = _read_json_or_fail(_MANIFEST_PATH, "moderation QA corpus manifest")
    if not isinstance(manifest, dict) or "books" not in manifest:
        msg = f"moderation QA corpus manifest has no 'books' array: {_MANIFEST_PATH}"
        raise ConfigurationError(msg, details={"path": str(_MANIFEST_PATH)})
    books: list[dict[str, Any]] = manifest["books"]
    return books


def _load_blob(entry: dict[str, Any]) -> dict[str, Any]:
    """Load a manifest entry's storybook JSON blob.

    Args:
        entry: One manifest book entry (carries a repo-relative ``file`` path).

    Returns:
        The parsed storybook blob.

    Raises:
        ConfigurationError: If the entry has no ``file`` key, or the file is
            missing or is not valid JSON.
    """
    if "file" not in entry:
        book_id = entry.get("id", "<no id>")
        msg = f"moderation QA manifest entry {book_id!r} has no 'file' key"
        raise ConfigurationError(msg, details={"manifest": str(_MANIFEST_PATH)})
    path = _REPO_ROOT / str(entry["file"])
    blob: dict[str, Any] = _read_json_or_fail(path, "moderation QA fixture storybook")
    return blob


async def _ensure_qa_family(session: AsyncSession) -> Family:
    """Idempotently resolve the dedicated Moderation QA family.

    #CRITICAL: security: containment layer 2 of 4. Every QA book belongs to
    this family, and this family is never given a ``ChildProfile`` by any
    code path in this script, so no ``StorybookAssignment`` can ever be
    inserted for a real (or fixture) child against it -- the read gate's
    assignment half is unsatisfiable by construction, not just by omission.
    #VERIFY: test_ensure_qa_family_never_creates_a_child_profile and
    test_seed_never_creates_a_child_profile_anywhere in
    tests/unit/test_seed_moderation_qa.py.

    Args:
        session: The active seed session.

    Returns:
        The Moderation QA family row (existing or freshly inserted).
    """
    existing = await session.get(Family, _QA_FAMILY_ID)
    if existing is not None:
        return existing
    family = Family(id=_QA_FAMILY_ID, name=_QA_FAMILY_NAME)
    session.add(family)
    await session.flush()
    return family


async def _seed_fixture_rows(
    session: AsyncSession, family: Family, books: list[dict[str, Any]]
) -> list[str]:
    """Idempotently insert draft Storybook/StorybookVersion rows for new books.

    #CRITICAL: security: containment layer 3 of 4. Every inserted
    ``Storybook.id`` carries the ``mqa_`` prefix (enforced by the manifest
    integrity tests in tests/unit/test_moderation_qa_corpus.py, not
    re-validated here) and is inserted at ``status="draft"`` with
    ``current_published_version=None``: this script never sets a status
    other than "draft" and never touches ``current_published_version``, so a
    freshly seeded book cannot be mistaken for a published one even before
    moderation runs.
    #VERIFY: test_seed_fixture_rows_skips_already_present_books;
    test_seed_fixture_rows_inserts_as_draft_with_no_published_version.

    Args:
        session: The active seed session.
        family: The Moderation QA family every row is scoped to.
        books: The manifest's book entries.

    Returns:
        The ids of books newly inserted this run (already-present ids are
        skipped and excluded).
    """
    inserted: list[str] = []
    for entry in books:
        book_id = str(entry["id"])
        existing = await session.get(Storybook, book_id)
        if existing is not None:
            continue
        blob = _load_blob(entry)
        session.add(
            Storybook(
                id=book_id,
                family_id=family.id,
                current_published_version=None,
                status="draft",
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=book_id,
                version=_FIRST_VERSION,
                blob=blob,
                moderation_report=None,
            )
        )
        inserted.append(book_id)
    if inserted:
        await session.flush()
    return inserted


async def _books_awaiting_moderation(
    session: AsyncSession, book_ids: list[str]
) -> list[str]:
    """Return the manifest books whose version-1 row has no report yet.

    This is what makes the seed genuinely retryable rather than a one-way
    door. Moderation is driven off persisted state (``moderation_report IS
    NULL``), not off "what this run inserted", so a book seeded earlier with
    ``--skip-moderation``, or one whose moderation raised and was rolled back
    by :func:`_moderate_new_books`, is picked up by the next run instead of
    being skipped forever by the already-present check in
    :func:`_seed_fixture_rows`.

    #ASSUME: data-integrity: a NULL ``moderation_report`` is the authoritative
    "not yet moderated" signal, because ``run_moderation_pipeline`` writes the
    report and drives submit/auto_reject inside the caller's transaction, and
    :func:`_moderate_new_books` rolls that whole unit back on failure.
    #VERIFY: test_books_awaiting_moderation_selects_only_unreported and
    test_seed_retries_a_previously_unmoderated_book in
    tests/unit/test_seed_moderation_qa.py.

    Args:
        session: The active seed session.
        book_ids: The manifest's book ids, in manifest order.

    Returns:
        The subset of ``book_ids`` still awaiting moderation, in manifest
        order.
    """
    if not book_ids:
        return []
    rows = (
        (
            await session.execute(
                select(StorybookVersion.storybook_id).where(
                    StorybookVersion.storybook_id.in_(book_ids),
                    StorybookVersion.version == _FIRST_VERSION,
                    StorybookVersion.moderation_report.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    pending = set(rows)
    return [book_id for book_id in book_ids if book_id in pending]


async def _moderate_new_books(session: AsyncSession, book_ids: list[str]) -> list[str]:
    """Run the real moderation pipeline over freshly seeded books.

    #CRITICAL: security: containment layer 4 of 4. This calls
    ``run_moderation_pipeline`` only, which per its own module contract may
    only drive ``submit`` (in_review) or ``auto_reject`` (needs_revision) --
    it never calls ``approve``/``publish``. This function calls nothing else
    that could publish a book.
    #VERIFY: test_moderate_new_books_never_calls_approve_or_publish.

    No real child is involved (the Moderation QA family has no
    ``ChildProfile``), so the PII guard runs with an empty forbidden-name set;
    it still screens the reviewer/repair prompts, just against nothing.

    Args:
        session: The active seed session.
        book_ids: Ids of the books to moderate (the set still awaiting
            moderation, per :func:`_books_awaiting_moderation`).

    Returns:
        The ids whose moderation run raised and was rolled back, in the order
        they were attempted. Empty when every book succeeded.
    """
    provider = build_provider(_default_settings)
    pii = PiiContext(child_names=frozenset())
    failures: list[str] = []
    for book_id in book_ids:
        try:
            # #CRITICAL: data-integrity: each book gets its own SAVEPOINT.
            # run_moderation_pipeline owns no transaction (it documents
            # "caller owns the transaction") and mutates session state before
            # it can raise: it overwrites version_row.blob on an adopted
            # repair and writes a repair_applied event, both BEFORE
            # moderation_report is persisted. Without this savepoint, a stage
            # that raises after an adopted repair would leave the seeded blob
            # silently different from the repo fixture that defines the
            # ground truth, with moderation_report still NULL, because seed()
            # commits unconditionally at the end. Rolling back to the
            # savepoint discards the partial run so the row still matches the
            # fixture and stays retryable.
            # #VERIFY: test_moderate_new_books_rolls_back_the_failed_book in
            # tests/unit/test_seed_moderation_qa.py.
            async with session.begin_nested():
                await run_moderation_pipeline(
                    session=session,
                    story_id=book_id,
                    version=_FIRST_VERSION,
                    settings=_default_settings,
                    generation_provider=provider,
                    pii=pii,
                )
        except Exception:
            # #ASSUME: external-resources: a single book's moderation run can
            # fail on a transient provider error without aborting the whole
            # batch. Its savepoint has been rolled back, so the row is
            # unchanged and still carries a NULL moderation_report; the next
            # run picks it up via _books_awaiting_moderation. The id is
            # returned so the caller can report it and exit nonzero.
            # #VERIFY: tests/unit/test_seed_moderation_qa.py has both
            # test_moderate_new_books_continues_after_one_failure and
            # test_moderate_new_books_returns_the_failed_ids.
            _logger.exception("seed_moderation_qa.moderate_failed", story_id=book_id)
            failures.append(book_id)
    return failures


async def seed(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
    moderate: bool = True,
) -> list[str]:
    """Idempotently seed the staging Moderation QA corpus.

    Refuses to run unless ``ENVIRONMENT=staging``. Resolves the dedicated
    Moderation QA family, inserts any manifest book not already present as a
    draft ``Storybook``/``StorybookVersion`` pair, and (unless ``moderate`` is
    False) runs the real moderation pipeline over every manifest book that
    still has a NULL ``moderation_report``, which is what makes a failed or
    ``--skip-moderation`` run retryable.

    Args:
        engine: Async engine to create the schema on. Defaults to the app's
            shared engine (``get_engine()``); tests inject a mock engine here.
        session_factory: Callable returning a new ``AsyncSession``. Defaults
            to a sessionmaker bound to ``engine``; tests inject a mocked
            session factory here so no real database connection is required.
        moderate: When True (default), run the real moderation pipeline over
            every book still awaiting moderation before committing. When
            False, only the draft rows are inserted (no LLM calls), for cheap
            re-seeding or inspection.

    Returns:
        The ids whose moderation run failed (and was rolled back). Empty when
        nothing failed.
    """
    _require_staging_or_exit()

    active_engine = engine if engine is not None else get_engine()
    async with active_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    new_session = (
        session_factory
        if session_factory is not None
        else async_sessionmaker(active_engine, expire_on_commit=False)
    )

    books = load_manifest()
    book_ids = [str(entry["id"]) for entry in books]
    failures: list[str] = []
    pending: list[str] = []
    async with new_session() as session:
        family = await _ensure_qa_family(session)
        inserted = await _seed_fixture_rows(session, family, books)
        if moderate:
            pending = await _books_awaiting_moderation(session, book_ids)
            failures = await _moderate_new_books(session, pending)
        await session.commit()

    print(
        f"Moderation QA corpus: {len(inserted)} book(s) newly seeded "
        f"({len(books)} in the manifest), family {family.id}, "
        f"moderation {'ran' if moderate else 'skipped'}"
        f" over {len(pending)} book(s), {len(failures)} failed."
    )
    if failures:
        print(
            "Moderation failed (rolled back, retry by re-running): "
            + ", ".join(failures)
        )
    return failures


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the seed script.

    Args:
        argv: Argument list, or None to use ``sys.argv``.

    Returns:
        The parsed namespace (``skip_moderation`` bool).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-moderation",
        action="store_true",
        help="Insert draft rows only; do not run the real moderation pipeline.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point for the moderation QA corpus seed script.

    Exits nonzero when any book's moderation run failed, so an operator does
    not read "N book(s) newly seeded" as success after six consecutive
    provider failures. A corpus that cannot be loaded at all exits with the
    ``ConfigurationError`` message (which names the offending path) rather
    than a raw traceback.
    """
    args = _parse_args()
    try:
        failures = asyncio.run(seed(moderate=not args.skip_moderation))
    except ConfigurationError as exc:
        sys.exit(f"seed_moderation_qa: {exc}")
    if failures:
        sys.exit(
            f"seed_moderation_qa: {len(failures)} book(s) failed moderation; "
            "their rows were rolled back and remain unmoderated."
        )


if __name__ == "__main__":
    main()
