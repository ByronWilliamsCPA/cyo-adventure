"""Unit tests for diversity.panel: manifest, runner, baseline compare (WS-0 Phase 2).

Includes the harness acceptance tests over the committed panel/baseline, the
doctored-baseline regression-rule tests (one per rule R1-R6), and the
subprocess-free harness smoke test that drives ``scripts.run_diversity_eval
.main`` directly.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.diversity.panel import (
    compare_to_baseline,
    load_panel,
    make_noun_swap_variant,
    run_panel,
)
from cyo_adventure.diversity.report import AntiTemplateVerdict
from cyo_adventure.diversity.structure import structure_fingerprint
from cyo_adventure.generation.provider import MockProvider
from cyo_adventure.storybook.models import Storybook
from scripts.run_diversity_eval import _judge_pair, _scored_pair, main

_PANEL_PATH = Path("tests/data/diversity_panel/panel.json")
_BASELINE_PATH = Path("tests/data/diversity_panel/baseline.json")
_REPO_ROOT = Path()


def _load_baseline() -> dict[str, object]:
    return json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))


def _sub_dict(mapping: dict[str, object], key: str) -> dict[str, object]:
    """Return ``mapping[key]`` narrowed to ``dict[str, object]``, for doctoring tests."""
    return cast("dict[str, object]", mapping[key])


def _minimal_story(body: str) -> Storybook:
    """Build a one-node ending-only Storybook wrapping a single body string."""
    data = {
        "schema_version": "2.0",
        "id": "sk_swap_test",
        "version": 1,
        "title": "T",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"scheme": "flesch_kincaid", "target": 4.5},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "gauntlet",
        },
        "start_node": "n0",
        "nodes": [
            {
                "id": "n0",
                "body": body,
                "is_ending": True,
                "ending": {
                    "id": "e0",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "End",
                },
            }
        ],
    }
    return Storybook.model_validate(data)


@pytest.mark.unit
def test_load_panel_parses_committed_manifest() -> None:
    """The committed manifest validates, has unique ids, and every path exists."""
    manifest = load_panel(_PANEL_PATH)
    assert manifest.schema_version == 1
    ids = [fill.id for fill in manifest.fills] + [
        synthetic.id for synthetic in manifest.synthetic
    ]
    assert len(ids) == len(set(ids))
    for fill in manifest.fills:
        assert (_REPO_ROOT / fill.path).exists()


@pytest.mark.unit
def test_make_noun_swap_variant_preserves_fingerprint_and_word_boundaries() -> None:
    """Swap matches both cases at a word boundary and leaves substrings alone."""
    story = _minimal_story(
        "The station is quiet. Station Two holds stationary supplies."
    )
    variant = make_noun_swap_variant(story, {"station": "burrow"})
    assert (
        variant.nodes[0].body
        == "The burrow is quiet. Burrow Two holds stationary supplies."
    )
    assert structure_fingerprint(story) == structure_fingerprint(variant)


@pytest.mark.unit
def test_run_panel_committed_expectations_hold() -> None:
    """Every ATG pair lands its expected verdict; cross-tree distances are all > 0."""
    manifest = load_panel(_PANEL_PATH)
    result = run_panel(manifest, _REPO_ROOT)
    for pair in manifest.atg_pairs:
        key = "~".join(sorted((pair.a, pair.b)))
        assert result.atg_pairs[key].report.verdict == pair.expected_verdict
    for a_id, b_id in manifest.cross_tree_pairs:
        key = "~".join(sorted((a_id, b_id)))
        assert result.struct_pairs[key] > 0.0
    baseline = _load_baseline()
    assert result.rar_value == pytest.approx(baseline["rar_sequence"])


@pytest.mark.unit
def test_compare_to_baseline_clean_run_has_no_findings() -> None:
    """The committed panel against the committed baseline produces zero findings."""
    manifest = load_panel(_PANEL_PATH)
    result = run_panel(manifest, _REPO_ROOT)
    findings = compare_to_baseline(result, _load_baseline(), manifest)
    assert findings == []


@pytest.mark.unit
def test_compare_to_baseline_raised_median_distance_trips_r2() -> None:
    """An artificially raised baseline median_distance trips R2 (genuine-pair erosion)."""
    manifest = load_panel(_PANEL_PATH)
    result = run_panel(manifest, _REPO_ROOT)
    doctored = copy.deepcopy(_load_baseline())
    _sub_dict(_sub_dict(doctored, "atg_pairs"), "cave-sea~cave-space")[
        "median_distance"
    ] = 1.0
    findings = compare_to_baseline(result, doctored, manifest)
    assert any(f.rule == "R2" and f.subject == "cave-sea~cave-space" for f in findings)


@pytest.mark.unit
def test_compare_to_baseline_raised_distinct_2_trips_r3() -> None:
    """An artificially raised baseline distinct_2 trips R3 (lexical erosion)."""
    manifest = load_panel(_PANEL_PATH)
    result = run_panel(manifest, _REPO_ROOT)
    doctored = copy.deepcopy(_load_baseline())
    _sub_dict(_sub_dict(doctored, "fills"), "cave-sea")["distinct_2"] = 1.0
    findings = compare_to_baseline(result, doctored, manifest)
    assert any(f.rule == "R3" and f.subject == "cave-sea" for f in findings)


@pytest.mark.unit
def test_compare_to_baseline_edited_fingerprint_trips_r5() -> None:
    """An edited baseline fingerprint trips R5 (fixture edited / algorithm changed)."""
    manifest = load_panel(_PANEL_PATH)
    result = run_panel(manifest, _REPO_ROOT)
    doctored = copy.deepcopy(_load_baseline())
    _sub_dict(_sub_dict(doctored, "fills"), "cave-sea")["fingerprint"] = "0" * 64
    findings = compare_to_baseline(result, doctored, manifest)
    assert any(f.rule == "R5" and f.subject == "cave-sea" for f in findings)


@pytest.mark.unit
def test_compare_to_baseline_deleted_entry_trips_r6() -> None:
    """A deleted baseline fills entry trips R6 (panel integrity: no baseline entry)."""
    manifest = load_panel(_PANEL_PATH)
    result = run_panel(manifest, _REPO_ROOT)
    doctored = copy.deepcopy(_load_baseline())
    del _sub_dict(doctored, "fills")["cave-sea"]
    findings = compare_to_baseline(result, doctored, manifest)
    assert any(f.rule == "R6" and f.subject == "cave-sea" for f in findings)


@pytest.mark.unit
def test_compare_to_baseline_flipped_expected_verdict_trips_r1() -> None:
    """Flipping a manifest expected_verdict trips R1, independent of the baseline."""
    manifest = load_panel(_PANEL_PATH)
    result = run_panel(manifest, _REPO_ROOT)
    target = next(
        pair
        for pair in manifest.atg_pairs
        if pair.expected_verdict == AntiTemplateVerdict.PASS_
    )
    target.expected_verdict = AntiTemplateVerdict.FAIL
    findings = compare_to_baseline(result, _load_baseline(), manifest)
    assert any(f.rule == "R1" for f in findings)


@pytest.mark.unit
def test_compare_to_baseline_flipped_expected_similar_trips_r4() -> None:
    """Flipping a manifest expected_similar trips R4, independent of the baseline."""
    manifest = load_panel(_PANEL_PATH)
    result = run_panel(manifest, _REPO_ROOT)
    manifest.brief_pairs[0].expected_similar = not manifest.brief_pairs[
        0
    ].expected_similar
    findings = compare_to_baseline(result, _load_baseline(), manifest)
    assert any(f.rule == "R4" for f in findings)


@pytest.mark.unit
def test_main_check_returns_zero_on_committed_tree() -> None:
    """``main(["--check"])`` exits 0 against the committed panel and baseline."""
    assert main(["--check"]) == 0


@pytest.mark.unit
def test_main_check_with_doctored_baseline_returns_one(tmp_path: Path) -> None:
    """``main`` exits 1 against a doctored baseline path override."""
    doctored = copy.deepcopy(_load_baseline())
    _sub_dict(_sub_dict(doctored, "atg_pairs"), "cave-sea~cave-space")[
        "median_distance"
    ] = 1.0
    doctored_path = tmp_path / "baseline.json"
    doctored_path.write_text(json.dumps(doctored), encoding="utf-8")
    assert main(["--check", "--baseline", str(doctored_path)]) == 1


@pytest.mark.unit
def test_main_update_baseline_writes_byte_stable_file(tmp_path: Path) -> None:
    """Two ``--update-baseline`` runs with no code change write identical bytes."""
    out_path = tmp_path / "baseline.json"
    assert main(["--update-baseline", "--baseline", str(out_path)]) == 0
    first_bytes = out_path.read_bytes()
    assert main(["--update-baseline", "--baseline", str(out_path)]) == 0
    assert out_path.read_bytes() == first_bytes


@pytest.mark.unit
def test_main_check_and_update_baseline_mutually_exclusive_returns_two() -> None:
    """``--check`` and ``--update-baseline`` together is an argparse usage error."""
    assert main(["--check", "--update-baseline"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_judge_pair_parses_score_from_mock_provider() -> None:
    """``_judge_pair`` parses a well-formed ``SCORE: <n>`` reply."""
    provider = MockProvider(responses=["SCORE: 8\nVery similar in tone and stakes."])
    score = await _judge_pair(provider, "story a text", "story b text", "8-11")
    assert score == 8


@pytest.mark.unit
@pytest.mark.asyncio
async def test_judge_pair_unparseable_response_yields_none_without_raising() -> None:
    """``_judge_pair`` returns None (never raises) for an unparseable reply."""
    provider = MockProvider(responses=["I decline to assign a numeric score."])
    score = await _judge_pair(provider, "story a text", "story b text", "8-11")
    assert score is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scored_pair_cache_round_trip_hits_cache_on_second_call() -> None:
    """A second ``_scored_pair`` call for the same pair hits the cache, not the provider."""
    provider = MockProvider(responses=["SCORE: 5\nSomewhat similar."])
    cache: dict[str, object] = {}
    first = await _scored_pair(cache, provider, "story a text", "story b text", "8-11")
    second = await _scored_pair(cache, provider, "story a text", "story b text", "8-11")
    assert first == 5
    assert second == 5
    assert len(provider.calls) == 1
