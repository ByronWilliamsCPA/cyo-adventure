"""build_cover_prompt derives a text prompt from a story blob."""

import pytest

from cyo_adventure.covers.prompt import build_cover_prompt

pytestmark = pytest.mark.unit

_BLOB = {
    "title": "The Lantern in the Woods",
    "metadata": {
        "themes": ["courage", "friendship"],
        "age_band": "5-8",
        "content_flags": {"scariness": "mild", "peril": "none", "violence": "none"},
    },
}


def test_includes_title_themes_and_ageband():
    prompt = build_cover_prompt(_BLOB, protagonist_name="Mira")
    assert "The Lantern in the Woods" in prompt
    assert "courage" in prompt
    assert "friendship" in prompt
    assert "5-8" in prompt
    assert "Mira" in prompt


def test_always_forbids_text_in_image():
    prompt = build_cover_prompt(_BLOB)
    assert "Do NOT include any text" in prompt


def test_missing_protagonist_degrades_gracefully():
    prompt = build_cover_prompt({"title": "x", "metadata": {}})
    assert "the main character" in prompt


def test_intense_flag_forces_gentle_clause():
    blob = {
        "title": "Storm",
        "metadata": {"content_flags": {"scariness": "intense", "peril": "moderate"}},
    }
    prompt = build_cover_prompt(blob)
    assert "non-graphic" in prompt
    assert "child-safe" in prompt


def test_includes_opening_scene_excerpt():
    blob = {
        "title": "The Bridge",
        "start_node": "n1",
        "nodes": [
            {"id": "n0", "body": "unused"},
            {"id": "n1", "body": "A stone bridge arched over a misty green river."},
        ],
        "metadata": {},
    }
    prompt = build_cover_prompt(blob)
    assert "stone bridge" in prompt
