"""Request-time similarity query: pure score_history + async composition.

The WS-4 interface (WS-0 design doc section 5): the escalation ladder
(TREE -> LEAF -> CATALOG) made computable from ``(brief, history, cell)``,
plus the ATG comparison-partner helper WS-1 will call (supervisor
Adjustment 2).

``similarity_context`` is the only function here that touches a database
(via ``history.load_family_history``), and it does so by calling into
``history.py`` rather than importing SQLAlchemy directly. ``score_history``
itself is pure and takes ``cell_slugs`` as a plain parameter -- the caller
passes ``generation.skeleton_match.candidates_for_cell(...)`` in -- so this
module never imports ``generation`` (WS-0 design doc section 1.1 import
rule; also never imports ``db``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from cyo_adventure.diversity.history import HistoryEntry, load_family_history
from cyo_adventure.diversity.normalize import jaccard_similarity, theme_signature

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

# StoryNeighbor list cap (WS-0 design doc section 5.1).
_MAX_NEIGHBORS = 10

# tau_theme: a prior, not a fitted constant (WS-0 design doc section 5.3).
_DEFAULT_THEME_THRESHOLD = 0.35


@dataclass(frozen=True, slots=True)
class StoryNeighbor:
    """One prior story scored against a request's theme signature.

    Attributes:
        storybook_id: The prior story's id.
        version: The specific version authored.
        skeleton_slug: The skeleton it was filled from, or None.
        theme_similarity: Jaccard similarity vs the request's theme
            signature.
    """

    storybook_id: str
    version: int
    skeleton_slug: str | None
    theme_similarity: float


class DifferentiationLevel(StrEnum):
    """The escalation ladder WS-4's selector consumes (WS-0 section 5.3)."""

    TREE = "tree"
    LEAF = "leaf"
    CATALOG = "catalog"


@dataclass(frozen=True, slots=True)
class SimilarityContext:
    """The full request-time similarity picture for one authoring plan.

    Attributes:
        neighbors: Prior stories, sorted by ``theme_similarity`` descending,
            capped at :data:`_MAX_NEIGHBORS`.
        cell_theme_saturation: Fraction of the cell's candidate skeletons
            already used for a similar-theme story, in ``[0, 1]``.
        used_slugs: Skeleton slugs (within the cell) already used for a
            similar-theme story; advisory de-weighting input for WS-4 --
            never a zero-weight instruction (the novelty-floor invariant is
            WS-4's obligation, not this contract's).
        similar_count_per_slug: Count of similar-theme history entries per
            cell candidate slug (0 for a candidate with none).
        recommendation: The computed escalation level.
    """

    neighbors: tuple[StoryNeighbor, ...]
    cell_theme_saturation: float
    used_slugs: frozenset[str]
    similar_count_per_slug: Mapping[str, int]
    recommendation: DifferentiationLevel


def score_history(
    *,
    request_theme_sig: frozenset[str],
    history: Sequence[HistoryEntry],
    cell_slugs: Sequence[str],
    theme_threshold: float = _DEFAULT_THEME_THRESHOLD,
) -> SimilarityContext:
    """Score a family's history against a request's theme signature.

    A deterministic, pure function of its three inputs (WS-0 design doc
    section 5.3): no I/O, hand-buildable ``HistoryEntry`` sequences are
    fully sufficient to exercise every branch.

    Args:
        request_theme_sig: The incoming request's theme signature (from
            :func:`~cyo_adventure.diversity.normalize.theme_signature`).
        history: The family's recent history (from
            :func:`~cyo_adventure.diversity.history.load_family_history`),
            in any order.
        cell_slugs: The request's cell candidate slugs (from
            ``generation.skeleton_match.candidates_for_cell``), passed in
            by the caller so this module never imports ``generation``.
        theme_threshold: The ``tau_theme`` similarity floor above which a
            history entry counts as "similar" to the request.

    Returns:
        SimilarityContext: Neighbors, saturation, used slugs, per-slug
            similar counts, and the escalation recommendation. When
            ``cell_slugs`` is empty, ``cell_theme_saturation`` is ``1.0``
            (WS-0 design doc section 5.3: nothing to pick anyway).
    """
    scored = [
        (entry, jaccard_similarity(request_theme_sig, entry.theme_sig))
        for entry in history
    ]
    ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)
    neighbors = tuple(
        StoryNeighbor(
            storybook_id=entry.storybook_id,
            version=entry.version,
            skeleton_slug=entry.skeleton_slug,
            theme_similarity=similarity,
        )
        for entry, similarity in ranked[:_MAX_NEIGHBORS]
    )

    similar_entries = [
        entry for entry, similarity in scored if similarity >= theme_threshold
    ]
    cell_slug_set = frozenset(cell_slugs)
    used_slugs = frozenset(
        entry.skeleton_slug
        for entry in similar_entries
        if entry.skeleton_slug is not None and entry.skeleton_slug in cell_slug_set
    )
    similar_count_per_slug = {
        slug: sum(1 for entry in similar_entries if entry.skeleton_slug == slug)
        for slug in cell_slugs
    }
    cell_theme_saturation = (
        len(used_slugs) / len(cell_slug_set) if cell_slug_set else 1.0
    )
    max_similar_count = max(similar_count_per_slug.values(), default=0)

    if cell_theme_saturation < 1.0:
        recommendation = DifferentiationLevel.TREE
    elif max_similar_count < 2:
        recommendation = DifferentiationLevel.LEAF
    else:
        recommendation = DifferentiationLevel.CATALOG

    return SimilarityContext(
        neighbors=neighbors,
        cell_theme_saturation=cell_theme_saturation,
        used_slugs=used_slugs,
        similar_count_per_slug=similar_count_per_slug,
        recommendation=recommendation,
    )


async def similarity_context(
    session: AsyncSession,
    *,
    family_id: uuid.UUID | None,
    brief: Mapping[str, object],
    cell_slugs: Sequence[str],
) -> SimilarityContext:
    """Compose ``load_family_history`` + ``score_history`` for one request.

    The thin async wrapper WS-4 actually calls from
    ``story_requests/authoring_plan.py`` (WS-0 design doc section 5.2). It
    deliberately takes ``cell_slugs`` as a parameter rather than calling
    ``generation.skeleton_match.candidates_for_cell`` itself, keeping
    ``diversity`` import-free of ``generation``.

    Args:
        session: An open async session.
        family_id: The requesting family, or None for a family-less
            (admin/catalog) request.
        brief: The request's ``ConceptBrief`` dump.
        cell_slugs: The request's cell candidate slugs, computed by the
            caller.

    Returns:
        SimilarityContext: The composed request-time similarity picture.
    """
    history = await load_family_history(session, family_id)
    request_theme_sig = theme_signature(brief)
    return score_history(
        request_theme_sig=request_theme_sig,
        history=history,
        cell_slugs=cell_slugs,
    )


def select_atg_comparison_partner(
    skeleton_slug: str | None, history: Sequence[HistoryEntry]
) -> HistoryEntry | None:
    """Select the nearest prior same-skeleton fill to ATG-compare against.

    The anti-template guard is a second-use, pairwise check; this answers
    "compare against which prior fill" (supervisor Adjustment 2), leaving
    it to WS-1 to fetch that entry's actual blob and call
    ``leaf.anti_template_verdict``.

    Args:
        skeleton_slug: The new fill's skeleton slug, or None for a
            fresh_generation fill (which has no tree to compare against).
        history: The family's recent history, in any order.

    Returns:
        HistoryEntry | None: The most recent prior entry sharing
            ``skeleton_slug``, or None when there is no such entry (first
            use of a tree: the guard is a no-op) or ``skeleton_slug`` is
            None.
    """
    if skeleton_slug is None:
        return None
    same_tree = [entry for entry in history if entry.skeleton_slug == skeleton_slug]
    if not same_tree:
        return None
    return max(same_tree, key=lambda entry: entry.created_at)
