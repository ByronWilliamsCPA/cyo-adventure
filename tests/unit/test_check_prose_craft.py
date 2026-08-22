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
    """Dialogue is legitimately present tense; only narration is evidence.

    Counted 4 past until 2026-08-14, when the exemption widened from quoted
    spans to whole tagged sentences. The two it lost were "he said." and "Nia
    added.", the attribution fragments quote-stripping leaves behind. Those are
    not narration evidence: their tense is the tag verb's, and every dialogue
    line in a book contributes one, so the previous count handed the tense
    detector a free vote per spoken line and biased mixed-tense detection
    toward whichever tense the tags happened to use. Two is the number of
    narrative sentences in this body.
    """
    body = (
        "Tom opened the hatch. 'I see it,' he said. "
        '"It is right there and it looks fine," Nia added. '
        "Sef climbed after them."
    )
    past, present = node_tense_counts(body)
    assert past == 2
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
        _story(
            [
                _node("n1", _PAST_BODY),
                # A distinct second body: identical bodies are now a real
                # sameness finding (AL-496/UW-C313), not a fixture shortcut.
                _node("n2", _PAST_BODY + " The lantern burned low."),
            ]
        ),
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


@pytest.mark.unit
def test_sameness_report_counts_duplicates_and_label_collapse() -> None:
    """AL-496's shape: repeated bodies and three labels covering everything."""
    from scripts.check_prose_craft import sameness_report

    story = _story(
        [
            _node("n1", _PAST_BODY),
            _node("n2", _PAST_BODY),
            _node("n3", _PAST_BODY + " The lantern burned low."),
        ]
    )
    for node in story["nodes"]:
        node["choices"] = [
            {"id": f"c_{node['id']}", "label": "Press on.", "target": "n1"}
        ]
    report = sameness_report(story)
    assert report.repeated_texts == 1
    assert report.redundant_nodes == 1
    assert report.distinct_labels == 1
    assert report.top3_share == 1.0


@pytest.mark.unit
def test_person_report_measures_second_person_rate() -> None:
    from scripts.check_prose_craft import person_report

    story = _story(
        [
            _node("n1", "You lift the latch and step through."),
            _node("n2", "The corridor smelled of rain."),
        ]
    )
    report = person_report(story)
    assert report.nodes == 2
    assert report.second_person_nodes == 1
    assert report.rate == 0.5


# --------------------------------------------------------------------------
# Narrative person (UW-C328)
# --------------------------------------------------------------------------


# Four distinct past-tense third-person bodies. Distinct because a repeated
# body is its own finding (sameness), and past-tense because a tense finding
# would breach independently and mask what these tests are measuring.
_THIRD_BODIES = (
    "Tom opened the hatch. Nia climbed the ladder first. Sef followed her up.",
    "The lamp swung on its hook. They found the dial cold and still.",
    "Tom turned the first ring. The gears settled into place with a click.",
    "Nia smiled at the sound. Sef counted the marks along the brass rim.",
)
# The same four passages rewritten to address the reader.
_SECOND_BODIES = (
    "You opened the hatch. You climbed the ladder first. Sef followed you up.",
    "The lamp swung by your shoulder. You found the dial cold and still.",
    "You turned the first ring. The gears settled into place under your hand.",
    "You smiled at the sound. You counted the marks along the brass rim.",
)


def _person_story(
    bodies: tuple[str, ...],
    *,
    person: str | None = None,
    style: str | None = None,
) -> dict[str, Any]:
    """Return a clean four-node book carrying the given person declaration."""
    story = _story([_node(f"n{i}", body) for i, body in enumerate(bodies)])
    metadata: dict[str, Any] = {}
    if person is not None:
        metadata["narrative_person"] = person
    if style is not None:
        metadata["narrative_style"] = style
    story["metadata"] = metadata
    return story


def _mixed(second_count: int) -> tuple[str, ...]:
    """Return four bodies of which ``second_count`` are second-person."""
    return _SECOND_BODIES[:second_count] + _THIRD_BODIES[second_count:]


@pytest.mark.unit
def test_declared_second_person_below_the_floor_breaches(tmp_path: Path) -> None:
    """1 of 4 nodes is 0.25, under the 0.5 floor a declared second-person book owes."""
    path = _write(tmp_path, "s.json", _person_story(_mixed(1), person="second"))
    assert main([path, "--check"]) == 1


@pytest.mark.unit
def test_declared_second_person_at_the_floor_does_not_breach(tmp_path: Path) -> None:
    """2 of 4 nodes is exactly 0.5; the floor is inclusive."""
    path = _write(tmp_path, "s.json", _person_story(_mixed(2), person="second"))
    assert main([path, "--check"]) == 0


@pytest.mark.unit
def test_declared_third_person_above_the_ceiling_breaches(tmp_path: Path) -> None:
    """2 of 4 nodes is 0.5, over the 0.35 ceiling a declared third-person book owes."""
    path = _write(tmp_path, "s.json", _person_story(_mixed(2), person="third"))
    assert main([path, "--check"]) == 1


@pytest.mark.unit
def test_declared_third_person_below_the_ceiling_does_not_breach(
    tmp_path: Path,
) -> None:
    """1 of 4 nodes is 0.25, inside the 0.35 ceiling."""
    path = _write(tmp_path, "s.json", _person_story(_mixed(1), person="third"))
    assert main([path, "--check"]) == 0


@pytest.mark.unit
def test_undeclared_gamebook_still_gets_the_second_person_floor(
    tmp_path: Path,
) -> None:
    """The pre-declaration behavior survives: genre implies the floor."""
    path = _write(tmp_path, "s.json", _person_story(_mixed(1), style="gamebook"))
    assert main([path, "--check"]) == 1


@pytest.mark.unit
def test_undeclared_prose_is_not_person_gated_in_either_direction(
    tmp_path: Path,
) -> None:
    """Nothing pins an undeclared prose book's person, so neither bound applies.

    Both rates here would breach if a bound were applied: 0.25 is under the
    0.5 floor, and 1.0 is over the 0.35 ceiling.
    """
    low = _write(tmp_path, "low.json", _person_story(_mixed(1), style="prose"))
    high = _write(tmp_path, "high.json", _person_story(_SECOND_BODIES, style="prose"))
    assert main([low, "--check"]) == 0
    assert main([high, "--check"]) == 0


# Third-person narration whose only "you" is a character speaking to another
# character. Every node would count as second-person without the exemption,
# putting the book at 1.0 against a 0.35 ceiling.
_DIALOGUE_BODIES = (
    'Tom opened the hatch. "You go first," Nia said. Sef followed her up.',
    'The lamp swung on its hook. "Your hands are steadier," Tom said.',
    'Nia turned the first ring. "You heard that too," she said. The gears settled.',
    'Sef counted the marks. "Yours is the last one," he said to the empty room.',
)


@pytest.mark.unit
def test_second_person_inside_dialogue_is_exempt_from_the_person_gate(
    tmp_path: Path,
) -> None:
    """A third-person book may have characters say "you" to each other.

    The regression this pins: without ``strip_dialogue`` every one of these
    four nodes counts as second-person, putting the book at 1.0 against the
    0.35 third-person ceiling and failing it for dialogue it is entitled to
    have. The control below shows the ceiling still fires when the same
    address is narration rather than speech.
    """
    quoted = _write(
        tmp_path, "quoted.json", _person_story(_DIALOGUE_BODIES, person="third")
    )
    narrated = _write(
        tmp_path, "narrated.json", _person_story(_SECOND_BODIES, person="third")
    )
    assert main([quoted, "--check"]) == 0
    assert main([narrated, "--check"]) == 1


@pytest.mark.unit
def test_person_report_ignores_second_person_confined_to_dialogue() -> None:
    """The unit-level half of the exemption: narration is what is measured."""
    from scripts.check_prose_craft import person_report

    report = person_report(_person_story(_DIALOGUE_BODIES, person="third"))
    assert report.nodes == 4
    assert report.second_person_nodes == 0
    assert report.rate == 0.0


@pytest.mark.unit
def test_a_declared_third_gamebook_is_flagged_as_contradictory(
    tmp_path: Path,
) -> None:
    """A gamebook declaring third person is a contract error, not a measurement.

    The bodies here are entirely second-person, so the book clears the
    gamebook floor with room to spare; the exit code must still be 1. That is
    what separates the contradiction branch from the measurement branches, and
    what pins the branch ORDER: reading the declaration first sent a correct
    second-person gamebook to the third-person ceiling and failed it for being
    right (PR #737 review, I10).
    """
    path = _write(
        tmp_path,
        "contradictory.json",
        _person_story(_SECOND_BODIES, person="third", style="gamebook"),
    )
    assert main([path, "--check"]) == 1
