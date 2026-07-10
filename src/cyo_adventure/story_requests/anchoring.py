"""Anchor validation and soft-continuation context for series requests (WS-B PR 3).

``resolve_anchor`` is the single seam every continuation entry point uses (kid
create, authored create, and approve re-validation), so the published/family/
series/band rules cannot drift apart between paths. ``load_anchor_context``
feeds the concept brief; extraction is deterministic (no LLM call).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import (
    Concept,
    GenerationJob,
    Series,
    Storybook,
    StorybookVersion,
)
from cyo_adventure.generation.concept import AnchorContext
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

_MAX_ENDING_EXCERPTS = 3
_EXCERPT_CHARS = 150
_SUMMARY_CHARS = 600
_TITLE_CHARS = 200
_MAX_CHARACTER_NAMES = 5
_MAX_VARIABLE_NAMES = 10
_VARIABLE_NAME_CHARS = 200  # matches concept._BoundedText's max_length


async def resolve_anchor(
    session: AsyncSession,
    anchor_storybook_id: str,
    *,
    family_id: uuid.UUID,
    expected_band: str,
) -> Series:
    """Validate a continuation anchor and return its series.

    Args:
        session: The request session.
        anchor_storybook_id: The storybook named as the continuation anchor.
        family_id: The resolved target family of the request being created or
            approved; the anchor must belong to it.
        expected_band: The band the request targets; must equal the series
            band (continuations inherit the series band, never fork it).

    Returns:
        Series: The anchor's series row.

    Raises:
        ResourceNotFoundError: Missing anchor or outside the family (-> 404,
            existence hiding, mirroring _load_scoped_request).
        ValidationError: Anchor not published, not series-linked, or band
            mismatch (-> 422).
    """
    storybook = await session.get(Storybook, anchor_storybook_id)
    # #CRITICAL: security: 404-over-403 for an anchor outside the caller's
    # family, so this endpoint cannot be used to probe other families' books.
    # #VERIFY: test_series_requests.py::test_kid_anchor_cross_family_is_404.
    if storybook is None or storybook.family_id != family_id:
        msg = f"storybook '{anchor_storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    version = None
    if storybook.current_published_version is not None:
        version = await session.scalar(
            select(StorybookVersion).where(
                StorybookVersion.storybook_id == storybook.id,
                StorybookVersion.version == storybook.current_published_version,
            )
        )
    # Mirrors the kid-library visibility filter (api/library.py): published
    # status, a current published version, and an approved version row.
    if (
        storybook.status != "published"
        or version is None
        or version.approved_by is None
    ):
        msg = "anchor storybook is not published"
        raise ValidationError(
            msg, field="anchor_storybook_id", value=anchor_storybook_id
        )
    if storybook.series_id is None:
        msg = "anchor storybook is not part of a series"
        raise ValidationError(
            msg, field="anchor_storybook_id", value=anchor_storybook_id
        )
    series = await session.get(Series, storybook.series_id)
    if series is None:
        msg = "series not found"
        raise ResourceNotFoundError(msg)
    if series.age_band != expected_band:
        msg = "request age band does not match the series band"
        raise ValidationError(msg, field="age_band", value=expected_band)
    return series


async def load_anchor_context(
    session: AsyncSession, anchor_storybook_id: str
) -> AnchorContext | None:
    """Extract the soft-continuation context from a validated anchor.

    Defensive by design: the anchor was validated at creation and approval,
    but this runs later (inside _build_concept) and degrades to None or to
    partial context rather than failing the approve on a malformed blob.
    """
    # #ASSUME: data integrity: the anchor storybook was validated (published,
    # series-linked, band-matched) at creation and re-validated at approval,
    # but this read runs later and the stored blob has no DB-level shape
    # constraint, so every field is re-checked here and degrades to None or a
    # partial AnchorContext rather than raising on a malformed blob.
    # #VERIFY: tests/unit/test_anchoring.py::test_malformed_blob_degrades_to_defaults.
    storybook = await session.get(Storybook, anchor_storybook_id)
    if storybook is None or storybook.current_published_version is None:
        logger.warning(
            "anchor.context_unavailable",
            anchor_storybook_id=anchor_storybook_id,
            reason="missing_or_unpublished",
        )
        return None
    version = await session.scalar(
        select(StorybookVersion).where(
            StorybookVersion.storybook_id == storybook.id,
            StorybookVersion.version == storybook.current_published_version,
        )
    )
    if version is None or not isinstance(version.blob, dict):
        # A validated anchor with no usable blob is a silent quality regression:
        # the continuation generates with no reference to the prior book. Log it
        # so the degradation is observable rather than invisible.
        logger.warning(
            "anchor.context_unavailable",
            anchor_storybook_id=anchor_storybook_id,
            reason="missing_or_malformed_blob",
        )
        return None
    names = await _protagonist_names(session, anchor_storybook_id)
    return anchor_context_from_blob(version.blob, character_names=names)


async def _protagonist_names(session: AsyncSession, storybook_id: str) -> list[str]:
    """Recover the anchor's protagonist name via its GenerationJob's concept.

    The document blob carries no character list; the protagonist lives on the
    concept brief the anchor was generated from. Empty on any missing link.
    """
    # #ASSUME: data integrity: the concept brief is an application-defined
    # JSONB blob with no DB-level schema constraint, so a missing or
    # wrong-typed "protagonist"/"name" key must degrade to an empty list
    # rather than raise.
    # #VERIFY: each defensive branch below (brief not a dict, protagonist not a
    # dict, name not a non-empty str) returns [] in-line. This is distinct from
    # anchor_context_from_blob, which caps an already-built character_names list;
    # these branches are not yet exercised by a dedicated unit test (follow-up).
    # #EDGE: data integrity: one storybook can in principle have more than one
    # GenerationJob row; ordering by created_at makes the pick deterministic
    # (oldest first) if that ever happens, though one job per storybook is the
    # current convention.
    brief = await session.scalar(
        select(Concept.brief)
        .join(GenerationJob, GenerationJob.concept_id == Concept.id)
        .where(GenerationJob.storybook_id == storybook_id)
        .order_by(GenerationJob.created_at)
        .limit(1)
    )
    if not isinstance(brief, dict):
        return []
    protagonist = brief.get("protagonist")
    if not isinstance(protagonist, dict):
        return []
    name = protagonist.get("name")
    if isinstance(name, str) and name:
        return [name]
    return []


def _variable_names_from_blob(blob: Mapping[str, object]) -> list[str]:
    """Collect declared variable names from a blob's ``variables`` array.

    Same defensive contract as the rest of this module: a malformed entry is
    skipped, an overlong name is truncated, nothing raises.
    """
    names: list[str] = []
    variables = blob.get("variables")
    if not isinstance(variables, list):
        return names
    for variable in variables:
        if len(names) >= _MAX_VARIABLE_NAMES:
            break
        if not isinstance(variable, dict):
            continue
        name = variable.get("name")
        if isinstance(name, str) and name:
            names.append(name[:_VARIABLE_NAME_CHARS])
    return names


def anchor_context_from_blob(
    blob: Mapping[str, object], *, character_names: list[str]
) -> AnchorContext:
    """Build an AnchorContext from a stored Storybook blob (pure function).

    Every field is read defensively (mirroring api/library.py::_library_item):
    a malformed value degrades to a safe default rather than raising.
    """
    title = blob.get("title")
    safe_title = title if isinstance(title, str) and title else "Untitled story"
    excerpts: list[str] = []
    nodes = blob.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if len(excerpts) >= _MAX_ENDING_EXCERPTS:
                break
            if not isinstance(node, dict) or not node.get("is_ending"):
                continue
            ending = node.get("ending")
            label = ending.get("title") if isinstance(ending, dict) else None
            body = node.get("body")
            body_text = body if isinstance(body, str) else ""
            piece = (
                f"{label}: {body_text}"
                if isinstance(label, str) and label
                else body_text
            )
            if piece:
                excerpts.append(piece[:_EXCERPT_CHARS])
    summary = " | ".join(excerpts)[:_SUMMARY_CHARS]
    return AnchorContext(
        title=safe_title[:_TITLE_CHARS],
        character_names=character_names[:_MAX_CHARACTER_NAMES],
        ending_summary=summary,
        variable_names=_variable_names_from_blob(blob),
    )
