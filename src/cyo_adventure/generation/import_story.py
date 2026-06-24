"""Import an externally-authored filled story into the story store.

Gated by the same validator used by the generation worker. Intended for use
by the cyo-author Claude Code authoring skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
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
        The persisted story id (the blob's ``id``).

    Raises:
        ValueError: If the validation gate blocks the story, or the blob has no
            string id.
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
        raise ValueError(msg)

    story_id = request.blob.get("id")
    if not isinstance(story_id, str) or not story_id:
        msg = "filled story has no string id"
        raise ValueError(msg)

    return await persist_storybook(
        session,
        StorybookParams(
            story_id=story_id,
            blob=request.blob,
            family_id=request.family_id,
            created_by=request.created_by,
            model=request.model,
            prompt_version=request.prompt_version,
            validation_report=result.report.to_dict(),
        ),
    )
