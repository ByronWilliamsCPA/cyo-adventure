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

import json
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

    Deliberately NOT truthy-by-default and NOT falsy either, for the same
    reason as :class:`PersonalizableSlotsUnrecoverable` and one arm further
    over. Once a consumer narrows the fail-closed marker away, the residual
    union is ``frozenset[str] | PersonalizableSlotsUnset``, and that union IS
    truthiness-testable with no diagnostic: a default-truthy sentinel lands
    in the "slots are declared" branch, a default-falsy one in the "no slot
    is declared" branch, and this value means neither. The code that reads
    this marker today is safe only because
    :func:`~cyo_adventure.moderation.pipeline.run_moderation_pipeline`
    narrows UNSET before UNRECOVERABLE, which is statement ordering rather
    than anything the type expresses; :meth:`__bool__` is what expresses it.
    """

    __slots__ = ()

    def __bool__(self) -> NoReturn:
        """Refuse to collapse "the caller supplied nothing" into a boolean.

        Raises:
            TypeError: Always. The message names both readings a truthiness
                test could have intended, because this marker means neither
                one and the traceback points at the line to fix.
        """
        msg = (
            "no personalizable_slots override was supplied, so this value has "
            "no truth value: it never means 'slots are declared' and it never "
            "means 'no slot is declared'. Use isinstance(slots, "
            "PersonalizableSlotsUnset) to resolve the contract yourself, or "
            "narrow to the frozenset arm first if you meant to read a declared "
            "slot set"
        )
        raise TypeError(msg)

    def __repr__(self) -> str:
        """Return the module-level constant's name rather than a default repr.

        Returns:
            str: The constant name, so a log line or a failed assertion names
                the state instead of printing an object id.
        """
        return "PERSONALIZABLE_SLOTS_UNSET"

    # #CRITICAL: data-integrity: the three methods below make this marker a
    # true singleton. Without them `copy.copy`, `copy.deepcopy`, and a
    # serialize/deserialize round trip each return a DISTINCT instance that
    # still satisfies `isinstance`, so an `is` comparison and an `isinstance`
    # narrowing disagree about the same value. That matters because this
    # marker travels through a frozen dataclass field and across
    # `run_sync`, and because this module's own tests assert with `is`.
    # #VERIFY: tests/unit/test_personalizable_slots.py::
    # test_the_markers_survive_copy_deepcopy_and_a_serialization_round_trip.
    def __copy__(self) -> PersonalizableSlotsUnset:
        """Return the module constant, never a second instance.

        Returns:
            PersonalizableSlotsUnset: :data:`PERSONALIZABLE_SLOTS_UNSET`.
        """
        return PERSONALIZABLE_SLOTS_UNSET

    def __deepcopy__(self, _memo: dict[int, object]) -> PersonalizableSlotsUnset:
        """Return the module constant, never a second instance.

        Args:
            _memo: The ``copy.deepcopy`` memo dict, unused: this marker holds
                no state to copy.

        Returns:
            PersonalizableSlotsUnset: :data:`PERSONALIZABLE_SLOTS_UNSET`.
        """
        return PERSONALIZABLE_SLOTS_UNSET

    def __reduce__(self) -> str:
        """Serialize by NAME, so a round trip resolves the module constant.

        Returns:
            str: The module-level constant's name, which is the stdlib
                serialization protocol for "this object is a singleton
                global".
        """
        return "PERSONALIZABLE_SLOTS_UNSET"


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
    the runtime ``TypeError`` :meth:`__bool__` raises. So a ``bool(...)``
    over a raw resolver result is a runtime crash the type gate will not
    catch: :class:`~cyo_adventure.generation.persistence.StorybookParams`
    documents the eligibility recipe with its ``isinstance`` narrowing step
    FIRST for exactly that reason. Narrowing to the ``frozenset`` arm first
    both type-checks and runs, which is precisely the reading that stays
    legitimate.

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

    # #CRITICAL: data-integrity: see the identical block on
    # `PersonalizableSlotsUnset`. Without these three, an `is` comparison and
    # an `isinstance` narrowing can disagree about the same value after a
    # copy or a serialization round trip, and this is the arm where that
    # disagreement fails OPEN.
    # #VERIFY: tests/unit/test_personalizable_slots.py::
    # test_the_markers_survive_copy_deepcopy_and_a_serialization_round_trip.
    def __copy__(self) -> PersonalizableSlotsUnrecoverable:
        """Return the module constant, never a second instance.

        Returns:
            PersonalizableSlotsUnrecoverable:
                :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE`.
        """
        return PERSONALIZABLE_SLOTS_UNRECOVERABLE

    def __deepcopy__(
        self, _memo: dict[int, object]
    ) -> PersonalizableSlotsUnrecoverable:
        """Return the module constant, never a second instance.

        Args:
            _memo: The ``copy.deepcopy`` memo dict, unused: this marker holds
                no state to copy.

        Returns:
            PersonalizableSlotsUnrecoverable:
                :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE`.
        """
        return PERSONALIZABLE_SLOTS_UNRECOVERABLE

    def __reduce__(self) -> str:
        """Serialize by NAME, so a round trip resolves the module constant.

        Returns:
            str: The module-level constant's name, which is the stdlib
                serialization protocol for "this object is a singleton
                global".
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


def _stored_slug(slug: object) -> str | None:
    """Return a stored skeleton slug's usable form, or None when it names none.

    The single definition of "this row names no skeleton", shared by
    :func:`_contract_for_job` (reading ``authoring_metadata``) and
    :func:`personalizable_slot_ids_for_version` (reading
    ``StorybookVersion.skeleton_slug``). The two used to disagree: the job
    path tested ``not isinstance(slug, str)``, so an EMPTY string passed the
    check, resolved a path ending in ``/.json``, failed to load, and returned
    the fail-closed marker; the version path tested ``not slug``, so the same
    corrupt provenance returned the benign empty frozenset. Identical
    provenance, opposite verdicts, decided only by whether the caller held a
    job or a version.

    Both functions' documented contracts already call "no ``skeleton_slug``"
    the benign arm, so the shared answer is that arm: an empty or
    whitespace-only slug is ABSENT provenance, not a contract that failed to
    load. It names no file, so there is no contract that could have declared
    a personalizable slot, which is exactly what the empty frozenset asserts.

    Args:
        slug: The raw stored value, deliberately un-narrowed: the job path
            reads it out of an untyped JSON dict.

    Returns:
        str | None: ``slug`` unchanged when it is a string with some
            non-whitespace content, else ``None``. Returned UNSTRIPPED, so a
            slug that merely has stray whitespace keeps resolving exactly as
            it does today; only the wholly-blank case changes arm.
    """
    # #ASSUME: data-integrity: a blank stored slug is ABSENT provenance, not a
    # contract that failed to load, so it resolves the benign empty frozenset
    # rather than PERSONALIZABLE_SLOTS_UNRECOVERABLE. This is the one arm this
    # helper MOVES: the job path used to fail closed on an empty string and
    # both paths used to fail closed on a whitespace-only one. It is the
    # benign direction on a fail-closed control, so it is deliberately narrow:
    # only a slug with NO non-whitespace content qualifies, and a slug with
    # real content keeps resolving unstripped, exactly as before.
    # #VERIFY: tests/unit/test_personalizable_slots.py::
    # test_a_blank_slug_resolves_the_benign_arm_from_a_job and
    # tests/unit/test_personalizable_slots.py::
    # test_a_blank_slug_resolves_the_same_arm_from_a_job_and_a_version.
    if not isinstance(slug, str) or not slug.strip():
        return None
    return slug


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
        # #VERIFY: INFO, not WARNING, and deliberately so. This is the ROUTINE
        # path for imported and seeded stories, which are the whole of the
        # current in_review population (api/remoderate.py records 17 of 17
        # production in_review books with no job row, verified 2026-08-24),
        # and this resolver runs on every moderation-pipeline entry and every
        # node edit. At WARNING it fired for the entire imported catalog on
        # the happy path. It cannot claim more than INFO either: this function
        # sees only "no row matched", which is byte-identical whether the row
        # never existed (legacy) or was deleted mid-pipeline, so the anomaly
        # it used to claim to surface was never distinguishable here. A caller
        # that reached this function FROM a job it already holds knows the
        # difference; moderation/pipeline.py is where that WARNING belongs if
        # someone wants the signal, not here.
        _logger.info(
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
    its own, more specific ``moderation.contract_band_missing`` log event at
    its own severity (WARNING, against `_ContractLoadError`'s ERROR), while
    :func:`personalizable_slot_fields_for_story`, which only
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
    slug = _stored_slug(authoring.get(SKELETON_SLUG_KEY))
    if slug is None:
        return None
    resolved_band = band if band is not None else authoring.get(SKELETON_BAND_KEY)
    if not isinstance(resolved_band, str):
        no_band_msg = f"no resolvable skeleton band for slug '{slug}'"
        raise _NoResolvableBandError(slug, None, no_band_msg)
    # #CRITICAL: external-resources: load_skeleton (generation/skeleton.py)
    # does json.loads(path.read_text(...)), which raises a raw
    # OSError/JSONDecodeError/UnicodeDecodeError, NOT a CoreValidationError,
    # when the skeleton file a stale GenerationJob.authoring_metadata points
    # at has since moved or been corrupted. Wrapped here (mirroring
    # generation/import_story.py::_load_resume_skeleton's handling of this
    # same resolve_skeleton_path -> load_skeleton chain) so every caller fails
    # closed with the slug and band on its log line instead of crashing its
    # whole pass.
    #
    # The catch is DELIBERATELY not `ValueError`, which is what it used to be.
    # JSONDecodeError and UnicodeDecodeError are both ValueError subclasses,
    # so catching the base swept in Pydantic's own ValidationError and every
    # ordinary int()/str.index() bug inside the contract parser as well, and
    # turned a genuine programming or schema fault into a routine
    # "contract unrecoverable" plus one log line. FileNotFoundError is gone
    # for the same reason in reverse: it is an OSError subclass, so listing it
    # said nothing the next member did not already say.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_repair_contract_file_missing_is_discarded_and_routes_to_human_review
    # and tests/unit/test_personalizable_slots.py::
    # test_slot_fields_for_story_degrades_to_empty_when_the_skeleton_is_missing.
    try:
        skeleton_path = resolve_skeleton_path(resolved_band, slug)
        skeleton = load_skeleton(skeleton_path)
        return load_contract_for(skeleton_path, skeleton)
    except (
        OSError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        CoreValidationError,
    ) as exc:
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
            at all, or a blank one (a ``fresh_generation`` job, or a row whose
            provenance is absent; see :func:`_stored_slug`, which is what
            makes this agree with
            :func:`personalizable_slot_ids_for_version`), or a legacy
            skeleton with no theme-contract sidecar
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
        # WARNING, not ERROR: a job with a slug but no recoverable band is a
        # routine data-shape condition (an older job predating the
        # skeleton_band metadata key, with no caller-supplied override), not
        # a broken catalog. The fail-closed marker is the response; nobody
        # needs to be paged.
        _logger.warning(
            "moderation.contract_band_missing",
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
        #
        # ERROR, not WARNING, and the split from the band arm above is the
        # point: reaching here means the on-disk catalog is broken, moved, or
        # failing validation for a slug that resolved a band. That is an
        # operational fault someone has to fix, and it is not self-healing.
        # `.exception` is the house spelling for ERROR inside an except block
        # (api/remoderate.py, covers/service.py, publishing/service.py): same
        # severity, plus the chained loader traceback that `error=` truncates.
        _logger.exception(
            "moderation.contract_load_failed",
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
            exist: no ``skeleton_slug``, or a blank one (not a
            skeleton-backed version; see :func:`_stored_slug`, which is what
            makes this agree with :func:`personalizable_slot_ids_for_job`),
            or a legacy skeleton whose contract sidecar is absent
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
    slug = _stored_slug(version_row.skeleton_slug)
    if slug is None:
        return frozenset()
    band = _band_for_version(version_row, slug)
    if band is None:
        return PERSONALIZABLE_SLOTS_UNRECOVERABLE
    try:
        skeleton_path = resolve_skeleton_path(band, slug)
        contract = load_contract_for(skeleton_path, load_skeleton(skeleton_path))
    except (
        CoreValidationError,
        OSError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        # #EDGE: external-resources: load_skeleton does json.loads(read_text),
        # which raises a raw OSError, JSONDecodeError or UnicodeDecodeError,
        # NOT a CoreValidationError, when a catalog file has moved or been
        # corrupted. Mirrors _contract_for_job's note on the identical chain,
        # including why the catch names those two ValueError subclasses rather
        # than `ValueError` itself: the base swept in Pydantic validation
        # failures and ordinary parser bugs, and dressed them up as a routine
        # missing file.
        #
        # ERROR (via `.exception`, the house spelling inside an except
        # block), not WARNING, for the same reason as `_ContractLoadError`'s
        # arm in personalizable_slot_ids_for_job: the band resolved and the
        # read still failed, so the on-disk catalog is broken rather than
        # merely thin.
        # #VERIFY: tests/unit/test_personalizable_slots.py::
        # test_version_with_an_unreadable_contract_fails_closed pins this
        # fail-closed marker, and
        # test_version_on_a_legacy_skeleton_returns_the_empty_set pins that
        # the no-sidecar arm below stays the EMPTY set rather than collapsing
        # into it.
        _logger.exception(
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
