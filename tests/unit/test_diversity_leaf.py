"""Unit tests for diversity.leaf, the anti-template guard (WS-0 Phase 1)."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.leaf import (
    AntiTemplateThresholds,
    anti_template_verdict,
    leaf_distance_profile,
)
from cyo_adventure.diversity.report import AntiTemplateVerdict
from cyo_adventure.storybook.models import Storybook

_SPACE_STATION_FILL = Path(
    "out/pilot/fills/the-cave-of-echoes.space-station.filled.json"
)
_DINO_DIG_FILL = Path("out/pilot/fills/the-cave-of-echoes.dino-dig.filled.json")
_LOCKED_CAROUSEL_SKELETON = Path("skeletons/8-11/the-locked-carousel.json")

# A committed swap table for the synthetic dog-for-cat variant: 18 proper and
# common nouns from the space-station fill, each replaced by an unrelated
# word of the same rough part of speech. Built at test run time (not
# committed as a fixture) per WS-0 design doc section 6.2's rationale:
# synthesizing avoids checking a deliberately-bad story into the corpus.
_NOUN_SWAPS: dict[str, str] = {
    "priya": "barnaby",
    "pip": "rex",
    "halcyon": "oakwood",
    "station": "cottage",
    "corridor": "hallway",
    "airlock": "doorway",
    "docking": "garden",
    "coolant": "soup",
    "chamber": "pantry",
    "beacon": "lantern",
    "reactor": "oven",
    "bulkhead": "gate",
    "drone": "pup",
    "console": "table",
    "hatch": "door",
    "echo": "song",
    "panel": "shelf",
    "signal": "smell",
}
_SWAP_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(word) for word in _NOUN_SWAPS) + r")\b",
    re.IGNORECASE,
)


def _swap_one(match: re.Match[str]) -> str:
    original = match.group(0)
    replacement = _NOUN_SWAPS[original.lower()]
    return replacement.capitalize() if original[0].isupper() else replacement


def _make_noun_swap_variant(fill: dict[str, object]) -> dict[str, object]:
    """Return a deep copy of ``fill`` with every _NOUN_SWAPS word replaced.

    A synthetic "dog for cat" template: the same structure and the same
    sentence-by-sentence rhythm, only the nouns changed -- the canonical
    anti-template-guard failure case.
    """
    variant = copy.deepcopy(fill)
    for node in variant["nodes"]:  # type: ignore[index]
        node["body"] = _SWAP_PATTERN.sub(_swap_one, node["body"])
    return variant


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_story(path: Path) -> Storybook:
    return Storybook.model_validate(_load(path))


@pytest.mark.unit
def test_anti_template_guard_pilot_fills_score_as_different() -> None:
    """The two genuinely re-authored pilot fills PASS with a wide margin."""
    a = _load_story(_SPACE_STATION_FILL)
    b = _load_story(_DINO_DIG_FILL)
    report = anti_template_verdict(a, b)
    assert report.verdict is AntiTemplateVerdict.PASS_
    assert report.median_distance >= 0.60
    assert report.p25_distance >= 0.45
    assert report.templated_nodes == ()
    assert report.node_count == 64


@pytest.mark.unit
def test_anti_template_guard_noun_swap_variant_fails() -> None:
    """A synthetic dog-for-cat noun swap of one pilot fill FAILs against itself."""
    original = _load(_SPACE_STATION_FILL)
    swapped = _make_noun_swap_variant(original)
    report = anti_template_verdict(
        Storybook.model_validate(original), Storybook.model_validate(swapped)
    )
    assert report.verdict is AntiTemplateVerdict.FAIL
    assert report.median_distance <= 0.25
    assert len(report.templated_nodes) > 0


@pytest.mark.unit
def test_anti_template_guard_identical_fill_fails_with_zero_distance() -> None:
    """A fill compared against itself is a template of itself: FAIL, distance 0."""
    story = _load_story(_SPACE_STATION_FILL)
    report = anti_template_verdict(story, story)
    assert report.verdict is AntiTemplateVerdict.FAIL
    assert report.median_distance == 0.0
    assert report.p25_distance == 0.0
    assert len(report.templated_nodes) == report.node_count


@pytest.mark.unit
def test_anti_template_guard_rejects_cross_tree_pair_with_validation_error() -> None:
    """Comparing fills of two different skeletons raises, it never scores."""
    a = _load_story(_SPACE_STATION_FILL)
    b = Storybook.model_validate(_load(_LOCKED_CAROUSEL_SKELETON))
    with pytest.raises(ValidationError):
        anti_template_verdict(a, b)


@pytest.mark.unit
def test_leaf_distance_zero_when_both_bodies_empty() -> None:
    """Two nodes with empty bodies are trivially identical, not different."""
    base = {
        "schema_version": "2.0",
        "id": "sk_empty",
        "version": 1,
        "title": "T",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"scheme": "flesch_kincaid", "target": 4.5},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "gauntlet",
        },
        "start_node": "n1",
        "nodes": [
            {
                "id": "n1",
                "body": "",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "End",
                },
            }
        ],
    }
    story_a = Storybook.model_validate(base)
    story_b = Storybook.model_validate(base)
    profile = leaf_distance_profile(story_a, story_b)
    assert profile.nodes[0].d_uni == 0.0
    assert profile.nodes[0].d_big == 0.0


@pytest.mark.unit
def test_band_threshold_override_changes_verdict_boundaries() -> None:
    """A custom AntiTemplateThresholds override changes the computed verdict."""
    a = _load_story(_SPACE_STATION_FILL)
    b = _load_story(_DINO_DIG_FILL)
    lenient = AntiTemplateThresholds(
        fail_median=0.0, fail_p25=0.0, pass_median=0.99, pass_p25=0.99
    )
    report = anti_template_verdict(a, b, thresholds=lenient)
    # The default verdict is PASS (see test above); an artificially high
    # pass bar with a near-zero fail floor pushes the same pair into WARN.
    assert report.verdict is AntiTemplateVerdict.WARN
