"""Import an externally-authored filled story into the story store.

Gated by the same validator used by the generation worker. Intended for use
by the cyo-author Claude Code authoring skill.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


async def import_filled_story(
    session: AsyncSession,
    *,
    blob: dict[str, object],
    family_id: uuid.UUID,
    created_by: uuid.UUID | None = None,
    model: str | None = None,
    prompt_version: str = "skeleton-fill-v1",
) -> str:
    """Validate a filled story and persist it if the gate does not block.

    Args:
        session: Open async session; caller owns the transaction.
        blob: The filled Storybook JSON as a dict.
        family_id: Owning family.
        created_by: Optional authoring user id.
        model: Optional model identifier (e.g. the fill model).
        prompt_version: Skill/prompt version recorded on the version.

    Returns:
        The persisted story id (the blob's ``id``).

    Raises:
        ValueError: If the validation gate blocks the story, or the blob has no
            string id.
    """
    # #CRITICAL: data-integrity: the gate result and the blob must agree on id;
    # if the blob's id is missing or wrong, the stored version row is unreachable.
    # #VERIFY: test_import_persists_a_valid_filled_story asserts story_id == blob["id"].
    result = run_gate(blob)
    if result.blocked:
        messages = (
            "; ".join(f.message for f in result.report.errors)
            or "no error details available"
        )
        msg = f"filled story blocked by validation gate: {messages}"
        raise ValueError(msg)

    story_id = blob.get("id")
    if not isinstance(story_id, str) or not story_id:
        msg = "filled story has no string id"
        raise ValueError(msg)

    return await persist_storybook(
        session,
        StorybookParams(
            story_id=story_id,
            blob=blob,
            family_id=family_id,
            created_by=created_by,
            model=model,
            prompt_version=prompt_version,
            validation_report=result.report.to_dict(),
        ),
    )
