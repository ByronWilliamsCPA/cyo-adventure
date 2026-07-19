"""ECS, the PS pair score, and repeat-adventure rate (trend-only metrics).

WS-0 Phase 2 (design doc section 3.1). ``effective_catalog_size`` is the
exponentiated-entropy catalog-diversity number; ``pair_score``/``PairScore``
is the offline PS proxy for "would a reader perceive these two stories as
the same adventure"; ``repeat_adventure_rate`` folds PS over a chronological
sequence. None of these ever gates CI (WS-0 design doc section 2.3's "never"
list); they are recorded and reported only, pending the Phase 3 judge
calibration (section 5).

Pure module: stdlib plus sibling pure ``diversity`` modules and
``cyo_adventure.storybook.models`` only. Never imports ``db``,
``generation``, or ``sqlalchemy``.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypeVar

from cyo_adventure.diversity.leaf import leaf_distance_profile
from cyo_adventure.diversity.normalize import (
    coerce_storybook,
    content_tokens,
    extract_entities,
    jaccard_similarity,
    mask_tokens,
    theme_signature,
)
from cyo_adventure.diversity.structure import structural_distance, structure_fingerprint

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from cyo_adventure.storybook.models import Storybook

# Declared priors (WS-0 design doc section 2.8): revisited only via the
# Phase 3 calibration PR (design doc section 5.3), never auto-loaded from
# calibration.json at runtime.
_PS_WEIGHT_LEAF: Final[float] = 0.50
_PS_WEIGHT_STRUCT: Final[float] = 0.30
_PS_WEIGHT_THEME: Final[float] = 0.20
REPEAT_THRESHOLD: Final[float] = 0.70

T = TypeVar("T")


def effective_catalog_size(rows: Iterable[T], key: Callable[[T], str]) -> float:
    """Return the exponentiated Shannon entropy of a key-partition.

    Args:
        rows: The population to partition (e.g. served-window storybook
            rows).
        key: Maps one row to its partition key. The caller owns the
            partition: for served-window ECS the key is ``skeleton_slug``
            with NULL-slug rows mapped to a per-storybook pseudo-slug (WS-0
            design doc section 2.7); a future (tree, leaf-cluster) unit
            changes only this function.

    Returns:
        float: ``exp(-sum(p * ln(p)))`` over the key distribution. ``0.0``
            for zero rows, ``1.0`` for a population with a single key.
    """
    counts = Counter(key(row) for row in rows)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = -sum(
        (count / total) * math.log(count / total) for count in counts.values()
    )
    return math.exp(entropy)


@dataclass(frozen=True, slots=True)
class PairScore:
    """The WS-0 design doc section 2.8 offline PS proxy for one story pair.

    Attributes:
        leaf_similarity: ``1 - median D_uni`` for a same-tree pair, or
            cosine similarity over masked whole-story content tokens for a
            cross-tree pair.
        structural_similarity: ``1.0`` for a same-tree pair, else
            ``1 - min(structural_distance(a, b), 1.0)``.
        theme_similarity: Jaccard similarity of the two stories'
            :func:`~cyo_adventure.diversity.normalize.theme_signature`.
        perceived_similarity: The weighted sum, in ``[0, 1]``.
        same_tree: Which ``leaf_similarity``/``structural_similarity``
            branch was taken.
    """

    leaf_similarity: float
    structural_similarity: float
    theme_similarity: float
    perceived_similarity: float
    same_tree: bool


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    """Return the cosine similarity between two token-count vectors.

    Args:
        a: The first story's masked content-token counts.
        b: The second story's masked content-token counts.

    Returns:
        float: Cosine similarity in ``[0, 1]``; ``0.0`` when either vector
            is empty (an empty story shares no signal with anything, the
            same "empty is never similar" convention as
            :func:`~cyo_adventure.diversity.normalize.jaccard_similarity`).
    """
    if not a or not b:
        return 0.0
    dot = sum(count * b[token] for token, count in a.items() if token in b)
    norm_a = math.sqrt(sum(count * count for count in a.values()))
    norm_b = math.sqrt(sum(count * count for count in b.values()))
    # A vector norm is non-negative, so `<= 0.0` is the zero-norm guard without
    # a float-equality comparison (SonarQube python:S1244); the earlier
    # emptiness check already makes a zero norm unreachable here.
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _whole_story_token_counts(
    story: Storybook, entities: frozenset[str]
) -> Counter[str]:
    """Return masked content-token counts pooled over every node's leaf text.

    Args:
        story: The story to tokenize.
        entities: The entity mask to apply (see
            :func:`~cyo_adventure.diversity.normalize.mask_tokens`).

    Returns:
        Counter[str]: Content-token counts, pooled across all nodes' leaf
            text (body plus choice labels; same leaf definition as
            :func:`~cyo_adventure.diversity.leaf.leaf_distance_profile`, so
            the cross-tree cosine branch sees the same "leaf" the same-tree
            branch does).
    """
    counts: Counter[str] = Counter()
    for node in story.nodes:
        leaf_text = " ".join([node.body, *(choice.label for choice in node.choices)])
        counts.update(content_tokens(mask_tokens(leaf_text, entities)))
    return counts


def _cross_tree_leaf_similarity(
    a: Storybook,
    b: Storybook,
    brief_a: Mapping[str, object] | None,
    brief_b: Mapping[str, object] | None,
) -> float:
    """Return the cross-tree ``leaf_similarity`` branch of :func:`pair_score`.

    Cosine (not Jaccard) similarity over whole-story masked content-token
    counts: at story scale, two long unrelated stories' token *sets*
    converge, so counts carry the discriminating signal (WS-0 design doc
    section 3.1 internals note); this is the opposite regime from
    :func:`~cyo_adventure.diversity.leaf.leaf_distance_profile`'s per-node
    Jaccard, which stays set-based for explainability over ~90-word bodies.

    Args:
        a: The first story.
        b: The second story.
        brief_a: The first story's theme brief, if available.
        brief_b: The second story's theme brief, if available.

    Returns:
        float: Cosine similarity in ``[0, 1]``.
    """
    entities = extract_entities(a, brief_a) | extract_entities(b, brief_b)
    return _cosine(
        _whole_story_token_counts(a, entities), _whole_story_token_counts(b, entities)
    )


def pair_score(
    a: Storybook | Mapping[str, object],
    b: Storybook | Mapping[str, object],
    *,
    brief_a: Mapping[str, object] | None = None,
    brief_b: Mapping[str, object] | None = None,
) -> PairScore:
    """Compute the offline PS proxy for one story pair (WS-0 section 2.8).

    Same-fingerprint pair (two fills of one skeleton):
        ``leaf_sim = 1 - median D_uni`` (:func:`~cyo_adventure.diversity.
        leaf.leaf_distance_profile`); ``struct_sim = 1.0``.

    Cross-fingerprint pair:
        ``leaf_sim`` = cosine similarity over masked whole-story content
        tokens (entities = the union of both stories' declared/detected
        entities); ``struct_sim = 1 - min(structural_distance(a, b), 1.0)``.

    Always:
        ``theme_sim = jaccard_similarity(theme_signature(brief_a,
        a.metadata.themes), theme_signature(brief_b, b.metadata.themes))``.

    ``perceived_similarity = 0.50*leaf_sim + 0.30*struct_sim +
    0.20*theme_sim``.

    Args:
        a: The first story (a validated Storybook, or a raw blob to
            coerce).
        b: The second story.
        brief_a: The first story's theme brief, if available.
        brief_b: The second story's theme brief, if available.

    Returns:
        PairScore: The full breakdown plus the weighted score.
    """
    model_a = coerce_storybook(a)
    model_b = coerce_storybook(b)
    same_tree = structure_fingerprint(model_a) == structure_fingerprint(model_b)

    if same_tree:
        profile = leaf_distance_profile(model_a, model_b, brief_a, brief_b)
        leaf_sim = 1.0 - profile.median_d_uni
        struct_sim = 1.0
    else:
        leaf_sim = _cross_tree_leaf_similarity(model_a, model_b, brief_a, brief_b)
        struct_sim = 1.0 - min(structural_distance(model_a, model_b), 1.0)

    theme_sim = jaccard_similarity(
        theme_signature(brief_a, model_a.metadata.themes),
        theme_signature(brief_b, model_b.metadata.themes),
    )
    perceived = (
        _PS_WEIGHT_LEAF * leaf_sim
        + _PS_WEIGHT_STRUCT * struct_sim
        + _PS_WEIGHT_THEME * theme_sim
    )
    return PairScore(
        leaf_similarity=leaf_sim,
        structural_similarity=struct_sim,
        theme_similarity=theme_sim,
        perceived_similarity=perceived,
        same_tree=same_tree,
    )


def perceived_similarity(
    a: Storybook | Mapping[str, object],
    b: Storybook | Mapping[str, object],
    *,
    brief_a: Mapping[str, object] | None = None,
    brief_b: Mapping[str, object] | None = None,
) -> float:
    """Return just the weighted PS value for one story pair.

    Args:
        a: The first story.
        b: The second story.
        brief_a: The first story's theme brief, if available.
        brief_b: The second story's theme brief, if available.

    Returns:
        float: ``pair_score(a, b, brief_a=brief_a, brief_b=brief_b)
            .perceived_similarity``.
    """
    return pair_score(a, b, brief_a=brief_a, brief_b=brief_b).perceived_similarity


def repeat_adventure_rate(
    stories: Sequence[Storybook | Mapping[str, object]],
    *,
    briefs: Sequence[Mapping[str, object] | None] | None = None,
    threshold: float = REPEAT_THRESHOLD,
) -> float:
    """Return the fraction of a chronological sequence that "repeats" a prior story.

    Args:
        stories: A chronologically ordered sequence of stories (oldest
            first). Pure over an already-windowed sequence: the caller (a
            future dashboard loader, or the harness's ``rar_sequence``)
            applies any trailing-window slicing; this function never
            touches the database.
        briefs: Per-story theme briefs, aligned by index with ``stories``,
            or ``None`` to compare with no briefs for every story.
        threshold: The PS value at/above which story *i* counts as a
            "repeat" of some earlier story *j* < *i*.

    Returns:
        float: The count of stories ``i >= 1`` whose maximum PS against any
            earlier story in the sequence is ``>= threshold``, divided by
            ``len(stories) - 1``. ``0.0`` for fewer than two stories.
    """
    if len(stories) < 2:
        return 0.0
    brief_seq = briefs if briefs is not None else [None] * len(stories)
    repeats = 0
    for i in range(1, len(stories)):
        best = max(
            perceived_similarity(
                stories[i], stories[j], brief_a=brief_seq[i], brief_b=brief_seq[j]
            )
            for j in range(i)
        )
        if best >= threshold:
            repeats += 1
    return repeats / (len(stories) - 1)
