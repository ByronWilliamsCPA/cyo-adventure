"""Per-node leaf distance and the anti-template guard (diversity/leaf.py).

The most important deliverable of WS-0 Phase 1 (design doc section 3): the
anti-template guard that fails a dog-for-cat noun swap while passing two
genuinely re-authored fills of one skeleton.

Pure module: stdlib and ``cyo_adventure.storybook.models`` /
``cyo_adventure.core.exceptions`` only, plus sibling pure ``diversity``
modules. Never imports ``db``, ``generation``, or ``sqlalchemy``.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.normalize import (
    content_tokens,
    extract_entities,
    jaccard_distance,
    mask_tokens,
)
from cyo_adventure.diversity.report import AntiTemplateReport, AntiTemplateVerdict
from cyo_adventure.diversity.structure import structure_fingerprint

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from cyo_adventure.storybook.models import Storybook


@dataclass(frozen=True, slots=True)
class NodeLeafDistance:
    """Per-node leaf distance between two fills of one skeleton.

    Attributes:
        node_id: The shared node id.
        d_uni: Masked content-unigram Jaccard distance.
        d_big: All-token (including stopwords) bigram Jaccard distance.
        word_count_a: Word count of the first fill's body at this node.
        word_count_b: Word count of the second fill's body at this node.
    """

    node_id: str
    d_uni: float
    d_big: float
    word_count_a: int
    word_count_b: int


@dataclass(frozen=True, slots=True)
class LeafDistanceProfile:
    """The full per-node leaf distance profile for a same-tree fill pair.

    Attributes:
        nodes: Per-node distances, in the first fill's node order.
        entity_count: Size of the masked entity set used for this pair.
        mean_d_uni: Mean ``d_uni`` across ``nodes``.
        median_d_uni: Median ``d_uni`` across ``nodes``.
        p10_d_uni: 10th percentile of ``d_uni`` across ``nodes``.
        p25_d_uni: 25th percentile of ``d_uni`` across ``nodes``.
        min_d_uni: Minimum ``d_uni`` across ``nodes``.
        max_d_uni: Maximum ``d_uni`` across ``nodes``.
        mean_d_big: Mean ``d_big`` across ``nodes``.
    """

    nodes: tuple[NodeLeafDistance, ...]
    entity_count: int
    mean_d_uni: float
    median_d_uni: float
    p10_d_uni: float
    p25_d_uni: float
    min_d_uni: float
    max_d_uni: float
    mean_d_big: float


def _percentile(values: Sequence[float], quantile: float) -> float:
    """Return the linear-interpolation percentile of a value sequence.

    Args:
        values: The values to summarize (need not be sorted).
        quantile: The quantile to compute, in ``[0, 1]``.

    Returns:
        float: The interpolated percentile; ``0.0`` for an empty sequence.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * quantile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _bigrams(tokens: Sequence[str]) -> frozenset[str]:
    """Return the set of adjacent-token bigrams, joined as ``"w1 w2"``.

    Args:
        tokens: The full masked token list (all tokens, incl. stopwords).

    Returns:
        frozenset[str]: Every distinct consecutive-pair bigram.
    """
    return frozenset(f"{first} {second}" for first, second in pairwise(tokens))


def leaf_distance_profile(
    fill_a: Storybook,
    fill_b: Storybook,
    brief_a: Mapping[str, object] | None = None,
    brief_b: Mapping[str, object] | None = None,
) -> LeafDistanceProfile:
    """Compute the per-node leaf distance profile between two fills.

    Args:
        fill_a: The first fill.
        fill_b: The second fill (normally, but not necessarily, of the same
            skeleton as ``fill_a``; only nodes with matching ids are
            compared).
        brief_a: The first fill's theme brief, if available.
        brief_b: The second fill's theme brief, if available.

    Returns:
        LeafDistanceProfile: Per-node ``(d_uni, d_big)`` plus summary
            statistics over ``d_uni`` and ``d_big``. Both distances are
            ``0.0`` for a node whose bodies are both empty (WS-0 design doc
            section 2.2).
    """
    entities = extract_entities(fill_a, brief_a) | extract_entities(fill_b, brief_b)
    bodies_a = {node.id: node.body for node in fill_a.nodes}
    bodies_b = {node.id: node.body for node in fill_b.nodes}
    shared_ids = [node_id for node_id in bodies_a if node_id in bodies_b]

    nodes: list[NodeLeafDistance] = []
    for node_id in shared_ids:
        masked_a = mask_tokens(bodies_a[node_id], entities)
        masked_b = mask_tokens(bodies_b[node_id], entities)
        uni_a = frozenset(content_tokens(masked_a))
        uni_b = frozenset(content_tokens(masked_b))
        nodes.append(
            NodeLeafDistance(
                node_id=node_id,
                d_uni=jaccard_distance(uni_a, uni_b),
                d_big=jaccard_distance(_bigrams(masked_a), _bigrams(masked_b)),
                word_count_a=len(bodies_a[node_id].split()),
                word_count_b=len(bodies_b[node_id].split()),
            )
        )

    d_uni_values = [node.d_uni for node in nodes]
    d_big_values = [node.d_big for node in nodes]
    return LeafDistanceProfile(
        nodes=tuple(nodes),
        entity_count=len(entities),
        mean_d_uni=statistics.fmean(d_uni_values) if d_uni_values else 0.0,
        median_d_uni=statistics.median(d_uni_values) if d_uni_values else 0.0,
        p10_d_uni=_percentile(d_uni_values, 0.10),
        p25_d_uni=_percentile(d_uni_values, 0.25),
        min_d_uni=min(d_uni_values) if d_uni_values else 0.0,
        max_d_uni=max(d_uni_values) if d_uni_values else 0.0,
        mean_d_big=statistics.fmean(d_big_values) if d_big_values else 0.0,
    )


@dataclass(frozen=True, slots=True)
class AntiTemplateThresholds:
    """Verdict boundaries for the anti-template guard (WS-0 section 3.2/3.5).

    Attributes:
        fail_median: Median ``d_uni`` below this value is FAIL.
        fail_p25: p25 ``d_uni`` below this value is FAIL.
        pass_median: Median ``d_uni`` at/above this value (with ``pass_p25``
            also met) is PASS.
        pass_p25: p25 ``d_uni`` at/above this value (with ``pass_median``
            also met) is PASS.
        node_flag_floor: Per-node ``d_uni`` below this value flags the node
            in ``templated_nodes``, regardless of overall verdict.
    """

    fail_median: float = 0.40
    fail_p25: float = 0.30
    pass_median: float = 0.60
    pass_p25: float = 0.45
    node_flag_floor: float = 0.30


# Per-band threshold overrides (WS-0 design doc section 3.5). Empty until a
# band has panel data (a WS-1 task); every band falls back to the
# section-3.2 default via _thresholds_for_band until then.
_BAND_THRESHOLDS: dict[str, AntiTemplateThresholds] = {}


def _thresholds_for_band(band: str) -> AntiTemplateThresholds:
    """Return the anti-template thresholds for an age band.

    Args:
        band: The story's ``metadata.age_band`` value.

    Returns:
        AntiTemplateThresholds: The band's override if one has been
            calibrated in :data:`_BAND_THRESHOLDS`, else the section-3.2
            default.
    """
    return _BAND_THRESHOLDS.get(band, AntiTemplateThresholds())


def anti_template_verdict(
    fill_a: Storybook,
    fill_b: Storybook,
    *,
    brief_a: Mapping[str, object] | None = None,
    brief_b: Mapping[str, object] | None = None,
    thresholds: AntiTemplateThresholds | None = None,
) -> AntiTemplateReport:
    """Judge whether two fills of one tree are genuinely different leaves.

    Args:
        fill_a: The first fill.
        fill_b: The second fill; must share ``fill_a``'s structure
            fingerprint (the guard is only defined for same-tree pairs).
        brief_a: The first fill's theme brief, if available.
        brief_b: The second fill's theme brief, if available.
        thresholds: An explicit per-band threshold override; defaults to
            ``fill_a``'s age band via :func:`_thresholds_for_band`.

    Returns:
        AntiTemplateReport: The verdict (PASS/WARN/FAIL per WS-0 design doc
            section 3.2), the ``d_uni`` distribution summary, and the
            flagged ``templated_nodes``.

    Raises:
        ValidationError: If the two fills do not share a structure
            fingerprint (the guard is only defined for same-tree pairs).
    """
    fingerprint_a = structure_fingerprint(fill_a)
    fingerprint_b = structure_fingerprint(fill_b)
    if fingerprint_a != fingerprint_b:
        msg = (
            "anti_template_verdict requires two fills of the same structure "
            "(cross-tree pairs are not comparable node-by-node)"
        )
        raise ValidationError(
            msg,
            field="structure_fingerprint",
            value=f"{fingerprint_a} != {fingerprint_b}",
        )

    profile = leaf_distance_profile(fill_a, fill_b, brief_a, brief_b)
    band_thresholds = thresholds or _thresholds_for_band(fill_a.metadata.age_band.value)

    if (
        profile.median_d_uni < band_thresholds.fail_median
        or profile.p25_d_uni < band_thresholds.fail_p25
    ):
        verdict = AntiTemplateVerdict.FAIL
    elif (
        profile.median_d_uni >= band_thresholds.pass_median
        and profile.p25_d_uni >= band_thresholds.pass_p25
    ):
        verdict = AntiTemplateVerdict.PASS_
    else:
        verdict = AntiTemplateVerdict.WARN

    templated_nodes = tuple(
        node.node_id
        for node in profile.nodes
        if node.d_uni < band_thresholds.node_flag_floor
    )
    return AntiTemplateReport(
        verdict=verdict,
        median_distance=profile.median_d_uni,
        p25_distance=profile.p25_d_uni,
        p10_distance=profile.p10_d_uni,
        mean_bigram_distance=profile.mean_d_big,
        entity_count=profile.entity_count,
        templated_nodes=templated_nodes,
        node_count=len(profile.nodes),
    )
