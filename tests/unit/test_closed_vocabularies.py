"""Membership tests for `CLOSED_VOCABULARIES` (ADR-023 Task D6).

One test per vocabulary, each asserting exact set equality (not just
membership of a sample) plus the accepted count, against the lists the owner
reviewed and accepted on 2026-07-29 in
`docs/planning/personalization-closed-vocabularies-proposal.md`. These tests
exist so a future hand-edit to `CLOSED_VOCABULARIES` (an added, removed, or
mis-typed value) fails loudly and locally, rather than only surfacing through
the broader drift guard in `test_personalization_vocab_drift.py` (which pins
`CLOSED_VOCABULARIES`'s key set against the DB CHECK and the taxonomy, not
its per-key contents) or through production behavior.

No case normalization anywhere (owner decision): every set below is
reproduced in the exact case the proposal doc specifies.
"""

from __future__ import annotations

from cyo_adventure.storybook.personalization_values import CLOSED_VOCABULARIES

_KINSHIP_LABELS = frozenset(
    {
        "Mom",
        "Dad",
        "Grandma",
        "Grandpa",
        "Nana",
        "Papa",
        "Gran",
        "Pop",
        "Abuela",
        "Abuelo",
        "Oma",
        "Opa",
        "Auntie",
        "Aunt",
        "Uncle",
        "Mama",
        "Mommy",
        "Daddy",
        "Nonna",
        "Nonno",
        "Grown-up",
    }
)


def test_pet_species_vocabulary_matches_the_accepted_list() -> None:
    """The 16-value pet species list matches the proposal doc exactly."""
    expected = frozenset(
        {
            "dog",
            "cat",
            "rabbit",
            "hamster",
            "fish",
            "bird",
            "guinea pig",
            "turtle",
            "lizard",
            "snake",
            "frog",
            "hermit crab",
            "chicken",
            "ferret",
            "goat",
            "horse",
        }
    )
    assert CLOSED_VOCABULARIES["pet_species"] == expected
    assert len(expected) == 16


def test_kinship_label_vocabulary_matches_the_accepted_list() -> None:
    """The 21-value kinship label list matches the proposal doc exactly."""
    assert CLOSED_VOCABULARIES["kinship_label"] == _KINSHIP_LABELS
    assert len(_KINSHIP_LABELS) == 21


def test_dedication_vocabulary_matches_the_accepted_list() -> None:
    """`dedication` shares the identical 21-value kinship list (AL-068/ADR-023 row 8)."""
    assert CLOSED_VOCABULARIES["dedication"] == _KINSHIP_LABELS
    assert len(_KINSHIP_LABELS) == 21


def test_home_type_vocabulary_matches_the_accepted_list() -> None:
    """The 12-value home type list matches the proposal doc exactly."""
    expected = frozenset(
        {
            "house",
            "apartment",
            "farm",
            "cabin",
            "houseboat",
            "trailer",
            "cottage",
            "condo",
            "duplex",
            "ranch",
            "bungalow",
            "tent",
        }
    )
    assert CLOSED_VOCABULARIES["home_type"] == expected
    assert len(expected) == 12


def test_favorite_color_vocabulary_matches_the_accepted_list() -> None:
    """The 12-value favorite color list matches the proposal doc exactly."""
    expected = frozenset(
        {
            "red",
            "blue",
            "green",
            "purple",
            "yellow",
            "orange",
            "pink",
            "black",
            "white",
            "teal",
            "silver",
            "gold",
        }
    )
    assert CLOSED_VOCABULARIES["favorite_color"] == expected
    assert len(expected) == 12


def test_favorite_food_vocabulary_matches_the_accepted_list() -> None:
    """The 12-value favorite food list matches the proposal doc exactly."""
    expected = frozenset(
        {
            "pizza",
            "tacos",
            "ice cream",
            "pancakes",
            "spaghetti",
            "burgers",
            "waffles",
            "sushi",
            "mac and cheese",
            "strawberries",
            "cookies",
            "soup",
        }
    )
    assert CLOSED_VOCABULARIES["favorite_food"] == expected
    assert len(expected) == 12


def test_favorite_hobby_vocabulary_matches_the_accepted_list() -> None:
    """The 12-value favorite hobby list matches the proposal doc exactly."""
    expected = frozenset(
        {
            "soccer",
            "dancing",
            "drawing",
            "swimming",
            "dinosaurs",
            "space",
            "robots",
            "reading",
            "gymnastics",
            "building blocks",
            "biking",
            "singing",
        }
    )
    assert CLOSED_VOCABULARIES["favorite_hobby"] == expected
    assert len(expected) == 12


def test_closed_vocabularies_has_exactly_the_seven_seeded_keys() -> None:
    """No stray key was added or dropped alongside the seeded lists.

    Guards against a copy-paste key typo (e.g. `favorite_colour`) that would
    otherwise pass every per-key test above by simply never being checked.
    """
    assert set(CLOSED_VOCABULARIES) == {
        "pet_species",
        "kinship_label",
        "dedication",
        "home_type",
        "favorite_color",
        "favorite_food",
        "favorite_hobby",
    }
