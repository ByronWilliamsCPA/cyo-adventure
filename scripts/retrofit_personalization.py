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

Five invariants gate every write, and any one of them failing stops that
book without touching the rest of the sweep:

1. The contract must declare at least one personalizable slot.
2. Every personalizable slot's pinned ``default_binding`` value must appear
   in the stored blob. This is the check that catches a re-themed book (see
   the ``#CRITICAL`` note on :func:`plan_retrofit`).
3. Stripping the sentinels back out must reproduce the stored text exactly,
   surface by surface, AND every field outside those text surfaces must be
   unchanged. The transform is only allowed to add wrappers. Both sides of
   the text comparison are normalized through ``strip_model_sentinels``, so
   a book this sweep already retrofitted compares equal to itself and the
   sweep stays re-runnable. The non-text half carries no exemption: the
   reinsertion transform writes exactly four keys (``title``,
   ``node.body``, ``node.ending.title``, ``choice.label``) into a deep copy
   of the stored blob, so ``metadata``, the choice targets, ``variables``,
   ``start_node`` and everything else must come through byte-identical, and
   any difference there is a defect rather than an expected rewrite. The
   refreshed ``validation_report`` a run persists is a sibling COLUMN, not
   part of the blob, so it is outside this comparison by construction.
4. The produced manifest must actually describe the produced document
   (``verify_manifest``), since the two are persisted together and
   ``personalization_eligible`` is derived from the manifest alone.
5. The deterministic validation gate must not report a finding the stored
   blob did not already carry, and must not newly block, so a retrofit can
   never be the reason a book starts failing validation. That comparison is
   directional rather than an equality, deliberately: PN-1
   (``validator/naming.py``) exempts the protagonist by reading the ``HERO``
   sentinel, so installing that sentinel is precisely what retires PN-1's
   finding on the hero's own name, and installing it is this transform's
   entire purpose. Measured on ``the-backyard-treasure-map``, PN-1 reports
   ``Nina``, ``Pepper`` and ``Theo`` against the stored blob and ``Pepper``
   and ``Theo`` afterwards, where ``Nina`` is the contract's pinned ``HERO``
   binding. An equality check read that improvement as a failure and stopped
   the book. A removal cannot be prose loss wearing a weaker check, because
   invariant 3 has already proven the document identical modulo wrappers,
   surfaces and non-text fields alike. The permission stops at severity:
   retiring an ERROR-severity finding is refused outright, because nothing
   about installing a sentinel motivates one and PL-28, the ADR-011
   prototype-seed firewall, is an ERROR.

Dry run is the default and writes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import load_only

from cyo_adventure.core.database import get_engine
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.events.models import Actor, EventType
from cyo_adventure.events.writer import record_event
from cyo_adventure.generation.binding import (
    load_contract_for,
    personalizable_slot_ids,
    render_bound_skeleton,
)
from cyo_adventure.storybook.reinsertion import (
    manifest_carries_tokens,
    reinsert_storybook,
    strip_model_sentinels,
    verify_manifest,
)
from cyo_adventure.utils.logging import get_logger, setup_logging
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.report import Severity

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from cyo_adventure.storybook.theme_contract import ThemeContract

_logger = get_logger(__name__)

_DEFAULT_SKELETON_ROOT = Path("skeletons")

# Every value ``BookOutcome.status`` may take. A bare ``str`` type-checked a
# misspelled literal clean while ``main()``'s exit code reads
# ``tallies["failed"]``, so a typo silently turned a failed sweep into an
# exit 0. Spelled as a Literal alias for the same reason
# ``storybook/reinsertion.py`` spells ``_TokenStatus`` that way.
_BookStatus = Literal["retrofitted", "planned", "skipped", "unmatched", "failed"]

# Failures reading or decoding a catalog file. Distinct from the project's
# ``ValidationError`` (a ``ProjectBaseError``, NOT a ``ValueError``), so
# neither handler catches the other by accident.
_CATALOG_INPUT_ERRORS = (OSError, UnicodeError, json.JSONDecodeError)


class RetrofitSkippedError(Exception):
    """A book this sweep deliberately declines to touch.

    Distinct from :class:`~cyo_adventure.core.exceptions.ValidationError`,
    which this module raises only for a violated invariant (a defect). A
    skip is an expected outcome for a book the retrofit cannot serve, and it
    is reported, never silently dropped.
    """


class SkeletonNotFoundError(RetrofitSkippedError):
    """No catalog skeleton carries the slug a stored version names.

    Reported under its own ``"unmatched"`` status rather than folded into
    ``"skipped"``: a routine skip means the contract declares no
    personalizable slot, whereas this one means the database references a
    skeleton the catalog does not have, which is drift worth investigating.
    """


@dataclass(frozen=True, slots=True)
class RetrofitPlan:
    """What a retrofit would write for one storybook version.

    Attributes:
        document: The stored blob with every reinsertable hero mention
            wrapped in its canonical sentinel.
        manifest: The at-rest sentinel manifest derived from ``document``.
        validation_report: The refreshed deterministic gate report for
            ``document``, computed by :func:`_assert_gate_no_worse` and
            persisted alongside the blob rather than discarded.
        personalizable_slots: The contract's declared personalizable slot
            ids. Carried so the write path can ask the import path's exact
            two-clause eligibility question rather than a one-clause
            approximation of it.
        tokens_expected: How many ``(node, token)`` pairs the reconstructed
            bound skeleton expected.
        tokens_reinserted: How many of those were deterministically
            reinserted. The remainder are the transform's ``not_found``
            outcomes (nodes whose prose never names the hero, which is
            common: the corpus is largely second-person) plus its
            ``ambiguous`` ones (a value another slot also owns, which the
            transform refuses to wrap rather than guess at).
    """

    document: dict[str, object]
    manifest: dict[str, object]
    validation_report: dict[str, object]
    personalizable_slots: frozenset[str]
    tokens_expected: int
    tokens_reinserted: int


@dataclass(frozen=True, slots=True)
class BookOutcome:
    """One book's result within a sweep.

    Attributes:
        storybook_id: The book's id.
        version: The version number acted on.
        status: One of :data:`_BookStatus`. ``"unmatched"`` is the
            catalog-drift case broken out of ``"skipped"``; ``"failed"`` is
            the only status that changes the process exit code.
        detail: A human-readable reason, or the coverage summary.
    """

    storybook_id: str
    version: int
    status: _BookStatus
    detail: str


def resolve_skeleton_path(skeleton_root: Path, slug: str) -> Path:
    """Return the catalog skeleton a slug names.

    Resolves by glob rather than by a slug-to-band map, because the shared
    band resolver lives on a branch this one does not build on. A slug that
    matches zero or several files fails closed rather than guessing.

    #CRITICAL: security: ``slug`` is ``storybook_version.skeleton_slug``, a
    database column, and ``Path.glob`` honours literal ``..`` components, so
    a slug such as ``../../etc/passwd`` resolves outside the catalog root
    and would be read and parsed as a skeleton. Containment is therefore
    checked on the RESOLVED path, not assumed from the glob pattern.
    #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_resolve_skeleton_path_rejects_a_traversing_slug

    Args:
        skeleton_root: The catalog root.
        slug: The version's ``skeleton_slug``.

    Returns:
        Path: The single matching skeleton file, resolved and proven to lie
        under ``skeleton_root``.

    Raises:
        SkeletonNotFoundError: If the slug matches no skeleton.
        ValidationError: If the slug matches more than one skeleton, which
            would make the reconstructed binding ambiguous, or if the match
            resolves outside ``skeleton_root``.
    """
    matches = sorted(skeleton_root.glob(f"*/{slug}.json"))
    if not matches:
        msg = f"no catalog skeleton named {slug!r}"
        raise SkeletonNotFoundError(msg)
    if len(matches) > 1:
        msg = f"slug {slug!r} matches {len(matches)} skeletons: {matches}"
        raise ValidationError(msg)
    resolved = matches[0].resolve()
    root = skeleton_root.resolve()
    if not resolved.is_relative_to(root):
        msg = f"slug {slug!r} resolves outside the catalog root: {resolved}"
        raise ValidationError(msg)
    return resolved


def load_skeleton(skeleton_path: Path) -> dict[str, object]:
    """Read and decode one catalog skeleton, failing at the boundary.

    The shape check is what keeps a malformed catalog file from failing
    several frames deep inside ``generation/binding.py`` with an error that
    names neither the file nor the problem.

    Args:
        skeleton_path: A path already proven to lie under the catalog root.

    Returns:
        dict[str, object]: The decoded skeleton.

    Raises:
        ValidationError: If the file decodes to anything other than a JSON
            object.
    """
    decoded = cast("object", json.loads(skeleton_path.read_text(encoding="utf-8")))
    if not isinstance(decoded, dict):
        msg = (
            f"skeleton {skeleton_path} is a JSON "
            f"{type(decoded).__name__}, not an object"
        )
        raise ValidationError(msg)
    return cast("dict[str, object]", decoded)


# Written into every text surface by :func:`_non_surface_skeleton` before
# two documents are compared field by field. Any value would serve: it is
# written to both sides at the same positions, so it can never be the reason
# they differ. A NUL-delimited string is chosen only so a value that somehow
# escaped into a message reads as machinery rather than as prose.
_BLANKED_SURFACE = "\x00text-surface\x00"


def _text_surface_slots(
    document: dict[str, object],
) -> Iterator[tuple[str, dict[str, object], str]]:
    """Yield ``(path, container, key)`` for every text surface of a document.

    The single enumeration of what counts as a text surface. Both readers of
    that definition go through here, :func:`document_surfaces` to read the
    text and :func:`_non_surface_skeleton` to blank it, so the two can never
    drift into disagreeing about which four keys the transform is allowed to
    write.

    Args:
        document: A storybook blob.

    Yields:
        tuple[str, dict[str, object], str]: A stable path label, the dict
        holding the text, and the key it sits under. The value at
        ``container[key]`` is always a ``str``.
    """
    if isinstance(document.get("title"), str):
        yield "title", document, "title"
    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        return
    for index, node in enumerate(cast("list[object]", nodes)):
        if not isinstance(node, dict):
            continue
        node_map = cast("dict[str, object]", node)
        node_id = node_map.get("id")
        label = node_id if isinstance(node_id, str) else f"#{index}"
        if isinstance(node_map.get("body"), str):
            yield f"{label}.body", node_map, "body"
        ending = node_map.get("ending")
        if isinstance(ending, dict):
            ending_map = cast("dict[str, object]", ending)
            if isinstance(ending_map.get("title"), str):
                yield f"{label}.ending.title", ending_map, "title"
        choices = node_map.get("choices")
        if not isinstance(choices, list):
            continue
        for position, choice in enumerate(cast("list[object]", choices)):
            if not isinstance(choice, dict):
                continue
            choice_map = cast("dict[str, object]", choice)
            if isinstance(choice_map.get("label"), str):
                yield f"{label}.choices[{position}].label", choice_map, "label"


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
    for path, container, key in _text_surface_slots(dict(document)):
        yield path, cast("str", container[key])


def _non_surface_skeleton(document: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of ``document`` with every text surface blanked out.

    What is left is exactly the part of the blob the reinsertion transform
    has no business writing, in a form two documents can be compared on with
    a single ``==``. Blanking rather than deleting keeps the structure
    intact, so a node that lost its ``body`` key still reads as a
    difference.

    Args:
        document: A storybook blob.

    Returns:
        dict[str, object]: A deep copy whose four text surfaces all hold
        :data:`_BLANKED_SURFACE`.
    """
    frame = copy.deepcopy(dict(document))
    for _path, container, key in _text_surface_slots(frame):
        container[key] = _BLANKED_SURFACE
    return frame


def _assert_only_wrappers_added(
    before: Mapping[str, object], after: Mapping[str, object]
) -> None:
    """Fail closed unless the two documents strip to the same prose.

    #CRITICAL: data-integrity: BOTH sides are normalized through
    ``strip_model_sentinels``. Stripping only ``after`` made this guard
    asymmetric and the sweep single-use: on a re-run ``before`` is already
    the sentinel-wrapped blob this same tool wrote, so a byte-perfect
    transform compared "flat prose" against "wrapped prose" and raised.
    Normalizing both sides is what makes the migration idempotent, which an
    operator re-running a partially-completed sweep depends on.
    #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_a_second_retrofit_over_a_retrofitted_blob_plans_cleanly

    #CRITICAL: data-integrity: the text surfaces are 4 of the ~37 distinct
    field paths a stored blob carries, and the ones this guard does NOT
    compare are read by the validation gate: all of ``metadata`` (``tier``,
    ``age_band``, ``topology``, ``production_eligible``, ``content_flags``,
    ``reading_level``), the choice targets, ``variables``, ``start_node``.
    :func:`_assert_gate_no_worse` cites this guard as its reason for
    permitting a retired finding, so a guard that stopped at the prose would
    let a metadata drift retire a finding under a claim of byte-identity it
    had never checked. Every non-text field is therefore compared too, with
    no exemption: the transform deep-copies the blob and writes four keys,
    so a difference anywhere else is a defect, not an expected rewrite. The
    ``validation_report`` a run persists is a sibling column rather than a
    blob field, so it is out of scope here by construction.
    #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_a_metadata_change_outside_the_text_surfaces_is_rejected

    Args:
        before: The stored blob.
        after: The retrofitted document.

    Raises:
        ValidationError: On any surface whose text changed by more than the
            addition of sentinel wrappers, if the surface sets differ, or if
            any field outside the text surfaces changed at all.
    """
    original = dict(document_surfaces(before))
    retrofitted = dict(document_surfaces(after))
    if original.keys() != retrofitted.keys():
        missing = sorted(original.keys() ^ retrofitted.keys())
        msg = f"retrofit changed the document's surface set: {missing[:5]}"
        raise ValidationError(msg)
    for path, text in original.items():
        if strip_model_sentinels(retrofitted[path]) != strip_model_sentinels(text):
            msg = f"retrofit altered text at {path} beyond adding sentinels"
            raise ValidationError(msg)
    stored_frame = _non_surface_skeleton(before)
    retrofitted_frame = _non_surface_skeleton(after)
    if stored_frame != retrofitted_frame:
        changed = sorted(
            key
            for key in stored_frame.keys() | retrofitted_frame.keys()
            if stored_frame.get(key) != retrofitted_frame.get(key)
        )
        msg = f"retrofit changed fields outside the text surfaces: {changed[:5]}"
        raise ValidationError(msg)


def _assert_gate_no_worse(
    before: Mapping[str, object], after: Mapping[str, object]
) -> dict[str, object]:
    """Fail closed unless the retrofit leaves the gate no worse than it found it.

    #CRITICAL: data integrity: this comparison is DIRECTIONAL, and an
    equality here would be wrong rather than merely strict. A rule whose
    verdict reads the sentinel manifest instead of the prose alone is not
    invariant under a sentinel-installing transform, and PN-1
    (``validator/naming.py``) is the first such rule: its protagonist
    exemption keys on the ``HERO`` sentinel, chosen over any frequency
    heuristic because a share-based rule would have exempted the very defect
    PN-1 exists to catch (`AL-639`). Installing that sentinel is what this
    whole script does, so the retrofit RETIRES PN-1's finding on the hero's
    own name on every book whose prose named the hero flatly. Under an
    equality check that improvement stopped the book. Retaining the
    guarantee that matters, "a retrofit can never be the reason a book
    starts failing validation", means refusing an INTRODUCED finding and a
    newly blocked verdict while permitting a retired one. What makes the
    permission safe is not this function: ``_assert_only_wrappers_added``
    has already proven the whole document identical once sentinels are
    stripped, text surfaces and non-text fields alike, so a retired finding
    cannot be prose loss, or a metadata drift, in disguise.
    #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_a_finding_the_retrofit_retires_is_permitted proves the
    #   direction, and ::test_gate_guard_fails_closed_on_an_introduced_finding
    #   proves the refusal still fires.

    #CRITICAL: security: the permission stops at severity. Every finding
    this transform is known to retire is a WARNING (PN-1), and nothing
    about installing a sentinel motivates retiring an ERROR, so an ERROR
    that disappears is a signal the inputs differed rather than a signal
    the book improved. PL-28 makes the cost concrete: it is the ADR-011
    firewall that stops a prototype MVP/Test seed reaching a child's
    library, it is ERROR severity, and retiring it flips ``blocked`` True
    to False on a real catalog book (``the-lost-mitten``) while this
    function hands back a ``validation_report`` describing the unblocked
    state for the write path to persist. A rule id counts as an ERROR
    retirement when ANY of its stored findings was ERROR, because the
    multiset comparison cannot say which of a rule's findings went away;
    an ambiguous case is refused rather than permitted. The severity test
    is written against WARNING rather than for ERROR so that a severity
    this script has never seen fails closed.
    #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_an_error_severity_finding_the_retrofit_retires_is_rejected

    Args:
        before: The stored blob.
        after: The retrofitted document.

    Returns:
        dict[str, object]: The refreshed report for ``after``. Returned
        rather than discarded so the write path can persist a
        ``validation_report`` that describes the blob actually stored, which
        matters more now that the two reports may legitimately differ: the
        stored report must name the findings the STORED document carries,
        not the retired ones.

    Raises:
        ValidationError: If the gate reports a finding the stored blob did
            not carry, blocks a document that previously passed, or retires
            an ERROR-severity finding the stored blob carried.
    """
    old = run_gate(before, context="fill_result")
    new = run_gate(after, context="fill_result")
    old_rules = Counter(finding.rule_id for finding in old.report.findings)
    new_rules = Counter(finding.rule_id for finding in new.report.findings)
    introduced = new_rules - old_rules
    if introduced or (new.blocked and not old.blocked):
        msg = (
            f"retrofit worsened the validation gate: blocked "
            f"{old.blocked} -> {new.blocked}, findings introduced "
            f"{sorted(introduced.elements())}"
        )
        raise ValidationError(msg)
    retired = old_rules - new_rules
    retired_errors = sorted(
        {
            finding.rule_id
            for finding in old.report.findings
            if retired[finding.rule_id] and finding.severity != Severity.WARNING
        }
    )
    if retired_errors:
        msg = (
            f"retrofit retired error-severity findings {retired_errors}; a "
            f"retrofit may retire an advisory finding but never an error"
        )
        raise ValidationError(msg)
    return new.report.to_dict()


def plan_retrofit(
    skeleton: dict[str, object],
    contract: ThemeContract,
    blob: Mapping[str, object],
) -> RetrofitPlan:
    """Compute, without writing, what this book's retrofit would produce.

    Deliberately DB-free so the whole transform is testable against a
    fixture pair, and so no caller ever needs to roll a transaction back on
    account of it.

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

    #CRITICAL: data-integrity: the document and the manifest are persisted
    together and ``personalization_eligible`` is derived from the manifest
    ALONE, so a manifest that does not describe its own document would
    commit an inconsistent pair. ``generation/import_story.py`` runs the
    same ``verify_manifest`` check before persistence; this path now runs it
    too rather than trusting the transform.
    #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_a_manifest_that_does_not_describe_the_document_is_rejected

    Args:
        skeleton: The catalog skeleton, FILL directives intact.
        contract: That skeleton's theme contract.
        blob: The stored storybook document.

    Returns:
        RetrofitPlan: The document, manifest, and refreshed validation
        report a write would persist.

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
    if not verify_manifest(outcome.document, outcome.manifest):
        msg = (
            "reinsertion produced a document its own manifest cannot "
            "account for; refusing to persist the pair"
        )
        raise ValidationError(msg)
    validation_report = _assert_gate_no_worse(blob, outcome.document)

    statuses = Counter(token.status for token in outcome.token_outcomes)
    return RetrofitPlan(
        document=outcome.document,
        manifest=outcome.manifest,
        validation_report=validation_report,
        personalizable_slots=slot_ids,
        tokens_expected=len(outcome.token_outcomes),
        tokens_reinserted=statuses["reinsertable"],
    )


async def _select_targets(
    session: AsyncSession, book_ids: list[str] | None
) -> list[StorybookVersion]:
    """Return the storybook versions this sweep will consider.

    Loads only the columns the sweep reads or writes. The default entity
    load pulls ``blob``, ``validation_report`` and ``moderation_report``,
    three JSONB columns, for every matching row, and ``expire_on_commit=False``
    then holds all of them resident for the whole sweep; restricting the
    column set removes two of the three.

    Streaming (``stream_scalars`` / ``yield_per``) was considered and
    rejected: this sweep commits inside the loop, once per book, and a
    commit invalidates the server-side cursor a streaming result depends
    on. Keeping the per-book commit boundary (one book's success is durable
    immediately, one book's failure never aborts the rest) is worth more
    than the residual row-count headroom, so the result set stays fully
    materialized and the column list is what bounds its size.

    Args:
        session: An open async session.
        book_ids: Explicit storybook ids, or ``None`` for every version that
            carries a ``skeleton_slug``.

    Returns:
        list[StorybookVersion]: Ordered by book id then version.
    """
    statement = (
        select(StorybookVersion)
        .options(
            load_only(
                StorybookVersion.storybook_id,
                StorybookVersion.version,
                StorybookVersion.skeleton_slug,
                StorybookVersion.blob,
                StorybookVersion.sentinel_manifest,
                StorybookVersion.personalization_eligible,
            )
        )
        .where(StorybookVersion.skeleton_slug.is_not(None))
    )
    if book_ids:
        statement = statement.where(StorybookVersion.storybook_id.in_(book_ids))
    statement = statement.order_by(
        StorybookVersion.storybook_id, StorybookVersion.version
    )
    return list((await session.execute(statement)).scalars().all())


def _prepare(
    skeleton_root: Path, slug: str, blob: Mapping[str, object]
) -> RetrofitPlan:
    """Resolve one version's catalog inputs and plan its retrofit.

    Split out of :func:`sweep` so the per-book failure handling there reads
    as one try block over "everything that can go wrong for this book", with
    no database call inside it.

    Args:
        skeleton_root: The catalog root.
        slug: The version's ``skeleton_slug``.
        blob: The stored storybook document.

    Returns:
        RetrofitPlan: What a write would persist for this version.

    Raises:
        RetrofitSkippedError: If the slug names no skeleton, the skeleton
            has no theme contract, or the plan declines the book.
        ValidationError: If a catalog file is malformed or an invariant
            fails.
    """
    skeleton_path = resolve_skeleton_path(skeleton_root, slug)
    skeleton = load_skeleton(skeleton_path)
    contract = load_contract_for(skeleton_path, skeleton)
    if contract is None:
        msg = f"skeleton {slug} has no theme contract"
        raise RetrofitSkippedError(msg)
    return plan_retrofit(skeleton, contract, blob)


async def _persist(
    session: AsyncSession, version: StorybookVersion, plan: RetrofitPlan
) -> None:
    """Write one book's retrofit and its audit event in a single transaction.

    Args:
        session: The sweep's open session.
        version: The row being rewritten.
        plan: What to write.
    """
    version.blob = plan.document
    version.sentinel_manifest = plan.manifest
    version.validation_report = plan.validation_report
    # #CRITICAL: data-integrity: the reader trusts this column
    # verbatim and prompts the child for a name whenever it is True
    # (frontend/src/reader/ReaderRoute.tsx returns null only on an
    # explicit False). Coverage is bimodal across this catalog: a
    # second-person book such as `the-drowned-court` names its hero
    # nowhere, so the transform reinserts 0 of 289 expected tokens and
    # `build_manifest` still returns a mapping, just an empty one.
    # Stamping True there asks a child for a name that no page will
    # ever show. This is now LITERALLY the expression
    # `generation/import_story.py` evaluates, both clauses included, rather
    # than a one-clause form that only agreed with it because
    # `plan_retrofit` raises earlier on an empty slot set; a divergent rule
    # is worse than the bug.
    # #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_a_zero_coverage_book_is_not_stamped_eligible
    version.personalization_eligible = bool(
        plan.personalizable_slots
    ) and manifest_carries_tokens(plan.manifest)
    # #CRITICAL: data-integrity: `db/models.py` documents a storybook
    # version as immutable and this sweep rewrites one in place, so without
    # an append-only record the mutation is invisible to
    # `api/audit.py`. REPAIR_APPLIED is the existing taxonomy member for a
    # system-driven in-place blob rewrite of a stored version
    # (moderation/pipeline.py writes it with stage="moderation"); no new
    # event type is invented for one migration. Added to the SAME session
    # and flushed before the commit below, so the event and the mutation
    # are atomic.
    # #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_a_retrofit_records_an_append_only_event
    await record_event(
        session,
        Actor.system(),
        entity_type="storybook_version",
        entity_id=f"{version.storybook_id}:{version.version}",
        event_type=EventType.REPAIR_APPLIED,
        payload={"stage": "personalization_retrofit"},
    )
    await session.commit()


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
    and one book's failure is recorded alone rather than aborting the sweep.

    #CRITICAL: data-integrity: nothing in the per-book failure path may
    touch the session. The planning half is DB-free, so a failure there has
    nothing to roll back, and `AsyncSession.rollback()` expires every loaded
    row: the next iteration's attribute read would then issue a lazy refresh
    outside a greenlet context, raising `MissingGreenlet` out of
    `asyncio.run` with no summary printed. `expire_on_commit=False` below is
    set for the same reason.
    #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_a_failed_book_does_not_abort_the_rest_of_the_sweep

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
            book_id = version.storybook_id
            number = version.version
            try:
                plan = _prepare(skeleton_root, slug, version.blob)
            except SkeletonNotFoundError as unmatched:
                outcomes.append(
                    BookOutcome(book_id, number, "unmatched", str(unmatched))
                )
                continue
            except RetrofitSkippedError as skipped:
                outcomes.append(BookOutcome(book_id, number, "skipped", str(skipped)))
                continue
            except ValidationError as failure:
                outcomes.append(BookOutcome(book_id, number, "failed", str(failure)))
                continue
            except _CATALOG_INPUT_ERRORS as unreadable:
                # A single unreadable or undecodable catalog file must not
                # end the sweep; the module's contract is per-book
                # isolation. Deliberately narrow: no database exception is
                # caught here, so a real DB fault still aborts loudly.
                outcomes.append(
                    BookOutcome(
                        book_id,
                        number,
                        "failed",
                        f"could not read catalog input: {unreadable}",
                    )
                )
                continue

            eligible = bool(plan.personalizable_slots) and manifest_carries_tokens(
                plan.manifest
            )
            detail = (
                f"{plan.tokens_reinserted}/{plan.tokens_expected} tokens "
                f"reinserted, eligible={eligible}"
            )
            if not execute:
                outcomes.append(BookOutcome(book_id, number, "planned", detail))
                continue

            await _persist(session, version, plan)
            _logger.info(
                "retrofit_applied",
                storybook_id=book_id,
                version=number,
                tokens_reinserted=plan.tokens_reinserted,
                tokens_expected=plan.tokens_expected,
                personalization_eligible=eligible,
            )
            outcomes.append(BookOutcome(book_id, number, "retrofitted", detail))
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

    #CRITICAL: security: ``setup_logging`` is what installs
    ``censor_sensitive_processor``; a module-level ``get_logger`` alone runs
    under structlog's unconfigured default chain, so the redaction backstop
    would be inert for every line this sweep emits. Matches
    ``scripts/backfill_covers_r2.py::main``.
    #VERIFY: tests/unit/test_retrofit_personalization.py::
    #   test_main_configures_logging_before_sweeping

    Args:
        argv: Argument list, or None to use ``sys.argv``.

    Returns:
        int: ``1`` if any book failed an invariant, else ``0``. A skip and
            an unmatched slug are not failures; a violated invariant is.
    """
    setup_logging(level="INFO", json_logs=False, include_correlation=False)
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
    unmatched = tallies["unmatched"]
    if unmatched:
        drift = f"{unmatched} version(s) name a skeleton slug the catalog lacks"
        print(f"retrofit_personalization: {drift}; investigate catalog/DB drift.")
    if not args.execute:
        print("retrofit_personalization: dry run. Pass --execute to write.")
    return 1 if tallies["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
