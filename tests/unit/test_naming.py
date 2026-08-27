"""Pin PN-1: a proper noun a reader can meet before the prose introduces it.

The discriminating case is `test_a_verb_before_a_name_is_not_a_gloss`. A first
prototype of this rule accepted any lowercase word immediately before a name as
a descriptor, which made "calls Biscuit" and "her dog Biscuit" indistinguishable
and reported `the-cave-of-echoes` as clean when it is the book the rule exists
for. Anchoring the gloss on a determiner is what separates a noun phrase from a
transitive verb without a part-of-speech tagger, so that test is the one that
must never be relaxed.

Calibration (2026-08-27, over the 31 committed filled books): 130 findings over
4,542 nodes, 2.86 per 100, median 2 per book, 3 books clean; 12 of the 130 are
one book's missing apostrophes rather than this rule's noise. The formulation
this replaces, a per-reference check over definite noun phrases, measured 3.48
findings per NODE and was abandoned (see `validator/continuity.py`). Proper
nouns are a decidable population where definite noun phrases are not, which is
the whole reason this rule is buildable and that one was not.
"""

from __future__ import annotations

from cyo_adventure.storybook.models import Node, Storybook
from cyo_adventure.validator.naming import (
    check_proper_noun_introduction,
    introduces,
    proper_noun_phrases,
)


def _story(nodes: list[Node], *, start: str = "n1") -> Storybook:
    """Build the smallest Storybook carrying a given set of node bodies.

    Args:
        nodes: The nodes, in the order the story declares them.
        start: The start node id.

    Returns:
        Storybook: The assembled story.
    """
    return Storybook.model_validate(
        {
            "schema_version": "2.0",
            "id": "sk_test",
            "version": 1,
            "title": "Test",
            "start_node": start,
            "variables": [],
            "metadata": {
                "age_band": "5-8",
                "reading_level": {
                    "scheme": "flesch_kincaid",
                    "target": 2.5,
                    "tolerance": 1.0,
                },
                "tier": 1,
                "themes": ["play"],
                "estimated_minutes": 5,
                "ending_count": sum(1 for node in nodes if node.is_ending),
                "content_flags": {
                    "violence": "none",
                    "scariness": "none",
                    "peril": "none",
                },
                "topology": "branch_and_bottleneck",
                "length": "short",
                "narrative_style": "prose",
            },
            "nodes": [node.model_dump() for node in nodes],
        }
    )


def _node(node_id: str, body: str, targets: list[str], *, ending: bool = False) -> Node:
    """Build one node with prose and outbound choices.

    Args:
        node_id: The node's id.
        body: The node's prose.
        targets: Ids this node offers a choice to.
        ending: Whether the node terminates a reading.

    Returns:
        Node: The assembled node.
    """
    return Node.model_validate(
        {
            "id": node_id,
            "body": body,
            "is_ending": ending,
            "ending": {
                "id": f"e_{node_id}",
                "valence": "positive",
                "kind": "success",
                "title": "The End",
            }
            if ending
            else None,
            "choices": [
                {"id": f"c_{node_id}_{i}", "label": f"Go {i}", "target": target}
                for i, target in enumerate(targets)
            ],
        }
    )


def _rule_ids(story: Storybook) -> list[str]:
    """Return the phrases PN-1 reports for a story, in report order.

    Args:
        story: The story to check.

    Returns:
        list[str]: The offending phrase quoted in each finding's message.
    """
    return [
        finding.message.split("'")[1]
        for finding in check_proper_noun_introduction(story).findings
    ]


# --- discovery -------------------------------------------------------------


def test_a_sentence_initial_capital_is_not_a_name() -> None:
    """ "The" leading a sentence names nothing and must not be discovered."""
    assert proper_noun_phrases("The tide went out. Ahead lay a cave.") == ()


def test_a_mid_sentence_capital_is_a_name() -> None:
    """A capitalised token inside a sentence is a proper-noun candidate."""
    assert proper_noun_phrases("She whistled for Biscuit.") == ("Biscuit",)


def test_consecutive_capitals_form_one_phrase() -> None:
    """A multi-word name is one entity, not one candidate per token."""
    assert proper_noun_phrases("They reached the Windvale Museum at last.") == (
        "Windvale Museum",
    )


def test_a_name_ending_in_s_survives_possessive_stripping() -> None:
    """ "Jess" must not be truncated to "Je" on the way to a comparison.

    Stripping a possessive with `rstrip("\'s")` strips any of those
    characters, not the suffix, so every name ending in "s" came back short.
    That silently HID the name rather than misreporting it: the head regex
    built from the truncated form matches nothing, the mention set comes back
    empty, and the rule skips the name entirely.
    """
    assert proper_noun_phrases("She waved at Jess and then at Thomas.") == (
        "Jess",
        "Thomas",
    )


def test_an_all_caps_token_is_not_a_name() -> None:
    """Signage and shouting are typography, not naming."""
    assert proper_noun_phrases("The sign read KEEP OUT in red paint.") == ()


# --- gloss detection -------------------------------------------------------


def test_a_determiner_anchored_noun_phrase_is_a_gloss() -> None:
    """ "her dog Biscuit" introduces Biscuit."""
    assert introduces("She went in with her dog Biscuit close behind.", "Biscuit")


def test_a_verb_before_a_name_is_not_a_gloss() -> None:
    """ "calls Biscuit" must not read as a descriptor.

    The defect that made the first prototype useless: without the determiner
    anchor, the transitive verb preceding a name is shaped exactly like a
    noun modifier, so every book looked introduced.
    """
    assert not introduces("She calls Biscuit back gently from the edge.", "Biscuit")


def test_an_appositive_is_a_gloss() -> None:
    """ "Tock, her tiny wind-up mouse" introduces Tock."""
    assert introduces("On her shoulder rode Tock, her tiny mouse.", "Tock")


def test_a_bare_name_is_not_a_gloss() -> None:
    """A name with nothing attached introduces nothing."""
    assert not introduces("Biscuit's tail thumped on the sand.", "Biscuit")


def test_a_title_introduces_the_name_it_precedes() -> None:
    """ "Mister Vole" carries its own descriptor."""
    assert introduces("Then Mister Vole opened the door.", "Vole")


# --- the rule --------------------------------------------------------------


def test_a_name_never_glossed_anywhere_is_reported() -> None:
    """The Cave of Echoes defect, reduced to two nodes."""
    story = _story(
        [
            _node(
                "n1", "Maya ducked under the rocks with Biscuit at her heels.", ["n2"]
            ),
            _node("n2", "Biscuit's tail thumped once.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == ["Biscuit"]


def test_a_name_glossed_on_arrival_is_not_reported() -> None:
    """A gloss anywhere every reader passes clears the name."""
    story = _story(
        [
            _node("n1", "Maya went in with her dog Biscuit at her heels.", ["n2"]),
            _node("n2", "Biscuit's tail thumped once.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


def test_a_gloss_on_an_optional_branch_does_not_cover_a_later_node() -> None:
    """Path-sensitivity: the reader who skipped the gloss still meets the name.

    ``n2`` introduces Pip; ``n3`` does not. Both reach ``n4``, which names Pip.
    A reader taking the ``n3`` branch arrives never having been told who Pip
    is, so the name is reported even though the book does introduce it.
    """
    story = _story(
        [
            _node("n1", "The deck was busy that morning.", ["n2", "n3"]),
            _node("n2", "A stowaway cat named Pip slipped past.", ["n4"]),
            _node("n3", "The ropes creaked in the wind.", ["n4"]),
            _node("n4", "Pip led the way below.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == ["Pip"]


def test_a_gloss_every_reader_passes_covers_a_later_node() -> None:
    """The same graph, with the gloss moved onto the dominating node."""
    story = _story(
        [
            _node("n1", "A stowaway cat named Pip slipped past.", ["n2", "n3"]),
            _node("n2", "The deck was busy that morning.", ["n4"]),
            _node("n3", "The ropes creaked in the wind.", ["n4"]),
            _node("n4", "Pip led the way below.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


def test_one_entity_named_two_ways_is_reported_once() -> None:
    """ "Doctor Nadia" and "Nadia" are one name and one fix.

    Both phrases share a head noun, so they select the same mentions and run
    the same coverage analysis; reporting both hands an author two rows for
    one edit. The bare form is the one reported, because that is the form a
    reader actually meets with nothing attached.
    """
    story = _story(
        [
            _node("n1", "The snow had drifted against the door.", ["n2", "n3"]),
            _node("n2", "The map was spread out for Doctor Nadia.", ["n4"]),
            _node("n3", "The wind picked up outside.", ["n4"]),
            _node("n4", "Then Nadia frowned at the ice.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == ["Nadia"]


def test_the_protagonist_is_exempt() -> None:
    """A HERO sentinel names the point-of-view character, who needs no gloss."""
    story = _story(
        [
            _node("n1", "{~HERO:Maya~} ducked under the rocks.", ["n2"]),
            _node("n2", "Maya climbed back into the light.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


def test_a_head_noun_used_lowercase_elsewhere_is_self_glossing() -> None:
    """ "the Windvale Museum" is introduced by the book's own word "museum"."""
    story = _story(
        [
            _node("n1", "She was locked inside the museum overnight.", ["n2"]),
            _node("n2", "The Windvale Museum was silent.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


def test_a_single_word_name_the_book_also_writes_lowercase_is_self_glossing() -> None:
    """ "the Keep" needs no gloss when the book also writes "the keep".

    The two-word case above and this one are the same rule. Restricting it to
    multi-word phrases cost 31 spurious findings across the committed corpus
    (``Keep``, ``Company``, ``Gallery``, ``Spoon``), and relaxing it is safe
    because a fill that never writes the common noun in lowercase, which is
    exactly ``the-cave-of-echoes`` and ``Biscuit``, still reports.
    """
    story = _story(
        [
            _node("n1", "She had slept in the keep since the frost came.", ["n2"]),
            _node("n2", "The Keep held its breath.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


def test_an_address_term_alone_is_its_own_descriptor() -> None:
    """ "Grandma" used as a name carries its own meaning.

    An address term is a common noun doing a name's job, so a reader who
    meets "Grandma" knows precisely who that is. This is the same reasoning
    as the title rule, applied to a name that is nothing but the title.
    """
    story = _story(
        [
            _node("n1", "The kitchen smelled of butter and cinnamon.", ["n2"]),
            _node("n2", "Then Grandma laughed out loud.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


def test_a_node_still_holding_a_fill_directive_is_skipped() -> None:
    """The rule reads prose, so an unfilled skeleton has nothing to say."""
    story = _story(
        [
            _node(
                "n1", "<<FILL role=setup words=40 beats='Maya meets Biscuit'>>", ["n2"]
            ),
            _node(
                "n2",
                "<<FILL role=rising words=40 beats='Biscuit runs'>>",
                [],
                ending=True,
            ),
        ]
    )
    assert _rule_ids(story) == []


def test_a_finding_is_a_warning_and_never_blocks() -> None:
    """PN-1 is advisory, on the same terms as every prose-reading rule here."""
    story = _story(
        [
            _node(
                "n1", "Maya ducked under the rocks with Biscuit at her heels.", ["n2"]
            ),
            _node("n2", "Biscuit's tail thumped once.", [], ending=True),
        ]
    )
    findings = check_proper_noun_introduction(story).findings
    assert [f.severity.value for f in findings] == ["warning"]
    assert [f.rule_id for f in findings] == ["PN-1"]
