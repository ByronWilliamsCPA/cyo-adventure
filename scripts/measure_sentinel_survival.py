"""Measure whether sentinels survive the fill LLM's first attempt (plan 3.4).

Story personalization (ADR-023) wraps a personalizable slot's value in a
``{~SLOTID:GenericWord~}`` sentinel before the fill LLM sees it; the fill step
must reproduce that token verbatim, or the fail-closed
``validator.sentinel_integrity`` gate discards the fill. Plan section 3.4
calls this "the single biggest unknown in P1/P2" and requires a measurement,
not a design guess, before P4 onward (data model, consent, UI) is scheduled.

This script is the ONLY place in the codebase that calls the paid
``generation.orchestrator.fill_skeleton`` boundary on behalf of this
measurement. It:

1. Loads (or authors) fixture specimens from real catalog skeletons+contracts
   (``cyo_adventure.measurement.fixtures``), since no contract on disk yet
   declares a personalizable slot (the dormancy fact).
2. Runs each specimen through ``fill_skeleton`` FIRST-ATTEMPT-ONLY
   (``max_repairs=0``, the default; see the module docstring note below) for
   every requested provider.
3. Classifies each result against the plan 3.4 failure taxonomy
   (``cyo_adventure.measurement.taxonomy``).
4. Aggregates the clean-pass rate, per-provider variance, and retry-cost
   projection (``cyo_adventure.measurement.report``), writing both a JSON and
   a markdown report under ``--out-dir/<run-slug>/``.

With ``--save-fills``, every trial that produces a document is additionally
persisted under ``--out-dir/<run-slug>/fills/<index>-<provider>-<slug>.json``
(specimen slug, provider, slot bindings, bound skeleton, and the filled
storybook exactly as ``classify_fill`` received it), so a later, separate
analysis (``scripts/prototype_sentinel_reinsertion.py``) can recompute
expectations against the saved fills without re-running generation. Without
the flag, this script's output is unchanged: no ``fills/`` directory is ever
created.

**First-attempt-only measurement.** ``fill_skeleton`` has an internal repair
loop (``max_repairs``, default 3 on the function itself) that re-prompts on
soft-gate findings and could perturb sentinel state before this script
observes it. With ``settings=None`` (this script never passes Stage 1
settings) and ``max_repairs=0``, ``_run_repair_loop`` executes zero iterations
in every branch (a blocked gate stops immediately since ``attempts >=
max_repairs`` is true at attempt 0; a clean gate stops immediately since no
Stage 1 config is present) -- confirmed by reading
``generation/orchestrator.py``'s ``_next_repair_prompt``/``_run_repair_loop``.
So the document this script observes is always the raw, unrepaired first
attempt, never a repaired one. This script does NOT implement the production
one-retry policy; the retry-cost projection is arithmetic from the measured
clean-pass rate (``1 - rate``), not a real retry run.

**Scope.** ``--providers mock`` (the default) proves the pipeline runs end to
end without a paid call; the report labels itself a plumbing dry-run, not a
survival number, since the deterministic mock provider echoes a fixed canned
story unrelated to any specimen's structure. Running this script against a
live, paid provider (``anthropic``/``openrouter``/``modal``) is a
human decision with real cost and real credentials; nothing in this repo
triggers that automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.exceptions import (
    ConfigurationError,
    ProviderError,
    ValidationError,
)
from cyo_adventure.generation.orchestrator import fill_skeleton
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.measurement.fixtures import (
    DEFAULT_FIXTURES,
    Specimen,
    build_specimen,
    load_pair,
)
from cyo_adventure.measurement.report import (
    TrialRecord,
    aggregate,
    render_json,
    render_markdown,
)
from cyo_adventure.measurement.taxonomy import RunRecord, classify_fill

if TYPE_CHECKING:
    from cyo_adventure.generation.provider import GenerationProvider

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKELETONS_ROOT = _REPO_ROOT / "skeletons"
_DEFAULT_OUT_DIR = _REPO_ROOT / "results" / "sentinel-survival"
_DEFAULT_SLOTS_PER_STORY = 4
_DEFAULT_COUNT = 30


def _refuses_under_skeletons(out_dir: Path) -> bool:
    """Return whether ``out_dir`` resolves to a path under a ``skeletons`` dir.

    Mirrors ``scripts/mutate_skeleton.py``'s guard: this is a measurement
    scratch output, never a catalog entry, so it must never land under
    ``skeletons/``.

    Args:
        out_dir: The requested output directory.

    Returns:
        bool: True if any path component resolves to ``"skeletons"``.
    """
    return "skeletons" in out_dir.resolve().parts


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["mock"],
        help=(
            "Provider names to run (default: mock only, a plumbing dry-run). "
            "Recognizes mock, anthropic, openrouter, modal (see "
            "generation.provider.build_provider); running a live provider "
            "spends real money and is a human decision, never made here."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=str(_DEFAULT_OUT_DIR),
        help=f"Directory to write the report under (default: {_DEFAULT_OUT_DIR}).",
    )
    parser.add_argument(
        "--band",
        action="append",
        default=None,
        help="Restrict the default fixture set to this band (repeatable).",
    )
    parser.add_argument(
        "--skeletons",
        action="append",
        default=None,
        metavar="BAND:SLUG",
        help=(
            "Override the default fixture set with an explicit band:slug pair "
            "(repeatable)."
        ),
    )
    parser.add_argument(
        "--slots-per-story",
        type=int,
        default=_DEFAULT_SLOTS_PER_STORY,
        help=f"Personalizable slots to flip per specimen (default: {_DEFAULT_SLOTS_PER_STORY}).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=_DEFAULT_COUNT,
        help=f"Total specimen runs per provider, cycling the fixture set (default: {_DEFAULT_COUNT}).",
    )
    parser.add_argument(
        "--max-repairs",
        type=int,
        default=0,
        help="Repair attempts before observing the fill (default: 0, first-attempt-only per plan 3.4).",
    )
    parser.add_argument(
        "--save-fills",
        action="store_true",
        help=(
            "Persist every trial's specimen slug, provider, slot bindings, "
            "bound skeleton, and filled storybook under <run-dir>/fills/ "
            "(default: off, matching prior behavior of discarding fills)."
        ),
    )
    return parser


def _select_fixture_pairs(
    skeletons_arg: list[str] | None, band_arg: list[str] | None
) -> list[tuple[str, str]]:
    """Resolve the ``(band, slug)`` fixture pairs a run should use.

    Args:
        skeletons_arg: Explicit ``BAND:SLUG`` overrides from ``--skeletons``,
            or ``None`` to use the default fixture set.
        band_arg: Bands to restrict the default fixture set to, or ``None``
            for every default pair.

    Returns:
        list[tuple[str, str]]: The resolved ``(band, slug)`` pairs, in a
            stable order.

    Raises:
        ValueError: If a ``--skeletons`` entry is not shaped ``BAND:SLUG``.
    """
    if skeletons_arg:
        pairs: list[tuple[str, str]] = []
        for entry in skeletons_arg:
            band, sep, slug = entry.partition(":")
            if not sep:
                msg = f"--skeletons entry {entry!r} must be shaped BAND:SLUG"
                raise ValueError(msg)
            pairs.append((band, slug))
        return pairs

    pairs = list(DEFAULT_FIXTURES)
    if band_arg:
        wanted = set(band_arg)
        pairs = [pair for pair in pairs if pair[0] in wanted]
    return pairs


def _build_specimens(
    pairs: list[tuple[str, str]], *, slots_per_story: int, count: int
) -> list[Specimen]:
    """Load fixture pairs, build one specimen each, and cycle to reach ``count``.

    Args:
        pairs: The resolved ``(band, slug)`` fixture pairs.
        slots_per_story: Personalizable slots to flip per specimen.
        count: The total number of specimen runs to produce per provider.

    Returns:
        list[Specimen]: ``count`` specimens, cycling through ``pairs`` in
            order.
    """
    specimens = [
        build_specimen(
            *load_pair(_SKELETONS_ROOT, band, slug),
            slug,
            slots_per_story=slots_per_story,
        )
        for band, slug in pairs
    ]
    if not specimens:
        return []
    return [specimens[i % len(specimens)] for i in range(count)]


async def _run_trial(
    specimen: Specimen, provider: GenerationProvider, *, max_repairs: int
) -> tuple[RunRecord, dict[str, object]] | None:
    """Run one specimen through one provider, classify the result, and return the fill.

    Args:
        specimen: The sentinel-bearing specimen to fill.
        provider: The provider to fill with.
        max_repairs: Repair attempts before observing the fill (0 for the
            first-attempt-only measurement; see the module docstring).

    Returns:
        tuple[RunRecord, dict[str, object]] | None: The classified outcome
            paired with the exact filled document ``classify_fill`` scored
            (so ``--save-fills`` can persist precisely what was classified),
            or ``None`` when the fill produced no document at all (a total
            generation failure, distinct from a sentinel-integrity
            violation; see the #EDGE note below).
    """
    # #CRITICAL: security: this harness must never carry real child identity;
    # every specimen's sentinel inner value is a generic default word chosen
    # by cyo_adventure.measurement.fixtures, never a real name.
    # #VERIFY: tests/unit/test_measurement_fixtures.py::test_fixtures_contain_no_real_identity
    pii = PiiContext(child_names=frozenset())
    outcome = await fill_skeleton(
        specimen.bound_skeleton,
        specimen.theme_brief,
        provider,
        pii,
        max_repairs=max_repairs,
        stage1_gate="skipped",
        slot_bindings=specimen.slot_bindings,
    )
    # #EDGE: external-resources: a provider that never produces a parseable
    # document at all (GenerationOutcome.storybook is None) has nothing for
    # check_sentinel_integrity to inspect. This is a total generation failure,
    # not a sentinel-survival data point, so it is skipped rather than folded
    # into the clean-pass denominator; the CLI logs it to stderr so a run with
    # many skips is visible rather than silently undercounted.
    # #VERIFY: with the deterministic mock provider this path is not expected
    # to trigger (the canned story always parses); a live provider run should
    # watch stderr for this warning.
    if outcome.storybook is None:
        return None
    record = classify_fill(specimen.bound_skeleton, outcome.storybook)
    return record, outcome.storybook


def _write_fill(
    fills_dir: Path,
    index: int,
    provider_name: str,
    specimen: Specimen,
    storybook: dict[str, object],
) -> None:
    """Persist one trial's specimen/provider/bindings/skeleton/fill to disk.

    #ASSUME: data integrity: ``bound_skeleton`` and ``slot_bindings`` are
    exactly the values ``fill_skeleton`` was called with (see
    ``_run_trial``), so a later analysis can recompute expectations without
    re-running specimen construction.
    #VERIFY: tests/unit/test_measure_sentinel_survival_cli.py::test_save_fills_writes_recoverable_trial_data

    Args:
        fills_dir: The ``fills/`` directory under this run's output dir;
            created on demand (only when at least one fill is written).
        index: This trial's position in the overall trial sequence, used as
            the filename's sortable prefix. Zero-padded to three digits so
            lexicographic order matches trial order: the reader
            (``prototype_sentinel_reinsertion._analyze_fills``) enumerates
            fills with ``sorted(glob(...))``, and an unpadded prefix would
            sort trial 10 ahead of trial 2.
        provider_name: The provider name this trial ran against.
        specimen: The specimen this trial filled.
        storybook: The exact filled document ``classify_fill`` scored.
    """
    fills_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "specimen_slug": specimen.slug,
        "provider": provider_name,
        "slot_bindings": specimen.slot_bindings,
        "bound_skeleton": specimen.bound_skeleton,
        "filled_storybook": storybook,
    }
    filename = f"{index:03d}-{provider_name}-{specimen.slug}.json"
    (fills_dir / filename).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


async def _run_all(
    specimens: list[Specimen],
    providers: list[str],
    *,
    max_repairs: int,
    fills_dir: Path | None = None,
) -> list[TrialRecord]:
    """Run every specimen through every requested provider.

    Args:
        specimens: The specimens to run.
        providers: Provider names to build (via ``build_provider``) and run.
        max_repairs: Repair attempts before observing each fill.
        fills_dir: When not ``None``, every trial that produces a document is
            additionally persisted here via ``_write_fill`` (``--save-fills``);
            ``None`` (the default) preserves the prior discard-the-fill
            behavior exactly.

    Returns:
        list[TrialRecord]: One record per specimen/provider pair that
            produced a document (skips are logged, not included).
    """
    trials: list[TrialRecord] = []
    for provider_name in providers:
        provider = build_provider(_default_settings, provider_override=provider_name)
        for specimen in specimens:
            try:
                outcome = await _run_trial(specimen, provider, max_repairs=max_repairs)
            # #EDGE: external-resources: a live provider can raise ProviderError
            # (network/API failure, rate limit) mid-run. Catch it per trial so
            # one flaky call skips just this specimen instead of aborting the
            # whole multi-provider run and discarding every trial gathered so
            # far. The deterministic mock provider never raises this.
            # #VERIFY: watch stderr for these skips on a live-provider run.
            except ProviderError as exc:
                sys.stderr.write(
                    " ".join(
                        [
                            f"warning: {provider_name}/{specimen.slug} provider",
                            f"error: {exc}; skipped (not a sentinel-survival",
                            "data point)",
                        ]
                    )
                    + "\n"
                )
                continue
            if outcome is None:
                sys.stderr.write(
                    " ".join(
                        [
                            f"warning: {provider_name}/{specimen.slug} produced no",
                            "document; skipped (not a sentinel-survival data point)",
                        ]
                    )
                    + "\n"
                )
                continue
            record, storybook = outcome
            trials.append(
                TrialRecord(
                    specimen_slug=specimen.slug, provider=provider_name, record=record
                )
            )
            if fills_dir is not None:
                _write_fill(
                    fills_dir, len(trials) - 1, provider_name, specimen, storybook
                )
    return trials


def _run_slug() -> str:
    """Return a filesystem-safe, sortable slug for this run's output directory."""
    return datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    """Run the sentinel-survival measurement and write its report.

    Args:
        argv: Command-line arguments, or ``None`` to use ``sys.argv``.

    Returns:
        int: 0 on success, 1 on any input, fixture, or fill error.
    """
    args = _build_parser().parse_args(argv)

    out_dir = Path(cast("str", args.out_dir))
    if _refuses_under_skeletons(out_dir):
        head = f"refusing: --out-dir {out_dir} resolves under a skeletons/ directory; "
        tail = "this is measurement scratch output, never a catalog entry\n"
        sys.stderr.write(head + tail)
        return 1

    try:
        pairs = _select_fixture_pairs(
            cast("list[str] | None", args.skeletons),
            cast("list[str] | None", args.band),
        )
        if not pairs:
            msg = "no fixture skeleton/contract pairs selected"
            raise ValueError(msg)
        specimens = _build_specimens(
            pairs,
            slots_per_story=cast("int", args.slots_per_story),
            count=cast("int", args.count),
        )
    except (OSError, ValueError, ValidationError, TypeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    providers = cast("list[str]", args.providers)
    save_fills = cast("bool", args.save_fills)
    run_dir = out_dir / _run_slug()
    fills_dir = (run_dir / "fills") if save_fills else None
    try:
        trials = asyncio.run(
            _run_all(
                specimens,
                providers,
                max_repairs=cast("int", args.max_repairs),
                fills_dir=fills_dir,
            )
        )
    except (ConfigurationError, ValidationError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    if not trials:
        sys.stderr.write("error: no trials produced a fill result\n")
        return 1

    data = aggregate(trials)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(
        json.dumps(render_json(data, providers=providers), indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(
        render_markdown(data, providers=providers), encoding="utf-8"
    )

    sys.stdout.write(
        " ".join(
            [
                f"sentinel-survival: {data.clean_runs}/{data.total_runs} clean",
                f"({data.clean_pass_rate:.1%}) [{data.threshold_band}] -> {run_dir}",
            ]
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
