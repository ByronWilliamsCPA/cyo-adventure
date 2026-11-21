"""Unit tests for SP-D plan density and the corpus it was calibrated on (AL-848).

SP-D is advisory: it may only ever add WARNING findings. The corpus tests run
every committed plan whose book is in the working tree (the seven
hand-written plans, the blind extractions whose source books are committed
files, and the six WP-2.3 smoke plans on their retained shapes) and pin that
the hand-written plans raise no SP-D warning, every smoke plan raises at least
one, SP-D never raises an ERROR, and the AL-849 SP-3 change touches none of
these plans.
"""

from __future__ import annotations

import copy
import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.storyplan import StoryPlan
from cyo_adventure.storyplan.checks import (
    COST_REUSE_MAX,
    DENSITY_RULE,
    EMPTY_NODE_SHARE_MAX,
    INTENT_REUSE_MAX,
    LEDGER_DENSITY_MIN,
    WITNESSES,
    base_example,
    check_plan,
    plan_density,
)
from cyo_adventure.storyplan.shapes import load_registry, load_shape, shape_entry_for
from cyo_adventure.validator.report import Severity, ValidationReport

_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE = _ROOT / "docs" / "planning" / "evidence"
_BLIND_SETS = (
    ("story-plan-retro/plans/manifest.json", "story-plan-retro/plans"),
    ("story-plan-retro/rerun/manifest.json", "story-plan-retro/rerun/plans"),
    ("fresh-corpus-2026-11-21/manifest.json", "fresh-corpus-2026-11-21/plans"),
)


def _density_findings(report: ValidationReport) -> list[str]:
    return [f.message for f in report.findings if f.rule_id == DENSITY_RULE]


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------


@cache
def _corpus() -> tuple[tuple[str, StoryPlan, Storybook, str | None], ...]:
    """Every committed plan whose book is readable from the working tree.

    Blind extractions whose source book only exists at an old revision are
    left out (a shallow CI clone may not have it); the rest are verified
    against the manifest's SHA-256 so a book edit cannot silently change
    what is measured.
    """
    found: list[tuple[str, StoryPlan, Storybook, str | None]] = []
    for path in sorted((_ROOT / "out").glob("*.plan.json")):
        slug = path.name.removesuffix(".plan.json")
        raw = (_ROOT / "out" / f"{slug}.filled.json").read_bytes()
        found.append(
            (
                f"hand:{slug}",
                StoryPlan.model_validate_json(path.read_text(encoding="utf-8")),
                Storybook.model_validate_json(raw),
                hashlib.sha256(raw).hexdigest(),
            )
        )
    for manifest, plans in _BLIND_SETS:
        data = json.loads((_EVIDENCE / manifest).read_text(encoding="utf-8"))
        for plan_id, entry in data["extractions"].items():
            revision = entry.get("revision")
            if isinstance(revision, str) and revision.startswith("git:"):
                continue
            raw = (_ROOT / entry["source_file"]).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != entry["book_sha256"]:
                continue
            plan_path = _EVIDENCE / plans / f"{plan_id}.plan.json"
            found.append(
                (
                    f"blind:{plan_id}",
                    StoryPlan.model_validate_json(plan_path.read_text("utf-8")),
                    Storybook.model_validate_json(raw),
                    digest,
                )
            )
    registry = load_registry()
    runs = _EVIDENCE / "plan-generation-smoke-2026-11-21" / "runs"
    for path in sorted(runs.glob("*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        entry = shape_entry_for(registry, run["shape"]["id"])
        assert entry is not None
        found.append(
            (
                f"smoke:{path.stem}",
                StoryPlan.model_validate(run["plan"]),
                Storybook.model_validate(load_shape(entry)),
                None,
            )
        )
    return tuple(found)


@cache
def _reports() -> dict[str, ValidationReport]:
    return {
        name: check_plan(plan, book, book_digest=digest)
        for name, plan, book, digest in _corpus()
    }


@pytest.mark.unit
def test_corpus_covers_every_group() -> None:
    names = [name for name, *_ in _corpus()]
    assert sum(n.startswith("hand:") for n in names) == 7
    assert sum(n.startswith("smoke:") for n in names) == 6
    assert sum(n.startswith("blind:") for n in names) >= 10


@pytest.mark.unit
def test_density_is_never_an_error_and_never_changes_ok() -> None:
    for name, report in _reports().items():
        density = [f for f in report.findings if f.rule_id == DENSITY_RULE]
        assert all(f.severity is Severity.WARNING for f in density), name
        assert report.ok == (not report.errors), name


@pytest.mark.unit
def test_hand_written_plans_raise_no_density_warning() -> None:
    for name, report in _reports().items():
        if name.startswith("hand:"):
            assert _density_findings(report) == [], name


@pytest.mark.unit
def test_every_thin_smoke_plan_raises_a_density_warning() -> None:
    # The six WP-2.3 smoke plans passed SP-1 to SP-9 while recording almost
    # nothing (AL-848); each trips at least one density metric.
    for name, report in _reports().items():
        if name.startswith("smoke:"):
            assert report.ok, name
            assert _density_findings(report), name


@pytest.mark.unit
def test_largest_smoke_plan_trips_every_ratio_metric() -> None:
    reports = _reports()
    messages = " | ".join(_density_findings(reports["smoke:6"]))
    assert "neither require nor establish a fact" in messages
    assert "the ledger records" in messages
    assert "share their intent" in messages
    assert "share their cost" in messages


@pytest.mark.unit
def test_no_existing_plan_meets_the_failure_fact_case() -> None:
    # The AL-849 SP-3 change (a failure fact marked against the truth becomes
    # a WARNING) applies to no committed plan, so it changed no SP-3 ERROR in
    # the corpus.
    for name, report in _reports().items():
        assert not any(
            f.rule_id == "SP-3" and "failure fact" in f.message for f in report.findings
        ), name


# ---------------------------------------------------------------------------
# The metrics on focused fixtures
# ---------------------------------------------------------------------------


def _cave() -> tuple[StoryPlan, Storybook]:
    root = _ROOT / "out"
    plan = StoryPlan.model_validate_json(
        (root / "the-cave-of-echoes.plan.json").read_text(encoding="utf-8")
    )
    book = Storybook.model_validate_json(
        (root / "the-cave-of-echoes.filled.json").read_bytes()
    )
    return plan, book


def _thinned(plan: StoryPlan, **changes: object) -> StoryPlan:
    doc = cast("dict[str, Any]", copy.deepcopy(plan.model_dump(mode="json")))
    if changes.get("empty_nodes"):
        for node in doc["nodes"].values():
            node["requires"] = []
            node["establishes"] = []
        for choice in doc["choices"].values():
            choice["requires"] = []
            choice["establishes"] = []
        doc["truth"]["facts"] = doc["truth"]["facts"][:1]
        for member in doc["cast"].values():
            member["knows"] = []
        keep = doc["truth"]["facts"][0]
        doc["facts"] = {keep: {"text": doc["facts"][keep]["text"]}}
        first = next(iter(doc["nodes"]))
        doc["nodes"][first]["establishes"] = [keep]
    if "intent" in changes:
        for choice in doc["choices"].values():
            choice["intent"] = changes["intent"]
    if "cost" in changes:
        for choice in doc["choices"].values():
            choice["cost"] = changes["cost"]
    return StoryPlan.model_validate(doc)


@pytest.mark.unit
def test_the_hand_written_cave_plan_measures_dense() -> None:
    plan, book = _cave()
    density = plan_density(plan, book)
    assert density is not None
    assert density.empty_share <= EMPTY_NODE_SHARE_MAX
    assert density.ledger_density >= LEDGER_DENSITY_MIN
    assert density.intent_reuse <= INTENT_REUSE_MAX
    assert density.cost_reuse <= COST_REUSE_MAX
    assert density.unreferenced_facts == ()
    assert set(density.to_dict()) >= {"empty_share", "ledger_density"}


@pytest.mark.unit
def test_a_plan_recording_nothing_warns_on_passages_and_ledger() -> None:
    plan, book = _cave()
    report = check_plan(_thinned(plan, empty_nodes=True), book)
    messages = _density_findings(report)
    assert any("neither require nor establish a fact" in m for m in messages)
    assert any("the ledger records 1 referenced facts" in m for m in messages)
    density = [f for f in report.findings if f.rule_id == DENSITY_RULE]
    assert all(f.severity is Severity.WARNING for f in density)


@pytest.mark.unit
def test_one_intent_and_one_cost_everywhere_warn() -> None:
    plan, book = _cave()
    report = check_plan(_thinned(plan, intent="Go on.", cost="time"), book)
    messages = _density_findings(report)
    assert any("share their intent" in m and "'go on'" in m for m in messages), messages
    assert any("share their cost" in m and "'time'" in m for m in messages)


@pytest.mark.unit
def test_a_shared_none_cost_is_not_cost_reuse() -> None:
    # A shared "none" at a decision is SP-8's concern, not SP-D's.
    plan, book = _cave()
    density = plan_density(_thinned(plan, cost="none"), book)
    assert density is not None
    assert density.cost_reuse == 0.0


@pytest.mark.unit
def test_one_intent_reused_for_one_destination_is_not_reuse() -> None:
    # Two choices to the same passage may share an intent (a hub repeating one
    # move); only reuse across different destinations counts.
    book, plan = base_example()
    doc = cast("dict[str, Any]", plan)
    doc["choices"]["c_cave_on"]["intent"] = "go home"
    doc["choices"]["c_tunnel_on"]["intent"] = "go home"
    density = plan_density(
        StoryPlan.model_validate(doc), Storybook.model_validate(book)
    )
    assert density is not None
    assert density.intent_reusers == ()


@pytest.mark.unit
def test_a_tiny_book_is_not_judged_on_ratios() -> None:
    # The base example has five passages and eight decision choices, below
    # both minimums: even with every intent and cost shared, no ratio warns.
    book, plan = base_example()
    doc = cast("dict[str, Any]", plan)
    for choice in doc["choices"].values():
        choice["intent"] = "walk on"
        choice["cost"] = "time"
    report = check_plan(StoryPlan.model_validate(doc), Storybook.model_validate(book))
    assert _density_findings(report) == []


@pytest.mark.unit
def test_an_unreferenced_fact_is_named_and_a_marked_opposite_is_not() -> None:
    book, plan = WITNESSES[-1].build()
    report = check_plan(StoryPlan.model_validate(plan), Storybook.model_validate(book))
    [finding] = [f for f in report.findings if f.rule_id == DENSITY_RULE]
    assert finding.severity is Severity.WARNING
    assert getattr(finding, "fact_id", None) == "fox_seen"
    # stranger_left_map is never established but is marked against the truth:
    # it names what the book must never tell, so it is not reported.
    assert "stranger_left_map" not in finding.message


@pytest.mark.unit
def test_density_is_none_when_coverage_blocks() -> None:
    book, plan = base_example()
    doc = cast("dict[str, Any]", plan)
    del doc["choices"]["c_road"]
    assert (
        plan_density(StoryPlan.model_validate(doc), Storybook.model_validate(book))
        is None
    )
