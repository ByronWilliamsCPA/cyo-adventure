"""Two-model comprehension probe: an offline authoring accelerator (C1).

One model reads a passage and writes three comprehension questions about it
("what happened", "why", "what should the reader remember"). A **different**
model then tries to answer those questions from the passage text alone, with
no access to the rest of the story. A question the answer model cannot answer
confidently flags ambiguity, a missing causal link, or an unclear referent in
that passage.

This exists to test whether an LLM-based check can do better than the
project's own prior attempt at this class of problem.
:mod:`cyo_adventure.validator.continuity` built three formulations of a
reference-tracking check, measured **3.48 findings per node** over the
committed corpus at a **1 true positive in 6** rate on the narrowest
formulation, and shipped none of them as a rule. C1 only earns promotion to an
advisory moderation stage on a measured precision materially better than that,
against human-reviewed stories.

**This script cannot compute that precision figure, and does not try to.**
Precision requires a human to label each unanswerable-question finding as a
true or false positive, and no such labelling exists yet. What this script
measures is the *unlabelled* unanswerable-question rate: how often the answer
model says it cannot answer from the text. That number is a real, useful
signal (it is what a human labeller would triage), but it is not precision,
and a report from this script never claims otherwise. Turning it into
precision needs a human to read every recorded finding (see
``ProbeSummary.questions_unanswerable`` for the count) and judge, for each
one, whether the passage really was ambiguous or the answer model simply
missed something stated plainly in the text. Until that labelling happens,
the promote-or-reject decision this feeds stays open.

Offline only: this script reads no database and no request, is never imported
by ``app.py`` or any router, and is not deployed surface. It reads story JSON
files from disk and calls two OpenRouter model legs.

Output goes under a gitignored reports path (default
``tmp/comprehension-probe-reports/``), not a tracked one, so raw model output
never lands in the repository. This is the opposite convention from
``scripts/judge_books.py`` / ``scripts/evaluate_books.py``, which use
``scripts/_paid_output.py``'s ``ensure_persistable`` to *refuse* a gitignored
destination (AL-379: those scripts' results are the measurement, so losing
them loses the finding). Here the plan is explicit that raw model output must
not be committed, so this script reuses only ``_paid_output``'s private
``_is_ignored`` check and inverts the verdict: it refuses to run against a
destination git is *not* configured to ignore, rather than the other way
round. This guard exists because the obvious default, ``out/reports/``,
*looks* gitignored (an empty-seeming subdirectory of a mostly-scratch tree)
but is not: `.gitignore` only ignores specific subtrees under ``out/``
(``out/diversity/``, ``out/mutations/``, ``out/w7/arms/``), and ``out/reports/``
itself already carries tracked content (`.gitkeep`, compliance-report
markdown). A destination that merely looks safe is exactly the failure mode
the cap-that-never-fires trap generalizes to: verify the property, do not
assume it from the name.

The run's AGGREGATE is the exception: counts, rates, model ids, prompt
version, sampling strategy, per-story breakdown and observed spend go to a
tracked directory (default ``out/reports/comprehension-probe/``) as
``summary-<run_id>.json``, with ``latest-summary.json`` beside it as a
pointer. Run-stamped rather than fixed-name, because a paid finding that the
next invocation overwrites is barely more durable than one never written.

Usage::

    uv run python scripts/comprehension_probe.py \\
        --corpus out --pattern '*.filled.json' --age-band 5-8 \\
        --max-passages 60 --budget-usd 5.00 \\
        --out tmp/comprehension-probe-reports
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cyo_adventure.core.config import Settings  # noqa: E402
from cyo_adventure.core.exceptions import (  # noqa: E402
    BusinessLogicError,
    ConfigurationError,
)
from cyo_adventure.core.pricing import (  # noqa: E402
    CostEstimate,
    estimate_cost,
    price_for,
)
from cyo_adventure.generation.provider import (  # noqa: E402
    build_openrouter_cost_reporting_leg,
)
from cyo_adventure.utils.logging import get_logger  # noqa: E402
from scripts._paid_output import (  # noqa: E402
    _is_ignored,  # pyright: ignore[reportPrivateUsage]
    ensure_persistable,
)
from scripts.adversarial_harness import (  # noqa: E402
    _load_env_file,  # pyright: ignore[reportPrivateUsage]
    _resolve_within,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.generation.usage import Completion

logger = get_logger(__name__)

__all__ = [
    "AnswerRecord",
    "BudgetTracker",
    "CorpusStats",
    "NodeResult",
    "Passage",
    "ProbeSummary",
    "collect_passages",
    "probe_passage",
    "run_probe",
    "summarize",
]

# A skeleton node whose body still holds this directive has no prose yet: it
# is a fill instruction, not a passage. AL and the plan's trap list are both
# explicit that silently including these corrupts the aggregate (an empty
# artifact reads as either "obviously answerable" or "obviously not",
# depending on what a model does when handed a template string, and either
# way moves the rate in a direction nobody chose). They are counted and
# excluded, never scored.
_FILL_PREFIX: Final[str] = "<<FILL"

_QUESTIONS_PER_PASSAGE: Final[int] = 3

# A run id becomes a directory name and a filename, so it is constrained to
# characters that cannot escape the destination it is joined onto.
_RUN_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._-]+")

# The fixed-name file beside the run-stamped aggregates. It holds a POINTER,
# never a run's findings: see :func:`write_tracked_aggregate`.
_LATEST_POINTER_NAME: Final[str] = "latest-summary.json"

# The one provider this script routes through, and the first half of the
# ``core.pricing.PRICES`` key both models are looked up by.
_PROVIDER: Final[str] = "openrouter"

# #ASSUME: external-resources: the comprehension probe's two-model split
# remains available and priced under the current budget.
# #VERIFY: before the pilot run, confirm that both model ids resolve to a
# complete price row (:func:`_ensure_models_are_priced`, which `main` calls
# before any spend), that the two ids are genuinely different
# (:func:`_validate_model_pair`, called at import), and that every report
# records the model ids and prompt-set version, so a figure is attributable to
# a configuration: tests/unit/test_comprehension_probe.py::
# TestConfiguredModels::test_the_two_configured_models_are_not_the_same_model,
# ::test_both_configured_models_resolve_to_a_complete_price_row and
# ::test_an_unpriced_model_refuses_to_start.
#
# The plan's original wording asked for these ids to be confirmed "against the
# provider allowlist", and that instruction was wrong rather than merely
# unperformed. ``generation/allowlist.py`` is an admin-editable DATABASE table
# (``provider_model_allowlist``), and its only enforcement point in ``src/`` is
# ``story_requests/authoring_plan.py::is_enabled_allowlist_pair``, which gates
# which provider/model a guardian or admin may select for FAMILY-LANE story
# generation. It governs no offline script, reads no script, and this script
# reads no database. Every other paid offline harness here already runs models
# absent from ``DEFAULT_ALLOWLIST`` for the same reason
# (``scripts/judge_books.py`` uses ``openai/gpt-5.6-sol``,
# ``scripts/w7_battery.py`` uses ``anthropic/claude-sonnet-5``,
# ``scripts/yield_harness.py`` documents ``google/gemma-4-31b-it:free``), so
# holding this one script to the family-lane allowlist would be a rule applied
# to exactly one caller. What the pair genuinely must satisfy is checked above:
# distinct, and priced. Recorded rather than silently dropped, because
# "confirm X" left unperformed and "confirm X" found inapplicable are
# indistinguishable in a diff.
#
# Two different labs, both cheap, both routed through the OpenRouter leg per
# ADR-003 (the direct anthropic leg is excluded from family-lane generation
# and unnecessary here regardless: this script is offline tooling, not a
# family-lane call). Genuinely different models matter more than which two:
# one model both asking and answering measures the model's self-consistency,
# not the passage's clarity.
_QUESTION_MODEL: Final[str] = "google/gemini-2.5-flash"
_ANSWER_MODEL: Final[str] = "deepseek/deepseek-v4-flash"


def _validate_model_pair(question_model: str, answer_model: str) -> None:
    """Refuse a configuration in which one model both asks and answers.

    The plan is explicit that the two models must genuinely differ: one model
    doing both measures that model's self-consistency, not the passage's
    clarity, and every number the run produces would be mislabelled. Checked
    at import rather than in ``main`` so the property cannot be edited away and
    left to be caught by a reviewer: a run, a test session, and a bare import
    all fail immediately and identically.

    Args:
        question_model: The model id that generates questions.
        answer_model: The model id that answers them.

    Raises:
        ConfigurationError: When the two ids are the same.
    """
    if question_model == answer_model:
        msg = (
            f"comprehension probe misconfigured: the question and answer legs "
            f"are both {question_model!r}. One model asking and answering its "
            "own questions measures that model's self-consistency, not the "
            "passage's clarity, so every rate the run reports would be "
            "mislabelled. Configure two genuinely different models."
        )
        raise ConfigurationError(msg)


_validate_model_pair(_QUESTION_MODEL, _ANSWER_MODEL)

# Bumped whenever the question or answer prompt text changes materially, so a
# report is attributable to the exact wording that produced it, not just the
# model ids.
_PROMPT_SET_VERSION: Final[str] = "comprehension-probe-v1"

# Recorded verbatim in every report, because a rate is only interpretable
# against the slice that produced it and "60 passages of this band" does not
# say which 60. Bump the version suffix whenever the selection rule changes,
# so two aggregates are never silently compared across different slices.
#
# #ASSUME: data-integrity: a figure published from a capped corpus walk is
# read as a figure about the whole population unless the artifact itself says
# otherwise, so the selection rule must travel with the number.
# #VERIFY: tests/unit/test_comprehension_probe.py::TestStratification::
# test_the_slice_spans_each_story_rather_than_its_opening pins that the
# selection is not a prefix, and tests/unit/test_comprehension_probe.py::
# TestSummarize::test_the_summary_records_the_sampling_strategy pins that the
# strategy is carried in the artifact.
_SAMPLING_STRATEGY: Final[str] = (
    "stratified-stride/v1: the cap is divided round-robin across the stories "
    "in the slice, and each story's share is taken at even intervals across "
    "that story's whole eligible node list, so the slice spans each story "
    "rather than sampling its opening passages"
)

# Sized for headroom over three short questions (or three short answers) plus
# JSON structure, not for the answer alone: AL-323 is what a per-node budget
# equal to the expected product buys you. Both chosen models are non-reasoning
# fast tiers, so the gap between "content" and "budget" should be small; the
# pilot run's actual truncation count is reported, not assumed.
_QUESTION_MAX_TOKENS: Final[int] = 1200
_ANSWER_MAX_TOKENS: Final[int] = 1500

_QUESTION_SYSTEM: Final[str] = (
    "You write comprehension questions for a children's reading assessment. "
    "You are given one passage from a branching story and must write exactly "
    f"{_QUESTIONS_PER_PASSAGE} short questions about it: one asking what "
    "happened, one asking why it happened, and one asking what the reader "
    "should remember going forward. Base every question only on this "
    "passage; do not assume anything about the rest of the story. Return "
    "only the JSON object requested, with no commentary around it."
)

_ANSWER_SYSTEM: Final[str] = (
    "You answer reading-comprehension questions using only the passage you "
    "are given. You have not read any other part of this story and must not "
    "guess at it. If the passage does not contain enough information to "
    "answer a question confidently, set can_answer to false and leave answer "
    "empty rather than inferring from outside knowledge or genre convention. "
    "Return only the JSON object requested, with no commentary around it."
)


@dataclass(frozen=True, slots=True)
class Passage:
    """One node's body, treated as a comprehension-probe passage.

    Attributes:
        story_id: The story's declared ``id``, falling back to the file stem
            when the document carries none.
        story_path: Path to the source file, relative to the repo root, kept
            for the per-story report grouping.
        node_id: The node's ``id`` within the story.
        body: The node's prose. Never a ``<<FILL ...>>`` directive; see
            :data:`_FILL_PREFIX`.
    """

    story_id: str
    story_path: str
    node_id: str
    body: str


@dataclass(frozen=True, slots=True)
class CorpusStats:
    """Counts from walking the corpus, before any model is called.

    Attributes:
        files_scanned: JSON files found under ``--corpus`` matching
            ``--pattern``.
        files_skipped_non_storybook: Files whose top-level ``nodes`` was not a
            list (sidecar contract/lineage/narrative files, or malformed
            JSON), so they were never Storybook documents to begin with.
        files_skipped_age_band: Files excluded by ``--age-band`` filtering.
        nodes_seen: Node dicts encountered across every included file.
        nodes_skipped_fill: Nodes excluded because ``body`` was a
            ``<<FILL ...>>`` directive.
        nodes_skipped_empty: Nodes excluded because ``body`` was missing or
            blank.
        passages_collected: What survived the cap, in the order they will be
            probed (round-robin across stories, strided within each; see
            :func:`collect_passages` and :data:`_SAMPLING_STRATEGY`).
        stories_available: How many distinct stories contributed at least one
            eligible passage before the cap was applied.
        stories_sampled: How many of those the collected slice actually drew
            from. When this is 1 and ``stories_available`` is more, the run's
            headline is a single-book figure whatever the slice was called.
    """

    files_scanned: int
    files_skipped_non_storybook: int
    files_skipped_age_band: int
    nodes_seen: int
    nodes_skipped_fill: int
    nodes_skipped_empty: int
    passages_collected: int
    stories_available: int
    stories_sampled: int


class ProbeParseError(ValueError):
    """A completion could not be parsed into the expected JSON shape.

    Attributes:
        kind: ``"truncated"`` when the completion was cut off before a
            complete JSON object was emitted, ``"malformed"`` when a complete
            reply carried invalid or wrongly-shaped JSON. The two need
            opposite fixes (raise the token budget vs. fix the prompt), so
            conflating them misattributes every truncated response as a
            model formatting failure.
    """

    def __init__(self, message: str, *, kind: str) -> None:
        """Record the parse failure and its kind.

        Args:
            message: Human-readable detail, safe to put in a report.
            kind: ``"truncated"`` or ``"malformed"``.
        """
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class AnswerRecord:
    """One question-answer pair from the answer model.

    Attributes:
        question: The question as generated (or as echoed back by the answer
            model, when it does not echo verbatim the two are compared by
            position, not by text).
        can_answer: Whether the answer model reported it could answer this
            question from the passage alone. ``False`` is the raw,
            unlabelled finding this script exists to produce.
        answer: The answer model's answer text, empty when ``can_answer`` is
            ``False``.
        reason: Optional short justification the answer model gave.
    """

    question: str
    can_answer: bool
    answer: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class NodeResult:
    """The outcome of probing one passage, successful or not.

    Attributes:
        story_id: Which story this node belongs to.
        node_id: The node probed.
        questions: The generated questions, or ``None`` if question
            generation failed or the budget was exhausted before this node.
        answers: The answer records, aligned by position with ``questions``,
            or ``None`` if answering failed, was skipped for budget, or
            question generation itself failed.
        error_stage: ``None`` on full success, else one of
            ``"question_generation:<kind>"``, ``"answering:<kind>"``,
            ``"budget"`` (no calls made), or ``"budget_after_questions"``
            (questions generated, answer call skipped).
        error_detail: Human-readable detail for ``error_stage``, or ``""``.
    """

    story_id: str
    node_id: str
    questions: list[str] | None
    answers: list[AnswerRecord] | None
    error_stage: str | None
    error_detail: str = ""


class UnaccountableSpendError(BusinessLogicError):
    """A call was made whose cost could not be established.

    Raised by :meth:`BudgetTracker.add` rather than counted, because a cost
    that cannot be established is the one input a spend cap cannot survive.
    See that method for why an exception rather than a flag.
    """

    def __init__(self, message: str) -> None:
        """Record the unaccountable call.

        Args:
            message: Human-readable detail naming the call and the reason.
        """
        super().__init__(message, rule="probe_unaccountable_spend")


def _ensure_models_are_priced() -> None:
    """Refuse to start unless both configured models carry a complete price.

    This is the first half of the cap's fail-closed behaviour, and it exists
    because the second half is a diagnosis after the money is gone. An
    unpriced pair makes :func:`~cyo_adventure.core.pricing.estimate_cost`
    return ``amount_usd=0, complete=False`` for every call, so a run against
    one would post zero for every call it made, never reach any cap, and
    report a spend of ``$0`` for real money. Reachable by a one-line edit to
    a model constant, a vendor slug rename, or a price refresh that drops a
    row. Checked once, before anything is spent, and it names which model is
    at fault so the diagnosis is not a search.

    Raises:
        ConfigurationError: When either model has no price row, or a row
            missing either half of its rate. A half-priced row is refused for
            the same reason a missing one is: it yields ``complete=False``,
            which is the state the cap cannot bind on.
    """
    problems: list[str] = []
    for role, model in (("question", _QUESTION_MODEL), ("answer", _ANSWER_MODEL)):
        price = price_for(_PROVIDER, model)
        if price is None:
            problems.append(
                f"{role} model {model!r}: no ({_PROVIDER}, model) row in "
                "core/pricing.py, so every call would cost 0 and the cap "
                "would never bind"
            )
        elif price.input_usd_per_mtok is None or price.output_usd_per_mtok is None:
            half = "input" if price.input_usd_per_mtok is None else "output"
            problems.append(
                f"{role} model {model!r}: price row is missing its {half} "
                "rate, so every cost estimate would be incomplete"
            )
    if problems:
        msg = (
            "refusing to start: the spend cap cannot bind on this model pair. "
            + "; ".join(problems)
            + ". Add the missing price row(s) with "
            "`uv run python scripts/refresh_pricing.py`, or configure models "
            "that are priced."
        )
        raise ConfigurationError(msg)


@dataclass
class BudgetTracker:
    """Tracks spend against a hard dollar cap and stops new calls once hit.

    Two independent spend figures are carried, and the cap binds on the
    larger. ``observed_usd`` is what the vendor said it charged, call by call
    (``Completion.vendor_cost_usd``); ``spent_usd`` is what
    ``core/pricing.py``'s dated, hand-transcribed table implies. They are kept
    apart rather than reconciled because they are different kinds of fact: the
    first is a measurement, the second an inference whose own module docstring
    warns that a vendor price change makes it silently wrong. Reporting only
    the estimate is how a spend claim ends up self-refuting; reporting only
    the vendor figure would leave the cap unable to bind on any call the
    vendor declined to price.

    #CRITICAL: payment/financial: a call whose ESTIMATE is incomplete raises
    out of :meth:`add` instead of being counted. Until it did, an unpriced
    pair or a response missing its ``usage`` block posted ``Decimal(0)``,
    ``exhausted`` stayed ``False`` forever, and 100 passages of 100k-in /
    100k-out ran to completion against a $0.0000001 cap reporting
    ``SPENT: 0``: the cap bound on nothing at all and spend was limited only
    by ``--max-passages``. The old code counted those calls in
    ``incomplete_cost_calls`` and NOTHING read that counter, which is this
    repository's documented tri-state trap: "off" and "not yet determined"
    were both falsy and collapsed into benign. An exception cannot collapse
    that way, which is why the decision point raises rather than returning a
    flag a caller may forget to test.
    #VERIFY: tests/unit/test_comprehension_probe.py::
    TestBudgetTracker::test_an_unpriced_call_aborts_the_run_rather_than_costing_zero
    and ::test_an_unreported_usage_block_aborts_the_run
    and ::test_an_absurdly_low_cap_stops_the_run_after_one_passage
    and ::test_the_real_cap_does_not_fire_on_a_realistic_slice.

    #CRITICAL: concurrency: ``exhausted`` and ``add`` are checked and updated
    from a single sequential loop (:func:`run_probe`), never from concurrent
    tasks. A concurrent caller could read ``exhausted`` as ``False`` on
    several tasks before any of them calls ``add``, overshooting the cap by
    however many calls raced past the check; that is exactly the shape of the
    prior defect this repository already paid for (a clamp that existed and
    never bound). Sequential processing is what makes the cap exact rather
    than best-effort.
    #VERIFY: tests/unit/test_comprehension_probe.py::
    TestBudgetTracker::test_an_absurdly_low_cap_stops_the_run_after_one_passage
    and ::test_the_real_cap_does_not_fire_on_a_realistic_slice.

    Attributes:
        cap_usd: The hard spend limit. Never exceeded by the run stopping new
            calls; a call already in flight when the cap is crossed still
            posts its real cost, so the charged total can land at or slightly
            over ``cap_usd``, never further.
        spent_usd: Price-table cost of every call made so far, summed from
            :func:`~cyo_adventure.core.pricing.estimate_cost`. Always a
            complete sum, because an incomplete estimate raises instead of
            being added.
        observed_usd: Sum of the vendor's own per-call charges, over the calls
            that reported one. A lower bound whenever
            ``calls_reporting_vendor_cost`` is below ``calls``.
        calls: How many provider calls were actually made.
        calls_reporting_vendor_cost: How many of those calls carried a vendor
            cost. Reported so ``observed_usd`` is never read as covering more
            calls than it does.
    """

    cap_usd: Decimal
    spent_usd: Decimal = field(default_factory=lambda: Decimal(0))
    observed_usd: Decimal = field(default_factory=lambda: Decimal(0))
    calls: int = 0
    calls_reporting_vendor_cost: int = 0

    def add(self, estimate: CostEstimate, *, vendor_cost_usd: Decimal | None) -> None:
        """Post one call's cost against the running totals.

        Args:
            estimate: The call's price-table cost, from
                :func:`~cyo_adventure.core.pricing.estimate_cost`.
            vendor_cost_usd: What the vendor said this call cost, or ``None``
                when it reported nothing. ``None`` is never treated as zero.

        Raises:
            UnaccountableSpendError: When ``estimate.complete`` is ``False``.
                The call has already been made and already cost money, so the
                run is stopped at the first one rather than continuing to buy
                calls it cannot count.
        """
        self.calls += 1
        if not estimate.complete:
            msg = (
                f"call {self.calls} produced no usable cost "
                f"({estimate.reason or 'reason not reported'}), so the "
                f"${self.cap_usd} cap cannot bind on it. Aborting: a run that "
                "cannot count what it spends bounds its spend by convention, "
                "not by a cap. Spend accounted for before this call: "
                f"${self.spent_usd} (price table), ${self.observed_usd} "
                "(vendor-reported)."
            )
            raise UnaccountableSpendError(msg)
        self.spent_usd += estimate.amount_usd
        if vendor_cost_usd is not None:
            self.observed_usd += vendor_cost_usd
            self.calls_reporting_vendor_cost += 1

    @property
    def charged_usd(self) -> Decimal:
        """The spend figure the cap binds on: the larger of the two totals.

        Returns:
            ``max(spent_usd, observed_usd)``. Taking the larger is what keeps
            the cap conservative when the two disagree, which they will
            whenever the price table has drifted from the vendor's live rate.
        """
        return max(self.spent_usd, self.observed_usd)

    @property
    def exhausted(self) -> bool:
        """Whether spend has reached or passed the cap.

        Returns:
            ``True`` once :attr:`charged_usd` reaches ``cap_usd``. Checked
            before every provider call in :func:`run_probe`, so once true no
            further calls are made.
        """
        return self.charged_usd >= self.cap_usd


@dataclass(frozen=True, slots=True)
class StoryBreakdown:
    """One story's share of a run, so a headline cannot hide its sources.

    The aggregate rate alone cannot distinguish a band-wide finding from one
    book's prose style, and the first pilot's headline was a single-book
    figure that read as an age-band one. Reporting per story is what makes
    that visible in the artifact rather than reconstructable only by someone
    who thinks to check.

    Attributes:
        story_id: The story these counts belong to.
        passages_probed: Nodes from this story that produced answers.
        questions_asked: Questions asked across those nodes.
        questions_unanswerable: How many the answer model declined.
        unlabelled_unanswerable_rate: The per-story rate, or ``None`` when
            this story produced no answered questions.
    """

    story_id: str
    passages_probed: int
    questions_asked: int
    questions_unanswerable: int
    unlabelled_unanswerable_rate: float | None


@dataclass(frozen=True, slots=True)
class ProbeSummary:
    """The aggregate report for one probe run.

    Every field a reader needs in order not to mistake this for a precision
    figure lives here: the model ids, the prompt version, an explicit
    ``unlabelled_unanswerable_rate`` name rather than anything calling itself
    precision, ``per_story`` so an aggregate rate cannot be read as band-wide
    when it came from one book, and ``sampling_strategy`` so it cannot be read
    as whole-story when it came from one part of each book.

    The two spend figures are deliberately both present and separately named.
    ``observed_spend_usd`` is what the vendor charged, summed from
    ``Completion.vendor_cost_usd`` over the
    ``calls_reporting_vendor_cost`` calls that reported one; ``spend_usd`` is
    what ``core/pricing.py``'s dated table implies. Collapsing them into one
    number is how a spend claim becomes an estimate presented as a
    measurement. ``charged_usd`` is the larger of the two, and is the figure
    the cap actually bound on.
    """

    generated_at: str
    corpus_description: str
    sampling_strategy: str
    question_model: str
    answer_model: str
    prompt_set_version: str
    corpus_stats: CorpusStats
    nodes_processed: int
    nodes_skipped_budget: int
    questions_asked: int
    questions_unanswerable: int
    unlabelled_unanswerable_rate: float | None
    avg_unanswerable_findings_per_node: float | None
    nodes_with_any_unanswerable: int
    error_counts: dict[str, int]
    per_story: list[StoryBreakdown]
    budget_cap_usd: str
    spend_usd: str
    observed_spend_usd: str
    charged_usd: str
    budget_exhausted: bool
    calls_made: int
    calls_reporting_vendor_cost: int
    uniform_verdict_warning: str | None
    note: str = (
        "unlabelled_unanswerable_rate is NOT precision. Turning it into a "
        "precision figure requires a human to read every finding this run "
        "recorded and judge whether the passage was genuinely ambiguous or "
        "the answer model missed something stated plainly in the text. No "
        "promote-or-reject verdict is recorded from this run."
    )


def _cost_of(completion: Completion) -> CostEstimate:
    """Cost one completion from the price table.

    Args:
        completion: A provider response, carrying which provider/model
            answered and what it consumed.

    Returns:
        The call's cost, a lower bound when the pair is unpriced or the
        backend did not report token counts.
    """
    price = price_for(completion.usage.provider, completion.usage.model)
    return estimate_cost(
        price, completion.usage.input_tokens, completion.usage.output_tokens
    )


def _question_prompt(passage_body: str) -> str:
    """Build the question-generation prompt for one passage.

    Args:
        passage_body: The node's prose.

    Returns:
        The user-role prompt.
    """
    return (
        f"Read this passage from a children's story and write exactly "
        f"{_QUESTIONS_PER_PASSAGE} short comprehension questions about it: "
        "one about what happened, one about why it happened, and one about "
        "what the reader should remember. Return exactly this JSON shape "
        'and nothing else: {"questions": ["...", "...", "..."]}\n\n'
        f"PASSAGE\n{passage_body}"
    )


def _answer_prompt(passage_body: str, questions: Sequence[str]) -> str:
    """Build the answering prompt for one passage and its questions.

    Args:
        passage_body: The same node prose the questions were generated from.
        questions: The questions to answer, in order.

    Returns:
        The user-role prompt.
    """
    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    return (
        "Below is a passage from a children's story, followed by "
        f"{len(questions)} questions about it. Answer each question using "
        "ONLY the information in the passage below. Do not use outside "
        "knowledge, genre convention, or a guess about how the story might "
        "continue. If the passage does not give you enough information to "
        "answer a question confidently, set can_answer to false and leave "
        "answer empty.\n\n"
        f"PASSAGE\n{passage_body}\n\nQUESTIONS\n{numbered}\n\n"
        "Return exactly this JSON shape and nothing else, with exactly "
        f"{len(questions)} entries in the same order as the questions: "
        '{"answers": [{"question": "...", "can_answer": true, "answer": '
        '"...", "reason": "..."}]}'
    )


def _parse_json_object(completion: Completion) -> dict[str, object]:
    """Extract a JSON object from a completion, classifying failure kind.

    ``finish_reason == "length"`` is the authoritative truncation signal
    (``providers/openrouter.py`` raises only on an *empty* truncation, so a
    partial one arrives here as ordinary, non-empty text with this
    finish_reason). Where a provider does not report ``finish_reason``, the
    same heuristic ``scripts/judge_books.py::_parse`` uses is the fallback:
    a reply that opens a JSON object but never closes it, or that fails
    ``json.loads`` while not ending in ``}``, is presumed cut off rather than
    malformed.

    Args:
        completion: The provider response to parse.

    Returns:
        The decoded JSON object.

    Raises:
        ProbeParseError: With ``kind="truncated"`` or ``kind="malformed"``.
    """
    raw = completion.text
    truncated_signal = completion.finish_reason == "length"
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        if truncated_signal or raw.lstrip().startswith("{"):
            msg = (
                f"reply cut off at {len(raw)} chars before any JSON object "
                f"closed (finish_reason={completion.finish_reason!r}); raise "
                "the completion token budget"
            )
            raise ProbeParseError(msg, kind="truncated")
        msg = f"no JSON object in reply: {raw[:120]!r}"
        raise ProbeParseError(msg, kind="malformed")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        # Same trap as judge_books._parse: the greedy `\{.*\}` closes on the
        # last *inner* brace a cut-off completion managed to emit, so the
        # decode error points at an unbalanced object that reads like a
        # formatting failure. finish_reason is checked first because it is
        # authoritative; the "did it end in a closing brace" heuristic is
        # only the fallback for a backend that reports no finish_reason.
        truncated = truncated_signal or not raw.rstrip().endswith("}")
        kind = "truncated" if truncated else "malformed"
        msg = f"could not parse JSON ({kind}, finish_reason={completion.finish_reason!r}): {exc}"
        raise ProbeParseError(msg, kind=kind) from exc
    if not isinstance(payload, dict):
        msg = f"JSON was not an object: {type(payload).__name__}"
        raise ProbeParseError(msg, kind="malformed")
    return payload


def _extract_questions(payload: dict[str, object]) -> list[str]:
    """Validate and return the ``questions`` list from a parsed payload.

    Args:
        payload: The decoded JSON object from the question model.

    Returns:
        Exactly :data:`_QUESTIONS_PER_PASSAGE` non-empty question strings.

    Raises:
        ProbeParseError: With ``kind="malformed"`` if the shape does not
            match: a complete, valid-JSON reply that simply did not follow
            the requested shape is a model failure, not a truncation.
    """
    questions = payload.get("questions")
    if (
        isinstance(questions, list)
        and len(questions) == _QUESTIONS_PER_PASSAGE
        and all(isinstance(q, str) and q.strip() for q in questions)
    ):
        return [q.strip() for q in questions]
    msg = (
        f"expected {_QUESTIONS_PER_PASSAGE} non-empty question strings under "
        f"'questions', got: {questions!r}"[:200]
    )
    raise ProbeParseError(msg, kind="malformed")


def _extract_answers(
    payload: dict[str, object], *, questions: Sequence[str]
) -> list[AnswerRecord]:
    """Validate and return the ``answers`` list from a parsed payload.

    Args:
        payload: The decoded JSON object from the answer model.
        questions: The questions that were asked, for the expected count.

    Returns:
        One :class:`AnswerRecord` per question, in the order asked.

    Raises:
        ProbeParseError: With ``kind="malformed"`` if the count or shape does
            not match what was asked.
    """
    answers = payload.get("answers")
    if not isinstance(answers, list) or len(answers) != len(questions):
        msg = f"expected {len(questions)} entries under 'answers', got: {answers!r}"[
            :200
        ]
        raise ProbeParseError(msg, kind="malformed")
    records: list[AnswerRecord] = []
    for question, entry in zip(questions, answers, strict=True):
        if not isinstance(entry, dict) or not isinstance(entry.get("can_answer"), bool):
            msg = f"malformed answer entry for {question!r}: {entry!r}"[:200]
            raise ProbeParseError(msg, kind="malformed")
        records.append(
            AnswerRecord(
                question=question,
                can_answer=entry["can_answer"],
                answer=str(entry.get("answer", "")),
                reason=str(entry.get("reason", "")),
            )
        )
    return records


def _load_storybook_nodes(path: Path) -> list[object] | None:
    """Read one JSON file and return its node list if it is a Storybook doc.

    The element type is deliberately ``object``, not ``dict[str, object]``:
    JSON decoded from an untrusted file can hold a list of anything (a
    string, a number, another list), and the caller still has to check each
    element before treating it as a node dict.

    Args:
        path: The file to read.

    Returns:
        The ``nodes`` list, or ``None`` when the file is not valid JSON, not
        an object, or its top-level ``nodes`` is not a list (skeleton catalog
        sidecar files such as ``*.contract.json`` and ``*.lineage.json`` all
        take this path, which is expected, not an error).
    """
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    nodes = doc.get("nodes")
    return nodes if isinstance(nodes, list) else None


def _story_id_and_band(path: Path) -> tuple[str, str | None]:
    """Return a story's declared id and age band without re-reading nodes.

    Args:
        path: The Storybook file.

    Returns:
        ``(story_id, age_band)``, falling back to the file stem for the id
        when the document carries none, and ``None`` for the band when
        undeclared.
    """
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return path.stem, None
    story_id = doc.get("id") if isinstance(doc, dict) else None
    metadata = doc.get("metadata") if isinstance(doc, dict) else None
    band = metadata.get("age_band") if isinstance(metadata, dict) else None
    return (
        story_id if isinstance(story_id, str) and story_id else path.stem,
        band if isinstance(band, str) else None,
    )


def _display_path(path: Path) -> str:
    """Render a path for reports without ever assuming it is repo-rooted.

    Report paths are cosmetic (they only help a human locate a story), so
    a path outside ``_REPO_ROOT`` (as every ``tmp_path``-based unit test
    fixture is) must render as something readable rather than raise. This
    also protects the pilot run itself: a corpus directory passed via
    ``--corpus`` with a symlink or a relative component that resolves
    outside the repo must not crash mid-scan over a purely cosmetic path.

    Args:
        path: The Storybook file path to render.

    Returns:
        The path relative to the repo root when possible, otherwise the
        path as given.
    """
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _round_robin_quotas(sizes: Sequence[int], *, max_passages: int) -> list[int]:
    """Divide a cap across stories one passage at a time, skipping exhausted ones.

    This is the fairness half of the sampler and nothing else: it decides HOW
    MANY passages each story contributes, never WHICH ones. Spending the cap a
    unit at a time (rather than as a flat ``cap // stories`` share) is what
    keeps a story with fewer eligible nodes than its share from stranding the
    remainder: whatever a short story cannot take is offered to the stories
    that still have nodes left.

    Args:
        sizes: Eligible passage counts per story, in the order the stories
            were first seen.
        max_passages: The total the quotas must not exceed.

    Returns:
        One quota per story, positionally aligned with ``sizes``, summing to
        ``min(max_passages, sum(sizes))``.
    """
    quotas = [0] * len(sizes)
    total = 0
    depth = 0
    while total < max_passages:
        took_any = False
        for index, size in enumerate(sizes):
            if depth >= size:
                continue
            quotas[index] += 1
            total += 1
            took_any = True
            if total >= max_passages:
                break
        if not took_any:
            break
        depth += 1
    return quotas


def _stride_positions(count: int, *, take: int) -> list[int]:
    """Choose ``take`` positions spread evenly across ``count`` items.

    Returns the midpoint of each of ``take`` equal blocks, so the chosen
    positions span the whole sequence and none of them is pinned to position
    0. Strictly increasing and distinct whenever ``take <= count``, because
    consecutive midpoints differ by ``count / take >= 1``.

    Args:
        count: How many items the sequence holds.
        take: How many positions to choose.

    Returns:
        The chosen positions, ascending. Every position when ``take >=
        count``, since there is then nothing to spread.
    """
    if take >= count:
        return list(range(count))
    return [((2 * index + 1) * count) // (2 * take) for index in range(take)]


def _stratified_stride_sample(
    by_story: dict[str, list[Passage]], *, max_passages: int
) -> list[Passage]:
    """Take a story-balanced slice that spans each story rather than its opening.

    Two properties, and they are separate defects if either is missing:

    * Across stories, the cap is divided round-robin, so a cap smaller than
      one book's node count cannot land entirely on that book.
    * Within a story, that story's share is taken at even intervals across
      its whole node list. The depth-interleaved walk this replaces satisfied
      the first property and silently violated the second: a 60-passage cap
      over 6 stories took node positions 0 to 9 of every story, so the
      published rate was the band's OPENING-PREFIX rate. Story openings are
      where referents are first introduced and where the least prior context
      exists, which is plausibly the worst case for an "answerable from this
      passage alone" probe, so a prefix figure is not merely a narrower
      figure than the one it was read as: it is biased in a known direction.

    Fully deterministic: the same corpus and cap always yield the same slice,
    which is the property a *stated* slice needs.

    Args:
        by_story: Eligible passages per story, in file order, keyed in the
            order the stories were first seen.
        max_passages: The most passages to take in total.

    Returns:
        The slice, at most ``max_passages`` long, interleaved across stories.
    """
    story_nodes = list(by_story.values())
    quotas = _round_robin_quotas(
        [len(nodes) for nodes in story_nodes], max_passages=max_passages
    )
    chosen = [
        [nodes[position] for position in _stride_positions(len(nodes), take=quota)]
        for nodes, quota in zip(story_nodes, quotas, strict=True)
    ]
    collected: list[Passage] = []
    depth = 0
    while True:
        took_any = False
        for picks in chosen:
            if depth >= len(picks):
                continue
            collected.append(picks[depth])
            took_any = True
        if not took_any:
            break
        depth += 1
    return collected


def collect_passages(
    corpus_dir: Path,
    *,
    pattern: str = "*.json",
    age_band: str | None = None,
    max_passages: int,
) -> tuple[list[Passage], CorpusStats]:
    """Walk a corpus directory and collect a slice STRATIFIED across stories.

    Every matching file is opened and every eligible node is grouped by story
    before the cap is applied, then the cap is divided round-robin across the
    stories (rather than greedily down the first one) and each story's share
    is taken at even intervals across that story's whole node list (rather
    than from its opening). See :func:`_stratified_stride_sample` and
    :data:`_SAMPLING_STRATEGY`.

    The greedy version this replaces broke out of the file loop as soon as the
    cap was reached, so a 60-passage slice of a 31-file corpus came entirely
    from ``the-backyard-treasure-map`` (62 eligible nodes, sorted first among
    the six stories in the band) and 27 of the 31 globbed files were never
    opened at all. The resulting rate was reported and read as an age-band
    figure while being a single-book figure confounded by one book's
    characters, setting and author, and the corpus counts said nothing that
    would reveal it. Scanning everything before capping also makes those
    counts describe the corpus rather than describing where the walk happened
    to stop.

    The depth-interleaved fix for THAT defect then introduced a second one of
    the same shape one level down: it spread the cap across stories but took
    positions 0 to 9 of each, so the figure was the band's opening-prefix
    rate while still reading as the band's rate. Striding within each story
    is what closes it.

    Args:
        corpus_dir: Directory to scan (non-recursive).
        pattern: Glob pattern within ``corpus_dir``.
        age_band: When given, only files whose ``metadata.age_band`` equals
            this string exactly are included.
        max_passages: Stop once this many passages have been collected.

    Returns:
        The collected passages and the counts describing what was skipped
        and why.
    """
    files = sorted(corpus_dir.glob(pattern))
    by_story: dict[str, list[Passage]] = {}
    skipped_non_storybook = 0
    skipped_age_band = 0
    nodes_seen = 0
    skipped_fill = 0
    skipped_empty = 0

    for path in files:
        story_id, band = _story_id_and_band(path)
        if age_band is not None and band != age_band:
            skipped_age_band += 1
            continue
        nodes = _load_storybook_nodes(path)
        if nodes is None:
            skipped_non_storybook += 1
            continue
        rel_path = _display_path(path)
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nodes_seen += 1
            node_id = node.get("id")
            body = node.get("body")
            if not isinstance(body, str) or not body.strip():
                skipped_empty += 1
                continue
            if body.strip().startswith(_FILL_PREFIX):
                skipped_fill += 1
                continue
            by_story.setdefault(story_id, []).append(
                Passage(
                    story_id=story_id,
                    story_path=rel_path,
                    node_id=node_id if isinstance(node_id, str) else "?",
                    body=body,
                )
            )

    passages = _stratified_stride_sample(by_story, max_passages=max_passages)
    stats = CorpusStats(
        files_scanned=len(files),
        files_skipped_non_storybook=skipped_non_storybook,
        files_skipped_age_band=skipped_age_band,
        nodes_seen=nodes_seen,
        nodes_skipped_fill=skipped_fill,
        nodes_skipped_empty=skipped_empty,
        passages_collected=len(passages),
        stories_available=len(by_story),
        stories_sampled=len({p.story_id for p in passages}),
    )
    return passages, stats


async def probe_passage(
    passage: Passage,
    *,
    question_provider: GenerationProvider,
    answer_provider: GenerationProvider,
    budget: BudgetTracker,
) -> NodeResult:
    """Ask one passage's questions, then try to answer them from the text.

    Two provider calls at most: question generation, then answering. The
    budget is checked again between them, because a passage whose question
    call happened to be the one that crossed the cap should not also spend on
    an answer call.

    Args:
        passage: The passage to probe.
        question_provider: The leg that generates questions.
        answer_provider: The leg that answers them; must be a different model
            from ``question_provider`` for the measurement to mean anything.
        budget: Shared spend tracker, mutated by this call.

    Returns:
        The outcome, successful or not.
    """
    q_completion = await question_provider.complete(
        system=_QUESTION_SYSTEM,
        prompt=_question_prompt(passage.body),
        max_tokens=_QUESTION_MAX_TOKENS,
    )
    budget.add(_cost_of(q_completion), vendor_cost_usd=q_completion.vendor_cost_usd)
    try:
        questions = _extract_questions(_parse_json_object(q_completion))
    except ProbeParseError as exc:
        return NodeResult(
            story_id=passage.story_id,
            node_id=passage.node_id,
            questions=None,
            answers=None,
            error_stage=f"question_generation:{exc.kind}",
            error_detail=str(exc),
        )

    if budget.exhausted:
        return NodeResult(
            story_id=passage.story_id,
            node_id=passage.node_id,
            questions=questions,
            answers=None,
            error_stage="budget_after_questions",
            error_detail=(
                f"budget cap ${budget.cap_usd} reached after generating "
                "questions; no answer call was made for this passage"
            ),
        )

    a_completion = await answer_provider.complete(
        system=_ANSWER_SYSTEM,
        prompt=_answer_prompt(passage.body, questions),
        max_tokens=_ANSWER_MAX_TOKENS,
    )
    budget.add(_cost_of(a_completion), vendor_cost_usd=a_completion.vendor_cost_usd)
    try:
        answers = _extract_answers(
            _parse_json_object(a_completion), questions=questions
        )
    except ProbeParseError as exc:
        return NodeResult(
            story_id=passage.story_id,
            node_id=passage.node_id,
            questions=questions,
            answers=None,
            error_stage=f"answering:{exc.kind}",
            error_detail=str(exc),
        )

    return NodeResult(
        story_id=passage.story_id,
        node_id=passage.node_id,
        questions=questions,
        answers=answers,
        error_stage=None,
    )


async def run_probe(
    passages: Sequence[Passage],
    *,
    question_provider: GenerationProvider,
    answer_provider: GenerationProvider,
    budget: BudgetTracker,
) -> list[NodeResult]:
    """Probe every passage in order, stopping new calls once budget is spent.

    Processed strictly sequentially (one ``await`` at a time, no
    ``asyncio.gather``): see the ``#CRITICAL: concurrency`` note on
    :class:`BudgetTracker` for why concurrent calls would make the cap only
    best-effort.

    Args:
        passages: The slice to probe, in order.
        question_provider: The question-generating leg.
        answer_provider: The answering leg.
        budget: Shared spend tracker.

    Returns:
        One :class:`NodeResult` per passage, including the passages skipped
        outright once the budget was already exhausted.
    """
    results: list[NodeResult] = []
    for index, passage in enumerate(passages):
        if budget.exhausted:
            results.append(
                NodeResult(
                    story_id=passage.story_id,
                    node_id=passage.node_id,
                    questions=None,
                    answers=None,
                    error_stage="budget",
                    error_detail=(
                        f"budget cap ${budget.cap_usd} reached before this "
                        f"passage ({index} of {len(passages)} attempted so "
                        "far); no calls made for it"
                    ),
                )
            )
            continue
        results.append(
            await probe_passage(
                passage,
                question_provider=question_provider,
                answer_provider=answer_provider,
                budget=budget,
            )
        )
    return results


def _story_breakdowns(results: Sequence[NodeResult]) -> list[StoryBreakdown]:
    """Group answered results by story and count each story's share.

    Args:
        results: Every node result from :func:`run_probe`.

    Returns:
        One :class:`StoryBreakdown` per story that produced answers, in the
        order the stories were first probed.
    """
    asked: dict[str, int] = {}
    unanswerable: dict[str, int] = {}
    probed: dict[str, int] = {}
    for result in results:
        if result.answers is None:
            continue
        probed[result.story_id] = probed.get(result.story_id, 0) + 1
        asked[result.story_id] = asked.get(result.story_id, 0) + len(result.answers)
        unanswerable[result.story_id] = unanswerable.get(result.story_id, 0) + sum(
            1 for a in result.answers if not a.can_answer
        )
    return [
        StoryBreakdown(
            story_id=story_id,
            passages_probed=count,
            questions_asked=asked[story_id],
            questions_unanswerable=unanswerable[story_id],
            unlabelled_unanswerable_rate=(
                unanswerable[story_id] / asked[story_id] if asked[story_id] else None
            ),
        )
        for story_id, count in probed.items()
    ]


def summarize(
    results: Sequence[NodeResult],
    *,
    budget: BudgetTracker,
    corpus_stats: CorpusStats,
    corpus_description: str,
) -> ProbeSummary:
    """Aggregate probe results into the report.

    Args:
        results: Every node result from :func:`run_probe`.
        budget: The spend tracker, read for the spend/cap figures.
        corpus_stats: Corpus-walk counts from :func:`collect_passages`.
        corpus_description: Human-readable description of the slice, for the
            report header. The selection RULE is not taken from here: it is
            recorded from :data:`_SAMPLING_STRATEGY`, so it cannot drift from
            what :func:`collect_passages` actually did.

    Returns:
        The aggregate summary, including a per-story breakdown so a
        single-story slice is visible in the artifact rather than only in the
        corpus counts. ``uniform_verdict_warning`` is set when every
        processed question landed on the same side (all answerable or all
        unanswerable), which is the signature of an environment fault, not a
        finding, per the trap this repository has already paid for once.
    """
    processed = [r for r in results if r.answers is not None]
    questions_asked = sum(len(r.answers or []) for r in processed)
    unanswerable = sum(
        1 for r in processed for a in (r.answers or []) if not a.can_answer
    )
    nodes_with_any = sum(
        1 for r in processed if any(not a.can_answer for a in (r.answers or []))
    )
    error_counts: dict[str, int] = {}
    for r in results:
        if r.error_stage:
            error_counts[r.error_stage] = error_counts.get(r.error_stage, 0) + 1

    rate = unanswerable / questions_asked if questions_asked else None
    avg_per_node = unanswerable / len(processed) if processed else None

    warning: str | None = None
    if processed and questions_asked:
        if unanswerable == 0:
            warning = (
                "every processed question was answerable (rate 0.0 across "
                f"{questions_asked} questions); a uniform verdict is the "
                "signature of an environment fault, not a finding -- verify "
                "the answer model actually saw the passage before trusting "
                "this as zero ambiguity."
            )
        elif unanswerable == questions_asked:
            warning = (
                "every processed question was UNanswerable (rate 1.0 across "
                f"{questions_asked} questions); a uniform verdict is the "
                "signature of an environment fault, not a finding -- verify "
                "the answer model actually received the passage text and "
                "that can_answer is not defaulting to false on parse."
            )

    return ProbeSummary(
        generated_at=datetime.now(UTC).isoformat(),
        corpus_description=corpus_description,
        # Not a parameter: :func:`collect_passages` is the only sampler this
        # script has, so the strategy is a property of the code that produced
        # the results rather than something a caller may assert about them.
        sampling_strategy=_SAMPLING_STRATEGY,
        question_model=_QUESTION_MODEL,
        answer_model=_ANSWER_MODEL,
        prompt_set_version=_PROMPT_SET_VERSION,
        corpus_stats=corpus_stats,
        nodes_processed=len(processed),
        nodes_skipped_budget=sum(
            1 for r in results if r.error_stage in {"budget", "budget_after_questions"}
        ),
        questions_asked=questions_asked,
        questions_unanswerable=unanswerable,
        unlabelled_unanswerable_rate=rate,
        avg_unanswerable_findings_per_node=avg_per_node,
        nodes_with_any_unanswerable=nodes_with_any,
        error_counts=error_counts,
        per_story=_story_breakdowns(results),
        budget_cap_usd=str(budget.cap_usd),
        spend_usd=str(budget.spent_usd),
        observed_spend_usd=str(budget.observed_usd),
        charged_usd=str(budget.charged_usd),
        budget_exhausted=budget.exhausted,
        calls_made=budget.calls,
        calls_reporting_vendor_cost=budget.calls_reporting_vendor_cost,
        uniform_verdict_warning=warning,
    )


def _node_result_to_dict(result: NodeResult) -> dict[str, object]:
    """Serialize one :class:`NodeResult` for the per-story JSON report."""
    return {
        "node_id": result.node_id,
        "questions": result.questions,
        "answers": (
            [dataclasses.asdict(a) for a in result.answers]
            if result.answers is not None
            else None
        ),
        "error_stage": result.error_stage,
        "error_detail": result.error_detail,
    }


def write_report(
    out_dir: Path,
    *,
    run_id: str,
    passages: Sequence[Passage],
    results: Sequence[NodeResult],
    summary: ProbeSummary,
) -> Path:
    """Write the per-story JSON reports and the aggregate summary.

    Args:
        out_dir: Destination directory (created if absent). Must already be
            verified gitignored by the caller (:func:`main` does this via
            ``_ensure_gitignored_destination`` before any spend); this
            function does not check again.
        run_id: This run's identity, supplied by the caller rather than read
            from the wall clock here, so the raw output directory and the
            tracked aggregate carry the SAME stamp and a test can assert on
            it deterministically.
        passages: The passages probed, aligned by position with ``results``,
            for grouping results back into their source stories.
        results: Every node result.
        summary: The aggregate summary.

    Returns:
        The run's directory (``run_id`` under ``out_dir``).
    """
    run_dir = out_dir / _validated_run_id(run_id)
    stories_dir = run_dir / "stories"
    stories_dir.mkdir(parents=True, exist_ok=True)

    by_story: dict[str, list[dict[str, object]]] = {}
    for passage, result in zip(passages, results, strict=True):
        by_story.setdefault(passage.story_id, []).append(_node_result_to_dict(result))

    for story_id, nodes in by_story.items():
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", story_id) or "story"
        (stories_dir / f"{safe_name}.json").write_text(
            json.dumps({"story_id": story_id, "nodes": nodes}, indent=2),
            encoding="utf-8",
        )

    summary_payload = dataclasses.asdict(summary)
    (run_dir / "summary.json").write_text(
        json.dumps(summary_payload, indent=2), encoding="utf-8"
    )
    return run_dir


def _validated_run_id(run_id: str) -> str:
    """Return ``run_id`` if it is safe to use as a single path component.

    Run ids reach the filesystem as directory and file names. This script
    generates its own, but the parameter exists precisely so a caller can
    supply one, and a caller-supplied id containing a separator or a parent
    reference would write outside the destination it was handed.

    Args:
        run_id: The candidate identity.

    Returns:
        The same string, unchanged.

    Raises:
        ValueError: When it is empty or contains anything outside
            ``[A-Za-z0-9._-]``.
    """
    if not run_id or not _RUN_ID_PATTERN.fullmatch(run_id):
        msg = (
            f"run id {run_id!r} is not a safe path component: expected a "
            "non-empty string of letters, digits, dots, underscores and "
            "hyphens"
        )
        raise ValueError(msg)
    return run_id


def write_tracked_aggregate(
    aggregate_dir: Path, summary: ProbeSummary, *, run_id: str
) -> Path:
    """Persist the run's AGGREGATE to a tracked, RUN-STAMPED path.

    The aggregate is written as ``summary-<run_id>.json`` and a fixed
    ``latest-summary.json`` POINTER is written beside it naming that file.
    The pointer is a convenience; the run-stamped file is the record. Writing
    the aggregate itself to a fixed name (as this did originally) means the
    next run silently destroys the previous run's finding, which is the same
    class of defect as not persisting it at all: an artifact that costs real
    money to reproduce must not be overwritable by the next invocation of the
    thing that produced it.

    The per-story reports and everything raw stay under the gitignored ``--out``
    tree: passages are copyrighted prose and model output is unreviewed text,
    and the plan is explicit that neither may be committed. The aggregate is a
    different artifact. It is the run's finding, it costs real money to
    reproduce, and until it was written somewhere tracked the rate, the model
    ids, the prompt version, the corpus slice and the observed cost existed
    only in ``tmp/``: clearing that directory would have destroyed the pilot
    and left the follow-up labelling work with nothing to be performed
    against.

    :class:`ProbeSummary` is safe to persist by construction: it carries
    counts, rates, ids and this script's own text, and no passage body,
    question, answer or model-authored string. The one field that could carry
    model output, ``NodeResult.error_detail``, is deliberately not part of it.

    Args:
        aggregate_dir: The tracked directory to write both files into.
        summary: The aggregate to persist.
        run_id: This run's identity, supplied by the caller so the filename
            is not produced by a wall-clock call inside the writer.

    Returns:
        The run-stamped path written (not the pointer).

    Raises:
        ValueError: When ``run_id`` is not a safe path component.
        SystemExit: When the destination is gitignored, via
            ``scripts/_paid_output.ensure_persistable``. A "durable" record
            that git is configured to ignore is the defect this call exists to
            prevent, and it is checked at write time as well as at start.
    """
    aggregate_path = aggregate_dir / f"summary-{_validated_run_id(run_id)}.json"
    ensure_persistable(aggregate_path)
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(
        json.dumps(dataclasses.asdict(summary), indent=2) + "\n", encoding="utf-8"
    )
    pointer = {
        "latest": aggregate_path.name,
        "run_id": run_id,
        "generated_at": summary.generated_at,
        "note": (
            "Pointer only. Every run's aggregate is kept beside this file as "
            "summary-<run_id>.json; this file names the most recent one and "
            "carries no findings of its own."
        ),
    }
    (aggregate_dir / _LATEST_POINTER_NAME).write_text(
        json.dumps(pointer, indent=2) + "\n", encoding="utf-8"
    )
    return aggregate_path


def _print_summary(summary: ProbeSummary) -> None:
    """Print the human-readable summary to stdout."""
    print("=" * 64)
    print("Comprehension Probe (C1) -- unlabelled pilot, not a precision figure")
    print("=" * 64)
    print(f"Question model: {summary.question_model}")
    print(f"Answer model:   {summary.answer_model}")
    print(f"Prompt set:     {summary.prompt_set_version}")
    print(f"Corpus:         {summary.corpus_description}")
    print(f"Sampling:       {summary.sampling_strategy}")
    stats = summary.corpus_stats
    print(
        f"Files scanned: {stats.files_scanned} "
        f"(skipped non-storybook: {stats.files_skipped_non_storybook}, "
        f"skipped age-band: {stats.files_skipped_age_band})"
    )
    print(
        f"Nodes seen: {stats.nodes_seen} "
        f"(skipped FILL: {stats.nodes_skipped_fill}, "
        f"skipped empty: {stats.nodes_skipped_empty}, "
        f"passages collected: {stats.passages_collected})"
    )
    print(
        f"Stories: {stats.stories_sampled} sampled of "
        f"{stats.stories_available} available in this slice"
    )
    print(f"Nodes processed: {summary.nodes_processed}")
    print(f"Nodes skipped for budget: {summary.nodes_skipped_budget}")
    print(f"Questions asked: {summary.questions_asked}")
    print(f"Questions unanswerable: {summary.questions_unanswerable}")
    print(f"Unlabelled unanswerable rate: {summary.unlabelled_unanswerable_rate}")
    print(
        f"Avg unanswerable findings per node: "
        f"{summary.avg_unanswerable_findings_per_node}"
    )
    print(
        f"Nodes with any unanswerable question: {summary.nodes_with_any_unanswerable}"
    )
    print(f"Error counts: {summary.error_counts}")
    print("Per story (story_id: probed, asked, unanswerable, rate):")
    for story in summary.per_story:
        print(
            f"  {story.story_id}: {story.passages_probed}, "
            f"{story.questions_asked}, {story.questions_unanswerable}, "
            f"{story.unlabelled_unanswerable_rate}"
        )
    print(
        f"Spend (vendor-reported, OBSERVED): ${summary.observed_spend_usd} "
        f"over {summary.calls_reporting_vendor_cost} of "
        f"{summary.calls_made} calls"
    )
    print(
        f"Spend (core/pricing.py table, ESTIMATE): ${summary.spend_usd} "
        f"over {summary.calls_made} calls"
    )
    print(
        f"Charged against the cap: ${summary.charged_usd} of "
        f"${summary.budget_cap_usd} (exhausted={summary.budget_exhausted})"
    )
    if summary.uniform_verdict_warning:
        print(f"WARNING: {summary.uniform_verdict_warning}")
    print(summary.note)


def _ensure_gitignored_destination(out_dir: Path) -> None:
    """Refuse to run unless git is actually configured to ignore ``out_dir``.

    This is the mirror image of ``scripts/_paid_output.py``'s
    ``ensure_persistable``: that guard exists because a paid measurement run's
    output must survive in git, so it refuses a destination git ignores. This
    script's plan is the opposite (raw model output must never be committed),
    so it refuses a destination git does *not* ignore.

    Checking is not optional here: ``out/reports/`` looks safe (an
    unassuming subdirectory of a mostly-scratch tree) and is not. Only
    specific subtrees under ``out/`` carry an ignore rule
    (``out/diversity/``, ``out/mutations/``, ``out/w7/arms/``), and
    ``out/reports/`` itself already holds tracked content. A default that
    merely looks gitignored is exactly the shape of cap-that-never-fires
    trap this repository has already paid for once; the fix is to verify
    the property being relied on, not to assume it from the path's name.

    Args:
        out_dir: The resolved ``--out`` destination.

    Raises:
        SystemExit: When git does not consider ``out_dir`` ignored.
    """
    if _is_ignored(out_dir):
        return
    message = (
        f"refusing to start: '{out_dir}' is NOT gitignored, so any raw model "
        "output this run writes could end up committed to this PUBLIC "
        "repository. Pass --out with a path under an already-ignored "
        "directory (for example tmp/, which is gitignored repo-wide), or add "
        "a specific ignore rule for the path you want first. This check "
        "exists because out/reports/ (an earlier default here) LOOKS "
        "gitignored and is not: only out/diversity/, out/mutations/, and "
        "out/w7/arms/ carry ignore rules under out/, and out/reports/ itself "
        "already holds tracked content."
    )
    raise SystemExit(message)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path, required=True, help="Directory of Storybook JSON files."
    )
    parser.add_argument(
        "--pattern",
        default="*.json",
        help="Glob pattern within --corpus (non-recursive). Default: *.json",
    )
    parser.add_argument(
        "--age-band",
        default=None,
        help="Only include documents whose metadata.age_band matches exactly.",
    )
    parser.add_argument("--max-passages", type=int, default=60)
    parser.add_argument("--budget-usd", type=str, default="5.00")
    parser.add_argument(
        "--out", type=Path, default=Path("tmp/comprehension-probe-reports")
    )
    parser.add_argument(
        "--aggregate-dir",
        type=Path,
        default=Path("out/reports/comprehension-probe"),
        help=(
            "Tracked DIRECTORY for the run's aggregate (counts, rates, model "
            "ids, prompt version, sampling strategy, per-story breakdown, "
            "observed spend). Written as summary-<run_id>.json so a later run "
            "cannot destroy this one's finding, with latest-summary.json "
            "beside it as a pointer. Must NOT be gitignored: raw output stays "
            "under --out, the finding does not."
        ),
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    corpus_dir = _resolve_within(args.corpus, label="--corpus")
    out_dir = _resolve_within(args.out, label="--out")
    aggregate_dir = _resolve_within(args.aggregate_dir, label="--aggregate-dir")
    env_path = _resolve_within(args.env_file, label="--env-file")

    # Stamped once, here, and passed to both writers: the raw output directory
    # and the tracked aggregate then carry the same identity, and neither
    # writer reads a clock a test would have to freeze.
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    _ensure_gitignored_destination(out_dir)
    # The exact file the run will write, not just its directory, so the
    # gitignore check at start covers the path the finding actually lands on.
    ensure_persistable(aggregate_dir / f"summary-{run_id}.json")
    _load_env_file(env_path)

    try:
        cap = Decimal(args.budget_usd)
    except (InvalidOperation, ValueError):
        print(
            f"Error: --budget-usd {args.budget_usd!r} is not a valid amount",
            file=sys.stderr,
        )
        return 2
    if cap <= 0:
        print("Error: --budget-usd must be positive", file=sys.stderr)
        return 2

    try:
        # Both halves of the cap's fail-closed behaviour, before a cent is
        # spent: the pair must be distinct (checked at import) and priced.
        _ensure_models_are_priced()
        settings = Settings()
        question_provider = build_openrouter_cost_reporting_leg(
            settings, _QUESTION_MODEL
        )
        answer_provider = build_openrouter_cost_reporting_leg(settings, _ANSWER_MODEL)
    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    passages, stats = collect_passages(
        corpus_dir,
        pattern=args.pattern,
        age_band=args.age_band,
        max_passages=args.max_passages,
    )
    if not passages:
        print(
            "Error: no passages collected from this corpus slice (every node "
            "was a <<FILL directive, blank, or excluded by --age-band); "
            f"stats={stats}",
            file=sys.stderr,
        )
        return 1

    corpus_description = (
        f"{args.corpus} (pattern={args.pattern!r}"
        + (f", age_band={args.age_band!r}" if args.age_band else "")
        + f", max_passages={args.max_passages}"
        + f", sampling={_SAMPLING_STRATEGY})"
    )
    print(
        f"Probing {len(passages)} passages with question model "
        f"{_QUESTION_MODEL} and answer model {_ANSWER_MODEL} "
        f"(cap ${cap})...",
        file=sys.stderr,
    )

    budget = BudgetTracker(cap_usd=cap)
    try:
        results = asyncio.run(
            run_probe(
                passages,
                question_provider=question_provider,
                answer_provider=answer_provider,
                budget=budget,
            )
        )
    except UnaccountableSpendError as exc:
        # No report is written on this path, deliberately. A run whose cost
        # accounting failed produced numbers whose spend cannot be stated, and
        # a report that looks like every other report is the wrong artifact to
        # leave behind for it.
        print(f"Error: {exc}", file=sys.stderr)
        print(
            f"Aborted after {budget.calls} call(s). No report written.",
            file=sys.stderr,
        )
        return 3
    summary = summarize(
        results,
        budget=budget,
        corpus_stats=stats,
        corpus_description=corpus_description,
    )
    run_dir = write_report(
        out_dir, run_id=run_id, passages=passages, results=results, summary=summary
    )
    written = write_tracked_aggregate(aggregate_dir, summary, run_id=run_id)
    _print_summary(summary)
    print(f"\nRaw report written to {run_dir} (gitignored; not committed).")
    print(f"Aggregate written to {written} (tracked; commit it).")
    print(
        f"Pointer updated at {aggregate_dir / _LATEST_POINTER_NAME} "
        "(names the aggregate above; carries no findings of its own)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
