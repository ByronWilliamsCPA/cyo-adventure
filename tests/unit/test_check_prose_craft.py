"""Unit tests for scripts/check_prose_craft.py (AL-170/UW-C106 detectors)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from scripts.check_prose_craft import (
    PAST,
    PRESENT,
    main,
    moral_tags,
    node_tense_counts,
    sentence_tense,
    strip_quoted,
    tense_report,
    told_emotion,
)

if TYPE_CHECKING:
    from pathlib import Path


def _story(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a minimal filled-story shape around the given nodes."""
    return {"id": "s", "start_node": nodes[0]["id"], "nodes": nodes}


def _node(node_id: str, body: str, *, ending: bool = False) -> dict[str, Any]:
    """Return one node, optionally marked as an ending."""
    node: dict[str, Any] = {"id": node_id, "body": body, "is_ending": ending}
    if ending:
        node["ending"] = {"id": f"e_{node_id}", "kind": "success"}
    return node


_PAST_BODY = (
    "Tom opened the hatch. Nia climbed the ladder first. "
    "Sef followed her up. The lamp swung on its hook. "
    "They found the dial cold. Tom turned the first ring. "
    "The gears settled into place. Nia smiled at the sound."
)
_PRESENT_BODY = (
    "Tom opens the hatch. Nia climbs the ladder first. "
    "Sef follows her up. The lamp swings on its hook. "
    "They find the dial cold. Tom turns the first ring. "
    "The gears settle into place. Nia smiles at the sound."
)


# --------------------------------------------------------------------------
# Tense
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_sentence_tense_classifies_a_simple_past_main_clause_as_past() -> None:
    assert sentence_tense("Nia opened the hatch.") == PAST


@pytest.mark.unit
def test_sentence_tense_classifies_a_simple_present_main_clause_as_present() -> None:
    assert sentence_tense("Nia opens the hatch.") == PRESENT


@pytest.mark.unit
def test_sentence_tense_ignores_a_habitual_sentence() -> None:
    """Gnomic and irrealis sentences carry no narrative-tense evidence."""
    assert sentence_tense("The tower always keeps its own hour.") is None
    assert sentence_tense("Tomorrow they open the vault.") is None
    assert sentence_tense("They would return the next night.") is None


@pytest.mark.unit
def test_sentence_tense_ignores_a_subordinate_opening() -> None:
    assert sentence_tense("Since the tower was built, nobody climbs it.") is None


@pytest.mark.unit
def test_sentence_tense_ignores_a_participle_after_an_auxiliary() -> None:
    """'have found' is a perfect construction, not a finite past cue."""
    assert sentence_tense("They have found nothing at all.") is None
    # 'had' is itself a finite past form, so it still counts as past.
    assert sentence_tense("They had found nothing at all.") == PAST


@pytest.mark.unit
def test_node_tense_counts_exempts_present_tense_dialogue_in_past_narration() -> None:
    """Dialogue is legitimately present tense; only narration is evidence."""
    body = (
        "Tom opened the hatch. 'I see it,' he said. "
        '"It is right there and it looks fine," Nia added. '
        "Sef climbed after them."
    )
    past, present = node_tense_counts(body)
    assert past == 4
    assert present == 0


@pytest.mark.unit
def test_strip_quoted_keeps_possessives_and_contractions() -> None:
    text = "Elara's dial isn't turning."
    assert strip_quoted(text) == text


@pytest.mark.unit
def test_tense_report_leaves_a_uniformly_past_book_clean() -> None:
    story = _story(
        [_node("n1", _PAST_BODY), _node("n2", _PAST_BODY), _node("n3", _PAST_BODY)]
    )
    report = tense_report(story)
    assert report.dominant == PAST
    assert report.unstable == []
    assert report.minority_ratio == pytest.approx(0.0)


@pytest.mark.unit
def test_tense_report_leaves_a_uniformly_present_book_clean() -> None:
    """A present-tense book is a legitimate choice, not a defect."""
    story = _story(
        [
            _node("n1", _PRESENT_BODY),
            _node("n2", _PRESENT_BODY),
            _node("n3", _PRESENT_BODY),
        ]
    )
    report = tense_report(story)
    assert report.dominant == PRESENT
    assert report.unstable == []


@pytest.mark.unit
def test_tense_report_flags_a_node_wholly_in_the_non_dominant_tense() -> None:
    story = _story(
        [
            _node("n1", _PAST_BODY),
            _node("n2", _PAST_BODY),
            _node("n_odd", _PRESENT_BODY),
        ]
    )
    report = tense_report(story)
    assert report.dominant == PAST
    assert [n.node_id for n in report.unstable] == ["n_odd"]
    assert "wholly present" in report.unstable[0].reason


@pytest.mark.unit
def test_tense_report_flags_a_node_that_mixes_both_tenses() -> None:
    """The AL-170 example: past setup flipping to present inside one node."""
    mixed = (
        "Tom opened the hatch. Nia climbed the ladder. "
        "Sef followed her up. The lamp swung on its hook. "
        "They found the dial cold. "
        "Tom stands very still. Sef takes a breath. "
        "The machine sounds patient now."
    )
    story = _story([_node("n1", _PAST_BODY), _node("n_mix", mixed)])
    report = tense_report(story)
    assert [n.node_id for n in report.unstable] == ["n_mix"]
    assert "mixed" in report.unstable[0].reason


@pytest.mark.unit
def test_tense_report_flags_a_node_that_flips_wholesale_mid_book() -> None:
    """A node that goes over to the other tense is reported as dominant-side."""
    flipped = (
        "They forced the rings. It seemed easier than thinking. "
        "The gears protested loudly. "
        "Tom stands very still. Sef takes a breath. "
        "The machine sounds patient now. Nia reaches for the tin."
    )
    story = _story([_node("n1", _PAST_BODY), _node("n_flip", flipped)])
    report = tense_report(story)
    assert [n.node_id for n in report.unstable] == ["n_flip"]
    assert "present-dominant" in report.unstable[0].reason


@pytest.mark.unit
def test_tense_report_does_not_flag_a_short_node_below_the_cue_floor() -> None:
    """One stray clause in a two-sentence node is not evidence of a break."""
    story = _story(
        [
            _node("n1", _PAST_BODY),
            _node("n2", _PAST_BODY),
            _node("n_short", "Tom opens the door. Nia opened it wider."),
        ]
    )
    assert tense_report(story).unstable == []


# --------------------------------------------------------------------------
# Narrator moral tags
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_moral_tags_flags_a_lesson_framing_in_an_ending_close() -> None:
    body = (
        "They set the comet back on its shelf. "
        "The four friends stood together as the settlement sang, "
        "understanding that sometimes the prize is not taking something, "
        "but giving something back."
    )
    hits = moral_tags(_story([_node("n_end", body, ending=True)]))
    assert len(hits) == 1
    assert hits[0].node_id == "n_end"
    assert "understanding that" in hits[0].sentence


@pytest.mark.unit
def test_moral_tags_flags_taught_them_what_matters_more() -> None:
    body = (
        "They carried the case back up the stair. "
        "The taking was brief, but it taught them what matters more than "
        "objects: the respect that comes from choosing rightly."
    )
    hits = moral_tags(_story([_node("n_end", body, ending=True)]))
    assert [h.pattern for h in hits] == ["taught them"]


@pytest.mark.unit
def test_moral_tags_leaves_a_dramatized_ending_clean() -> None:
    body = (
        "They each held the little glass comet in turn and swore the same "
        "simple oath over it: guard the room, tell no one, come back often. "
        "Then the comet went back on its shelf and the door settled shut. "
        "Walking home, shoulder to shoulder, they carried nothing at all."
    )
    assert moral_tags(_story([_node("n_end", body, ending=True)])) == []


@pytest.mark.unit
def test_moral_tags_ignores_non_ending_nodes() -> None:
    body = "It taught them what matters more than objects."
    assert moral_tags(_story([_node("n_mid", body)])) == []


@pytest.mark.unit
def test_moral_tags_ignores_a_lesson_outside_the_tail_window() -> None:
    body = (
        "It taught them what matters more than objects. "
        "Nia pulled the door shut. Tom counted the stairs down. "
        "Sef swung the lamp. They walked out into the harbor wind."
    )
    hits = moral_tags(_story([_node("n_end", body, ending=True)]), tail_sentences=2)
    assert hits == []


@pytest.mark.unit
def test_moral_tags_exempts_a_lesson_spoken_by_a_character() -> None:
    """A keeper may say it out loud; the narrator may not."""
    body = "'You learned that the hard way,' Quayle said, and shut the door."
    assert moral_tags(_story([_node("n_end", body, ending=True)])) == []


# --------------------------------------------------------------------------
# Told emotion
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_told_emotion_flags_stock_interiority_reports() -> None:
    body = (
        "Tom's heart sinks. Panic flickers through the room. "
        "Nia's eyes go wide and Tom laughs nervously."
    )
    report = told_emotion(_story([_node("n1", body)]))
    assert sorted(h.phrase.lower() for h in report.hits) == [
        "eyes go wide",
        "heart sinks",
        "laughs nervously",
        "panic flickers",
    ]
    assert all(h.node_id == "n1" for h in report.hits)


@pytest.mark.unit
def test_told_emotion_leaves_staged_behavior_clean() -> None:
    body = (
        "Tom put the tin down and did not pick it up again. "
        "Nia counted the stairs twice before she answered. "
        "Sef laughed at the wrong moment and then stopped."
    )
    assert told_emotion(_story([_node("n1", body)])).hits == []


@pytest.mark.unit
def test_told_emotion_exempts_dialogue() -> None:
    body = "'My heart sinks every time,' Tom said, and put the tin down."
    assert told_emotion(_story([_node("n1", body)])).hits == []


@pytest.mark.unit
def test_told_emotion_rate_is_normalized_by_narration_length() -> None:
    """AL-159 length normalization: the same count in a longer book scores lower."""
    tell = "Tom's heart sinks. "
    filler = "Nia counted the stairs and put the lamp down again. " * 20
    short = told_emotion(_story([_node("n1", tell + filler)]))
    long = told_emotion(_story([_node("n1", tell + filler * 3)]))
    assert len(short.hits) == len(long.hits) == 1
    assert short.per_1000 > long.per_1000
    assert long.per_1000 == pytest.approx(1 / long.words * 1000.0)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, story: dict[str, Any]) -> str:
    """Write a story to tmp_path and return its path as a string."""
    path = tmp_path / name
    path.write_text(json.dumps(story), encoding="utf-8")
    return str(path)


@pytest.mark.unit
def test_main_exits_zero_for_a_clean_book_under_check(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "clean.json",
        _story([_node("n1", _PAST_BODY), _node("n2", _PAST_BODY)]),
    )
    assert main([path, "--check"]) == 0


@pytest.mark.unit
def test_main_exits_one_when_a_threshold_is_breached_under_check(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        "dirty.json",
        _story(
            [
                _node("n1", _PAST_BODY),
                _node("n2", _PAST_BODY),
                _node("n_odd", _PRESENT_BODY),
            ]
        ),
    )
    assert main([path, "--check"]) == 1


@pytest.mark.unit
def test_main_reports_but_exits_zero_without_check(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "dirty.json",
        _story(
            [
                _node("n1", _PAST_BODY),
                _node("n2", _PAST_BODY),
                _node("n_odd", _PRESENT_BODY),
            ]
        ),
    )
    assert main([path]) == 0


@pytest.mark.unit
def test_main_returns_two_for_an_unreadable_file(tmp_path: Path) -> None:
    assert main([str(tmp_path / "missing.json"), "--check"]) == 2


@pytest.mark.unit
def test_moral_tags_with_a_zero_tail_scans_nothing() -> None:
    """A tail of 0 must scan an empty window, not slice [-0:] into the whole body."""
    story = {
        "nodes": [
            {
                "id": "e1",
                "is_ending": True,
                "ending": {"kind": "completion", "valence": "positive"},
                "body": "They walked home. It taught them what matters more than gold.",
            }
        ]
    }
    assert moral_tags(story, tail_sentences=0) == []
    assert moral_tags(story, tail_sentences=4)
