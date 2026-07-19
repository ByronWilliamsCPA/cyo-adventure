"""HistoryEntry and the family-history loader (diversity/history.py).

The ONLY impure ``diversity`` module (WS-0 design doc section 1.1): it
imports ``db.models`` and SQLAlchemy and is the single I/O boundary the rest
of the package stays free of. Mirrors the impure half of
``generation/skeleton_match.py`` (``recent_skeleton_usage``): read-only
queries, no writes, no caching.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from cyo_adventure.db.models import Concept, GenerationJob, Storybook, StorybookVersion
from cyo_adventure.diversity.normalize import theme_signature

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    # Row shape for the family-history query: the JSONB `blob`/`brief`
    # columns are not statically typed by the SQLAlchemy JSONB extension, so
    # the raw row is cast to this explicit tuple once, and every element is
    # narrowed defensively from there (``object``, never ``Any``).
    _HistoryRow = tuple[str, int, str | None, datetime, object, object]

# Matches generation.skeleton_match._RECENT_WINDOW (WS-0 design doc section
# 5.4: the two signals must not disagree about what "recent" means).
_DEFAULT_WINDOW = 20


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """One prior story of the family, reduced to what similarity needs.

    Attributes:
        storybook_id: The prior story's id.
        version: The specific version authored.
        skeleton_slug: The production skeleton it was filled from, or None
            for a fresh_generation/imported version.
        theme_sig: ``theme_signature()`` of its brief plus
            ``metadata.themes``.
        created_at: When this version was authored (drives recency
            ordering and the ATG nearest-partner selection in ``query.py``).
    """

    storybook_id: str
    version: int
    skeleton_slug: str | None
    theme_sig: frozenset[str]
    created_at: datetime


def _themes_from_blob(blob: object) -> list[str]:
    """Extract ``metadata.themes`` from a StorybookVersion blob, defensively.

    Args:
        blob: The version's ``blob`` column value (loosely-typed JSONB).

    Returns:
        list[str]: The declared themes; empty for a missing, wrong-typed,
            or malformed ``metadata``/``themes`` path.
    """
    if not isinstance(blob, Mapping):
        return []
    metadata = cast("Mapping[str, object]", blob).get("metadata")
    if not isinstance(metadata, Mapping):
        return []
    themes = cast("Mapping[str, object]", metadata).get("themes")
    if not isinstance(themes, list):
        return []
    return [theme for theme in cast("list[object]", themes) if isinstance(theme, str)]


def _brief_mapping(brief: object) -> Mapping[str, object] | None:
    """Return ``brief`` as a mapping, or None if it is not one.

    Args:
        brief: The joined ``Concept.brief`` value (may be None: no linked
            concept, or a JSONB value of the wrong shape).

    Returns:
        Mapping[str, object] | None: ``brief`` narrowed to a mapping, or
            None.
    """
    if not isinstance(brief, Mapping):
        return None
    return cast("Mapping[str, object]", brief)


async def load_family_history(
    session: AsyncSession,
    family_id: uuid.UUID | None,
    *,
    window: int = _DEFAULT_WINDOW,
) -> list[HistoryEntry]:
    """Return a family's recent story history, reduced to similarity inputs.

    Args:
        session: An open async session.
        family_id: The requesting family, or None for a family-less
            (admin/catalog) request.
        window: How many of the family's most recent
            ``storybook_version`` rows to load; matches
            ``skeleton_match._RECENT_WINDOW`` (both signals must agree on
            "recent").

    Returns:
        list[HistoryEntry]: Most-recent-first; empty when ``family_id`` is
            None or the family has no history.
    """
    # #ASSUME: external-resources: this issues a live database query; the
    # caller (WS-4's authoring_plan.py, via query.similarity_context) is
    # expected to hold an open async session, exactly like
    # generation.skeleton_match.recent_skeleton_usage.
    # #VERIFY: a session that is closed or out of a transaction context
    # raises before this function runs; no defensive re-open is attempted.
    if family_id is None:
        return []

    # #EDGE: data-integrity: a storybook can have more than one
    # GenerationJob row (retries); take the earliest by created_at, matching
    # story_requests/anchoring.py::_protagonist_names's convention. A scalar
    # subquery (rather than a plain LEFT JOIN on generation_job) avoids
    # fanning a single storybook_version row out into duplicates when more
    # than one job exists.
    first_job_concept_id = (
        select(GenerationJob.concept_id)
        .where(GenerationJob.storybook_id == StorybookVersion.storybook_id)
        .order_by(GenerationJob.created_at.asc())
        .limit(1)
        .correlate(StorybookVersion)
        .scalar_subquery()
    )
    stmt = (
        select(
            StorybookVersion.storybook_id,
            StorybookVersion.version,
            StorybookVersion.skeleton_slug,
            StorybookVersion.created_at,
            StorybookVersion.blob,
            Concept.brief,
        )
        .join(Storybook, Storybook.id == StorybookVersion.storybook_id)
        .outerjoin(Concept, Concept.id == first_job_concept_id)
        .where(Storybook.family_id == family_id)
        .order_by(StorybookVersion.created_at.desc())
        .limit(window)
    )
    result = await session.execute(stmt)

    # #ASSUME: data-integrity: ``blob`` and ``Concept.brief`` are
    # loosely-typed JSONB with no DB-level shape constraint; a row with a
    # missing or malformed themes array or brief degrades to an empty theme
    # signature for that entry (it simply never counts as "similar" in
    # query.score_history) rather than raising.
    # #VERIFY: test_diversity_history.py::test_malformed_blob_degrades_to_empty_signature.
    entries: list[HistoryEntry] = []
    rows = cast("Sequence[_HistoryRow]", result.all())
    for storybook_id, version, skeleton_slug, created_at, blob, brief in rows:
        entries.append(
            HistoryEntry(
                storybook_id=storybook_id,
                version=version,
                skeleton_slug=skeleton_slug,
                theme_sig=theme_signature(
                    _brief_mapping(brief), _themes_from_blob(blob)
                ),
                created_at=created_at,
            )
        )
    return entries


async def load_version_blob(
    session: AsyncSession,
    storybook_id: str,
    version: int,
) -> Mapping[str, object] | None:
    """Return one storybook version's blob, or None when the row is absent.

    The blob fetch WS-1's anti-template guard needs for its comparison
    partner (see diversity/query.py::select_atg_comparison_partner):
    HistoryEntry deliberately does not carry the blob, so the caller
    resolves a selected partner to its content with this single read.

    Args:
        session: An open async session (the caller owns the transaction).
        storybook_id: The partner story's id.
        version: The partner version number.

    Returns:
        The version's ``blob`` JSONB mapping, or ``None`` when no such row
        exists (deleted content, or a stale HistoryEntry).
    """
    # #ASSUME: external-resources: one read-only primary-key lookup on the
    # caller's session; a closed session raises before the query runs, exactly
    # like load_family_history above.
    # #VERIFY: tests/unit/test_diversity_history.py::test_load_version_blob_missing_row_returns_none.
    # #ASSUME: concurrency: StorybookVersion rows are immutable once written
    # (db/models.py: "An immutable version of a story"), so this read needs no
    # lock and cannot race the pipeline's FOR UPDATE on the *current* storybook.
    # #VERIFY: no with_for_update() here; the pipeline locks only its own row.
    # #EDGE: data-integrity: blob is loosely-typed JSONB; this loader does NOT
    # validate it. The caller must coerce (diversity.normalize.coerce_storybook)
    # and treat a validation failure as fail-open.
    # #VERIFY: moderation/leaf_diversity.py catches the coerce ValidationError.
    row = await session.get(StorybookVersion, (storybook_id, version))
    if row is None:
        return None
    return row.blob
