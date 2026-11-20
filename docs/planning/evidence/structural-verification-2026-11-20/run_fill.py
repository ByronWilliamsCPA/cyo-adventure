"""Drive one production-shaped skeleton fill and record everything it cost.

Run from inside a worktree so ``cyo_adventure`` (and with it the prompt
templates) resolves to THAT worktree's code; the OLD arm runs from
``.worktrees/prompt-baseline`` and the NEW arm from ``.worktrees/verify-runs``.
This script holds no prompt logic of its own: it calls the production
``build_provider`` (the OpenRouter cascade: deepseek-v4-pro on its priced
``azure/us`` pin, then claude-sonnet-4.6) and the production ``fill_skeleton``,
exactly as ``generation/worker.py::_run_skeleton_fill`` does, with three
declared deviations:

1. ``stage1_gate="skipped"`` (the worker passes ``"required"``). The Stage 1
   fidelity check is a second LLM review whose verdict can trigger repairs, so
   it would add an uncontrolled variable to a prompt A/B; the 2026-08-21
   structural round skipped it for the same reason.
2. For a contract-bearing skeleton the binding is the contract's own
   ``default_binding`` rendered deterministically (the worker asks an LLM
   binder, ``interpret_and_bind``). Holding the binding fixed is what lets both
   arms receive byte-identical bound skeletons.
3. ``--force-cap`` monkeypatches ``orchestrator.resolve_output_cap`` so a
   skeleton that fits one-shot on deepseek-v4-pro takes the chunked path. It is
   used for exactly one fill, to exercise the per-batch merge notes.

Every call is recorded (rendered system and user prompt, raw reply, serving
provider and model, tokens, wall clock) so the raw model output can be checked
before ``normalize_filled_story`` restores frozen fields.

The OpenRouter key is read from the environment by ``Settings`` and is never
printed or written.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from importlib.resources import files
from pathlib import Path
from typing import Any

import httpx

import cyo_adventure
from cyo_adventure.core.config import Settings
from cyo_adventure.generation import orchestrator
from cyo_adventure.generation.binding import (
    load_contract_for,
    personalizable_slot_ids,
    render_bound_skeleton,
)
from cyo_adventure.generation.cost import estimate_run_cost
from cyo_adventure.generation.metered import MeteredProvider
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.generation.usage import UsageLedger
from cyo_adventure.storybook.reinsertion import reinsert_storybook
from cyo_adventure.utils.logging import setup_logging
from cyo_adventure.validator.slots import validate_slot_bindings


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _template_fingerprint() -> dict[str, str]:
    root = files("cyo_adventure.generation") / "templates"
    out = {
        name: _sha((root / name).read_text(encoding="utf-8"))
        for name in (
            "fill.md",
            "fill_bound.md",
            "fill_subset.md",
            "fill_subset_bound.md",
            "drafting_guide.md",
            "reading_level_repair.md",
            "fidelity_repair.md",
        )
    }
    prompts_py = Path(cyo_adventure.__file__).parent / "generation" / "prompts.py"
    out["prompts.py"] = _sha(prompts_py.read_text(encoding="utf-8"))
    return out


def _key_usage() -> float | None:
    """OpenRouter's own cumulative spend for this key, in USD."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        resp = httpx.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        usage = resp.json().get("data", {}).get("usage")
    except (httpx.HTTPError, ValueError):
        return None
    return float(usage) if isinstance(usage, (int, float)) else None


class Recorder:
    """Record every completion; forward ``model``/``name`` like the cascade."""

    def __init__(self, inner: Any, call_dir: Path) -> None:
        self.inner = inner
        self.call_dir = call_dir
        self.calls: list[dict[str, object]] = []

    @property
    def model(self) -> object:
        return getattr(self.inner, "model", None)

    @property
    def name(self) -> object:
        return getattr(self.inner, "name", None)

    @property
    def resolved_provider(self) -> object:
        return getattr(self.inner, "resolved_provider", None)

    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> Any:
        index = len(self.calls)
        stem = self.call_dir / f"call-{index:02d}"
        (stem.with_suffix(".system.txt")).write_text(system, encoding="utf-8")
        (stem.with_suffix(".prompt.txt")).write_text(prompt, encoding="utf-8")
        started = time.monotonic()
        record: dict[str, object] = {
            "index": index,
            "max_tokens": max_tokens,
            "system_chars": len(system),
            "prompt_chars": len(prompt),
            "system_sha": _sha(system),
            "prompt_sha": _sha(prompt),
        }
        try:
            result = await self.inner.complete(
                system=system, prompt=prompt, max_tokens=max_tokens
            )
        except Exception as exc:
            record.update(
                error=f"{type(exc).__name__}: {str(exc)[:400]}",
                wall_s=round(time.monotonic() - started, 1),
            )
            self.calls.append(record)
            raise
        (stem.with_suffix(".response.txt")).write_text(result.text, encoding="utf-8")
        usage = result.usage
        record.update(
            wall_s=round(time.monotonic() - started, 1),
            provider=usage.provider,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            finish_reason=result.finish_reason,
            response_chars=len(result.text),
        )
        self.calls.append(record)
        return result


async def _run(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    call_dir = out / "calls"
    call_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(level="INFO", json_logs=True)

    skeleton_path = Path(args.skeleton).resolve()
    skeleton: dict[str, object] = json.loads(skeleton_path.read_text("utf-8"))
    brief: dict[str, object] = json.loads(Path(args.brief).read_text("utf-8"))

    contract = load_contract_for(skeleton_path, skeleton)
    slot_bindings: dict[str, str] | None = None
    to_fill = skeleton
    if contract is not None:
        slot_bindings = dict(contract.default_binding)
        violations = validate_slot_bindings(contract, slot_bindings, is_default=True)
        if violations:
            print(json.dumps({"binding_violations": [str(v) for v in violations]}))
            return 3
        to_fill = render_bound_skeleton(
            skeleton, slot_bindings, personalizable_slot_ids(contract)
        )
    bound_sha = _sha(json.dumps(to_fill, sort_keys=True))

    if args.force_cap is not None:
        forced = int(args.force_cap)

        def _forced_cap(model: object, **_: object) -> int:
            del model
            return forced

        orchestrator.resolve_output_cap = _forced_cap  # type: ignore[assignment]

    meta: dict[str, object] = {
        "label": args.label,
        "arm": args.arm,
        "skeleton": str(skeleton_path.name),
        "brief_sha": _sha(json.dumps(brief, sort_keys=True)),
        "bound_skeleton_sha": bound_sha,
        "bound": slot_bindings is not None,
        "force_cap": args.force_cap,
        "cyo_adventure_path": str(Path(cyo_adventure.__file__).parent),
        "templates": _template_fingerprint(),
        "stage1_gate": "skipped",
    }
    print(json.dumps({"start": meta}), flush=True)

    settings = Settings(generation_provider="openrouter")
    meta["primary_model"] = settings.openrouter_model
    meta["fallback_model"] = settings.openrouter_fallback_model
    cascade = build_provider(settings)
    recorder = Recorder(cascade, call_dir)
    ledger = UsageLedger()
    provider = MeteredProvider(recorder, ledger=ledger)
    pii = PiiContext(child_names=frozenset())

    usage_before = _key_usage()
    started = time.monotonic()
    error: str | None = None
    outcome = None
    try:
        outcome = await orchestrator.fill_skeleton(
            to_fill,
            brief,
            provider,
            pii,
            settings=settings,
            stage1_gate="skipped",
            slot_bindings=slot_bindings,
        )
    except Exception as exc:  # recorded as a result, not hidden
        error = f"{type(exc).__name__}: {str(exc)[:600]}"
    elapsed = round(time.monotonic() - started, 1)
    await asyncio.sleep(5)  # let the provider's usage counter settle
    usage_after = _key_usage()

    final = None
    if outcome is not None and outcome.storybook is not None:
        final = outcome.storybook
        if slot_bindings is not None:
            final = reinsert_storybook(to_fill, outcome.storybook).document
        (out / "filled.json").write_text(
            json.dumps(final, indent=2, ensure_ascii=False) + "\n", "utf-8"
        )
    cost = estimate_run_cost(ledger.calls)
    run = {
        **meta,
        "status": None if outcome is None else outcome.status,
        "attempts": None if outcome is None else outcome.attempts,
        "stage_log": None if outcome is None else outcome.stage_log,
        "error": error,
        "elapsed_s": elapsed,
        "calls": recorder.calls,
        "served_models": sorted(
            {str(c.get("model")) for c in recorder.calls if c.get("model")}
        ),
        "input_tokens": sum(int(c.get("input_tokens") or 0) for c in recorder.calls),
        "output_tokens": sum(
            int(c.get("output_tokens") or 0) for c in recorder.calls
        ),
        "estimated_cost_usd": str(cost.amount_usd),
        "estimate_complete": cost.complete,
        "provider_reported_spend_usd": (
            None
            if usage_before is None or usage_after is None
            else round(usage_after - usage_before, 6)
        ),
    }
    if outcome is not None:
        report = outcome.report
        (out / "report.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n", "utf-8"
        )
        run["fill_rate"] = report.get("fill_rate") if isinstance(report, dict) else None
    (out / "run.json").write_text(json.dumps(run, indent=2, default=str) + "\n", "utf-8")
    summary = {k: run[k] for k in ("label", "status", "error", "elapsed_s",
                                   "served_models", "estimated_cost_usd",
                                   "provider_reported_spend_usd")}
    print(json.dumps({"done": summary}, default=str), flush=True)
    return 0 if final is not None else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--arm", required=True, choices=["old", "new"])
    parser.add_argument("--force-cap", type=int, default=None)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
