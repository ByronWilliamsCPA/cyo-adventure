"""Unit tests for diversity.lexical, the distinct-n/self-BLEU-lite guards (WS-0 Phase 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.diversity.lexical import LexicalProfile, lexical_profile
from cyo_adventure.storybook.models import Storybook

if TYPE_CHECKING:
    from collections.abc import Sequence


def _make_story(bodies: Sequence[str], topology: str = "time_cave") -> Storybook:
    """Build a minimal valid Storybook: a linear chain of nodes, one per body.

    The last body becomes the (single) ending node; every earlier body gets
    a single choice to the next node. A one-body sequence is itself the
    ending node (matching ``test_diversity_leaf.py``'s convention for a
    minimal fixture).

    Args:
        bodies: The node bodies, in chain order.
        topology: The declared topology (metadata-only; the schema does not
            cross-check topology against graph shape).

    Returns:
        Storybook: The validated story.
    """
    nodes: list[dict[str, object]] = []
    last_index = len(bodies) - 1
    for index, body in enumerate(bodies):
        node_id = f"n{index}"
        if index == last_index:
            nodes.append(
                {
                    "id": node_id,
                    "body": body,
                    "is_ending": True,
                    "ending": {
                        "id": f"e{index}",
                        "valence": "positive",
                        "kind": "completion",
                        "title": "End",
                    },
                }
            )
        else:
            nodes.append(
                {
                    "id": node_id,
                    "body": body,
                    "choices": [
                        {
                            "id": f"c{index}",
                            "label": "Continue",
                            "target": f"n{index + 1}",
                        }
                    ],
                }
            )
    data = {
        "schema_version": "2.0",
        "id": "sk_test",
        "version": 1,
        "title": "T",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"scheme": "flesch_kincaid", "target": 4.5},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": topology,
        },
        "start_node": "n0",
        "nodes": nodes,
    }
    return Storybook.model_validate(data)


@pytest.mark.unit
def test_lexical_profile_hand_built_three_node_story_matches_exact_values() -> None:
    """A hand-computable 3-node story yields exactly-derivable metric values.

    Pooled content unigrams: cat, sat, mat, dog, sat, log, bird, flew, sea
    (9 total, 8 unique: "sat" repeats) -> distinct_1 = 8/9.
    Within-node bigrams only, all six distinct -> distinct_2 = 1.0. Every
    node's cross-node unigram overlap is at most the shared "sat" token and
    no node shares a bigram with another, so self_bleu_lite is 0.0.
    """
    story = _make_story(
        [
            "The cat sat on the mat.",
            "The dog sat on the log.",
            "The bird flew over the sea.",
        ]
    )
    profile = lexical_profile(story)
    assert profile.distinct_1 == pytest.approx(8 / 9)
    assert profile.distinct_2 == pytest.approx(1.0)
    assert profile.self_bleu_lite == pytest.approx(0.0)
    assert profile.content_token_count == 9


@pytest.mark.unit
def test_duplicating_a_node_body_lowers_distinct2_and_raises_self_bleu() -> None:
    """Duplicating one node's body verbatim lowers distinct_2, raises self_bleu_lite."""
    original = _make_story(
        [
            "The cat sat on the mat.",
            "The dog sat on the log.",
            "The bird flew over the sea.",
        ]
    )
    duplicated = _make_story(
        [
            "The cat sat on the mat.",
            "The cat sat on the mat.",
            "The bird flew over the sea.",
        ]
    )
    original_profile = lexical_profile(original)
    duplicated_profile = lexical_profile(duplicated)
    assert duplicated_profile.distinct_2 < original_profile.distinct_2
    assert duplicated_profile.self_bleu_lite > original_profile.self_bleu_lite


@pytest.mark.unit
def test_bigrams_do_not_cross_node_boundaries() -> None:
    """Bigrams are formed within one node only, never spanning a node boundary.

    node1's content tokens are [alpha, beta, gamma] (bigrams: "alpha beta",
    "beta gamma"); node2's are [gamma, alpha, beta] (bigrams: "gamma alpha",
    "alpha beta"). If a phantom boundary bigram ("gamma gamma", node1's last
    token joined with node2's first) were formed, distinct_2 would be 4/5
    (0.8) instead of the correct 3/4 (0.75).
    """
    story = _make_story(["Alpha beta gamma.", "Gamma alpha beta."])
    profile = lexical_profile(story)
    assert profile.distinct_2 == pytest.approx(0.75)


@pytest.mark.unit
def test_empty_story_profile_is_all_zero() -> None:
    """A story with no content tokens at all reports every metric as zero."""
    story = _make_story([""])
    profile = lexical_profile(story)
    assert profile == LexicalProfile(
        distinct_1=0.0, distinct_2=0.0, self_bleu_lite=0.0, content_token_count=0
    )


@pytest.mark.unit
def test_entities_are_masked_before_counting() -> None:
    """A repeated hero name does not tank distinct-1 differently across two heroes.

    Two stories are identical except for a name repeated 21 times (once
    sentence-medially, establishing it as an entity, then 20 more times);
    once masked to the single entity placeholder, the two stories'
    computed profiles are byte-for-byte identical.
    """

    def _repeated_name_story(name: str) -> Storybook:
        sentences = [f"Ravi and {name} walked home."]
        sentences += [f"{name} explored the cave." for _ in range(20)]
        return _make_story([" ".join(sentences)], topology="gauntlet")

    priya_profile = lexical_profile(_repeated_name_story("Priya"))
    theo_profile = lexical_profile(_repeated_name_story("Theo"))
    assert priya_profile == theo_profile
