"""Figures, thresholds and the held-out rule for the plan reviewer (WP-3.7).

The pure scoring half of ``scripts/validate_plan_reviewer.py``: it takes one
scored plan per validation item and computes the figures the D12 thresholds are
judged on, each as counts with a Wilson 95 percent interval (the samples are
small and clustered by book, so a bare rate would overstate what is known). No
I/O, no model, no clock.

Figures, never merged:

* **(a) real defective recall**, overall (the whole plan-approval path: checker
  plus reviewer), split into *checker-caught* plans (the deterministic checks
  reported an ERROR, so no model was needed) and *reviewer-decisive* plans (the
  checks were clean and only the reviewer could flag them); recall on the
  reviewer-decisive subset is the reviewer's own recall. Also split by the worst
  severity a plan carries, and per blocker entry.
* **(b) synthetic recall**, family A (checker-visible) and family B
  (checker-invisible) apart, B further by class.
* **(c) clean flag rate** on the checker-repaired baselines: raw, and with a
  reviewer finding at a recorded known residual counted as the true positive it
  is (``AL-882``); per book, and with and without the baselines that needed a
  repair.
* **(d) run agreement**: identical verdicts across the runs of a plan.
* **(e) the D12 thresholds and a G3b pass or fail line.**

The tuning discipline is here too: :func:`check_held_out_allowed` is the
pre-registered rule that refuses a second held-out run with a prompt hash
already run, and a revision budget of one (D12).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from cyo_adventure.storyplan.review import PlanReview

__all__ = [
    "AGREEMENT_MIN",
    "CLEAN_FLAG_MAX",
    "MIN_CLEAN_BOOKS",
    "MIN_DEFECTIVE",
    "RECALL_MIN",
    "Figures",
    "G3bResult",
    "Proportion",
    "ScoredPlan",
    "check_held_out_allowed",
    "compute_figures",
    "evaluate_g3b",
    "project_costs",
    "residual_explained",
    "wilson_interval",
]

RECALL_MIN: Final = 0.90
CLEAN_FLAG_MAX: Final = 0.20
AGREEMENT_MIN: Final = 0.90
MIN_DEFECTIVE: Final = 15
MIN_CLEAN_RAW: Final = 15
MIN_CLEAN_BOOKS: Final = 5
"""D12 as amended 2026-11-21 (``AL-853``): the clean minimum is met by baselines
of five books, reported per book, not by 15 independent clean plans."""

_Z95: Final = 1.959964
_BLOCKING_SEVERITIES: Final = ("blocker", "should-fix")

Source = Literal["real", "synthetic", "baseline"]


def wilson_interval(k: int, n: int) -> tuple[float, float]:
    """Return the Wilson 95 percent interval for ``k`` of ``n``.

    Args:
        k: Successes.
        n: Trials.

    Returns:
        tuple[float, float]: ``(low, high)``; ``(0.0, 1.0)`` when ``n`` is 0.
    """
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    z2 = _Z95**2
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = _Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True, slots=True)
class Proportion:
    """A count over a total, with its interval.

    Attributes:
        k: The numerator.
        n: The denominator.
    """

    k: int
    n: int

    @property
    def rate(self) -> float | None:
        """Return ``k / n``, or None when ``n`` is 0.

        Returns:
            float | None: The rate.
        """
        return None if self.n == 0 else self.k / self.n

    def to_dict(self) -> dict[str, object]:
        """Return the proportion as a JSON-ready dict.

        Returns:
            dict[str, object]: ``k``, ``n``, ``rate`` and ``ci95``.
        """
        low, high = wilson_interval(self.k, self.n)
        return {
            "k": self.k,
            "n": self.n,
            "rate": self.rate,
            "ci95": [round(low, 4), round(high, 4)],
        }

    def __str__(self) -> str:
        """Render as ``k/n = rate (95% low to high)``.

        Returns:
            str: The text.
        """
        if self.n == 0:
            return "0/0 (no plans)"
        low, high = wilson_interval(self.k, self.n)
        return (
            f"{self.k}/{self.n} = {self.k / self.n:.2f} (95% {low:.2f} to {high:.2f})"
        )


@dataclass(frozen=True, slots=True)
class ScoredPlan:
    """One validation item with the reviewer's final answer.

    Attributes:
        id: The item id.
        source: ``real`` (validation-set.json), ``synthetic`` or ``baseline``.
        half: ``tuning`` or ``held_out``.
        unit: The book (the split key).
        expected: ``reject`` (defective) or ``pass`` (clean).
        review: The final answer after the checker's authority.
        severity: The worst severity the plan carries (real and synthetic).
        blockers: Ids of the blocker-severity defect entries the plan carries.
        family: ``A`` or ``B`` for a synthetic item.
        defect_class: The synthetic class or rule (``B1`` to ``B4``, ``SP-3``).
        needed_repair: For a baseline, whether the checker repair changed it.
        residual_entries: Node and choice ids of the plan's known residuals.
    """

    id: str
    source: Source
    half: str
    unit: str
    expected: Literal["reject", "pass"]
    review: PlanReview
    severity: str | None = None
    blockers: tuple[str, ...] = ()
    family: str | None = None
    defect_class: str | None = None
    needed_repair: bool | None = None
    residual_entries: frozenset[str] = field(default_factory=frozenset)


def residual_explained(review: PlanReview, residual_entries: frozenset[str]) -> bool:
    """Whether a flag on a clean plan is the true positive a known residual is.

    A flag is explained when the plan has findings, at least one cites a known
    residual's node or choice, and no blocker or should-fix finding cites
    anything else. A flag with no findings (a disagreement or a parse failure)
    is not explained, and a flag elsewhere on the book is still a false flag.

    Args:
        review: The plan's final answer.
        residual_entries: The plan's known residuals' node and choice ids.

    Returns:
        bool: True when the flag is explained by a known residual.
    """
    if not review.flagged or not review.findings or not residual_entries:
        return False
    cited = any(f.entry in residual_entries for f in review.findings)
    elsewhere = any(
        f.severity in _BLOCKING_SEVERITIES and f.entry not in residual_entries
        for f in review.findings
    )
    return cited and not elsewhere


def _proportion(items: Sequence[ScoredPlan]) -> Proportion:
    """Count the flagged plans among ``items``.

    Args:
        items: The plans.

    Returns:
        Proportion: Flagged over total.
    """
    return Proportion(sum(1 for i in items if i.review.flagged), len(items))


@dataclass(frozen=True, slots=True)
class Figures:
    """Every figure for one run, in the order the report prints them.

    Attributes:
        real_recall: Flagged over all real defective plans (the whole path).
        real_checker_caught: Real defective plans the checker rejected.
        real_decisive: Reviewer-decisive plans, flagged over total: the
            reviewer's own recall.
        real_by_severity: Flagged over total per worst severity carried.
        blocker_entries: Per blocker entry id: plans carrying it, plans flagged.
        synthetic_a: Family A recall (a floor: checker-visible by construction).
        synthetic_b: Family B recall.
        synthetic_b_by_class: Family B recall per class.
        synthetic_by_half: Synthetic recall per family and half (for context).
        clean_raw: Flagged over baselines.
        clean_false: Flags not explained by a known residual, over baselines.
        clean_explained: Flags explained by a known residual.
        clean_by_book: Per book: raw flags, false flags, baselines.
        clean_repaired: False-flag proportion over baselines that needed repair.
        clean_unrepaired: False-flag proportion over baselines that did not.
        agreement: Plans whose runs gave identical verdicts, over plans the
            reviewer ran on.
        checker_only_clean: Clean-labelled real plans the checker rejected
            (a count; observation only).
        real_defective_n: Count of real defective plans.
        clean_books: Distinct books among the baselines.
    """

    real_recall: Proportion
    real_checker_caught: Proportion
    real_decisive: Proportion
    real_by_severity: dict[str, Proportion]
    blocker_entries: dict[str, dict[str, int]]
    synthetic_a: Proportion
    synthetic_b: Proportion
    synthetic_b_by_class: dict[str, Proportion]
    synthetic_by_half: dict[str, Proportion]
    clean_raw: Proportion
    clean_false: Proportion
    clean_explained: int
    clean_by_book: dict[str, dict[str, int]]
    clean_repaired: Proportion
    clean_unrepaired: Proportion
    agreement: Proportion
    real_defective_n: int
    clean_books: int
    checker_only_clean: int = 0

    @property
    def blockers_all_flagged(self) -> bool:
        """Whether every blocker entry had every plan carrying it flagged.

        Returns:
            bool: True when no blocker entry has an unflagged plan (vacuously
                true with no blocker entries).
        """
        return all(e["flagged"] == e["plans"] for e in self.blocker_entries.values())

    def to_dict(self) -> dict[str, object]:
        """Return every figure as a JSON-ready dict.

        Returns:
            dict[str, object]: The figures, each with counts and intervals.
        """
        return {
            "real_defective": {
                "recall_overall": self.real_recall.to_dict(),
                "checker_caught": self.real_checker_caught.to_dict(),
                "reviewer_decisive_recall": self.real_decisive.to_dict(),
                "by_worst_severity": {
                    k: v.to_dict() for k, v in sorted(self.real_by_severity.items())
                },
                "blocker_entries": self.blocker_entries,
                "blockers_all_flagged": self.blockers_all_flagged,
                "note": (
                    "checker_caught plans were rejected by SP-0 to SP-9 with no "
                    "model call; reviewer_decisive_recall is the reviewer's own"
                ),
            },
            "synthetic": {
                "family_A_checker_visible": self.synthetic_a.to_dict(),
                "family_B_checker_invisible": self.synthetic_b.to_dict(),
                "family_B_by_class": {
                    k: v.to_dict() for k, v in sorted(self.synthetic_b_by_class.items())
                },
                "by_family_and_half": {
                    k: v.to_dict() for k, v in sorted(self.synthetic_by_half.items())
                },
                "note": "synthetic recall overstates real recall; never merged",
            },
            "clean_baselines": {
                "flag_rate_raw": self.clean_raw.to_dict(),
                "false_flag_rate": self.clean_false.to_dict(),
                "flags_explained_by_known_residual": self.clean_explained,
                "by_book": self.clean_by_book,
                "needed_repair_false_flags": self.clean_repaired.to_dict(),
                "no_repair_false_flags": self.clean_unrepaired.to_dict(),
                "books": self.clean_books,
            },
            "run_agreement": self.agreement.to_dict(),
            "checker_only_clean_plans_rejected": self.checker_only_clean,
        }


def compute_figures(
    items: Sequence[ScoredPlan], *, checker_only_clean: int = 0
) -> Figures:
    """Compute every figure from the scored plans of one run.

    Args:
        items: One scored plan per validation item run.
        checker_only_clean: How many clean-labelled real plans the checker
            rejected (they are not sent to the reviewer; observation only).

    Returns:
        Figures: The figures.
    """
    real = [i for i in items if i.source == "real" and i.expected == "reject"]
    caught = [i for i in real if i.review.checker_caught]
    decisive = [i for i in real if not i.review.checker_caught]
    by_severity: dict[str, list[ScoredPlan]] = {}
    for item in real:
        by_severity.setdefault(item.severity or "unrated", []).append(item)
    entries: dict[str, list[ScoredPlan]] = {}
    for item in real:
        for entry in item.blockers:
            entries.setdefault(entry, []).append(item)
    synthetic = [i for i in items if i.source == "synthetic"]
    family_a = [i for i in synthetic if i.family == "A"]
    family_b = [i for i in synthetic if i.family == "B"]
    b_classes: dict[str, list[ScoredPlan]] = {}
    for item in family_b:
        b_classes.setdefault(item.defect_class or "unclassed", []).append(item)
    halves: dict[str, list[ScoredPlan]] = {}
    for item in synthetic:
        halves.setdefault(f"{item.family}:{item.half}", []).append(item)
    baselines = [i for i in items if i.source == "baseline"]
    false_flags = [
        i
        for i in baselines
        if i.review.flagged and not residual_explained(i.review, i.residual_entries)
    ]
    by_book: dict[str, dict[str, int]] = {}
    for item in baselines:
        row = by_book.setdefault(
            item.unit, {"plans": 0, "flagged": 0, "false_flags": 0}
        )
        row["plans"] += 1
        row["flagged"] += 1 if item.review.flagged else 0
        row["false_flags"] += 1 if item in false_flags else 0
    repaired = [i for i in baselines if i.needed_repair]
    unrepaired = [i for i in baselines if i.needed_repair is False]
    ran = [
        i for i in items if i.review.reviewer_ran and len(i.review.run_verdicts) >= 2
    ]
    agreed = sum(1 for i in ran if len(set(i.review.run_verdicts)) == 1)
    return Figures(
        real_recall=_proportion(real),
        real_checker_caught=Proportion(len(caught), len(real)),
        real_decisive=_proportion(decisive),
        real_by_severity={k: _proportion(v) for k, v in by_severity.items()},
        blocker_entries={
            entry: {
                "plans": len(carried),
                "flagged": sum(1 for p in carried if p.review.flagged),
            }
            for entry, carried in sorted(entries.items())
        },
        synthetic_a=_proportion(family_a),
        synthetic_b=_proportion(family_b),
        synthetic_b_by_class={k: _proportion(v) for k, v in b_classes.items()},
        synthetic_by_half={k: _proportion(v) for k, v in halves.items()},
        clean_raw=_proportion(baselines),
        clean_false=Proportion(len(false_flags), len(baselines)),
        clean_explained=sum(
            1
            for i in baselines
            if i.review.flagged and residual_explained(i.review, i.residual_entries)
        ),
        clean_by_book=by_book,
        clean_repaired=Proportion(
            sum(1 for i in repaired if i in false_flags), len(repaired)
        ),
        clean_unrepaired=Proportion(
            sum(1 for i in unrepaired if i in false_flags), len(unrepaired)
        ),
        agreement=Proportion(agreed, len(ran)),
        real_defective_n=len(real),
        clean_books=len({i.unit for i in baselines}),
        checker_only_clean=checker_only_clean,
    )


@dataclass(frozen=True, slots=True)
class G3bResult:
    """The gate G3b verdict and each condition behind it.

    Attributes:
        passed: True only when every condition holds.
        checks: ``(name, passed, detail)`` per condition, in report order.
    """

    passed: bool
    checks: tuple[tuple[str, bool, str], ...]

    def to_dict(self) -> dict[str, object]:
        """Return the verdict as a JSON-ready dict.

        Returns:
            dict[str, object]: ``passed`` and each check.
        """
        return {
            "passed": self.passed,
            "checks": [
                {"name": n, "passed": p, "detail": d} for n, p, d in self.checks
            ],
        }


def evaluate_g3b(
    figures: Figures, *, half: str, live: bool, complete: bool
) -> G3bResult:
    """Judge a run against every D12 threshold and the minimum validation size.

    G3b can pass only on the held-out half, from a live run that finished (no
    spend stop, no plan left unrun). Synthetic recall is reported but is not a
    threshold: D12 names none for it.

    Args:
        figures: The run's figures.
        half: The half the run covered.
        live: Whether the reviewer was a real model (a dry run never passes).
        complete: Whether every selected plan was run (no spend stop).

    Returns:
        G3bResult: The verdict and each condition.
    """
    recall = figures.real_recall.rate
    false_rate = figures.clean_false.rate
    agreement = figures.agreement.rate
    clean_detail = (
        f"{figures.clean_books} books, {figures.clean_raw.n} baselines, "
        f"unamended minimum {MIN_CLEAN_RAW} plans"
    )
    checks: list[tuple[str, bool, str]] = [
        ("held-out half", half == "held_out", f"half is {half}"),
        ("live reviewer", live, "a dry run never passes G3b"),
        ("run complete", complete, "every selected plan was run within the budget"),
        (
            f"defective plans >= {MIN_DEFECTIVE}",
            figures.real_defective_n >= MIN_DEFECTIVE,
            f"{figures.real_defective_n} real defective plans",
        ),
        (
            f"clean baselines cover >= {MIN_CLEAN_BOOKS} books (D12 amended)",
            figures.clean_books >= MIN_CLEAN_BOOKS,
            clean_detail,
        ),
        (
            f"defect recall >= {RECALL_MIN}",
            recall is not None and recall >= RECALL_MIN,
            str(figures.real_recall),
        ),
        (
            "every blocker entry flagged",
            figures.blockers_all_flagged,
            f"{len(figures.blocker_entries)} blocker entries",
        ),
        (
            f"clean false-flag rate <= {CLEAN_FLAG_MAX}",
            false_rate is not None and false_rate <= CLEAN_FLAG_MAX,
            str(figures.clean_false),
        ),
        (
            f"run agreement >= {AGREEMENT_MIN}",
            agreement is not None and agreement >= AGREEMENT_MIN,
            str(figures.agreement),
        ),
    ]
    return G3bResult(passed=all(ok for _, ok, _ in checks), checks=tuple(checks))


def check_held_out_allowed(
    records: Sequence[Mapping[str, object]],
    *,
    writer_model: str,
    reviewer_model: str,
    prompt_hash: str,
) -> tuple[bool, str]:
    """Apply the pre-registered held-out rule (D12: one revision, then stop).

    Records are per pairing (writer and reviewer). A held-out run is allowed
    when the pairing has none; or when it has exactly one that failed (or never
    finished, which counts as failed: it saw held-out data) and the prompt hash
    now differs. A prompt hash already run for the pairing is always refused,
    and after one revision the pairing is closed.

    Args:
        records: The entries of ``held-out-runs.json``.
        writer_model: The plan writer's model id.
        reviewer_model: The reviewer's model id.
        prompt_hash: The prompt hash about to be run.

    Returns:
        tuple[bool, str]: ``(allowed, reason)``.
    """
    mine = [
        r
        for r in records
        if r.get("writer_model") == writer_model
        and r.get("reviewer_model") == reviewer_model
    ]
    for record in mine:
        if record.get("prompt_hash") == prompt_hash:
            run_id = record.get("run_id")
            msg = f"held-out half already run for this pairing with this prompt hash (run {run_id}); refused"
            return False, msg
    if not mine:
        return True, "first held-out run for this pairing"
    if len(mine) == 1:
        if mine[0].get("g3b_passed") is True:
            msg = "first held-out run passed G3b; a changed prompt needs a new owner decision"
            return False, msg
        return True, "the one allowed prompt revision after a failed first run"
    msg = "pairing has used its held-out run and its one prompt revision (D12); refused"
    return False, msg


def project_costs(  # noqa: PLR0913 - the cost model's independent knobs
    prompt_chars: Sequence[int],
    *,
    runs: int,
    chars_per_token: float,
    output_tokens_per_call: int,
    input_usd_per_mtok: float,
    output_usd_per_mtok: float,
) -> dict[str, object]:
    """Project tokens and USD for ``runs`` calls of every prompt.

    Args:
        prompt_chars: The characters (system plus user) of each prompt that
            would reach the reviewer.
        runs: Calls per plan.
        chars_per_token: Characters per input token (the pilot measured about
            2.0 to 2.1 on plan JSON).
        output_tokens_per_call: Assumed output tokens per call, reasoning
            included (the pilot's twelve calls averaged about 14,000).
        input_usd_per_mtok: USD per million input tokens.
        output_usd_per_mtok: USD per million output tokens.

    Returns:
        dict[str, object]: Plans, calls, tokens in and out, and USD.
    """
    in_tokens = sum(math.ceil(c / chars_per_token) for c in prompt_chars) * runs
    out_tokens = len(prompt_chars) * runs * output_tokens_per_call
    usd = (
        in_tokens * input_usd_per_mtok + out_tokens * output_usd_per_mtok
    ) / 1_000_000
    return {
        "plans": len(prompt_chars),
        "calls": len(prompt_chars) * runs,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "usd": round(usd, 2),
        "assumptions": {
            "chars_per_token": chars_per_token,
            "output_tokens_per_call": output_tokens_per_call,
            "input_usd_per_mtok": input_usd_per_mtok,
            "output_usd_per_mtok": output_usd_per_mtok,
        },
    }
