"""Pin PN-1: a proper noun a reader can meet before the prose introduces it.

The discriminating case is `test_a_verb_before_a_name_is_not_a_gloss`. A first
prototype of this rule accepted any lowercase word immediately before a name as
a descriptor, which made "calls Biscuit" and "her dog Biscuit" indistinguishable
and reported `the-cave-of-echoes` as clean when it is the book the rule exists
for. Anchoring the gloss on a determiner is what separates a noun phrase from a
transitive verb without a part-of-speech tagger, so that test is the one that
must never be relaxed.

Calibration (2026-08-28, over the 31 committed filled books): 135 findings over
4,542 nodes, 2.97 per 100, median 2 per book, max 34, 3 books clean; 12 of the
135 are a name reported twice (eleven from one book that emitted no
apostrophes, one genuine plural) rather than this rule's noise. The
formulation this replaces, a per-reference check over definite noun phrases,
measured 3.48 findings per NODE and was abandoned (see
`validator/continuity.py`). Proper nouns are a decidable population where
definite noun phrases are not, which is the whole reason this rule is buildable
and that one was not.
"""

from __future__ import annotations

import pytest

from cyo_adventure.storybook.models import Node, Storybook
from cyo_adventure.validator import naming
from cyo_adventure.validator.naming import (
    check_proper_noun_introduction,
    introduces,
    proper_noun_phrases,
)

# Named rather than inlined for the same reason `validator/naming.py` names it:
# a bare typographic apostrophe in a literal is an ambiguous unicode character,
# and filled prose carries whichever apostrophe the provider emitted.
_RIGHT_SINGLE = "\u2019"


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


def _node(
    node_id: str,
    body: str,
    targets: list[str],
    *,
    ending: bool = False,
    labels: list[str] | None = None,
) -> Node:
    """Build one node with prose and outbound choices.

    Args:
        node_id: The node's id.
        body: The node's prose.
        targets: Ids this node offers a choice to.
        ending: Whether the node terminates a reading.
        labels: Choice labels, positionally matched to *targets*. Defaults to
            filler text, and matters only to the test that pins choice labels
            as out of scope.

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
                {
                    "id": f"c_{node_id}_{i}",
                    "label": labels[i] if labels else f"Go {i}",
                    "target": target,
                }
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


@pytest.mark.unit
def test_a_sentence_initial_capital_is_not_a_name() -> None:
    """ "The" leading a sentence names nothing and must not be discovered."""
    assert proper_noun_phrases("The tide went out. Ahead lay a cave.") == ()


@pytest.mark.unit
def test_a_mid_sentence_capital_is_a_name() -> None:
    """A capitalised token inside a sentence is a proper-noun candidate."""
    assert proper_noun_phrases("She whistled for Biscuit.") == ("Biscuit",)


@pytest.mark.unit
def test_consecutive_capitals_form_one_phrase() -> None:
    """A multi-word name is one entity, not one candidate per token."""
    assert proper_noun_phrases("They reached the Windvale Museum at last.") == (
        "Windvale Museum",
    )


@pytest.mark.unit
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


@pytest.mark.unit
def test_an_all_caps_token_is_not_a_name() -> None:
    """Signage and shouting are typography, not naming."""
    assert proper_noun_phrases("The sign read KEEP OUT in red paint.") == ()


@pytest.mark.unit
def test_a_capitalised_pronoun_or_connective_names_nothing() -> None:
    """Capitalisation inside a sentence is not on its own evidence of naming.

    Two shapes reach this: a pronoun opening reported speech, and the
    connectives inside a title-cased name. Both are capitalised mid-sentence,
    where the sentence-initial rule cannot reach them, and neither names an
    entity, so the naming filter is the only thing standing between them and
    a finding an author cannot act on.
    """
    assert proper_noun_phrases("Then It rolled away downhill.") == ()
    assert proper_noun_phrases("She read The Book Of Names aloud.") == ("Book Names",)


@pytest.mark.unit
def test_an_abbreviated_title_does_not_end_a_sentence() -> None:
    """The period in "Mr." is orthography, not a sentence boundary.

    Splitting there made "Whiskers" the first token of a new sentence, and a
    sentence-initial capital carries no evidence, so the cat vanished from
    discovery entirely. Three of the 31 committed books write abbreviated
    address terms ("Mr. Fez", "Ms. Flores", "Mrs. Okafor", "Mr. Pell").
    """
    assert proper_noun_phrases("Her cat Mr. Whiskers purred loudly.") == (
        "Mr",
        "Whiskers",
    )


@pytest.mark.unit
def test_a_typographic_possessive_is_the_same_name() -> None:
    """A curly apostrophe must strip exactly as the ASCII one does.

    Filled prose carries whichever apostrophe the provider emitted, so a book
    written with U+2019 would otherwise read every possessive as a separate
    name and match none of them back to the name itself.
    """
    assert proper_noun_phrases(f"She tugged at Nell{_RIGHT_SINGLE}s sleeve.") == (
        "Nell",
    )
    assert introduces(f"She patted her dog Biscuit{_RIGHT_SINGLE}s head.", "Biscuit")


# --- gloss detection -------------------------------------------------------


@pytest.mark.unit
def test_a_determiner_anchored_noun_phrase_is_a_gloss() -> None:
    """ "her dog Biscuit" introduces Biscuit."""
    assert introduces("She went in with her dog Biscuit close behind.", "Biscuit")


@pytest.mark.unit
def test_a_verb_before_a_name_is_not_a_gloss() -> None:
    """ "calls Biscuit" must not read as a descriptor.

    The defect that made the first prototype useless: without the determiner
    anchor, the transitive verb preceding a name is shaped exactly like a
    noun modifier, so every book looked introduced.
    """
    assert not introduces("She calls Biscuit back gently from the edge.", "Biscuit")


@pytest.mark.unit
def test_an_appositive_is_a_gloss() -> None:
    """ "Tock, her tiny mouse" introduces Tock.

    The obvious fixture, "On her shoulder rode Tock, her tiny mouse.", never
    reaches the appositive test at all: the pre-modifier walk goes back over
    "rode" and "shoulder" onto the determiner "her" and short-circuits the
    `or` chain, so the appositive arm could be deleted with the suite green.
    This shape closes the pre-modifier route with a phrase break and leaves
    the appositive as the only arm that can answer.
    """
    assert introduces("Then Tock, her tiny mouse, went in.", "Tock")


@pytest.mark.unit
def test_a_bare_name_is_not_a_gloss() -> None:
    """A name with nothing attached introduces nothing."""
    assert not introduces("Biscuit's tail thumped on the sand.", "Biscuit")


@pytest.mark.unit
def test_a_copula_before_a_determiner_is_a_gloss() -> None:
    """ "Biscuit is her dog" introduces Biscuit.

    The copular arm had no test of its own and could be deleted with the
    whole suite green. Nothing else can answer this shape: there is no
    pre-modifier to walk back over and no comma to open an appositive.
    """
    assert introduces("Biscuit is her dog.", "Biscuit")


@pytest.mark.unit
def test_a_copula_without_a_determiner_is_not_a_gloss() -> None:
    """A copula followed by an adjective describes, it does not introduce."""
    assert not introduces("Biscuit was quick and clever.", "Biscuit")


@pytest.mark.unit
def test_a_title_inside_the_phrase_introduces_it() -> None:
    """ "Captain Reed" carries its title inside the phrase, not before it.

    The walk back over the phrase's own capitalised tokens has to test each
    one as it passes, because for this phrase the address term IS one of the
    tokens; testing only the word before the phrase reaches "Then" and
    answers no.
    """
    assert introduces("Then Captain Reed opened the hatch.", "Captain Reed")


@pytest.mark.unit
def test_a_title_introduces_the_name_it_precedes() -> None:
    """ "Mister Vole" carries its own descriptor."""
    assert introduces("Then Mister Vole opened the door.", "Vole")


# --- the rule --------------------------------------------------------------


@pytest.mark.unit
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


@pytest.mark.unit
def test_a_name_glossed_on_arrival_is_not_reported() -> None:
    """A gloss anywhere every reader passes clears the name."""
    story = _story(
        [
            _node("n1", "Maya went in with her dog Biscuit at her heels.", ["n2"]),
            _node("n2", "Biscuit's tail thumped once.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
def test_the_protagonist_is_exempt() -> None:
    """A HERO sentinel names the point-of-view character, who needs no gloss.

    The hero mention has to sit mid-sentence. The first version of this test
    opened both bodies with her name, so Maya was sentence-initial in both and
    discovery never proposed her at all; the assertion held with the whole
    exemption deleted and pinned nothing.
    """
    story = _story(
        [
            _node("n1", "Then {~HERO:Maya~} ducked under the rocks.", ["n2"]),
            _node("n2", "Maya climbed back into the light.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


@pytest.mark.unit
def test_a_protagonist_sentinel_names_the_hero() -> None:
    """PROTAGONIST is the catalog's other slot id for the same character."""
    story = _story(
        [
            _node("n1", "Then {~PROTAGONIST:Maya~} ducked under the rocks.", ["n2"]),
            _node("n2", "Maya climbed back into the light.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


@pytest.mark.unit
def test_an_undeclared_protagonist_is_reported() -> None:
    """With no sentinel the exemption has nothing to read and stays silent.

    This is the ordinary case for every committed artifact: all 31 predate
    ADR-023 and carry no sentinels, so each reports its own hero and each
    corpus figure in the module docstring includes one finding a sentinelized
    fill would not produce. The rule is not entitled to guess the hero from
    the prose, so this reports, and that is the intended answer rather than a
    gap to close by inference.
    """
    story = _story(
        [
            _node("n1", "Then Maya ducked under the rocks.", ["n2"]),
            _node("n2", "Maya climbed back into the light.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == ["Maya"]


@pytest.mark.unit
def test_a_place_sharing_a_hero_token_is_still_reported() -> None:
    """The exemption covers the protagonist, not everything named after her.

    Testing each word of a phrase against the hero tokens erased a distinct
    entity that merely shared one. Under hero ``Maya`` a peak called ``Maya
    Mountain`` vanished from the report while the identical book under an
    unrelated hero reported it, so the control below is the whole point of
    the test: without it, an exemption that swallowed every phrase would
    still pass the first assertion.
    """

    def peak(hero: str) -> list[str]:
        return _rule_ids(
            _story(
                [
                    _node("n1", f"Then {{~HERO:{hero}~}} woke early.", ["n2"]),
                    _node(
                        "n2",
                        "Far off stood Maya Mountain, sharp against the sky.",
                        [],
                        ending=True,
                    ),
                ]
            )
        )

    assert peak("Maya") == ["Maya Mountain"]
    assert peak("Tam") == ["Maya Mountain"]


@pytest.mark.unit
def test_a_titled_hero_is_exempt() -> None:
    """A title in front of the hero's name is still the hero.

    This is what the whole-phrase hero test has to keep working. Narrowing
    the exemption to an exact name match would fix the namesake defect above
    by reporting ``Marshal Hedda`` in a book that declares Hedda its
    protagonist, trading a false negative for a false positive.
    """
    story = _story(
        [
            _node("n1", "Then {~HERO:Hedda~} woke early.", ["n2"]),
            _node("n2", "The others waited on Marshal Hedda.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


@pytest.mark.unit
def test_a_name_in_every_node_is_still_reported() -> None:
    """Frequency is the worst available proxy for "needs no introduction".

    ``the-cave-of-echoes`` names Biscuit in all 65 of its 65 nodes and never
    once says he is a dog, so any share-based hero rule erases precisely the
    defect this rule exists for. Two nodes cannot show that, because a
    plausible share rule would carry a minimum book size and go vacuous on
    them; six can. The exemption must come from the declared sentinel and
    never from a count.
    """
    ids = [f"n{i}" for i in range(1, 7)]
    story = _story(
        [
            _node(
                node_id,
                f"Ahead, Biscuit waited by the water at stop {index}.",
                [] if node_id == ids[-1] else [ids[index]],
                ending=node_id == ids[-1],
            )
            for index, node_id in enumerate(ids, start=1)
        ]
    )
    assert _rule_ids(story) == ["Biscuit"]


@pytest.mark.unit
def test_a_head_noun_used_lowercase_elsewhere_is_self_glossing() -> None:
    """ "the Windvale Museum" is introduced by the book's own word "museum"."""
    story = _story(
        [
            _node(
                "n1",
                "She was locked inside the museum overnight, and the museum was dark.",
                ["n2"],
            ),
            _node("n2", "The Windvale Museum was silent.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


@pytest.mark.unit
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
            _node(
                "n1",
                "She had slept in the keep since the frost came, and the keep "
                "had held.",
                ["n2"],
            ),
            _node("n2", "The Keep held its breath.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


@pytest.mark.unit
def test_one_incidental_lowercase_use_does_not_exempt_a_name() -> None:
    """One lowercase use is as likely to be a miscasing as a common noun.

    ``the-salt-archive`` writes "Verrin" capitalised 38 times and lowercase
    exactly once, in "...what elias verrin could set down...", which is the
    same proper name the fill failed to capitalise rather than the word the
    name was built from. Taking that as self-glossing killed 51 of 181
    findings across the corpus, so the evidence has to be more than
    incidental: one mention of a rusty gate does not introduce a dog.
    """
    story = _story(
        [
            _node("n1", "She pushed past a rusty gate and went on.", ["n2"]),
            _node("n2", "Then Rusty barked twice.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == ["Rusty"]


@pytest.mark.unit
def test_two_lowercase_uses_of_a_head_noun_exempt_a_name() -> None:
    """The same story, with the word used as a common noun rather than once.

    Two is the floor, and it is what keeps the correct exemptions the rule
    depends on: "Astronomy Hall", "Map Room" and "Windvale Museum" all clear
    it comfortably.
    """
    story = _story(
        [
            _node(
                "n1",
                "She pushed past a rusty gate and then a rusty hinge.",
                ["n2"],
            ),
            _node("n2", "Then Rusty barked twice.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
def test_an_abbreviated_title_introduces_the_name_it_precedes() -> None:
    """ "Mr. Vole" introduces Vole exactly as "Mister Vole" does.

    The costly half of the sentence-splitter defect. Splitting on the period
    of "Mr." left the bare "Vole" of the second node with no introducing node
    anywhere, so this book reported a name it had introduced in its first
    sentence, while the unabbreviated control below reported nothing. Two
    spellings of the same address term must not give two answers.
    """
    story = _story(
        [
            _node("n1", "Then Mr. Vole opened the door.", ["n2"]),
            _node("n2", "Then Vole shuffled off down the hall.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == []

    control = _story(
        [
            _node("n1", "Then Mister Vole opened the door.", ["n2"]),
            _node("n2", "Then Vole shuffled off down the hall.", [], ending=True),
        ]
    )
    assert _rule_ids(control) == []


@pytest.mark.unit
def test_a_bare_name_collapses_into_its_titled_form() -> None:
    """ "Marshal Hedda" and a later bare "Hedda" are one entity and one edit.

    One direction of the collapse rule: the bare form is a suffix of the
    titled one, so they fold together and the author gets one row. Without
    the fold both phrases select the same mentions, run the same coverage
    analysis, and report the same defect twice.
    """
    story = _story(
        [
            _node("n1", "The snow had drifted against the door.", ["n2", "n3"]),
            _node("n2", "The map was spread out for Marshal Hedda.", ["n4"]),
            _node("n3", "The wind picked up outside.", ["n4"]),
            _node("n4", "Then Hedda frowned at the ice.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == ["Hedda"]


@pytest.mark.unit
def test_distinct_names_sharing_a_head_noun_stay_distinct() -> None:
    """The other direction: two places are not one place.

    "Stone Hollow" and "Green Hollow" share a head noun and neither is a
    suffix of the other. Folding them on the head alone kept whichever the
    discovery order reached first, so the introduced one silently answered
    for the un-introduced one and the finding was lost; the same book written
    with distinct heads reported it.
    """
    story = _story(
        [
            _node("n1", "The road ran past the ruined mill Stone Hollow.", ["n2"]),
            _node("n2", "They turned north toward Green Hollow.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == ["Green Hollow"]


@pytest.mark.unit
def test_a_contraction_is_not_a_name() -> None:
    """ "I'm" is a capitalised pronoun with a suffix, and names nothing.

    Both apostrophes reach this: filled prose carries whichever one the
    provider emitted, so the ASCII and typographic spellings have to answer
    alike.
    """
    for mark in ("'", _RIGHT_SINGLE):
        story = _story(
            [
                _node("n1", "The door creaked open at last.", ["n2"]),
                _node(
                    "n2",
                    f'Nell called out, "I{mark}m ready now," and stepped through.',
                    [],
                    ending=True,
                ),
            ]
        )
        assert _rule_ids(story) == []


@pytest.mark.unit
def test_a_calendar_term_or_interjection_is_not_a_name() -> None:
    """ "Monday" and "Hooray" are capitalised without naming anything."""
    story = _story(
        [
            _node("n1", "The kitchen was warm and quiet.", ["n2"]),
            _node(
                "n2",
                "Then Monday came at last, and she shouted Hooray.",
                [],
                ending=True,
            ),
        ]
    )
    assert _rule_ids(story) == []


@pytest.mark.unit
def test_a_typographic_possessive_still_names_the_bare_form() -> None:
    """A book written with U+2019 reports the name, not the possessive.

    Only the ASCII apostrophe was asserted anywhere, though the possessive
    suffixes and the token pattern both carry explicit handling for the
    typographic one.
    """
    story = _story(
        [
            _node("n1", f"She tugged at Nell{_RIGHT_SINGLE}s sleeve.", ["n2"]),
            _node("n2", "The door swung wide.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == ["Nell"]


@pytest.mark.unit
def test_a_name_met_first_in_a_choice_label_is_out_of_scope() -> None:
    """A KNOWN BOUNDARY, asserted so that it changes deliberately or not at all.

    The rule reads node bodies only, so a reader who meets a name first in a
    choice label gets no finding. That is a real gap and not a claim the gap
    does not matter; widening the scan to labels would re-calibrate every
    published corpus figure, which is a separate decision from this one. The
    second story is the same sentence moved into a body, and it reports.
    """
    labelled = _story(
        [
            _node(
                "n1",
                "The path forked at the old fence.",
                ["n2"],
                labels=["Follow Biscuit into the woods"],
            ),
            _node("n2", "The woods were quiet.", [], ending=True),
        ]
    )
    assert _rule_ids(labelled) == []

    in_body = _story(
        [
            _node("n1", "She would follow Biscuit into the woods.", ["n2"]),
            _node("n2", "The woods were quiet.", [], ending=True),
        ]
    )
    assert _rule_ids(in_body) == ["Biscuit"]


def _budget_story() -> Storybook:
    """Return a story whose scan cost is exactly its character count.

    Exactly one name survives exemption, so the product the scan budget
    bounds is the prose volume itself and the boundary needs no arithmetic.

    Returns:
        Storybook: The two-node story.
    """
    return _story(
        [
            _node(
                "n1", "Maya ducked under the rocks with Biscuit at her heels.", ["n2"]
            ),
            _node("n2", "Biscuit's tail thumped once.", [], ending=True),
        ]
    )


@pytest.mark.unit
def test_a_story_inside_the_scan_budget_is_scanned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A story sitting exactly on the budget is checked, not waved through."""
    story = _budget_story()
    volume = sum(len(node.body) for node in story.nodes)
    monkeypatch.setattr(naming, "_SCAN_BUDGET", volume)
    assert _rule_ids(story) == ["Biscuit"]


@pytest.mark.unit
def test_a_story_past_the_scan_budget_is_skipped_out_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One character past the budget the rule declines, and says it declined.

    The cost is names times prose and the caller pays it synchronously on the
    per-edit gate path, holding a worker thread and a database session for
    the duration, so the scan needs a ceiling. What it must not do is drop
    the story quietly: a story nobody checked and a story with nothing to
    report are the same empty answer, and only this finding tells them apart.
    """
    story = _budget_story()
    volume = sum(len(node.body) for node in story.nodes)
    monkeypatch.setattr(naming, "_SCAN_BUDGET", volume - 1)
    findings = check_proper_noun_introduction(story).findings
    assert len(findings) == 1
    assert findings[0].rule_id == "PN-1"
    assert findings[0].severity.value == "warning"
    assert "NOT CHECKED" in findings[0].message
    assert "Biscuit" not in findings[0].message


@pytest.mark.unit
def test_an_appositive_without_a_determiner_is_not_a_gloss() -> None:
    """ "Tock, waving wildly" is a participle, not a descriptor.

    The mirror of the copular pair: the appositive arm is anchored on a
    determiner for the same reason the pre-modifier arm is, and without that
    anchor any comma after a name would read as a gloss.
    """
    assert not introduces("Then Tock, waving wildly, went in.", "Tock")


@pytest.mark.unit
def test_a_titled_form_met_after_the_bare_name_is_still_one_entity() -> None:
    """The collapse holds whichever order the two forms are discovered in.

    ``test_a_bare_name_collapses_into_its_titled_form`` meets "Marshal Hedda"
    first; this book meets the bare "Hedda" first and must still produce one
    row rather than two.
    """
    story = _story(
        [
            _node("n1", "Then Hedda frowned at the ice.", ["n2"]),
            _node(
                "n2",
                "The map was spread out for Marshal Hedda.",
                [],
                ending=True,
            ),
        ]
    )
    assert _rule_ids(story) == ["Hedda"]


@pytest.mark.unit
def test_a_non_hero_sentinel_grants_no_exemption() -> None:
    """Only a hero slot exempts; a companion slot is an ordinary name.

    The sentinel scan reads every slot in the body and keeps only the hero
    ones. Widening it to any sentinel would exempt exactly the companion this
    rule was built for, since `the-cave-of-echoes` binds "Biscuit" through
    `COMPANION`.
    """
    story = _story(
        [
            _node("n1", "Then {~COMPANION:Biscuit~} barked at the gate.", ["n2"]),
            _node("n2", "The gate swung open.", [], ending=True),
        ]
    )
    assert _rule_ids(story) == ["Biscuit"]
