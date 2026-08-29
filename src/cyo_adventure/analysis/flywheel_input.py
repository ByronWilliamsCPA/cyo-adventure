"""Derive a flywheel candidate-strategy input from the ADR-030 artifact.

The flywheel's candidate strategy currently triggers on request-side saturation
only: nothing it does is a function of whether real readers finish a book. This
module closes that loop at the seam the strategy already declares for it,
:func:`~cyo_adventure.flywheel.strategy.eligible_parents`'s
``excluded_parent_slugs``, whose docstring names it as the design's injection
point with the caller supplying the real set at run time.

**Why exclusion and not ranking.** The other available seam is
``compute_candidate_metrics`` -> ``CandidateMetrics`` -> ``ranking_key``. Three
reasons this one was taken instead. Exclusion is already a caller-supplied set,
so nothing in ``strategy.py`` changes and the flywheel stays pure over catalog
files; a ranking input would mean widening a frozen four-field dataclass and
re-stating the design's 6.4 precedence, which is a change to a settled contract
rather than a use of a provided one. Exclusion is provable by a test as a
membership fact, where a ranking change is provable only as an ordering, and
ordering is entangled with the tie-breaks and the empty-cohort ``inf`` case.
And exclusion is the conservative direction: it can only stop a shell being
mutated. A ranking input would let this artifact *promote* a shell, giving an
aggregate over children's reading a positive say in what gets built, which is a
larger blast radius for a job whose governing ADR is still ``proposed``.

**The join key, and why it is a parameter.** The flywheel keys on skeleton
slugs; the artifact keys on ``storybook.id``. The bridge is
``storybook_version.skeleton_slug``, which ADR-030 Decision 4 does not
allowlist, so the job may not read it and the artifact may not carry it. The map
is therefore an argument, exactly as ``excluded_parent_slugs`` itself is an
argument to the strategy: this module derives behaviour from the artifact and
takes the identity mapping from its caller. Widening the allowlists to carry the
slug is an ADR-030 amendment (Decision 10), not a code change.

**A suppressed cell is never treated as low.** A completion rate the job
suppressed means *unknown*, and a book whose engagement is unknown is not
evidence against its parent shell. Reading the marker as a low rate would turn
a privacy control into a silent behaviour change in the catalog.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cyo_adventure.analysis.engagement_correlation import SUPPRESSION_MARKER

if TYPE_CHECKING:
    from collections.abc import Mapping

# #ASSUME: data-integrity: a published book whose completion rate is at or below
# this is evidence its parent shell is not worth mutating again. Derived from
# nothing measured (ADR-030 Decision 1 records that no reader distribution is
# observable yet); it is a starting value that a reviewed PR changes, matching
# the flywheel's other design-8.2 constants which have no runtime override path.
# #VERIFY: tests/unit/test_engagement_correlation_flywheel_input.py::
# TestExclusionDerivation::test_a_low_completion_row_excludes_its_parent_slug.
LOW_COMPLETION_CEILING: Final = 0.35


def _rows(artifact: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return the artifact's rows, dropping anything of an unexpected shape.

    Reader-side validation rather than trust: the artifact is a file on disk and
    a malformed document must degrade to "no exclusions", never to an exception
    inside a catalog-growth run.

    Args:
        artifact: The parsed artifact document.

    Returns:
        list: The well-formed rows.
    """
    raw = artifact.get("rows")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]  # pyright: ignore[reportUnknownVariableType]


def low_completion_storybook_ids(
    artifact: Mapping[str, object],
    *,
    ceiling: float = LOW_COMPLETION_CEILING,
) -> frozenset[str]:
    """Return the storybook ids whose published completion rate is at or below.

    A row whose ``completion_rate`` is the suppression marker contributes
    nothing: the marker means unknown, and unknown is not low.

    Args:
        artifact: The parsed artifact document.
        ceiling: The inclusive completion-rate ceiling.

    Returns:
        frozenset[str]: The matching storybook ids.
    """
    matched: set[str] = set()
    for row in _rows(artifact):
        storybook_id = row.get("storybook_id")
        rate = row.get("completion_rate")
        if not isinstance(storybook_id, str):
            continue
        if rate == SUPPRESSION_MARKER or isinstance(rate, bool):
            continue
        if isinstance(rate, (int, float)) and rate <= ceiling:
            matched.add(storybook_id)
    return frozenset(matched)


def excluded_parent_slugs(
    artifact: Mapping[str, object],
    slug_by_storybook_id: Mapping[str, str],
    *,
    ceiling: float = LOW_COMPLETION_CEILING,
) -> frozenset[str]:
    """Return the skeleton slugs to withhold from the flywheel's parent pool.

    The returned set is passed straight to
    :func:`~cyo_adventure.flywheel.strategy.eligible_parents` (or through
    :func:`~cyo_adventure.flywheel.strategy.plan_attempts`) as
    ``excluded_parent_slugs``, where it unions with the open-PR exclusions the
    caller already supplies.

    Args:
        artifact: The parsed artifact document.
        slug_by_storybook_id: The storybook-to-skeleton-slug map, supplied by the
            caller because ADR-030 Decision 4 does not allowlist
            ``storybook_version.skeleton_slug`` for this job to read.
        ceiling: The inclusive completion-rate ceiling.

    Returns:
        frozenset[str]: The slugs to exclude; empty when nothing qualifies.
    """
    ids = low_completion_storybook_ids(artifact, ceiling=ceiling)
    return frozenset(
        slug
        for storybook_id, slug in slug_by_storybook_id.items()
        if storybook_id in ids
    )
