"""The A21 residual retired-theme leak scan (validator/theme_leak.py).

Before A21, ``legacy_lexicon`` was only ever matched against a *proposed slot
value*. Nothing looked at the skeleton's own text, so a migration that left a
retired character's name hardcoded in a choice label passed all six acceptance
checks and then survived every re-theme. These tests pin the properties that
make the new scan trustworthy enough to gate CI on: it finds the decidable
class, it refuses to guess at the undecidable one, and it attributes each hit
to the slot that should have covered it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.storybook.theme_contract import ThemeContract
from cyo_adventure.validator.theme_leak import (
    proper_noun_terms,
    residual_theme_leaks,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def _contract(
    *, legacy_lexicon: list[str], default_binding: dict[str, str] | None = None
) -> ThemeContract:
    """Build a minimal one-slot contract for a leak scan.

    Args:
        legacy_lexicon: The retired theme's terms.
        default_binding: Overrides the single ``HERO`` default, so a test can
            control which slot a leaked term is attributed to.

    Returns:
        ThemeContract: The contract.
    """
    binding = default_binding if default_binding is not None else {"HERO": "Tock"}
    return ThemeContract.model_validate(
        {
            "contract_version": 1,
            "skeleton_slug": "fixture",
            "age_band": "8-11",
            "legacy_lexicon": legacy_lexicon,
            "default_binding": binding,
            "slots": [
                {"id": slot_id, "scope": "global", "meaning": f"the {slot_id}"}
                for slot_id in binding
            ],
        }
    )


def _skeleton(
    *, beats: str = "", title: str = "", label: str = ""
) -> Mapping[str, object]:
    """Build a one-node skeleton exercising the requested surfaces.

    Args:
        beats: Text for the node's ``<<FILL>>`` beats guidance; omitted when "".
        title: Text for the node's ending title; omitted when "".
        label: Text for a single choice label; omitted when "".

    Returns:
        Mapping[str, object]: The raw skeleton mapping.
    """
    node: dict[str, object] = {"id": "n1"}
    if beats:
        node["body"] = f"<<FILL role=setup words=80 beats='{beats}'>>"
    if title:
        node["ending"] = {"id": "e1", "title": title}
    if label:
        node["choices"] = [{"id": "c1", "label": label, "target": "n2"}]
    return {"nodes": [node]}


# ---------------------------------------------------------------------------
# proper_noun_terms: which lexicon entries are decidable at all
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "term",
    ["Tock", "Bone Field", "the Cold Mirror", "Warden Ivy", "Room 12"],
)
def test_a_naming_term_is_selected(term: str) -> None:
    """A term with a capitalized naming word is in the gateable class."""
    assert proper_noun_terms([term]) == (term,)


@pytest.mark.parametrize("term", ["sea cave", "brine", "tide pool", "the salt"])
def test_an_all_lowercase_term_is_excluded(term: str) -> None:
    """A generic term cannot be gated on: in prose it is just a word.

    This is the whole reason the check reports 273 rather than the 1,771 a
    stem-based scan over the full lexicon produces.
    """
    assert proper_noun_terms([term]) == ()


def test_a_leading_article_alone_does_not_make_a_term_nameable() -> None:
    """ "The" is capitalized by orthography, not because it names anything."""
    assert proper_noun_terms(["The"]) == ()
    assert proper_noun_terms(["The Quiet"]) == ("The Quiet",)


# ---------------------------------------------------------------------------
# residual_theme_leaks: the three surfaces
# ---------------------------------------------------------------------------


def test_a_leak_in_a_choice_label_is_found() -> None:
    """The 12-instance `Follow Tock.` case from the-clockwork-menagerie."""
    leaks = residual_theme_leaks(
        _skeleton(label="Follow Tock."), _contract(legacy_lexicon=["Tock"])
    )
    assert [(leak.term, leak.kind, leak.location) for leak in leaks] == [
        ("Tock", "label", "n1/c1")
    ]


def test_a_leak_in_an_ending_title_is_found() -> None:
    """The `The Cirrus Sails On` case from the-sky-ship-stowaway."""
    leaks = residual_theme_leaks(
        _skeleton(title="The Cirrus Sails On"),
        _contract(legacy_lexicon=["Cirrus"], default_binding={"SHIP_NAME": "Cirrus"}),
    )
    assert [(leak.term, leak.kind) for leak in leaks] == [("Cirrus", "title")]


def test_a_leak_in_beats_guidance_is_found() -> None:
    """Beats guidance is authored text too, and reaches the model verbatim."""
    leaks = residual_theme_leaks(
        _skeleton(beats="Okafor waits by the door"),
        _contract(legacy_lexicon=["Okafor"]),
    )
    assert [(leak.term, leak.kind) for leak in leaks] == [("Okafor", "beats")]


def test_the_fill_wrapper_itself_is_never_scanned() -> None:
    """A term colliding with `role`/`words` must not register as a leak.

    Only the inner ``beats='...'`` group is authored text; the wrapper is
    machine syntax, so a lexicon entry like "Setup" cannot be a hit there.
    """
    leaks = residual_theme_leaks(
        _skeleton(beats="a quiet room"), _contract(legacy_lexicon=["Setup", "FILL"])
    )
    assert leaks == ()


# ---------------------------------------------------------------------------
# Boundaries and false positives
# ---------------------------------------------------------------------------


def test_a_possessive_is_a_leak() -> None:
    """`Follow Alder's notes` leaks Alder just as much as `Follow Alder` does.

    Pinned because the first implementation treated an apostrophe as a
    word-interior character and silently missed all four of
    the-mapmakers-island's real hits.
    """
    leaks = residual_theme_leaks(
        _skeleton(label="Follow Alder's notes toward the camp."),
        _contract(legacy_lexicon=["Alder"], default_binding={"PREDECESSOR": "Alder"}),
    )
    assert [leak.term for leak in leaks] == ["Alder"]


def test_a_term_inside_a_longer_word_is_not_a_leak() -> None:
    """Substring matching would make the check unusable."""
    leaks = residual_theme_leaks(
        _skeleton(beats="the Tockington road"), _contract(legacy_lexicon=["Tock"])
    )
    assert leaks == ()


def test_matching_is_case_sensitive() -> None:
    """Capitalization is the only evidence separating a name from a noun.

    "Alder" the character is a leak; "alder" the tree is not, and casefolding
    (as ``validate_slot_bindings`` does) would conflate them.
    """
    leaks = residual_theme_leaks(
        _skeleton(beats="a stand of alder by the water"),
        _contract(legacy_lexicon=["Alder"]),
    )
    assert leaks == ()


def test_a_slot_id_is_not_mistaken_for_a_leak() -> None:
    """`{ALDER_CHART}` is machine text, not a hardcoded name."""
    leaks = residual_theme_leaks(
        _skeleton(label="Read {ALDER_CHART} again."),
        _contract(
            legacy_lexicon=["ALDER_CHART"],
            default_binding={"ALDER_CHART": "the ALDER_CHART"},
        ),
    )
    assert leaks == ()


def test_blanking_a_token_cannot_fuse_two_words() -> None:
    """Token removal must leave a separator, or it would invent matches."""
    leaks = residual_theme_leaks(
        _skeleton(beats="Bone{X}Field is not Bone Field"),
        _contract(legacy_lexicon=["Bone Field"], default_binding={"X": "Bone Field"}),
    )
    # Exactly one hit, from the genuine trailing "Bone Field", not two.
    assert [leak.term for leak in leaks] == ["Bone Field"]


# ---------------------------------------------------------------------------
# Attribution: which fixes are mechanical
# ---------------------------------------------------------------------------


def test_a_leak_names_the_slot_that_should_have_covered_it() -> None:
    """Attribution is what separates a surface rewrite from a contract change."""
    leaks = residual_theme_leaks(
        _skeleton(label="Follow Tock."),
        _contract(
            legacy_lexicon=["Tock"],
            default_binding={
                "COMPANION": "Tock the brass sparrow",
                "PLACE": "the yard",
            },
        ),
    )
    assert leaks[0].owning_slot_ids == ("COMPANION",)


def test_an_unowned_leak_reports_no_slot() -> None:
    """the-midnight-frequency's 3 leaks: no slot exists, so the fix is bigger."""
    leaks = residual_theme_leaks(
        _skeleton(beats="Okafor waits"),
        _contract(legacy_lexicon=["Okafor"], default_binding={"HERO": "Mira"}),
    )
    assert leaks[0].owning_slot_ids == ()


def test_an_empty_lexicon_short_circuits() -> None:
    """A contract with no naming terms can carry no decidable leak."""
    assert (
        residual_theme_leaks(
            _skeleton(beats="anything at all"), _contract(legacy_lexicon=[])
        )
        == ()
    )
