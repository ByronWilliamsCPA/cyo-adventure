"""Unit tests for the checker-repaired clean baselines (WP-3.7, D12).

Owner decision 2026-11-22 (option 1): the plan reviewer's clean sample is the
checker-repaired baseline of each clean plan. ``scripts/build_clean_baselines.py``
writes them under ``docs/planning/evidence/plan-reviewer/clean-baselines/``,
reusing ``repair_baseline`` from ``scripts/build_synthetic_plans.py``. These tests
hold that: baselines exist for exactly the expected plan set; every baseline is
checker-clean; repairs are recorded; each baseline is byte-identical to the seed
source of the synthetic builder; the committed files are what the builder
produces; and no file contains the em-dash character.

scripts/ is not an importable package, so both builders are loaded from their
file paths. A shallow clone lacks the pinned git revisions the builders read; the
tests that need them skip there, and the structural tests run on the committed
files.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.storyplan.checks import check_plan
from cyo_adventure.storyplan.models import StoryPlan

if TYPE_CHECKING:
    from types import ModuleType

_REPO = Path(__file__).resolve().parents[2]
_DIR = _REPO / "docs/planning/evidence/plan-reviewer/clean-baselines"
_MANIFEST = _DIR / "manifest.json"
_SYNTH_SET = (
    _REPO
    / "docs/planning/evidence/plan-reviewer/synthetic/validation-set.synthetic.json"
)
_REAL_SET = _REPO / "docs/planning/evidence/continuity-reader/validation-set.json"

JsonObj = dict[str, object]

EM_DASH = chr(0x2014)
EXPECTED_PLANS = {
    "PL-e1",
    "PL-e2",
    "PL-e3",
    "PL-e4",
    "PL-e5",
    "PL-f1",
    "PL-f2",
    "PL-f3",
    "PL-f4",
    "PL-f5",
    "PL-the-hollow-lighthouse-postfix",
    "PL-the-vanishing-orchard-postfix",
}
EXCLUDED_PLANS = {
    "PL-the-midnight-museum-postfix",
    "PL-c1",
    "PL-d3",
    "PL-x3",
}
NEEDED_REPAIR = {"PL-e1", "PL-e2", "PL-e3", "PL-e5", "PL-f2", "PL-f3", "PL-f4", "PL-f5"}
REPAIR_COUNTS = {
    "PL-e1": 1,
    "PL-e2": 7,
    "PL-e3": 16,
    "PL-e5": 1,
    "PL-f2": 2,
    "PL-f3": 3,
    "PL-f4": 17,
    "PL-f5": 2,
}


def _load(name: str) -> ModuleType:
    """Load a script from scripts/ by file path.

    Args:
        name: The module name, equal to the script's file stem.

    Returns:
        ModuleType: The loaded module.
    """
    spec = importlib.util.spec_from_file_location(
        name, _REPO / "scripts" / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def synth() -> ModuleType:
    """Return the synthetic builder module."""
    return _load("build_synthetic_plans")


@pytest.fixture(scope="module")
def builder(synth: ModuleType) -> ModuleType:
    """Return the clean-baselines builder module."""
    assert synth is not None
    return _load("build_clean_baselines")


@pytest.fixture(scope="module")
def doc() -> JsonObj:
    """Return the committed manifest."""
    return cast("JsonObj", json.loads(_MANIFEST.read_text("utf-8")))


@pytest.fixture(scope="module")
def items(doc: JsonObj) -> list[JsonObj]:
    """Return the committed manifest items."""
    return cast("list[JsonObj]", doc["items"])


@pytest.fixture(scope="module")
def built(builder: ModuleType) -> dict[Path, str]:
    """Rebuild every output, or skip in a shallow clone."""
    try:
        return cast("dict[Path, str]", builder.expected_files())
    except builder.SYN.MissingRevisionError:
        pytest.skip("pinned revisions are not in this checkout (shallow clone)")


def test_baselines_exist_for_exactly_the_expected_plans(
    items: list[JsonObj],
) -> None:
    """Twelve strong clean plans; no minor-only plan and not the weak control."""
    ids = {cast("str", i["source_plan_id"]) for i in items}
    assert ids == EXPECTED_PLANS
    assert not ids & EXCLUDED_PLANS
    assert len(items) == len(ids)
    on_disk = {p.name for p in _DIR.glob("*.baseline.plan.json")}
    assert on_disk == {f"{pid}.baseline.plan.json" for pid in EXPECTED_PLANS}


def test_expected_set_is_the_strong_pass_plans_without_minor_only(
    builder: ModuleType,
) -> None:
    """The builder's selection rule yields the expected ids from the real set."""
    real = cast("JsonObj", json.loads(_REAL_SET.read_text("utf-8")))
    plans = {
        cast("str", i["id"]): i
        for i in cast("list[JsonObj]", real["items"])
        if i["kind"] == "plan"
    }
    assert set(builder.clean_plan_ids(plans)) == EXPECTED_PLANS
    strong_pass = {
        pid
        for pid, i in plans.items()
        if i["expected_verdict"] == "pass" and i["label_strength"] == "strong"
    }
    assert strong_pass - EXPECTED_PLANS == EXCLUDED_PLANS - {"PL-x3"}


def test_manifest_item_fields(doc: JsonObj, items: list[JsonObj]) -> None:
    """Each item carries the documented fields and labels."""
    assert doc["schema"] == "clean-baselines/v1"
    real = cast("JsonObj", json.loads(_REAL_SET.read_text("utf-8")))
    real_by_id = {cast("str", i["id"]): i for i in cast("list[JsonObj]", real["items"])}
    for item in items:
        pid = cast("str", item["source_plan_id"])
        source = real_by_id[pid]
        assert item["id"] == f"CBL-{pid}"
        assert item["kind"] == "plan"
        assert item["half"] == source["half"]
        assert item["book"] == source["book"]
        assert item["known_residuals"] == source["known_residuals"]
        assert item["expected_verdict"] == "pass"
        assert item["scored_for"] == "D12"
        assert item["label_strength"] == "strong"
        assert item["checker_clean"] is True
        src_plan = cast("JsonObj", item["source_plan"])
        assert src_plan == {
            "file": cast("JsonObj", source["plan"])["file"],
            "sha256": cast("JsonObj", source["plan"])["sha256"],
        }


def test_every_baseline_is_checker_clean_and_hashes_to_the_manifest(
    synth: ModuleType, items: list[JsonObj]
) -> None:
    """Re-run the checker on each written file; the manifest hash matches it."""
    plan_items = synth.load_validation_set()
    try:
        for item in items:
            ref = cast("JsonObj", item["plan"])
            data = (_REPO / cast("str", ref["file"])).read_bytes()
            assert hashlib.sha256(data).hexdigest() == ref["sha256"]
            source = synth.load_source(cast("str", item["source_plan_id"]), plan_items)
            plan = StoryPlan.model_validate(json.loads(data))
            report = check_plan(plan, source.book, book_digest=source.digest)
            assert report.ok, (item["id"], sorted(synth.error_rules(report)))
            assert not report.errors
    except synth.MissingRevisionError:
        pytest.skip("pinned revisions are not in this checkout (shallow clone)")


def test_repairs_are_recorded(items: list[JsonObj]) -> None:
    """repair_count, needed_repair and the pointer list agree, per plan."""
    for item in items:
        pid = cast("str", item["source_plan_id"])
        repairs = cast("list[str]", item["repairs"])
        assert item["repair_count"] == len(repairs) == REPAIR_COUNTS.get(pid, 0), pid
        assert item["needed_repair"] is (pid in NEEDED_REPAIR), pid
        assert repairs == sorted(set(repairs)), pid
        assert all(p.startswith("/") for p in repairs), pid


def test_summary_counts(doc: JsonObj) -> None:
    """The summary reports halves, books and how many needed repair."""
    summary = cast("JsonObj", doc["summary"])
    assert summary["items"] == 12
    assert summary["needed_repair"] == 8
    assert summary["no_repair"] == 4
    assert summary["repairs"] == sum(REPAIR_COUNTS.values()) == 49
    by_half = cast("dict[str, JsonObj]", summary["by_half"])
    assert by_half["held_out"]["total"] == 10
    assert by_half["held_out"]["needed_repair"] == 8
    assert by_half["tuning"]["total"] == 2
    assert by_half["tuning"]["needed_repair"] == 0
    by_book = cast("dict[str, JsonObj]", summary["by_book"])
    assert {u: b["total"] for u, b in by_book.items()} == {
        "the-cave-of-echoes": 2,
        "the-hollow-lighthouse": 1,
        "the-mapmakers-island": 2,
        "the-midnight-museum": 2,
        "the-signal-in-the-static": 2,
        "the-sky-ship-stowaway": 2,
        "the-vanishing-orchard": 1,
    }
    assert by_book["the-mapmakers-island"]["repairs"] == 33


def test_baseline_is_byte_identical_to_the_synthetic_seed_source(
    synth: ModuleType, items: list[JsonObj]
) -> None:
    """repair_baseline output, encoded, is exactly the committed baseline file."""
    plan_items = synth.load_validation_set()
    try:
        for item in items:
            pid = cast("str", item["source_plan_id"])
            source = synth.load_source(pid, plan_items)
            baseline, repairs = synth.repair_baseline(source)
            text = synth.encode_plan(baseline)
            ref = cast("JsonObj", item["plan"])
            assert (_REPO / cast("str", ref["file"])).read_text("utf-8") == text, pid
            assert repairs == item["repairs"], pid
    except synth.MissingRevisionError:
        pytest.skip("pinned revisions are not in this checkout (shallow clone)")


def test_synthetic_seeds_still_build_from_the_same_baselines(
    synth: ModuleType, items: list[JsonObj]
) -> None:
    """Each synthetic item's baseline repairs equal its source's manifest repairs."""
    manifest = {cast("str", i["source_plan_id"]): i for i in items}
    synthetic = cast("JsonObj", json.loads(_SYNTH_SET.read_text("utf-8")))
    seeds = cast("list[JsonObj]", synthetic["items"])
    assert len(seeds) == 32
    sources = {cast("str", s["source_plan_id"]) for s in seeds}
    assert sources <= set(manifest)
    for seed in seeds:
        base = manifest[cast("str", seed["source_plan_id"])]
        assert seed["baseline_repairs"] == base["repairs"], seed["id"]
        assert seed["half"] == base["half"], seed["id"]
    assert synth.SP9_REWORDINGS  # the table that repairs e2 and f5


def test_committed_files_are_what_the_builder_produces(
    builder: ModuleType, built: dict[Path, str]
) -> None:
    """No drift and no stray baseline file."""
    assert builder._drift(built) == []
    assert _MANIFEST in built


def test_a_baseline_that_still_fails_the_checker_is_refused(
    builder: ModuleType, synth: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The build fails when a repaired plan still raises an ERROR."""
    plan_items = synth.load_validation_set()
    try:
        source = synth.load_source("PL-e3", plan_items)
    except synth.MissingRevisionError:
        pytest.skip("pinned revisions are not in this checkout (shallow clone)")
    monkeypatch.setattr(
        synth, "repair_baseline", lambda _source: (dict(source.plan), [])
    )
    with pytest.raises(synth.SeedError, match="still raises ERROR rules"):
        builder._build_item("PL-e3", plan_items)


def test_no_em_dash_in_the_baselines() -> None:
    """The repository bans U+2014; neither the manifest nor a baseline carries one."""
    for path in [_MANIFEST, *_DIR.glob("*.baseline.plan.json"), _DIR / "README.md"]:
        assert EM_DASH not in path.read_text("utf-8"), path.name
