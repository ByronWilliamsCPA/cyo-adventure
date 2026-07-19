"""Unit tests for moderation.leaf_diversity: the ATG pipeline wiring (WS-1 D1).

Two suites, per ``docs/planning/ws1-leaf-diversity-sprint-design.md`` section 6:

- ``findings_from_anti_template`` (pure): built directly from hand-constructed
  ``AntiTemplateReport`` instances, no story fixtures needed.
- ``run_leaf_diversity_check`` (async, fail-open branches plus one FAIL
  happy-path): built from the committed WS-0 panel fixtures
  (``tests/data/diversity_panel/fills/``) and ``diversity.panel.
  make_noun_swap_variant``, with ``load_family_history``/``load_version_blob``
  monkeypatched at this module's import site (no live database).
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from cyo_adventure.db.models import Storybook as DbStorybook
from cyo_adventure.db.models import StorybookVersion as DbStorybookVersion
from cyo_adventure.diversity.history import HistoryEntry
from cyo_adventure.diversity.normalize import coerce_storybook
from cyo_adventure.diversity.panel import make_noun_swap_variant
from cyo_adventure.diversity.report import AntiTemplateReport, AntiTemplateVerdict
from cyo_adventure.moderation import leaf_diversity as leaf_diversity_mod
from cyo_adventure.moderation.leaf_diversity import (
    findings_from_anti_template,
    run_leaf_diversity_check,
)
from cyo_adventure.moderation.report import ModerationReport, Source, Verdict

_FILLS_DIR = Path("tests/data/diversity_panel/fills")
_CAVE_SPACE_PATH = _FILLS_DIR / "the-cave-of-echoes.space-station.filled.json"

# Mirrors panel.json's committed "cave-space-swap" synthetic (a known ATG FAIL
# pair, WS-0 design doc section 6.2): a word-boundary noun substitution over
# one committed fill, never itself committed as a story file.
_NOUN_SWAPS: dict[str, str] = {
    "station": "burrow",
    "drone": "ferret",
    "airlock": "gate",
    "hull": "wall",
    "corridor": "tunnel",
    "console": "desk",
    "oxygen": "air",
    "solar": "lunar",
    "panel": "plank",
    "module": "room",
    "gravity": "weight",
    "orbit": "circle",
    "engine": "motor",
    "signal": "whistle",
    "metal": "wood",
    "light": "lamp",
    "door": "hatch",
    "echo": "ring",
}


def _load_blob(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def _cave_space_fail_pair() -> tuple[dict[str, object], dict[str, object]]:
    """Return (current_blob, fail_partner_blob), a known ATG FAIL pair.

    ``current`` is the committed cave-space fill; the partner is its
    noun-swap variant (panel.json's ``cave-space`` vs ``cave-space-swap``).
    """
    raw = _load_blob(_CAVE_SPACE_PATH)
    current_story = coerce_storybook(raw)
    variant_story = make_noun_swap_variant(current_story, _NOUN_SWAPS)
    return raw, variant_story.model_dump(mode="json")


def _report(
    verdict: AntiTemplateVerdict,
    *,
    median: float = 0.2,
    p25: float = 0.15,
    p10: float = 0.1,
    templated_nodes: tuple[str, ...] = (),
    node_count: int = 10,
) -> AntiTemplateReport:
    return AntiTemplateReport(
        verdict=verdict,
        median_distance=median,
        p25_distance=p25,
        p10_distance=p10,
        mean_bigram_distance=0.3,
        entity_count=5,
        templated_nodes=templated_nodes,
        node_count=node_count,
    )


def _db_storybook(
    story_id: str = "s2", family_id: uuid.UUID | None = None
) -> DbStorybook:
    return DbStorybook(id=story_id, family_id=family_id or uuid.uuid4())


def _db_version(
    blob: dict[str, object],
    *,
    skeleton_slug: str | None = "the-cave-of-echoes",
    story_id: str = "s2",
    version: int = 1,
) -> DbStorybookVersion:
    return DbStorybookVersion(
        storybook_id=story_id,
        version=version,
        blob=blob,
        skeleton_slug=skeleton_slug,
    )


def _history_entry(
    *,
    storybook_id: str = "s1",
    version: int = 1,
    skeleton_slug: str | None = "the-cave-of-echoes",
) -> HistoryEntry:
    return HistoryEntry(
        storybook_id=storybook_id,
        version=version,
        skeleton_slug=skeleton_slug,
        theme_sig=frozenset(),
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# findings_from_anti_template: the pure verdict -> Finding mapping.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fail_with_templated_nodes_yields_flag_per_node_plus_summary() -> None:
    """FAIL with N templated nodes yields N FLAGs (one per node) plus one
    ADVISORY summary, each with the section-3.4-mandated producer fields."""
    report = _report(
        AntiTemplateVerdict.FAIL, templated_nodes=("n1", "n2", "n3"), node_count=10
    )

    findings = findings_from_anti_template(
        report, partner_storybook_id="book-1", partner_version=2
    )

    flags = [f for f in findings if f.verdict is Verdict.FLAG]
    advisories = [f for f in findings if f.verdict is Verdict.ADVISORY]
    assert len(findings) == 4
    assert len(flags) == 3
    assert {f.node_id for f in flags} == {"n1", "n2", "n3"}
    for finding in flags:
        assert finding.stage == 0
        assert finding.source is Source.PIPELINE
        assert finding.category == "leaf_diversity"
        assert finding.score is None
    assert len(advisories) == 1
    summary = advisories[0]
    assert summary.node_id is None
    assert summary.category == "leaf_diversity_summary"
    assert summary.stage == 0
    assert summary.source is Source.PIPELINE
    assert summary.score is None


@pytest.mark.unit
def test_fail_with_no_templated_nodes_yields_summary_only() -> None:
    """A FAIL whose median/p25 trip the boundary but no node crosses the
    per-node floor degrades to the ADVISORY summary alone (design doc section
    3.4 edge case): there is no node-targeted repair instruction to give."""
    report = _report(AntiTemplateVerdict.FAIL, templated_nodes=())

    findings = findings_from_anti_template(
        report, partner_storybook_id="book-2", partner_version=1
    )

    assert len(findings) == 1
    assert findings[0].verdict is Verdict.ADVISORY
    assert findings[0].category == "leaf_diversity_summary"
    assert findings[0].node_id is None


@pytest.mark.unit
def test_warn_yields_summary_only_never_flag() -> None:
    """WARN never produces a FLAG, even if templated_nodes were populated:
    only a FAIL verdict drives per-node repair targeting."""
    report = _report(AntiTemplateVerdict.WARN, templated_nodes=("n1",), node_count=5)

    findings = findings_from_anti_template(
        report, partner_storybook_id="book-3", partner_version=4
    )

    assert len(findings) == 1
    assert findings[0].verdict is Verdict.ADVISORY
    assert findings[0].category == "leaf_diversity_summary"


@pytest.mark.unit
def test_pass_yields_no_findings() -> None:
    """PASS_ is zero findings, zero noise."""
    report = _report(AntiTemplateVerdict.PASS_)

    findings = findings_from_anti_template(
        report, partner_storybook_id="book-4", partner_version=1
    )

    assert findings == []


@pytest.mark.unit
def test_messages_contain_no_story_prose() -> None:
    """Messages are prose-free by design: they enter the PII-guarded repair
    prompt, so no committed fixture body may appear inside one."""
    raw = _load_blob(_CAVE_SPACE_PATH)
    bodies = [
        cast("str", node["body"])
        for node in cast("list[dict[str, object]]", raw["nodes"])
    ]
    report = _report(
        AntiTemplateVerdict.FAIL, templated_nodes=("n_start",), node_count=64
    )

    findings = findings_from_anti_template(
        report, partner_storybook_id="book-5", partner_version=3
    )

    for finding in findings:
        for body in bodies:
            assert body not in finding.message


@pytest.mark.unit
def test_flag_findings_drive_soft_gate_not_hard_block() -> None:
    """The FLAG findings a FAIL produces trigger has_soft_flag without ever
    tripping has_hard_block, so they can only ever drive the bounded repair,
    never auto_reject (design doc section 3.4)."""
    report = _report(AntiTemplateVerdict.FAIL, templated_nodes=("n1",))
    findings = findings_from_anti_template(
        report, partner_storybook_id="book-6", partner_version=1
    )

    moderation_report = ModerationReport()
    for finding in findings:
        moderation_report.add(finding)

    assert moderation_report.has_soft_flag is True
    assert moderation_report.has_hard_block is False


# ---------------------------------------------------------------------------
# run_leaf_diversity_check: fail-open branches, plus one FAIL happy path.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skeleton_slug_none_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh_generation / slug-less import has no tree to compare against."""
    storybook = _db_storybook()
    version_row = _db_version({"id": "x"}, skeleton_slug=None)
    history_mock = AsyncMock()
    monkeypatch.setattr(leaf_diversity_mod, "load_family_history", history_mock)

    findings = await run_leaf_diversity_check(
        session=MagicMock(), storybook=storybook, version_row=version_row
    )

    assert findings == []
    history_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_history_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A family with no history at all: first use of anything, no partner."""
    storybook = _db_storybook()
    version_row = _db_version({"id": "x"})
    monkeypatch.setattr(
        leaf_diversity_mod, "load_family_history", AsyncMock(return_value=[])
    )
    blob_mock = AsyncMock()
    monkeypatch.setattr(leaf_diversity_mod, "load_version_blob", blob_mock)

    findings = await run_leaf_diversity_check(
        session=MagicMock(), storybook=storybook, version_row=version_row
    )

    assert findings == []
    blob_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_atg_excludes_current_storybook_from_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The self-exclusion filter is load-bearing (supervisor sign-off section
    10): without it, the just-persisted draft (visible to the same-transaction
    history query) selects ITSELF as its own comparison partner and would FAIL
    at distance ~0 on every second fill. History containing only an entry for
    the current storybook's own id must behave exactly like empty history.
    """
    storybook = _db_storybook(story_id="s2")
    version_row = _db_version({"id": "x"}, story_id="s2", version=2)
    self_entry = _history_entry(storybook_id="s2", version=1)
    monkeypatch.setattr(
        leaf_diversity_mod, "load_family_history", AsyncMock(return_value=[self_entry])
    )
    blob_mock = AsyncMock()
    monkeypatch.setattr(leaf_diversity_mod, "load_version_blob", blob_mock)

    findings = await run_leaf_diversity_check(
        session=MagicMock(), storybook=storybook, version_row=version_row
    )

    assert findings == []
    blob_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_same_slug_partner_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """History exists but nothing shares this fill's skeleton slug: first use
    of this particular tree for the family."""
    storybook = _db_storybook(story_id="s2")
    version_row = _db_version({"id": "x"}, story_id="s2")
    other_entry = _history_entry(storybook_id="s1", skeleton_slug="a-different-tree")
    monkeypatch.setattr(
        leaf_diversity_mod, "load_family_history", AsyncMock(return_value=[other_entry])
    )
    blob_mock = AsyncMock()
    monkeypatch.setattr(leaf_diversity_mod, "load_version_blob", blob_mock)

    findings = await run_leaf_diversity_check(
        session=MagicMock(), storybook=storybook, version_row=version_row
    )

    assert findings == []
    blob_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_partner_blob_missing_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A selected partner whose version row is gone (deleted content, or a
    stale HistoryEntry) is a no-op, not a crash."""
    storybook = _db_storybook(story_id="s2")
    version_row = _db_version({"id": "x"}, story_id="s2")
    partner_entry = _history_entry(storybook_id="s1")
    monkeypatch.setattr(
        leaf_diversity_mod,
        "load_family_history",
        AsyncMock(return_value=[partner_entry]),
    )
    monkeypatch.setattr(
        leaf_diversity_mod, "load_version_blob", AsyncMock(return_value=None)
    )

    findings = await run_leaf_diversity_check(
        session=MagicMock(), storybook=storybook, version_row=version_row
    )

    assert findings == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_partner_blob_invalid_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partner blob that fails Storybook schema validation (malformed at
    rest) is a no-op, never an unhandled raise out of the pipeline."""
    storybook = _db_storybook(story_id="s2")
    current_raw = _load_blob(_CAVE_SPACE_PATH)
    version_row = _db_version(current_raw, story_id="s2")
    partner_entry = _history_entry(storybook_id="s1")
    monkeypatch.setattr(
        leaf_diversity_mod,
        "load_family_history",
        AsyncMock(return_value=[partner_entry]),
    )
    monkeypatch.setattr(
        leaf_diversity_mod,
        "load_version_blob",
        AsyncMock(return_value={"garbage": True}),
    )

    findings = await run_leaf_diversity_check(
        session=MagicMock(), storybook=storybook, version_row=version_row
    )

    assert findings == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_current_blob_invalid_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A CURRENT blob that fails Storybook schema validation is also a no-op:
    the pipeline's own except-ValidationError block already hard-blocks this
    case upstream in practice, but the guard must not raise either way."""
    storybook = _db_storybook(story_id="s2")
    version_row = _db_version({"garbage": True}, story_id="s2")
    partner_raw = _load_blob(_CAVE_SPACE_PATH)
    partner_entry = _history_entry(storybook_id="s1")
    monkeypatch.setattr(
        leaf_diversity_mod,
        "load_family_history",
        AsyncMock(return_value=[partner_entry]),
    )
    monkeypatch.setattr(
        leaf_diversity_mod, "load_version_blob", AsyncMock(return_value=partner_raw)
    )

    findings = await run_leaf_diversity_check(
        session=MagicMock(), storybook=storybook, version_row=version_row
    )

    assert findings == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_structure_drift_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partner whose graph shape differs (skeleton revised between fills)
    exits at the fingerprint pre-check rather than reaching
    anti_template_verdict's raise (design doc section 3.2, "pre-check vs
    catch-the-raise")."""
    storybook = _db_storybook(story_id="s2")
    current_raw = _load_blob(_CAVE_SPACE_PATH)
    version_row = _db_version(current_raw, story_id="s2")

    partner_raw = copy.deepcopy(current_raw)
    nodes = cast("list[dict[str, object]]", partner_raw["nodes"])
    start_node = next(n for n in nodes if n["id"] == "n_start")
    choices = cast("list[dict[str, object]]", start_node["choices"])
    # Retarget one choice to an existing node id: schema-valid, but the graph
    # shape (and so the structure fingerprint) now differs from `current`.
    choices[0]["target"] = choices[1]["target"]

    partner_entry = _history_entry(storybook_id="s1")
    monkeypatch.setattr(
        leaf_diversity_mod,
        "load_family_history",
        AsyncMock(return_value=[partner_entry]),
    )
    monkeypatch.setattr(
        leaf_diversity_mod, "load_version_blob", AsyncMock(return_value=partner_raw)
    )

    findings = await run_leaf_diversity_check(
        session=MagicMock(), storybook=storybook, version_row=version_row
    )

    assert findings == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fail_pair_produces_flags_and_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuine same-tree noun-swap FAIL pair (panel.json's cave-space vs
    cave-space-swap) produces per-node FLAGs plus one ADVISORY summary, with
    the partner id/version threaded into the messages."""
    current_raw, fail_partner_raw = _cave_space_fail_pair()
    storybook = _db_storybook(story_id="s2")
    version_row = _db_version(current_raw, story_id="s2")
    partner_entry = _history_entry(storybook_id="s1", version=3)
    monkeypatch.setattr(
        leaf_diversity_mod,
        "load_family_history",
        AsyncMock(return_value=[partner_entry]),
    )
    monkeypatch.setattr(
        leaf_diversity_mod,
        "load_version_blob",
        AsyncMock(return_value=fail_partner_raw),
    )

    findings = await run_leaf_diversity_check(
        session=MagicMock(), storybook=storybook, version_row=version_row
    )

    flags = [f for f in findings if f.verdict is Verdict.FLAG]
    advisories = [f for f in findings if f.verdict is Verdict.ADVISORY]
    assert len(flags) > 0
    assert len(advisories) == 1
    assert "storybook s1 v3" in advisories[0].message
    for finding in flags:
        assert finding.category == "leaf_diversity"
        assert finding.node_id is not None
