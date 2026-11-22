"""The plan reviewer's provider call (WP-3.7, owner decisions D11 and D12).

Beside the other model reviewers. :func:`review_plan` reads one Story Plan and
the book graph it plans (no prose), asks a reviewer model that is not the
plan's writer for a verdict twice, combines the two answers, and lets the
deterministic checker's authority override a pass. The pure parts (verdict
model, parser, independence rule, combination, authority, sample draw,
suspension, pairing refusal) live in :mod:`cyo_adventure.storyplan.review`;
the prompt is ``generation/templates/plan_review.md``.

What this module adds, and why it is written the way it is:

* **Reasoning is an effort, and ``max_tokens`` sits well above it.** The
  OpenRouter ``effort`` form is the one that works on the Sonnet family; the
  token-budget form is not honored there (AL-856). With effort the model may
  spend most of ``max_tokens`` on reasoning and return no answer (AL-823,
  AL-847: a first pilot attempt at 8,000 spent every token reasoning), so the
  default ceiling is 24,000 and a ``length`` finish is recorded as ``unsure``,
  never retried: a retry would buy the same starvation again.
* **Low temperature, settable.** Two runs of one plan should differ only as
  far as sampling forces them to; the agreement figure is the measure.
* **Bounded concurrency, a hard spend cap.** A shared semaphore bounds calls in
  flight; a :class:`ReviewSpendCap` reserves each call's worst case before it
  is made and refuses the call when the cap would be crossed.
* **Per-call cost from ``usage``.** The cost-reporting leg asks OpenRouter for
  its own charge, which wins over the local estimate when present.
* **Nothing quotes story text.** Logs and messages carry plan ids, run
  numbers, verdicts, counts and rule ids.

Not wired into ``generation/worker.py`` or ``story_requests/authoring_plan.py``:
that is WP-2.4. :func:`settings_refusal` is the function the worker will call.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Final, cast

from cyo_adventure.core.exceptions import BusinessLogicError, ProviderError
from cyo_adventure.core.pricing import ModelPrice, estimate_cost, price_for
from cyo_adventure.generation.prompts import (
    build_plan_review_prompt,
    plan_review_prompt_hash,
)
from cyo_adventure.generation.reasoning import ReasoningControl, explicit_reasoning
from cyo_adventure.generation.usage import Completion, TokenUsage
from cyo_adventure.moderation.review_provider import (
    completion_finish_reason,
    completion_text,
)
from cyo_adventure.storyplan.review import (
    CheckerSummary,
    PlanReview,
    PlanVerdict,
    apply_checker_authority,
    assert_independent,
    combine_runs,
    parse_plan_verdict,
    plan_entry_ids,
    plan_for_review,
    render_book_graph,
    reviewer_refusal,
    unsure_verdict,
)
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings
    from cyo_adventure.generation.prompts import StagePrompt
    from cyo_adventure.moderation.review_provider import ReviewProvider
    from cyo_adventure.storybook.models import Storybook
    from cyo_adventure.storyplan.models import StoryPlan
    from cyo_adventure.validator.report import ValidationReport

__all__ = [
    "ASSUMED_PRICE",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_RUNS",
    "REVIEW_TIMEOUT_SECONDS",
    "PlanReviewResult",
    "ReviewCall",
    "ReviewSpendCap",
    "SpendCapReachedError",
    "StubReviewProvider",
    "build_plan_reviewer_provider",
    "build_review_prompt",
    "estimate_input_tokens",
    "format_checker_findings",
    "reasoning_from_settings",
    "review_plan",
    "settings_refusal",
]

logger = get_logger(__name__)

DEFAULT_RUNS: Final = 2
DEFAULT_MAX_TOKENS: Final = 24_000
REVIEW_TIMEOUT_SECONDS: Final = 600
"""Per-attempt timeout for one review call. A plan prompt is about 40,000 input
tokens and the answer is reasoning plus a short JSON object, so the 120-second
generation default is too short."""

_WORST_CASE_CHARS_PER_TOKEN: Final = 2
"""Deliberately low, so the worst-case input estimate is high. The pilot's
prompts measured about 2.0 to 2.1 characters per token (74,842 plan characters
in a 41,430-token prompt)."""
_TOKENS_PER_MTOK: Final = Decimal(1_000_000)
_MAX_CHECKER_MESSAGE_CHARS: Final = 300
_ATTEMPT_MULTIPLIER: Final = 3

ASSUMED_PRICE: Final = ModelPrice(
    input_usd_per_mtok=Decimal(3),
    output_usd_per_mtok=Decimal(15),
    as_of=date(2026, 11, 22),
    source="WP-3.7 brief: a reviewer at 3 USD in and 15 USD out per million tokens",
    note="used only when core/pricing.py has no row for the reviewer",
)
"""The price assumed for a reviewer model that has no ``core/pricing.py`` row."""


class SpendCapReachedError(BusinessLogicError):
    """The next review call could take spend over the hard cap."""

    def __init__(
        self, message: str, *, spent_usd: Decimal, budget_usd: Decimal
    ) -> None:
        """Record the figures behind the refusal.

        Args:
            message: What was refused.
            spent_usd: Spend plus in-flight reservations when refused.
            budget_usd: The cap.
        """
        super().__init__(
            message,
            rule="plan_reviewer_spend_cap",
            context={"spent_usd": str(spent_usd), "budget_usd": str(budget_usd)},
        )


def estimate_input_tokens(system: str, prompt: str) -> int:
    """Return a deliberately high estimate of a call's input tokens.

    Args:
        system: The system block.
        prompt: The user block.

    Returns:
        int: Characters divided by 2, plus one.
    """
    return (len(system) + len(prompt)) // _WORST_CASE_CHARS_PER_TOKEN + 1


@dataclass
class ReviewSpendCap:
    """A hard spend cap shared by every review call of one run.

    Each call reserves its worst case (the full ``max_tokens`` as output plus a
    high input estimate, at the reviewer's price) BEFORE it is made, and the
    reservation is replaced by the actual cost when the call returns. A call
    whose worst case would take spend plus open reservations over the budget
    is refused, so no single call can carry total spend past the cap. A failed
    call keeps its worst case times the attempts it may have been billed for.

    Attributes:
        budget_usd: The hard cap.
        price: The reviewer's price per million tokens.
        spent_usd: Settled spend.
        reserved_usd: Worst cases of calls in flight.
        refused: True once any call was refused.
    """

    budget_usd: Decimal
    price: ModelPrice
    spent_usd: Decimal = Decimal(0)
    reserved_usd: Decimal = Decimal(0)
    refused: bool = False

    def worst_case_usd(self, system: str, prompt: str, max_tokens: int) -> Decimal:
        """Return the most one call could cost.

        Args:
            system: The system block.
            prompt: The user block.
            max_tokens: The call's output ceiling.

        Returns:
            Decimal: USD at this cap's price.
        """
        return estimate_cost(
            self.price, estimate_input_tokens(system, prompt), max_tokens
        ).amount_usd

    def reserve(self, system: str, prompt: str, max_tokens: int) -> Decimal:
        """Reserve a call's worst case, or refuse it.

        There is no ``await`` between the check and the reservation, so two
        concurrent calls cannot both pass a check only one of them fits.

        Args:
            system: The system block.
            prompt: The user block.
            max_tokens: The call's output ceiling.

        Returns:
            Decimal: The reserved worst case, to pass to :meth:`settle`.

        Raises:
            SpendCapReachedError: When the reservation would cross the cap.
        """
        # #CRITICAL: payment/financial: the owner's spend ceiling is checked
        # BEFORE the call against settled spend plus every open reservation.
        # #VERIFY: test_plan_reviewer.py::test_cost_cap_stops_further_calls.
        worst = self.worst_case_usd(system, prompt, max_tokens)
        if self.spent_usd + self.reserved_usd + worst > self.budget_usd:
            self.refused = True
            msg = (
                f"review call refused: spent {self.spent_usd} + reserved "
                f"{self.reserved_usd} + worst case {worst} exceeds the budget "
                f"{self.budget_usd}"
            )
            raise SpendCapReachedError(
                msg,
                spent_usd=self.spent_usd + self.reserved_usd + worst,
                budget_usd=self.budget_usd,
            )
        self.reserved_usd += worst
        return worst

    def settle(
        self, reserved: Decimal, actual: Decimal | None, *, failed: bool
    ) -> None:
        """Replace a reservation with what the call actually cost.

        Args:
            reserved: The value :meth:`reserve` returned.
            actual: The call's cost, or None when unknown.
            failed: True when the call raised; its worst case is then charged
                for every attempt the adapter may have made.
        """
        self.reserved_usd -= reserved
        if failed:
            self.spent_usd += reserved * _ATTEMPT_MULTIPLIER
        else:
            self.spent_usd += reserved if actual is None else actual


@dataclass(frozen=True, slots=True)
class ReviewCall:
    """One model call (or the record of a call not made).

    Attributes:
        run: The run number, from 1.
        verdict: The parsed verdict of this run.
        finish_reason: The provider's finish reason, ``"<not-called>"`` when
            the call was refused or failed before an answer.
        model: The model id the provider reported, or the requested one.
        input_tokens: Reported prompt tokens, or None.
        output_tokens: Reported completion tokens (reasoning included), or None.
        reasoning_tokens: Reported reasoning tokens, or None.
        cost_usd: The vendor charge or the priced estimate, or None.
        latency_ms: Wall-clock milliseconds.
        called: False when no request was made (spend cap).
        error: The exception class name when the call raised, else None.
        raw_text: The model's answer, kept for evidence files only; never logged.
    """

    run: int
    verdict: PlanVerdict
    finish_reason: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: Decimal | None = None
    latency_ms: int = 0
    called: bool = True
    error: str | None = None
    raw_text: str = field(default="", repr=False)

    def to_dict(self, *, include_raw: bool = False) -> dict[str, object]:
        """Return the call as a JSON-ready dict.

        Args:
            include_raw: Whether to include the model's answer text.

        Returns:
            dict[str, object]: The fields.
        """
        data: dict[str, object] = {
            "run": self.run,
            "verdict": self.verdict.to_dict(),
            "finish_reason": self.finish_reason,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_usd": None if self.cost_usd is None else float(self.cost_usd),
            "latency_ms": self.latency_ms,
            "called": self.called,
            "error": self.error,
        }
        if include_raw:
            data["raw_text"] = self.raw_text
        return data


@dataclass(frozen=True, slots=True)
class PlanReviewResult:
    """Everything one plan's review produced.

    Attributes:
        plan_id: The plan's id.
        review: The final answer after the checker's authority.
        runs: Each run's call record (empty when the checker rejected the plan
            and no model was called).
        prompt_hash: The reviewer prompt's hash.
        reviewer_model: The configured reviewer.
        writer_model: The configured writer.
        spend_stopped: True when the spend cap refused a call.
    """

    plan_id: str
    review: PlanReview
    runs: tuple[ReviewCall, ...]
    prompt_hash: str
    reviewer_model: str
    writer_model: str | None
    spend_stopped: bool = False

    @property
    def cost_usd(self) -> Decimal:
        """Return the summed known cost of the runs.

        Returns:
            Decimal: USD; a lower bound when :attr:`cost_complete` is False.
        """
        return sum(
            (c.cost_usd for c in self.runs if c.cost_usd is not None), Decimal(0)
        )

    @property
    def cost_complete(self) -> bool:
        """Whether every call that was made has a known cost.

        Returns:
            bool: False when any made call reported neither a charge nor usage.
        """
        return all(c.cost_usd is not None for c in self.runs if c.called)

    @property
    def input_tokens(self) -> int:
        """Return the summed reported input tokens.

        Returns:
            int: Tokens (unknown counts contribute zero).
        """
        return sum(c.input_tokens or 0 for c in self.runs)

    @property
    def output_tokens(self) -> int:
        """Return the summed reported output tokens (reasoning included).

        Returns:
            int: Tokens (unknown counts contribute zero).
        """
        return sum(c.output_tokens or 0 for c in self.runs)

    @property
    def finish_reasons(self) -> tuple[str, ...]:
        """Return each run's finish reason.

        Returns:
            tuple[str, ...]: One per run.
        """
        return tuple(c.finish_reason for c in self.runs)

    def to_dict(self, *, include_raw: bool = False) -> dict[str, object]:
        """Return the result as a JSON-ready dict.

        Args:
            include_raw: Whether to include each run's answer text.

        Returns:
            dict[str, object]: The fields.
        """
        return {
            "plan_id": self.plan_id,
            "review": self.review.to_dict(),
            "runs": [c.to_dict(include_raw=include_raw) for c in self.runs],
            "prompt_hash": self.prompt_hash,
            "reviewer_model": self.reviewer_model,
            "writer_model": self.writer_model,
            "cost_usd": float(self.cost_usd),
            "cost_complete": self.cost_complete,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "finish_reasons": list(self.finish_reasons),
            "spend_stopped": self.spend_stopped,
        }


def format_checker_findings(report: ValidationReport) -> list[str]:
    """Render the checker's findings as one line each, for the prompt.

    Args:
        report: The report from ``check_plan``.

    Returns:
        list[str]: ``SEVERITY RULE node=.. choice=..: message``, errors first,
            each message capped. Entry ids only; the checker reads no prose.
    """
    lines: list[str] = []
    for finding in [*report.errors, *report.warnings]:
        parts = [finding.severity.value.upper(), finding.rule_id]
        if finding.node_id is not None:
            parts.append(f"node={finding.node_id}")
        if finding.choice_id is not None:
            parts.append(f"choice={finding.choice_id}")
        fact_id = cast("object", getattr(finding, "fact_id", None))
        if isinstance(fact_id, str):
            parts.append(f"fact={fact_id}")
        message = " ".join(finding.message.split())[:_MAX_CHECKER_MESSAGE_CHARS]
        lines.append(" ".join(parts) + f": {message}")
    return lines


def build_review_prompt(
    plan: StoryPlan, book: Storybook, checker: ValidationReport
) -> tuple[StagePrompt, frozenset[str]]:
    """Build the reviewer's prompt for one plan and list the entry ids it names.

    The plan is rendered without ``request`` and without ``provenance.notes``,
    ``approver`` and ``checks``; the request goes in its own untrusted fence;
    the book contributes only its graph. This is the only place the prompt is
    assembled, so the harness's cost projection and the live call see the same
    text.

    Args:
        plan: The parsed plan.
        book: The parsed book (only its graph is used).
        checker: The report from ``check_plan``.

    Returns:
        tuple[StagePrompt, frozenset[str]]: The prompt and every entry id of
            the plan (the ids a finding may name).
    """
    plan_dict = cast(
        "dict[str, object]",
        plan.model_dump(mode="json", exclude_none=True, exclude_defaults=True),
    )
    body, request = plan_for_review(plan_dict)
    prompt = build_plan_review_prompt(
        plan_json=json.dumps(body, separators=(",", ":"), ensure_ascii=True),
        request_json=json.dumps(request, indent=1, ensure_ascii=True),
        graph_text=render_book_graph(book),
        checker_findings=format_checker_findings(checker),
        band=plan.request.band.value,
    )
    return prompt, plan_entry_ids(plan_dict)


def reasoning_from_settings(settings: Settings) -> ReasoningControl:
    """Return the reviewer's reasoning control (the effort form).

    Args:
        settings: Application settings.

    Returns:
        ReasoningControl: ``effort`` from ``story_plan_reviewer_reasoning_effort``.
    """
    return ReasoningControl(effort=settings.story_plan_reviewer_reasoning_effort)


def settings_refusal(
    settings: Settings, *, writer_model: str | None = None
) -> str | None:
    """Return why the configured reviewer must not be used, or None.

    The function the plan worker (WP-2.4) calls before every plan: any
    non-None answer routes the job to the owner. Covers a disabled or
    suspended reviewer, a writer that is the reviewer (or its family), an
    unvalidated pairing and a pairing that no longer matches (a changed
    writer, reviewer or prompt voids it).

    Args:
        settings: Application settings.
        writer_model: The model that wrote the plan; defaults to
            ``story_plan_writer_model``.

    Returns:
        str | None: A reason code from
            :func:`cyo_adventure.storyplan.review.reviewer_refusal`, or None.
    """
    return reviewer_refusal(
        enabled=settings.story_plan_reviewer_enabled,
        suspended=settings.story_plan_reviewer_suspended,
        writer_model=writer_model or settings.story_plan_writer_model,
        reviewer_model=settings.story_plan_reviewer_model,
        prompt_hash=plan_review_prompt_hash(),
        validated_pairing=settings.story_plan_reviewer_validated_pairing,
    )


def build_plan_reviewer_provider(
    settings: Settings, model: str | None = None
) -> ReviewProvider:
    """Build the live reviewer leg: OpenRouter, vendor cost reported, low temperature.

    Args:
        settings: Application settings (the OpenRouter key and base url, and
            ``story_plan_reviewer_temperature``).
        model: The reviewer model; defaults to ``story_plan_reviewer_model``.

    Returns:
        ReviewProvider: The adapter. Reasoning is applied per call by
            :func:`review_plan` through ``explicit_reasoning``.

    Raises:
        ConfigurationError: When the OpenRouter key is not configured.
    """
    # #CRITICAL: external-resources: this builds a network-backed HTTP client;
    # a missing key raises by name at build time, not mid-run.
    # #VERIFY: build_openrouter_cost_reporting_leg raises ConfigurationError.
    from cyo_adventure.generation.provider import (  # noqa: PLC0415 - keeps the HTTP stack off this module's import path
        build_openrouter_cost_reporting_leg,
    )

    target = model or settings.story_plan_reviewer_model
    timed = settings.model_copy(
        update={
            "llm_timeout_seconds": max(
                settings.llm_timeout_seconds, REVIEW_TIMEOUT_SECONDS
            )
        }
    )
    return build_openrouter_cost_reporting_leg(
        timed, target, temperature=settings.story_plan_reviewer_temperature
    )


@dataclass
class StubReviewProvider:
    """A deterministic offline provider for ``--dry-run`` and tests.

    Returns the same configured verdict for every call, with token counts
    estimated from the prompt length, so a dry run exercises the whole harness
    and its cost arithmetic without a network call.

    Attributes:
        verdict: The verdict every call returns.
        model: The model id the usage reports.
        output_tokens: The completion tokens every call reports.
        calls: How many calls were made.
    """

    verdict: str = "pass"
    model: str = "stub/dry-run"
    output_tokens: int = 1_500
    calls: int = 0

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,  # noqa: ARG002 - the protocol's signature
    ) -> Completion:
        """Return the configured verdict as a completion.

        Args:
            system: The system block.
            prompt: The user block.
            max_tokens: Accepted for the protocol; unused.

        Returns:
            Completion: A ``stop`` completion with estimated usage.
        """
        self.calls += 1
        text = json.dumps({"verdict": self.verdict, "confidence": 0.5, "findings": []})
        return Completion(
            text=text,
            usage=TokenUsage(
                provider="stub",
                model=self.model,
                input_tokens=estimate_input_tokens(system, prompt),
                output_tokens=self.output_tokens,
                duration_ms=0,
                reasoning_tokens=0,
            ),
            finish_reason="stop",
        )


def _call_cost(
    returned: object, price: ModelPrice
) -> tuple[Decimal | None, TokenUsage | None]:
    """Return a call's cost and usage from whatever the provider returned.

    Args:
        returned: The provider's return value.
        price: The reviewer's price, used when the vendor reported no charge.

    Returns:
        tuple[Decimal | None, TokenUsage | None]: The vendor's charge when
            reported, else the priced estimate when both token counts are
            known, else None; and the usage record when there is one.
    """
    if not isinstance(returned, Completion):
        return None, None
    usage = returned.usage
    if returned.vendor_cost_usd is not None:
        return returned.vendor_cost_usd, usage
    estimate = estimate_cost(price, usage.input_tokens, usage.output_tokens)
    return (estimate.amount_usd if estimate.complete else None), usage


async def _one_run(  # noqa: PLR0913 - one run's inputs, all independent
    *,
    run: int,
    provider: ReviewProvider,
    system: str,
    prompt: str,
    max_tokens: int,
    reasoning: ReasoningControl,
    model: str,
    price: ModelPrice,
    known_entries: frozenset[str],
    spend_cap: ReviewSpendCap | None,
    semaphore: asyncio.Semaphore,
    plan_id: str,
) -> ReviewCall:
    """Make one review call and parse it; never raises on model or provider trouble.

    Args:
        run: The run number.
        provider: The reviewer leg.
        system: The system block.
        prompt: The user block.
        max_tokens: The output ceiling.
        reasoning: The reasoning control for this call.
        model: The requested model id, for the record.
        price: The reviewer's price.
        known_entries: The plan's entry ids.
        spend_cap: The shared cap, or None.
        semaphore: The shared concurrency bound.
        plan_id: The plan, for logs.

    Returns:
        ReviewCall: The record. A refused call, a provider error or an unusable
            answer is a call whose verdict is ``unsure``.
    """
    # #CRITICAL: timing-dependencies: a live call can hang or fail after the
    # adapter's own retries; either way this plan's run becomes `unsure` and the
    # review fails closed, it never becomes a pass and never aborts the batch.
    # #VERIFY: test_plan_reviewer.py::test_a_provider_error_is_unsure_not_a_crash.
    # #CRITICAL: concurrency: the semaphore bounds calls in flight across plans;
    # the cap reservation happens inside it with no await before the call.
    # #VERIFY: test_plan_reviewer.py::test_concurrency_is_bounded.
    async with semaphore:
        reserved = Decimal(0)
        if spend_cap is not None:
            try:
                reserved = spend_cap.reserve(system, prompt, max_tokens)
            except SpendCapReachedError:
                logger.warning("plan_review_spend_cap", plan=plan_id, run=run)
                return ReviewCall(
                    run=run,
                    verdict=unsure_verdict("spend_cap_reached"),
                    finish_reason="<not-called>",
                    model=model,
                    called=False,
                )
        started = time.monotonic()
        try:
            with explicit_reasoning(reasoning):
                returned = cast(
                    "object",
                    await provider.complete(
                        system=system, prompt=prompt, max_tokens=max_tokens
                    ),
                )
        except (ProviderError, TimeoutError) as exc:
            if spend_cap is not None:
                spend_cap.settle(reserved, None, failed=True)
            latency = int((time.monotonic() - started) * 1000)
            logger.warning(
                "plan_review_provider_error",
                plan=plan_id,
                run=run,
                error=type(exc).__name__,
            )
            return ReviewCall(
                run=run,
                verdict=unsure_verdict("provider_error"),
                finish_reason="<not-called>",
                model=model,
                latency_ms=latency,
                error=type(exc).__name__,
            )
    latency = int((time.monotonic() - started) * 1000)
    cost, usage = _call_cost(returned, price)
    if spend_cap is not None:
        spend_cap.settle(reserved, cost, failed=False)
    finish = completion_finish_reason(returned)
    text = completion_text(returned)
    verdict = parse_plan_verdict(
        text, finish_reason=finish, known_entries=known_entries
    )
    call = ReviewCall(
        run=run,
        verdict=verdict,
        finish_reason=finish,
        model=usage.model if usage is not None else model,
        input_tokens=None if usage is None else usage.input_tokens,
        output_tokens=None if usage is None else usage.output_tokens,
        reasoning_tokens=None if usage is None else usage.reasoning_tokens,
        cost_usd=cost,
        latency_ms=latency,
        raw_text=text or "",
    )
    logger.info(
        "plan_review_run",
        plan=plan_id,
        run=run,
        verdict=verdict.verdict,
        finish_reason=finish,
        findings=len(verdict.findings),
        reason_codes=list(verdict.reasons),
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
        reasoning_tokens=call.reasoning_tokens,
        cost_usd=None if cost is None else float(cost),
        model=call.model,
    )
    return call


async def review_plan(  # noqa: PLR0913 - the harness and the worker pass every one
    *,
    plan_id: str,
    plan: StoryPlan,
    book: Storybook,
    checker: ValidationReport,
    provider: ReviewProvider | None,
    writer_model: str | None,
    reviewer_model: str,
    reasoning: ReasoningControl,
    runs: int = DEFAULT_RUNS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    spend_cap: ReviewSpendCap | None = None,
    semaphore: asyncio.Semaphore | None = None,
    price: ModelPrice | None = None,
) -> PlanReviewResult:
    """Review one plan: the checker first, then the reviewer twice, then authority.

    When the deterministic checks reported an ERROR no model is called: the
    plan is rejected as ``checker_caught``. Otherwise the reviewer is called
    ``runs`` times concurrently (bounded by ``semaphore``), the verdicts are
    combined (a disagreement is ``unsure``) and the combined verdict stands.

    Args:
        plan_id: A stable id for the plan (its content hash in production).
        plan: The parsed plan.
        book: The parsed book the plan covers (only its graph is sent).
        checker: The report from ``check_plan`` for this plan and book.
        provider: The reviewer leg. May be None only when the checker rejected
            the plan, so no call is needed.
        writer_model: The model that wrote the plan.
        reviewer_model: The reviewer model.
        reasoning: The reasoning control applied to every call.
        runs: Calls per plan (the design is two).
        max_tokens: The output ceiling; keep it well above any reasoning.
        spend_cap: A hard cap shared across plans, or None.
        semaphore: A concurrency bound shared across plans; a private one of
            ``runs`` is used when None.
        price: The reviewer's price; resolved from ``core/pricing.py``, else
            :data:`ASSUMED_PRICE`.

    Returns:
        PlanReviewResult: The combined verdict, each run, cost and tokens.

    Raises:
        BusinessLogicError: When the reviewer is not independent of the writer
            (``plan_reviewer_not_independent``), or a call is needed and no
            provider was given.
    """
    # #CRITICAL: security: independence is enforced here, before any model is
    # called, so no caller can review a plan with its own writer by forgetting
    # a check.
    # #VERIFY: test_plan_reviewer.py::test_a_reviewer_equal_to_the_writer_makes_no_call.
    assert_independent(writer_model, reviewer_model)
    summary = CheckerSummary.from_rule_ids(
        (f.rule_id for f in checker.errors), warnings=len(checker.warnings)
    )
    prompt_hash = plan_review_prompt_hash()
    if summary.errors > 0:
        return PlanReviewResult(
            plan_id=plan_id,
            review=apply_checker_authority(None, summary),
            runs=(),
            prompt_hash=prompt_hash,
            reviewer_model=reviewer_model,
            writer_model=writer_model,
        )
    if provider is None:
        msg = "a review provider is required when the checker reported no ERROR"
        raise BusinessLogicError(msg, rule="plan_reviewer_no_provider")
    prompt, known = build_review_prompt(plan, book, checker)
    bound = semaphore if semaphore is not None else asyncio.Semaphore(max(1, runs))
    effective_price = price or price_for("openrouter", reviewer_model) or ASSUMED_PRICE
    calls = await asyncio.gather(
        *(
            _one_run(
                run=i + 1,
                provider=provider,
                system=prompt.system,
                prompt=prompt.user,
                max_tokens=max_tokens,
                reasoning=reasoning,
                model=reviewer_model,
                price=effective_price,
                known_entries=known,
                spend_cap=spend_cap,
                semaphore=bound,
                plan_id=plan_id,
            )
            for i in range(runs)
        )
    )
    verdicts = [c.verdict for c in calls]
    review = apply_checker_authority(
        combine_runs(verdicts),
        summary,
        run_verdicts=[v.verdict for v in verdicts],
    )
    logger.info(
        "plan_review_done",
        plan=plan_id,
        verdict=review.verdict,
        run_verdicts=list(review.run_verdicts),
        findings=len(review.findings),
        reviewer=reviewer_model,
    )
    return PlanReviewResult(
        plan_id=plan_id,
        review=review,
        runs=tuple(calls),
        prompt_hash=prompt_hash,
        reviewer_model=reviewer_model,
        writer_model=writer_model,
        spend_stopped=any(not c.called for c in calls),
    )
