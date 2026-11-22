"""Unit tests for the plan reviewer's validation harness and figures (WP-3.7).

Covers ``cyo_adventure.storyplan.review_figures`` (counts with intervals, the
residual rule, G3b, the held-out rule, the cost model) and the two scripts
``scripts/validate_plan_reviewer.py`` and ``scripts/review_story_plan.py``
end to end on hand-made fixtures with a scripted provider. Nothing here calls a
model or the network.

scripts/ is not an importable package, so the scripts are loaded from their file
paths, as tests/unit/test_synthetic_plans.py does.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import pytest

from cyo_adventure.generation.usage import Completion, TokenUsage
from cyo_adventure.storyplan.checks import WITNESSES, base_example
from cyo_adventure.storyplan.review import (
    PlanReview,
    ReviewFinding,
    parse_validated_pairing,
)
from cyo_adventure.storyplan.review_figures import (
    Proportion,
    ScoredPlan,
    check_held_out_allowed,
    compute_figures,
    evaluate_g3b,
    project_costs,
    residual_explained,
    wilson_interval,
)

if TYPE_CHECKING:
    import argparse
    from types import ModuleType

_REPO = Path(__file__).resolve().parents[2]
EM_DASH = chr(0x2014)
WRITER = "anthropic/claude-sonnet-5.5"
REVIEWER = "google/gemini-3.1-pro-preview"

JsonObj = dict[str, object]


def _load(name: str) -> ModuleType:
    path = _REPO / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def harness() -> ModuleType:
    return _load("validate_plan_reviewer")


@pytest.fixture(scope="module")
def review_cli() -> ModuleType:
    return _load("review_story_plan")


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _review(
    verdict: Literal["pass", "reject", "unsure"],
    *,
    checker_caught: bool = False,
    runs: tuple[Literal["pass", "reject", "unsure"], ...] = ("pass", "pass"),
    findings: tuple[ReviewFinding, ...] = (),
    ran: bool = True,
) -> PlanReview:
    return PlanReview(
        verdict=verdict,
        confidence=None,
        findings=findings,
        reasons=(),
        run_verdicts=runs if ran else (),
        checker_caught=checker_caught,
        reviewer_ran=ran,
    )


def _scored(
    plan_id: str,
    source: Literal["real", "synthetic", "baseline"],
    expected: Literal["reject", "pass"],
    review: PlanReview,
    **kwargs: object,
) -> ScoredPlan:
    return ScoredPlan(
        id=plan_id,
        source=source,
        half="held_out",
        unit=cast("str", kwargs.pop("unit", "book-a")),
        expected=expected,
        review=review,
        **cast("dict[str, object]", kwargs),  # pyright: ignore[reportArgumentType]
    )


class TestStatistics:
    """Counts with Wilson intervals; the cost model."""

    def test_the_interval_of_no_trials_is_everything(self) -> None:
        assert wilson_interval(0, 0) == (0.0, 1.0)

    def test_the_interval_brackets_the_rate_and_stays_in_range(self) -> None:
        low, high = wilson_interval(9, 10)
        assert 0.0 <= low < 0.9 < high <= 1.0
        assert low == pytest.approx(0.5958, abs=1e-3)
        low_all, high_all = wilson_interval(10, 10)
        assert high_all == pytest.approx(1.0)
        assert low_all == pytest.approx(0.7225, abs=1e-3)

    def test_a_proportion_renders_counts_rate_and_interval(self) -> None:
        text = str(Proportion(3, 4))
        assert text.startswith("3/4 = 0.75 (95% ")
        assert str(Proportion(0, 0)) == "0/0 (no plans)"
        assert Proportion(3, 4).to_dict()["rate"] == 0.75
        assert Proportion(0, 0).rate is None

    def test_the_cost_model_is_arithmetic_on_prompt_size(self) -> None:
        out = project_costs(
            [2_100_000, 1_050_000],
            runs=2,
            chars_per_token=2.1,
            output_tokens_per_call=10_000,
            input_usd_per_mtok=3.0,
            output_usd_per_mtok=15.0,
        )
        # (1,000,000 + 500,000 input tokens) x 2 runs; 4 calls x 10,000 output tokens.
        assert out["input_tokens"] == 3_000_000
        assert out["output_tokens"] == 40_000
        assert out["calls"] == 4
        assert out["usd"] == pytest.approx(9.0 + 0.6)


class TestResidualRule:
    """A finding at a known residual is a true positive, a flag elsewhere is not."""

    RESIDUALS = frozenset({"n_a", "c_b"})

    def _flag(
        self, *findings: ReviewFinding, verdict: Literal["reject", "unsure"] = "reject"
    ) -> PlanReview:
        return _review(verdict, findings=findings)

    def test_a_finding_only_at_a_residual_is_explained(self) -> None:
        review = self._flag(ReviewFinding("n_a", "other", "should-fix", "r"))
        assert residual_explained(review, self.RESIDUALS)

    def test_a_choice_residual_counts_too(self) -> None:
        assert residual_explained(
            self._flag(ReviewFinding("c_b", "other", "blocker", "r")), self.RESIDUALS
        )

    def test_a_blocking_finding_elsewhere_makes_it_a_false_flag(self) -> None:
        review = self._flag(
            ReviewFinding("n_a", "other", "should-fix", "r"),
            ReviewFinding("n_z", "other", "should-fix", "r"),
        )
        assert not residual_explained(review, self.RESIDUALS)

    def test_a_minor_elsewhere_does_not_undo_the_residual(self) -> None:
        review = self._flag(
            ReviewFinding("n_a", "other", "should-fix", "r"),
            ReviewFinding("n_z", "other", "minor", "r"),
        )
        assert residual_explained(review, self.RESIDUALS)

    def test_no_findings_no_residual_or_a_pass_is_not_explained(self) -> None:
        assert not residual_explained(self._flag(), self.RESIDUALS)
        assert not residual_explained(
            self._flag(ReviewFinding("n_z", "other", "minor", "r")), self.RESIDUALS
        )
        assert not residual_explained(
            self._flag(ReviewFinding("n_a", "other", "minor", "r")), frozenset()
        )
        assert not residual_explained(_review("pass"), self.RESIDUALS)


class TestFigures:
    """Every figure, counted from scored plans, never merged."""

    def _items(self) -> list[ScoredPlan]:
        caught = _review("reject", checker_caught=True, ran=False)
        flag = _review("reject")
        miss = _review("pass")
        resid = _review(
            "reject", findings=(ReviewFinding("n_fork", "other", "should-fix", "r"),)
        )
        return [
            _scored(
                "r1", "real", "reject", caught, severity="blocker", blockers=("KD-1",)
            ),
            _scored("r2", "real", "reject", flag, severity="should-fix"),
            _scored(
                "r3",
                "real",
                "reject",
                miss,
                severity="blocker",
                blockers=("KD-2", "KD-1"),
            ),
            _scored(
                "sa", "synthetic", "reject", caught, family="A", defect_class="SP-7"
            ),
            _scored("sb1", "synthetic", "reject", flag, family="B", defect_class="B1"),
            _scored("sb2", "synthetic", "reject", miss, family="B", defect_class="B2"),
            _scored("b1", "baseline", "pass", miss, unit="book-x", needed_repair=False),
            _scored("b2", "baseline", "pass", flag, unit="book-x", needed_repair=True),
            _scored(
                "b3",
                "baseline",
                "pass",
                resid,
                unit="book-y",
                needed_repair=False,
                residual_entries=frozenset({"n_fork"}),
            ),
            _scored(
                "b4",
                "baseline",
                "pass",
                _review("pass", runs=("pass", "unsure")),
                unit="book-y",
                needed_repair=False,
            ),
        ]

    def test_real_recall_splits_into_checker_caught_and_reviewer_decisive(self) -> None:
        f = compute_figures(self._items())
        assert (f.real_recall.k, f.real_recall.n) == (2, 3)
        assert (f.real_checker_caught.k, f.real_checker_caught.n) == (1, 3)
        assert (f.real_decisive.k, f.real_decisive.n) == (1, 2)
        assert {k: (v.k, v.n) for k, v in f.real_by_severity.items()} == {
            "blocker": (1, 2),
            "should-fix": (1, 1),
        }

    def test_every_blocker_entry_is_counted_per_plan_carrying_it(self) -> None:
        f = compute_figures(self._items())
        assert f.blocker_entries == {
            "KD-1": {"plans": 2, "flagged": 1},
            "KD-2": {"plans": 1, "flagged": 0},
        }
        assert not f.blockers_all_flagged

    def test_synthetic_recall_is_reported_by_family_and_class(self) -> None:
        f = compute_figures(self._items())
        assert (f.synthetic_a.k, f.synthetic_a.n) == (1, 1)
        assert (f.synthetic_b.k, f.synthetic_b.n) == (1, 2)
        assert {k: (v.k, v.n) for k, v in f.synthetic_b_by_class.items()} == {
            "B1": (1, 1),
            "B2": (0, 1),
        }

    def test_clean_flags_are_raw_and_residual_adjusted_and_per_book(self) -> None:
        f = compute_figures(self._items())
        assert (f.clean_raw.k, f.clean_raw.n) == (2, 4)
        assert (f.clean_false.k, f.clean_false.n) == (1, 4)
        assert f.clean_explained == 1
        assert f.clean_by_book == {
            "book-x": {"plans": 2, "flagged": 1, "false_flags": 1},
            "book-y": {"plans": 2, "flagged": 1, "false_flags": 0},
        }
        assert (f.clean_repaired.k, f.clean_repaired.n) == (1, 1)
        assert (f.clean_unrepaired.k, f.clean_unrepaired.n) == (0, 3)
        assert f.clean_books == 2

    def test_agreement_counts_plans_the_reviewer_ran_on(self) -> None:
        f = compute_figures(self._items())
        # r1, sa never ran a reviewer; b4's runs disagree; the other seven agree.
        assert (f.agreement.k, f.agreement.n) == (7, 8)

    def test_to_dict_is_json_ready(self) -> None:
        document = compute_figures(self._items(), checker_only_clean=2).to_dict()
        json.dumps(document)
        assert document["checker_only_clean_plans_rejected"] == 2


def _passing_items() -> list[ScoredPlan]:
    items = [
        _scored(
            f"r{i}",
            "real",
            "reject",
            _review("reject", checker_caught=True, ran=False),
            severity="blocker",
            blockers=(f"KD-{i}",),
        )
        for i in range(15)
    ]
    items += [
        _scored(
            f"b{i}",
            "baseline",
            "pass",
            _review("pass"),
            unit=f"book-{i % 5}",
            needed_repair=False,
        )
        for i in range(10)
    ]
    return items


class TestG3b:
    """The gate is judged on every D12 threshold and the minimum size."""

    def test_a_run_meeting_every_threshold_passes(self) -> None:
        result = evaluate_g3b(
            compute_figures(_passing_items()), half="held_out", live=True, complete=True
        )
        assert result.passed
        assert all(ok for _, ok, _ in result.checks)

    @pytest.mark.parametrize(
        ("half", "live", "complete", "failed"),
        [
            ("tuning", True, True, "held-out half"),
            ("held_out", False, True, "live reviewer"),
            ("held_out", True, False, "run complete"),
        ],
    )
    def test_context_conditions_each_fail_the_gate(
        self, half: str, live: bool, complete: bool, failed: str
    ) -> None:
        result = evaluate_g3b(
            compute_figures(_passing_items()), half=half, live=live, complete=complete
        )
        assert not result.passed
        assert [n for n, ok, _ in result.checks if not ok] == [failed]

    def test_too_few_defective_plans_fails(self) -> None:
        items = [i for i in _passing_items() if i.id != "r0"]
        result = evaluate_g3b(
            compute_figures(items), half="held_out", live=True, complete=True
        )
        assert not result.passed

    def test_clean_baselines_of_four_books_fail_the_amended_minimum(self) -> None:
        items = [i for i in _passing_items() if i.unit != "book-0"]
        result = evaluate_g3b(
            compute_figures(items), half="held_out", live=True, complete=True
        )
        failed = next(n for n, ok, _ in result.checks if not ok)
        assert failed.startswith("clean baselines cover")

    def test_recall_below_point_nine_fails(self) -> None:
        items = _passing_items()
        items[0] = _scored(
            "r0", "real", "reject", _review("pass"), severity="should-fix"
        )
        items[1] = _scored(
            "r1", "real", "reject", _review("pass"), severity="should-fix"
        )
        result = evaluate_g3b(
            compute_figures(items), half="held_out", live=True, complete=True
        )
        failed = [n for n, ok, _ in result.checks if not ok]
        assert any(n.startswith("defect recall") for n in failed)

    def test_a_missed_blocker_entry_fails_even_at_high_recall(self) -> None:
        items = _passing_items() + [
            _scored(
                f"extra{i}",
                "real",
                "reject",
                _review("reject", checker_caught=True, ran=False),
                severity="should-fix",
            )
            for i in range(20)
        ]
        items[0] = _scored(
            "r0",
            "real",
            "reject",
            _review("pass"),
            severity="blocker",
            blockers=("KD-0",),
        )
        result = evaluate_g3b(
            compute_figures(items), half="held_out", live=True, complete=True
        )
        failed = [n for n, ok, _ in result.checks if not ok]
        assert failed == ["every blocker entry flagged"]

    def test_a_clean_false_flag_rate_above_a_fifth_fails(self) -> None:
        items = _passing_items()
        for index in (15, 16, 17):  # 3 of 10 baselines flagged, none at a residual
            items[index] = _scored(
                f"b{index}",
                "baseline",
                "pass",
                _review("reject"),
                unit=f"book-{index % 5}",
                needed_repair=False,
            )
        result = evaluate_g3b(
            compute_figures(items), half="held_out", live=True, complete=True
        )
        assert any(
            n.startswith("clean false-flag") for n, ok, _ in result.checks if not ok
        )

    def test_run_agreement_below_point_nine_fails(self) -> None:
        items = _passing_items()
        for index in (15, 16):
            items[index] = _scored(
                f"b{index}",
                "baseline",
                "pass",
                _review("pass", runs=("pass", "reject")),
                unit=f"book-{index % 5}",
                needed_repair=False,
            )
        result = evaluate_g3b(
            compute_figures(items), half="held_out", live=True, complete=True
        )
        assert any(
            n.startswith("run agreement") for n, ok, _ in result.checks if not ok
        )


class TestHeldOutRule:
    """D12: one held-out run per pairing, one prompt revision after a failure, then stop."""

    def _run(
        self,
        prompt: str,
        *,
        passed: bool | None,
        writer: str = WRITER,
        reviewer: str = REVIEWER,
    ) -> JsonObj:
        return {
            "run_id": f"run-{prompt}",
            "writer_model": writer,
            "reviewer_model": reviewer,
            "prompt_hash": prompt,
            "g3b_passed": passed,
        }

    def _allowed(self, records: list[JsonObj], prompt: str) -> tuple[bool, str]:
        return check_held_out_allowed(
            records, writer_model=WRITER, reviewer_model=REVIEWER, prompt_hash=prompt
        )

    def test_a_first_run_is_allowed(self) -> None:
        assert self._allowed([], "h1")[0]

    def test_a_repeat_with_the_same_prompt_hash_is_refused(self) -> None:
        allowed, reason = self._allowed([self._run("h1", passed=False)], "h1")
        assert not allowed
        assert "already run" in reason

    def test_one_revision_with_a_new_hash_is_allowed_after_a_failure(self) -> None:
        assert self._allowed([self._run("h1", passed=False)], "h2")[0]

    def test_an_unfinished_first_run_counts_as_failed(self) -> None:
        assert self._allowed([self._run("h1", passed=None)], "h2")[0]

    def test_a_passed_first_run_allows_no_second_look(self) -> None:
        allowed, reason = self._allowed([self._run("h1", passed=True)], "h2")
        assert not allowed
        assert "passed G3b" in reason

    def test_after_the_one_revision_the_pairing_is_closed(self) -> None:
        records = [self._run("h1", passed=False), self._run("h2", passed=False)]
        assert not self._allowed(records, "h3")[0]
        assert not self._allowed(records, "h2")[0]

    def test_a_different_pairing_starts_fresh(self) -> None:
        records = [self._run("h1", passed=False, reviewer="openai/gpt-5.6-sol")]
        assert self._allowed(records, "h1")[0]


# ---------------------------------------------------------------------------
# The harness end to end, on hand-made fixtures
# ---------------------------------------------------------------------------


class RejectEverythingProvider:
    """Rejects every plan, always citing the same entry that no seed edited."""

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        return Completion(
            text=json.dumps(
                {
                    "verdict": "reject",
                    "confidence": 0.9,
                    "findings": [
                        {
                            "entry": "n_elsewhere",
                            "class": "state_contradiction",
                            "severity": "blocker",
                            "reason": "a flag on an entry no seed touched",
                        }
                    ],
                }
            ),
            usage=TokenUsage("openrouter", REVIEWER, 20_000, 3_000, 10, 1_000),
            finish_reason="stop",
            vendor_cost_usd=None,
        )


class MarkerProvider:
    """Answers by a marker planted in the plan text: reject, residual or pass."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        self.calls += 1
        findings: list[JsonObj] = []
        verdict = "pass"
        if "MARK_REJECT" in prompt:
            verdict = "reject"
            findings = [
                {
                    "entry": "c_take_map",
                    "class": "label_outcome_mismatch",
                    "severity": "should-fix",
                    "reason": f"intent and outcome disagree {EM_DASH} see n_path",
                }
            ]
        elif "MARK_RESIDUAL" in prompt:
            verdict = "reject"
            findings = [
                {
                    "entry": "n_fork",
                    "class": "other",
                    "severity": "should-fix",
                    "reason": "known",
                }
            ]
        return Completion(
            text=json.dumps(
                {"verdict": verdict, "confidence": 0.8, "findings": findings}
            ),
            usage=TokenUsage("openrouter", REVIEWER, 20_000, 3_000, 10, 1_000),
            finish_reason="stop",
            vendor_cost_usd=None,
        )


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


class Tree:
    """A fixture repo: one clean pair, one checker-rejected pair, and the three sets."""

    def __init__(self, root: Path, harness: ModuleType) -> None:
        self.root = root
        self.harness = harness
        clean_book, clean_plan = base_example()
        bad_book, bad_plan = next(w for w in WITNESSES if w.rule_id == "SP-7").build()
        self.book_sha = {
            "clean": _write(root / "books/clean.json", json.dumps(clean_book).encode()),
            "bad": _write(root / "books/bad.json", json.dumps(bad_book).encode()),
        }
        self.plans = {"clean": clean_plan, "bad": bad_plan}
        self.real: list[JsonObj] = []
        self.synthetic: list[JsonObj] = []
        self.baselines: list[JsonObj] = []

    def _pair(
        self, kind: str, item_id: str, marker: str | None
    ) -> tuple[JsonObj, JsonObj]:
        plan = json.loads(json.dumps(self.plans[kind]))
        if marker is not None:
            plan["pitch"]["hero"] = f"{marker} hero"
        digest = _write(
            self.root / f"plans/{item_id}.plan.json", json.dumps(plan).encode()
        )
        book = {
            "file": f"books/{kind}.json",
            "unit": "book-x",
            "sha256": self.book_sha[kind],
        }
        return {"file": f"plans/{item_id}.plan.json", "sha256": digest}, book

    def add_real(
        self,
        item_id: str,
        *,
        kind: str = "clean",
        expected: str = "reject",
        marker: str | None = None,
        half: str = "held_out",
        strength: str = "strong",
        blockers: tuple[str, ...] = (),
        severity: str | None = "should-fix",
        unit: str = "book-x",
    ) -> None:
        plan, book = self._pair(kind, item_id, marker)
        book["unit"] = unit
        self.real.append(
            {
                "id": item_id,
                "kind": "plan",
                "half": half,
                "expected_verdict": expected,
                "label_strength": strength,
                "severity": severity,
                "defects": [{"id": b, "severity": "blocker"} for b in blockers],
                "known_residuals": [],
                "plan": plan,
                "book": book,
            }
        )

    def add_synthetic(
        self,
        item_id: str,
        *,
        kind: str,
        family: str,
        code: str,
        marker: str | None = None,
        edited_paths: tuple[str, ...] = (),
    ) -> None:
        plan, book = self._pair(kind, item_id, marker)
        self.synthetic.append(
            {
                "id": item_id,
                "kind": "plan",
                "half": "held_out",
                "expected_verdict": "reject",
                "family": family,
                "class_code": code if family == "B" else None,
                "intended_rule": code if family == "A" else None,
                "edited_paths": list(edited_paths),
                "severity": "should-fix",
                "plan": plan,
                "book": book,
            }
        )

    def add_baseline(
        self,
        item_id: str,
        *,
        unit: str,
        marker: str | None = None,
        repaired: bool = False,
        residual_nodes: tuple[str, ...] = (),
        half: str = "held_out",
    ) -> None:
        plan, book = self._pair("clean", item_id, marker)
        book["unit"] = unit
        self.baselines.append(
            {
                "id": item_id,
                "kind": "plan",
                "half": half,
                "book": book,
                "plan": plan,
                "needed_repair": repaired,
                "checker_clean": True,
                "expected_verdict": "pass",
                "known_residuals": [{"nodes": list(residual_nodes), "choice": None}]
                if residual_nodes
                else [],
            }
        )

    def paths(self, *, baselines: bool = True) -> object:
        _write(self.root / "real.json", json.dumps({"items": self.real}).encode())
        _write(
            self.root / "synthetic.json", json.dumps({"items": self.synthetic}).encode()
        )
        if baselines:
            _write(
                self.root / "baselines.json",
                json.dumps(
                    {"schema": "clean-baselines/v1", "items": self.baselines}
                ).encode(),
            )
        return self.harness.Paths(
            repo=self.root,
            real_set=self.root / "real.json",
            synthetic_set=self.root / "synthetic.json",
            baselines=self.root / "baselines.json",
            out_root=self.root / "out",
        )


def _args(harness: ModuleType, *argv: str) -> argparse.Namespace:
    return cast("argparse.Namespace", harness._build_parser().parse_args(list(argv)))  # pyright: ignore[reportPrivateUsage]


def _live(*extra: str) -> list[str]:
    return [
        "--live",
        "--budget",
        "1000",
        "--reviewer-model",
        REVIEWER,
        "--writer-model",
        WRITER,
        *extra,
    ]


def _small_tree(harness: ModuleType, root: Path) -> Tree:
    tree = Tree(root, harness)
    tree.add_real("R-caught", kind="bad", blockers=("KD-1",), severity="blocker")
    tree.add_real("R-decisive", marker="MARK_REJECT")
    tree.add_real("R-missed", blockers=("KD-2",), severity="blocker")
    tree.add_real("R-clean", expected="pass")
    tree.add_real("R-unknown", expected="unknown", strength="unlabelled")
    tree.add_real("R-weak", expected="pass", strength="weak")
    tree.add_real("R-tuning", half="tuning", marker="MARK_REJECT")
    tree.add_synthetic("SY-A-1", kind="bad", family="A", code="SP-7")
    tree.add_synthetic(
        "SY-B-1",
        kind="clean",
        family="B",
        code="B1",
        marker="MARK_REJECT",
        edited_paths=("/choices/c_take_map/intent", "/choices/c_take_map/cost"),
    )
    tree.add_synthetic(
        "SY-B-2",
        kind="clean",
        family="B",
        code="B2",
        edited_paths=("/facts/f_new", "/nodes/n_fork/establishes"),
    )
    tree.add_baseline("BL-1", unit="book-x")
    tree.add_baseline("BL-2", unit="book-x", marker="MARK_REJECT", repaired=True)
    tree.add_baseline(
        "BL-3", unit="book-y", marker="MARK_RESIDUAL", residual_nodes=("n_fork",)
    )
    return tree


class TestHarnessEndToEnd:
    """Figures, per-book flags, the held-out gate and the outputs, on fixtures."""

    @pytest.fixture
    def tree(self, harness: ModuleType, tmp_path: Path) -> Tree:
        return _small_tree(harness, tmp_path)

    def _run(
        self,
        harness: ModuleType,
        tree: Tree,
        *argv: str,
        provider: object | None = None,
    ) -> int:
        import asyncio

        return asyncio.run(
            harness.run_validation(
                _args(harness, *argv),
                tree.paths(),
                provider_override=provider
                if provider is not None
                else MarkerProvider(),
            )
        )

    def _results(self, tree: Tree, run_id: str) -> JsonObj:
        return cast(
            "JsonObj",
            json.loads(
                (tree.root / "out" / run_id / "results.json").read_text("utf-8")
            ),
        )

    def test_figures_are_computed_from_the_fixture(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        code = self._run(
            harness,
            tree,
            "--half",
            "held_out",
            *_live("--confirm-held-out", "--run-id", "t1"),
        )
        assert (
            code == harness.EXIT_G3B_FAILED
        )  # 3 defective plans and 2 books: far below the minimums
        figures = cast("JsonObj", self._results(tree, "t1")["figures"])
        real = cast("JsonObj", figures["real_defective"])
        recall = cast("JsonObj", real["recall_overall"])
        assert (recall["k"], recall["n"]) == (2, 3)
        decisive = cast("JsonObj", real["reviewer_decisive_recall"])
        assert (decisive["k"], decisive["n"]) == (1, 2)
        caught = cast("JsonObj", real["checker_caught"])
        assert (caught["k"], caught["n"]) == (1, 3)
        assert real["blockers_all_flagged"] is False
        synthetic = cast("JsonObj", figures["synthetic"])
        assert cast("JsonObj", synthetic["family_A_checker_visible"])["k"] == 1
        assert cast("JsonObj", synthetic["family_B_checker_invisible"])["k"] == 1
        assert set(cast("JsonObj", synthetic["family_B_by_class"])) == {"B1", "B2"}
        clean = cast("JsonObj", figures["clean_baselines"])
        assert cast("JsonObj", clean["flag_rate_raw"])["k"] == 2
        assert cast("JsonObj", clean["false_flag_rate"])["k"] == 1
        assert clean["flags_explained_by_known_residual"] == 1
        by_book = cast("dict[str, dict[str, int]]", clean["by_book"])
        assert by_book["book-x"] == {"plans": 2, "flagged": 1, "false_flags": 1}
        assert by_book["book-y"] == {"plans": 1, "flagged": 1, "false_flags": 0}
        assert cast("JsonObj", clean["needed_repair_false_flags"])["k"] == 1
        assert cast("JsonObj", clean["no_repair_false_flags"])["n"] == 2
        agreement = cast("JsonObj", figures["run_agreement"])
        assert (agreement["k"], agreement["n"]) == (7, 7)
        assert figures["checker_only_clean_plans_rejected"] == 0

    def test_skipped_unknown_and_weak_plans_and_the_other_half_are_not_scored(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        self._run(
            harness,
            tree,
            "--half",
            "held_out",
            *_live("--confirm-held-out", "--run-id", "t2"),
        )
        document = self._results(tree, "t2")
        ids = {p["id"] for p in cast("list[JsonObj]", document["plans"])}
        assert "R-unknown" not in ids
        assert "R-weak" not in ids
        assert "R-tuning" not in ids
        assert "R-clean" not in ids  # clean-labelled real plans are only checked
        run = cast("JsonObj", document["run"])
        assert run["skipped_real_plans"] == {"unknown": 1, "weak": 1}
        assert run["plans_checker_only"] == 1

    def test_the_outputs_are_written_and_free_of_the_em_dash(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        self._run(
            harness,
            tree,
            "--half",
            "held_out",
            *_live("--confirm-held-out", "--run-id", "t3"),
        )
        out = tree.root / "out" / "t3"
        report = (out / "report.md").read_text("utf-8")
        assert "G3b: **FAIL**" in report
        assert "| Figure | Value |" in report
        assert "## Limits" in report
        for path in out.rglob("*"):
            if path.is_file():
                assert EM_DASH not in path.read_text("utf-8"), path
        raw = json.loads((out / "raw" / "R-decisive.run1.json").read_text("utf-8"))
        assert "raw_text" in raw
        assert "\\u2014" in (out / "raw" / "R-decisive.run1.json").read_text("utf-8")
        document = self._results(tree, "t3")
        run = cast("JsonObj", document["run"])
        assert run["prompt_hash"] == harness.plan_review_prompt_hash()
        assert run["reported_models"] == [REVIEWER]
        assert run["cost_usd"] > 0
        assert cast("JsonObj", document["g3b"])["passed"] is False
        assert not (tree.root / "out" / "validated-pairing.json").exists()

    def test_a_held_out_run_needs_confirmation_and_is_recorded(
        self, harness: ModuleType, tree: Tree, capsys: pytest.CaptureFixture[str]
    ) -> None:
        provider = MarkerProvider()
        code = self._run(
            harness,
            tree,
            "--half",
            "held_out",
            *_live("--run-id", "t4"),
            provider=provider,
        )
        assert code == harness.EXIT_BAD_INPUT
        assert "--confirm-held-out" in capsys.readouterr().err
        assert provider.calls == 0
        assert not (tree.root / "out" / "held-out-runs.json").exists()

    def test_the_held_out_gate_refuses_a_repeat_and_allows_one_revision(
        self,
        harness: ModuleType,
        tree: Tree,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        argv = ["--half", "held_out", *_live("--confirm-held-out")]
        assert (
            self._run(harness, tree, *argv, "--run-id", "h1") == harness.EXIT_G3B_FAILED
        )
        record = json.loads(
            (tree.root / "out" / "held-out-runs.json").read_text("utf-8")
        )
        (entry,) = record["runs"]
        assert entry["run_id"] == "h1"
        assert entry["finished"] is True
        assert entry["g3b_passed"] is False
        assert entry["prompt_hash"] == harness.plan_review_prompt_hash()
        # An unchanged prompt hash is refused, and spends nothing.
        provider = MarkerProvider()
        assert (
            self._run(harness, tree, *argv, "--run-id", "h2", provider=provider)
            == harness.EXIT_BAD_INPUT
        )
        assert "already run" in capsys.readouterr().err
        assert provider.calls == 0
        # One revision (a different hash) is allowed after the failure ...
        monkeypatch.setattr(
            harness, "plan_review_prompt_hash", lambda: "sha256:" + "1" * 64
        )
        assert (
            self._run(harness, tree, *argv, "--run-id", "h3") == harness.EXIT_G3B_FAILED
        )
        # ... and then the pairing is closed, even for a third new hash.
        monkeypatch.setattr(
            harness, "plan_review_prompt_hash", lambda: "sha256:" + "2" * 64
        )
        assert (
            self._run(harness, tree, *argv, "--run-id", "h4") == harness.EXIT_BAD_INPUT
        )
        assert "one prompt revision" in capsys.readouterr().err
        runs = json.loads(
            (tree.root / "out" / "held-out-runs.json").read_text("utf-8")
        )["runs"]
        assert [r["run_id"] for r in runs] == ["h1", "h3"]

    def test_the_tuning_half_needs_no_confirmation_and_records_nothing(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        tree.add_baseline("BL-T", unit="book-t", half="tuning")
        code = self._run(harness, tree, "--half", "tuning", *_live("--run-id", "tune1"))
        assert code == harness.EXIT_G3B_FAILED  # tuning never passes G3b
        ids = {
            p["id"]
            for p in cast("list[JsonObj]", self._results(tree, "tune1")["plans"])
        }
        assert ids == {"R-tuning", "BL-T"}
        assert not (tree.root / "out" / "held-out-runs.json").exists()

    def test_a_dry_run_uses_the_stub_writes_nothing_and_never_passes(
        self, harness: ModuleType, tree: Tree, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import asyncio

        code = asyncio.run(
            harness.run_validation(
                _args(harness, "--half", "held_out", "--dry-run"), tree.paths()
            )
        )
        assert code == harness.EXIT_OK
        out = capsys.readouterr().out
        assert "Dry run" in out
        assert "G3b: FAIL" in out
        assert not (tree.root / "out").exists()

    def test_a_live_run_without_a_budget_is_refused(
        self, harness: ModuleType, tree: Tree, capsys: pytest.CaptureFixture[str]
    ) -> None:
        provider = MarkerProvider()
        code = self._run(harness, tree, "--half", "tuning", "--live", provider=provider)
        assert code == harness.EXIT_BAD_INPUT
        assert "--budget" in capsys.readouterr().err
        assert provider.calls == 0

    def test_a_run_with_neither_mode_is_refused(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        assert self._run(harness, tree, "--half", "tuning") == harness.EXIT_BAD_INPUT

    def test_a_reviewer_equal_to_the_writer_is_refused_before_any_call(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        provider = MarkerProvider()
        code = self._run(
            harness,
            tree,
            "--half",
            "tuning",
            "--live",
            "--budget",
            "5",
            "--reviewer-model",
            WRITER,
            "--writer-model",
            WRITER,
            provider=provider,
        )
        assert code == harness.EXIT_NOT_INDEPENDENT
        assert provider.calls == 0

    def test_a_missing_baselines_manifest_stops_with_a_clear_message(
        self, harness: ModuleType, tree: Tree, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import asyncio

        paths = tree.paths(baselines=False)
        code = asyncio.run(
            harness.run_validation(
                _args(harness, "--half", "held_out", "--dry-run"), paths
            )
        )
        assert code == harness.EXIT_BAD_INPUT
        err = capsys.readouterr().err
        assert "clean-baselines manifest" in err
        assert "does not exist" in err

    def test_a_changed_file_fails_the_sha256_check(
        self, harness: ModuleType, tree: Tree, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tree.paths()
        path = tree.root / "plans/R-decisive.plan.json"
        path.write_bytes(path.read_bytes() + b" ")
        code = self._run(harness, tree, "--half", "held_out", "--dry-run")
        assert code == harness.EXIT_BAD_INPUT
        assert "sha256 mismatch" in capsys.readouterr().err

    def test_a_wrong_manifest_schema_is_refused(
        self, harness: ModuleType, tree: Tree, capsys: pytest.CaptureFixture[str]
    ) -> None:
        paths = tree.paths()
        paths.baselines.write_text(
            json.dumps({"schema": "other", "items": []}), encoding="utf-8"
        )  # pyright: ignore[reportAttributeAccessIssue]
        import asyncio

        code = asyncio.run(
            harness.run_validation(
                _args(harness, "--half", "held_out", "--dry-run"), paths
            )
        )
        assert code == harness.EXIT_BAD_INPUT
        assert "clean-baselines/v1" in capsys.readouterr().err

    def test_a_spend_stop_makes_the_run_incomplete_and_never_passes(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        argv = [
            "--half",
            "held_out",
            "--live",
            "--budget",
            "0.0001",
            "--reviewer-model",
            REVIEWER,
            "--writer-model",
            WRITER,
            "--confirm-held-out",
            "--run-id",
            "stop1",
        ]
        provider = MarkerProvider()
        assert (
            self._run(harness, tree, *argv, provider=provider)
            == harness.EXIT_SPEND_STOP
        )
        assert provider.calls == 0
        document = self._results(tree, "stop1")
        run = cast("JsonObj", document["run"])
        assert run["spend_stopped"] is True
        assert run["plans_unrun"] > 0
        assert cast("JsonObj", document["g3b"])["passed"] is False
        record = json.loads(
            (tree.root / "out" / "held-out-runs.json").read_text("utf-8")
        )["runs"][0]
        assert record["spend_stopped"] is True
        assert record["g3b_passed"] is False
        assert not (tree.root / "out" / "validated-pairing.json").exists()

    def test_only_narrows_the_run_and_a_partial_run_cannot_pass(
        self, harness: ModuleType, tree: Tree, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = self._run(
            harness,
            tree,
            "--half",
            "held_out",
            *_live("--confirm-held-out", "--run-id", "p1", "--only", "R-decisive,BL-1"),
        )
        assert code == harness.EXIT_G3B_FAILED
        document = self._results(tree, "p1")
        assert {p["id"] for p in cast("list[JsonObj]", document["plans"])} == {
            "R-decisive",
            "BL-1",
        }
        assert cast("JsonObj", document["run"])["partial"] is True
        checks = cast("list[JsonObj]", cast("JsonObj", document["g3b"])["checks"])
        assert next(c for c in checks if c["name"] == "run complete")["passed"] is False
        assert (
            self._run(harness, tree, "--half", "tuning", "--dry-run", "--only", "nope")
            == harness.EXIT_BAD_INPUT
        )
        assert "nope" in capsys.readouterr().err

    def test_the_cost_projection_counts_only_plans_the_checker_passes(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        tree.paths()
        candidates, _ = harness.load_candidates(tree.paths(), "held_out")
        projection = harness.estimate_run(
            candidates, runs=2, price_in=3.0, price_out=15.0, output_tokens=10_000
        )
        assert projection["checker_already_rejects"] == 2  # R-caught, SY-A-1
        assert (
            projection["plans"] == 7
        )  # R-decisive, R-missed, SY-B-1, SY-B-2, BL-1 to BL-3
        assert projection["calls"] == 14
        assert cast("float", projection["usd"]) > 0

    def test_a_validated_pairing_is_written_only_when_g3b_passes(
        self, harness: ModuleType, tmp_path: Path
    ) -> None:
        tree = Tree(tmp_path, harness)
        for i in range(15):
            tree.add_real(
                f"R{i}", kind="bad", severity="blocker", blockers=(f"KD-{i}",)
            )
        for i in range(10):
            tree.add_baseline(f"B{i}", unit=f"book-{i % 5}")
        code = self._run(
            harness,
            tree,
            "--half",
            "held_out",
            *_live("--confirm-held-out", "--run-id", "ok1"),
        )
        assert code == harness.EXIT_OK
        document = self._results(tree, "ok1")
        assert cast("JsonObj", document["g3b"])["passed"] is True
        pairing = json.loads(
            (tmp_path / "out" / "validated-pairing.json").read_text("utf-8")
        )
        assert (pairing["writer_model"], pairing["reviewer_model"]) == (
            WRITER,
            REVIEWER,
        )
        assert pairing["prompt_hash"] == harness.plan_review_prompt_hash()
        parsed = parse_validated_pairing(pairing["value"])
        assert parsed is not None
        assert parsed.prompt_hash == pairing["prompt_hash"]
        record = json.loads(
            (tmp_path / "out" / "held-out-runs.json").read_text("utf-8")
        )["runs"][0]
        assert record["g3b_passed"] is True


# ---------------------------------------------------------------------------
# The single-plan CLI
# ---------------------------------------------------------------------------


class TestLocatedRecallAndRescore:
    """Located recall, the reject-everything diagnostic and the offline re-scorer."""

    @pytest.fixture
    def tree(self, harness: ModuleType, tmp_path: Path) -> Tree:
        return _small_tree(harness, tmp_path)

    def _run(
        self, harness: ModuleType, tree: Tree, run_id: str, provider: object
    ) -> int:
        import asyncio

        return asyncio.run(
            harness.run_validation(
                _args(
                    harness,
                    "--half",
                    "held_out",
                    *_live("--confirm-held-out", "--run-id", run_id),
                ),
                tree.paths(),
                provider_override=provider,
            )
        )

    def _doc(self, directory: Path, name: str = "results.json") -> JsonObj:
        return cast("JsonObj", json.loads((directory / name).read_text("utf-8")))

    def test_results_record_the_seeded_entries_and_the_findings_at_them(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        self._run(harness, tree, "loc1", MarkerProvider())
        plans = {
            cast("str", p["id"]): p
            for p in cast(
                "list[JsonObj]", self._doc(tree.root / "out" / "loc1")["plans"]
            )
        }
        hit = plans["SY-B-1"]
        assert hit["seeded_entry_ids"] == ["c_take_map"]
        assert hit["reviewer_findings_at_entry"] == {
            "c_take_map": [
                {"class": "label_outcome_mismatch", "severity": "should-fix"}
            ]
        }
        assert hit["located"] is True
        miss = plans["SY-B-2"]
        assert miss["seeded_entry_ids"] == ["f_new", "n_fork"]
        assert miss["reviewer_findings_at_entry"] == {"f_new": [], "n_fork": []}
        assert miss["located"] is False
        assert plans["BL-3"]["residual_entries"] == ["n_fork"]
        assert plans["R-missed"]["blockers"] == ["KD-2"]

    def test_a_reviewer_that_rejects_everything_scores_below_its_any_reject_recall(
        self, harness: ModuleType, tree: Tree, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._run(harness, tree, "all1", RejectEverythingProvider())
        out = tree.root / "out" / "all1"
        synthetic = cast(
            "JsonObj", cast("JsonObj", self._doc(out)["figures"])["synthetic"]
        )
        any_reject = cast("JsonObj", synthetic["family_B_checker_invisible"])
        located = cast("JsonObj", synthetic["family_B_located"])
        assert (any_reject["k"], any_reject["n"]) == (2, 2)
        assert (located["k"], located["n"]) == (0, 2)
        by_class = cast("JsonObj", synthetic["family_B_located_by_class"])
        assert set(by_class) == {"B1", "B2"}
        assert all(cast("JsonObj", v)["k"] == 0 for v in by_class.values())
        diagnostic = cast(
            "JsonObj",
            cast("JsonObj", self._doc(out)["figures"])["reject_everything_diagnostic"],
        )
        assert diagnostic["warning"] is True
        report = (out / "report.md").read_text("utf-8")
        assert "WARNING: the reviewer flagged more than 90%" in report
        assert "located recall, family B: 0/2" in report
        assert "any-reject recall 2/2" in report
        assert "## (f) Reject-everything diagnostic" in report

    def test_g3b_rules_ignore_located_recall(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        self._run(harness, tree, "g3b1", RejectEverythingProvider())
        g3b = cast("JsonObj", self._doc(tree.root / "out" / "g3b1")["g3b"])
        names = [c["name"] for c in cast("list[JsonObj]", g3b["checks"])]
        assert not any("locat" in cast("str", n) for n in names)

    def test_the_warning_does_not_trigger_for_a_discriminating_reviewer(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        self._run(harness, tree, "ok1", MarkerProvider())
        out = tree.root / "out" / "ok1"
        diagnostic = cast(
            "JsonObj",
            cast("JsonObj", self._doc(out)["figures"])["reject_everything_diagnostic"],
        )
        assert diagnostic["warning"] is False
        report = (out / "report.md").read_text("utf-8")
        assert "WARNING: the reviewer flagged" not in report
        assert "No warning" in report

    def test_rescore_reproduces_the_figures_and_leaves_the_original_untouched(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        self._run(harness, tree, "re1", MarkerProvider())
        out = tree.root / "out" / "re1"
        before = {n: (out / n).read_bytes() for n in ("results.json", "report.md")}
        assert harness.rescore_run(out, tree.paths()) == harness.EXIT_OK
        assert {n: (out / n).read_bytes() for n in before} == before
        original = self._doc(out)
        rescored = self._doc(out, "results.rescored.json")
        assert rescored["figures"] == original["figures"]
        assert rescored["g3b"] == original["g3b"]
        note = cast("JsonObj", rescored["rescored"])
        assert note["model_calls"] == 0
        assert note["original_g3b_passed"] == note["g3b_passed_now"]
        report = (out / "report.rescored.md").read_text("utf-8")
        assert "Re-scored offline" in report
        assert EM_DASH not in report
        assert EM_DASH not in (out / "results.rescored.json").read_text("utf-8")

    def test_rescore_refuses_to_overwrite_its_outputs(
        self,
        harness: ModuleType,
        tree: Tree,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._run(harness, tree, "re2", MarkerProvider())
        out = tree.root / "out" / "re2"
        assert harness.rescore_run(out, tree.paths()) == harness.EXIT_OK
        first = (out / "report.rescored.md").read_bytes()
        (out / "report.rescored.md").write_text("edited by hand\n", encoding="utf-8")
        assert harness.rescore_run(out, tree.paths()) == harness.EXIT_BAD_INPUT
        assert "never overwrites" in capsys.readouterr().err
        assert (out / "report.rescored.md").read_text("utf-8") == "edited by hand\n"
        assert first != b"edited by hand\n"
        # One of the two outputs existing is enough to refuse.
        (out / "report.rescored.md").unlink()
        assert harness.rescore_run(out, tree.paths()) == harness.EXIT_BAD_INPUT
        assert not (out / "report.rescored.md").exists()

    def test_rescore_of_a_directory_without_results_is_refused(
        self,
        harness: ModuleType,
        tree: Tree,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        empty = tmp_path / "empty-run"
        empty.mkdir()
        assert harness.rescore_run(empty, tree.paths()) == harness.EXIT_BAD_INPUT
        assert "cannot read" in capsys.readouterr().err
        assert not any(empty.iterdir())

    def test_rescore_backfills_a_results_file_written_before_the_new_fields(
        self, harness: ModuleType, tree: Tree
    ) -> None:
        self._run(harness, tree, "old1", MarkerProvider())
        out = tree.root / "out" / "old1"
        document = self._doc(out)
        expected = cast("JsonObj", document["figures"])
        for plan in cast("list[JsonObj]", document["plans"]):
            for key in (
                "blockers",
                "residual_entries",
                "seeded_entry_ids",
                "reviewer_findings_at_entry",
                "located",
            ):
                plan.pop(key)
        (out / "results.json").write_text(json.dumps(document), encoding="utf-8")
        assert harness.rescore_run(out, tree.paths()) == harness.EXIT_OK
        rescored = self._doc(out, "results.rescored.json")
        assert rescored["figures"] == expected

    def test_the_cli_rescores_a_run_directory_and_rejects_mixed_modes(
        self,
        harness: ModuleType,
        tree: Tree,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._run(harness, tree, "cli1", MarkerProvider())
        out = tree.root / "out" / "cli1"
        assert harness.main(["--rescore", str(out)]) == harness.EXIT_OK
        assert (out / "results.rescored.json").is_file()
        capsys.readouterr()
        assert (
            harness.main(["--rescore", str(out), "--half", "tuning"])
            == harness.EXIT_BAD_INPUT
        )
        assert "--rescore takes only a run directory" in capsys.readouterr().err
        assert harness.main(["--dry-run"]) == harness.EXIT_BAD_INPUT
        assert "--half is required" in capsys.readouterr().err

    def test_rescoring_the_committed_tuning_run_locates_three_of_four_seeds(
        self, harness: ModuleType, tmp_path: Path
    ) -> None:
        source = _REPO / "docs/planning/evidence/plan-reviewer/tuning-1/results.json"
        run = tmp_path / "tuning-1"
        run.mkdir()
        (run / "results.json").write_bytes(source.read_bytes())
        assert harness.rescore_run(run, harness.Paths()) == harness.EXIT_OK
        figures = cast("JsonObj", self._doc(run, "results.rescored.json")["figures"])
        synthetic = cast("JsonObj", figures["synthetic"])
        located = cast("JsonObj", synthetic["family_B_located"])
        assert (located["k"], located["n"]) == (3, 4)
        by_class = cast("dict[str, JsonObj]", synthetic["family_B_located_by_class"])
        assert {k: v["k"] for k, v in by_class.items()} == {
            "B1": 0,
            "B2": 1,
            "B3": 1,
            "B4": 1,
        }
        diagnostic = cast("JsonObj", figures["reject_everything_diagnostic"])
        assert diagnostic["warning"] is True


class TestReviewCli:
    """scripts/review_story_plan.py: one plan, its book, a verdict."""

    def _files(self, root: Path, kind: str = "clean") -> tuple[Path, Path]:
        if kind == "clean":
            book, plan = base_example()
        else:
            book, plan = next(w for w in WITNESSES if w.rule_id == "SP-7").build()
        book_path, plan_path = root / "book.json", root / "plan.json"
        book_path.write_text(json.dumps(book), encoding="utf-8")
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return plan_path, book_path

    def test_a_dry_run_prints_the_verdict_and_the_cost_line(
        self, review_cli: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        plan, book = self._files(tmp_path)
        code = review_cli.main(
            [
                "--plan",
                str(plan),
                "--book",
                str(book),
                "--dry-run",
                "--reviewer-model",
                REVIEWER,
                "--writer-model",
                WRITER,
            ]
        )
        out = capsys.readouterr().out
        assert code == review_cli.EXIT_PASS
        assert "verdict: pass" in out
        assert "stub provider" in out
        assert "calls: 2" in out

    def test_a_checker_error_rejects_without_a_call(
        self, review_cli: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        plan, book = self._files(tmp_path, "bad")
        code = review_cli.main(
            [
                "--plan",
                str(plan),
                "--book",
                str(book),
                "--dry-run",
                "--reviewer-model",
                REVIEWER,
                "--writer-model",
                WRITER,
            ]
        )
        out = capsys.readouterr().out
        assert code == review_cli.EXIT_REJECT
        assert "checker_caught" in out
        assert "calls: 0" in out

    def test_a_live_review_without_a_budget_is_refused(
        self, review_cli: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        plan, book = self._files(tmp_path)
        code = review_cli.main(["--plan", str(plan), "--book", str(book)])
        assert code == review_cli.EXIT_UNREADABLE
        assert "--budget" in capsys.readouterr().err

    def test_the_writer_cannot_review_its_own_plan(
        self, review_cli: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        plan, book = self._files(tmp_path)
        code = review_cli.main(
            [
                "--plan",
                str(plan),
                "--book",
                str(book),
                "--dry-run",
                "--reviewer-model",
                WRITER,
                "--writer-model",
                WRITER,
            ]
        )
        assert code == review_cli.EXIT_NOT_INDEPENDENT
        assert "REFUSED" in capsys.readouterr().err

    def test_an_unreadable_plan_is_exit_two(
        self, review_cli: ModuleType, tmp_path: Path
    ) -> None:
        _, book = self._files(tmp_path)
        assert (
            review_cli.main(
                [
                    "--plan",
                    str(tmp_path / "missing.json"),
                    "--book",
                    str(book),
                    "--dry-run",
                ]
            )
            == review_cli.EXIT_UNREADABLE
        )


def test_no_em_dash_in_the_scripts_figures_and_template() -> None:
    for rel in (
        "scripts/validate_plan_reviewer.py",
        "scripts/review_story_plan.py",
        "src/cyo_adventure/storyplan/review_figures.py",
        "src/cyo_adventure/storyplan/review.py",
        "src/cyo_adventure/generation/templates/plan_review.md",
    ):
        assert EM_DASH not in (_REPO / rel).read_text(encoding="utf-8"), rel
