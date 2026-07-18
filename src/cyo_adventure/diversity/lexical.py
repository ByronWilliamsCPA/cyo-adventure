"""distinct-n and self-BLEU-lite lexical guard metrics (diversity/lexical.py).

WS-0 Phase 2 (design doc section 3.2). These are floors checked after the
fact against a committed baseline, never optimization targets, and never
exposed to ``generation`` (WS-0 design doc sections 2.6 and 7.2).

Pure module: stdlib plus sibling pure ``diversity`` modules and
``cyo_adventure.storybook.models`` only. Never imports ``db``,
``generation``, or ``sqlalchemy``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from cyo_adventure.diversity.normalize import (
    coerce_storybook,
    content_tokens,
    extract_entities,
    mask_tokens,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cyo_adventure.storybook.models import Storybook


@dataclass(frozen=True, slots=True)
class LexicalProfile:
    """One fill's lexical guard profile (WS-0 design doc section 3.2).

    Attributes:
        distinct_1: Unique unigrams over total unigrams, pooled across
            every node's masked content tokens.
        distinct_2: Unique bigrams over total bigrams; bigrams are formed
            within one node only, pooled across nodes.
        self_bleu_lite: Arithmetic mean, over nodes with at least one
            content token, of that node's geometric-mean overlap with the
            union of every other node's unigrams/bigrams (a set-based,
            no-brevity-penalty self-similarity proxy). Recorded and
            reported, never gated in Phase 2.
        content_token_count: Total pooled content-token count across all
            nodes.
    """

    distinct_1: float
    distinct_2: float
    self_bleu_lite: float
    content_token_count: int


def _node_bigrams(tokens: list[str]) -> list[str]:
    """Return the within-node adjacent-token bigrams, joined as ``"w1 w2"``.

    Args:
        tokens: One node's masked content tokens, in body order.

    Returns:
        list[str]: Consecutive-pair bigrams; never spans a node boundary
            (WS-0 design doc section 3.2: "a phantom bigram spanning two
            unrelated bodies is noise").
    """
    return [f"{first} {second}" for first, second in pairwise(tokens)]


def _node_overlap_score(
    node_unigrams: list[str],
    node_bigrams: list[str],
    other_unigrams: frozenset[str],
    other_bigrams: frozenset[str],
) -> float:
    """Return one node's self-BLEU-lite contribution.

    Args:
        node_unigrams: The node's own content-token unigrams.
        node_bigrams: The node's own within-node bigrams.
        other_unigrams: The union of unigrams from every other node.
        other_bigrams: The union of bigrams from every other node.

    Returns:
        float: ``sqrt(p1 * p2)`` (geometric mean) where ``p1`` is the
            fraction of the node's distinct unigrams present in
            ``other_unigrams`` and ``p2`` likewise for bigrams; a node with
            fewer than two tokens has no bigrams and uses ``p1`` alone
            (WS-0 design doc section 3.2).
    """
    unique_unigrams = frozenset(node_unigrams)
    p1 = (
        len(unique_unigrams & other_unigrams) / len(unique_unigrams)
        if unique_unigrams
        else 0.0
    )
    if not node_bigrams:
        return p1
    unique_bigrams = frozenset(node_bigrams)
    p2 = len(unique_bigrams & other_bigrams) / len(unique_bigrams)
    return math.sqrt(p1 * p2)


def lexical_profile(
    story: Storybook | Mapping[str, object],
    brief: Mapping[str, object] | None = None,
) -> LexicalProfile:
    """Compute one fill's lexical guard profile.

    Args:
        story: A validated Storybook, or a raw blob to coerce.
        brief: The story's own theme brief, if available (entities are
            drawn from the story's own fill; this is a single-story
            metric, no pair partner).

    Returns:
        LexicalProfile: ``distinct_1``, ``distinct_2``, ``self_bleu_lite``,
            and ``content_token_count``; all-zero for a story with no
            content tokens at all.
    """
    model = coerce_storybook(story)
    entities = extract_entities(model, brief)
    per_node_unigrams = [
        content_tokens(mask_tokens(node.body, entities)) for node in model.nodes
    ]
    per_node_bigrams = [_node_bigrams(unigrams) for unigrams in per_node_unigrams]

    all_unigrams = [token for node_tokens in per_node_unigrams for token in node_tokens]
    all_bigrams = [
        bigram for node_bigrams in per_node_bigrams for bigram in node_bigrams
    ]

    distinct_1 = (
        len(frozenset(all_unigrams)) / len(all_unigrams) if all_unigrams else 0.0
    )
    distinct_2 = len(frozenset(all_bigrams)) / len(all_bigrams) if all_bigrams else 0.0

    node_scores: list[float] = []
    for index, node_unigrams in enumerate(per_node_unigrams):
        if not node_unigrams:
            continue
        other_unigrams = frozenset(
            token
            for other_index, tokens in enumerate(per_node_unigrams)
            if other_index != index
            for token in tokens
        )
        other_bigrams = frozenset(
            bigram
            for other_index, bigrams in enumerate(per_node_bigrams)
            if other_index != index
            for bigram in bigrams
        )
        node_scores.append(
            _node_overlap_score(
                node_unigrams, per_node_bigrams[index], other_unigrams, other_bigrams
            )
        )
    self_bleu_lite = math.fsum(node_scores) / len(node_scores) if node_scores else 0.0

    return LexicalProfile(
        distinct_1=distinct_1,
        distinct_2=distinct_2,
        self_bleu_lite=self_bleu_lite,
        content_token_count=len(all_unigrams),
    )
