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
    # Count first, on the SHIPPED list: a dropped or duplicated value
    # reports as "16 != N" rather than as an opaque set difference.
    assert len(CLOSED_VOCABULARIES["pet_species"]) == 16
    assert CLOSED_VOCABULARIES["pet_species"] == expected


def test_kinship_label_vocabulary_matches_the_accepted_list() -> None:
    """The 21-value kinship label list matches the proposal doc exactly."""
    # Count first, on the SHIPPED list: a dropped or duplicated value
    # reports as "21 != N" rather than as an opaque set difference.
    assert len(CLOSED_VOCABULARIES["kinship_label"]) == 21
    assert CLOSED_VOCABULARIES["kinship_label"] == _KINSHIP_LABELS


def test_dedication_vocabulary_matches_the_accepted_list() -> None:
    """`dedication` shares the identical 21-value kinship list (AL-068/ADR-023 row 8)."""
    # Count first, on the SHIPPED list: a dropped or duplicated value
    # reports as "21 != N" rather than as an opaque set difference.
    assert len(CLOSED_VOCABULARIES["dedication"]) == 21
    assert CLOSED_VOCABULARIES["dedication"] == _KINSHIP_LABELS


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
    # Count first, on the SHIPPED list: a dropped or duplicated value
    # reports as "12 != N" rather than as an opaque set difference.
    assert len(CLOSED_VOCABULARIES["home_type"]) == 12
    assert CLOSED_VOCABULARIES["home_type"] == expected


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
    # Count first, on the SHIPPED list: a dropped or duplicated value
    # reports as "12 != N" rather than as an opaque set difference.
    assert len(CLOSED_VOCABULARIES["favorite_color"]) == 12
    assert CLOSED_VOCABULARIES["favorite_color"] == expected


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
    # Count first, on the SHIPPED list: a dropped or duplicated value
    # reports as "12 != N" rather than as an opaque set difference.
    assert len(CLOSED_VOCABULARIES["favorite_food"]) == 12
    assert CLOSED_VOCABULARIES["favorite_food"] == expected


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
    # Count first, on the SHIPPED list: a dropped or duplicated value
    # reports as "12 != N" rather than as an opaque set difference.
    assert len(CLOSED_VOCABULARIES["favorite_hobby"]) == 12
    assert CLOSED_VOCABULARIES["favorite_hobby"] == expected


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


def test_no_vocabulary_member_exceeds_three_words() -> None:
    """No seeded value is longer than 3 words, the ceiling the catalog must clear.

    `validate_personalization_value` applies only the structural and denylist
    checks; it never applies a theme contract's own `max_words`, `pattern`, or
    `legacy_lexicon` constraints. So a personalizable slot authored onto a
    contract slot whose `max_words` is below the longest vocabulary member
    would store, and render into a child's prose, a value that contract would
    itself have rejected. Nothing on disk declares a `personalizable` slot
    yet, which is why this is a ceiling to hold rather than a bug to fix; the
    test exists so adding a longer member (say a 4-word food) fails here,
    where the ceiling is written down, instead of silently raising the bar the
    catalog has to clear.

    See the `#EDGE: data-integrity` note above `CLOSED_VOCABULARIES` in
    `storybook/personalization_values.py`.
    """
    too_long = {
        value
        for vocabulary in CLOSED_VOCABULARIES.values()
        for value in vocabulary
        if len(value.split()) > 3
    }
    assert too_long == set(), (
        f"value(s) {sorted(too_long)} exceed the 3-word ceiling; either shorten "
        "them or raise the ceiling here AND in the personalization_values.py "
        "#EDGE note, and re-check every catalog slot's max_words"
    )


def test_dedication_and_kinship_label_share_one_vocabulary() -> None:
    """The two kinship-shaped keys draw from the identical value set.

    They are separate keys because ADR-023 row 8 gives them different
    meanings (the dedication names the book's giver; the kinship label names
    the in-story trusted adult), but they have never been intended to hold
    different values. Pinned explicitly so the shared-list decision survives
    a future edit to one of them.
    """
    assert CLOSED_VOCABULARIES["dedication"] == CLOSED_VOCABULARIES["kinship_label"]
