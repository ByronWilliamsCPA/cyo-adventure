"""Wrap the hero's name in stored storybooks with personalization sentinels.

Usage::

    CYO_ADVENTURE_DATABASE_URL=... uv run python \\
        scripts/retrofit_personalization.py --all            # dry run
    CYO_ADVENTURE_DATABASE_URL=... uv run python \\
        scripts/retrofit_personalization.py --all --execute

ADR-023 shipped the personalization machinery and
``promote_personalizable_slots.py`` migrated the catalog's contracts, but a
book that was generated before either lands still stores flat prose: the
hero's name sits in the text as a bare word, so no client can resolve it to
a family's chosen name. ADR-023 section 6 names "replace as the default",
justified by there being no live child-linked production data; that premise
expires the moment kids start reading, and it has not expired yet.

This is the in-place alternative to regenerating: entirely deterministic,
with no LLM in the path. Reconstruct the bound skeleton the fill was
originally given, then run the same strip-then-reinsert transform
(``storybook/reinsertion.py``) that the live generation path runs
pre-persist, and store its document and manifest over the existing ones.

Four invariants gate every write, and any one of them failing stops that
book without touching the rest of the sweep:

1. The contract must declare at least one personalizable slot.
2. Every personalizable slot's pinned ``default_binding`` value must appear
   in the stored blob. This is the check that catches a re-themed book (see
   the ``#CRITICAL`` note on :func:`plan_retrofit`).
3. Stripping the sentinels back out must reproduce the stored text exactly,
   surface by surface. The transform is only allowed to add wrappers.
4. The deterministic validation gate must return the same finding multiset
   before and after, so a retrofit can never be the reason a book starts
   failing validation.

Dry run is the default and writes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.core.database import get_engine
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.generation.binding import load_contract_for, render_bound_skeleton
from cyo_adventure.storybook.reinsertion import (
    reinsert_storybook,
    strip_model_sentinels,
)
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from cyo_adventure.storybook.theme_contract import ThemeContract

_logger = get_logger(__name__)

_DEFAULT_SKELETON_ROOT = Path("skeletons")


class RetrofitSkippedError(Exception):
    """A book this sweep deliberately declines to touch.

    Distinct from :class:`~cyo_adventure.core.exceptions.ValidationError`,
    which this module raises only for a violated invariant (a defect). A
    skip is an expected outcome for a book the retrofit cannot serve, and it
    is reported, never silently dropped.
    """


@dataclass(frozen=True)
class RetrofitPlan:
    """What a retrofit would write for one storybook version.

    Attributes:
        document: The stored blob with every reinsertable hero mention
            wrapped in its canonical sentinel.
        manifest: The at-rest sentinel manifest derived from ``document``.
        tokens_expected: How many ``(node, token)`` pairs the reconstructed
            bound skeleton expected.
        tokens_reinserted: How many of those were deterministically
            reinserted. The remainder are nodes whose prose never names the
            hero, which is common: the corpus is largely second-person.
    """

    document: dict[str, object]
    manifest: dict[str, object]
    tokens_expected: int
    tokens_reinserted: int


@dataclass(frozen=True)
class BookOutcome:
    """One book's result within a sweep.

    Attributes:
        storybook_id: The book's id.
        version: The version number acted on.
        status: ``"retrofitted"``, ``"planned"`` (dry run), ``"skipped"``,
            or ``"failed"``.
        detail: A human-readable reason, or the coverage summary.
    """

    storybook_id: str
    version: int
    status: str
    detail: str


def resolve_skeleton_path(skeleton_root: Path, slug: str) -> Path:
    """Return the catalog skeleton a slug names.

    Resolves by glob rather than by a slug-to-band map, because the shared
    band resolver lives on a branch this one does not build on. A slug that
    matches zero or several files fails closed rather than guessing.

    Args:
        skeleton_root: The catalog root.
        slug: The version's ``skeleton_slug``.

    Returns:
        Path: The single matching skeleton file.

    Raises:
        RetrofitSkippedError: If the slug matches no skeleton.
        ValidationError: If the slug matches more than one skeleton, which
            would make the reconstructed binding ambiguous.
    """
    matches = sorted(skeleton_root.glob(f"*/{slug}.json"))
    if not matches:
        msg = f"no catalog skeleton named {slug!r}"
        raise RetrofitSkippedError(msg)
    if len(matches) > 1:
        msg = f"slug {slug!r} matches {len(matches)} skeletons: {matches}"
        raise ValidationError(msg)
    return matches[0]


def personalizable_slot_ids(contract: ThemeContract) -> frozenset[str]:
    """Return the ids of a contract's personalizable slots.

    Args:
        contract: The skeleton's theme contract.

    Returns:
        frozenset[str]: Possibly empty.
    """
    return frozenset(
        slot.id for slot in contract.slots if slot.kind == "personalizable"
    )


def document_surfaces(document: Mapping[str, object]) -> Iterator[tuple[str, str]]:
    """Yield every text surface of a storybook document as ``(path, text)``.

    Covers the same surfaces the reinsertion transform normalizes: the
    top-level title, each node body, each ending title, and each choice
    label. Used to prove the transform only added sentinel wrappers.

    Args:
        document: A storybook blob.

    Yields:
        tuple[str, str]: A stable path label and the text at it.
    """
    title = document.get("title")
    if isinstance(title, str):
        yield "title", title
    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        return
    for index, node in enumerate(cast("list[object]", nodes)):
        if not isinstance(node, dict):
            continue
        node_map = cast("dict[str, object]", node)
        node_id = node_map.get("id")
        label = node_id if isinstance(node_id, str) else f"#{index}"
        body = node_map.get("body")
        if isinstance(body, str):
            yield f"{label}.body", body
        ending = node_map.get("ending")
        if isinstance(ending, dict):
            ending_title = cast("dict[str, object]", ending).get("title")
            if isinstance(ending_title, str):
                yield f"{label}.ending.title", ending_title
        choices = node_map.get("choices")
        if not isinstance(choices, list):
            continue
        for position, choice in enumerate(cast("list[object]", choices)):
            if not isinstance(choice, dict):
                continue
            choice_label = cast("dict[str, object]", choice).get("label")
            if isinstance(choice_label, str):
                yield f"{label}.choices[{position}].label", choice_label


def _assert_only_wrappers_added(
    before: Mapping[str, object], after: Mapping[str, object]
) -> None:
    """Fail closed unless stripping ``after``'s sentinels reproduces ``before``.

    Args:
        before: The stored blob.
        after: The retrofitted document.

    Raises:
        ValidationError: On any surface whose text changed by more than the
            addition of sentinel wrappers, or if the surface sets differ.
    """
    original = dict(document_surfaces(before))
    retrofitted = dict(document_surfaces(after))
    if original.keys() != retrofitted.keys():
        missing = sorted(original.keys() ^ retrofitted.keys())
        msg = f"retrofit changed the document's surface set: {missing[:5]}"
        raise ValidationError(msg)
    for path, text in original.items():
        if strip_model_sentinels(retrofitted[path]) != text:
            msg = f"retrofit altered text at {path} beyond adding sentinels"
            raise ValidationError(msg)


def _assert_gate_neutral(
    before: Mapping[str, object], after: Mapping[str, object]
) -> None:
    """Fail closed unless the validation gate is indifferent to the retrofit.

    Args:
        before: The stored blob.
        after: The retrofitted document.

    Raises:
        ValidationError: If the finding multiset or the blocked verdict
            changed.
    """
    old = run_gate(before, context="fill_result")
    new = run_gate(after, context="fill_result")
    old_rules = Counter(finding.rule_id for finding in old.report.findings)
    new_rules = Counter(finding.rule_id for finding in new.report.findings)
    if old_rules != new_rules or old.blocked != new.blocked:
        delta = sorted((new_rules - old_rules) + (old_rules - new_rules))
        msg = (
            f"retrofit changed the validation gate: blocked "
            f"{old.blocked} -> {new.blocked}, findings delta {delta}"
        )
        raise ValidationError(msg)


def plan_retrofit(
    skeleton: dict[str, object],
    contract: ThemeContract,
    blob: Mapping[str, object],
) -> RetrofitPlan:
    """Compute, without writing, what this book's retrofit would produce.

    Deliberately DB-free so the whole transform is testable against a
    fixture pair.

    #CRITICAL: data-integrity: no column records the theme binding a stored
    book was actually generated with, so the contract's ``default_binding``
    is an assumption, not a fact. It is wrong for any book generated from a
    re-themed binding of the same skeleton, and three such books exist (the
    ``the-cave-of-echoes`` variants, whose heroes are Theo and Priya rather
    than the contract's pinned name). Reinserting the contract's value there
    would not corrupt the prose (it simply finds nothing), but it WOULD
    stamp ``personalization_eligible`` on a book whose hero is never
    actually parameterized, promising a personalization the reader never
    gets. Presence of the pinned value in the stored blob is therefore a
    precondition, not a diagnostic.
    #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_a_rethemed_book_is_skipped_not_silently_zero_covered

    Args:
        skeleton: The catalog skeleton, FILL directives intact.
        contract: That skeleton's theme contract.
        blob: The stored storybook document.

    Returns:
        RetrofitPlan: The document and manifest a write would persist.

    Raises:
        RetrofitSkippedError: If the contract declares no personalizable slot, or
            if a pinned binding value does not appear in the stored blob.
        ValidationError: If any post-transform invariant fails.
    """
    slot_ids = personalizable_slot_ids(contract)
    if not slot_ids:
        msg = f"contract {contract.skeleton_slug} declares no personalizable slot"
        raise RetrofitSkippedError(msg)

    stored_text = json.dumps(blob, ensure_ascii=False)
    for slot_id in sorted(slot_ids):
        value = contract.default_binding.get(slot_id, "")
        if not value or value not in stored_text:
            msg = (
                f"pinned {slot_id} value {value!r} does not appear in the "
                f"stored blob; this book was generated from a different "
                f"binding and its real one is unrecoverable"
            )
            raise RetrofitSkippedError(msg)

    bound = render_bound_skeleton(
        skeleton, contract.default_binding, personalizable_slots=slot_ids
    )
    outcome = reinsert_storybook(bound, blob)
    _assert_only_wrappers_added(blob, outcome.document)
    _assert_gate_neutral(blob, outcome.document)

    statuses = Counter(token.status for token in outcome.token_outcomes)
    return RetrofitPlan(
        document=outcome.document,
        manifest=outcome.manifest,
        tokens_expected=len(outcome.token_outcomes),
        tokens_reinserted=statuses["reinsertable"],
    )


async def _select_targets(
    session: AsyncSession, book_ids: list[str] | None
) -> list[StorybookVersion]:
    """Return the storybook versions this sweep will consider.

    Args:
        session: An open async session.
        book_ids: Explicit storybook ids, or ``None`` for every version that
            carries a ``skeleton_slug``.

    Returns:
        list[StorybookVersion]: Ordered by book id then version.
    """
    statement = select(StorybookVersion).where(
        StorybookVersion.skeleton_slug.is_not(None)
    )
    if book_ids:
        statement = statement.where(StorybookVersion.storybook_id.in_(book_ids))
    statement = statement.order_by(
        StorybookVersion.storybook_id, StorybookVersion.version
    )
    return list((await session.execute(statement)).scalars().all())


async def sweep(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
    skeleton_root: Path = _DEFAULT_SKELETON_ROOT,
    book_ids: list[str] | None = None,
    execute: bool = False,
) -> list[BookOutcome]:
    """Plan, and optionally apply, the retrofit across the selected books.

    Commits after each book, so one book's success is durable immediately
    and one book's failure is rolled back alone rather than aborting the
    sweep.

    Args:
        engine: Async engine to bind to; defaults to the app's shared engine.
        session_factory: Callable returning a new session; tests inject here.
        skeleton_root: The catalog root.
        book_ids: Explicit storybook ids, or ``None`` for every candidate.
        execute: When False (default), nothing is written.

    Returns:
        list[BookOutcome]: One entry per considered version.
    """
    factory = session_factory or async_sessionmaker(
        engine or get_engine(), expire_on_commit=False
    )
    outcomes: list[BookOutcome] = []
    async with factory() as session:
        for version in await _select_targets(session, book_ids):
            slug = version.skeleton_slug or ""
            try:
                skeleton_path = resolve_skeleton_path(skeleton_root, slug)
                skeleton = cast(
                    "dict[str, object]", json.loads(skeleton_path.read_text())
                )
                contract = load_contract_for(skeleton_path, skeleton)
                if contract is None:
                    msg = f"skeleton {slug} has no theme contract"
                    raise RetrofitSkippedError(msg)
                plan = plan_retrofit(skeleton, contract, version.blob)
            except RetrofitSkippedError as skipped:
                outcomes.append(
                    BookOutcome(
                        version.storybook_id, version.version, "skipped", str(skipped)
                    )
                )
                continue
            except ValidationError as failure:
                await session.rollback()
                outcomes.append(
                    BookOutcome(
                        version.storybook_id, version.version, "failed", str(failure)
                    )
                )
                continue

            detail = (
                f"{plan.tokens_reinserted}/{plan.tokens_expected} tokens reinserted"
            )
            if not execute:
                outcomes.append(
                    BookOutcome(
                        version.storybook_id, version.version, "planned", detail
                    )
                )
                continue

            version.blob = plan.document
            version.sentinel_manifest = plan.manifest
            version.personalization_eligible = True
            await session.commit()
            _logger.info(
                "retrofit_applied",
                storybook_id=version.storybook_id,
                version=version.version,
                tokens_reinserted=plan.tokens_reinserted,
                tokens_expected=plan.tokens_expected,
            )
            outcomes.append(
                BookOutcome(
                    version.storybook_id, version.version, "retrofitted", detail
                )
            )
    return outcomes


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument list, or None to use ``sys.argv``.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument(
        "--book-id",
        action="append",
        dest="book_id",
        metavar="STORYBOOK_ID",
        help="Retrofit this storybook id (repeatable).",
    )
    selector.add_argument(
        "--all",
        action="store_true",
        help="Consider every version that carries a skeleton_slug.",
    )
    parser.add_argument(
        "--skeleton-root",
        type=Path,
        default=_DEFAULT_SKELETON_ROOT,
        help="Catalog root to resolve skeleton slugs against.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write the retrofit. Without it, nothing is written.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Argument list, or None to use ``sys.argv``.

    Returns:
        int: ``1`` if any book failed an invariant, else ``0``. A skip is
            not a failure; a violated invariant is.
    """
    args = _parse_args(argv)
    outcomes = asyncio.run(
        sweep(
            skeleton_root=cast("Path", args.skeleton_root),
            book_ids=cast("list[str] | None", args.book_id),
            execute=bool(args.execute),
        )
    )
    if not outcomes:
        print("retrofit_personalization: no candidate versions found.")
        return 0

    tallies = Counter(outcome.status for outcome in outcomes)
    for outcome in outcomes:
        print(
            f"  {outcome.storybook_id} v{outcome.version} "
            f"{outcome.status}: {outcome.detail}"
        )
    print(
        "retrofit_personalization: "
        + ", ".join(f"{count} {status}" for status, count in sorted(tallies.items()))
    )
    if not args.execute:
        print("retrofit_personalization: dry run. Pass --execute to write.")
    return 1 if tallies["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
