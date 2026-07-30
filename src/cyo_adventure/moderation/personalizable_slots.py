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
- ``None`` when a contract may exist but cannot be recovered (fail closed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from cyo_adventure.core.exceptions import ValidationError as CoreValidationError
from cyo_adventure.db.models import GenerationJob
from cyo_adventure.generation.authoring_metadata import (
    SKELETON_BAND_KEY,
    SKELETON_SLUG_KEY,
)
from cyo_adventure.generation.binding import load_contract_for, personalizable_slot_ids
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.generation.skeleton_match import resolve_skeleton_path
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_logger = get_logger(__name__)


class PersonalizableSlotsUnset:
    """Marker type for :data:`PERSONALIZABLE_SLOTS_UNSET` (Task 6c).

    ``None`` is a MEANINGFUL, fail-closed return value in the
    personalizable-slot tri-state contract (see
    :func:`personalizable_slot_ids_for_job`'s docstring), so it cannot also
    serve as "the caller passed nothing" for
    :func:`~cyo_adventure.moderation.pipeline.run_moderation_pipeline`'s
    ``personalizable_slots`` parameter, nor for
    :func:`~cyo_adventure.generation.import_story.import_filled_story`'s
    pass-through of the same parameter: a caller that legitimately resolved
    ``None`` (personalization possible but the contract is uncomputable) must
    be able to thread that exact value through and have it still fail
    closed, not have it silently reinterpreted as "resolve it yourself,
    caller forgot". A dedicated sentinel TYPE (not a shared ``object()``)
    lets ``isinstance`` narrow the parameter cleanly under BasedPyright
    strict mode.
    """

    __slots__ = ()


PERSONALIZABLE_SLOTS_UNSET: Final = PersonalizableSlotsUnset()
"""Default marker meaning "the caller did not supply personalizable_slots".

When :func:`~cyo_adventure.moderation.pipeline.run_moderation_pipeline`
receives this exact sentinel (its parameter's default), it resolves the slot
set itself via :func:`personalizable_slot_ids_for_story`, exactly as it always
has. Any other value passed for the parameter -- a real ``frozenset[str]`` OR
an explicit ``None`` -- is used VERBATIM instead (Task 6c: threads the
resume path's own, correctly-timed and correctly-banded, resolution).
"""

PersonalizableSlotsArg = frozenset[str] | None | PersonalizableSlotsUnset
"""Type of the ``personalizable_slots`` override parameter.

Shared by
:func:`~cyo_adventure.moderation.pipeline.run_moderation_pipeline` and
:func:`~cyo_adventure.generation.import_story.import_filled_story`, which
forwards its own same-named parameter through unchanged.
"""


async def personalizable_slot_ids_for_story(
    session: AsyncSession, story_id: str
) -> frozenset[str] | None:
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
        frozenset[str] | None: see :func:`personalizable_slot_ids_for_job` for
            the two cases that function decides. This function adds a third
            that the delegated contract does not cover: NO matching
            ``GenerationJob`` row at all, which returns an EMPTY frozenset.
            See the comment on that branch for why empty and not ``None``.
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
        # legitimately exist: an empty frozenset, not the fail-closed `None`.
        # `None` would be the more paranoid answer, but it is the WRONG one
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


def personalizable_slot_ids_for_job(
    job: GenerationJob, *, band: str | None = None
) -> frozenset[str] | None:
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
        frozenset[str] | None: The declared personalizable slot ids. An EMPTY
            frozenset is returned (not a guess) whenever no personalizable
            slot could legitimately exist for this job: no ``skeleton_slug``
            (a ``fresh_generation`` job), or a legacy skeleton with no
            theme-contract sidecar
            (:func:`~cyo_adventure.generation.binding.load_contract_for`
            returns ``None``). ``None`` is returned only when the job DOES
            carry a ``skeleton_slug`` (so a contract may genuinely declare
            personalizable slots) but the contract cannot be recovered (no
            band available from either source, or the skeleton/contract
            sidecar failing to load): the caller must fail closed rather
            than risk treating a real sentinel as forged with a guessed
            empty set.
    """
    authoring = (
        job.authoring_metadata if isinstance(job.authoring_metadata, dict) else {}
    )
    slug = authoring.get(SKELETON_SLUG_KEY)
    if not isinstance(slug, str):
        return frozenset()
    resolved_band = band if band is not None else authoring.get(SKELETON_BAND_KEY)
    if not isinstance(resolved_band, str):
        _logger.warning(
            "moderation.repair_contract_band_missing",
            job_id=str(job.id),
            story_id=job.storybook_id,
            slug=slug,
        )
        return None
    try:
        skeleton_path = resolve_skeleton_path(resolved_band, slug)
        skeleton = load_skeleton(skeleton_path)
        contract = load_contract_for(skeleton_path, skeleton)
    # #CRITICAL: external-resources: load_skeleton (generation/skeleton.py)
    # does json.loads(path.read_text(...)), which raises a raw
    # FileNotFoundError/OSError/JSONDecodeError (a ValueError subclass), NOT
    # a CoreValidationError, when the skeleton file a stale
    # GenerationJob.authoring_metadata points at has since moved or been
    # corrupted. Broadened here to mirror
    # generation/import_story.py::_load_resume_skeleton's handling of this
    # same resolve_skeleton_path -> load_skeleton chain, so a missing/corrupt
    # sidecar fails this function closed (None) instead of crashing the
    # entire moderation pass.
    # #VERIFY: test_repair_contract_file_missing_is_discarded_and_routes_to_human_review.
    except (FileNotFoundError, OSError, ValueError, CoreValidationError) as exc:
        _logger.warning(
            "moderation.repair_contract_load_failed",
            job_id=str(job.id),
            story_id=job.storybook_id,
            slug=slug,
            band=resolved_band,
            error=str(exc)[:500],
        )
        return None
    if contract is None:
        return frozenset()
    return personalizable_slot_ids(contract)
