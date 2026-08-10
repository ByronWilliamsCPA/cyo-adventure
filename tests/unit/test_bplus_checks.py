"""Unit tests for the B-plus amendment tools (AL-156..158)."""

from __future__ import annotations

import pytest

from scripts.check_bible_diversity import mechanic_divergence, near_noun_swaps
from scripts.check_narrative_contract import check_selection
from scripts.check_sibling_fills import shared_grams


def _bible(kinds: list[str]) -> dict[str, object]:
    return {
        "device_vocabulary": {
            "clue_channels": [
                {"text": f"t{i} {k}", "kind": k} for i, k in enumerate(kinds)
            ]
        }
    }


@pytest.mark.unit
def test_mechanic_divergence_zero_for_identical_kind_multisets() -> None:
    a = _bible(["disturbance", "testimony", "sensory_trace"])
    b = _bible(["disturbance", "testimony", "sensory_trace"])
    assert mechanic_divergence(a, b) == pytest.approx(0.0)


@pytest.mark.unit
def test_mechanic_divergence_one_for_disjoint_kinds() -> None:
    a = _bible(["disturbance", "testimony"])
    b = _bible(["instrument", "container"])
    assert mechanic_divergence(a, b) == pytest.approx(1.0)


@pytest.mark.unit
def test_near_noun_swap_flags_same_kind_heavy_overlap() -> None:
    a = {
        "device_vocabulary": {
            "c": [{"text": "a line of flattened grass", "kind": "disturbance"}]
        }
    }
    b = {
        "device_vocabulary": {
            "c": [{"text": "a lane of flattened grass", "kind": "disturbance"}]
        }
    }
    assert near_noun_swaps(a, b)


@pytest.mark.unit
def test_shared_grams_counts_cross_fill_repeats_only() -> None:
    def story(body: str) -> dict[str, object]:
        return {"nodes": [{"id": "n", "body": body, "choices": []}]}

    fills = [
        story("one two three reach it together now"),
        story("one two three reach for the sky"),
        story("completely different words appear in here"),
    ]
    shared = shared_grams(fills)
    assert ("one", "two", "three", "reach") in shared
    assert shared[("one", "two", "three", "reach")] == 2


@pytest.mark.unit
def test_nc7_validates_mechanism_and_uniqueness() -> None:
    contract = {
        "premise": {"resolution_space": ["shared", "solo"]},
        "nodes": {
            "n_end": {"tier": "locked_outcome", "mechanisms": ["shared", "solo"]},
            "n_a": {"invention": {"clue_channel": {"unique_within_story": True}}},
            "n_b": {"invention": {"clue_channel": {"unique_within_story": True}}},
        },
    }
    bible = {
        "device_vocabulary": {
            "clue_channels": [{"text": "a trail", "kind": "disturbance"}]
        }
    }
    ok_sel = {
        "n_end": {"mechanism": "shared"},
        "n_a": {"clue_channel": {"text": "a trail", "kind": "disturbance"}},
    }
    errors, _ = check_selection(ok_sel, contract, bible)
    assert errors == []

    bad_sel = {
        "n_end": {"mechanism": "time-travel"},
        "n_a": {"clue_channel": {"text": "a trail", "kind": "disturbance"}},
        "n_b": {"clue_channel": {"text": "a trail", "kind": "disturbance"}},
    }
    errors, _ = check_selection(bad_sel, contract, bible)
    assert any("mechanism 'time-travel'" in e for e in errors)
    assert any("unique_within_story" in e for e in errors)
