"""Unit tests for located recall and the reject-everything diagnostic (WP-3.7).

Pure scoring only: ``cyo_adventure.storyplan.review_figures`` takes scored plans
and returns figures, so nothing here touches a file, a model or the network.
Located recall credits a synthetic seed only when a reviewer finding names an
entry the seed edited; the "any reject" recall credits any reject or unsure, so
a reviewer that rejects everything must score below it.
"""

from __future__ import annotations

from typing import Literal

import pytest

from cyo_adventure.storyplan.review import PlanReview, ReviewFinding
from cyo_adventure.storyplan.review_figures import (
    REJECT_EVERYTHING_MIN,
    ScoredPlan,
    compute_figures,
    pointer_entry_ids,
    seeded_entry_ids,
)

Verdict = Literal["pass", "reject", "unsure"]


def _finding(entry: str, severity: str = "should-fix") -> ReviewFinding:
    return ReviewFinding(
        entry=entry,
        defect_class="label_outcome_mismatch",
        severity="blocker" if severity == "blocker" else "should-fix",
        reason="r",
    )


def _review(verdict: Verdict, *findings: ReviewFinding, ran: bool = True) -> PlanReview:
    return PlanReview(
        verdict=verdict,
        confidence=None,
        findings=tuple(findings),
        reasons=(),
        run_verdicts=(verdict, verdict) if ran else (),
        checker_caught=not ran,
        reviewer_ran=ran,
    )


def _seed(
    plan_id: str,
    defect_class: str,
    seeded: tuple[str, ...],
    review: PlanReview,
    *,
    family: str = "B",
) -> ScoredPlan:
    return ScoredPlan(
        id=plan_id,
        source="synthetic",
        half="tuning",
        unit="book-a",
        expected="reject",
        review=review,
        family=family,
        defect_class=defect_class,
        seeded_entries=frozenset(seeded),
    )


def _baseline(plan_id: str, review: PlanReview) -> ScoredPlan:
    return ScoredPlan(
        id=plan_id,
        source="baseline",
        half="tuning",
        unit=f"book-{plan_id}",
        expected="pass",
        review=review,
        needed_repair=False,
    )


class TestPointerEntryIds:
    """One JSON pointer to the plan entry ids it touches."""

    @pytest.mark.parametrize(
        ("pointer", "expected"),
        [
            ("/choices/c_a_hearth_1/intent", {"c_a_hearth_1"}),
            ("/choices/c_left", {"c_left"}),
            ("/nodes/n_start/establishes", {"n_start"}),
            ("/nodes/n_start/requires", {"n_start"}),
            ("/facts/grandmother_writes_postcards", {"grandmother_writes_postcards"}),
            ("/facts/maya_explorer/text", {"maya_explorer"}),
            ("/endings/da_bat_back/gift", {"da_bat_back"}),
            ("/endings/e_rec_a", {"e_rec_a"}),
            ("/threads/t_key/payoff_sites/0/shows", {"t_key"}),
            ("/threads/has_battery/payoff_sites", {"has_battery"}),
            ("/choices/c~1odd/intent", {"c/odd"}),
            ("/choices/c~0odd/intent", {"c~odd"}),
        ],
    )
    def test_each_pointer_shape_gives_its_entry_id(
        self, pointer: str, expected: set[str]
    ) -> None:
        assert pointer_entry_ids(pointer) == frozenset(expected)

    def test_a_node_pointer_that_walks_into_a_fact_list_by_id_counts_the_fact(
        self,
    ) -> None:
        assert pointer_entry_ids("/nodes/pho_entry/establishes/f_new") == frozenset(
            {"pho_entry", "f_new"}
        )

    def test_a_node_pointer_with_a_list_index_counts_only_the_node(self) -> None:
        assert pointer_entry_ids("/nodes/pho_entry/establishes/0") == frozenset(
            {"pho_entry"}
        )

    @pytest.mark.parametrize(
        "pointer",
        [
            "",
            "/",
            "choices/c1",
            "/choices",
            "/choices/",
            "/truth/rules/0",
            "/provenance/notes",
            "/cast/maya/role",
        ],
    )
    def test_a_pointer_that_names_no_entry_gives_nothing(self, pointer: str) -> None:
        assert pointer_entry_ids(pointer) == frozenset()


class TestSeededEntryIds:
    """All the entries a seed's edited paths touch."""

    def test_two_pointers_into_one_choice_give_one_id(self) -> None:
        paths = ["/choices/c_a_hearth_1/intent", "/choices/c_a_hearth_1/cost"]
        assert seeded_entry_ids(paths) == frozenset({"c_a_hearth_1"})

    def test_a_node_edit_that_adds_a_fact_counts_the_node_and_the_fact(self) -> None:
        paths = ["/facts/grandmother_writes_postcards", "/nodes/pho_entry/establishes"]
        assert seeded_entry_ids(paths) == frozenset(
            {"grandmother_writes_postcards", "pho_entry"}
        )

    def test_pointers_into_several_collections_give_every_entry(self) -> None:
        paths = [
            "/threads/has_battery/payoff_sites",
            "/nodes/e_he_okafor/requires",
            "/choices/c_n_start_1/cost",
            "/endings/e_pho_a/gift",
        ]
        assert seeded_entry_ids(paths) == frozenset(
            {"has_battery", "e_he_okafor", "c_n_start_1", "e_pho_a"}
        )

    def test_no_paths_gives_no_entries(self) -> None:
        assert seeded_entry_ids([]) == frozenset()


class TestLocatedRecall:
    """Located recall beside the any-reject recall, with intervals."""

    def test_a_reviewer_that_rejects_everything_is_located_below_any_reject(
        self,
    ) -> None:
        elsewhere = _finding("n_elsewhere", "blocker")
        items = [
            _seed("B1-1", "B1", ("c_one",), _review("reject", elsewhere)),
            _seed("B2-1", "B2", ("f_two", "n_two"), _review("reject", elsewhere)),
            _seed("B3-1", "B3", ("e_three",), _review("unsure", elsewhere)),
            _seed("B4-1", "B4", ("t_four",), _review("reject", elsewhere)),
        ]
        figures = compute_figures(items)
        assert figures.synthetic_b.rate == 1.0
        assert figures.located_b.k == 0
        assert figures.located_b.n == 4
        assert figures.located_b.rate is not None
        assert figures.synthetic_b.rate is not None
        assert figures.located_b.rate < figures.synthetic_b.rate
        assert {c: p.k for c, p in figures.located_b_by_class.items()} == {
            "B1": 0,
            "B2": 0,
            "B3": 0,
            "B4": 0,
        }

    def test_a_finding_at_a_seeded_entry_is_located(self) -> None:
        items = [
            _seed("B1-1", "B1", ("c_one",), _review("reject", _finding("c_one"))),
            _seed(
                "B2-1",
                "B2",
                ("f_two", "n_two"),
                _review("reject", _finding("n_two"), _finding("other")),
            ),
            _seed("B3-1", "B3", ("e_three",), _review("reject", _finding("other"))),
        ]
        figures = compute_figures(items)
        assert (figures.located_b.k, figures.located_b.n) == (2, 3)
        assert figures.located_b_by_class["B1"].k == 1
        assert figures.located_b_by_class["B2"].k == 1
        assert figures.located_b_by_class["B3"].k == 0

    def test_findings_of_both_runs_count_through_the_unioned_review(self) -> None:
        # PlanReview.findings is the union of the runs, so a finding raised by
        # only one run still locates the seed.
        review = PlanReview(
            verdict="unsure",
            confidence=None,
            findings=(_finding("c_one"),),
            reasons=("runs_disagree",),
            run_verdicts=("reject", "pass"),
        )
        figures = compute_figures([_seed("B1-1", "B1", ("c_one",), review)])
        assert figures.located_b.k == 1

    def test_a_pass_with_a_minor_finding_at_the_entry_is_not_located(self) -> None:
        item = _seed("B1-1", "B1", ("c_one",), _review("pass", _finding("c_one")))
        assert not item.located
        assert compute_figures([item]).located_b.k == 0

    def test_located_entries_name_which_seeded_entries_were_flagged(self) -> None:
        item = _seed(
            "B2-1",
            "B2",
            ("f_two", "n_two"),
            _review("reject", _finding("n_two"), _finding("zz")),
        )
        assert item.located_entries == ("n_two",)

    def test_a_seed_with_no_known_entries_is_counted_apart_not_as_a_miss(self) -> None:
        items = [
            _seed("B1-1", "B1", ("c_one",), _review("reject", _finding("c_one"))),
            _seed("B1-2", "B1", (), _review("reject", _finding("c_two"))),
        ]
        figures = compute_figures(items)
        assert (figures.located_b.k, figures.located_b.n) == (1, 1)
        assert figures.located_b_unscorable == 1
        assert figures.synthetic_b.n == 2  # the any-reject denominator is unchanged

    def test_family_a_and_family_b_checker_caught_plans_change_nothing(self) -> None:
        items = [
            _seed(
                "A-1",
                "SP-1",
                ("c_left",),
                _review("reject", ran=False),
                family="A",
            ),
            _seed("B1-1", "B1", ("c_one",), _review("reject", _finding("c_one"))),
        ]
        figures = compute_figures(items)
        assert figures.synthetic_a.k == 1
        assert (figures.located_b.k, figures.located_b.n) == (1, 1)

    def test_the_figures_dict_carries_located_with_intervals(self) -> None:
        items = [
            _seed("B1-1", "B1", ("c_one",), _review("reject", _finding("c_one"))),
            _seed("B1-2", "B1", ("c_two",), _review("reject", _finding("zz"))),
        ]
        synthetic = compute_figures(items).to_dict()["synthetic"]
        assert isinstance(synthetic, dict)
        located = synthetic["family_B_located"]
        assert isinstance(located, dict)
        assert (located["k"], located["n"]) == (1, 2)
        assert located["ci95"] == pytest.approx([0.0945, 0.9055], abs=1e-3)
        assert "family_B_located_by_class" in synthetic
        assert synthetic["family_B_located_unscorable"] == 0


class TestRejectEverythingDiagnostic:
    """The share of reviewer-run plans flagged, and the discriminates-nothing warning."""

    def _flagged_everywhere(self, n_clean: int, n_seeds: int) -> list[ScoredPlan]:
        items = [
            _baseline(f"c{i}", _review("reject", _finding("x"))) for i in range(n_clean)
        ]
        items += [
            _seed(f"B-{i}", "B1", (f"c{i}",), _review("reject", _finding("x")))
            for i in range(n_seeds)
        ]
        return items

    def test_the_warning_triggers_when_clean_and_seeds_are_all_flagged(self) -> None:
        figures = compute_figures(self._flagged_everywhere(5, 4))
        assert figures.rejects_everything
        diagnostic = figures.to_dict()["reject_everything_diagnostic"]
        assert isinstance(diagnostic, dict)
        assert diagnostic["warning"] is True
        assert diagnostic["threshold"] == REJECT_EVERYTHING_MIN

    def test_the_share_counts_every_reviewer_run_plan_clean_and_defective(
        self,
    ) -> None:
        items = [
            _baseline("c1", _review("pass")),
            _baseline("c2", _review("reject", _finding("x"))),
            _seed("B1", "B1", ("c_one",), _review("reject", _finding("c_one"))),
            _seed("A1", "SP-1", ("c_left",), _review("reject", ran=False), family="A"),
        ]
        figures = compute_figures(items)
        assert (figures.reviewer_flag_all.k, figures.reviewer_flag_all.n) == (2, 3)
        assert (figures.reviewer_flag_seeds.k, figures.reviewer_flag_seeds.n) == (1, 1)

    def test_the_warning_does_not_trigger_when_clean_baselines_pass(self) -> None:
        items = [_baseline(f"c{i}", _review("pass")) for i in range(5)]
        items += [
            _seed(f"B-{i}", "B1", (f"c{i}",), _review("reject", _finding("x")))
            for i in range(4)
        ]
        assert not compute_figures(items).rejects_everything

    def test_the_warning_does_not_trigger_when_the_seeds_are_not_all_flagged(
        self,
    ) -> None:
        items = [_baseline(f"c{i}", _review("reject", _finding("x"))) for i in range(5)]
        items += [
            _seed("B-0", "B1", ("c0",), _review("reject", _finding("x"))),
            _seed("B-1", "B1", ("c1",), _review("pass")),
        ]
        assert not compute_figures(items).rejects_everything

    def test_exactly_ninety_percent_is_not_more_than_ninety_percent(self) -> None:
        clean = [_baseline(f"c{i}", _review("reject", _finding("x"))) for i in range(9)]
        clean.append(_baseline("c9", _review("pass")))
        seeds = [
            _seed(f"B-{i}", "B1", (f"c{i}",), _review("reject", _finding("x")))
            for i in range(4)
        ]
        assert not compute_figures(clean + seeds).rejects_everything

    def test_a_run_with_no_baselines_or_no_reviewer_run_seeds_does_not_warn(
        self,
    ) -> None:
        only_seeds = [_seed("B-0", "B1", ("c0",), _review("reject", _finding("x")))]
        only_clean = [_baseline("c0", _review("reject", _finding("x")))]
        checker_seeds = [
            _seed("A-0", "SP-1", ("c0",), _review("reject", ran=False), family="A"),
            *only_clean,
        ]
        assert not compute_figures(only_seeds).rejects_everything
        assert not compute_figures(only_clean).rejects_everything
        assert not compute_figures(checker_seeds).rejects_everything
        assert not compute_figures([]).rejects_everything
