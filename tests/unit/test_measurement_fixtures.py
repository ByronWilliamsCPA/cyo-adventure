"""Unit tests for the sentinel-survival measurement fixtures (plan 3.4).

Covers loading a real skeleton+contract pair, building a personalized
specimen (the flipped slots actually carry sentinels, choice labels stay
bare, the flipped contract passes normal contract validation), and the
identity-safety invariant that every sentinel inner value is a generic
default, never a real name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.measurement.fixtures import (
    _CANDIDATES,  # pyright: ignore[reportPrivateUsage]
    DEFAULT_FIXTURES,
    _personalize_contract,  # pyright: ignore[reportPrivateUsage]
    build_specimen,
    load_pair,
)
from cyo_adventure.storybook.sentinels import SENTINEL_RE, wrap
from cyo_adventure.storybook.theme_contract import ThemeContract

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_GENERIC_WORDS = frozenset(word for _, word, _ in _CANDIDATES)


def _choice_labels(bound_skeleton: dict[str, object]) -> list[str]:
    labels: list[str] = []
    for node in bound_skeleton["nodes"]:  # type: ignore[index]
        labels.extend(choice["label"] for choice in node.get("choices", []))
    return labels


@pytest.mark.unit
def test_load_pair_loads_a_real_catalog_fixture() -> None:
    """load_pair reads a real skeleton+contract pair off disk."""
    skeleton, contract = load_pair(_SKELETONS_ROOT, "3-5", "puddle-jumping-day")
    assert skeleton["id"]
    assert isinstance(contract, ThemeContract)
    assert str(contract.age_band) == "3-5"


@pytest.mark.unit
def test_load_pair_missing_skeleton_raises() -> None:
    """A missing skeleton file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_pair(_SKELETONS_ROOT, "3-5", "does-not-exist")


@pytest.mark.unit
@pytest.mark.parametrize(("band", "slug"), DEFAULT_FIXTURES)
def test_default_fixture_pairs_exist_on_disk(band: str, slug: str) -> None:
    """Every default fixture pair (plan 3.4's >=5 skeletons) is present."""
    skeleton, contract = load_pair(_SKELETONS_ROOT, band, slug)
    assert skeleton["nodes"]
    assert contract.slots


@pytest.mark.unit
def test_default_fixtures_span_at_least_four_bands() -> None:
    """The default fixture set spans >=4 distinct age bands (plan 3.4)."""
    bands = {band for band, _ in DEFAULT_FIXTURES}
    assert len(bands) >= 4


@pytest.mark.unit
def test_build_specimen_flips_the_requested_slot_count() -> None:
    """build_specimen flips exactly slots_per_story theme slots to personalizable."""
    skeleton, contract = load_pair(_SKELETONS_ROOT, "8-11", "the-cave-of-echoes")
    specimen = build_specimen(
        skeleton, contract, "the-cave-of-echoes", slots_per_story=3
    )
    assert len(specimen.personalizable_slots) == 3


@pytest.mark.unit
def test_build_specimen_bound_skeleton_contains_a_sentinel_per_flipped_slot() -> None:
    """Every flipped slot's bound value appears as a sentinel in the bound skeleton."""
    skeleton, contract = load_pair(_SKELETONS_ROOT, "3-5", "puddle-jumping-day")
    specimen = build_specimen(
        skeleton, contract, "puddle-jumping-day", slots_per_story=4
    )
    serialized = json.dumps(specimen.bound_skeleton)
    for slot_id in specimen.personalizable_slots:
        value = specimen.slot_bindings[slot_id]
        assert wrap(slot_id, value) in serialized
    assert len(specimen.expected_sentinels) >= len(specimen.personalizable_slots)
    for token in specimen.expected_sentinels:
        assert SENTINEL_RE.fullmatch(token) is not None


@pytest.mark.unit
def test_build_specimen_choice_labels_stay_bare() -> None:
    """No choice label carries a sentinel token, even for a flipped slot."""
    skeleton, contract = load_pair(_SKELETONS_ROOT, "5-8", "the-night-market")
    specimen = build_specimen(skeleton, contract, "the-night-market", slots_per_story=4)
    for label in _choice_labels(specimen.bound_skeleton):
        assert "{~" not in label


@pytest.mark.unit
@pytest.mark.parametrize(("band", "slug"), DEFAULT_FIXTURES)
def test_personalized_contract_passes_normal_contract_validation(
    band: str, slug: str
) -> None:
    """The flipped contract round-trips through ThemeContract's own validators."""
    _, contract = load_pair(_SKELETONS_ROOT, band, slug)
    personalized = _personalize_contract(contract, slots_per_story=4)
    assert isinstance(personalized, ThemeContract)
    # Re-validate independently via the public constructor (round-trip),
    # proving this is not merely an already-validated in-memory object.
    revalidated = ThemeContract(**personalized.model_dump(mode="json"))
    assert revalidated == personalized


@pytest.mark.unit
def test_fixtures_contain_no_real_identity() -> None:
    """Every personalizable slot's bound value is a generic default word.

    #CRITICAL: security: the harness must never carry real child identity.
    #VERIFY: this test, run across every default fixture pair.
    """
    for band, slug in DEFAULT_FIXTURES:
        skeleton, contract = load_pair(_SKELETONS_ROOT, band, slug)
        specimen = build_specimen(skeleton, contract, slug, slots_per_story=4)
        original_values = set(contract.default_binding.values())
        for slot_id in specimen.personalizable_slots:
            value = specimen.slot_bindings[slot_id]
            assert value in _GENERIC_WORDS, (
                f"{band}/{slug} slot {slot_id!r} bound to non-generic value {value!r}"
            )
            # Defense in depth: the generic word is never the catalog's own
            # original (real-character) theme value for this same slot.
            assert value != contract.default_binding.get(slot_id)
        # None of the fixed generic candidate words happens to collide with
        # this catalog theme's own real character/place names.
        assert original_values.isdisjoint(_GENERIC_WORDS)
