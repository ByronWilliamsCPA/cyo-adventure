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
    _parse_args,  # pyright: ignore[reportPrivateUsage]
    _partition_stage1,  # pyright: ignore[reportPrivateUsage]
    _run_stage1_sweep_band,  # pyright: ignore[reportPrivateUsage]
    _sweep_rows,  # pyright: ignore[reportPrivateUsage]
    _sweep_to_json,  # pyright: ignore[reportPrivateUsage]
    classify_item,
    estimate_call_counts,
    run_sweep,
)

if TYPE_CHECKING:
    from cyo_adventure.moderation.review_provider import ReviewProvider


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
        by_item, structural_count = await _run_stage1_sweep_band(
            "8-11", band_items, provider, batch_size=4
        )
        assert len(provider.calls) == 1  # one call for both items, not two
        assert by_item == {"A": ["pass"], "B": ["flag"]}
        assert structural_count == 0

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
        by_item, structural_count = await _run_stage1_sweep_band(
            "8-11", band_items, provider, batch_size=1
        )
        assert len(provider.calls) == 2
        assert by_item == {"A": ["pass"], "B": ["flag"]}
        assert structural_count == 0

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
        by_item, structural_count = await _run_stage1_sweep_band(
            "8-11", band_items, provider, batch_size=2
        )
        assert structural_count == 1
        assert by_item == {"C": ["flag"]}  # fail-safe FLAG, not the real verdict

        # Feed the observed verdicts through the same scoring path run_sweep
        # uses, to show the concrete recall consequence: FLAG (rank 2) never
        # satisfies an expected "block" (rank 3), so the item is a miss.
        outcome = classify_item(band_items[0], by_item["C"])
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
        sizes = payload["sizes"]
        assert isinstance(sizes, list)
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
                "docs/planning/safety/adversarial-corpus.json",
            ],
        )
        sweep_cli_mock = Mock()
        monkeypatch.setattr(adversarial_harness, "_run_sweep_cli", sweep_cli_mock)

        def _fake_build_review_provider_for_cli(
            _name: str,
        ) -> tuple[ReviewProvider, adversarial_harness.ReviewProviderName]:
            return MockProvider(responses=["{}"] * 50), "mock"

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
                "docs/planning/safety/adversarial-corpus.json",
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
