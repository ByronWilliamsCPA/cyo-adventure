"""Import an externally-authored filled story into the story store.

Gated by the same validator used by the generation worker, and screened by the
same moderation pipeline before it can leave ``draft``. Intended for use by the
cyo-author Claude Code authoring skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import ChildProfile
from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.moderation import run_moderation_pipeline
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


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
