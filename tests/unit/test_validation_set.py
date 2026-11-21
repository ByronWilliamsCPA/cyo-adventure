"""Unit tests for the WP-3.1 validation set and scripts/build_validation_set.py.

The committed ``validation-set.json`` is the shared split for the continuity
reader (WP-3.2, D6) and the plan reviewer (WP-3.7, D12). These tests hold its
invariants: it loads; every item names a book in one half only; the books seen
in reviewer-prompt design are all in tuning; evidence files still hash to what
the set records; and rebuilding from the sources gives the committed file
byte for byte (which re-checks every pinned sha256 and every node id).

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


def test_no_em_dash_in_the_set() -> None:
    """The repository bans U+2014; the generated JSON must not carry one."""
    assert chr(0x2014) not in _SET.read_text("utf-8")
