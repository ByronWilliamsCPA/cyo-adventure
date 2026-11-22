#!/usr/bin/env python3
"""WP-2.3 paid smoke for Story Plan generation (owner-approved 2026-11-21).

Runs six 8-11 requests through the production plan path,
:func:`cyo_adventure.storyplan.generate.generate_story_plan`, the way
``generation/worker.py::_run_plan_generation`` calls it (cell match to a
retained shape, one pitch call, one plan call, up to two repairs), and writes
one evidence record per request under
``docs/planning/evidence/plan-generation-smoke-2026-11-21/runs/``.

Requests
--------

* Runs 1 to 5: the first five entries of
  ``docs/planning/evidence/short-request-panel/panel.json`` at band 8-11. The
  panel has no per-request band field: every request runs at both of the
  panel's bands, and its README orders jobs "panel order, band 8-11 then
  10-13", so the first five 8-11 jobs are P01 to P05. Length is short, as the
  panel fixes. The brief is built by the production
  ``story_requests/brief.py::brief_from_request`` from an in-memory request
  row; the shape is picked by the production
  ``story_requests/authoring_plan.py::_pick_shape`` among the cell's retained
  shapes, seeded by a deterministic request id (a UUID5 of the panel id) so a
  re-run draws the same shape.
* Run 6: panel request G03 at 8-11 medium, bound to the retained shape
  ``the-lantern-keepers-list`` (three threads) the way an admin
  ``skeleton_slug`` override binds it, so the thread rules SP-4 to SP-6 are
  exercised (AL-843).

Deviations from the worker, all declared
----------------------------------------

* **Stage 0 skipped.** There is no ``OPENAI_API_KEY`` in this environment; the
  owner approved running without it. The screen is the production
  ``classifier_screen(None)``, which with no key calls nothing and returns no
  finding; every result records the skip and how many pitch strings were
  offered to it. The SP-9 floors and the PII guard still screen each pitch.
* **Provider.** One OpenRouter leg for ``anthropic/claude-sonnet-5.5`` built by
  ``build_openrouter_cost_reporting_leg`` (the production leg builder plus
  OpenRouter's own per-call charge), not the production cascade. Reasoning is
  bounded explicitly through the provider's only supported setting,
  ``llm_effort="low"``, sent as OpenRouter's ``reasoning.effort``. The first
  attempt ran with ``llm_effort="off"`` (the production default, which omits
  the parameter) on the assumption that Sonnet 5.5 then does not think; it
  thought anyway (11,490 reasoning tokens on one plan call; kept as
  ``config-probe-effort-off.json``), so the budget is now explicit. Every
  call's reported reasoning tokens are recorded, and the driver stops if a
  call ends ``finish_reason="length"`` (the AL-823 symptom). Plan calls use
  the generator's own ``max_tokens`` of 32,000 (Sonnet 5.5 has no lower row in
  ``MODEL_OUTPUT_CAPS``, so ``resolve_output_cap`` keeps it); the pitch call
  uses its 2,000. The per-attempt timeout is 900 seconds, because a 21k-token
  plan is a long non-streamed call.
* **PII context.** Empty: these are panel texts, not a family's request.

Spend stop
----------

The provider stack is ``SpendGuard(MeteredProvider(leg))``; the PII guard that
``generate_story_plan`` adds sits outside both. Before every call the guard
adds a worst-case estimate for that call (prompt characters / 2 as input
tokens, plus the full ``max_tokens`` as output, at the Sonnet 5.5 price) to
the spend so far, and refuses the call by raising :class:`BudgetStopError` if the
sum would exceed the budget (8.00 USD by default). Spend so far is the larger
of the metered estimate (the ``MeteredProvider`` ledgers' tokens at that
price) and OpenRouter's own reported charges, plus, for any call that raised,
its worst case times the provider's attempt count (a failed call's billing is
unknown, so it is charged as if every attempt was billed in full). A stop ends
the whole smoke cleanly; completed runs keep their records.

Usage::

    uv run python scripts/smoke_plan_generation.py --dry-run
    uv run python scripts/smoke_plan_generation.py
    uv run python scripts/smoke_plan_generation.py --only 6

The API key is read by ``Settings`` from ``OPENROUTER_API_KEY`` and is never
printed, logged or written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.core.config import Settings
from cyo_adventure.core.pricing import ModelPrice, estimate_cost
from cyo_adventure.db.models import StoryRequest
from cyo_adventure.generation.metered import MeteredProvider
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_openrouter_cost_reporting_leg
from cyo_adventure.generation.providers._base import DEFAULT_MAX_RETRIES
from cyo_adventure.generation.reasoning import ReasoningControl
from cyo_adventure.generation.skeleton_match import candidates_for_cell
from cyo_adventure.generation.usage import UsageLedger
from cyo_adventure.story_requests.authoring_plan import _pick_shape
from cyo_adventure.story_requests.brief import brief_from_request
from cyo_adventure.storyplan.checks import check_plan
from cyo_adventure.storyplan.generate import (
    _assemble,
    _carries_pii,
    _decode_object,
    _load_errors,
    _normalize,
    classifier_screen,
    generate_story_plan,
    load_bound_shape,
    plan_request_from_brief,
)
from cyo_adventure.storyplan.models import StoryPlan
from cyo_adventure.storyplan.shapes import load_registry, shape_entry_for

MODEL: Final = "anthropic/claude-sonnet-5.5"
BAND: Final = "8-11"
STYLE: Final = "prose"
DEFAULT_BUDGET_USD: Final = Decimal("8.00")
MAX_REPAIRS: Final = 2  # generation/worker.py::_PLAN_MAX_REPAIRS
TIMEOUT_SECONDS: Final = 900
PANEL: Final = Path("docs/planning/evidence/short-request-panel/panel.json")
REASONING_BUDGET: list[int | None] = [None]  # set from --reasoning-budget
OUT: Final = Path("docs/planning/evidence/plan-generation-smoke-2026-11-21")
MEDIUM_SHAPE: Final = "the-lantern-keepers-list"
MEDIUM_REQUEST: Final = "G03"
CHARS_PER_TOKEN_WORST: Final = 2  # deliberately low, so the input estimate is high

# Sonnet 5.5 has no row in core/pricing.py. Its price is read off OpenRouter's
# own cost breakdown in the plan-review pilot (same model, same key):
# 0.08286 USD for 41,430 prompt tokens and 0.15713 USD for 15,713 completion
# tokens, that is 2.00 and 10.00 USD per million (the Sonnet 5 row's values).
PRICE: Final = ModelPrice(
    input_usd_per_mtok=Decimal(2),
    output_usd_per_mtok=Decimal(10),
    as_of=date(2026, 11, 21),
    source=(
        "OpenRouter cost_details in docs/planning/evidence/"
        "plan-review-pilot-2026-11-21/runs/lh_postfix.run1.json"
    ),
    note="script-local; Sonnet 5.5 has no core/pricing.py row",
)


class BudgetStopError(RuntimeError):
    """The next call could take total spend over the budget."""


class TruncationStopError(RuntimeError):
    """A call hit its max_tokens (AL-823): a configuration fault, not a result."""


def _usd(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001")))


@dataclass
class Spend:
    """Spend across the whole smoke, shared by every run's guard."""

    budget: Decimal
    ledgers: list[UsageLedger] = field(default_factory=list)
    vendor_usd: Decimal = Decimal(0)
    failed_charge_usd: Decimal = Decimal(0)

    def metered_usd(self) -> Decimal:
        total = Decimal(0)
        for ledger in self.ledgers:
            for usage in ledger.calls:
                total += estimate_cost(
                    PRICE, usage.input_tokens, usage.output_tokens
                ).amount_usd
        return total

    def spent_usd(self) -> Decimal:
        return max(self.metered_usd(), self.vendor_usd) + self.failed_charge_usd


def worst_case_usd(system: str, prompt: str, max_tokens: int) -> Decimal:
    in_tokens = (len(system) + len(prompt)) // CHARS_PER_TOKEN_WORST + 1
    return estimate_cost(PRICE, in_tokens, max_tokens).amount_usd


class SpendGuard:
    """Refuses a call that could cross the budget; records every call."""

    def __init__(self, inner: MeteredProvider, spend: Spend) -> None:
        self._inner = inner
        self._spend = spend
        self.calls: list[dict[str, Any]] = []
        self.texts: list[str | None] = []

    # generate_story_plan reads `model` for resolve_output_cap, and the worker
    # labels provenance from it, so both labels are forwarded.
    @property
    def model(self) -> str | None:
        return self._inner.model

    @property
    def name(self) -> str | None:
        return self._inner.name

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Any:
        # #CRITICAL: payment/financial: the owner's hard stop is checked BEFORE
        # the call, against spend so far plus this call's worst case, so no
        # single call can carry total spend over the budget.
        # #VERIFY: --dry-run prints every call's worst case; the README records
        # the spend after each run.
        index = len(self.calls)
        worst = worst_case_usd(system, prompt, max_tokens)
        spent = self._spend.spent_usd()
        record: dict[str, Any] = {
            "index": index,
            "kind": "pitch" if index == 0 else f"plan_{index}",
            "max_tokens": max_tokens,
            "prompt_chars": len(system) + len(prompt),
            "worst_case_usd": _usd(worst),
            "spent_before_usd": _usd(spent),
        }
        if spent + worst > self._spend.budget:
            record["refused"] = "spend stop"
            self.calls.append(record)
            self.texts.append(None)
            msg = (
                f"call {index} refused: spent {_usd(spent)} + worst case "
                f"{_usd(worst)} > budget {self._spend.budget}"
            )
            raise BudgetStopError(msg)
        started = time.monotonic()
        try:
            result = await self._inner.complete(
                system=system, prompt=prompt, max_tokens=max_tokens
            )
        except Exception as exc:
            charge = worst * DEFAULT_MAX_RETRIES
            self._spend.failed_charge_usd += charge
            record.update(
                error=f"{type(exc).__name__}: {str(exc)[:400]}",
                latency_s=round(time.monotonic() - started, 1),
                charged_as_failed_usd=_usd(charge),
            )
            self.calls.append(record)
            self.texts.append(None)
            raise
        usage = result.usage
        estimate = estimate_cost(PRICE, usage.input_tokens, usage.output_tokens)
        if result.vendor_cost_usd is not None:
            self._spend.vendor_usd += result.vendor_cost_usd
        record.update(
            model=usage.model,
            provider=usage.provider,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            finish_reason=result.finish_reason,
            cost_estimate_usd=_usd(estimate.amount_usd),
            vendor_cost_usd=(
                None if result.vendor_cost_usd is None else _usd(result.vendor_cost_usd)
            ),
            latency_s=round(time.monotonic() - started, 1),
            provider_duration_ms=usage.duration_ms,
            response_chars=len(result.text),
        )
        self.calls.append(record)
        self.texts.append(result.text)
        if result.finish_reason == "length":
            msg = (
                f"call {index} stopped at max_tokens ({usage.reasoning_tokens} "
                "reasoning tokens)"
            )
            raise TruncationStopError(msg)
        return result


@dataclass(frozen=True)
class RunSpec:
    n: int
    request_id: str
    text: str
    length: str
    shape_override: str | None
    note: str


def run_specs() -> list[RunSpec]:
    panel = json.loads(PANEL.read_text(encoding="utf-8"))
    requests = panel["requests"]
    specs = [
        RunSpec(
            n=i + 1,
            request_id=r["id"],
            text=r["text"],
            length="short",
            shape_override=None,
            note="panel order, band 8-11 first (panel README); length short as fixed",
        )
        for i, r in enumerate(requests[:5])
    ]
    medium = next(r for r in requests if r["id"] == MEDIUM_REQUEST)
    specs.append(
        RunSpec(
            n=6,
            request_id=medium["id"],
            text=medium["text"],
            length="medium",
            shape_override=MEDIUM_SHAPE,
            note=(
                "panel text at medium, bound to the three-thread shape by "
                "override so SP-4 to SP-6 run (AL-843)"
            ),
        )
    )
    return specs


def build_job(spec: RunSpec) -> tuple[Any, Any, dict[str, Any]]:
    """Return (request side, shape view, shape record) as the worker builds them."""
    row = StoryRequest(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"wp23-smoke:{spec.request_id}:{BAND}"),
        request_text=spec.text,
        age_band=BAND,
        length=spec.length,
        narrative_style=STYLE,
    )
    registry = load_registry()
    in_cell = candidates_for_cell(BAND, spec.length, STYLE)
    retained = [entry for entry in registry.shapes if entry.id in set(in_cell)]
    if spec.shape_override is not None:
        entry = shape_entry_for(registry, spec.shape_override)
        if entry is None:
            msg = f"{spec.shape_override} is not retained"
            raise SystemExit(msg)
        selection = "override (admin skeleton_slug path)"
    else:
        entry = _pick_shape(retained, row)
        selection = "cell pick (authoring_plan._pick_shape, seeded by request id)"
    view = load_bound_shape(entry.id, entry.hash)
    brief = brief_from_request(row, None)
    request = plan_request_from_brief(brief, view)
    shape = {
        "id": entry.id,
        "hash": entry.hash,
        "selection": selection,
        "cell": {"band": BAND, "length": spec.length, "style": STYLE},
        "cell_candidates": in_cell,
        "retained_in_cell": [e.id for e in retained],
        "nodes": len(view.book.nodes),
        "choices": sum(len(node.choices) for node in view.book.nodes),
        "variables": len(view.book.variables),
        "request_seed_id": str(row.id),
    }
    return request, view, shape


def replay_attempt(view: Any, request: Any, pitch: Any, text: str) -> dict[str, Any]:
    """Re-run the generator's load and check steps on one plan answer (no calls)."""
    decoded, problem = _decode_object(text)
    if decoded is None:
        return {"loaded": False, "unparseable": problem, "response_text": text}
    sections, dropped = _normalize(view, view.to_real(decoded))
    if _carries_pii(sections, PiiContext(child_names=frozenset())):
        return {"loaded": False, "personal_information": True}
    document = _assemble(
        view, sections, request=request, pitch=pitch, model_label=MODEL, note="replay"
    )
    try:
        plan = StoryPlan.model_validate(document)
    except PydanticValidationError as exc:
        return {
            "loaded": False,
            "dropped_keys": dropped,
            "load_errors": _load_errors(view, exc),
            "response_text": text,
        }
    report = check_plan(plan, view.book)
    return {
        "loaded": True,
        "dropped_keys": dropped,
        "ok": report.ok,
        "errors_by_rule": dict(
            sorted(Counter(f.rule_id for f in report.errors).items())
        ),
        "warnings_by_rule": dict(
            sorted(Counter(f.rule_id for f in report.warnings).items())
        ),
        "findings": [f.to_dict() for f in report.findings],
    }


async def run_one(spec: RunSpec, leg: Any, spend: Spend) -> dict[str, Any]:
    request, view, shape = build_job(spec)
    ledger = UsageLedger()
    spend.ledgers.append(ledger)
    guard = SpendGuard(MeteredProvider(leg, ledger=ledger), spend)
    offered: list[int] = []
    production_screen = classifier_screen(None)

    async def screen(items: Any) -> Any:
        offered.append(len(items))
        return await production_screen(items)

    record: dict[str, Any] = {
        "run": spec.n,
        "request": {
            "id": spec.request_id,
            "source": f"{PANEL.as_posix()} requests[id={spec.request_id}]",
            "text": spec.text,
            "band": BAND,
            "length": spec.length,
            "style": STYLE,
            "selection_note": spec.note,
        },
        "shape": shape,
        "model": MODEL,
        "reasoning": "explicit: llm_effort='low' sent as reasoning.effort",
        "max_repairs": MAX_REPAIRS,
        "brief": request.brief,
    }
    started = time.monotonic()
    spent_before = spend.spent_usd()
    stop: str | None = None
    result = None
    try:
        result = await generate_story_plan(
            request,
            view,
            guard,
            pii=PiiContext(child_names=frozenset()),
            screen=screen,
            max_repairs=MAX_REPAIRS,
            model_label=guard.model,
            reasoning=(
                ReasoningControl(max_tokens=REASONING_BUDGET[0])
                if REASONING_BUDGET[0]
                else None
            ),
        )
    except (BudgetStopError, TruncationStopError) as exc:
        stop = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # recorded, then the smoke continues
        stop = f"error: {type(exc).__name__}: {str(exc)[:400]}"
    record["stage0"] = {
        "status": "skipped",
        "reason": (
            "no OPENAI_API_KEY in this environment (owner-approved skip, "
            "2026-11-21); production classifier_screen(None) ran and called nothing"
        ),
        "pitch_strings_offered": sum(offered),
    }
    record["calls"] = guard.calls
    record["wall_seconds"] = round(time.monotonic() - started, 1)
    record["stopped"] = stop
    if result is not None:
        record["story_plan_status"] = result.status
        record["attempts"] = result.plan_calls
        record["stage_log"] = result.stage_log
        record["pitches"] = [p.to_report() for p in result.pitches]
        chosen = next((p for p in result.pitches if p.passed), None)
        attempts = []
        if chosen is not None and chosen.pitch is not None:
            for number, text in enumerate(guard.texts[1:], start=1):
                entry: dict[str, Any] = {"attempt": number}
                if text is None:
                    entry["loaded"] = False
                    entry["no_answer"] = True
                else:
                    entry.update(replay_attempt(view, request, chosen.pitch, text))
                attempts.append(entry)
        record["attempt_findings"] = attempts
        final_errors = 0 if result.checks is None else len(result.checks.errors)
        replay_errors = (
            sum(attempts[-1].get("errors_by_rule", {}).values()) if attempts else 0
        )
        record["replay_consistent"] = replay_errors == final_errors
        record["final_checks"] = (
            None if result.checks is None else result.checks.to_dict()
        )
        record["load_errors"] = result.load_errors
        record["plan"] = result.plan_json
    else:
        record["story_plan_status"] = None
        record["attempts"] = max(len(guard.calls) - 1, 0)
    done = [c for c in guard.calls if "input_tokens" in c]
    record["totals"] = {
        "calls": len(guard.calls),
        "input_tokens": sum(c["input_tokens"] or 0 for c in done),
        "output_tokens": sum(c["output_tokens"] or 0 for c in done),
        "reasoning_tokens": sum(c["reasoning_tokens"] or 0 for c in done),
        "cost_estimate_usd": round(sum(c["cost_estimate_usd"] for c in done), 6),
        "vendor_cost_usd": round(sum(c["vendor_cost_usd"] or 0 for c in done), 6),
        "provider_seconds": round(
            sum(c["latency_s"] for c in guard.calls if "latency_s" in c), 1
        ),
    }
    record["budget"] = {
        "budget_usd": float(spend.budget),
        "spent_before_usd": _usd(spent_before),
        "spent_after_usd": _usd(spend.spent_usd()),
    }
    return record


def dry_run(specs: list[RunSpec]) -> int:
    """Print each request's shape and plan-call worst case; no network."""
    from cyo_adventure.generation.prompts import build_plan_prompt  # noqa: PLC0415

    total = Decimal(0)
    for spec in specs:
        request, view, shape = build_job(spec)
        shape_json = json.dumps(view.render(), separators=(",", ":"))
        pitch = dict.fromkeys(
            ("hero", "want", "obstacle", "stake", "ending_kind"), "x" * 40
        )
        prompt = build_plan_prompt(shape_json, pitch, request.brief)
        first = worst_case_usd(prompt.system, prompt.user, 32_000)
        # A repair carries the previous plan too (about 32k tokens at worst).
        repair = estimate_cost(
            PRICE,
            (len(prompt.system) + len(prompt.user)) // CHARS_PER_TOKEN_WORST + 64_000,
            32_000,
        ).amount_usd
        run_worst = Decimal("0.05") + first + 2 * repair
        total += run_worst
        print(
            f"run {spec.n} {spec.request_id} {shape['id']} nodes={shape['nodes']} "
            f"choices={shape['choices']} vars={shape['variables']} "
            f"plan_prompt_chars={len(prompt.system) + len(prompt.user)} "
            f"worst_first={_usd(first)} worst_run={_usd(run_worst)}"
        )
    print(f"worst case, every run using all repairs: {_usd(total)} USD")
    return 0


async def main_async(args: argparse.Namespace) -> int:
    specs = run_specs()
    REASONING_BUDGET[0] = args.reasoning_budget
    if args.only:
        specs = [s for s in specs if s.n in set(args.only)]
    if args.dry_run:
        return dry_run(specs)
    settings = Settings(
        generation_provider="openrouter",
        llm_effort="low",
        llm_timeout_seconds=TIMEOUT_SECONDS,
    )
    leg = build_openrouter_cost_reporting_leg(settings, MODEL)
    spend = Spend(budget=Decimal(args.budget) - Decimal(args.already_spent))
    runs_dir = Path(args.out) / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        print(f"run {spec.n} ({spec.request_id}) starting", flush=True)
        record = await run_one(spec, leg, spend)
        path = runs_dir / f"{spec.n}.json"
        path.write_text(
            json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(
            f"run {spec.n}: status={record['story_plan_status']} "
            f"attempts={record['attempts']} stop={record['stopped']} "
            f"cost={record['totals']['cost_estimate_usd']} "
            f"vendor={record['totals']['vendor_cost_usd']} "
            f"spent={record['budget']['spent_after_usd']}",
            flush=True,
        )
        if record["stopped"] and record["stopped"].startswith(
            ("BudgetStopError", "TruncationStopError")
        ):
            print("smoke stopped", flush=True)
            return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--reasoning-budget",
        type=int,
        default=None,
        help="explicit reasoning token budget for every pitch and plan call",
    )
    parser.add_argument(
        "--out", default=str(OUT), help="evidence directory (runs/ is written under it)"
    )
    parser.add_argument("--only", type=int, nargs="*")
    parser.add_argument("--budget", default=str(DEFAULT_BUDGET_USD))
    parser.add_argument(
        "--already-spent",
        default="0",
        help="USD already spent by earlier invocations against the same budget",
    )
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
