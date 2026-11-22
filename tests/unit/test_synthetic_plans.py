"""Unit tests for the WP-3.7 synthetic seeded-defect plans.

``docs/planning/evidence/plan-reviewer/synthetic/`` holds the plans seeded with
one defect each that owner decision D12 (as amended 2026-11-21) allows beside
the real validation set, reported separately as synthetic. These tests hold the
family rules: every family A seed trips exactly its intended rule through
``check_plan`` (the function ``verify_witnesses`` uses); every family B seed
passes ``check_plan`` with no ERROR and no warning its source baseline lacks;
sources are clean strong held-out or tuning plans of the matching half only;
no rule supplies more than two seeds in a half; the D12 minimums are met; the
committed files are exactly what the builder produces; and nothing here shares
an id with ``validation-set.json`` or contains the em-dash character.

scripts/ is not an importable package, so the builder is loaded from its file
path via importlib, as tests/unit/test_validation_set.py does. A shallow clone
lacks the pinned git revisions the builder reads; the tests that need them skip
there, and the structural tests still run on the committed files.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.storyplan.checks import WITNESSES, check_plan
from cyo_adventure.storyplan.models import StoryPlan

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

_REPO = Path(__file__).resolve().parents[2]
_SYNTH = _REPO / "docs/planning/evidence/plan-reviewer/synthetic"
_SYNTH_SET = _SYNTH / "validation-set.synthetic.json"
_REAL_SET = _REPO / "docs/planning/evidence/continuity-reader/validation-set.json"
_BUILDER = _REPO / "scripts/build_synthetic_plans.py"

JsonObj = dict[str, object]

#: The em-dash character, built from its code point so this file stays clean.
EM_DASH = chr(0x2014)
#: Museum's minor-only plans: `pass` by owner ruling, never a source (AL-882).
MINOR_ONLY_PLANS = ("PL-c1", "PL-d3", "PL-the-midnight-museum-postfix")
HELD_OUT_SOURCES = (
    "PL-e1",
    "PL-e3",
    "PL-e4",
    "PL-e5",
    "PL-f1",
    "PL-f5",
)
TUNING_SOURCES = (
    "PL-the-hollow-lighthouse-postfix",
    "PL-the-vanishing-orchard-postfix",
)
HELD_OUT_BOOKS = (
    "the-cave-of-echoes",
    "the-mapmakers-island",
    "the-midnight-museum",
    "the-signal-in-the-static",
    "the-sky-ship-stowaway",
)
SEED_RULES = tuple(f"SP-{n}" for n in range(1, 10))
B_CLASSES = (
    "label_outcome_mismatch",
    "truth_contradiction",
    "ending_gift_mismatch",
    "payoff_shows_mismatch",
)
ID_PATTERN = re.compile(r"^SY-(A-SP-[1-9]|B-B[1-4])-\d+$")


def _load_builder() -> ModuleType:
    """Load scripts/build_synthetic_plans.py from its file path.

    Returns:
        ModuleType: The builder module.
    """
    spec = importlib.util.spec_from_file_location("build_synthetic_plans", _BUILDER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_synthetic_plans"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder() -> ModuleType:
    """Return the loaded builder module."""
    return _load_builder()


@pytest.fixture(scope="module")
def doc() -> JsonObj:
    """Return the committed synthetic validation-set document."""
    return cast("JsonObj", json.loads(_SYNTH_SET.read_text("utf-8")))


@pytest.fixture(scope="module")
def items(doc: JsonObj) -> list[JsonObj]:
    """Return the committed synthetic items."""
    return cast("list[JsonObj]", doc["items"])


@pytest.fixture(scope="module")
def real_items() -> dict[str, JsonObj]:
    """Return the real validation set's items by id."""
    real = cast("JsonObj", json.loads(_REAL_SET.read_text("utf-8")))
    return {
        str(cast("JsonObj", item)["id"]): cast("JsonObj", item)
        for item in cast("list[object]", real["items"])
    }


@pytest.fixture(scope="module")
def real_doc() -> JsonObj:
    """Return the real validation set's document."""
    return cast("JsonObj", json.loads(_REAL_SET.read_text("utf-8")))


@pytest.fixture(scope="module")
def built(builder: ModuleType) -> dict[Path, str]:
    """Rebuild every output from the sources, or skip in a shallow clone."""
    try:
        return cast("dict[Path, str]", builder.expected_files())
    except builder.MissingRevisionError:
        pytest.skip("pinned revisions are not in this checkout (shallow clone)")


@pytest.fixture(scope="module")
def sources(builder: ModuleType, items: list[JsonObj]) -> dict[str, object]:
    """Load every source plan the items name, or skip in a shallow clone."""
    plan_items = builder.load_validation_set()
    try:
        return {
            str(item["source_plan_id"]): builder.load_source(
                str(item["source_plan_id"]), plan_items
            )
            for item in items
        }
    except builder.MissingRevisionError:
        pytest.skip("pinned revisions are not in this checkout (shallow clone)")


def _seed_plan(item: JsonObj) -> JsonObj:
    """Read an item's plan file.

    Args:
        item: A synthetic item.

    Returns:
        JsonObj: The decoded plan.
    """
    plan_ref = cast("JsonObj", item["plan"])
    path = _REPO / str(plan_ref["file"])
    return cast("JsonObj", json.loads(path.read_text("utf-8")))


def _check(builder: ModuleType, sources: dict[str, object], item: JsonObj) -> object:
    """Run ``check_plan`` on an item's plan against its source's book.

    Args:
        builder: The builder module.
        sources: The loaded sources by plan id.
        item: A synthetic item.

    Returns:
        object: The ``ValidationReport``.
    """
    source = sources[str(item["source_plan_id"])]
    plan = StoryPlan.model_validate(_seed_plan(item))
    return check_plan(
        plan,
        source.book,  # pyright: ignore[reportAttributeAccessIssue]
        book_digest=source.digest,  # pyright: ignore[reportAttributeAccessIssue]
    )


def _family(items: list[JsonObj], family: str) -> list[JsonObj]:
    """Return the items of one family.

    Args:
        items: The synthetic items.
        family: ``A`` or ``B``.

    Returns:
        list[JsonObj]: The matching items.
    """
    return [i for i in items if i["family"] == family]


# ---------------------------------------------------------------------------
# Structure of the committed files
# ---------------------------------------------------------------------------


def test_document_header_states_the_set_is_never_merged(doc: JsonObj) -> None:
    """The JSON names its schema and says it is never merged into the real set."""
    assert doc["schema"] == "validation-set-synthetic/v1"
    assert doc["work_package"] == "WP-3.7"
    assert str(doc["readme"]).endswith("synthetic/README.md")
    assert (_REPO / str(doc["readme"])).is_file()
    assert "never merged" in str(doc["never_merged"])
    assert "validation-set.json" in str(doc["never_merged"])


def test_every_item_has_the_required_fields(items: list[JsonObj]) -> None:
    """Every item carries the fields D12 asks for, with the fixed constants."""
    common = (
        "id",
        "kind",
        "family",
        "half",
        "book",
        "source_plan_id",
        "plan",
        "expected_verdict",
        "defect_class",
        "edited_paths",
        "description",
        "scored_for",
        "label_strength",
        "severity",
    )
    for item in items:
        for field in common:
            assert field in item, f"{item['id']}: missing {field}"
        assert item["kind"] == "plan"
        assert item["expected_verdict"] == "reject"
        assert item["scored_for"] == "D12-synthetic"
        assert item["label_strength"] == "synthetic"
        assert item["half"] in {"tuning", "held_out"}
        assert ID_PATTERN.match(str(item["id"])), item["id"]
        assert item["edited_paths"], item["id"]
        if item["family"] == "A":
            assert item["intended_rule"] == item["defect_class"]
            assert item["severity"] == "blocker"
        else:
            assert item["intended_class"] == item["defect_class"]
            assert item["defect_class"] in B_CLASSES
            assert item["severity"] in {"blocker", "should-fix", "minor"}
            assert item["reviewer_should_say"]


def test_ids_are_unique_and_do_not_overlap_the_real_set(
    items: list[JsonObj], real_items: dict[str, JsonObj]
) -> None:
    """No synthetic id repeats, and none is an id of ``validation-set.json``."""
    ids = [str(i["id"]) for i in items]
    assert len(set(ids)) == len(ids)
    assert not set(ids) & set(real_items)
    plan_files = [str(cast("JsonObj", i["plan"])["file"]) for i in items]
    assert len(set(plan_files)) == len(plan_files)


def test_plan_files_match_the_recorded_hashes_and_nothing_is_stray(
    items: list[JsonObj],
) -> None:
    """Each plan file exists, hashes to its record, and has the stated format."""
    recorded = set()
    for item in items:
        plan_ref = cast("JsonObj", item["plan"])
        path = _REPO / str(plan_ref["file"])
        recorded.add(path)
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == plan_ref["sha256"], item["id"]
        text = data.decode("utf-8")
        assert text.endswith("}\n")
        assert text.isascii()
        assert text == json.dumps(json.loads(text), indent=2, ensure_ascii=True) + "\n"
    assert set(_SYNTH.glob("*.plan.json")) == recorded


def test_the_synthetic_set_was_not_merged_into_the_real_one(
    real_doc: JsonObj, real_items: dict[str, JsonObj]
) -> None:
    """The real set has no synthetic item and no synthetic summary key."""
    assert real_doc["schema"] == "validation-set/v1"
    assert not any(i.startswith("SY-") for i in real_items)
    assert all(
        item.get("label_strength") != "synthetic" for item in real_items.values()
    )


def test_summary_counts_match_the_items(doc: JsonObj, items: list[JsonObj]) -> None:
    """The recorded summary is the count of the items it summarises."""
    summary = cast("JsonObj", doc["summary"])
    assert summary["items"] == len(items)
    for family, key in (("A", "family_a"), ("B", "family_b")):
        block = cast("JsonObj", summary[key])
        members = _family(items, family)
        assert block["total"] == len(members)
        for half in ("tuning", "held_out"):
            half_block = cast("JsonObj", block[half])
            assert half_block["total"] == len([m for m in members if m["half"] == half])


# ---------------------------------------------------------------------------
# Sources and halves
# ---------------------------------------------------------------------------


def test_sources_are_clean_strong_plans_of_the_matching_half(
    items: list[JsonObj], real_items: dict[str, JsonObj], real_doc: JsonObj
) -> None:
    """Sources are `pass`/`strong` plans; a seed takes its source's half and unit."""
    units = cast("JsonObj", cast("JsonObj", real_doc["split"])["units"])
    for item in items:
        source_id = str(item["source_plan_id"])
        assert source_id not in MINOR_ONLY_PLANS, source_id
        source = real_items[source_id]
        assert source["kind"] == "plan"
        assert source["expected_verdict"] == "pass"
        assert source["label_strength"] == "strong"
        assert item["half"] == source["half"], item["id"]
        assert item["book"] == source["book"], item["id"]
        unit = str(cast("JsonObj", item["book"])["unit"])
        assert cast("JsonObj", units[unit])["half"] == item["half"], item["id"]
        plan_ref = cast("JsonObj", source["plan"])
        assert item["source_plan"] == {
            "file": plan_ref["file"],
            "sha256": plan_ref["sha256"],
        }


def test_held_out_and_tuning_sources_never_cross(items: list[JsonObj]) -> None:
    """Held-out items come only from held-out sources and tuning from tuning."""
    for item in items:
        source_id = str(item["source_plan_id"])
        if item["half"] == "held_out":
            assert source_id in HELD_OUT_SOURCES, item["id"]
            assert source_id not in TUNING_SOURCES
        else:
            assert source_id in TUNING_SOURCES, item["id"]
            assert source_id not in HELD_OUT_SOURCES


def test_sources_with_checker_errors_record_their_baseline_repairs(
    doc: JsonObj, items: list[JsonObj]
) -> None:
    """Each item lists its source's mechanical repairs, and the document does too."""
    sources = cast("JsonObj", doc["sources"])
    for item in items:
        record = cast("JsonObj", sources[str(item["source_plan_id"])])
        assert item["baseline_repairs"] == record["baseline_repairs"], item["id"]
    assert sources["PL-e3"]
    assert cast("JsonObj", sources["PL-e4"])["baseline_repairs"] == []


# ---------------------------------------------------------------------------
# Family rules
# ---------------------------------------------------------------------------


def test_every_family_a_seed_trips_exactly_its_intended_rule(
    builder: ModuleType, sources: dict[str, object], items: list[JsonObj]
) -> None:
    """Through ``check_plan``, a family A seed's ERRORs are its rule and no other."""
    witnessed = {w.rule_id for w in WITNESSES} - {"SP-0", "SP-D"}
    for item in _family(items, "A"):
        rule = str(item["intended_rule"])
        assert rule in witnessed
        report = _check(builder, sources, item)
        fired = {f.rule_id for f in report.errors}  # pyright: ignore[reportAttributeAccessIssue]
        assert fired == {rule}, f"{item['id']}: {sorted(fired)}"
        assert item["checker_errors"] == [rule]


def test_every_family_b_seed_has_no_error(
    builder: ModuleType, sources: dict[str, object], items: list[JsonObj]
) -> None:
    """A family B seed passes ``check_plan`` with no ERROR at all."""
    for item in _family(items, "B"):
        report = _check(builder, sources, item)
        assert report.ok, item["id"]  # pyright: ignore[reportAttributeAccessIssue]
        assert not report.errors  # pyright: ignore[reportAttributeAccessIssue]
        assert item["checker_errors"] == []


def test_family_b_seeds_add_no_warning_to_their_baseline(
    builder: ModuleType, sources: dict[str, object], items: list[JsonObj]
) -> None:
    """Any warning a family B seed carries is one its clean source already had."""
    for item in _family(items, "B"):
        source = sources[str(item["source_plan_id"])]
        baseline, _ = builder.repair_baseline(source)
        base_keys = builder._warning_keys(builder.run_check(baseline, source))
        seed_keys = builder._warning_keys(_check(builder, sources, item))
        assert seed_keys <= base_keys, f"{item['id']}: {sorted(seed_keys - base_keys)}"


def test_every_seed_differs_from_its_source_only_at_declared_paths(
    sources: dict[str, object], items: list[JsonObj]
) -> None:
    """A seed is its source plan plus the baseline repairs plus its edited paths."""
    for item in items:
        source = sources[str(item["source_plan_id"])]
        declared = [
            *cast("list[str]", item["edited_paths"]),
            *cast("list[str]", item["baseline_repairs"]),
        ]
        original = source.plan  # pyright: ignore[reportAttributeAccessIssue]
        for pointer in _leaf_diffs(original, _seed_plan(item), ""):
            assert any(
                pointer.startswith(p) or p.startswith(pointer) for p in declared
            ), f"{item['id']}: undeclared change at {pointer}"
        assert any(
            pointer.startswith(p) or p.startswith(pointer)
            for pointer in _leaf_diffs(original, _seed_plan(item), "")
            for p in cast("list[str]", item["edited_paths"])
        ), f"{item['id']}: no change at an edited path"


def _leaf_diffs(a: object, b: object, path: str) -> Iterator[str]:
    """Yield the JSON pointers at which two decoded documents differ.

    Args:
        a: The first value.
        b: The second value.
        path: The pointer of both values.

    Yields:
        str: A pointer to the shallowest differing value.
    """
    if isinstance(a, dict) and isinstance(b, dict):
        left, right = cast("JsonObj", a), cast("JsonObj", b)
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                yield f"{path}/{key}"
            else:
                yield from _leaf_diffs(left[key], right[key], f"{path}/{key}")
    elif isinstance(a, list) and isinstance(b, list):
        la, lb = cast("list[object]", a), cast("list[object]", b)
        for index in range(max(len(la), len(lb))):
            if index >= len(la) or index >= len(lb):
                yield f"{path}/{index}"
            else:
                yield from _leaf_diffs(la[index], lb[index], f"{path}/{index}")
    elif a != b:
        yield path


def test_no_rule_supplies_more_than_two_family_a_seeds_in_a_half(
    items: list[JsonObj],
) -> None:
    """D12: spread the rules so none supplies more than two seeds in a half."""
    for half in ("tuning", "held_out"):
        counts: dict[str, int] = {}
        for item in _family(items, "A"):
            if item["half"] == half:
                rule = str(item["intended_rule"])
                counts[rule] = counts.get(rule, 0) + 1
        assert counts
        assert max(counts.values()) <= 2, (half, counts)


def test_held_out_minimums_are_met(items: list[JsonObj]) -> None:
    """Five books: at least two family A seeds on different rules and one B each."""
    held = [i for i in items if i["half"] == "held_out"]
    assert len(held) >= 15
    for book in HELD_OUT_BOOKS:
        a_rules = {
            str(i["intended_rule"])
            for i in _family(held, "A")
            if cast("JsonObj", i["book"])["unit"] == book
        }
        b_seeds = [
            i for i in _family(held, "B") if cast("JsonObj", i["book"])["unit"] == book
        ]
        assert len(a_rules) >= 2, (book, a_rules)
        assert len(b_seeds) >= 1, book
    seeded_units = {str(cast("JsonObj", i["book"])["unit"]) for i in held}
    assert seeded_units == set(HELD_OUT_BOOKS)


def test_tuning_minimums_are_met(items: list[JsonObj]) -> None:
    """The tuning half has at least six family A seeds and three family B seeds."""
    tuning = [i for i in items if i["half"] == "tuning"]
    assert len(_family(tuning, "A")) >= 6
    assert len(_family(tuning, "B")) >= 3


def test_every_rule_and_class_available_is_covered(items: list[JsonObj]) -> None:
    """Held-out family A covers SP-1 to SP-9; both families cover every class."""
    held_a = {
        str(i["intended_rule"]) for i in _family(items, "A") if i["half"] == "held_out"
    }
    assert held_a == set(SEED_RULES)
    for half in ("tuning", "held_out"):
        classes = {
            str(i["intended_class"]) for i in _family(items, "B") if i["half"] == half
        }
        assert classes == set(B_CLASSES), half
    rule_counts: dict[str, int] = {}
    for item in _family(items, "A"):
        rule = str(item["intended_rule"])
        rule_counts[rule] = rule_counts.get(rule, 0) + 1
    assert rule_counts["SP-4"] == 3  # two witnesses held out, one tuning


# ---------------------------------------------------------------------------
# Reproducibility and hygiene
# ---------------------------------------------------------------------------


def test_the_committed_files_are_what_the_builder_produces(
    builder: ModuleType, built: dict[Path, str]
) -> None:
    """Rebuilding from the sources reproduces every committed file byte for byte."""
    assert builder._drift(built) == []
    for path, text in built.items():
        assert path.read_text("utf-8") == text


def test_check_mode_exits_zero_on_a_clean_tree_and_one_on_drift(
    builder: ModuleType,
    built: dict[Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--check`` exits 0 when the files match and 1 when one differs."""
    monkeypatch.setattr(builder, "expected_files", lambda: built)
    assert builder.main(["--check"]) == 0
    first = next(p for p in built if p.name.endswith(".plan.json"))
    drifted = {**built, first: built[first] + " "}
    monkeypatch.setattr(builder, "expected_files", lambda: drifted)
    assert builder.main(["--check"]) == 1


def test_build_is_deterministic(builder: ModuleType, built: dict[Path, str]) -> None:
    """Two builds give identical output (no randomness, no ordering drift)."""
    again = cast("dict[Path, str]", builder.expected_files())
    assert again == built


def test_no_synthetic_file_contains_an_em_dash() -> None:
    """The directive: no em-dash in any synthetic file, README or the builder."""
    paths = [*_SYNTH.iterdir(), _BUILDER, Path(__file__)]
    assert len(paths) > 30
    for path in paths:
        assert EM_DASH not in path.read_text("utf-8"), path.name
