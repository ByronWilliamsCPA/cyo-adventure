"""Import an externally-authored filled story into the story store.

Gated by the same validator used by the generation worker, and screened by the
same moderation pipeline before it can leave ``draft``. Intended for use by the
cyo-author Claude Code authoring skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.exceptions import (
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import ChildProfile, Concept, GenerationJob
from cyo_adventure.generation.fidelity_gate import run_stage1_gate
from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.moderation import run_moderation_pipeline
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

# Every job resumed by resume_manual_fill produces a fresh Storybook, so its
# sole version is 1, mirroring generation/worker.py's _FIRST_VERSION.
_FIRST_VERSION = 1

# Sentinel recorded on StorybookVersion.provider for a version created via
# this offline authoring import path, distinguishing it from a real generation
# provider name ("mock", "anthropic", ...) stamped by generation/worker.py.
_IMPORT_PROVIDER = "import"


@dataclass(frozen=True, slots=True)
class ImportRequest:
    """Caller-supplied inputs for import_filled_story.

    Attributes:
        family_id: Owning family (the ownership boundary).
        blob: The filled Storybook JSON as a dict.
        created_by: Optional authoring user id.
        model: Optional model identifier (e.g. the fill model).
        prompt_version: Skill/prompt version recorded on the version.
        review_model_override: Optional admin-chosen override for the Stage 2
            moderation review model, threaded into ``run_moderation_pipeline``.
            Mirrors ``generation/worker.py::run_generation_job``'s own
            ``authoring_metadata.get("review_stage2_model")`` read, so the
            skill-authored resume path (``resume_manual_fill``) honors the
            same per-job override the automated_provider path already does.
    """

    family_id: uuid.UUID
    blob: dict[str, object]
    created_by: uuid.UUID | None = None
    model: str | None = None
    prompt_version: str = "skeleton-fill-v1"
    review_model_override: str | None = None


async def import_filled_story(session: AsyncSession, request: ImportRequest) -> str:
    """Validate a filled story and persist it if the gate does not block.

    Args:
        session: Open async session; caller owns the transaction.
        request: The grouped import inputs (see :class:`ImportRequest`).

    Returns:
        The persisted story id (the blob's ``id``). The story leaves ``draft``
        for ``in_review`` (clean or repaired) or ``needs_revision`` (hard
        block) before this returns; it is never left as an unscreened draft.

    Raises:
        ValidationError: If the validation gate blocks the story, or the blob has
            no string id.
        ProjectBaseError: Propagated, uncaught, from the post-persist moderation
            pipeline call below (e.g. ResourceNotFoundError, or an
            ExternalServiceError from a review-backend failure). Unlike
            generation/worker.py, this function does not own the transaction, so
            it does not catch or reinterpret a moderation failure; the caller's
            session close/rollback (core/database.py::get_session) is what keeps
            a failed import from leaving a half-committed row.
    """
    # #CRITICAL: data-integrity: the gate result and the blob must agree on id;
    # if the blob's id is missing or wrong, the stored version row is unreachable.
    # #VERIFY: test_import_persists_a_valid_filled_story asserts story_id == blob["id"].
    result = run_gate(request.blob)
    if result.blocked:
        messages = (
            "; ".join(f.message for f in result.report.errors)
            or "no error details available"
        )
        msg = f"filled story blocked by validation gate: {messages}"
        raise ValidationError(msg)

    story_id = request.blob.get("id")
    if not isinstance(story_id, str) or not story_id:
        msg = "filled story has no string id"
        raise ValidationError(msg)

    params = StorybookParams(
        story_id=story_id,
        blob=request.blob,
        family_id=request.family_id,
        created_by=request.created_by,
        model=request.model,
        prompt_version=request.prompt_version,
        provider=_IMPORT_PROVIDER,
        validation_report=result.report.to_dict(),
    )
    await persist_storybook(session, params)

    # #CRITICAL: security: closes C3-SAFETY Finding 1 (adversarial-safety-
    # evaluation.md): import_filled_story used to persist a draft and stop,
    # leaving an externally-authored story (e.g. the cyo-author skeleton-fill
    # route) reachable by admin submit/approve with zero content screening.
    # This calls the same run_moderation_pipeline as generation/worker.py, but
    # NOT identically: worker.py wraps this call in try/except and does its own
    # rollback/status bookkeeping on failure, while this function deliberately
    # lets a moderation-pipeline exception propagate uncaught (see the Raises:
    # section above) because it does not own the transaction.
    # publishing.service.approve additionally refuses to publish any version
    # with moderation_report=None (Finding 2's structural backstop), so this
    # call is defense in depth, not the sole gate.
    # #VERIFY: test_import_screens_the_persisted_story /
    # test_import_propagates_moderation_failure.
    child_result = await session.execute(
        select(ChildProfile.display_name).where(
            ChildProfile.family_id == request.family_id
        )
    )
    child_names: frozenset[str] = frozenset(row for (row,) in child_result.all() if row)
    pii = PiiContext(child_names=child_names, birthdates=frozenset())

    await run_moderation_pipeline(
        session=session,
        story_id=story_id,
        version=params.version,
        settings=_default_settings,
        generation_provider=build_provider(_default_settings),
        pii=pii,
        review_model_override=request.review_model_override,
    )

    return story_id


def _str_meta(metadata: object, key: str) -> str | None:
    """Read a string value from a job's ``authoring_metadata``, tolerating junk.

    Args:
        metadata: The job's ``authoring_metadata`` (expected dict, but any type
            is tolerated).
        key: The metadata key to read.

    Returns:
        The value at ``key`` only when ``metadata`` is a dict and the value is a
        string; any other shape degrades to ``None`` (no override) instead of
        raising, matching the defensive reads in generation/worker.py.
    """
    # #ASSUME: data-integrity: authoring_metadata is a plain dict for every
    # method="skeleton_fill" job (see story_requests/authoring_plan.py); a
    # missing/wrong-typed value degrades to "no override" instead of raising.
    # #VERIFY: test_review_model_overrides_are_threaded_through_resume.
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _load_resume_skeleton(band: str, skeleton_slug: str) -> dict[str, object]:
    """Load the skeleton a parked fill was matched against, as a clean error.

    Args:
        band: The age-band directory segment (may be "").
        skeleton_slug: The matched skeleton's filename stem.

    Returns:
        The parsed skeleton document.

    Raises:
        ResourceNotFoundError: If the skeleton file no longer exists.
        ValidationError: If the skeleton file is unreadable or not valid JSON.
    """
    # #ASSUME: external-resources: re-reads the same skeleton file the
    # authoring-plan endpoint matched (see generation/skeleton_match.py); a file
    # moved or corrupted since matching raises a raw FileNotFoundError/JSON
    # error, which is not a ProjectBaseError. Map those to the project hierarchy
    # so import_cli's top-level handler reports a clean "import failed" instead
    # of a raw traceback; the caller still rolls back cleanly (no orphaned job).
    # #VERIFY: test_resume_missing_skeleton_file_is_clean_error.
    skeleton_path = Path("skeletons") / band / f"{skeleton_slug}.json"
    try:
        return load_skeleton(skeleton_path)
    except FileNotFoundError as exc:
        msg = f"skeleton file not found for resume: {skeleton_path}"
        raise ResourceNotFoundError(
            msg, resource_type="Skeleton", resource_id=skeleton_slug
        ) from exc
    except (OSError, ValueError) as exc:
        msg = f"skeleton for resume is unreadable or invalid: {skeleton_path}"
        raise ValidationError(msg) from exc


async def resume_manual_fill(
    session: AsyncSession,
    job_id: uuid.UUID,
    blob: dict[str, object],
    *,
    model: str | None = None,
) -> tuple[str, str]:
    """Resume a skill-authored skeleton fill parked at "awaiting_manual_fill".

    Loads the job's concept for its family_id, then delegates to
    :func:`import_filled_story` for the same gate + persist + moderation
    pipeline every other import uses, threading the job's own
    ``authoring_metadata.get("review_stage2_model")`` override through as
    ``ImportRequest.review_model_override``. On success the job is marked
    "passed" and linked to the new storybook. If the job carries a
    ``skeleton_slug``, the Stage 1 fidelity gate also runs afterward (using
    ``authoring_metadata.get("review_stage1_model")`` as its own override,
    same source dict, different key); a fidelity violation marks the job
    "needs_review" instead of "passed", but the job is still linked to the
    storybook :func:`import_filled_story` already persisted (only
    status/error differ between the two outcomes -- neither branch orphans
    the job row from its story). On a validation-gate block the job is
    marked "failed" and the error is recorded before the exception
    propagates, mirroring generation/worker.py's failure-commit-then-reraise
    pattern. Unlike import_filled_story (which deliberately does not own the
    transaction -- see its own docstring), this function commits the job row's
    status itself for every HANDLED outcome (gate block -> "failed", Stage 1
    downgrade -> "needs_review", clean -> "passed"), so a caller-side rollback
    cannot silently discard a recorded outcome. An UNEXPECTED exception after
    the storybook was persisted (a provider error in the semantic check) is
    deliberately NOT committed here: it propagates and the caller's session
    rolls back, discarding the just-persisted story so the job stays
    "awaiting_manual_fill" for a clean retry (never orphaned).

    The matched skeleton library file is loaded BEFORE the story is persisted
    (closes #128), not re-read afterward: the file may be moved, renamed, or
    removed at any point in the job's lifetime (it is static production
    content matched at authoring-plan time, possibly long before a skill
    resumes it), and a re-read after persisting used to raise an uncaught
    ResourceNotFoundError, stranding the job at "awaiting_manual_fill" despite
    a real, already-persisted story existing for it. Loading first means the
    in-memory snapshot survives even if the file is deleted later in this same
    call. If the file cannot be loaded at all (missing even at this earlier
    point), the Stage 1 gate is skipped and the job is marked "needs_review"
    instead of being stranded: the story already exists and passed moderation,
    it just cannot be re-verified against its origin skeleton.

    Args:
        session: Open async session; the story/version write still follows
            import_filled_story's own transaction contract, but this
            function's job-row updates are committed here directly.
        job_id: The GenerationJob row to resume.
        blob: The filled Storybook JSON, already loaded from disk.
        model: Optional model identifier to record (the fill model).

    Returns:
        A ``(story_id, status)`` pair: the persisted story id and the job's
        final status, either ``"passed"`` or ``"needs_review"`` (a Stage 1
        fidelity downgrade, or a skeleton the Stage 1 gate could not load). A
        hard gate block does not return; it raises.

    Raises:
        ResourceNotFoundError: If the job or its concept does not exist.
        StateTransitionError: If the job is not "awaiting_manual_fill".
        ValidationError: Propagated from import_filled_story if the gate
            blocks the filled story (the job is marked "failed" first).
        ProjectBaseError: Propagated from the moderation pipeline on failure,
            same as import_filled_story (not intercepted here).
    """
    job = await session.get(GenerationJob, job_id)
    if job is None:
        msg = f"GenerationJob {job_id} not found"
        raise ResourceNotFoundError(
            msg, resource_type="GenerationJob", resource_id=str(job_id)
        )
    if job.status != "awaiting_manual_fill":
        msg = f"job is '{job.status}', not awaiting_manual_fill"
        raise StateTransitionError(msg)

    concept = await session.get(Concept, job.concept_id)
    if concept is None:
        msg = f"Concept {job.concept_id} not found"
        raise ResourceNotFoundError(
            msg, resource_type="Concept", resource_id=str(job.concept_id)
        )

    # #CRITICAL: external-resources: load the matched skeleton BEFORE
    # persisting the filled story, not after (#128). The skeleton library file
    # is read once here, into memory; even if it is moved or removed later in
    # this same call (or at any point before this call, since it may have been
    # matched long ago), the Stage 1 gate below still runs against this
    # captured snapshot -- or, if it could not be loaded at all, degrades to
    # a needs_review downgrade instead of stranding the job.
    # #VERIFY: integration test test_resume_survives_skeleton_file_deleted_after_persist
    # in tests/integration/test_resume_manual_fill.py exercises a real missing
    # file, not a monkeypatched load_skeleton.
    skeleton_slug = _str_meta(job.authoring_metadata, "skeleton_slug")
    original_skeleton: dict[str, object] | None = None
    skeleton_load_error: str | None = None
    if skeleton_slug is not None:
        band = (
            concept.brief.get("age_band") if isinstance(concept.brief, dict) else None
        )
        band = band if isinstance(band, str) else ""
        try:
            original_skeleton = _load_resume_skeleton(band, skeleton_slug)
        except (ResourceNotFoundError, ValidationError) as exc:
            skeleton_load_error = str(exc)

    review_stage2_model = _str_meta(job.authoring_metadata, "review_stage2_model")
    request = ImportRequest(
        blob=blob,
        family_id=concept.family_id,
        model=model,
        review_model_override=review_stage2_model,
    )
    try:
        story_id = await import_filled_story(session, request)
    except ValidationError as exc:
        # #CRITICAL: data-integrity: record the gate-block on the job row
        # before re-raising, mirroring worker.py's failure-commit-then-reraise
        # pattern, so import_cli's get_session context manager (which rolls
        # back on an exception exiting the `async with` block) cannot
        # silently discard this job's failure state.
        # #VERIFY: covered at the integration level (tests/integration/
        # test_resume_manual_fill.py::test_resume_gate_block_marks_job_failed);
        # this unit test file's fake session cannot exercise the real gate.
        job.status = "failed"
        job.error = str(exc)[:512]
        await session.commit()
        raise

    # import_filled_story already persisted a real Storybook + StorybookVersion
    # for story_id above; link the job to it now, before the Stage 1 check
    # below can downgrade the status, so neither outcome ever orphans the job
    # row from the story it produced (only status/error differ below).
    job.storybook_id = story_id
    job.version = _FIRST_VERSION

    if skeleton_slug is not None:
        if original_skeleton is None:
            # #CRITICAL: data-integrity: the skeleton could not be loaded even
            # before persisting (moved/removed at any point since the
            # authoring-plan match, or concurrently). The story already exists
            # and passed moderation; it just cannot be re-verified against its
            # origin skeleton, so this is a needs_review downgrade, never a
            # stuck "awaiting_manual_fill" job (#128).
            # #VERIFY: covered at the unit level by monkeypatching
            # load_skeleton to raise; no dedicated real-file test for this
            # branch since it degenerates to the same missing-file mechanics
            # test_resume_survives_skeleton_file_deleted_after_persist proves.
            job.status = "needs_review"
            job.error = (
                skeleton_load_error or "matched skeleton unavailable for Stage 1 gate"
            )[:512]
            await session.commit()
            return story_id, "needs_review"

        pii = PiiContext(child_names=frozenset(), birthdates=frozenset())
        review_stage1_model = _str_meta(job.authoring_metadata, "review_stage1_model")
        violations = await run_stage1_gate(
            original_skeleton,
            blob,
            review_stage1_model=review_stage1_model,
            prep_model=job.model,
            settings=_default_settings,
            pii=pii,
        )
        if violations:
            # #CRITICAL: data-integrity: storybook_id/version were already
            # linked above; only status/error differ from the clean-pass
            # branch below, mirroring the automated_provider mechanism's own
            # Stage 1 downgrade in worker.py::run_generation_job, which
            # persists the storybook and still marks the job needs_review.
            # #VERIFY: covered by test_stage1_violations_are_recorded_on_the_job
            # in the unit test file, which checks the job's storybook_id and
            # version fields are both populated alongside needs_review.
            job.status = "needs_review"
            job.error = "; ".join(violations)[:512]
            await session.commit()
            return story_id, "needs_review"

    job.status = "passed"
    await session.commit()
    return story_id, "passed"
