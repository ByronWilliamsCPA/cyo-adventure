"""Unit tests for the Gate 3 batch-size recall-comparison sweep.

Covers the sweep-mode additions to ``scripts/adversarial_harness.py``: grouping
Stage-1 items by age band, batching them into one ``run_safety_stage`` call set
per band, per-size recall computation (including the batching failure mode
where an unparseable batch response collapses to a fail-safe structural
finding), delta computation against the batch_size=1 baseline, and that the
no-flag CLI invocation still takes the pre-existing single-run path.

Uses ``MockProvider`` (scripted responses, no network) exactly like
``tests/unit/test_moderation_stages.py``; nothing here talks to a live model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.provider import MockProvider
from scripts import adversarial_harness
from scripts.adversarial_harness import (
    ReviewProviderName,
    SweepReport,
    _catch_rate,  # pyright: ignore[reportPrivateUsage]
    _group_by_age_band,  # pyright: ignore[reportPrivateUsage]
    _has_misses,  # pyright: ignore[reportPrivateUsage]
    _load_items,  # pyright: ignore[reportPrivateUsage]
    _parse_args,  # pyright: ignore[reportPrivateUsage]
    _partition_stage1,  # pyright: ignore[reportPrivateUsage]
    _review_batch_size_bounds,  # pyright: ignore[reportPrivateUsage]
    _run_stage1_sweep_band,  # pyright: ignore[reportPrivateUsage]
    _sweep_regressions,  # pyright: ignore[reportPrivateUsage]
    _sweep_rows,  # pyright: ignore[reportPrivateUsage]
    _sweep_to_json,  # pyright: ignore[reportPrivateUsage]
    _validate_batch_sizes,  # pyright: ignore[reportPrivateUsage]
    _verdict_drift,  # pyright: ignore[reportPrivateUsage]
    _write_sweep_results,  # pyright: ignore[reportPrivateUsage]
    classify_item,
    estimate_call_counts,
    run_sweep,
)

if TYPE_CHECKING:
    from cyo_adventure.moderation.review_provider import ReviewProvider

# Anchored to this file, not to the process cwd: the harness resolves --corpus
# against the repo root, and a cwd-relative literal silently becomes a
# nonexistent path (exit 2, a load error) when pytest runs from anywhere but
# the repo root, which reads as a passing "it exited non-zero" assertion.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORPUS_ARG = str(
    _REPO_ROOT / "docs" / "planning" / "safety" / "adversarial-corpus.json"
)


def _stage1_item(
    item_id: str,
    *,
    taxonomy_class: str = "A",
    age_band: str = "8-11",
    expected_min_verdict: str = "flag",
    passage: str = "some passage text",
) -> dict[str, object]:
    """Build a minimal executable Stage-1 (single-node) corpus item."""
    return {
        "id": item_id,
        "taxonomy_class": taxonomy_class,
        "executable": True,
        "target_stage": 1,
        "age_band": age_band,
        "expected_min_verdict": expected_min_verdict,
        "passage": passage,
    }


class TestGroupByAgeBand:
    """Grouping corpus items by age band for one batched call per band."""

    def test_groups_items_by_age_band_preserving_order(self) -> None:
        items = [
            _stage1_item("x1", age_band="3-5"),
            _stage1_item("x2", age_band="8-11"),
            _stage1_item("x3", age_band="3-5"),
        ]
        groups = _group_by_age_band(items)
        assert list(groups) == ["3-5", "8-11"]
        assert [it["id"] for it in groups["3-5"]] == ["x1", "x3"]
        assert [it["id"] for it in groups["8-11"]] == ["x2"]


class TestPartitionStage1:
    """Only Stage-1/aggregate items are batchable by review_batch_size."""

    def test_splits_stage1_batchable_from_other_items(self) -> None:
        stage1_item: dict[str, object] = _stage1_item("A1")
        aggregate_item: dict[str, object] = {
            "id": "C1",
            "taxonomy_class": "C",
            "executable": True,
            "target_stage": "aggregate",
            "age_band": "8-11",
            "known_gap": True,
            "nodes": [{"id": "n1", "body": "a"}],
        }
        pii_item: dict[str, object] = {
            "id": "F1",
            "taxonomy_class": "F",
            "executable": True,
            "target": "pii_guard",
            "age_band": "5-8",
            "passage": "child data",
        }
        skipped_item: dict[str, object] = {
            "id": "D1",
            "taxonomy_class": "D",
            "executable": False,
            "target": "call_graph",
        }
        stage1, rest = _partition_stage1(
            [stage1_item, aggregate_item, pii_item, skipped_item]
        )
        assert [it["id"] for it in stage1] == ["A1", "C1"]
        assert [it["id"] for it in rest] == ["F1", "D1"]


class TestEstimateCallCounts:
    """The preflight call-count estimate, checked against manual chunk math."""

    def test_matches_manual_chunk_math_across_sizes(self) -> None:
        items = [
            _stage1_item("x1", age_band="5-8"),
            _stage1_item("x2", age_band="5-8"),
            {
                "id": "F1",
                "taxonomy_class": "F",
                "executable": True,
                "target": "pii_guard",
                "age_band": "5-8",
                "passage": "child data",
            },
        ]
        estimates = estimate_call_counts(items, [1, 4])
        # size 1: 1 (pii_guard) + ceil(2/1) = 3
        assert estimates[1] == 3
        # size 4: 1 (pii_guard) + ceil(2/4) = 2
        assert estimates[4] == 2

    def test_non_executable_items_never_counted(self) -> None:
        items = [
            _stage1_item("x1", age_band="5-8"),
            {
                "id": "D1",
                "taxonomy_class": "D",
                "executable": False,
                "target": "call_graph",
            },
        ]
        estimates = estimate_call_counts(items, [1])
        assert estimates[1] == 1


class TestRunStage1SweepBand:
    """The per-band batched Stage-1 probe: grouping, attribution, and collapse."""

    @pytest.mark.asyncio
    async def test_groups_multiple_items_into_one_batched_call(self) -> None:
        band_items = [
            _stage1_item("A", expected_min_verdict="pass", passage="calm text"),
            _stage1_item("B", expected_min_verdict="flag", passage="scary text"),
        ]
        provider = MockProvider(
            responses=[
                json.dumps(
                    [
                        {"verdict": "safe", "reason": "fine", "node_id": "i0n0"},
                        {"verdict": "flag", "reason": "scary", "node_id": "i1n0"},
                    ]
                )
            ]
        )
        result = await _run_stage1_sweep_band(
            "8-11", band_items, provider, batch_size=4
        )
        assert len(provider.calls) == 1  # one call for both items, not two
        assert result.by_item == {"A": ["pass"], "B": ["flag"]}
        assert result.structural_count == 0
        # Requested 4, but the band only held 2 nodes, so a batch of 4 was
        # never exercised. The realized sizes are what the artifact reports.
        assert result.realized_chunk_sizes == (2,)
        assert len(result.realized_chunk_sizes) == len(provider.calls)

    @pytest.mark.asyncio
    async def test_batch_size_one_issues_one_call_per_node(self) -> None:
        band_items = [
            _stage1_item("A", passage="calm text"),
            _stage1_item("B", passage="scary text"),
        ]
        provider = MockProvider(
            responses=[
                json.dumps({"verdict": "safe", "reason": "fine"}),
                json.dumps({"verdict": "flag", "reason": "scary"}),
            ]
        )
        result = await _run_stage1_sweep_band(
            "8-11", band_items, provider, batch_size=1
        )
        assert len(provider.calls) == 2
        assert result.by_item == {"A": ["pass"], "B": ["flag"]}
        assert result.structural_count == 0
        assert result.realized_chunk_sizes == (1, 1)
        assert len(result.realized_chunk_sizes) == len(provider.calls)

    @pytest.mark.asyncio
    async def test_unparseable_batch_response_collapses_structurally_and_degrades_recall(
        self,
    ) -> None:
        """An unparseable batch response is the batching failure mode this
        sweep exists to measure: it collapses to a fail-safe FLAG for every
        node in the batch, which is *below* a "block" expectation, so a
        bright-line item is scored a miss instead of a genuine judgment."""
        band_items = [
            _stage1_item(
                "C",
                taxonomy_class="A",
                expected_min_verdict="block",
                passage="bright-line unsafe text",
            ),
        ]
        provider = MockProvider(responses=["not a json array"])
        result = await _run_stage1_sweep_band(
            "8-11", band_items, provider, batch_size=2
        )
        assert result.structural_count == 1
        # fail-safe FLAG, not the real verdict
        assert result.by_item == {"C": ["flag"]}

        # Feed the observed verdicts through the same scoring path run_sweep
        # uses, to show the concrete recall consequence: FLAG (rank 2) never
        # satisfies an expected "block" (rank 3), so the item is a miss.
        outcome = classify_item(band_items[0], result.by_item["C"])
        assert outcome.status == "missed"

    @pytest.mark.asyncio
    async def test_pii_context_from_band_items_is_forwarded_to_guard(self) -> None:
        """A Stage-1 item that (hypothetically) carries pii_context still gets
        guarded in the batched sweep path, matching the single-item probe's
        topology (_observe_item always routes through PiiGuardedProvider)."""
        item = _stage1_item("A", passage="my friend Aabria said hello")
        item["pii_context"] = {"child_names": ["Aabria"], "birthdates": []}
        provider = MockProvider(responses=[])
        with pytest.raises(ValidationError):
            _ = await _run_stage1_sweep_band("8-11", [item], provider, batch_size=1)

    @pytest.mark.asyncio
    async def test_guard_covers_the_band_wide_union_not_just_the_owning_item(
        self,
    ) -> None:
        """Batching merges two items into one prompt, so the guard must cover
        both items' child names. A guard scoped to only the item that declared
        the name would let the OTHER item's merged text egress that name."""
        carrier = _stage1_item("A", passage="my friend Aabria said hello")
        declarer = _stage1_item("B", passage="nothing identifying here")
        # B declares the name; A is the item whose text actually contains it.
        declarer["pii_context"] = {"child_names": ["Aabria"], "birthdates": []}
        provider = MockProvider(responses=[])
        with pytest.raises(ValidationError):
            _ = await _run_stage1_sweep_band(
                "8-11", [carrier, declarer], provider, batch_size=8
            )
        assert not provider.calls  # raised BEFORE egress, not after


class TestRunSweep:
    """End-to-end sweep: per-size reports, call counts, and delta vs baseline."""

    @pytest.mark.asyncio
    async def test_computes_delta_vs_baseline_across_sizes(self) -> None:
        item_x = _stage1_item(
            "X", taxonomy_class="A", expected_min_verdict="flag", passage="text-x"
        )
        item_y = _stage1_item(
            "Y", taxonomy_class="A", expected_min_verdict="flag", passage="text-y"
        )
        # Sequential responses: size=1 issues two single-node calls (both catch
        # the flag), size=2 issues one batched call where Y is now misjudged as
        # safe, simulating batching degrading recall for that item.
        provider = MockProvider(
            responses=[
                json.dumps({"verdict": "flag", "reason": "r1"}),
                json.dumps({"verdict": "flag", "reason": "r2"}),
                json.dumps(
                    [
                        {"verdict": "flag", "reason": "r1", "node_id": "i0n0"},
                        {"verdict": "safe", "reason": "r2", "node_id": "i1n0"},
                    ]
                ),
            ]
        )
        review_provider_name: ReviewProviderName = "openrouter"
        sweep: SweepReport = await run_sweep(
            [item_x, item_y],
            provider,
            review_provider_name=review_provider_name,
            batch_sizes=[1, 2],
        )

        assert sweep.baseline.batch_size == 1
        size1, size2 = sweep.sizes
        assert size1.call_count == 2
        assert size2.call_count == 1
        assert size1.report.per_class["A"] == {"caught": 2}
        assert size2.report.per_class["A"] == {"caught": 1, "missed": 1}

        rows = {(row["class"], row["batch_size"]): row for row in _sweep_rows(sweep)}
        assert rows[("A", 1)]["catch_rate"] == pytest.approx(1.0)
        assert rows[("A", 1)]["delta_vs_baseline"] == pytest.approx(0.0)
        assert rows[("A", 2)]["catch_rate"] == pytest.approx(0.5)
        assert rows[("A", 2)]["delta_vs_baseline"] == pytest.approx(-0.5)
        assert rows[("overall", 2)]["delta_vs_baseline"] == pytest.approx(-0.5)

    @pytest.mark.asyncio
    async def test_baseline_is_first_size_when_one_not_requested(self) -> None:
        item_x = _stage1_item("X", expected_min_verdict="flag", passage="text-x")
        provider = MockProvider(
            responses=[
                json.dumps({"verdict": "flag", "reason": "r"}),
                json.dumps([{"verdict": "flag", "reason": "r", "node_id": "i0n0"}]),
            ]
        )
        review_provider_name: ReviewProviderName = "openrouter"
        sweep = await run_sweep(
            [item_x],
            provider,
            review_provider_name=review_provider_name,
            batch_sizes=[4, 8],
        )
        assert sweep.baseline.batch_size == 4

    @pytest.mark.asyncio
    async def test_sweep_json_payload_carries_baseline_and_rows(self) -> None:
        item_x = _stage1_item("X", expected_min_verdict="flag", passage="text-x")
        provider = MockProvider(
            responses=[json.dumps({"verdict": "flag", "reason": "r"})]
        )
        review_provider_name: ReviewProviderName = "openrouter"
        sweep = await run_sweep(
            [item_x],
            provider,
            review_provider_name=review_provider_name,
            batch_sizes=[1],
        )
        payload = _sweep_to_json(sweep)
        assert payload["baseline_batch_size"] == 1
        # cast, not isinstance: isinstance(x, list) narrows the container but
        # not its element type, so indexing stays partially-unknown in strict
        # mode. _sweep_to_json's return is dict[str, object] by declaration.
        sizes = cast("list[dict[str, object]]", payload["sizes"])
        assert sizes[0]["batch_size"] == 1
        assert sizes[0]["call_count"] == 1


class TestCatchRateHelperReuse:
    """The sweep reuses the existing catch-rate helper; a quick sanity pin."""

    def test_catch_rate_matches_existing_semantics(self) -> None:
        assert _catch_rate({"caught": 1, "missed": 1}) == pytest.approx(0.5)


class TestParseArgsBatchSizeFlag:
    """--batch-size is opt-in and repeatable; absence keeps classic mode."""

    def test_default_batch_sizes_is_none_classic_mode_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            ["adversarial_harness.py", "--corpus", "docs/planning/safety/x.json"],
        )
        args = _parse_args()
        assert cast("list[int] | None", args.batch_sizes) is None

    def test_repeated_batch_size_flag_collects_list_in_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "adversarial_harness.py",
                "--corpus",
                "docs/planning/safety/x.json",
                "--batch-size",
                "1",
                "--batch-size",
                "4",
                "--batch-size",
                "8",
            ],
        )
        args = _parse_args()
        assert cast("list[int] | None", args.batch_sizes) == [1, 4, 8]


class TestMainRoutesToSweepOnlyWhenBatchSizeGiven:
    """main() must only take the sweep path when --batch-size was given."""

    def test_no_batch_size_flag_uses_classic_single_run_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "adversarial_harness.py",
                "--corpus",
                _CORPUS_ARG,
            ],
        )
        sweep_cli_mock = Mock()
        monkeypatch.setattr(adversarial_harness, "_run_sweep_cli", sweep_cli_mock)

        def _fake_build_review_provider_for_cli(
            _name: str,
        ) -> tuple[
            ReviewProvider, adversarial_harness.ReviewProviderName, int, str | None
        ]:
            # The mock backend has no configurable model, so the resolved review
            # model is None and endpoint_pin_for is never consulted.
            return MockProvider(responses=["{}"] * 50), "mock", 8, None

        monkeypatch.setattr(
            adversarial_harness,
            "_build_review_provider_for_cli",
            _fake_build_review_provider_for_cli,
        )
        with pytest.raises(SystemExit) as exc:
            adversarial_harness.main()
        sweep_cli_mock.assert_not_called()
        assert exc.value.code == 3  # mock run: non-evidence, unchanged semantics

    def test_batch_size_flag_routes_to_sweep_cli_not_classic_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "adversarial_harness.py",
                "--corpus",
                _CORPUS_ARG,
                "--batch-size",
                "1",
            ],
        )
        run_corpus_mock = Mock()
        sweep_cli_mock = Mock()
        monkeypatch.setattr(adversarial_harness, "run_corpus", run_corpus_mock)
        monkeypatch.setattr(adversarial_harness, "_run_sweep_cli", sweep_cli_mock)
        adversarial_harness.main()
        sweep_cli_mock.assert_called_once()
        run_corpus_mock.assert_not_called()


class TestLoadItemsIdValidation:
    """Corpus ids are the sweep's stitching key, so they are validated on load."""

    def test_blank_id_is_rejected(self, tmp_path: Path) -> None:
        corpus = tmp_path / "c.json"
        _ = corpus.write_text(
            json.dumps({"items": [_stage1_item("A"), {"taxonomy_class": "B"}]}),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as exc:
            _ = _load_items(corpus)
        assert exc.value.code == 2

    def test_duplicate_id_is_rejected(self, tmp_path: Path) -> None:
        corpus = tmp_path / "c.json"
        _ = corpus.write_text(
            json.dumps({"items": [_stage1_item("A"), _stage1_item("A")]}),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as exc:
            _ = _load_items(corpus)
        assert exc.value.code == 2

    def test_valid_ids_load_cleanly(self, tmp_path: Path) -> None:
        corpus = tmp_path / "c.json"
        _ = corpus.write_text(
            json.dumps({"items": [_stage1_item("A"), _stage1_item("B")]}),
            encoding="utf-8",
        )
        assert [it["id"] for it in _load_items(corpus)] == ["A", "B"]


class TestSweepRegressionGate:
    """The gate compares sizes to the baseline; it does not re-report absolute
    misses, which a permanently-missed corpus item would pin to 'fail'.

    Each case sweeps a ONE-item corpus, so both sizes send single-node chunks:
    ``run_safety_stage`` takes its single-node path whenever a chunk holds one
    node, whatever batch size was requested (stages.py, ``len(batch) == 1``).
    The scripted responses are therefore objects, not arrays, and the verdict
    difference between the two runs comes from the response script rather than
    from the chunking. That keeps these tests about the comparison logic.
    """

    @pytest.mark.asyncio
    async def _sweep_from(
        self, items: list[dict[str, object]], responses: list[str]
    ) -> SweepReport:
        provider = MockProvider(responses=responses)
        name: ReviewProviderName = "openrouter"
        return await run_sweep(
            items, provider, review_provider_name=name, batch_sizes=[1, 2]
        )

    @pytest.mark.asyncio
    async def test_permanent_baseline_miss_alone_is_not_a_regression(self) -> None:
        """An item missed at EVERY size is a pre-existing recall gap. Gating on
        it would saturate the gate: it could never report 'no batching
        regression' no matter how batching behaved."""
        item = _stage1_item("E", expected_min_verdict="block", passage="t")
        sweep = await self._sweep_from(
            [item],
            [
                json.dumps({"verdict": "safe", "reason": "r"}),
                json.dumps({"verdict": "safe", "reason": "r"}),
            ],
        )
        assert _has_misses(sweep.baseline.report)  # the gap is real...
        assert _sweep_regressions(sweep) == []  # ...and is not a regression

    @pytest.mark.asyncio
    async def test_caught_at_baseline_missed_at_size_is_a_regression(self) -> None:
        item = _stage1_item("X", expected_min_verdict="flag", passage="t")
        sweep = await self._sweep_from(
            [item],
            [
                json.dumps({"verdict": "flag", "reason": "r"}),
                json.dumps({"verdict": "safe", "reason": "r"}),
            ],
        )
        regressions = _sweep_regressions(sweep)
        kinds = {r.kind for r in regressions}
        assert "status" in kinds
        assert all(r.batch_size == 2 for r in regressions)

    @pytest.mark.asyncio
    async def test_severity_downgrade_above_expected_min_is_still_a_regression(
        self,
    ) -> None:
        """block -> flag against expected_min='flag' scores caught both times
        and a catch-rate delta of 0.0. The binary scoring cannot see it; the
        severity comparison can."""
        item = _stage1_item("X", expected_min_verdict="flag", passage="t")
        sweep = await self._sweep_from(
            [item],
            [
                json.dumps({"verdict": "block", "reason": "r"}),
                json.dumps({"verdict": "flag", "reason": "r"}),
            ],
        )
        assert not _has_misses(sweep.sizes[1].report)  # invisible to status scoring
        rows = {(r["class"], r["batch_size"]): r for r in _sweep_rows(sweep)}
        assert rows[("A", 2)]["delta_vs_baseline"] == pytest.approx(0.0)
        assert [r.kind for r in _sweep_regressions(sweep)] == ["severity"]

    @pytest.mark.asyncio
    async def test_hardening_is_reported_as_drift_but_not_as_a_regression(self) -> None:
        item = _stage1_item("X", expected_min_verdict="flag", passage="t")
        sweep = await self._sweep_from(
            [item],
            [
                json.dumps({"verdict": "flag", "reason": "r"}),
                json.dumps({"verdict": "block", "reason": "r"}),
            ],
        )
        assert _sweep_regressions(sweep) == []
        drift = _verdict_drift(sweep)
        assert len(drift) == 1
        assert drift[0]["baseline_observed"] == ["flag"]
        assert drift[0]["observed"] == ["block"]


class TestBatchSizeValidation:
    """--batch-size bounds come from the Settings field, and repeats are errors."""

    def test_bounds_match_the_settings_field_constraints(self) -> None:
        assert _review_batch_size_bounds() == (1, 50)

    @pytest.mark.parametrize("size", [0, -1, 51])
    def test_out_of_range_size_exits_2(self, size: int) -> None:
        with pytest.raises(SystemExit) as exc:
            _validate_batch_sizes([1, size])
        assert exc.value.code == 2

    def test_repeated_size_exits_2_rather_than_paying_for_a_duplicate_run(
        self,
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            _validate_batch_sizes([1, 4, 4])
        assert exc.value.code == 2

    def test_distinct_in_range_sizes_pass(self) -> None:
        _validate_batch_sizes([1, 4, 8])


class TestWriteSweepResults:
    """A write failure after a paid sweep must be a loud exit, not a traceback."""

    @pytest.mark.asyncio
    async def test_unwritable_path_exits_2(self, tmp_path: Path) -> None:
        provider = MockProvider(responses=[json.dumps({"verdict": "flag", "r": "r"})])
        name: ReviewProviderName = "openrouter"
        sweep = await run_sweep(
            [_stage1_item("X")], provider, review_provider_name=name, batch_sizes=[1]
        )
        blocker = tmp_path / "blocker"
        _ = blocker.write_text("not a directory", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            _write_sweep_results(blocker / "sub" / "out.json", sweep)
        assert exc.value.code == 2

    @pytest.mark.asyncio
    async def test_payload_records_realized_chunk_sizes(self, tmp_path: Path) -> None:
        provider = MockProvider(
            responses=[
                json.dumps(
                    [
                        {"verdict": "flag", "reason": "r", "node_id": "i0n0"},
                        {"verdict": "flag", "reason": "r", "node_id": "i1n0"},
                    ]
                )
            ]
        )
        name: ReviewProviderName = "openrouter"
        sweep = await run_sweep(
            [_stage1_item("X"), _stage1_item("Y")],
            provider,
            review_provider_name=name,
            batch_sizes=[8],
        )
        out = tmp_path / "out.json"
        _write_sweep_results(out, sweep)
        payload = cast("dict[str, object]", json.loads(out.read_text(encoding="utf-8")))
        sizes = cast("list[dict[str, object]]", payload["sizes"])
        # Requested 8, realized 2: the artifact must not imply 8 was measured.
        assert sizes[0]["batch_size"] == 8
        assert sizes[0]["max_realized_chunk_size"] == 2
