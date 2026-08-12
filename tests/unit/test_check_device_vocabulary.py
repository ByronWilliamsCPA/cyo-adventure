"""Unit tests for scripts/check_device_vocabulary.py (DV checks)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.check_device_vocabulary import analyse, main

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SHIPPED_CONTRACTS = [
    _REPO_ROOT / "skeletons/3-5/the-lost-mitten.narrative.json",
    _REPO_ROOT / "skeletons/10-13/the-clocktower-cipher.narrative.json",
]


def _contract(
    requires: dict[str, Any],
    nodes: dict[str, Any] | None = None,
    permitted: list[str] | None = None,
    forbidden: list[str] | None = None,
) -> dict[str, Any]:
    """Build a minimal narrative contract around the parts DV checks read."""
    envelope: dict[str, Any] = {}
    if permitted is not None:
        envelope["permitted_device_kinds"] = permitted
    if forbidden is not None:
        envelope["forbidden_device_kinds"] = forbidden
    return {
        "world_recipe": {"requires": requires},
        "safety_envelope": envelope,
        "nodes": nodes or {},
    }


def _spec(axis: str, **extra: Any) -> dict[str, Any]:
    """Build one invention spec drawing from ``axis`` with an explicit category."""
    return {
        "pick": 1,
        "from": f"bible.device_vocabulary.{axis}",
        "category": axis,
        **extra,
    }


def _codes(contract: dict[str, Any], books: int = 5) -> list[str]:
    findings, _ = analyse(contract, books)
    return [finding.code for finding in findings]


@pytest.mark.unit
def test_dv0_reports_a_contract_with_no_requires_mapping() -> None:
    findings, capacities = analyse({"nodes": {}}, 5)
    assert [f.code for f in findings] == ["DV-0"]
    assert capacities == []


@pytest.mark.unit
def test_dv1_flags_an_axis_that_declares_a_count_but_enumerates_no_kinds() -> None:
    contract = _contract(
        {"clue_channels": {"count": 3}},
        {"n1": {"invention": {"clue": _spec("clue_channels", pick=3)}}},
    )
    assert "DV-1" in _codes(contract)


@pytest.mark.unit
def test_dv1_axis_is_excluded_from_the_capacity_table() -> None:
    """An axis with no kinds has no computable headroom; it must not read as ok."""
    contract = _contract({"clue_channels": {"count": 3}})
    _, capacities = analyse(contract, 5)
    assert capacities == []


@pytest.mark.unit
def test_dv2_flags_a_duplicate_entry_inside_kinds() -> None:
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["a", "b", "a", "c", "d", "e"]}},
        {"n1": {"invention": {"slot": _spec("axis")}}},
    )
    assert "DV-2" in _codes(contract)


@pytest.mark.unit
def test_dv2_duplicates_do_not_inflate_the_capacity() -> None:
    """Six entries but three distinct kinds supports three books, not six."""
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["a", "b", "c", "a", "b", "c"]}},
        {"n1": {"invention": {"slot": _spec("axis")}}},
    )
    _, capacities = analyse(contract, 5)
    assert capacities[0].distinct_kinds == 3
    assert capacities[0].books_supported == 3


@pytest.mark.unit
def test_dv3_flags_fewer_distinct_kinds_than_picks_per_book() -> None:
    """Two kinds cannot fill three picks without repeating inside one story."""
    contract = _contract(
        {"axis": {"count": 3, "kinds": ["a", "b"]}},
        {"n1": {"invention": {"slot": _spec("axis", pick=3)}}},
    )
    assert "DV-3" in _codes(contract)


@pytest.mark.unit
def test_dv4_flags_a_kind_listed_in_forbidden_device_kinds() -> None:
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["gentle", "injury"]}},
        {"n1": {"invention": {"slot": _spec("axis")}}},
        permitted=["gentle", "injury"],
        forbidden=["injury"],
    )
    findings, _ = analyse(contract, 1)
    assert any(f.code == "DV-4" and "injury" in f.message for f in findings)


@pytest.mark.unit
def test_dv4_flags_a_kind_absent_from_permitted_device_kinds() -> None:
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["known", "unlisted"]}},
        {"n1": {"invention": {"slot": _spec("axis")}}},
        permitted=["known"],
    )
    findings, _ = analyse(contract, 1)
    assert any(f.code == "DV-4" and "unlisted" in f.message for f in findings)


@pytest.mark.unit
def test_dv4_stays_silent_when_no_envelope_is_declared() -> None:
    """An absent permitted list means no envelope, not that everything is banned.

    NC-5 reports the missing envelope once; emitting one DV-4 per kind here
    would bury that single finding under noise.
    """
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["a", "b", "c"]}},
        {"n1": {"invention": {"slot": _spec("axis")}}},
    )
    assert "DV-4" not in _codes(contract, books=1)


@pytest.mark.unit
def test_dv4_enforces_an_explicitly_empty_permitted_list() -> None:
    """``"permitted_device_kinds": []`` bans everything; absent bans nothing.

    The two were collapsed into the same empty set, so an author who wrote an
    empty list (nothing is permitted) was read as one who wrote nothing
    (everything is permitted): the exact inverse of the declaration, applied
    silently. The distinction mirrors the one ``_kinds`` already draws for
    DV-3, where ``"kinds": []`` likewise says something a missing key does
    not.
    """
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["a", "b"]}},
        {"n1": {"invention": {"slot": _spec("axis")}}},
        permitted=[],
    )
    findings, _ = analyse(contract, 1)

    breaches = [f for f in findings if f.code == "DV-4"]
    assert len(breaches) == 2
    assert all("absent from permitted_device_kinds" in f.message for f in breaches)


@pytest.mark.unit
def test_dv5_flags_a_count_above_what_the_specs_consume() -> None:
    """The 10-13 room_curiosities defect: declares 4 picks, three nodes take one."""
    contract = _contract(
        {"axis": {"count": 4, "kinds": list("abcdefghijklmnopqrst")}},
        {
            "n1": {"invention": {"slot": _spec("axis")}},
            "n2": {"invention": {"slot": _spec("axis")}},
            "n3": {"invention": {"slot": _spec("axis")}},
        },
    )
    findings, _ = analyse(contract, 5)
    assert any(f.code == "DV-5" and "consume 3" in f.message for f in findings)


@pytest.mark.unit
def test_dv5_counts_a_multi_pick_spec_by_its_pick_value() -> None:
    """One spec taking three kinds satisfies a count of three."""
    contract = _contract(
        {"axis": {"count": 3, "kinds": list("abcdefghijklmno")}},
        {"n1": {"invention": {"slot": _spec("axis", pick=3)}}},
    )
    assert "DV-5" not in _codes(contract)


@pytest.mark.unit
def test_dv5_treats_an_absent_pick_as_one() -> None:
    contract = _contract(
        {"axis": {"count": 1, "kinds": list("abcde")}},
        {
            "n1": {
                "invention": {
                    "slot": {"from": "bible.device_vocabulary.axis", "category": "axis"}
                }
            }
        },
    )
    assert "DV-5" not in _codes(contract)


@pytest.mark.unit
def test_dv6_flags_a_forced_repeat_inside_the_target_series() -> None:
    """Eight kinds over four picks runs dry after two books."""
    contract = _contract(
        {"axis": {"count": 4, "kinds": list("abcdefgh")}},
        {"n1": {"invention": {"slot": _spec("axis", pick=4)}}},
    )
    findings, _ = analyse(contract, 5)
    assert any(f.code == "DV-6" and "book 3" in f.message for f in findings)


@pytest.mark.unit
def test_dv6_passes_when_the_repeat_falls_beyond_the_target() -> None:
    contract = _contract(
        {"axis": {"count": 4, "kinds": list("abcdefghijklmnopqrst")}},
        {"n1": {"invention": {"slot": _spec("axis", pick=4)}}},
    )
    assert "DV-6" not in _codes(contract, books=5)


@pytest.mark.unit
def test_dv6_is_waived_by_premise_fixed() -> None:
    """A single-kind axis that IS the story engine repeats by design."""
    contract = _contract(
        {
            "obstacle_kinds": {
                "count": 1,
                "kinds": ["out_of_reach"],
                "premise_fixed": True,
                "note": "the band's one obstacle by design",
            }
        },
        {"n1": {"invention": {"slot": _spec("obstacle_kinds")}}},
    )
    findings, capacities = analyse(contract, 5)
    assert "DV-6" not in [f.code for f in findings]
    assert capacities[0].premise_fixed is True


@pytest.mark.unit
def test_premise_fixed_must_be_exactly_true_to_waive() -> None:
    """A truthy-but-not-True value is a typo, not an opt-out."""
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["only"], "premise_fixed": "yes"}},
        {"n1": {"invention": {"slot": _spec("axis")}}},
    )
    assert "DV-6" in _codes(contract)


@pytest.mark.unit
def test_dv7_flags_a_frozen_kind_the_axis_does_not_enumerate() -> None:
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["a", "b", "c", "d", "e"]}},
        {"n1": {"invention": {"slot": _spec("axis", kind_must_be="absent")}}},
    )
    assert "DV-7" in _codes(contract)


@pytest.mark.unit
def test_dv8_flags_a_spec_that_omits_category() -> None:
    """The 3-5 defect: check_bible_diversity keys frozen kinds on category alone."""
    contract = _contract(
        {"axis": {"count": 1, "kinds": list("abcde")}},
        {
            "n1": {
                "invention": {
                    "slot": {"pick": 1, "from": "bible.device_vocabulary.axis"}
                }
            }
        },
    )
    assert "DV-8" in _codes(contract)


@pytest.mark.unit
def test_dv9_warns_on_a_spec_naming_an_axis_the_recipe_omits() -> None:
    contract = _contract(
        {"declared": {"count": 1, "kinds": list("abcde")}},
        {
            "n1": {"invention": {"slot": _spec("declared")}},
            "n2": {"invention": {"slot": _spec("undeclared")}},
        },
    )
    findings, _ = analyse(contract, 5)
    dv9 = [f for f in findings if f.code == "DV-9"]
    assert len(dv9) == 1
    assert dv9[0].severity == "WARNING"


@pytest.mark.unit
def test_a_spec_drawing_from_a_non_vocabulary_path_is_ignored() -> None:
    """n_start.loss_moment draws from bible.world + bible.motifs, not an axis."""
    contract = _contract(
        {"axis": {"count": 1, "kinds": list("abcde")}},
        {
            "n1": {"invention": {"slot": _spec("axis")}},
            "n_start": {
                "invention": {
                    "loss_moment": {
                        "pick": 1,
                        "from": "bible.world.physics_notes + bible.motifs",
                    }
                }
            },
        },
    )
    assert _codes(contract) == []


@pytest.mark.unit
def test_frozen_picks_raise_the_headroom_rather_than_lowering_it() -> None:
    """The arithmetic that drives how much vocabulary an author is asked for.

    Seven kinds over three picks reads naively as two books. One pick frozen
    to a single kind leaves six free kinds over two free picks, which is three.
    Reporting the naive number would order vocabulary nobody needs.
    """
    contract = _contract(
        {"access_details": {"count": 3, "kinds": list("abcdefg")}},
        {
            "n1": {"invention": {"slot": _spec("access_details")}},
            "n2": {"invention": {"slot": _spec("access_details")}},
            "n3": {"invention": {"slot": _spec("access_details", kind_must_be="a")}},
        },
    )
    _, capacities = analyse(contract, 5)
    capacity = capacities[0]
    assert capacity.frozen_picks == 1
    assert capacity.free_kinds == 6
    assert capacity.free_picks == 2
    assert capacity.books_supported == 3
    assert capacity.forced_repeat_book == 4


@pytest.mark.unit
def test_a_fully_frozen_axis_reports_no_forced_repeat_book() -> None:
    """Nothing is free to vary, so no vocabulary size changes the outcome."""
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["a", "b", "c"]}},
        {"n1": {"invention": {"slot": _spec("axis", kind_must_be="a")}}},
    )
    _, capacities = analyse(contract, 5)
    assert capacities[0].books_supported is None
    assert capacities[0].forced_repeat_book is None


@pytest.mark.unit
def test_a_fully_frozen_axis_does_not_fail_dv6() -> None:
    contract = _contract(
        {"axis": {"count": 1, "kinds": ["a", "b", "c"]}},
        {"n1": {"invention": {"slot": _spec("axis", kind_must_be="a")}}},
    )
    assert "DV-6" not in _codes(contract)


@pytest.mark.unit
def test_an_axis_is_resolved_from_the_path_tail_when_category_is_absent() -> None:
    """A legacy spec still contributes its picks, so DV-5 stays accurate.

    Keying resolution on ``category`` alone is the exact bug DV-8 reports in
    check_bible_diversity; this checker must not repeat it.
    """
    contract = _contract(
        {"axis": {"count": 2, "kinds": list("abcdefghij")}},
        {
            "n1": {
                "invention": {
                    "slot": {"pick": 1, "from": "bible.device_vocabulary.axis"}
                }
            },
            "n2": {
                "invention": {
                    "slot": {"pick": 1, "from": "bible.device_vocabulary.axis"}
                }
            },
        },
    )
    codes = _codes(contract)
    assert "DV-5" not in codes
    assert codes.count("DV-8") == 2


@pytest.mark.unit
def test_malformed_nodes_are_skipped_rather_than_raising() -> None:
    """Contract shape problems are NC-0's finding to report, not this script's."""
    contract = _contract(
        {"axis": {"count": 0, "kinds": list("abcde")}},
        {
            "n1": "not-a-dict",
            "n2": {"invention": "not-a-dict"},
            "n3": {"invention": {"slot": "not-a-dict"}},
        },
    )
    assert analyse(contract, 5)[0] == []


@pytest.mark.unit
@pytest.mark.parametrize("path", _SHIPPED_CONTRACTS, ids=lambda p: p.parent.name)
def test_shipped_contracts_clear_the_five_book_target(path: Path) -> None:
    """Regression guard: the widening must not silently rot back."""
    contract = json.loads(path.read_text(encoding="utf-8"))
    findings, _ = analyse(contract, 5)
    errors = [f for f in findings if f.severity == "ERROR"]
    assert errors == [], [f"{f.code} [{f.axis}]: {f.message}" for f in errors]


@pytest.mark.unit
def test_main_exits_one_under_check_when_an_error_is_found(tmp_path: Path) -> None:
    path = tmp_path / "bad.narrative.json"
    path.write_text(json.dumps(_contract({"axis": {"count": 3}})), encoding="utf-8")
    assert main([str(path), "--check"]) == 1


@pytest.mark.unit
def test_main_exits_zero_without_check_even_when_errors_exist(tmp_path: Path) -> None:
    """The report is useful on its own; only --check turns it into a gate."""
    path = tmp_path / "bad.narrative.json"
    path.write_text(json.dumps(_contract({"axis": {"count": 3}})), encoding="utf-8")
    assert main([str(path)]) == 0


@pytest.mark.unit
def test_main_exits_zero_under_check_on_a_clean_contract(tmp_path: Path) -> None:
    path = tmp_path / "ok.narrative.json"
    contract = _contract(
        {"axis": {"count": 1, "kinds": list("abcde")}},
        {"n1": {"invention": {"slot": _spec("axis")}}},
    )
    path.write_text(json.dumps(contract), encoding="utf-8")
    assert main([str(path), "--check"]) == 0


@pytest.mark.unit
def test_main_rejects_a_series_target_below_one(tmp_path: Path) -> None:
    path = tmp_path / "ok.narrative.json"
    path.write_text(json.dumps(_contract({})), encoding="utf-8")
    assert main([str(path), "--books", "0"]) == 2


@pytest.mark.unit
def test_main_reports_a_usage_error_on_an_unreadable_contract(tmp_path: Path) -> None:
    assert main([str(tmp_path / "missing.json")]) == 2


@pytest.mark.unit
def test_main_reports_a_usage_error_on_a_json_document_that_is_not_an_object(
    tmp_path: Path,
) -> None:
    path = tmp_path / "list.narrative.json"
    path.write_text("[]", encoding="utf-8")
    assert main([str(path)]) == 2
