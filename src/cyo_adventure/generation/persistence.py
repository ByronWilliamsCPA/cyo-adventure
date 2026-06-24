"""Reusable persistence for a validated Storybook blob.

Extracted from the generation worker so both the worker and the offline
authoring-import path create ``storybook`` and ``storybook_version`` rows
identically. The caller owns the transaction (this helper flushes but does not
commit), matching the worker's unit-of-work contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.db.models import Storybook, StorybookVersion

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

_FIRST_VERSION = 1


@dataclass(frozen=True, slots=True)
class StorybookParams:
    """Grouped inputs for persist_storybook (avoids a wide kwargs signature).

    Attributes:
        story_id: Primary key for the storybook row and stamped onto the blob.
        blob: The validated Storybook JSON as a dict.
        family_id: Owning family (the ownership boundary).
        created_by: Optional authoring user id.
        model: Optional model identifier recorded on the version.
        prompt_version: Optional prompt/skill version recorded on the version.
        validation_report: Optional gate report stored on the version.
        status: Storybook lifecycle status (default ``"draft"``).
        version: Version number (default 1).
    """

    story_id: str
    blob: dict[str, object]
    family_id: uuid.UUID
    created_by: uuid.UUID | None = None
    model: str | None = None
    prompt_version: str | None = None
    validation_report: dict[str, object] | None = None
    status: str = "draft"
    version: int = _FIRST_VERSION


async def persist_storybook(session: AsyncSession, params: StorybookParams) -> str:
    """Create a ``Storybook`` row and its first ``StorybookVersion``.

    The blob's ``id`` is stamped to ``params.story_id`` so the stored content's id
    always matches its DB primary key. Flushes after each insert so the FK ordering
    holds; the caller commits.

    Args:
        session: An open async session; the caller owns the transaction.
        params: The grouped storybook inputs (see :class:`StorybookParams`).

    Returns:
        The ``story_id`` that was persisted.
    """
    # #CRITICAL: data-integrity: the stored blob's id must equal its DB row id, or
    # the reader resolves a story by a key absent from the blob.
    # #VERIFY: test_persist_creates_storybook_and_version asserts blob["id"] == story_id.
    stamped = {**params.blob, "id": params.story_id}

    storybook_row = Storybook(
        id=params.story_id,
        family_id=params.family_id,
        status=params.status,
        created_by=params.created_by,
    )
    session.add(storybook_row)
    await session.flush()  # ensure PK exists before the version FK

    version_row = StorybookVersion(
        storybook_id=params.story_id,
        version=params.version,
        blob=stamped,
        validation_report=params.validation_report,
        model=params.model,
        prompt_version=params.prompt_version,
    )
    session.add(version_row)
    await session.flush()

    return params.story_id
