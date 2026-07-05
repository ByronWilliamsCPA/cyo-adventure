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


@dataclass(frozen=True, slots=True)
class ImportRequest:
    """Caller-supplied inputs for import_filled_story.

    Attributes:
        family_id: Owning family (the ownership boundary).
        blob: The filled Storybook JSON as a dict.
        created_by: Optional authoring user id.
        model: Optional model identifier (e.g. the fill model).
        prompt_version: Skill/prompt version recorded on the version.
    """

    family_id: uuid.UUID
    blob: dict[str, object]
    created_by: uuid.UUID | None = None
    model: str | None = None
    prompt_version: str = "skeleton-fill-v1"


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
    )

    return story_id


async def resume_manual_fill(
    session: AsyncSession,
    job_id: uuid.UUID,
    blob: dict[str, object],
    *,
    model: str | None = None,
) -> str:
    """Resume a skill-authored skeleton fill parked at "awaiting_manual_fill".

    Loads the job's concept for its family_id, then delegates to
    :func:`import_filled_story` for the same gate + persist + moderation
    pipeline every other import uses. On success the job is marked "passed"
    and linked to the new storybook. On a validation-gate block the job is
    marked "failed" and the error is recorded before the exception
    propagates, mirroring generation/worker.py's failure-commit-then-reraise
    pattern. Unlike import_filled_story (which deliberately does not own the
    transaction -- see its own docstring), this function DOES commit the job
    row's status itself, in both branches, so a caller-side rollback can
    never silently discard it.

    Args:
        session: Open async session; the story/version write still follows
            import_filled_story's own transaction contract, but this
            function's job-row updates are committed here directly.
        job_id: The GenerationJob row to resume.
        blob: The filled Storybook JSON, already loaded from disk.
        model: Optional model identifier to record (the fill model).

    Returns:
        The persisted story id.

    Raises:
        ResourceNotFoundError: If the job or its concept does not exist.
        StateTransitionError: If the job is not "awaiting_manual_fill".
        ValidationError: Propagated from import_filled_story if the gate
            blocks the filled story; the job is marked "failed" first.
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

    request = ImportRequest(blob=blob, family_id=concept.family_id, model=model)
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

    skeleton_slug = (
        job.authoring_metadata.get("skeleton_slug")
        if isinstance(job.authoring_metadata, dict)
        else None
    )
    if isinstance(skeleton_slug, str):
        band = (
            concept.brief.get("age_band") if isinstance(concept.brief, dict) else None
        )
        band = band if isinstance(band, str) else ""
        # #ASSUME: external-resources: re-reads the same skeleton file the
        # authoring-plan endpoint matched (see generation/skeleton_match.py);
        # a moved or renamed file since matching would raise FileNotFoundError.
        # #VERIFY: test_stage1_violations_are_recorded_on_the_job.
        original_skeleton = load_skeleton(
            Path("skeletons") / band / f"{skeleton_slug}.json"
        )
        pii = PiiContext(child_names=frozenset(), birthdates=frozenset())
        violations = await run_stage1_gate(
            original_skeleton,
            blob,
            review_stage1_model=None,
            settings=_default_settings,
            pii=pii,
        )
        if violations:
            job.status = "needs_review"
            job.error = "; ".join(violations)[:512]
            await session.commit()
            return story_id

    job.status = "passed"
    job.storybook_id = story_id
    job.version = _FIRST_VERSION
    await session.commit()
    return story_id
