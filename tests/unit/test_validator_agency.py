"""Unit tests for the reader-agency detectors (``validator/agency.py``).

Every positive case quotes or minimally adapts a sentence the detector caught
in the 31-book calibration; every negative case is a false-positive class the
calibration found and the code now excludes, so a loosened pattern fails
here before it fails on a book.
"""

from __future__ import annotations

from typing import Any

import pytest

from cyo_adventure.validator.agency import (
    agency_report,
    book_person,
    decisions_to_reach,
    early_setbacks,
    give_up_endings,
    inbound_sources,
    label_defects,
    merge_seams,
    option_recaps,
    state_counts,
)

pytestmark = pytest.mark.unit


def _node(
    node_id: str,
    body: str = "Mira looked around.",
    targets: tuple[str, ...] = (),
    labels: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return a non-ending node with one choice per target."""
    choices = [
        {
            "id": f"c_{node_id}_{i}",
            "label": labels[i] if i < len(labels) else f"Go to {target}.",
            "target": target,
        }
        for i, target in enumerate(targets)
    ]
    return {"id": node_id, "body": body, "is_ending": False, "choices": choices}


def _ending(node_id: str, body: str, valence: str = "negative") -> dict[str, Any]:
    """Return an ending node with the given valence."""
    return {
        "id": node_id,
        "body": body,
        "is_ending": True,
        "choices": [],
        "ending": {"id": f"e_{node_id}", "kind": "setback", "valence": valence},
    }


def _story(nodes: list[dict[str, Any]], **metadata: str) -> dict[str, Any]:
    """Wrap nodes in a minimal filled-story shape starting at the first node."""
    return {
        "id": "s",
        "start_node": nodes[0]["id"],
        "metadata": dict(metadata),
        "variables": [],
        "nodes": nodes,
    }


def _merge_story(opening: str) -> dict[str, Any]:
    """Return a story whose node ``m`` has two inbound nodes and this body."""
    return _story(
        [
            _node("start", targets=("a", "b")),
            _node("a", targets=("m",)),
            _node("b", targets=("m",)),
            _node("m", opening + " The door stood open.", targets=("end",)),
            _ending("end", "The end.", "positive"),
        ]
    )


def _seam_ids(opening: str) -> list[str]:
    return [hit.node_id for hit in merge_seams(_merge_story(opening))]


# --------------------------------------------------------------------------
# Graph helpers
# --------------------------------------------------------------------------


def test_inbound_sources_counts_distinct_parents_and_ignores_self_loops() -> None:
    story = _story(
        [
            _node("start", targets=("a", "b")),
            _node("a", targets=("m", "a")),
            _node("b", targets=("m",)),
            _node("m"),
        ]
    )
    inbound = inbound_sources(story)
    assert inbound["m"] == frozenset({"a", "b"})
    assert inbound["a"] == frozenset({"start"})


def test_decisions_to_reach_is_the_minimum_not_the_fewest_taps() -> None:
    """Page turns are free: a long single-choice corridor beats one fork."""
    story = _story(
        [
            _node("start", targets=("fork", "c1")),
            _node("fork", targets=("x", "y")),
            _node("x", targets=("goal",)),
            _node("y"),
            _node("c1", targets=("c2",)),
            _node("c2", targets=("c3",)),
            _node("c3", targets=("goal",)),
            _node("goal"),
        ]
    )
    assert decisions_to_reach(story)["goal"] == 1
    assert decisions_to_reach(story)["x"] == 2


def test_two_labels_to_one_target_are_not_a_decision() -> None:
    story = _story([_node("start", targets=("a", "a")), _node("a")])
    assert decisions_to_reach(story)["a"] == 0


def test_state_counts_reads_variables_conditions_and_effects() -> None:
    story = _story([_node("start", targets=("a", "b")), _node("a"), _node("b")])
    story["variables"] = [{"name": "k"}]
    story["nodes"][0]["choices"][0]["condition"] = {"var": "k"}
    story["nodes"][0]["choices"][1]["effects"] = [{"op": "set"}]
    story["nodes"][1]["on_enter"] = [{"op": "inc"}]
    counts = state_counts(story)
    assert (counts.variables, counts.conditional_choices, counts.effects) == (1, 1, 2)
    assert not counts.stateless


# --------------------------------------------------------------------------
# Merge seams
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "opening",
    [
        "Whichever way Mira had come, every path had led her here at last.",
        (
            "However she got here, tonight of all nights, Wren arrives at the same "
            "certainty from three different directions."
        ),
        "Whatever thread Wren had followed to get here, it leaves her cold.",
        "Wherever the trail just led her, Wren ends up under a streetlight.",
        (
            "Whether she pulled the curtain back herself or only watched the gap, "
            "the berth was empty."
        ),
        "Either way, it was the sketch that won out in the end.",
        (
            "The threads knot together into one answer, no matter which of them "
            "Wren pulled on tonight to get here."
        ),
        "Every route through the storm had led to this one place.",
        "Both ways through the aviary brought Nia to the same place at last.",
        "Every wing of the museum had led Nia here, to the rotunda.",
        "The threads she had followed reconverged into a single answer.",
        (
            "The way down had been different for each of them, but it ended in the "
            "same place."
        ),
    ],
)
def test_merge_seam_catches_calibrated_route_erasing_openings(opening: str) -> None:
    assert _seam_ids(opening) == ["m"]


def test_merge_seam_scans_the_second_opening_sentence() -> None:
    assert _seam_ids("The cellar was cold. Every path had brought Rowan here.") == ["m"]


@pytest.mark.parametrize(
    "opening",
    [
        # Concessive opener with no history verb or route noun: in-scene.
        "Whatever it was, it was big.",
        "Wherever she looked, there was dust.",
        # "However," is the connective adverb, not a concessive opener.
        "However, the door held fast against her shoulder.",
        # Mid-sentence "however," in the 13-16 gamebook's stamina beats.
        (
            "Hold your pace and read each mark in turn, however, and you will keep "
            "the trail."
        ),
        # Ordinary staging of the merge room.
        "The rotunda was cold and dark under its glass dome.",
    ],
)
def test_merge_seam_ignores_calibrated_false_positive_classes(opening: str) -> None:
    assert _seam_ids(opening) == []


def test_merge_seam_requires_two_inbound_nodes() -> None:
    story = _story(
        [
            _node("start", targets=("m",)),
            _node("m", "Whichever way Mira had come, every path had led her here."),
        ]
    )
    assert merge_seams(story) == []


def test_merge_seam_ignores_the_phrase_deep_in_the_body() -> None:
    body = (
        "The rotunda was cold. Dust hung in the air. Nadia counted the doors. "
        "Whichever way she had come, it did not matter now."
    )
    assert _seam_ids(body) == []


def test_merge_seam_ignores_a_seam_spoken_by_a_character() -> None:
    assert _seam_ids("Whichever way you came, you got here, Gran said.") == []


# --------------------------------------------------------------------------
# Option recaps
# --------------------------------------------------------------------------


def _decision(body: str) -> dict[str, Any]:
    return _story(
        [
            _node("d", body, targets=("a", "b")),
            _ending("a", "The end.", "positive"),
            _ending("b", "The end.", "positive"),
        ]
    )


def _recap_kinds(body: str) -> tuple[str, ...] | None:
    hits = option_recaps(_decision(body))
    return hits[0].kinds if hits else None


@pytest.mark.parametrize(
    "tail",
    [
        "She could hum slow and sure into the tube. Or she could let her fear win out.",
        "Wren could creep along the catwalk, or she could dash across.",
        "She can climb toward the source or dig for it at ground level instead.",
        "They could put their weight into the side door, or take the high route.",
        "You can lead them across, split the party, or send scouts first.",
        "Should they trace the message? Or should they save the station?",
        "Should she lead them now? Or go back first?",
        (
            "Taking her hand at once might carry her through, or it might mean "
            "trusting a stranger."
        ),
    ],
)
def test_option_recap_catches_restated_options(tail: str) -> None:
    assert _recap_kinds("The pier was dark. " + tail) == ("enumerates",)


@pytest.mark.parametrize(
    "tail",
    [
        "Wren had a choice to make.",
        "Both choices feel urgent right now.",
        "Only one of them actually fits in the time she has left.",
        "She has to choose blind.",
        "Maya has only moments to decide.",
        "Nia weighed the butterflies against the beetles.",
        "She crouched there, unsure which would tell her more.",
        "Which plan would work best?",
        "Choose your way in.",
    ],
)
def test_option_recap_catches_announced_choices(tail: str) -> None:
    assert _recap_kinds("The pier was dark. " + tail) == ("announces",)


@pytest.mark.parametrize(
    "tail",
    [
        # Epistemic modals: a possibility, not an option the hero can take.
        "The carving might mean something, or it might mean nothing at all.",
        "It could wait, or it could not.",
        "Or the old wood might have gone soft under the paddle.",
        # "pick her way" is careful movement, not a choice.
        "Wren had to pick her way fast.",
        # A bare "Or" sentence carries no option.
        "Or so she thought.",
        # Comma-or followed by a non-verb.
        "She could see the lighthouse, or what was left of it.",
        # Weighing without "against" is physical.
        "She weighed the stone in her hand.",
        # Descriptive staging is the setup the buttons need.
        "One stair climbed toward the sky. One led down to the engines.",
    ],
)
def test_option_recap_ignores_calibrated_false_positive_classes(tail: str) -> None:
    assert _recap_kinds("The pier was dark. " + tail) is None


def test_option_recap_ignores_options_staged_in_dialogue() -> None:
    body = "The pier was dark. We could try the attic, or the shed, Gran said."
    assert _recap_kinds(body) is None


def test_option_recap_only_reads_the_closing_sentences() -> None:
    body = (
        "Wren had a choice to make. The pier creaked. The water slapped. "
        "Gulls cried. The wind rose."
    )
    assert _recap_kinds(body) is None


def test_option_recap_skips_single_choice_nodes() -> None:
    story = _story(
        [
            _node("d", "Wren had a choice to make.", targets=("a",)),
            _ending("a", "The end.", "positive"),
        ]
    )
    assert option_recaps(story) == []


# --------------------------------------------------------------------------
# Labels
# --------------------------------------------------------------------------


def _labelled(labels: tuple[str, ...], **metadata: str) -> dict[str, Any]:
    targets = tuple(f"t{i}" for i in range(len(labels)))
    return _story(
        [_node("d", "Mira looked around.", targets=targets, labels=labels)]
        + [_ending(t, "The end.", "positive") for t in targets],
        **metadata,
    )


@pytest.mark.parametrize(
    "label",
    [
        "Sit with what this means.",
        "Sit with Alder's kind hidden note.",
        "Take in the weight of it.",
        "Decide which question to chase.",
        "Decide she is imagining the pattern.",
        "Weigh what dark forever means.",
        "Choose an approach before zero.",
        "Think about what Gran said.",
    ],
)
def test_meta_label_catches_mental_acts(label: str) -> None:
    assert [h.label for h in label_defects(_labelled((label,))).meta] == [label]


@pytest.mark.parametrize(
    "label",
    [
        "Sit with Gran and let the tide finish the rescuing.",
        "Sit with the silent drover table.",
        "Decide to go without a wizard.",
        "Decide the ledge is too risky and back out.",
        "Think up a rescue plan for Stella.",
        "Trust the cracked rung.",
        "Go on.",
        "Press on.",
    ],
)
def test_meta_label_ignores_calibrated_false_positive_classes(label: str) -> None:
    assert label_defects(_labelled((label,))).meta == []


def test_jargon_label_catches_graph_vocabulary() -> None:
    labels = ("Feel your way to the hub.", "Turn to page 40.")
    assert len(label_defects(_labelled(labels)).jargon) == 2


@pytest.mark.parametrize(
    "label",
    [
        "Follow the downward branch.",
        "Take the coast path along the fence.",
        "Read the last log page.",
        "Float back and try again.",
        "Double back and start over.",
        "Turn to the great spring.",
    ],
)
def test_jargon_label_ignores_in_world_words(label: str) -> None:
    assert label_defects(_labelled((label,))).jargon == []


def test_second_person_label_is_flagged_over_third_person_prose() -> None:
    labels = ("Use your grandfather transmitter.", "Steady yourself.")
    defects = label_defects(_labelled(labels))
    assert defects.person.person == "third"
    assert [h.label for h in defects.second_person] == list(labels)
    assert defects.second_person[0].choice_id == "c_d_0"


@pytest.mark.parametrize(
    "label",
    [
        "Go collect Auntie Mo's thank-you.",
        "Say thank you to Gran.",
        'Ask "Are you lost?"',
    ],
)
def test_second_person_label_ignores_courtesies_and_quoted_speech(
    label: str,
) -> None:
    assert label_defects(_labelled((label,))).second_person == []


@pytest.mark.parametrize(
    "metadata",
    [
        {"narrative_style": "gamebook"},
        {"narrative_style": "prose", "narrative_person": "second"},
    ],
)
def test_second_person_label_respects_second_person_books(
    metadata: dict[str, str],
) -> None:
    story = _labelled(("Use your rope.",), **metadata)
    assert label_defects(story).second_person == []


def test_book_person_infers_second_person_from_the_narration() -> None:
    story = _story(
        [
            _node("a", "You climb the stair.", targets=("b",)),
            _node("b", "You open your pack.", labels=("Use your rope.",)),
        ]
    )
    story["nodes"][1]["choices"] = [
        {"id": "c", "label": "Use your rope.", "target": "a"}
    ]
    assert book_person(story).person == "second"
    assert label_defects(story).second_person == []


def test_book_person_declared_third_beats_the_measured_rate() -> None:
    story = _story([_node("a", "You climb the stair.")], narrative_person="third")
    assert book_person(story).person == "third"


# --------------------------------------------------------------------------
# Endings
# --------------------------------------------------------------------------


def _ending_story(body: str, valence: str = "negative") -> dict[str, Any]:
    return _story([_node("start", targets=("e",)), _ending("e", body, valence)])


@pytest.mark.parametrize(
    ("close", "reason"),
    [
        ("She turned her steps toward the long walk home to town.", "goes home"),
        ("Then she bikes home alone through the pouring rain.", "goes home"),
        ("Mira gave up the search.", "gives up"),
        ("Mira retreated into the lamp room.", "turns back"),
        ("The ledger stayed unread, its secrets safe for now.", "defers"),
        ("It was simply too risky tonight.", "too risky"),
        ("The entire trail has gone cold.", "trail gone cold"),
    ],
)
def test_give_up_ending_catches_the_hero_leaving(close: str, reason: str) -> None:
    hits = give_up_endings(_ending_story("The tower went dark. " + close))
    assert [(h.node_id, h.reason) for h in hits] == [("e", reason)]


@pytest.mark.parametrize(
    "body",
    [
        # Bedtime and consolation closes on non-negative endings.
        "She went back home. She was happy and tired.",
        "Home went a page of underground sky.",
    ],
)
def test_give_up_ending_ignores_positive_and_neutral_endings(body: str) -> None:
    assert give_up_endings(_ending_story(body, "positive")) == []
    assert give_up_endings(_ending_story(body, "neutral")) == []


@pytest.mark.parametrize(
    "close",
    [
        # Trapped, not quitting.
        "There is no way onward and no time left to turn back.",
        # A station giving up its dead is not the hero quitting.
        "The station gives up its dead.",
        # Only the closing sentences count.
    ],
)
def test_give_up_ending_ignores_calibrated_false_positive_classes(
    close: str,
) -> None:
    assert give_up_endings(_ending_story("The tunnel narrowed. " + close)) == []


def test_give_up_ending_only_reads_the_close() -> None:
    body = "She nearly walked home. Then she found the key. The vault opened. It held."
    assert give_up_endings(_ending_story(body)) == []


def test_early_setbacks_counts_decisions_not_page_turns() -> None:
    story = _story(
        [
            _node("start", targets=("x", "y")),
            _node("x", targets=("x2",)),
            _node("x2", targets=("bad",)),
            _ending("bad", "It went wrong."),
            _ending("y", "It went right.", "positive"),
        ]
    )
    hits = early_setbacks(story, max_decisions=1)
    assert [(h.node_id, h.decisions) for h in hits] == [("bad", 1)]
    assert early_setbacks(story, max_decisions=0) == []


# --------------------------------------------------------------------------
# Book report
# --------------------------------------------------------------------------


def test_agency_report_headline_names_merges_state_and_recaps() -> None:
    story = _merge_story("Whichever way Mira had come, every path had led her here.")
    report = agency_report(story)
    assert report.merge_nodes == 1
    assert report.decision_nodes == 1
    assert report.headline.startswith(
        "1 merge nodes, 1 of them tell the reader the route did not matter; "
        "0 variables, so no choice comes back;"
    )


def test_agency_report_headline_for_a_pure_tree_with_state() -> None:
    story = _decision("The pier was dark.")
    story["variables"] = [{"name": "k"}]
    story["nodes"][0]["choices"][0]["condition"] = {"var": "k"}
    headline = agency_report(story).headline
    assert headline.startswith("no merge nodes")
    assert "1 variables and 1 conditional choices carry earlier choices forward" in (
        headline
    )
