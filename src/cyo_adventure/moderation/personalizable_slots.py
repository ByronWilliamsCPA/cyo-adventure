"""Resolve a story's declared personalizable-slot contract (Task 6a/6c).

This module is the single, public home for the personalizable-slot tri-state
contract shared across package boundaries: the moderation pipeline
(:mod:`cyo_adventure.moderation.pipeline`), the cyo-author resume path
(:mod:`cyo_adventure.generation.import_story`), and the admin node editor
(:mod:`cyo_adventure.api.node_edit`) all resolve the SAME answer from the same
provenance chain. It was extracted from ``moderation/pipeline.py`` so those
cross-package consumers import a public name from a dedicated module rather
than reaching into a sibling module's private (underscore-prefixed) surface.

The tri-state answer (see :func:`personalizable_slot_ids_for_job`):

- a real ``frozenset[str]`` of declared personalizable slot ids,
- an EMPTY ``frozenset`` when no personalizable slot could legitimately exist,
- :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE` when a contract may exist but
  cannot be recovered (fail closed). This was spelled ``None`` until the
  falsy-collapse hazard described on
  :class:`PersonalizableSlotsUnrecoverable` retired it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NoReturn

from sqlalchemy import select

from cyo_adventure.core.exceptions import ValidationError as CoreValidationError
from cyo_adventure.db.models import GenerationJob
from cyo_adventure.generation.authoring_metadata import (
    SKELETON_BAND_KEY,
    SKELETON_SLUG_KEY,
)
from cyo_adventure.generation.binding import (
    load_contract_for,
    personalizable_slot_fields,
    personalizable_slot_ids,
)
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.generation.skeleton_match import (
    find_skeleton_band,
    resolve_skeleton_path,
)
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.db.models import StorybookVersion
    from cyo_adventure.storybook.theme_contract import ThemeContract

_logger = get_logger(__name__)


class PersonalizableSlotsUnset:
    """Marker type for :data:`PERSONALIZABLE_SLOTS_UNSET` (Task 6c).

    "The caller passed nothing" is a distinct state from every arm of the
    personalizable-slot tri-state (see
    :func:`personalizable_slot_ids_for_job`'s docstring), so it needs its own
    value in :data:`PersonalizableSlotsArg`, the override parameter shared by
    :func:`~cyo_adventure.moderation.pipeline.run_moderation_pipeline` and
    :func:`~cyo_adventure.generation.import_story.import_filled_story`. A
    caller that legitimately resolved
    :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE` (personalization possible, the
    contract uncomputable) must be able to thread that exact value through
    and have it still fail closed, never have it reinterpreted as "resolve it
    yourself, the caller forgot".

    A dedicated sentinel TYPE (not a shared ``object()``) lets ``isinstance``
    narrow the parameter cleanly under BasedPyright strict mode.
    """

    __slots__ = ()


PERSONALIZABLE_SLOTS_UNSET: Final = PersonalizableSlotsUnset()
"""Default marker meaning "the caller did not supply personalizable_slots".

When :func:`~cyo_adventure.moderation.pipeline.run_moderation_pipeline`
receives this exact sentinel (its parameter's default), it resolves the slot
set itself via :func:`personalizable_slot_ids_for_story`, exactly as it always
has. Any other value passed for the parameter -- a real ``frozenset[str]`` OR
an explicit :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE` -- is used VERBATIM
instead (Task 6c: threads the resume path's own, correctly-timed and
correctly-banded, resolution).
"""


class PersonalizableSlotsUnrecoverable:
    """Marker type for :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE`.

    The fail-closed arm of the personalizable-slot tri-state (see
    :func:`personalizable_slot_ids_for_job`), which used to be spelled
    ``None``. ``None`` carried the meaning correctly but not safely: it is
    FALSY, and so is the benign empty ``frozenset`` that means "no
    personalizable slot could legitimately exist". Those two states are
    opposites, and a single ``if not slots:`` collapses the fail-closed one
    into the benign one with nothing left to notice.

    Strict-mode typing already caught the OTHER way to mishandle this arm:
    passing ``frozenset[str] | None`` where a plain ``frozenset[str]`` was
    wanted has always been an error, so "a caller forgot to handle it" was
    caught at every typed boundary. A truthiness test was the one shape that
    type-checked perfectly under the ``None`` spelling and still routed a
    security control the wrong way. That is the hole this type closes, with
    two defences of UNEQUAL reach. Because :meth:`__bool__` returns
    :data:`~typing.NoReturn`, BasedPyright rejects the shapes that take a
    conditional operand directly -- ``if slots``, ``if not slots``, ``while
    slots``, ``assert slots``, a ternary condition, and a comprehension
    ``if`` -- with "Invalid conditional operand of type PersonalizableSlots",
    so those fail the type gate rather than shipping. Other truthiness
    shapes ESCAPE the type gate and type-check clean: ``bool(slots)``,
    ``slots or x``, ``slots and x``, and ``any([slots])`` are caught only by
    the runtime ``TypeError`` :meth:`__bool__` raises. That matters because
    :mod:`cyo_adventure.generation.persistence` prescribes exactly the
    ``bool(...) and ...`` shape as the house recipe, so treat the runtime
    raise, not the type gate, as the backstop there. Narrowing to the
    ``frozenset`` arm first both type-checks and runs, which is precisely
    the reading that stays legitimate.

    Deliberately NOT falsy-by-omission and NOT truthy either. Either choice
    would silently pick one of the two readings below for a caller who never
    stated which one they meant.
    """

    __slots__ = ()

    def __bool__(self) -> NoReturn:
        """Refuse to collapse an unrecoverable contract into a boolean.

        Raises:
            TypeError: Always. The message names both readings a truthiness
                test could have intended, because the author meant exactly
                one of them and the traceback points at the line to fix.
        """
        msg = (
            "the personalizable-slot contract could not be recovered, so its "
            "truth value is ambiguous: use isinstance(slots, "
            "PersonalizableSlotsUnrecoverable) to fail closed, or narrow to "
            "the frozenset arm first if you meant 'no slots are declared'"
        )
        raise TypeError(msg)

    def __repr__(self) -> str:
        """Return the module-level constant's name rather than a default repr.

        Returns:
            str: The dotted-free constant name, so a log line or a failed
                assertion names the state instead of printing an object id.
        """
        return "PERSONALIZABLE_SLOTS_UNRECOVERABLE"


PERSONALIZABLE_SLOTS_UNRECOVERABLE: Final = PersonalizableSlotsUnrecoverable()
"""A contract may exist for this story, and it could not be recovered.

Returned by every ``personalizable_slot_ids_for_*`` resolver in place of the
``None`` they used to return. A caller holding this value must refuse to treat
the story's sentinels as provably safe. It must NOT substitute an empty
frozenset, which asserts the opposite: that no personalizable slot could
legitimately exist, and therefore that every sentinel in the blob is forged.
"""

PersonalizableSlots = frozenset[str] | PersonalizableSlotsUnrecoverable
"""The personalizable-slot tri-state every resolver returns.

Three states across two union members: a populated ``frozenset[str]`` (these
slot ids are declared), an EMPTY ``frozenset`` (no personalizable slot could
legitimately exist), and :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE` (fail
closed). Only the third is the marker; the first two are both the frozenset
arm, which is why narrowing with ``isinstance`` rather than truthiness is the
only way to tell the fail-closed state from the benign empty one.
"""

PersonalizableSlotsArg = PersonalizableSlots | PersonalizableSlotsUnset
"""Type of the ``personalizable_slots`` override parameter.

Shared by
:func:`~cyo_adventure.moderation.pipeline.run_moderation_pipeline` and
:func:`~cyo_adventure.generation.import_story.import_filled_story`, which
forwards its own same-named parameter through unchanged.
"""


async def personalizable_slot_ids_for_story(
    session: AsyncSession, story_id: str
) -> PersonalizableSlots:
    """Resolve a story's declared personalizable slot ids for the repair re-check.

    ``StorybookVersion`` carries ``skeleton_slug`` but no band, so the story's
    matched skeleton is recovered via its ``GenerationJob`` row, mirroring the
    same provenance chain :func:`~cyo_adventure.generation.worker._run_skeleton_fill`
    and :mod:`cyo_adventure.generation.import_story` already use.
    ``GenerationJob.storybook_id`` is not a FK (see that model's docstring);
    this uses the same degrade-on-missing pattern already established by
    :mod:`cyo_adventure.story_requests.anchoring` and
    :mod:`cyo_adventure.covers.service` (oldest job first, ``None`` on no match).

    The SELECT is the only part of this resolution that is unique to "find
    the job from the story id"; everything after it (Task 6c) is extracted
    into :func:`personalizable_slot_ids_for_job`, a reusable helper for a
    caller that already holds the ``GenerationJob`` row (and, on the
    cyo-author resume path, a better-resolved band than the raw
    ``authoring_metadata`` key) -- see that function's own docstring for the
    full tri-state contract this function inherits unchanged.

    Args:
        session: The pipeline's own open async session.
        story_id: The persisted storybook id under moderation.

    Returns:
        PersonalizableSlots: see :func:`personalizable_slot_ids_for_job` for
            the two cases that function decides. This function adds a third
            that the delegated contract does not cover: NO matching
            ``GenerationJob`` row at all, which returns an EMPTY frozenset.
            See the comment on that branch for why empty and not the
            fail-closed marker.
    """
    job = (
        await session.execute(
            select(GenerationJob)
            .where(GenerationJob.storybook_id == story_id)
            .order_by(GenerationJob.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        # #ASSUME: data-integrity: no job row means no reachable skeleton and
        # therefore no theme contract, so no personalizable slot can
        # legitimately exist: an empty frozenset, not
        # PERSONALIZABLE_SLOTS_UNRECOVERABLE. Failing closed would be the more
        # paranoid answer, but it is the WRONG one
        # here. Stories reach the catalog without a `GenerationJob` (seeded
        # and directly-imported ones do), and failing closed for them would
        # make the at-rest scan newly treat every brace-bearing legacy story
        # as sentinel-corrupt, which is a behaviour change well outside this
        # slot contract's remit.
        # #VERIFY: the anomaly is still worth a signal, because the moderation
        # pipeline reaches this function FROM a job: a missing row on that
        # path means the row was deleted mid-pipeline, not that the story is
        # legacy. Logged rather than swallowed so that case is visible; the
        # empty set is returned either way.
        _logger.warning(
            "moderation.personalizable_slots_no_job_row",
            story_id=story_id,
        )
        return frozenset()
    return personalizable_slot_ids_for_job(job)


class _ContractForJobError(Exception):
    """Base for :func:`_contract_for_job` failures, carrying provenance.

    A structured error rather than a bare ``str(exc)`` payload: every caller
    logs a degrade-path warning, and the log line is only actionable when it
    names WHICH skeleton could not be resolved and at WHICH band, so both
    travel as attributes instead of being smuggled through the message.

    Attributes:
        slug: The job's ``skeleton_slug``.
        band: The resolved band the failure occurred at, or ``None`` when no
            band was resolvable at all (`_NoResolvableBandError`).
    """

    def __init__(self, slug: str, band: str | None, detail: str) -> None:
        super().__init__(detail)
        self.slug = slug
        self.band = band


class _NoResolvableBandError(_ContractForJobError):
    """Raised by :func:`_contract_for_job` when no skeleton band is available.

    ``band`` is always ``None`` on this subclass. Kept distinct from
    `_ContractLoadError` so :func:`personalizable_slot_ids_for_job` preserves
    its own, more specific ``moderation.repair_contract_band_missing`` log
    event, while :func:`personalizable_slot_fields_for_story`, which only
    wants "no contract, no matter why", folds both subclasses into a single
    catch of the shared `_ContractForJobError` base.
    """


class _ContractLoadError(_ContractForJobError):
    """Raised by :func:`_contract_for_job` when the skeleton/contract load fails.

    Wraps the raw ``load_skeleton``/``load_contract_for`` exception (chained
    as ``__cause__``) so the slug and resolved band survive to the caller's
    log line instead of being lost in the loader's own message.
    """


def _contract_for_job(
    job: GenerationJob, *, band: str | None = None
) -> ThemeContract | None:
    """Resolve a ``GenerationJob``'s theme contract from disk.

    Extracted from :func:`personalizable_slot_ids_for_job` (ADR-023 Stage C,
    Task C0c) so :func:`personalizable_slot_fields_for_story` shares the
    IDENTICAL slug/band derivation and ``resolve_skeleton_path`` plus
    ``load_skeleton`` plus ``load_contract_for`` sequence, rather than
    re-deriving it, so both functions provably resolve the same contract for
    the same job.

    Args:
        job: The already-resolved ``GenerationJob``.
        band: Explicit band override; see
            :func:`personalizable_slot_ids_for_job` for the full contract.

    Returns:
        ThemeContract | None: ``None`` when the job carries no
        ``skeleton_slug`` (no contract could legitimately exist), or when
        :func:`~cyo_adventure.generation.binding.load_contract_for` itself
        returns ``None`` (a legacy skeleton with no contract sidecar).

    Raises:
        _NoResolvableBandError: No band is available from either ``band`` or
            the job's ``authoring_metadata`` (its ``band`` attribute is
            ``None``).
        _ContractLoadError: The skeleton path a stale ``authoring_metadata``
            points at has moved, been corrupted, or fails contract
            validation; carries the slug and resolved band, with the raw
            loader exception chained as ``__cause__``.
    """
    authoring = (
        job.authoring_metadata if isinstance(job.authoring_metadata, dict) else {}
    )
    slug = authoring.get(SKELETON_SLUG_KEY)
    if not isinstance(slug, str):
        return None
    resolved_band = band if band is not None else authoring.get(SKELETON_BAND_KEY)
    if not isinstance(resolved_band, str):
        no_band_msg = f"no resolvable skeleton band for slug '{slug}'"
        raise _NoResolvableBandError(slug, None, no_band_msg)
    # #CRITICAL: external-resources: load_skeleton (generation/skeleton.py)
    # does json.loads(path.read_text(...)), which raises a raw
    # FileNotFoundError/OSError/JSONDecodeError (a ValueError subclass), NOT
    # a CoreValidationError, when the skeleton file a stale
    # GenerationJob.authoring_metadata points at has since moved or been
    # corrupted. Wrapped here (mirroring generation/import_story.py::
    # _load_resume_skeleton's handling of this same resolve_skeleton_path ->
    # load_skeleton chain) so every caller fails closed with the slug and
    # band on its log line instead of crashing its whole pass.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_repair_contract_file_missing_is_discarded_and_routes_to_human_review
    # and tests/unit/test_personalizable_slots.py::
    # test_slot_fields_for_story_degrades_to_empty_when_the_skeleton_is_missing.
    try:
        skeleton_path = resolve_skeleton_path(resolved_band, slug)
        skeleton = load_skeleton(skeleton_path)
        return load_contract_for(skeleton_path, skeleton)
    except (FileNotFoundError, OSError, ValueError, CoreValidationError) as exc:
        raise _ContractLoadError(slug, resolved_band, str(exc)) from exc


def personalizable_slot_ids_for_job(
    job: GenerationJob, *, band: str | None = None
) -> PersonalizableSlots:
    """Resolve a ``GenerationJob``'s declared personalizable slot ids.

    Extracted from :func:`personalizable_slot_ids_for_story` (Task 6c) so a
    caller that already holds the job row can resolve the SAME tri-state
    answer that function would produce for that job, without a second
    ``GenerationJob`` SELECT. This is a plain synchronous function (no
    ``await``): every step below (skeleton/contract loading) is file I/O,
    not database I/O, so a caller like ``generation/import_story.py::
    resume_manual_fill`` can call it directly on its in-memory job, before
    that job is ever linked to a persisted story id.

    Args:
        job: The already-resolved ``GenerationJob`` (its ``authoring_metadata``
            is the source of ``skeleton_slug`` and, absent ``band``, the
            stored ``skeleton_band``).
        band: Explicit band override. When provided (not ``None``), used
            INSTEAD OF reading ``job.authoring_metadata[SKELETON_BAND_KEY]``.
            A caller that has already resolved the CORRECT band through its
            own richer logic -- e.g. ``generation/import_story.py::
            _resolve_resume_band``, which falls back to the request's brief
            band when the job predates that authoring_metadata key -- should
            pass that resolution here (Task 6c's I2 fix) rather than let
            this function re-derive a possibly-``None`` band from the raw
            metadata key alone. ``None`` (the default) means "no override;
            read the raw metadata key", matching this function's own
            historical behavior and every non-resume caller (which has no
            better band to offer). Note ``""`` (no band directory) IS a
            legitimate override value, distinct from ``None``; a caller that
            resolved an override always passes a ``str``, never ``None``.

    Returns:
        PersonalizableSlots: The declared personalizable slot ids. An EMPTY
            frozenset is returned (not a guess) whenever no personalizable
            slot could legitimately exist for this job: no ``skeleton_slug``
            (a ``fresh_generation`` job), or a legacy skeleton with no
            theme-contract sidecar
            (:func:`~cyo_adventure.generation.binding.load_contract_for`
            returns ``None``). :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE` is
            returned only when the job DOES carry a ``skeleton_slug`` (so a
            contract may genuinely declare personalizable slots) but the
            contract cannot be recovered (no band available from either
            source, or the skeleton/contract sidecar failing to load): the
            caller must fail closed rather than risk treating a real sentinel
            as forged with a guessed empty set.
    """
    try:
        contract = _contract_for_job(job, band=band)
    except _NoResolvableBandError as exc:
        _logger.warning(
            "moderation.repair_contract_band_missing",
            job_id=str(job.id),
            story_id=job.storybook_id,
            slug=exc.slug,
        )
        return PERSONALIZABLE_SLOTS_UNRECOVERABLE
    except _ContractLoadError as exc:
        # The load failure itself is caught and wrapped inside
        # `_contract_for_job` (see its #CRITICAL note); this arm only turns
        # the structured error into the fail-closed marker plus a log line
        # that names the slug and band, not just the loader's message.
        _logger.warning(
            "moderation.repair_contract_load_failed",
            job_id=str(job.id),
            story_id=job.storybook_id,
            slug=exc.slug,
            band=exc.band,
            error=str(exc)[:500],
        )
        return PERSONALIZABLE_SLOTS_UNRECOVERABLE
    if contract is None:
        return frozenset()
    return personalizable_slot_ids(contract)


async def personalizable_slot_fields_for_story(
    session: AsyncSession, story_id: str
) -> dict[str, str]:
    """Resolve a story's slot-id to personalization-field map for the values payload.

    The ring-1 and ring-2 values payloads are keyed by slot TYPE while prose
    sentinels are keyed by slot ID, and only the theme contract joins them
    (see :func:`cyo_adventure.generation.binding.personalizable_slot_fields`).
    The reader cannot read a contract sidecar, so the values route ships the map.

    Reuses the identical provenance chain as
    :func:`personalizable_slot_ids_for_story`: the story's oldest
    ``GenerationJob`` row, then that job's matched skeleton, then that
    skeleton's contract (:func:`_contract_for_job`, shared with
    :func:`personalizable_slot_ids_for_job`).

    Args:
        session: The request session.
        story_id: The storybook id whose contract map is wanted.

    Returns:
        dict[str, str]: slot id -> personalization field. EMPTY in all three
        degrade cases, unlike the tri-state ``_ids_`` functions: no job row, an
        unrecoverable contract, and a contract with no personalizable slots all
        return ``{}``. Empty is correct for every one of them here, because this
        map is only ever used to LOOK UP a value for a sentinel the blob already
        contains; a missing entry makes the resolver fall back to the sentinel's
        own generic word, which is exactly the fail-safe outcome. There is no
        decision this function could fail closed on.
    """
    job = (
        await session.execute(
            select(GenerationJob)
            .where(GenerationJob.storybook_id == story_id)
            .order_by(GenerationJob.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        return {}
    # #EDGE: performance: `_contract_for_job` reads two JSON files from disk
    # (``resolve_skeleton_path`` then ``load_contract_for``) synchronously,
    # inside a request path, on the reader's book-open call. The cost is
    # bounded: one call per book OPEN (never per node render), and the values
    # route calls this only on its fully-authorized happy path, after every
    # reachability/subject/values predicate has passed (api/personalization.py,
    # `_resolve_ring1_view`/`_resolve_ring2_view`). It also matches the
    # existing precedent in `personalizable_slot_ids_for_job`, which the
    # moderation pipeline calls the same way from async code.
    # #VERIFY: no behavioural test asserts the timing; if profiling ever shows
    # it matters, the exit is persisting this map on ``storybook_version``
    # beside ``sentinel_manifest`` at re-insertion time, not caching it here.
    # #ASSUME: external-resources: every `_contract_for_job` failure, band or
    # load, degrades to {} here (fail-safe, not fail-closed; see Returns), and
    # the warning below carries the slug and band so the degrade is traceable.
    # #VERIFY: tests/unit/test_personalizable_slots.py::
    # test_slot_fields_for_story_degrades_to_empty_when_the_skeleton_is_missing.
    try:
        contract = _contract_for_job(job)
    except _ContractForJobError as exc:
        _logger.warning(
            "personalization.slot_fields_contract_unresolved",
            storybook_id=story_id,
            slug=exc.slug,
            band=exc.band,
            error=str(exc)[:500],
        )
        return {}
    if contract is None:
        return {}
    return personalizable_slot_fields(contract)


def _band_for_version(version_row: StorybookVersion, slug: str) -> str | None:
    """Recover the band directory a version's skeleton slug lives under.

    Args:
        version_row: The version being resolved, for log attribution.
        slug: The version's ``skeleton_slug``.

    Returns:
        The band directory name, or None if the slug does not resolve to
        exactly one readable band. Every None is fail-closed: the caller must
        not substitute an empty contract for one it could not read.
    """
    try:
        band = find_skeleton_band(slug)
    except CoreValidationError:
        # A traversing or ambiguous slug. Fail closed rather than pick a band:
        # the version claims provenance that cannot be resolved to one file.
        # #VERIFY: tests/unit/test_personalizable_slots.py::
        # test_version_with_a_traversing_slug_fails_closed.
        _logger.warning(
            "moderation.version_contract_slug_unresolvable",
            story_id=version_row.storybook_id,
            slug=slug,
        )
        return None
    except OSError as exc:
        # #CRITICAL: external-resources: find_skeleton_band SCANS the catalog
        # (skeleton_match.py::_locate_skeleton walks _SKELETON_ROOT.iterdir()),
        # so an unreadable or hung skeleton root raises a raw OSError here, NOT
        # a CoreValidationError. Uncaught it escapes the caller entirely and
        # takes down the whole re-moderation request, while the contract load
        # already catches OSError on the very same catalog: the asymmetry was
        # an oversight, not a decision. Fail closed like every other
        # unrecoverable arm, under its OWN log event, because "the catalog is
        # unreadable" and "this slug does not resolve" need different
        # responses from whoever reads the line.
        # #VERIFY: tests/unit/test_personalizable_slots.py::
        # test_version_resolution_fails_closed_when_the_catalog_is_unreadable.
        _logger.warning(
            "moderation.version_contract_band_scan_failed",
            story_id=version_row.storybook_id,
            slug=slug,
            error=str(exc)[:500],
        )
        return None
    if band is None:
        _logger.warning(
            "moderation.version_contract_band_missing",
            story_id=version_row.storybook_id,
            slug=slug,
        )
    return band


def personalizable_slot_ids_for_version(
    version_row: StorybookVersion,
) -> PersonalizableSlots:
    """Resolve a ``StorybookVersion``'s declared personalizable slot ids.

    The sibling of :func:`personalizable_slot_ids_for_job` for a caller that
    holds a version but no job. Returns the SAME tri-state, resolved from the
    version's own ``skeleton_slug`` instead of a ``GenerationJob``'s
    ``authoring_metadata``.

    ``StorybookVersion`` carries no band, which is the reason
    :func:`personalizable_slot_ids_for_story` recovers one from a job row at
    all. :func:`~cyo_adventure.generation.skeleton_match.find_skeleton_band`
    recovers it from the catalog instead, so a book with no job row stops
    being unresolvable.

    Args:
        version_row: The version whose theme contract to resolve.

    Returns:
        PersonalizableSlots: The declared personalizable slot ids. An EMPTY
            frozenset whenever no personalizable slot could legitimately
            exist: no ``skeleton_slug`` (not a skeleton-backed version), or a
            legacy skeleton whose contract sidecar is absent
            (:func:`~cyo_adventure.generation.binding.load_contract_for`
            returns ``None``). :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE` only
            when the version DOES carry a slug but the contract cannot be
            recovered, so the caller must fail closed rather than risk
            treating a real sentinel as forged.
    """
    # #CRITICAL: data-integrity: this exists because api/remoderate.py's
    # population is imported books, which have NO generation_job row (verified
    # against production 2026-08-24: 17 of 17 in_review books). Routed through
    # personalizable_slot_ids_for_story they resolve the fail-closed marker,
    # and moderation/pipeline.py turns that into a sentinel_integrity_violation
    # BLOCK, so every book's accurate report would be overwritten with a block
    # describing absent provenance rather than its prose, and the repair branch
    # (gated on `not report.has_hard_block`) would be suppressed with it. The
    # tri-state itself is unchanged: only the "this book never had a job" case,
    # which says nothing about safety, stops failing closed.
    # #VERIFY: tests/unit/test_personalizable_slots.py::
    # test_version_resolution_needs_no_generation_job and
    # ::test_version_with_an_unlocatable_slug_fails_closed pin both arms.
    slug = version_row.skeleton_slug
    if not slug:
        return frozenset()
    band = _band_for_version(version_row, slug)
    if band is None:
        return PERSONALIZABLE_SLOTS_UNRECOVERABLE
    try:
        skeleton_path = resolve_skeleton_path(band, slug)
        contract = load_contract_for(skeleton_path, load_skeleton(skeleton_path))
    except (CoreValidationError, OSError, ValueError) as exc:
        # #EDGE: external-resources: load_skeleton does json.loads(read_text),
        # which raises a raw OSError or JSONDecodeError (a ValueError subclass),
        # NOT a CoreValidationError, when a catalog file has moved or been
        # corrupted. Mirrors _contract_for_job's note on the identical chain.
        # #VERIFY: tests/unit/test_personalizable_slots.py::
        # test_version_with_an_unreadable_contract_fails_closed pins this
        # fail-closed marker, and
        # test_version_on_a_legacy_skeleton_returns_the_empty_set pins that
        # the no-sidecar arm below stays the EMPTY set rather than collapsing
        # into it.
        _logger.warning(
            "moderation.version_contract_load_failed",
            story_id=version_row.storybook_id,
            slug=slug,
            band=band,
            error=str(exc)[:500],
        )
        return PERSONALIZABLE_SLOTS_UNRECOVERABLE
    if contract is None:
        return frozenset()
    return personalizable_slot_ids(contract)
