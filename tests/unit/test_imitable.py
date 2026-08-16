"""Pin the three scoping decisions that make the hazard screen usable.

Each of them was forced by measurement rather than chosen: endings only, young
bands only, and co-occurrence rather than single words. Ungated or unscoped, the
screen selects a tenth of the corpus and selects nothing.

The bodies below are paraphrases of the real endings two readers named, kept
short enough to read in place. The screen is a router, so every assertion here
is about what reaches a person, never about what passes or fails.
"""

from __future__ import annotations

import pytest

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.imitable import screen_for_review

_TUNNEL = (
    "They dug from both ends at once until their mittens met in the middle. "
    "The snow tunnel was long enough to crawl through, and they crawled it "
    "again and again. Greatest fort ever built."
)
_FLAME = (
    "She touched the flame to the wick all by herself. Her paws did not shake "
    "once. The lantern woke up glowing and the whole crowd cheered for her."
)
_HARMLESS = (
    "They shared the last of the biscuits on the back step and watched the "
    "light go gold over the fence. It had been a good, ordinary day."
)


def _story(
    bodies: dict[str, str], *, band: str = "5-8", endings: bool = True
) -> Storybook:
    """Build a one-start, many-ending story carrying *bodies*.

    Args:
        bodies: Node id to body text. All become endings unless *endings* is
            False, in which case they become ordinary nodes.
        band: The age band to declare.
        endings: Whether the bodies are ending nodes.

    Returns:
        Storybook: The assembled story.
    """
    targets = list(bodies)
    nodes = [
        {
            "id": "n_start",
            "body": "The day began the way most days do, slowly and all at once.",
            "is_ending": False,
            "choices": [
                {"id": f"c{index}", "label": f"Go {index}", "target": target}
                for index, target in enumerate(targets)
            ],
        }
    ]
    nodes += [
        {
            "id": node_id,
            "body": body,
            "is_ending": endings,
            "ending": (
                {
                    "id": f"end_{node_id}",
                    "title": "Done",
                    "valence": "positive",
                    "kind": "success",
                }
                if endings
                else None
            ),
            "choices": []
            if endings
            else [{"id": f"x_{node_id}", "label": "On", "target": "n_final"}],
        }
        for node_id, body in bodies.items()
    ]
    if not endings:
        nodes.append(
            {
                "id": "n_final",
                "body": "And then the day was over, the way days are.",
                "is_ending": True,
                "ending": {
                    "id": "end_final",
                    "title": "Done",
                    "valence": "positive",
                    "kind": "success",
                },
                "choices": [],
            }
        )
    return Storybook.model_validate(
        {
            "schema_version": "2.0",
            "id": "sk_test",
            "version": 1,
            "title": "Test",
            "start_node": "n_start",
            "variables": [],
            "metadata": {
                "age_band": band,
                "reading_level": {
                    "scheme": "flesch_kincaid",
                    "target": 2.5,
                    "tolerance": 1.0,
                },
                "tier": 1,
                "themes": ["play"],
                "estimated_minutes": 5,
                "ending_count": sum(1 for node in nodes if node["is_ending"]),
                "content_flags": {
                    "violence": "none",
                    "scariness": "none",
                    "peril": "none",
                },
                "topology": "time_cave",
                "length": "short",
                "narrative_style": "prose",
            },
            "nodes": nodes,
        }
    )


@pytest.mark.unit
def test_the_two_endings_the_readers_named_are_selected() -> None:
    """The regression anchor: these are the real cases, paraphrased."""
    story = _story({"e_tunnel": _TUNNEL, "e_flame": _FLAME})

    selected = {(cue.node_id, cue.cue) for cue in screen_for_review(story)}

    assert ("e_tunnel", "snow_enclosure") in selected
    assert ("e_flame", "open_flame") in selected


@pytest.mark.unit
def test_an_ordinary_ending_is_not_selected() -> None:
    """A router that selects everything routes nothing."""
    assert screen_for_review(_story({"e_quiet": _HARMLESS})) == []


@pytest.mark.unit
def test_an_older_band_is_out_of_scope_by_design() -> None:
    """Gating to young bands is what makes the screen usable, not an oversight.

    Ungated, the flame cue alone fires on 23 endings, mostly 16+ gamebooks where
    a depicted flame is not a child-imitation risk. Scoping this out is a claim
    about who might copy the behaviour, not a claim that older books are safe.
    """
    assert screen_for_review(_story({"e_flame": _FLAME}, band="16+")) == []


@pytest.mark.unit
def test_the_same_hazard_in_a_mid_scene_node_is_not_selected() -> None:
    """The concern is what a book REWARDS, not what it depicts along the way.

    Scanning every node buries the signal in scene-setting, and a hazard a
    character passes through and learns from is the opposite of the case here.
    """
    story = _story({"n_middle": _TUNNEL}, endings=False)

    assert screen_for_review(story) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        "The snow lay deep and clean across the whole white yard that morning.",
        "They crawled through the long tunnel under the hedge, out into the sun.",
    ],
    ids=["hazard-cue-alone", "action-cue-alone"],
)
def test_one_cue_without_the_other_is_not_enough(body: str) -> None:
    """Co-occurrence is the whole design.

    A single word selects on vocabulary rather than on practice: `climb` alone
    matched 10.8 percent of all endings and was dropped for exactly this.
    """
    assert screen_for_review(_story({"e_one": body})) == []
