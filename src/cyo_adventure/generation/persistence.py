"""Reusable persistence for a validated Storybook blob.

Extracted from the generation worker so both the worker and the offline
authoring-import path create ``storybook`` and ``storybook_version`` rows
identically. The caller owns the transaction (this helper flushes but does not
commit), matching the worker's unit-of-work contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Storybook, StorybookVersion

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

_FIRST_VERSION = 1

# Byte ceiling for the stored blob and validation_report JSONB columns (audit
# Finding 12). Neither has a natural structural size cap (a story blob's node
# count is bounded elsewhere, but total serialized size also depends on prose
# length; a validation_report's finding count is data-dependent), so this is a
# flat resource-exhaustion backstop rather than a value derived from story
# structure: 2,000,000 bytes (2 MB) comfortably exceeds any real story or
# report while still bounding a pathological or malicious multi-megabyte blob.
_MAX_BLOB_BYTES = 2_000_000


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

    Raises:
        ValidationError: If the stamped blob or the validation report
            serializes to more than ``_MAX_BLOB_BYTES`` (audit Finding 12).
    """
    # #CRITICAL: data-integrity: the stored blob's id must equal its DB row id, or
    # the reader resolves a story by a key absent from the blob.
    # #VERIFY: test_persist_creates_storybook_and_version asserts blob["id"] == story_id.
    stamped = {**params.blob, "id": params.story_id}

    # #CRITICAL: security: guard both JSONB payloads BEFORE any row is added,
    # so an oversized blob or report never partially persists (Storybook row
    # created, StorybookVersion rejected) and never reaches the database as an
    # unbounded write.
    # #VERIFY: test_persist_rejects_oversized_blob and
    # test_persist_rejects_oversized_validation_report assert session.added
    # stays empty; the ``_at_byte_limit_accepted`` counterparts assert the
    # boundary itself still passes.
    _check_byte_budget(stamped, field="blob")
    if params.validation_report is not None:
        _check_byte_budget(params.validation_report, field="validation_report")

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


def _check_byte_budget(payload: dict[str, object], *, field: str) -> None:
    """Raise ``ValidationError`` when ``payload``'s serialized size is too large.

    Args:
        payload: The JSONB-bound dict to size-check (the stamped blob, or the
            validation report).
        field: The field name to attach to the raised error for context.

    Raises:
        ValidationError: If ``len(json.dumps(payload))`` exceeds
            ``_MAX_BLOB_BYTES``.
    """
    size = len(json.dumps(payload))
    if size > _MAX_BLOB_BYTES:
        msg = f"{field} serialized size {size} exceeds the {_MAX_BLOB_BYTES}-byte limit"
        raise ValidationError(msg, field=field)
