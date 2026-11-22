"""Unit tests for the WP-3.1 validation set and scripts/build_validation_set.py.

The committed ``validation-set.json`` is the shared split for the continuity
reader (WP-3.2, D6) and the plan reviewer (WP-3.7, D12). These tests hold its
invariants: it loads; every item names a book in one half only; the books seen
in reviewer-prompt design are all in tuning; evidence files still hash to what
the set records; the held-out clean books and clean plans are the revisions
fixed on 2026-11-22 while plans of the defective post-fix revisions are
``reject``; the split stays frozen at its recorded assignment; and rebuilding
from the sources gives the committed file byte for byte (which re-checks
every pinned sha256 and every node id).

scripts/ is not an importable package, so the builder is loaded from its file
path via importlib, as tests/unit/test_check_lessons_log.py does.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_REPO = Path(__file__).resolve().parents[2]
_SET = _REPO / "docs/planning/evidence/continuity-reader/validation-set.json"

JsonObj = dict[str, object]

PILOT_UNITS = (
    "the-hollow-lighthouse",
    "the-lantern-keepers-list",
    "the-orchard-signal",
    "the-vanishing-orchard",
)
PILOT_BOOK_KEYS = (
    "the-hollow-lighthouse@15b14a1",
    "the-hollow-lighthouse@3e29e04",
    "B-lkl-new-1",
    "B-lkl-new-2",
    "B-os-new-1",
    "the-vanishing-orchard@db7fb22",
)
VERDICTS = {
    "node_assertion": {"defect"},
    "payoff_judgment": {"defect", "clean"},
    "merge_count": {"count"},
    "clean_book": {"clean"},
    "plan": {"reject", "pass", "unknown"},
}
REQUIRED = (
    "id",
    "kind",
    "half",
    "book",
    "expected_verdict",
    "defect_class",
    "severity",
    "source",
    "scored_for",
    "label_strength",
)


def _load_builder() -> ModuleType:
    """Load scripts/build_validation_set.py from its file path."""
    path = _REPO / "scripts/build_validation_set.py"
    spec = importlib.util.spec_from_file_location("build_validation_set", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their module through sys.modules at class creation.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_BUILDER = _load_builder()


@pytest.fixture(scope="module")
def doc() -> JsonObj:
    """Return the committed validation set."""
    return cast("JsonObj", json.loads(_SET.read_text("utf-8")))


def _items(doc: JsonObj) -> list[JsonObj]:
    return cast("list[JsonObj]", doc["items"])


def _book(item: JsonObj) -> JsonObj:
    return cast("JsonObj", item["book"])


def _units(doc: JsonObj) -> dict[str, JsonObj]:
    return cast("dict[str, JsonObj]", cast("JsonObj", doc["split"])["units"])


def test_every_item_has_the_documented_fields(doc: JsonObj) -> None:
    """Each item carries the README's required fields and a valid verdict."""
    ids = [cast("str", i["id"]) for i in _items(doc)]
    assert len(ids) == len(set(ids))
    for item in _items(doc):
        missing = [f for f in REQUIRED if f not in item]
        assert not missing, (item["id"], missing)
        kind = cast("str", item["kind"])
        assert item["expected_verdict"] in VERDICTS[kind], item["id"]


def test_no_book_appears_in_both_halves(doc: JsonObj) -> None:
    """A unit maps to one half, and every item sits in its unit's half."""
    units = _units(doc)
    seen: dict[str, set[str]] = {}
    for item in _items(doc):
        unit = cast("str", _book(item)["unit"])
        assert item["half"] == units[unit]["half"], item["id"]
        seen.setdefault(unit, set()).add(cast("str", item["half"]))
    assert all(len(halves) == 1 for halves in seen.values()), seen


def test_pilot_books_are_all_in_tuning(doc: JsonObj) -> None:
    """Books seen in reviewer-prompt design never reach the held-out half."""
    units = _units(doc)
    for unit in PILOT_UNITS:
        assert units[unit]["half"] == "tuning", unit
    keys = {cast("str | None", _book(i)["key"]): i["half"] for i in _items(doc)}
    for key in PILOT_BOOK_KEYS:
        assert keys[key] == "tuning", key


def test_held_out_half_has_both_labels_in_every_family_band(doc: JsonObj) -> None:
    """The held-out half holds a defective and a clean real plan per family band."""
    units = _units(doc)
    cells: set[tuple[object, object]] = set()
    for item in _items(doc):
        if item["kind"] != "plan" or item["half"] != "held_out":
            continue
        if item["label_strength"] == "strong":
            band = units[cast("str", _book(item)["unit"])]["band"]
            cells.add((band, item["expected_verdict"]))
    for band in ("8-11", "10-13", "13-16"):
        assert (band, "reject") in cells, band
        assert (band, "pass") in cells, band


def test_working_tree_files_still_hash_to_the_recorded_sha256(doc: JsonObj) -> None:
    """Evidence books and plan files are unchanged since the set was built."""
    for item in _items(doc):
        book = _book(item)
        if book["revision"] == "working-tree":
            data = (_REPO / cast("str", book["file"])).read_bytes()
            assert hashlib.sha256(data).hexdigest() == book["sha256"], item["id"]
        plan = cast("JsonObj | None", item.get("plan"))
        if plan is not None and "revision" not in plan:
            data = (_REPO / cast("str", plan["file"])).read_bytes()
            assert hashlib.sha256(data).hexdigest() == plan["sha256"], item["id"]


def test_rebuild_from_sources_matches_the_committed_file() -> None:
    """Rebuilding re-verifies every pin and node id and reproduces the file."""
    try:
        text = cast("str", _BUILDER.render(_BUILDER.build()))
    except _BUILDER.MissingRevisionError as exc:
        pytest.skip(f"pinned git history not in this checkout: {exc}")
    assert text == _SET.read_text("utf-8")


def test_a_node_missing_from_the_book_is_refused() -> None:
    """A transcribed row naming a node the book lacks fails verification."""
    src = _BUILDER.FindingSource(
        doc=_BUILDER.FINDINGS[0].doc,
        book="B-lkl-new-1",
        prefix="X",
        class_from_source=frozenset(),
        severity_note="test",
        rows=(),
    )
    text = "| F1 | `no_such_node` |"
    with pytest.raises(_BUILDER.SourceError, match="no_such_node"):
        _BUILDER._finding_item(src, ("F1", "B", "u", "no_such_node"), text)


def test_a_finding_id_absent_from_the_source_is_refused() -> None:
    """The anchor check rejects an id the source never lists as an entry."""
    assert _BUILDER._anchor_ok("| B1 | `n_open` |", "B1")
    assert _BUILDER._anchor_ok("12. **ch_pencil** (blocker)", "12")
    assert not _BUILDER._anchor_ok("see B1 above", "B1")


def test_split_forces_pilot_units_into_tuning_whatever_the_items() -> None:
    """With no plan items at all, forced units still land in tuning."""
    split = cast("dict[str, str]", _BUILDER.compute_split([]))
    for unit in PILOT_UNITS:
        assert split[unit] == "tuning"


FIXED_KEYS = {
    "the-sky-ship-stowaway": "the-sky-ship-stowaway@da5c467",
    "the-midnight-museum": "the-midnight-museum@fcd389e",
    "the-signal-in-the-static": "the-signal-in-the-static@161e1e7",
    "the-cave-of-echoes": "the-cave-of-echoes@a6b399d",
    "the-mapmakers-island": "the-mapmakers-island@c085d3c",
}
POSTFIX_KEYS = {
    "the-sky-ship-stowaway": "the-sky-ship-stowaway@e9adcd1",
    "the-midnight-museum": "the-midnight-museum@a0b61e9",
    "the-signal-in-the-static": "the-signal-in-the-static@38f6a5a",
    "the-cave-of-echoes": "the-cave-of-echoes@1e2c853",
    "the-mapmakers-island": "the-mapmakers-island@16932c1",
}
MINORS_2026_11_22 = {
    "the-sky-ship-stowaway": set[str](),
    "the-midnight-museum": {"MM-5"},
    "the-signal-in-the-static": {"SG-7", "SG-8"},
    "the-cave-of-echoes": set[str](),
    "the-mapmakers-island": {"MI-12", "MI-13", "MI-14", "MI-15", "MI-16", "MI-17"},
}
RECORDED_HALVES = {
    "tuning": {
        "the-hollow-lighthouse",
        "the-lantern-keepers-list",
        "the-locked-carousel",
        "the-orchard-signal",
        "the-thornwood-trial",
        "the-vanishing-orchard",
    },
    "held_out": {
        "the-cave-of-echoes",
        "the-clocktower-cipher",
        "the-clockwork-menagerie",
        "the-last-train-north",
        "the-mapmakers-island",
        "the-midnight-museum",
        "the-signal-in-the-static",
        "the-sky-ship-stowaway",
    },
}


def _by_id(doc: JsonObj) -> dict[str, JsonObj]:
    return {cast("str", i["id"]): i for i in _items(doc)}


def _residual_ids(item: JsonObj) -> set[str]:
    return {
        cast("str", r["id"]) for r in cast("list[JsonObj]", item["known_residuals"])
    }


def test_clean_held_out_books_are_the_fixed_revisions(doc: JsonObj) -> None:
    """Each held-out clean book is the 2026-11-22 fix, never the post-fix one."""
    clean = {
        cast("str", _book(i)["unit"]): i
        for i in _items(doc)
        if i["kind"] == "clean_book" and i["half"] == "held_out"
    }
    assert set(clean) == set(FIXED_KEYS)
    by_id = _by_id(doc)
    for unit, key in FIXED_KEYS.items():
        item = clean[unit]
        assert _book(item)["key"] == key
        assert item["label_strength"] == "strong"
        assert _residual_ids(item) == MINORS_2026_11_22[unit], unit
        # fixed_nodes are the nodes of the post-fix revision's residual items.
        residual_nodes = {
            n
            for i in by_id.values()
            if i["kind"] == "node_assertion" and _book(i)["key"] == POSTFIX_KEYS[unit]
            for n in [i["node"], *cast("list[str]", i["other_nodes"])]
        }
        fixed = set(cast("list[str]", item["fixed_nodes"]))
        assert fixed, unit
        assert fixed <= residual_nodes, unit
    assert not any(
        i["kind"] == "clean_book" and _book(i)["key"] in POSTFIX_KEYS.values()
        for i in _items(doc)
    )


def test_lighthouse_and_orchard_clean_items_are_unchanged(doc: JsonObj) -> None:
    """The two WP-0.4 clean books keep their post-fix revisions and residuals."""
    by_id = _by_id(doc)
    lighthouse = by_id["CB-the-hollow-lighthouse@3e29e04"]
    orchard = by_id["CB-the-vanishing-orchard@db7fb22"]
    assert lighthouse["known_residuals"] == []
    residuals = cast("list[JsonObj]", orchard["known_residuals"])
    assert [r["choice"] for r in residuals] == ["c_b1a_dec_2"]


def test_residuals_of_2026_11_21_are_defects_of_the_post_fix_revisions(
    doc: JsonObj,
) -> None:
    """Every real 2026-11-21 residual is a reader defect item, SG-2 the blocker."""
    rows = [
        i
        for i in _items(doc)
        if cast("str", i["id"]).startswith("R1121-") and i["kind"] == "node_assertion"
    ]
    assert len(rows) == 20
    assert {_book(i)["key"] for i in rows} == set(POSTFIX_KEYS.values())
    blockers = {cast("str", i["id"]) for i in rows if i["severity"] == "blocker"}
    assert blockers == {"R1121-SG-2"}
    not_defects = ("SS-4", "SG-3", "MI-3", "MI-4", "MI-6", "CE-3", "MM-1", "MM-2")
    ids = {cast("str", i["id"]) for i in rows}
    assert not any(f"R1121-{n}" in ids for n in (*not_defects, "MM-3"))


def test_fixed_revision_plans_pass_despite_minor_residuals(doc: JsonObj) -> None:
    """e/f plans are strong D12 passes; their book's minors do not reject them."""
    by_id = _by_id(doc)
    for n in range(1, 6):
        for p in ("e", "f"):
            item = by_id[f"PL-{p}{n}"]
            unit = cast("str", _book(item)["unit"])
            assert _book(item)["key"] == FIXED_KEYS[unit]
            assert item["expected_verdict"] == "pass", item["id"]
            assert item["defects"] == []
            assert item["scored_for"] == "D12"
            assert item["label_strength"] == "strong"
            assert _residual_ids(item) == MINORS_2026_11_22[unit], item["id"]


def test_post_fix_revision_plans_follow_their_worst_severity(doc: JsonObj) -> None:
    """c/d and held-out hand-written plans reject on a should-fix, pass on minors only.

    Owner ruling 2026-11-22 (AL-882): a revision whose every defect is minor
    labels its plans ``pass`` with the minors as known residuals.
    """
    by_id = _by_id(doc)
    plan_ids = [f"PL-{p}{n}" for p in ("c", "d") for n in range(1, 6)]
    plan_ids += [f"PL-{u}-postfix" for u in POSTFIX_KEYS]
    minor_only = {"the-midnight-museum"}
    for pid in plan_ids:
        item = by_id[pid]
        unit = cast("str", _book(item)["unit"])
        assert _book(item)["key"] == POSTFIX_KEYS[unit], pid
        if unit in minor_only:
            assert item["expected_verdict"] == "pass", pid
            assert item["defects"] == []
            assert item["blocker_entries"] == 0
            assert item["severity"] is None
            assert _residual_ids(item) == {"R1121-MM-4"}, pid
            continue
        assert item["expected_verdict"] == "reject", pid
        defects = cast("list[JsonObj]", item["defects"])
        assert defects, pid
        assert all(cast("str", d["id"]).startswith("R1121-") for d in defects)
        blockers = 1 if unit == "the-signal-in-the-static" else 0
        assert item["blocker_entries"] == blockers, pid
    for unit in ("the-hollow-lighthouse", "the-vanishing-orchard"):
        assert by_id[f"PL-{unit}-postfix"]["expected_verdict"] == "pass"


def test_held_out_d12_counts_are_reported_per_book(doc: JsonObj) -> None:
    """The summary breaks plans out by book; Museum's minor-only plans pass."""
    summary = cast("JsonObj", cast("JsonObj", doc["summary"])["held_out"])
    by_unit = cast("dict[str, dict[str, int]]", summary["d12_plans_by_unit"])
    for unit in FIXED_KEYS:
        expected = 5 if unit == "the-midnight-museum" else 2
        assert by_unit[unit]["pass/strong"] == expected, unit
    plans = cast("dict[str, int]", summary["plans"])
    assert plans["pass/strong"] == 13
    assert plans["reject/strong"] == 17
    assert plans["reject/strong"] >= 15


def test_split_is_frozen_at_the_recorded_assignment(doc: JsonObj) -> None:
    """The split did not move when the residual sources were added."""
    units = _units(doc)
    for half, members in RECORDED_HALVES.items():
        assert {u for u, v in units.items() if v["half"] == half} == members
    recorded = cast("dict[str, str]", _BUILDER.RECORDED_SPLIT)
    assert {u: units[u]["half"] for u in units} == recorded
    assert _BUILDER.compute_split(_items(doc)) == recorded


def test_a_split_that_would_move_a_unit_is_refused() -> None:
    """frozen_split fails the build rather than accept a moved unit."""
    with pytest.raises(_BUILDER.SourceError, match="would move"):
        _BUILDER.frozen_split([])


def test_no_em_dash_in_the_set() -> None:
    """The repository bans U+2014; the generated JSON must not carry one."""
    assert chr(0x2014) not in _SET.read_text("utf-8")
