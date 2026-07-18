"""Unit tests for diversity.normalize (WS-0 Phase 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.diversity.normalize import (
    ENTITY_PLACEHOLDER,
    STOPWORDS,
    content_tokens,
    extract_entities,
    jaccard_similarity,
    mask_tokens,
    theme_signature,
)
from cyo_adventure.storybook.models import Storybook

_SPACE_STATION_FILL = Path(
    "out/pilot/fills/the-cave-of-echoes.space-station.filled.json"
)


def _load_story(path: Path) -> Storybook:
    return Storybook.model_validate(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.unit
def test_extract_entities_finds_medial_caps_from_pilot_fill() -> None:
    """Priya, Pip, and Halcyon are recovered via medial-caps; "the" is not."""
    story = _load_story(_SPACE_STATION_FILL)
    entities = extract_entities(story)
    assert {"priya", "pip", "halcyon"} <= entities
    assert "the" not in entities


@pytest.mark.unit
def test_extract_entities_includes_brief_names() -> None:
    """A brief's protagonist name is masked even if used only sentence-initially."""
    story = Storybook.model_validate(
        {
            "schema_version": "2.0",
            "id": "sk_test",
            "version": 1,
            "title": "Test Story",
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
                    "body": "Zephyrine walks alone. She hums a quiet tune. Later, she rests.",
                    "is_ending": True,
                    "ending": {
                        "id": "e1",
                        "valence": "positive",
                        "kind": "completion",
                        "title": "The End",
                    },
                }
            ],
        }
    )
    # "Zephyrine" appears only sentence-initially in the body above, so
    # medial-caps extraction alone would miss it; only the brief-declared
    # protagonist name recovers it (WS-0 design doc section 10, "Minor").
    entities_without_brief = extract_entities(story)
    assert "zephyrine" not in entities_without_brief

    brief = {"protagonist": {"name": "Zephyrine", "age": 9, "role": "a wanderer"}}
    entities_with_brief = extract_entities(story, brief)
    assert "zephyrine" in entities_with_brief


@pytest.mark.unit
def test_extract_entities_includes_anchor_context_character_names() -> None:
    """anchor_context.character_names contribute to the entity set."""
    brief = {
        "anchor_context": {
            "title": "The Prior Book",
            "character_names": ["Oakley Finch"],
        }
    }
    entities = extract_entities(
        Storybook.model_validate(
            {
                "schema_version": "2.0",
                "id": "sk_test2",
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
                        "body": "Nothing relevant happens here at all today.",
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
        ),
        brief,
    )
    assert {"oakley", "finch"} <= entities


@pytest.mark.unit
def test_mask_tokens_collapses_all_entities_to_one_placeholder() -> None:
    """Every entity token collapses to the same placeholder, regardless of identity."""
    entities = frozenset({"priya", "theo"})
    masked = mask_tokens("Priya waves at Theo, and Theo waves back.", entities)
    assert masked.count(ENTITY_PLACEHOLDER) == 3
    assert "priya" not in masked
    assert "theo" not in masked


@pytest.mark.unit
def test_content_tokens_drops_stopwords_but_keeps_placeholder() -> None:
    """content_tokens filters stopwords; the entity placeholder is never one."""
    masked = mask_tokens("The <ent> is in the room.", frozenset())
    filtered = content_tokens(masked)
    assert "the" not in filtered
    assert "room" in filtered


@pytest.mark.unit
def test_theme_signature_keeps_nouns_and_drops_stopwords() -> None:
    """theme_signature maps recognized nouns to tags, dropping stopword noise."""
    sig = theme_signature({"premise": "a dragon who lost his fire in the night"})
    assert sig == frozenset({"dragon", "fire"})


@pytest.mark.unit
def test_theme_signature_matches_paraphrased_same_theme_briefs() -> None:
    """Paraphrased same-theme briefs share a tag and score well above unrelated pairs."""
    dragon_a = theme_signature({"premise": "a dragon who lost his fire"})
    dragon_b = theme_signature({"premise": "dragon story please"})
    unrelated = theme_signature({"premise": "a robot who learns to paint"})

    similar_score = jaccard_similarity(dragon_a, dragon_b)
    unrelated_score = jaccard_similarity(dragon_a, unrelated)

    assert "dragon" in dragon_a
    assert "dragon" in dragon_b
    assert similar_score > 0.35
    assert unrelated_score < 0.1


@pytest.mark.unit
def test_theme_signature_includes_metadata_themes() -> None:
    """Curated metadata.themes are kept even when the tag map has no entry."""
    sig = theme_signature(None, ["Exploration", "courage"])
    assert sig == frozenset({"exploration", "courage"})


@pytest.mark.unit
def test_theme_signature_empty_brief_and_themes_is_empty() -> None:
    """No premise and no metadata themes yields an empty signature."""
    assert theme_signature(None) == frozenset()
    assert theme_signature({}) == frozenset()


@pytest.mark.unit
def test_stopwords_contains_common_function_words() -> None:
    """Sanity check: the stopword list covers core function words."""
    assert {"the", "a", "and", "is", "of"} <= STOPWORDS
